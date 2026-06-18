# -*- coding: utf-8 -*-
"""
群进群申请审核插件
功能：收到 695934967 群的进群申请时，发送通知到群里
引用通知消息回复 1 同意 | 回复 2 拒绝（支持多人同时申请分别审核）
"""
import logging
import re
import time

from ncatbot.plugin import BasePlugin
from ncatbot.event.qq import GroupMessageEvent, GroupRequestEvent
from ncatbot.types import PlainText, MessageArray
from ncatbot.core import registrar

logger = logging.getLogger("group_join_review")

# 目标群号（支持多个群）
TARGET_GROUP_IDS = {695934967, 894356872}
# 待处理申请过期时间（秒），30 分钟未审核自动清理
EXPIRE_SECONDS = 1800


def _parse_comment(comment: str) -> str:
    """解析申请信息，NapCat 下 comment 格式可能为 '问题：xxx\\n答案：yyy'"""
    if not comment:
        return "无"
    if "答案：" in comment:
        parts = comment.split("答案：", 1)
        return parts[1].strip() if len(parts) > 1 else comment
    if "答案:" in comment:
        parts = comment.split("答案:", 1)
        return parts[1].strip() if len(parts) > 1 else comment
    return comment.strip()


def _format_level(level) -> str:
    """格式化等级（QQ 等级数字转太阳/月亮/星星）"""
    if not level:
        return "未知"
    try:
        lv = int(level)
        if lv <= 0:
            return "0"
        sun = lv // 64
        moon = (lv % 64) // 16
        star = (lv % 16) // 4
        parts = []
        if sun:
            parts.append(f"☀{sun}")
        if moon:
            parts.append(f"🌙{moon}")
        if star:
            parts.append(f"⭐{star}")
        return " ".join(parts) if parts else str(lv)
    except (ValueError, TypeError):
        return str(level)


def _extract_reply_id(raw_message) -> str:
    """从消息中提取引用回复的 message_id"""
    if not raw_message:
        return None
    match = re.search(r'\[CQ:reply,id=(\d+)\]', str(raw_message))
    return match.group(1) if match else None


def _extract_text(raw_message) -> str:
    """从消息中提取纯文本内容（去掉所有 CQ 码）"""
    if not raw_message:
        return ""
    return re.sub(r'\[CQ:[^\]]+\]', '', str(raw_message)).strip()


