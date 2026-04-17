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
from bs4 import BeautifulSoup
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

# 爬虫相关配置
WEB_BASE_URL = "https://www.xianyudanji.top"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.xianyudanji.top/pcdj",
    "Connection": "keep-alive",
}

# 初始 Cookie (回退用)
COOKIES_STR = "_ok4_=rQ82TEEOuj4itJ3txH9Br1uXXyXfrNSaN89XObp23bySYqXJ4iD2DyD/42a1M5E2xpzyS0dlL+kfRyraYlJCSs3ywBbbRIU5JS0chVuySMmMq36w3/f9of54ZkckaRO2; ripro_notice_cookie=1; PHPSESSID=s30mcssb4f080tjpft80meobef; wordpress_logged_in_6ecf6dea701570829ebc52b61ed750f6=HHH9201%7C1777095782%7Co7oQrcnPq61oqMwDEYacKVlvVO5iaKMugxEnwvjlztC%7Cd77b5b34ab5cf82d7347ee524374ee7b930203a0752b5630e9c5fb0f145e0601"

async def get_latest_cookie():
    """动态获取数据库中的最新 Cookie"""
    try:
        db_cookie = await db_permission_manager.get_cookie("xydj")
        if db_cookie:
            return db_cookie
    except:
        pass
    return COOKIES_STR

def get_cookies_dict(cookies_str):
    if not cookies_str: return {}
    return {c.split('=')[0]: c.split('=')[1] for c in cookies_str.split('; ') if '=' in c}

async def search_game_from_web(game_name: str):
    """从网站搜索游戏"""
    search_url = f"{WEB_BASE_URL}/?cat=1&s={game_name}&order=views"
    print(f"[Web Search] 正在从网站搜索: {game_name}")
    try:
        current_cookie = await get_latest_cookie()
        async with httpx.AsyncClient(timeout=15, headers=HEADERS, cookies=get_cookies_dict(current_cookie)) as client:
            resp = await client.get(search_url)
            if resp.status_code != 200:
                logger.error(f"[Web Search] 搜索请求失败: {resp.status_code}")
                return "搜索请求失败", None
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            games = []
            text_lines = []
            
            # 查找文章列表
            items = soup.find_all('article', class_='post')
            if not items:
                # 尝试另一种布局 (item-thumbnail)
                items = soup.find_all('div', class_='item-thumbnail') or soup.find_all('article', class_='item')
            
            for idx, item in enumerate(items):
                title_tag = item.find('h2', class_='entry-title') or item.find('a')
                if title_tag:
                    a_tag = title_tag if title_tag.name == 'a' else title_tag.find('a')
                    if a_tag:
                        detail_url = a_tag.get('href')
                        title = a_tag.get('title') or a_tag.get_text().strip()
                        if detail_url and title:
                            title = re.sub(r'<[^>]+>', '', title).strip()
                            # 过滤非详情页链接
                            if "/pcdj/" not in detail_url and "xianyudanji.top" not in detail_url:
                                continue
                            
                            # 严格过滤：游戏标题必须包含完整的搜索关键词
                            if game_name.lower() not in title.lower():
                                continue
                                
                            games.append({
                                "from_db": False,
                                "title": title,
                                "detail_url": detail_url
                            })
                            text_lines.append(f"{idx+1}. {title} (来自网页)")
            
            if not games:
                return "暂未收录", None
            
            return "\n\n".join(text_lines), games
    except Exception as e:
        logger.error(f"[Web Search] 搜索失败: {e}")
        return "搜索服务异常，请稍后再试", None

async def resolve_redirect(client: httpx.AsyncClient, url: str, referer: str = None):
    """解析重定向链接，增加 Referer 支持"""
    if not url: return url
    url = url.strip().rstrip(':') # 清理末尾可能的冒号或空格
    
    # 处理相对路径
    if url.startswith('/'):
        url = f"{WEB_BASE_URL}{url}"
        
    try:
        headers = HEADERS.copy()
        if referer:
            headers["Referer"] = referer
            
        resp = await client.get(url, follow_redirects=True, headers=headers, timeout=30)
        if "window.location" in resp.text:
            match = re.search(r'window\.location\.(?:replace|href)\s*=\s*["'']([^"'']+)["'']', resp.text)
            if match: return match.group(1)
        return str(resp.url)
    except Exception as e:
        logger.error(f"[Redirect] 解析失败 {url} | 错误: {type(e).__name__}: {e}")
        return url

