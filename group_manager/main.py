# -*- coding: utf-8 -*-
"""
群管工具插件
功能：
1. 机器人为管理员时，自动撤回非群主/管理员发送的链接和广告关键词消息，并禁言
2. 管理命令（仅群主/管理员可用）：
   - @群员 [@群员 ...] 禁言 [分钟数]  支持批量，默认10分钟
   - @群员 [@群员 ...] 解除禁言      支持批量
   - @群员 踢了                      直接移除该群员
"""
import logging
import re
import time

from ncatbot.plugin import BasePlugin
from ncatbot.event.qq import GroupMessageEvent
from ncatbot.types import PlainText, MessageArray
from ncatbot.core import registrar

logger = logging.getLogger("group_manager")

# 目标群号（支持多个群）
TARGET_GROUP_IDS = {695934967, 894356872}
# 禁言时长（秒）- 自动检测违规用
BAN_DURATION = 60
# 默认禁言分钟数 - 管理命令用
DEFAULT_BAN_MINUTES = 10
# 机器人角色缓存有效期（秒）
ROLE_CACHE_TTL = 300

# 广告关键词列表
AD_KEYWORDS = [
    "加微信", "加V", "加微", "加v", "加Q", "加q",
    "代理", "代购", "代刷",
    "刷单", "刷赞", "刷量",
    "赚钱", "日入", "月入", "暴利",
    "兼职", "副业", "躺赚",
    "网赚", "引流", "变现",
    "色情", "赌博", "彩票", "博彩",
    "棋牌", "娛樂", "娱乐城",
    "送彩金", "注册就送", "首充",
]

# 链接检测正则
URL_PATTERN = re.compile(
    r'https?://|www\.|[a-zA-Z0-9-]+\.(?:com|cn|net|org|xyz|top|vip|cc|me|info|io|live|club)'
)


