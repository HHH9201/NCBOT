"""
测试插件 - 联动版 (Webhook 高性能版)
1. 用户发送 "3" -> 插件请求后端创建任务 -> 发送小程序码给用户
2. 用户扫码点击 "修成正果" -> 后端验证任务 -> 后端主动触发 Webhook
3. 插件收到 Webhook -> 立即回复用户 "测试成功"
"""

import logging
import asyncio
import httpx
import uvicorn
import time
from fastapi import FastAPI, Request as FastRequest
from ncatbot.plugin import NcatBotPlugin
from ncatbot.core import registrar
from ncatbot.event.qq import GroupMessageEvent, PrivateMessageEvent

# 使用框架自带的日志系统
logger = logging.getLogger("CardSender")

# 配置信息
BACKEND_URL = "http://127.0.0.1:8978"
BOT_WEBHOOK_PORT = 8979
BOT_WEBHOOK_URL = f"http://127.0.0.1:{BOT_WEBHOOK_PORT}/webhook"
APP_ID = "card_sender"
APP_SECRET = "card_sender_secret"

# 创建一个全局的 FastAPI 应用用于接收 Webhook
webhook_app = FastAPI()
_current_plugin_instance = None

@webhook_app.post("/webhook")
async def handle_webhook(request: FastRequest):
    """处理来自后端的 Webhook 通知"""
    try:
        data = await request.json()
        ticket = data.get("ticket")
        status = data.get("status")
        
        if status == "verified" and _current_plugin_instance:
            await _current_plugin_instance.reply_task_finished(ticket)
    except Exception as e:
        logger.error(f"解析 Webhook 失败: {e}")
    
    return {"status": "ok"}

class CardSenderPlugin(NcatBotPlugin):
    """联动测试插件"""

    name = "card_sender"
    version = "3.4.0"

    async def on_load(self):
        """插件加载时启动 Webhook 服务"""
        global _current_plugin_instance
        _current_plugin_instance = self
        self.pending_tasks = {} # ticket -> event
        
        # 启动 Webhook 接收端
        config = uvicorn.Config(webhook_app, host="0.0.0.0", port=BOT_WEBHOOK_PORT, log_level="error")
        server = uvicorn.Server(config)
        asyncio.create_task(server.serve())
        logger.info(f"Webhook 服务已就绪: {BOT_WEBHOOK_URL}")

    async def reply_task_finished(self, ticket: str):
        """由 Webhook 触发的回复逻辑"""
        if ticket in self.pending_tasks:
            task_info = self.pending_tasks.pop(ticket)
            event = task_info["event"]
            start_time = task_info["start_time"]
            qrcode_time = task_info["qrcode_time"]
            
            end_time = time.time()
            total_duration = end_time - start_time
            user_action_duration = end_time - qrcode_time
            
            await event.reply("✅ 测试成功")
            logger.info(f"⏱️ 任务完成耗时统计 [Ticket: {ticket}]:")
            logger.info(f"   - 总耗时: {total_duration:.2f}s")
            logger.info(f"   - 用户扫码+点击耗时: {user_action_duration:.2f}s")

    async def _handle_logic(self, event):
        """核心业务逻辑"""
        start_time = time.time()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{BACKEND_URL}/api/task/create",
                    json={
                        "platform": "qq_id",
                        "platform_id": str(event.user_id),
                        "app_id": APP_ID,
                        "callback_url": BOT_WEBHOOK_URL
                    },
                    headers={"app-id": APP_ID, "app-secret": APP_SECRET},
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    ticket = data.get("ticket")
                    qrcode_url = data.get("qrcode_url")
                    
                    if ticket and qrcode_url:
                        qrcode_ready_time = time.time()
                        creation_duration = qrcode_ready_time - start_time
                        
                        self.pending_tasks[ticket] = {
                            "event": event,
                            "start_time": start_time,
                            "qrcode_time": qrcode_ready_time
                        }
                        
                        await event.reply(image=qrcode_url)
                        logger.info(f"⏱️ 任务创建耗时 [Ticket: {ticket}]: {creation_duration:.2f}s")
        except Exception as e:
            logger.error(f"处理失败: {e}")

    @registrar.on_group_command("3")
    async def handle_test_group(self, event: GroupMessageEvent):
        await self._handle_logic(event)

    @registrar.on_private_command("3")
    async def handle_test_private(self, event: PrivateMessageEvent):
        await self._handle_logic(event)

# 插件入口
entry_class = CardSenderPlugin


# 插件入口
entry_class = CardSenderPlugin
