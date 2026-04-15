# /home/hjh/BOT/NCBOT/plugins/trae_stats/main.py
import os
import httpx
import logging
from ncatbot.plugin import NcatBotPlugin
from ncatbot.event.qq import GroupMessageEvent, PrivateMessageEvent
from ncatbot.types import PlainText, MessageArray
from ncatbot.core.registry import registrar
from common.permissions import permission_manager

# 加载 .env 获取后端地址
# plugins/trae_stats/main.py -> plugins/ -> root/
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
BACKEND_URL = "http://127.0.0.1:8978"

if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            if line.startswith("BACKEND_URL="):
                BACKEND_URL = line.split("=")[1].strip()
                break

class TraeStats(NcatBotPlugin):
    name = "trae_stats"
    version = "1.0.0"

    @registrar.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent):
        if not permission_manager.is_plugin_enabled(event.group_id, "trae_stats"):
            return
        await self._handle_stats(event)

    async def _handle_stats(self, event):
        # 使用 raw_message 进行匹配
        msg = event.raw_message.strip()
        if msg == "当前额度":
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(f"{BACKEND_URL}/api/task/stats")
                    if resp.status_code == 200:
                        count = resp.json().get("data", {}).get("available_count", 0)
                        # 使用 MessageArray 和 PlainText 形式进行回复
                        await event.reply(rtf=MessageArray([PlainText(text=f"📊 当前可用额度：{count}")]))
                    else:
                        await event.reply(rtf=MessageArray([PlainText(text="❌ 接口响应异常")]))
            except Exception as e:
                await event.reply(rtf=MessageArray([PlainText(text=f"❌ 获取失败: {str(e)}")]))