class GroupManager(BasePlugin):
    name = "group_manager"
    version = "1.0.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bot_id = None
        self._role_cache = {}  # {group_id: (is_admin, timestamp)}

    async def on_load(self):
        logger.info(f"[{self.name}] 插件已加载，版本: {self.version}")

    async def _get_bot_id(self):
        """获取机器人 QQ 号（缓存）"""
        if self._bot_id is None:
            try:
                info = await self.api.qq.query.get_login_info()
                self._bot_id = info.user_id
            except Exception as e:
                logger.warning(f"获取机器人 QQ 号失败: {e}")
        return self._bot_id

    async def _is_bot_admin(self, group_id):
        """检查机器人是否为群管理员（带缓存）"""
        now = time.time()
        cached = self._role_cache.get(group_id)
        if cached and (now - cached[1]) < ROLE_CACHE_TTL:
            return cached[0]
        try:
            bot_id = await self._get_bot_id()
            if bot_id is None:
                return False
            member = await self.api.qq.query.get_group_member_info(group_id, bot_id)
            role = getattr(member, "role", "") or ""
            is_admin = role in ("owner", "admin")
            self._role_cache[group_id] = (is_admin, now)
            return is_admin
        except Exception as e:
            logger.warning(f"检查机器人权限失败: {e}")
            return False

    @registrar.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent):
        try:
            group_id = int(event.group_id)
            if group_id not in TARGET_GROUP_IDS:
                return
        except (TypeError, ValueError):
            return

        sender_id = event.user_id
        raw = event.raw_message or ""
        msg_id = event.message_id

        # 获取发送者角色
        sender_role = ""
        try:
            member = await self.api.qq.query.get_group_member_info(group_id, sender_id)
            sender_role = getattr(member, "role", "") or ""
        except Exception:
            pass

        # ===== 管理命令处理（仅群主/管理员可用）=====
        if sender_role in ("owner", "admin"):
            bot_id = await self._get_bot_id()
            # 提取所有被 @ 的 QQ 号（排除机器人自己）
            at_ids = [
                int(t) for t in re.findall(r"\[CQ:at,qq=(\d+)\]", raw)
                if bot_id is None or int(t) != int(bot_id)
            ]

            # @群员 [@群员 ...] 解除禁言  支持批量（先判断，避免被"禁言"误匹配）
            if at_ids and re.search(r"(解除禁言|解禁|取消禁言)", raw):
                await self._unban_members(group_id, at_ids, sender_id)
                return
            # @群员 [@群员 ...] 禁言 [分钟数]  支持批量
            if at_ids and "禁言" in raw:
                ban_match = re.search(r"禁言\s*(\d+)?", raw)
                minutes = int(ban_match.group(1)) if ban_match and ban_match.group(1) else DEFAULT_BAN_MINUTES
                await self._ban_members(group_id, at_ids, minutes, sender_id)
                return
            # @群员 踢了
            kick_match = re.search(r"\[CQ:at,qq=(\d+)\].*?踢了", raw)
            if kick_match:
                target_id = int(kick_match.group(1))
                await self._kick_member(group_id, target_id, sender_id)
                return

        # 群主/管理员的消息不做事后检测
        if sender_role in ("owner", "admin"):
            return

        # 检查机器人是否为管理员
        if not await self._is_bot_admin(group_id):
            return

        # 检测链接
        if URL_PATTERN.search(raw):
            await self._handle_violation(group_id, sender_id, msg_id, "发送链接")
            return

        # 检测广告关键词
        for keyword in AD_KEYWORDS:
            if keyword in raw:
                await self._handle_violation(group_id, sender_id, msg_id, f"广告关键词: {keyword}")
                return

    async def _get_member_name(self, group_id, user_id):
        """获取群成员昵称（优先群名片，其次昵称，最后用QQ号）"""
        try:
            member = await self.api.qq.query.get_group_member_info(group_id, user_id)
            card = getattr(member, "card", "") or ""
            nickname = getattr(member, "nickname", "") or ""
            name = card or nickname
            return f"{name}({user_id})" if name else str(user_id)
        except Exception:
            return str(user_id)

    async def _ban_members(self, group_id, target_ids, minutes, operator_id):
        """批量禁言群员"""
        duration = minutes * 60
        names = []
        failed = []
        for tid in target_ids:
            try:
                await self.api.qq.manage.set_group_ban(group_id, tid, duration)
                name = await self._get_member_name(group_id, tid)
                names.append(name)
            except Exception as e:
                logger.error(f"禁言 {tid} 失败: {e}")
                failed.append(str(tid))

        if names:
            logger.info(f"管理员 {operator_id} 批量禁言 {names} {minutes}分钟")
            text = f"已禁言 {len(names)} 人 {minutes}分钟：\n" + "\n".join(names)
            if failed:
                text += f"\n⚠️ 以下 {len(failed)} 人禁言失败（可能是管理员/权限不足）：\n" + "\n".join(failed)
        else:
            text = "禁言失败，可能是权限不足或对方是管理员"

        await self.api.qq.post_group_msg(
            group_id=group_id,
            rtf=MessageArray([PlainText(text=text)]),
        )

    async def _kick_member(self, group_id, target_id, operator_id):
        """踢出指定群员"""
        target_name = await self._get_member_name(group_id, target_id)
        try:
            await self.api.qq.manage.set_group_kick(group_id, target_id, False)
            logger.info(f"管理员 {operator_id} 踢出 {target_id}")
            await self.api.qq.post_group_msg(
                group_id=group_id,
                rtf=MessageArray([PlainText(
                    text=f"已移除群员 {target_name}"
                )]),
            )
        except Exception as e:
            logger.error(f"踢人失败: {e}")
            await self.api.qq.post_group_msg(
                group_id=group_id,
                rtf=MessageArray([PlainText(
                    text=f"踢人失败，可能是权限不足或对方是管理员"
                )]),
            )

    async def _unban_members(self, group_id, target_ids, operator_id):
        """批量解除禁言"""
        names = []
        failed = []
        for tid in target_ids:
            try:
                await self.api.qq.manage.set_group_ban(group_id, tid, 0)
                name = await self._get_member_name(group_id, tid)
                names.append(name)
            except Exception as e:
                logger.error(f"解除禁言 {tid} 失败: {e}")
                failed.append(str(tid))

        if names:
            logger.info(f"管理员 {operator_id} 批量解除禁言 {names}")
            text = f"已解除 {len(names)} 人的禁言：\n" + "\n".join(names)
            if failed:
                text += f"\n⚠️ 以下 {len(failed)} 人解禁失败：\n" + "\n".join(failed)
        else:
            text = "解除禁言失败，可能是权限不足"

        await self.api.qq.post_group_msg(
            group_id=group_id,
            rtf=MessageArray([PlainText(text=text)]),
        )

    async def _handle_violation(self, group_id, user_id, msg_id, reason):
        """处理违规：撤回 + 禁言 + 提示"""
        try:
            await self.api.qq.delete_msg(msg_id)
            logger.info(f"已撤回 {user_id} 的消息（{reason}）")
        except Exception as e:
            logger.error(f"撤回消息失败: {e}")
            # 撤回失败可能是权限不足，更新缓存
            self._role_cache[group_id] = (False, time.time())
            return

        # 禁言
        try:
            await self.api.qq.manage.set_group_ban(group_id, user_id, BAN_DURATION)
            logger.info(f"已禁言 {user_id} {BAN_DURATION}秒（{reason}）")
        except Exception as e:
            logger.error(f"禁言失败: {e}")

        # 发送提示
        try:
            await self.api.qq.post_group_msg(
                group_id=group_id,
                rtf=MessageArray([PlainText(
                    text=f"⚠️ 已撤回并禁言用户 {user_id}（{BAN_DURATION}秒）\n原因: {reason}"
                )]),
            )
        except Exception as e:
            logger.error(f"发送提示失败: {e}")
