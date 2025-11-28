# welcome.py
# -*- coding: utf-8 -*-
"""
Welcome & Goodbye with GPT
功能：
  1. 记录成员退群次数 & 上次退群时间
  2. 成员加群时由 GPT 实时生成**不重复**欢迎语
  3. 成员退群时由 GPT 实时生成**不重复**告别语
  4. 所有时间按北京时间展示
  5. 自带兜底文案，GPT 挂掉也能用
"""
import logging
import yaml
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List

from ncatbot.plugin import BasePlugin, CompatibleEnrollment
from ncatbot.core.message import MessageChain
from ncatbot.core.event.message_segment.message_segment import Text, At

try:
    from openai import AsyncOpenAI
except ImportError:
    raise RuntimeError("请先 pip install openai")

# ---------- 配置 ----------
GPT_API_KEY = "sk-kilwgyrrwhpzhqwvugdjliknqcuvvrdbmltlvythobukelfg"
GPT_BASE_URL = "https://api.siliconflow.cn/v1"
GPT_MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507"         
CN_TZ = timezone(timedelta(hours=8))

client = AsyncOpenAI(api_key=GPT_API_KEY, base_url=GPT_BASE_URL)
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

async def gpt_text(system: str, prompt: str) -> str:
    """异步调 GPT，失败返回空字符串"""
    try:
        rsp = await client.chat.completions.create(
            model=GPT_MODEL,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=120
        )
        return rsp.choices[0].message.content.strip()
    except Exception as e:
        logger.exception("[Welcome] GPT 调用失败：%s", e)
        return ""

# ---------- 插件主体 ----------
class Welcome(BasePlugin):
    name = "Welcome"
    version = "0.0.4"

    def __init__(self, event_bus=None, **kwargs):
        super().__init__(event_bus=event_bus, **kwargs)
        self.leave_count_file = Path(__file__).with_name("leave_count.yaml")
        self.leave_records: Dict[str, dict] = {}
        self._ensure_dir()
        self._load()

    def _ensure_dir(self):
        self.leave_count_file.parent.mkdir(parents=True, exist_ok=True)

    def _load(self):
        if self.leave_count_file.exists():
            with open(self.leave_count_file, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
                self.leave_records = {str(uid): self._norm(rec) for uid, rec in raw.items()}
        else:
            self.leave_records = {}
        logger.info("[Welcome] 已加载 %d 条退群记录", len(self.leave_records))

    def _norm(self, rec):
        if isinstance(rec, int):
            return {"count": rec, "last_leave": None, "history": []}
        return {
            "count": rec.get("count", 0),
            "last_leave": rec.get("last_leave"),
            "history": rec.get("history", [])
        }

    def _save(self):
        with open(self.leave_count_file, "w", encoding="utf-8") as f:
            yaml.dump(self.leave_records, f, allow_unicode=True)

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
            system = "你是一个活泼可爱、喜欢使用颜文字的群助手，全程只用中文。"
            prompt = (f"用户(ID:{user_id})第{rec['count']+1}次加入群聊，"
                      f"上次退群时间：{_fmt_time(rec['last_leave'])}。"
                      "请写一条30字左右的个性化成员进群欢迎语，要求带颜文字，每次风格不同。")
            gpt_welcome = await gpt_text(system, prompt)
            if not gpt_welcome:   # 兜底
                gpt_welcome = f"欢迎回来！上次退群：{_fmt_time(rec['last_leave'])}"

            await self.api.post_group_msg(
                group_id=group_id,
                rtf=MessageChain([At(user_id), Text(" " + gpt_welcome)])
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
            self._save()

            system = "你是一个活泼可爱、喜欢使用颜文字的群助手，全程只用中文。"
            prompt = (f"成员{user_id}已第{rec['count']}次离开群聊，"
                      "请写一条20字左右的个性化告别语，带颜文字，风格与前几次不同。")
            gpt_bye = await gpt_text(system, prompt)
            if not gpt_bye:
                gpt_bye = "有缘再见👋"

            text = f"成员 {user_id} 已离开，这是第 {rec['count']} 次离开，{gpt_bye}"
            await self.api.post_group_msg(
                group_id=group_id,
                rtf=MessageChain([Text(text)])
            )

    async def on_load(self):
        logger.info("[Welcome] 插件已加载，版本 %s", self.version)