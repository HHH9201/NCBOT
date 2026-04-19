# /home/hjh/BOT/NCBOT/plugins/trae_stats/main.py
import logging
from typing import Optional

import httpx
from ncatbot.plugin import NcatBotPlugin
from ncatbot.event.qq import GroupMessageEvent
from ncatbot.types import PlainText, MessageArray
from ncatbot.core.registry import registrar

from common import GLOBAL_CONFIG
from common.permissions import permission_manager

logger = logging.getLogger(__name__)

class TraeStats(NcatBotPlugin):
    name = "trae_stats"
    version = "1.0.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.backend_url = GLOBAL_CONFIG.get("backend.url", "http://127.0.0.1:8978").rstrip("/")
        self.http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self.http_client is None:
            self.http_client = httpx.AsyncClient(base_url=self.backend_url, timeout=10)
        return self.http_client

    async def on_load(self):
        await self._get_client()
        logger.info("%s v%s 已加载", self.name, self.version)

    async def on_unload(self):
        if self.http_client is not None:
            await self.http_client.aclose()
            self.http_client = None

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
                client = await self._get_client()
                resp = await client.get("/api/task/stats")
                if resp.status_code == 200:
                    count = resp.json().get("data", {}).get("available_count", 0)
                    await event.reply(rtf=MessageArray([PlainText(text=f"📊 当前可用额度：{count}")]))
                else:
                    await event.reply(rtf=MessageArray([PlainText(text="❌ 接口响应异常")]))
            except Exception as e:
                logger.error("[trae_stats] 获取额度失败: %s", e)
                await event.reply(rtf=MessageArray([PlainText(text=f"❌ 获取失败: {str(e)}")]))
