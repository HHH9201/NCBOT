# /home/hjh/BOT/NCBOT/plugins/xydj/main.py
# -*- coding: utf-8 -*-
"""
咸鱼单机（全能版）
- 整合了数据库搜索与同步逻辑
- 支持扫码解锁与机器人发消息同步
- 适配 NcatBot 5.0 框架
"""
import re
import os
import time
import json
import asyncio
import logging
import httpx
import base64
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from ncatbot.plugin import BasePlugin
from ncatbot.event.qq import GroupMessageEvent
from ncatbot.types import PlainText, Reply, MessageArray, Image
from ncatbot.types.qq import ForwardConstructor
from ncatbot.core import registrar
from dotenv import load_dotenv

# 加载根目录 .env 配置
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
load_dotenv(env_path)

# 引入全局服务和配置
from common import (
    GLOBAL_CONFIG, db_manager
)
from common.db_permissions import db_permission_manager

# 配置更清爽的日志格式
logger = logging.getLogger("xydj")

# 从环境变量读取配置 (带默认值)
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8978")
APP_ID = os.getenv("APP_ID", "card_sender")
APP_SECRET = os.getenv("APP_SECRET", "card_sender_secret")

async def search_game_from_db(game_name: str):
    """从数据库搜索游戏（模糊匹配中英文，且必须有下载链接）"""
    print(f"[DB Search] 正在从数据库搜索: {game_name}")
    try:
        cloud_games = await db_permission_manager.search_game_resources(game_name)
        if not cloud_games:
            return "暂未收录", None
        
        text_lines = []
        games = []
        
        # 过滤必须有下载链接的游戏
        valid_cloud_games = []
        url_fields = [
            "baidu_url", "quark_url", "uc_url", "pan123_url", 
            "xunlei_url", "mobile_url", "online_url", "patch_url"
        ]
        
        for g_data in cloud_games:
            has_link = any(g_data.get(f) for f in url_fields)
            if has_link:
                valid_cloud_games.append(g_data)
        
        if not valid_cloud_games:
            # 虽然找到了名字匹配的，但都没有链接，也返回提示
            return "暂未收录", None

        for idx, game_data in enumerate(valid_cloud_games):
            zh_name = game_data.get("zh_name", game_data.get("name", ""))
            en_name = game_data.get("en_name", "")
            display_text = f"{idx+1}. {zh_name}"
            if en_name: display_text += f"\n   英文名: {en_name}"
            text_lines.append(display_text)
            
            games.append({
                "from_db": True,
                "db_data": game_data,
                "title": zh_name
            })
        return "\n\n".join(text_lines), games
    except Exception as e:
        logger.error(f"[DB Search] 搜索失败: {e}")
        return "搜索服务异常，请稍后再试", None

class SearchSession:
    def __init__(self, user_id, games, task=None, original_msg_id=None):
        self.user_id = user_id
        self.games = games
        self.task = task
        self.processing = False
        self.original_msg_id = original_msg_id

