import os
import httpx
import logging
from ncatbot.plugin import NcatBotPlugin
from ncatbot.event.qq import GroupMessageEvent, PrivateMessageEvent
from ncatbot.types import PlainText, MessageArray
from ncatbot.core.registry import registrar

# 加载 .env 获取后端地址
# /home/hjh/BOT/NCBOT/plugins/trae_analytics/main.py -> plugins/ -> root/
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
BACKEND_URL = "http://127.0.0.1:8978"

if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            if line.strip().startswith("BACKEND_URL="):
                BACKEND_URL = line.split("=")[1].strip()
                break

logger = logging.getLogger(__name__)

class TraeAnalytics(NcatBotPlugin):
    name = "trae_analytics"
    version = "1.0.0"
    
    # 授权管理员 QQ
    ADMIN_QQ = "1783069903"

    @registrar.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent):
        await self._handle_analytics(event)

    @registrar.on_private_message()
    async def on_private_message(self, event: PrivateMessageEvent):
        await self._handle_analytics(event)

    async def _handle_analytics(self, event):
        # 1. 鉴权：仅限管理员
        user_id = str(event.user_id)
        if user_id != self.ADMIN_QQ:
            return

        # 2. 匹配指令
        msg = event.raw_message.strip()
        if msg == "查询今日人数":
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    # 调用 WxTool 后端新接口
                    resp = await client.get(f"{BACKEND_URL}/api/analytics/today_new_users")
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("success"):
                            count = data.get("data", {}).get("today_new_users", 0)
                            await event.reply(rtf=MessageArray([PlainText(text=f"📊 今日新增用户数：{count} 人")]))
                        else:
                            await event.reply(rtf=MessageArray([PlainText(text=f"❌ 获取失败: {data.get('message', '未知错误')}")]))
                    else:
                        await event.reply(rtf=MessageArray([PlainText(text=f"❌ 后端响应异常 (HTTP {resp.status_code})")]))
            except Exception as e:
                logger.error(f"[analytics] 获取今日人数异常: {e}")
                await event.reply(rtf=MessageArray([PlainText(text=f"❌ 统计服务异常: {str(e)}")]))