async def scrape_game_detail_and_save(game_name: str, detail_url: str):
    """抓取游戏详情并存入数据库"""
    logger.info(f"[Web Scrape] 正在抓取详情: {game_name}")
    try:
        current_cookie = await get_latest_cookie()
        async with httpx.AsyncClient(timeout=20, headers=HEADERS, cookies=get_cookies_dict(current_cookie)) as client:
            resp = await client.get(detail_url)
            if resp.status_code != 200:
                return None
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            data_to_save = {"detail_url": detail_url}
            
            # 1. 获取更新时间
            update_time_elem = soup.find('p', class_='info', string=re.compile(r'\d{4}年\d{2}月\d{2}日'))
            if update_time_elem:
                raw_date = update_time_elem.get_text()
                match = re.search(r'(\d{4})年(\d{2})月(\d{2})日', raw_date)
                if match:
                    data_to_save["updated_at"] = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

            # 2. 获取下载区域
            down_widget = soup.find('div', id=re.compile(r'ripro_v2_shop_down-\d+'))
            if not down_widget:
                logger.warning(f"[Web Scrape] 未找到下载区域: {game_name}")
                return None

            game_passwords = []
            cards = down_widget.find_all('div', class_='pan-download-card')
            for card in cards:
                name_elem = card.find('span', class_='pan-name')
                link_elem = card.find('a', class_='pan-download-link')
                pwd_elem = card.find('span', class_='pan-pwd')
                
                if not name_elem: continue
                pan_name = name_elem.get_text().strip()
                
                if "解压密码" in pan_name:
                    pwd = pwd_elem.get('data-clipboard-text', "").strip() if pwd_elem else ""
                    if pwd and pwd not in game_passwords: game_passwords.append(pwd)
                    continue

                if not link_elem: continue
                goto_url = link_elem.get('href', "").strip()
                if not goto_url: continue
                
                target_pan = None
                if "百度网盘" in pan_name: target_pan = "baidu"
                elif "夸克网盘" in pan_name: target_pan = "quark"
                elif "UC网盘" in pan_name: target_pan = "uc"
                elif "123云盘" in pan_name or "123网盘" in pan_name: target_pan = "pan123"
                elif "移动网盘" in pan_name: target_pan = "mobile"
                elif "迅雷" in pan_name: target_pan = "xunlei"
                
                if not target_pan: continue
                
                # 动态设置 Referer 为当前详情页
                final_url = await resolve_redirect(client, goto_url, referer=detail_url)
                pwd = pwd_elem.get('data-clipboard-text', "").strip() if pwd_elem else ""
                
                data_to_save[f"{target_pan}_url"] = final_url
                data_to_save[f"{target_pan}_code"] = pwd

            # 3. 额外信息
            down_info = soup.find('div', class_='down-info')
            if down_info:
                info_items = down_info.find_all('li')
                for item in info_items:
                    label_elem = item.find('p', class_='data-label')
                    val_elem = item.find('p', class_='info')
                    if label_elem and "解压密码" in label_elem.get_text():
                        pwd = val_elem.get_text().strip()
                        if pwd and pwd not in game_passwords: game_passwords.append(pwd)

            if game_passwords:
                data_to_save["password"] = " ".join(game_passwords)

            # 保存到数据库
            await db_permission_manager.save_game_resource(game_name, data_to_save)
            
            # 返回完整的 db_data 结构，以便后续 process_game_resource 使用
            data_to_save["zh_name"] = game_name
            return data_to_save
    except Exception as e:
        logger.error(f"[Web Scrape] 抓取失败: {e}")
        return None