class Xydj(BasePlugin):
    name = "xydj"
    version = "1.2.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sessions = {}
        # 统一使用 self.api.misc 或 httpx
        self.http_client = httpx.AsyncClient(timeout=30)

    async def check_user_is_vip(self, user_id):
        """检查用户VIP状态，返回 (is_vip, expired_at)"""
        try:
            url = f"{BACKEND_URL}/api/user/info?platform=qq_id&platform_id={user_id}"
            resp = await self.http_client.get(url, headers={"app-id": APP_ID, "app-secret": APP_SECRET})
            if resp.status_code == 200:
                data = resp.json()
                return data.get("is_vip", False), data.get("vip_expired_at")
        except Exception as e:
            logger.error(f"[VIP Check] 失败: {e}")
        return False, None

    def _build_complete_game_content(self, game_data):
        """构建与群消息一致的排版内容"""
        content = []
        zh_name = game_data.get("zh_name", game_data.get("name", "未知游戏"))
        content.append(f"游戏名字：{zh_name}\n")
        
        password = game_data.get("password", "")
        if password: content.append(f"解压密码：【{password}】\n")
        
        pans = [
            ("baidu_url", "百度网盘", "baidu_code"),
            ("quark_url", "夸克网盘", "quark_code"),
            ("uc_url", "UC网盘", "uc_code"),
            ("pan123_url", "123网盘", "pan123_code"),
            ("xunlei_url", "迅雷网盘", "xunlei_code"),
            ("mobile_url", "移动端", "mobile_code"),
            ("online_url", "联机版", "online_code"),
            ("patch_url", "联机补丁", "")
        ]
        
        for key, name, code_key in pans:
            if game_data.get(key):
                line = f"{name}：{game_data[key]}"
                if game_data.get(code_key):
                    line += f" 提取码：【{game_data[code_key]}】"
                content.append(line + "\n")
        
        return content

    async def _send_final_forward(self, group_id, lines, user_id, nickname):
        """发送合并转发消息"""
        try:
            fc = ForwardConstructor()
            fc.attach_text("".join(lines), user_id, nickname)
            await self.api.qq.post_group_forward_msg(group_id, fc.build())
            return True
        except Exception as e:
            logger.error(f"合并转发失败: {e}")
            return False

    async def process_game_resource(self, game, event, original_msg_id=None):
        try:
            user_id = str(event.user_id)
            # 1. VIP 检查
            is_vip, vip_expired_at = await self.check_user_is_vip(user_id)
            if is_vip:
                # 1. 单独发送会员提示 (引用但不@)
                try:
                    date_part = vip_expired_at.split('T')[0]
                    y, m, d = date_part.split('-')
                    tip = f"当前为赞助，有效期至：{y}年{m}月{d}日"
                except:
                    tip = "当前为赞助状态"
                
                # 使用 post_group_msg 配合 MessageArray 发送引用但不 @ 的消息
                msg_id = original_msg_id or event.message_id
                await self.api.qq.post_group_msg(
                    group_id=event.group_id,
                    rtf=MessageArray([Reply(id=msg_id), PlainText(text=tip)])
                )
                
                # 2. 发送资源消息 (合并转发)
                content = self._build_complete_game_content(game["db_data"])
                await self._send_final_forward(event.group_id, content, user_id, event.sender.nickname)
                return

            # 2. 构造同步 Payload (机器人排版)
            content_text = "".join(self._build_complete_game_content(game["db_data"]))
            
            # 3. 请求 Ticket
            ticket_id = None
            res_data = {}
            logger.info(f"[PopReady] Sending Payload: {content_text[:50]}...")
            async with httpx.AsyncClient() as client:
                # 优先从池子拿
                resp = await client.post(
                    f"{BACKEND_URL}/api/task/pop_ready",
                    json={
                        "platform": "qq_id", 
                        "platform_id": user_id, 
                        "app_id": APP_ID, 
                        "resource_payload": content_text
                    },
                    headers={"app-id": APP_ID, "app-secret": APP_SECRET}
                )
                if resp.status_code != 200:
                    # 池子没有则创建
                    resp = await client.post(
                        f"{BACKEND_URL}/api/task/create",
                        json={"platform": "qq_id", "platform_id": user_id, "app_id": APP_ID, "resource_payload": content_text},
                        headers={"app-id": APP_ID, "app-secret": APP_SECRET}
                    )
                
                if resp.status_code == 200:
                    res_data = resp.json()
                    ticket_id = res_data.get("ticket")

            if ticket_id:
                # 4. 下载并发送二维码
                qrcode_url = res_data.get("qrcode_url")
                msg_parts = [Reply(id=event.message_id)]
                try:
                    img_resp = await self.http_client.get(f"{BACKEND_URL}/api/task/qrcode/{ticket_id}", timeout=15)
                    if img_resp.status_code == 200:
                        img_size = len(img_resp.content)
                        logger.info(f"QR Code Size: {img_size} bytes")
                        img_b64 = f"base64://{base64.b64encode(img_resp.content).decode()}"
                        msg_parts.append(Image(file=img_b64))
                    else: 
                        logger.warning(f"获取二维码失败: {img_resp.status_code}")
                        msg_parts.append(Image(file=qrcode_url))
                except Exception as e:
                    logger.error(f"下载二维码异常: {e}")
                    msg_parts.append(Image(file=qrcode_url))

                msg_parts.append(PlainText(text="\n✅ 请长按扫码点击“点击获取”，完成后我将立即在此发送资源链接！QQ内长按二维码也是可以的"))
                
                try:
                    await event.reply(rtf=MessageArray(msg_parts))
                except Exception as e:
                    logger.error(f"发送二维码消息失败: {e}")
                    # 尝试只发送文字提示
                    await event.reply(f"⚠️ 二维码发送失败，请尝试访问: {qrcode_url}\n扫码完成后我将发送资源。")

                # 5. 启动轮询
                asyncio.create_task(self._wait_and_send_resource(event, event.group_id, ticket_id, game, user_id, event.sender.nickname))
        except Exception as e:
            logger.error(f"处理资源失败: {e}")

    async def _wait_and_send_resource(self, event, group_id, ticket_id, game, user_id, nickname):
        content_lines = self._build_complete_game_content(game["db_data"])
        content_text = "".join(content_lines)
        
        for _ in range(45):
            await asyncio.sleep(4)
            try:
                resp = await self.http_client.get(f"{BACKEND_URL}/api/user/get_result?ticket={ticket_id}")
                res = resp.json()
                if res and res.get("status") in ["verified", "claimed"]:
                    # 发送群消息
                    await self._send_final_forward(group_id, content_lines, user_id, nickname)
                    await event.reply(rtf=MessageArray([PlainText(text="🎉 验证成功！资源已在上方以合并转发形式发出。")]))
                    return
            except: pass

    def _cleanup(self, group_id):
        if group_id in self.sessions:
            if self.sessions[group_id].task: self.sessions[group_id].task.cancel()
            del self.sessions[group_id]

    async def countdown(self, event, group_id):
        await asyncio.sleep(20)
        self._cleanup(group_id)
        await event.reply(rtf=MessageArray([PlainText(text="⏰ 操作超时，已取消。")]))

    @registrar.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent):
        msg = event.raw_message.strip()
        
        # 1. 处理序号选择
        session = self.sessions.get(event.group_id)
        if session and event.user_id == session.user_id:
            if msg == "0":
                self._cleanup(event.group_id)
                await event.reply("操作已取消")
                return
            if msg.isdigit() and 1 <= int(msg) <= len(session.games):
                game = session.games[int(msg)-1]
                original_msg_id = session.original_msg_id
                self._cleanup(event.group_id)
                await self.process_game_resource(game, event, original_msg_id=original_msg_id)
                return

        # 2. 处理搜索命令
        if msg.startswith("搜索") or msg.startswith("搜库"):
            game_name = msg[2:].strip()
            if not game_name: return
            
            text_result, games = await search_game_from_db(game_name)
            if not games:
                # 使用 post_group_msg 配合 MessageArray 发送引用但不 @ 的消息，避免 event.reply 产生重复的 @
                await self.api.qq.post_group_msg(
                    group_id=event.group_id,
                    rtf=MessageArray([Reply(id=event.message_id), PlainText(text=text_result)])
                )
                return
            
            if len(games) == 1:
                await self.process_game_resource(games[0], event, original_msg_id=event.message_id)
                return
            
            if len(games) > 1:
                await event.reply(rtf=MessageArray([PlainText(text=f"🎯 发现 {len(games)} 款游戏\n{text_result}\n⏰ 20秒内回复序号选择 | 回复 0 取消")]))
                session = SearchSession(event.user_id, games, original_msg_id=event.message_id)
                session.task = asyncio.create_task(self.countdown(event, event.group_id))
                self.sessions[event.group_id] = session

    async def on_load(self):
        logger.info(f"[{self.name}] 插件已加载，版本: {self.version}")
