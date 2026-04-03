# /home/hjh/BOT/NCBOT/plugins/welcome/main.py
# NcatBot 5.x 欢迎插件
import logging
import yaml
import asyncio
import random
import aiofiles
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List

from ncatbot.plugin import BasePlugin
from ncatbot.core import registrar
from ncatbot.event.qq import NoticeEvent

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from common.permissions import permission_manager

# 北京时间时区
CN_TZ = timezone(timedelta(hours=8))


def _now_beijing() -> str:
    """获取当前北京时间"""
    return datetime.utcnow().replace(tzinfo=timezone.utc).astimezone(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _fmt_time(ts: str | None) -> str:
    """格式化时间字符串"""
    if not ts:
        return ""
    try:
        return (
            datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            .replace(tzinfo=timezone.utc)
            .astimezone(CN_TZ)
            .strftime("%Y年%m月%d日 %H:%M:%S")
        )
    except Exception:
        return ts


class Welcome(BasePlugin):
    """欢迎插件 - 成员加群欢迎、退群记录和告别"""
    name = "Welcome"
    version = "1.0.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 数据文件路径
        self.data_dir = Path("/home/hjh/BOT/NCBOT/data/Welcome")
        self.leave_count_file = self.data_dir / "leave_counts.yaml"

        # 配置文件路径
        self.config_file = Path(__file__).parent / "tool" / "config.yaml"

        self.leave_records: Dict[str, dict] = {}
        self.welcome_messages: List[str] = []
        self.goodbye_template: str = "成员 {user_id} 已离开，这是第 {count} 次离开，有缘再见👋"

        self._ensure_dir()
        # 同步加载一次配置和数据（初始化）
        self._load_sync()

    def _ensure_dir(self):
        """确保数据目录存在"""
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _load_sync(self):
        """同步加载配置和数据（仅在初始化时调用）"""
        # 加载配置
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
                    self.welcome_messages = config.get("welcome_messages", [])
                    self.goodbye_template = config.get("goodbye_template", self.goodbye_template)
            except Exception as e:
                logger.error(f"[Welcome] 加载配置失败: {e}")

        # 加载数据
        if self.leave_count_file.exists():
            try:
                with open(self.leave_count_file, "r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f) or {}
                    self.leave_records = {str(uid): self._norm(rec) for uid, rec in raw.items()}
            except Exception as e:
                logger.error(f"[Welcome] 加载数据失败: {e}")
                self.leave_records = {}
        else:
            self.leave_records = {}

        # 如果没有配置欢迎语，使用默认兜底
        if not self.welcome_messages:
            self.welcome_messages = ["欢迎新人入群！🎉"]

        logger.debug("[Welcome] 已加载 %d 条退群记录", len(self.leave_records))

    async def _save_async(self):
        """异步保存数据"""
        try:
            data_str = yaml.dump(self.leave_records, allow_unicode=True)
            async with aiofiles.open(self.leave_count_file, "w", encoding="utf-8") as f:
                await f.write(data_str)
        except Exception as e:
            logger.error(f"[Welcome] 保存数据失败: {e}")

    def _norm(self, rec):
        """规范化记录格式"""
        if isinstance(rec, int):
            return {"count": rec, "last_leave": None, "history": []}
        return {
            "count": rec.get("count", 0),
            "last_leave": rec.get("last_leave"),
            "history": rec.get("history", [])
        }

    @registrar.on_notice()
    async def on_notice(self, event: NoticeEvent):
        """处理群通知事件（加群/退群）"""
        # 只处理群相关通知
        if not hasattr(event, 'group_id'):
            return

        notice_type = getattr(event, 'notice_type', None)
        group_id = event.group_id
        user_id = str(getattr(event, 'user_id', None))

        if not notice_type or not user_id:
            return

        # 获取机器人自身的 QQ 号
        self_id = getattr(event, 'self_id', None)

        # ---- 机器人被邀请入群 ----
        if notice_type == "group_increase" and str(user_id) == str(self_id):
            # 机器人加入新群，自动添加到权限数据库
            logger.info(f"🤖 机器人加入新群: {group_id}")
            try:
                # 检查是否已在本地 YAML 配置中
                existing = permission_manager.get_group_config(str(group_id))
                if not existing:
                    # 新群，添加默认配置（全部允许）
                    permission_manager.set_all_plugins(str(group_id), True)
                    logger.info(f"✅ 已自动添加群 {group_id} 到本地权限配置")

                    # 发送入群通知
                    await self.api.qq.post_group_msg(
                        group_id=group_id,
                        text="🎉 大家好！我是机器人，已成功加入本群。\n"
                               "发送 帮助 查看可用功能。\n"
                               "管理员可通过私聊管理本群权限。"
                    )
                else:
                    logger.info(f"📋 群 {group_id} 已存在于本地权限配置")
            except Exception as e:
                logger.error(f"❌ 自动添加群 {group_id} 失败: {e}")
            return

        # 检查插件是否启用（使用本地 YAML 权限）
        if not permission_manager.is_plugin_enabled(str(group_id), "welcome"):
            return

        # ---- 成员加群 ----
        if notice_type == "group_increase":

            rec = self.leave_records.setdefault(
                user_id, {"count": 0, "last_leave": None, "history": []}
            )

            # 随机选择欢迎语
            welcome_msg = random.choice(self.welcome_messages)

            # 如果有退群记录，加上提示
            if rec['last_leave']:
                welcome_msg += f"\n(欢迎回家！上次离开：{_fmt_time(rec['last_leave'])})"

            # 发送欢迎消息
            await self.api.qq.post_group_msg(
                group_id=group_id,
                text=f"[CQ:at,qq={user_id}] {welcome_msg}"
            )

        # ---- 退群 ----
        elif notice_type == "group_decrease":

            rec = self.leave_records.setdefault(
                user_id, {"count": 0, "last_leave": None, "history": []}
            )
            rec["count"] += 1
            rec["last_leave"] = _now_beijing()
            rec["history"].append(rec["last_leave"])

            # 异步保存
            await self._save_async()

            # 使用配置的模板发送告别消息
            text = self.goodbye_template.format(user_id=user_id, count=rec['count'])
            await self.api.qq.post_group_msg(
                group_id=group_id,
                text=text
            )

    async def on_load(self):
        logger.info(f"🚀 {self.name} v{self.version} 已加载")