class GroupJoinReview(BasePlugin):
    name = "group_join_review"
    version = "1.1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 存储待处理的进群申请: {message_id(str): {"user_id":..., "flag":..., "sub_type":..., "nickname":..., "timestamp":...}}
        self.pending_requests = {}

    def _cleanup_expired(self):
        """清理过期的待处理申请"""
        now = time.time()
        expired = [k for k, v in self.pending_requests.items() if now - v.get("timestamp", 0) > EXPIRE_SECONDS]
        for k in expired:
            self.pending_requests.pop(k, None)
        if expired:
            logger.info(f"清理了 {len(expired)} 个过期的待处理申请")

    @registrar.qq.on_group_request()
    async def on_group_request(self, event: GroupRequestEvent):
        """收到进群申请"""
        try:
            group_id = int(event.group_id)
            if group_id not in TARGET_GROUP_IDS:
                return
        except (TypeError, ValueError):
            return

        # 清理过期申请
        self._cleanup_expired()

        user_id = event.user_id
        comment = _parse_comment(event.comment)
        flag = event.flag
        sub_type = event.sub_type or "add"

        # 获取用户信息（陌生人信息，不含等级）
        nickname = str(user_id)
        sex = ""
        age = ""
        level = ""

        try:
            info = await self.api.qq.query.get_stranger_info(user_id)
            nickname = getattr(info, "nickname", None) or nickname
            raw_sex = getattr(info, "sex", None)
            if raw_sex == "male":
                sex = "男"
            elif raw_sex == "female":
                sex = "女"
            raw_age = getattr(info, "age", 0)
            if raw_age and int(raw_age) > 0:
                age = str(raw_age)
            level = _format_level(getattr(info, "level", None))
        except Exception as e:
            logger.warning(f"获取用户 {user_id} 信息失败: {e}")

        # 尝试获取群成员等级（用户可能曾在群里）
        try:
            member = await self.api.qq.query.get_group_member_info(group_id, user_id)
            mem_level = getattr(member, "level", None)
            if mem_level:
                level = _format_level(mem_level)
        except Exception:
            pass

        # 构建通知消息（只显示有效字段）
        lines = [
            "📋 进群申请通知",
            "━━━━━━━━━━━━━",
            f"用户：{nickname}（{user_id}）",
        ]
        if level and level != "未知":
            lines.append(f"等级：{level}")
        if sex:
            lines.append(f"性别：{sex}")
        if age:
            lines.append(f"年龄：{age}")
        lines.append(f"申请信息：{comment}")
        lines.append("━━━━━━━━━━━━━")
        lines.append("引用本消息回复 1 同意 | 2 拒绝")
        lines.append("直接回复 1 全部同意 | 2 全部拒绝")
        msg = "\n".join(lines)

        try:
            result = await self.api.qq.post_group_msg(
                group_id=group_id,
                rtf=MessageArray([PlainText(text=msg)]),
            )
            # 获取发送的消息ID（兼容多种返回格式）
            msg_id = None
            if result is not None:
                if hasattr(result, 'message_id'):
                    msg_id = result.message_id
                elif isinstance(result, dict):
                    msg_id = result.get('message_id')
                elif hasattr(result, 'data'):
                    data = result.data
                    if isinstance(data, dict):
                        msg_id = data.get('message_id')
                    elif hasattr(data, 'message_id'):
                        msg_id = data.message_id

            if msg_id is not None:
                self.pending_requests[str(msg_id)] = {
                    "user_id": user_id,
                    "flag": flag,
                    "sub_type": sub_type,
                    "nickname": nickname,
                    "group_id": group_id,
                    "timestamp": time.time(),
                }
                logger.info(f"已发送进群申请通知到群 {group_id}（用户 {user_id}，消息ID {msg_id}）")
            else:
                logger.warning(f"发送通知成功但未获取到消息ID（用户 {user_id}），结果: {result}")
        except Exception as e:
            logger.error(f"发送进群申请通知失败: {e}")

    @registrar.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent):
        """处理审核回复
        - 引用通知消息回复 1/2：审核该条对应的单个申请
        - 直接回复 1/2：全部同意 / 全部拒绝
        """
        try:
            group_id = int(event.group_id)
            if group_id not in TARGET_GROUP_IDS:
                return
        except (TypeError, ValueError):
            return

        raw = event.raw_message if hasattr(event, "raw_message") and event.raw_message else ""

        # 提取纯文本内容（去掉 CQ 码）
        text = _extract_text(raw)
        if text not in ("1", "2"):
            return

        # 清理过期申请
        self._cleanup_expired()

        # 没有待处理申请则忽略
        if not self.pending_requests:
            return

        # 仅群主或管理员可审核
        sender_id = event.user_id
        try:
            member = await self.api.qq.query.get_group_member_info(group_id, sender_id)
            role = getattr(member, "role", "") or ""
        except Exception as e:
            logger.warning(f"获取发送者 {sender_id} 群成员信息失败: {e}")
            return
        if role not in ("owner", "admin"):
            return

        approve = (text == "1")
        action_text = "同意" if approve else "拒绝"
        emoji = "✅" if approve else "❌"

        # 提取引用回复的 message_id
        reply_msg_id = _extract_reply_id(raw)

        if reply_msg_id:
            # 引用回复：审核单个申请
            request = self.pending_requests.get(reply_msg_id)
            if not request:
                return
            try:
                await self.api.qq.manage.set_group_add_request(
                    flag=request["flag"],
                    sub_type=request["sub_type"],
                    approve=approve,
                    reason="管理员拒绝" if not approve else "",
                )
                await event.reply(rtf=MessageArray([PlainText(
                    text=f"{emoji} 已{action_text} {request['nickname']}（{request['user_id']}）的进群申请"
                )]))
                self.pending_requests.pop(reply_msg_id, None)
                logger.info(f"已{action_text}用户 {request['user_id']} 的进群申请")
            except Exception as e:
                logger.error(f"{action_text}进群申请失败: {e}")
                await event.reply(rtf=MessageArray([PlainText(text=f"❌ {action_text}失败: {e}")]))
        else:
            # 直接回复：当前群全部同意 / 全部拒绝
            items = [(mid, req) for mid, req in self.pending_requests.items() if req.get("group_id") == group_id]
            if not items:
                return
            success = 0
            fail = 0
            for mid, req in items:
                try:
                    await self.api.qq.manage.set_group_add_request(
                        flag=req["flag"],
                        sub_type=req["sub_type"],
                        approve=approve,
                        reason="管理员拒绝" if not approve else "",
                    )
                    self.pending_requests.pop(mid, None)
                    success += 1
                    logger.info(f"批量{action_text}：用户 {req['user_id']}")
                except Exception as e:
                    fail += 1
                    logger.error(f"批量{action_text}用户 {req['user_id']} 失败: {e}")
            await event.reply(rtf=MessageArray([PlainText(
                text=f"{emoji} 批量{action_text}完成：成功 {success} | 失败 {fail}"
            )]))

    async def on_load(self):
        logger.info(f"[{self.name}] 插件已加载，版本: {self.version}")

    async def on_unload(self):
        self.pending_requests.clear()
