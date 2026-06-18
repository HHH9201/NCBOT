# main.py - Epic 限免插件，适配 NcatBot5
import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Union

import yaml

from ncatbot.plugin import BasePlugin
from ncatbot.event.qq import GroupMessageEvent, PrivateMessageEvent
from ncatbot.types import PlainText, MessageArray
from ncatbot.types.qq.helper import ForwardConstructor
from ncatbot.core import registrar

from .config import plugin_config
from .data_source import (
    get_epic_free,
    subscribe_helper,
    DATA_DIR,
)
from .schedule import scheduler_manage

logger = logging.getLogger("epicfree")

PLUGIN_DIR = Path(__file__).resolve().parent
HISTORY_FILE = DATA_DIR / "push_history.json"

# EpicGameStore 合并转发节点作者信息
EPIC_USER_ID = "2854196320"
EPIC_NICKNAME = "EpicGameStore"

# 喜加一命令正则
EPIC_FREE_PATTERN = re.compile(r"^(epic)?喜(加|\+|＋)(一|1)$")


def _get_message_fingerprint(msg_list: List[dict]) -> str:
    """计算消息列表的指纹（Hash），用于判断内容是否变化"""
    content_str = json.dumps(msg_list, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(content_str.encode("utf-8")).hexdigest()


def _check_and_update_history(job_id: str, msg_list: List[dict]) -> bool:
    """检查该 job_id 是否已经推送过当前内容。返回 True 表示需要推送"""
    current_fingerprint = _get_message_fingerprint(msg_list)
    history_data: Dict[str, str] = {}
    if HISTORY_FILE.exists():
        try:
            history_data = json.loads(HISTORY_FILE.read_text(encoding="UTF-8"))
        except Exception:
            logger.warning("历史记录文件损坏，将重置。")

    last_fingerprint = history_data.get(job_id)
    if last_fingerprint == current_fingerprint:
        return False

    history_data[job_id] = current_fingerprint
    HISTORY_FILE.write_text(
        json.dumps(history_data, ensure_ascii=False, indent=2), encoding="UTF-8"
    )
    return True


def _build_forward(msg_list: List[dict]) -> ForwardConstructor:
    """将消息列表构建为合并转发构造器"""
    fc = ForwardConstructor(user_id=EPIC_USER_ID, nickname=EPIC_NICKNAME)
    for item in msg_list:
        if item.get("type") == "text":
            fc.attach_text(item["content"])
        elif item.get("type") == "image":
            try:
                fc.attach_image(item["content"])
            except Exception as e:
                logger.warning(f"添加图片到合并转发失败，跳过: {e}")
    return fc


class EpicFree(BasePlugin):
    name = "epicfree"
    version = "1.0.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._jobs: Dict[str, asyncio.Task] = {}
        self._super_users = set()

    # ---------- 工具方法 ----------

    @staticmethod
    def _get_job_id(event: Union[GroupMessageEvent, PrivateMessageEvent]) -> str:
        if isinstance(event, GroupMessageEvent):
            return f"epic_group_{event.group_id}"
        return f"epic_private_{event.user_id}"

    @staticmethod
    def _get_sub_info(event: Union[GroupMessageEvent, PrivateMessageEvent]) -> dict:
        if isinstance(event, GroupMessageEvent):
            return {"sub_type": "群聊", "subject": str(event.group_id)}
        return {"sub_type": "私聊", "subject": str(event.user_id)}

    def _has_permission(self, event: GroupMessageEvent) -> bool:
        """检查群聊中的权限"""
        if not plugin_config.superuser_only:
            return True
        if str(event.user_id) in self._super_users:
            return True
        role = getattr(event.sender, "role", "") or ""
        return role in ("admin", "owner")

    # ---------- 定时任务管理 ----------

    async def _run_job(self, job_id: str, sub_info: dict, hour: int, minute: int):
        """定时推送任务的循环体"""
        while job_id in self._jobs:
            now = datetime.now()
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            await asyncio.sleep(wait_seconds)
            if job_id not in self._jobs:
                break
            await self._push_epic_free(job_id, sub_info)

    def _add_job(self, job_id: str, sub_info: dict, hour: int, minute: int):
        """添加或更新定时任务"""
        self._remove_job(job_id)
        task = asyncio.create_task(self._run_job(job_id, sub_info, hour, minute))
        self._jobs[job_id] = task

    def _remove_job(self, job_id: str):
        """移除定时任务"""
        task = self._jobs.pop(job_id, None)
        if task:
            task.cancel()

    async def _push_epic_free(self, job_id: str, sub_info: dict):
        """定时推送的执行函数"""
        logger.info(f"开始执行 Epic 推送任务: {job_id}")

        # 再次检查订阅状态
        all_subs = await subscribe_helper(method="读取")
        if sub_info["subject"] not in all_subs.get(sub_info["sub_type"], []):
            logger.warning(f"任务 {job_id} 启动，但目标 {sub_info['subject']} 已不在订阅列表，自动移除任务。")
            self._remove_job(job_id)
            return

        # 获取游戏信息
        msg_list = await get_epic_free()

        # 检查是否已经推送过这批游戏
        if not _check_and_update_history(job_id, msg_list):
            logger.info(f"任务 {job_id}: 游戏内容未变，已跳过推送。")
            return

        # 发送合并转发消息
        fc = _build_forward(msg_list)
        try:
            if sub_info["sub_type"] == "群聊":
                await self.api.qq.post_group_forward_msg(
                    group_id=int(sub_info["subject"]), forward=fc.build()
                )
            else:
                await self.api.qq.post_private_forward_msg(
                    user_id=int(sub_info["subject"]), forward=fc.build()
                )
            logger.info(f"Epic 推送任务 {job_id} 执行成功。")
        except Exception as e:
            logger.error(f"Epic 推送任务 {job_id} 失败: {e.__class__.__name__}: {e}")

    async def _load_jobs(self):
        """启动时从文件加载所有已保存的定时任务"""
        logger.info("正在从文件加载 Epic 推送任务...")
        try:
            sched_data: Dict[str, str] = json.loads(
                HISTORY_FILE.parent.joinpath("scheduler.json").read_text(encoding="UTF-8")
            ) if HISTORY_FILE.parent.joinpath("scheduler.json").exists() else {}
        except Exception:
            sched_data = {}

        job_count = 0
        for job_id, cron_time in sched_data.items():
            try:
                _, sub_type, subject_id = job_id.split("_", 2)
                sub_type_cn = "群聊" if sub_type == "group" else "私聊"
                sub_info = {"sub_type": sub_type_cn, "subject": subject_id}
                minute, hour = cron_time.split()
                self._add_job(job_id, sub_info, int(hour), int(minute))
                job_count += 1
            except Exception as e:
                logger.error(f"加载 Epic 任务 {job_id} 失败: {e}")
        logger.info(f"成功加载 {job_count} 个 Epic 推送任务。")

    # ---------- 命令处理 ----------

    async def _handle_epic_free(self, event: Union[GroupMessageEvent, PrivateMessageEvent]):
        """手动获取本周免费游戏信息"""
        msg_list = await get_epic_free()
        fc = _build_forward(msg_list)
        try:
            if isinstance(event, GroupMessageEvent):
                await self.api.qq.post_group_forward_msg(
                    group_id=event.group_id, forward=fc.build()
                )
            else:
                await self.api.qq.post_private_forward_msg(
                    user_id=event.user_id, forward=fc.build()
                )
        except Exception as e:
            logger.error(f"发送 Epic 限免信息失败: {e.__class__.__name__}: {e}")
            # 降级为纯文本发送
            try:
                text_parts = [
                    item["content"]
                    for item in msg_list
                    if item.get("type") == "text"
                ]
                text = "\n\n".join(text_parts)
                if isinstance(event, GroupMessageEvent):
                    await self.api.qq.post_group_msg(
                        group_id=event.group_id,
                        rtf=MessageArray([PlainText(text=text)]),
                    )
                else:
                    await self.api.qq.post_private_msg(
                        user_id=event.user_id,
                        rtf=MessageArray([PlainText(text=text)]),
                    )
            except Exception as e2:
                logger.error(f"降级发送也失败: {e2}")

    async def _handle_subscribe(
        self, event: Union[GroupMessageEvent, PrivateMessageEvent], arg_text: str
    ):
        """开启订阅"""
        if not arg_text:
            await self._reply(event, "请提供订阅时间，格式为 HH:MM，例如 epic订阅 8:30")
            return

        try:
            hour, minute = map(int, arg_text.split(":"))
            cron_time = f"{minute} {hour}"
        except ValueError:
            await self._reply(event, "时间格式不正确！请使用 HH:MM 格式，例如 epic订阅 8:30")
            return

        sub_info = self._get_sub_info(event)
        job_id = self._get_job_id(event)

        # 更新订阅者列表
        await subscribe_helper(method="启用", **sub_info)
        # 存储定时任务配置
        await scheduler_manage(job_id=job_id, action="set", time=cron_time)
        # 添加定时任务
        self._add_job(job_id, sub_info, hour, minute)

        await self._reply(
            event,
            f"已成功为本{sub_info['sub_type']}开启 Epic 每日推送，时间：{hour:02d}:{minute:02d}",
        )

    async def _handle_unsubscribe(self, event: Union[GroupMessageEvent, PrivateMessageEvent]):
        """取消订阅"""
        sub_info = self._get_sub_info(event)
        job_id = self._get_job_id(event)

        await subscribe_helper(method="删除", **sub_info)
        await scheduler_manage(job_id=job_id, action="delete")
        self._remove_job(job_id)

        await self._reply(event, f"已为本{sub_info['sub_type']}取消 Epic 每日推送。")

    async def _handle_status(self, event: Union[GroupMessageEvent, PrivateMessageEvent]):
        """查看订阅状态"""
        sub_info = self._get_sub_info(event)
        job_id = self._get_job_id(event)

        all_subs = await subscribe_helper(method="读取")
        if sub_info["subject"] not in all_subs.get(sub_info["sub_type"], []):
            await self._reply(event, f"本{sub_info['sub_type']}当前未订阅 Epic 推送。")
            return

        sched_info = await scheduler_manage(job_id=job_id, action="get")
        if sched_info:
            minute_str, hour_str = sched_info.split()
            minute = int(minute_str)
            hour = int(hour_str)
            await self._reply(
                event,
                f"本{sub_info['sub_type']}已订阅 Epic 推送，每日推送时间为：{hour:02d}:{minute:02d}",
            )
        else:
            await self._reply(
                event,
                f"本{sub_info['sub_type']}已订阅，但未找到推送时间设置。请使用 epic取消订阅 后重新订阅。",
            )

    async def _reply(self, event: Union[GroupMessageEvent, PrivateMessageEvent], text: str):
        """统一回复方法"""
        if isinstance(event, GroupMessageEvent):
            await self.api.qq.post_group_msg(
                group_id=event.group_id,
                rtf=MessageArray([PlainText(text=text)]),
            )
        else:
            await self.api.qq.post_private_msg(
                user_id=event.user_id,
                rtf=MessageArray([PlainText(text=text)]),
            )

    # ---------- 事件监听 ----------

    @registrar.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent):
        text = (event.raw_message or "").strip()
        if not text:
            return

        # 喜加一命令
        if EPIC_FREE_PATTERN.match(text):
            await self._handle_epic_free(event)
            return

        # 订阅命令（需要权限）
        if text == "epic订阅" or text.startswith("epic订阅 "):
            if not self._has_permission(event):
                await self._reply(event, "只有群管理员和主人才能操作订阅哦~")
                return
            arg_text = text[len("epic订阅"):].strip()
            await self._handle_subscribe(event, arg_text)
            return

        # 取消订阅命令
        if text in ("epic取消订阅", "取消epic订阅"):
            if not self._has_permission(event):
                await self._reply(event, "只有群管理员和主人才能操作订阅哦~")
                return
            await self._handle_unsubscribe(event)
            return

        # 订阅状态命令
        if text in ("epic订阅状态", "epic推送状态"):
            await self._handle_status(event)
            return

    @registrar.on_private_message()
    async def on_private_message(self, event: PrivateMessageEvent):
        text = (event.raw_message or "").strip()
        if not text:
            return

        # 喜加一命令
        if EPIC_FREE_PATTERN.match(text):
            await self._handle_epic_free(event)
            return

        # 订阅命令
        if text == "epic订阅" or text.startswith("epic订阅 "):
            arg_text = text[len("epic订阅"):].strip()
            await self._handle_subscribe(event, arg_text)
            return

        # 取消订阅命令
        if text in ("epic取消订阅", "取消epic订阅"):
            await self._handle_unsubscribe(event)
            return

        # 订阅状态命令
        if text in ("epic订阅状态", "epic推送状态"):
            await self._handle_status(event)
            return

    # ---------- 生命周期 ----------

    async def on_load(self):
        # 从 NCBOT 配置读取超级用户
        try:
            root_dir = PLUGIN_DIR.parents[2]
            config_path = root_dir / "config.yaml"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                root = cfg.get("root", "")
                if root:
                    self._super_users.add(str(root))
        except Exception as e:
            logger.warning(f"读取超级用户配置失败: {e}")

        # 加载已保存的定时任务
        await self._load_jobs()
        logger.info(
            f"[epicfree] 插件已加载 v{self.version} | 超级用户: {self._super_users or '无'}"
        )

    async def on_unload(self):
        # 取消所有定时任务
        for job_id in list(self._jobs.keys()):
            self._remove_job(job_id)
