# welcome.py
# -*- coding: utf-8 -*-
"""
Welcome & Goodbye (No AI Version)
功能：
  1. 记录成员退群次数 & 上次退群时间
  2. 成员加群时随机发送欢迎语
  3. 成员退群时记录并发送告别
  4. 所有时间按北京时间展示
"""
import logging
import yaml
import asyncio
import random
import aiofiles
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List

from ncatbot.plugin import BasePlugin, CompatibleEnrollment
from ncatbot.core.message import MessageChain
from ncatbot.core.event.message_segment.message_segment import Text, At

# ---------- 配置 ----------
CN_TZ = timezone(timedelta(hours=8))
bot = CompatibleEnrollment
logger = logging.getLogger(__name__)

# ---------- 工具 ----------
def _now_beijing() -> str:
    return datetime.utcnow().replace(tzinfo=timezone.utc).astimezone(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")

def _fmt_time(ts: str | None) -> str:
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

# ---------- 插件主体 ----------
class Welcome(BasePlugin):
    name = "Welcome"
    version = "1.0.1"

    def __init__(self, event_bus=None, **kwargs):
        super().__init__(event_bus=event_bus, **kwargs)
        # 数据文件路径：/home/hjh/BOT/NCBOT/data/Welcome/leave_counts.yaml
        self.data_dir = Path("/home/hjh/BOT/NCBOT/data/Welcome")
        self.leave_count_file = self.data_dir / "leave_counts.yaml"
        
        # 配置文件路径：/home/hjh/BOT/NCBOT/plugins/welcome/tool/config.yaml
        self.config_file = Path(__file__).parent / "tool" / "config.yaml"
        
        self.leave_records: Dict[str, dict] = {}
        self.welcome_messages: List[str] = []
        self.goodbye_template: str = "成员 {user_id} 已离开，这是第 {count} 次离开，有缘再见👋"
        
        self._ensure_dir()
        
        # 同步加载一次配置和数据（初始化）
        self._load_sync()

    def _ensure_dir(self):
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
            # 将数据转为 YAML 字符串
            data_str = yaml.dump(self.leave_records, allow_unicode=True)
            async with aiofiles.open(self.leave_count_file, "w", encoding="utf-8") as f:
                await f.write(data_str)
        except Exception as e:
            logger.error(f"[Welcome] 保存数据失败: {e}")

    def _norm(self, rec):
        if isinstance(rec, int):
            return {"count": rec, "last_leave": None, "history": []}
        return {
            "count": rec.get("count", 0),
            "last_leave": rec.get("last_leave"),
            "history": rec.get("history", [])
        }

    # ---------- 事件 ----------
    @bot.notice_event
    async def on_notice(self, notice):
        """统一处理加群 / 退群"""
        # 处理NoticeEvent对象或dict类型
        if hasattr(notice, 'notice_type'):
            notice_type = notice.notice_type
            group_id = notice.group_id if hasattr(notice, 'group_id') else None
            user_id = str(notice.user_id) if hasattr(notice, 'user_id') else None
        else:
            notice_type = notice.get("notice_type")
            group_id = notice.get("group_id")
            user_id = str(notice.get("user_id"))
        
        if notice_type not in ("group_increase", "group_decrease"):
            return

        # ---- 加群 ----
        if notice_type == "group_increase":
            rec = self.leave_records.setdefault(
                user_id, {"count": 0, "last_leave": None, "history": []}
            )
            
            # 随机选择欢迎语
            welcome_msg = random.choice(self.welcome_messages)
            
            # 如果有退群记录，加上提示
            if rec['last_leave']:
                welcome_msg += f"\n(欢迎回家！上次离开：{_fmt_time(rec['last_leave'])})"

            await self.api.post_group_msg(
                group_id=group_id,
                rtf=MessageChain([At(user_id), Text(" " + welcome_msg)])
            )

        # ---- 退群 ----
        elif notice_type == "group_decrease":
            user_id = str(notice.get("user_id"))          # 被退者 QQ
            rec = self.leave_records.setdefault(
                user_id, {"count": 0, "last_leave": None, "history": []}
            )
            rec["count"] += 1
            rec["last_leave"] = _now_beijing()
            rec["history"].append(rec["last_leave"])
            
            # 异步保存
            await self._save_async()

            # 使用配置的模板
            text = self.goodbye_template.format(user_id=user_id, count=rec['count'])
            await self.api.post_group_msg(
                group_id=group_id,
                rtf=MessageChain([Text(text)])
            )

    async def on_load(self):
        logger.info("[Welcome] 插件已加载，版本 %s", self.version)