async def search_game_from_db(game_name: str):
    """从数据库搜索游戏（模糊匹配中英文，且必须有下载链接）"""
    print(f"[DB Search] 正在从数据库搜索: {game_name}")
    try:
        cloud_games = await db_permission_manager.search_game_resources(game_name)
        if not cloud_games:
            return "暂未收录", None
        
        text_lines = []
        games = []
        
        # 过滤必须有下载链接的游戏（如果只有补丁链接，视为无效资源）
        valid_cloud_games = []
        main_url_fields = [
            "baidu_url", "quark_url", "uc_url", "pan123_url", 
            "xunlei_url", "mobile_url", "online_url"
        ]
        
        for g_data in cloud_games:
            zh_name = g_data.get("zh_name", g_data.get("name", ""))
            en_name = g_data.get("en_name", "")
            
            # 严格过滤：中/英文名必须包含完整的搜索关键词
            if game_name.lower() not in zh_name.lower() and game_name.lower() not in en_name.lower():
                continue

            # 必须拥有至少一个主下载链接（补丁链接不算）
            has_main_link = any(g_data.get(f) for f in main_url_fields)
            if has_main_link:
                valid_cloud_games.append(g_data)
        
        if not valid_cloud_games:
            # 虽然找到了名字匹配的，但都没有主链接，也返回提示以触发网页搜索
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

    async def get_user_info(self, user_id):
        """获取用户信息，返回数据字典或 None"""
        try:
            # 修正接口路径：从 /api/admin/user_info 统一到正式权限校验接口
            # 注意：此处必须使用 resolve_openid 或直接查询 users 表的接口
            # 经过之前的优化，后端 /api/admin/user_info 应该已经支持通过 qq_id 查询
            url = f"{BACKEND_URL}/api/admin/user_info?platform=qq_id&platform_id={user_id}"
            headers = {"app-id": APP_ID, "app-secret": APP_SECRET}
            
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers=headers)
                
                if resp.status_code == 200:
                    res_json = resp.json()
                    # 这里的 success 指的是接口请求成功，data 指的是查到了用户
                    if res_json.get("success") and res_json.get("data"):
                        user_data = res_json["data"]
                        # 核心判定：只要这个 QQ 号在 users 表里有记录，就认为已验证
                        if user_data.get("openid") or user_data.get("qq_id"):
                            logger.info(f"[User Check] 确认用户 {user_id} 已存在，OpenID: {user_data.get('openid')}")
                            return user_data
                
                # 记录非 200 或未查到数据的情况
                if resp.status_code != 404:
                    logger.warning(f"[User Check] 接口响应异常: {resp.status_code}, 内容: {resp.text[:100]}")
                    
            return None
        except Exception as e:
            logger.error(f"[User Check] 请求异常: {e}")
            return None

    def _build_game_messages(self, game_data):
        """构建三段式消息内容：单机、联机、图片"""
        messages = []
        
        # 1. 单机版
        sp_content = ["【单机版】\n"]
        zh_name = game_data.get("zh_name", game_data.get("name", "未知游戏"))
        version = game_data.get("version", "")
        details = game_data.get("details", "")
        
        name_line = f"游戏中文名字：{zh_name}"
        if version: name_line += f"，{version}"
        if details: name_line += f"，{details}"
        sp_content.append(name_line + "：\n")
        
        password = game_data.get("password", "")
        sp_content.append(f"解压密码：【{password}】\n")
        
        # 遍历网盘，取前三个非联机的
        sp_pans = [
            ("baidu_url", "百度网盘", "baidu_code"),
            ("quark_url", "夸克网盘", "quark_code"),
            ("uc_url", "UC网盘", "uc_code"),
            ("pan123_url", "123网盘", "pan123_code"),
            ("xunlei_url", "迅雷网盘", "xunlei_code"),
            ("mobile_url", "移动端", "mobile_code")
        ]
        
        count = 1
        for key, name, code_key in sp_pans:
            url = game_data.get(key)
            if url:
                sp_content.append(f"网盘{count}：{url}\n")
                code = game_data.get(code_key)
                if code:
                    sp_content.append(f"提取码：【{code}】\n")
                count += 1
                if count > 3: break
                
        updated_at = game_data.get("updated_at", "")
        if updated_at:
            sp_content.append(f"最近更新时间：{updated_at}\n")
            
        messages.append("".join(sp_content))
        
        # 2. 联机版
        online_url = game_data.get("online_url")
        patch_url = game_data.get("patch_url")
        if online_url or patch_url:
            ol_content = ["【联机版】\n"]
            ol_content.append(f"游戏中文名字：{zh_name}\n")
            
            # 联机版解压密码：直接使用 online_code 字段
            ol_pwd = game_data.get("online_code")
            if ol_pwd:
                ol_content.append(f"解压密码：【{ol_pwd}】\n")
            
            if online_url:
                ol_content.append(f"网盘1：{online_url}\n")
            elif patch_url:
                ol_content.append(f"网盘1：{patch_url}\n")
                
            online_at = game_data.get("online_at")
            if online_at:
                ol_content.append(f"最近更新时间：{online_at}\n")
            elif updated_at:
                ol_content.append(f"最近更新时间：{updated_at}\n")
                
            messages.append("".join(ol_content))
            
        # 3. 图片
        image_url = game_data.get("image_url")
        if image_url:
            messages.append({"type": "image", "url": image_url})
            
        return messages

    async def _send_final_forward(self, group_id, messages, user_id, nickname):
        """发送合并转发消息，支持多段文字和图片"""
        try:
            fc = ForwardConstructor()
            for msg in messages:
                if isinstance(msg, str):
                    fc.attach_text(msg, user_id, nickname)
                elif isinstance(msg, dict) and msg.get("type") == "image":
                    # 构建 Image 节点
                    img_node = MessageArray([Image(file=msg["url"])])
                    fc.attach_message(img_node, user_id, nickname)
            
            await self.api.qq.post_group_forward_msg(group_id, fc.build())
            return True
        except Exception as e:
            logger.error(f"合并转发失败: {e}")
            return False

    async def process_game_resource(self, game, event, original_msg_id=None):
        try:
            user_id = str(event.user_id)
            
            # 如果资源来自网页，先抓取详情并保存到数据库
            if not game.get("from_db"):
                await event.reply("正在从网站抓取最新资源，请稍候...")
                db_data = await scrape_game_detail_and_save(game["title"], game["detail_url"])
                if not db_data:
                    await event.reply("❌ 抓取详情失败，资源可能已下架。")
                    return
                game["db_data"] = db_data
                game["from_db"] = True

            # 1. 检查用户是否存在（是否有数据）
            user_info = await self.get_user_info(user_id)
            if user_info:
                logger.info(f"[Auth] 用户 {user_id} 已存在记录，跳过验证直接发送资源。")
                # 只要有数据，直接发送资源内容 (合并转发)
                messages = self._build_game_messages(game["db_data"])
                await self._send_final_forward(event.group_id, messages, user_id, event.sender.nickname)
                # 显式回复一条提示
                await event.reply(rtf=MessageArray([Reply(id=event.message_id), PlainText(text="✅ 您已完成过验证，资源已通过合并转发消息发送！")]))
                return

            # 2. 构造同步 Payload (机器人排版)
            messages = self._build_game_messages(game["db_data"])
            # 同步给后端时，取所有文字部分合并，不包含图片
            content_text = "\n".join([m for m in messages if isinstance(m, str)])
            
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
        messages = self._build_game_messages(game["db_data"])
        
        for _ in range(45):
            await asyncio.sleep(4)
            try:
                resp = await self.http_client.get(f"{BACKEND_URL}/api/user/get_result?ticket={ticket_id}")
                res = resp.json()
                if res and res.get("status") in ["verified", "claimed"]:
                    # 发送群消息
                    await self._send_final_forward(group_id, messages, user_id, nickname)
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
            
            # 先从数据库搜索
            text_result, games = await search_game_from_db(game_name)
            
            # 如果数据库没找到，尝试从网站搜索
            if not games:
                text_result, games = await search_game_from_web(game_name)
            
            if not games:
                # 依然没找到
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
