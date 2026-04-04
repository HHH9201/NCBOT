# """
# 测试插件 - 联动版 (Webhook 高性能版)
# 1. 用户发送 "3" -> 插件请求后端创建任务 -> 发送小程序码给用户
# 2. 用户扫码点击 "点击获取" -> 后端验证任务 -> 后端主动触发 Webhook
# 3. 插件收到 Webhook -> 立即回复用户 "测试成功"
# """

# import os
# import time
# import asyncio
# import httpx
# import uvicorn
# import logging
# from io import BytesIO
# from dotenv import load_dotenv
# from fastapi import FastAPI, Request as FastRequest, Header, HTTPException
# from ncatbot.plugin import NcatBotPlugin
# from ncatbot.core import registrar
# from ncatbot.event.qq import GroupMessageEvent, PrivateMessageEvent

# # 加载根目录 .env 配置
# # 查找路径：当前文件 -> plugins -> NCBOT 根目录
# env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
# load_dotenv(env_path)

# # 使用框架自带的日志系统
# logger = logging.getLogger("CardSender")

# # 从环境变量读取配置 (带默认值)
# BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8978")
# BOT_WEBHOOK_PORT = int(os.getenv("BOT_WEBHOOK_PORT", "8979"))
# BOT_WEBHOOK_URL = f"http://127.0.0.1:{BOT_WEBHOOK_PORT}/webhook"
# APP_ID = os.getenv("APP_ID", "card_sender")
# APP_SECRET = os.getenv("APP_SECRET", "card_sender_secret")
# WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "cs_8f2d9e1a4b7c6d5e8f0a1b2c3d4e5f6g") 

# # 创建一个全局的 FastAPI 应用用于接收 Webhook
# webhook_app = FastAPI()
# _current_plugin_instance = None

# @webhook_app.post("/webhook")
# async def handle_webhook(request: FastRequest, x_auth_token: str = Header(None)):
#     """处理来自后端的 Webhook 通知 (带鉴权)"""
#     # 鉴权逻辑
#     if x_auth_token != WEBHOOK_TOKEN:
#         logger.warning(f"⚠️ 收到非法的 Webhook 请求，Token 不匹配: {x_auth_token}")
#         raise HTTPException(status_code=403, detail="Invalid Auth Token")
        
#     try:
#         data = await request.json()
#         ticket = data.get("ticket")
#         status = data.get("status")
        
#         if status == "verified" and _current_plugin_instance:
#             await _current_plugin_instance.reply_task_finished(ticket)
#     except Exception as e:
#         logger.error(f"解析 Webhook 失败: {e}")
    
#     return {"status": "ok"}

# class CardSenderPlugin(NcatBotPlugin):
#     """联动测试插件 - 轻量化版"""

#     name = "card_sender"
#     version = "4.0.0"

#     async def on_load(self):
#         """插件加载时启动 Webhook 服务"""
#         global _current_plugin_instance
#         _current_plugin_instance = self
#         self.pending_tasks = {} # ticket -> event
        
#         # 启动 Webhook 接收端
#         config = uvicorn.Config(webhook_app, host="0.0.0.0", port=BOT_WEBHOOK_PORT, log_level="error")
#         server = uvicorn.Server(config)
#         asyncio.create_task(server.serve())
#         logger.info(f"Webhook 服务已就绪: {BOT_WEBHOOK_URL}")

#     async def reply_task_finished(self, ticket: str):
#         """由 Webhook 触发的回复逻辑"""
#         if ticket in self.pending_tasks:
#             task_info = self.pending_tasks.pop(ticket)
#             event = task_info["event"]
#             start_time = task_info["start_time"]
            
#             end_time = time.time()
#             total_duration = end_time - start_time
            
#             await event.reply("✅ 测试成功")
#             logger.info(f"⏱️ 任务完成 [Ticket: {ticket}], 总耗时: {total_duration:.2f}s")

#     async def _handle_logic(self, event, mode="qrcode"):
#         """核心业务逻辑 (已改造为向后端请求预生成资源)"""
#         start_time = time.time()
#         logger.info(f"收到指令 '{mode}', 来自用户: {event.user_id}")
        
#         try:
#             async with httpx.AsyncClient() as client:
#                 # 请求后端获取一个已经上传好七牛云的“现成”票据
#                 response = await client.post(
#                     f"{BACKEND_URL}/api/task/pop_ready",
#                     json={
#                         "platform": "qq_id",
#                         "platform_id": str(event.user_id),
#                         "app_id": APP_ID,
#                         "callback_url": BOT_WEBHOOK_URL,
#                     },
#                     headers={"app-id": APP_ID, "app-secret": APP_SECRET},
#                     timeout=10.0
#                 )
                
#                 if response.status_code == 200:
#                     data = response.json()
#                     ticket = data.get("ticket")
#                     qrcode_url = data.get("qrcode_url") # 后端此时应返回已上传七牛云的 URL
                    
#                     if ticket and qrcode_url:
#                         self.pending_tasks[ticket] = {
#                             "event": event,
#                             "start_time": start_time
#                         }
#                         await event.reply(image=qrcode_url)
#                         logger.info(f"⚡ [后端池子] 获取成功! Ticket: {ticket}, 响应耗时: {time.time() - start_time:.2f}s")
#                 else:
#                     logger.error(f"后端返回错误: {response.status_code} - {response.text}")
#                     await event.reply(f"❌ 后端池子异常: {response.status_code}")
                            
#         except Exception as e:
#             import traceback
#             logger.error(f"处理指令 '{mode}' 发生异常: {e}")
#             logger.error(traceback.format_exc())
#             await event.reply(f"❌ 处理失败: {str(e)}")

#     @registrar.on_group_command("2")
#     async def handle_scheme_group(self, event: GroupMessageEvent):
#         await self._handle_logic(event, mode="scheme")

#     @registrar.on_private_command("2")
#     async def handle_scheme_private(self, event: PrivateMessageEvent):
#         await self._handle_logic(event, mode="scheme")

#     @registrar.on_group_command("3")
#     async def handle_test_group(self, event: GroupMessageEvent):
#         await self._handle_logic(event, mode="qrcode")

#     @registrar.on_private_command("3")
#     async def handle_test_private(self, event: PrivateMessageEvent):
#         await self._handle_logic(event, mode="qrcode")

# # 插件入口
# entry_class = CardSenderPlugin
