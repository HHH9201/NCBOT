import logging
from typing import Optional

import httpx
from ncatbot.plugin import NcatBotPlugin
from ncatbot.event.qq import GroupMessageEvent, PrivateMessageEvent
from ncatbot.types import PlainText, MessageArray
from ncatbot.core.registry import registrar

from common import GLOBAL_CONFIG

logger = logging.getLogger(__name__)

class TraeAnalytics(NcatBotPlugin):
    name = "trae_analytics"
    version = "1.0.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.backend_url = GLOBAL_CONFIG.get("backend.url", "http://127.0.0.1:8978").rstrip("/")
        admin_list = GLOBAL_CONFIG.get("admin_qq", [])
        self.admin_qq = str(admin_list[0]) if admin_list else "1783069903"
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
        await self._handle_analytics(event)

    @registrar.on_private_message()
    async def on_private_message(self, event: PrivateMessageEvent):
        await self._handle_analytics(event)

    async def _handle_analytics(self, event):
        # 1. 鉴权：仅限管理员
        user_id = str(event.user_id)
        if user_id != self.admin_qq:
            return

        # 2. 匹配指令
        msg = event.raw_message.strip()
        if msg == "查询今日人数":
            try:
                client = await self._get_client()
                resp = await client.get("/api/analytics/today_new_users")
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success"):
                        res_data = data.get("data", {})
                        today_count = res_data.get("today_new_users", 0)
                        cumulative_count = res_data.get("cumulative_since_0420", 0)
                        
                        msg_text = (
                            f"📊 数据统计报告\n"
                            f"─" * 15 + "\n"
                            f"📅 今日新增用户：{today_count} 人\n"
                            f"📈 累计新增(自04-20)：{cumulative_count} 人"
                        )
                        await event.reply(rtf=MessageArray([PlainText(text=msg_text)]))
                    else:
                        await event.reply(rtf=MessageArray([PlainText(text=f"❌ 获取失败: {data.get('message', '未知错误')}")]))
                else:
                    await event.reply(rtf=MessageArray([PlainText(text=f"❌ 后端响应异常 (HTTP {resp.status_code})")]))
            except Exception as e:
                logger.error(f"[analytics] 获取今日人数异常: {e}")
                await event.reply(rtf=MessageArray([PlainText(text=f"❌ 统计服务异常: {str(e)}")]))
