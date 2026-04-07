# /home/hjh/BOT/NCBOT/plugins/xydj/web_search.py
# -*- coding: utf-8 -*-
"""
咸鱼单机 - 网站搜索版
- 只从网站搜索
- 直接发送资源（不需要小程序）
- 搜索到的游戏插入数据库
"""
import re
import os
import time
import json
import asyncio
import logging
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from bs4 import BeautifulSoup
from ncatbot.plugin import NcatBotPlugin
from ncatbot.event.qq import GroupMessageEvent
from ncatbot.types import PlainText, Reply, MessageArray
from ncatbot.types.qq import ForwardConstructor
from ncatbot.core.registry import registrar
from dotenv import load_dotenv

# 加载根目录 .env 配置
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
load_dotenv(env_path)

# 引入全局服务和配置
from common import (
    GLOBAL_CONFIG, load_yaml, save_yaml,
    DEFAULT_HEADERS, db_manager, AsyncHttpClient
)
from common.db_permissions import db_permission_manager

# 配置更清爽的日志格式，去掉进程和线程信息
logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    level=logging.INFO
)

# Cookie 缓存
_XYDJ_COOKIE = None

async def get_xydj_cookie() -> str:
    """从数据库获取 xydj cookie"""
    global _XYDJ_COOKIE
    if _XYDJ_COOKIE is None:
        _XYDJ_COOKIE = await db_permission_manager.get_cookie("xydj")
    return _XYDJ_COOKIE

# 快速HTTP客户端：增加重试和超时时间
FAST_HTTP = AsyncHttpClient(retry_count=3, retry_delay=1.0, timeout=30)

# 全局并发限制信号量
SEARCH_SEMAPHORE = asyncio.Semaphore(5)

# -------------------- 预编译正则表达式 --------------------
RE_PARENTHESIS = re.compile(r'\([^)]*\)')
RE_BRACKETS = re.compile(r'\[[^\]]*\]')
RE_NON_WORD_CHARS = re.compile(r'[^\w\s]')
RE_MULTIPLE_SPACES = re.compile(r'\s+')
RE_EXTRACT_CODE = re.compile(r'【([a-zA-Z0-9]{4})】')
RE_PASSWORD_PATTERN = re.compile(r'解压密码[:：]\s*([^\s\u4e00-\u9fa5]{4,})')
RE_RUSSIAN_DATE = re.compile(r"(\d{1,2}\s+[а-яА-Я]+\s+\d{4},\s*\d{1,2}:\d{2})")
RE_CQ_CODE = re.compile(r'\[CQ:[^\]]+\]')

async def save_game_to_db(keyword: str, game: dict, detail_info: list = None, web_updated_at: str = ""):
    """保存游戏信息到数据库"""
    try:
        decompress_password = ""
        pan_links = {}

        if detail_info:
            for line in detail_info:
                if "解压密码" in line and "【" in line:
                    match = re.search(r'【([^】]+)】', line)
                    if match:
                        decompress_password = match.group(1)

                pan_code_match = re.search(r'(百度网盘|夸克网盘|UC网盘)提取码[:：]\s*【([^】]+)】', line)
                if pan_code_match:
                    pan_name = pan_code_match.group(1)
                    pan_code = pan_code_match.group(2)
                    if pan_name not in pan_links:
                        pan_links[pan_name] = {}
                    pan_links[pan_name]["code"] = pan_code

                pan_url_match = re.search(r'(百度网盘|夸克网盘|UC网盘)[:：]\s*(https?://\S+)', line)
                if pan_url_match:
                    pan_name = pan_url_match.group(1)
                    pan_url = pan_url_match.group(2)
                    if pan_name not in pan_links:
                        pan_links[pan_name] = {}
                    pan_links[pan_name]["url"] = pan_url

        save_data = {"password": decompress_password}
        if web_updated_at:
            save_data["web_updated_at"] = web_updated_at
        if game.get("url"):
            save_data["source_url"] = game["url"]

        pan_name_mapping = {
            "百度网盘": "baidu",
            "夸克网盘": "quark",
            "UC网盘": "uc",
        }

        for pan_name, pan_info in pan_links.items():
            field_prefix = pan_name_mapping.get(pan_name, pan_name)
            if pan_info.get("url"):
                save_data[f"{field_prefix}_url"] = pan_info["url"]
            if pan_info.get("code"):
                save_data[f"{field_prefix}_code"] = pan_info["code"]

        await db_permission_manager.save_game_resource(
            name=game.get("title", ""),
            data=save_data
        )
        print(f"[DB] 保存游戏到数据库: {game.get('title', '')}, 字段: {list(save_data.keys())}")
    except Exception as e:
        logging.error(f"[DB] 保存游戏到数据库失败: {e}")

async def extract_download_info(game_url: str, skip_cache: bool = False):
    """从游戏详情页提取下载信息"""
    async with SEARCH_SEMAPHORE:
        print(f"[XianYu Detail] Processing: {game_url}")
        try:
            cookie = await get_xydj_cookie()
            headers = {"Cookie": cookie} if cookie else None
            html = await FAST_HTTP.get_text(game_url, headers=headers, timeout=20)
            if not html:
                print(f"[XianYu Detail] No HTML returned")
                return ["无法获取页面内容"], ""
            
            soup = BeautifulSoup(html, "html.parser")
            
            if "安全验证" in html or "guardok" in html:
                print(f"[XianYu Detail] 遇到安全验证，cookie可能已失效")
                return ["❌ 遇到网站安全验证，请联系管理员更新cookie"], ""
            
            box = soup.select_one("#ripro_v2_shop_down-5")
            if not box:
                print(f"[XianYu Detail] Download box not found")
                return ["未找到下载区域"], ""
            
            print(f"[XianYu Detail] Download box found")
            
            results = []
            password_val = None
            pan_cards = []
            web_updated_at = ""
            
            down_info = box.select_one(".down-info")
            if down_info:
                for li in down_info.select("li"):
                    label = li.select_one(".data-label")
                    if label and "最近更新" in label.get_text(strip=True):
                        info = li.select_one(".info")
                        if info:
                            web_updated_at = info.get_text(strip=True)
                            print(f"[XianYu Detail] 网页更新时间: {web_updated_at}")
                            break
            
            for card in box.select(".pan-download-card"):
                a_tag = card.select_one("a.pan-download-link")
                if not a_tag:
                    continue
                
                name_span = a_tag.select_one("span.pan-name")
                if name_span:
                    pan_name = name_span.get_text(strip=True)
                    if pan_name == "解压密码":
                        pwd_span = card.select_one("span.pan-pwd")
                        if pwd_span:
                            pwd_code = pwd_span.get("data-clipboard-text", "").strip()
                            if pwd_code:
                                password_val = pwd_code
                                print(f"[XianYu Detail] 从解压密码卡片获取: {password_val}")
                                break
            
            if not password_val and down_info:
                for li in down_info.select("li"):
                    label = li.select_one(".data-label")
                    if label and "解压密码" in label.get_text(strip=True):
                        info = li.select_one(".info")
                        if info:
                            pwd_text = info.get_text(strip=True)
                            if re.fullmatch(r'\d+', pwd_text):
                                password_val = pwd_text
                                print(f"[XianYu Detail] 从down-info获取数字密码: {password_val}")
                            else:
                                b_tag = info.select_one("b")
                                if b_tag:
                                    pwd_text = b_tag.get_text(strip=True)
                                    if re.fullmatch(r'\d+', pwd_text):
                                        password_val = pwd_text
                                        print(f"[XianYu Detail] 从down-info b标签获取: {password_val}")
                            break
            
            for card in box.select(".pan-download-card"):
                a_tag = card.select_one("a.pan-download-link")
                if not a_tag:
                    continue
                    
                pan_name = ""
                pan_link = a_tag.get('href', '').strip()
                
                name_span = a_tag.select_one("span.pan-name")
                if name_span:
                    pan_name = name_span.get_text(strip=True)
                
                if pan_name == "解压密码":
                    continue
                
                pwd_span = card.select_one("span.pan-pwd")
                pwd_code = ""
                if pwd_span:
                    pwd_code = pwd_span.get("data-clipboard-text", "").strip()
                    if not pwd_code:
                        pwd_text = pwd_span.get_text(strip=True)
                        pwd_match = re.search(r'密码[：:]\s*([a-zA-Z0-9]+)', pwd_text)
                        if pwd_match:
                            pwd_code = pwd_match.group(1)
                
                if pan_link and pan_name and any(keyword in pan_name for keyword in ['百度', '夸克', 'UC']):
                    pan_cards.append({
                        "name": pan_name,
                        "link": pan_link,
                        "code": pwd_code
                    })
            
            if password_val:
                results.append(f"解压密码: 【{password_val}】")
            
            if pan_cards:
                for card in pan_cards:
                    if card.get("code"):
                        results.append(f"{card['name']}提取码: 【{card['code']}】")
                    
                    if card.get("link"):
                        try:
                            real_url = await FAST_HTTP.get_redirect_url(card["link"], headers=headers, timeout=10)
                            if real_url:
                                results.append(f"{card['name']}: {real_url}")
                            else:
                                results.append(f"{card['name']}: {card['link']}")
                        except Exception as e:
                            print(f"[XianYu Detail] 获取链接失败: {e}")
                            results.append(f"{card['name']}: {card['link']}")
            else:
                results.append("网盘链接: 未找到")
            
            print(f"[XianYu Detail] Results: {results}, 更新时间: {web_updated_at}")
            return results, web_updated_at
            
        except Exception as e:
            print(f"[XianYu Detail] Exception: {e}")
            return [f"解析游戏信息时出错: {e}"], ""

async def search_game(game_name: str):
    """从网站搜索游戏"""
    print(f"[XianYu Search] Fetching from website: {game_name}")

    game_name_lower = game_name.lower()

    async with SEARCH_SEMAPHORE:
        url = f"https://www.xianyudanji.to/?cat=1&s={game_name}&order=views"
        print(f"[XianYu Search] Requesting: {url}")
        cookie = await get_xydj_cookie()
        headers = {"Cookie": cookie} if cookie else None
        html = await FAST_HTTP.get_text(url, headers=headers, timeout=12)
        if not html:
            print(f"[XianYu Search] No HTML returned")
            return None, None
        print(f"[XianYu Search] HTML length: {len(html)}")

        if "安全验证" in html or "guardok" in html:
            print(f"[XianYu Search] 遇到安全验证，cookie可能已失效")
            return "❌ 遇到网站安全验证，请联系管理员更新cookie", None

        soup = BeautifulSoup(html, "html.parser")
        games = []
        seen = set()
        articles = soup.select("article.post-grid a[href][title]")
        print(f"[XianYu Search] Found {len(articles)} articles")

        for a in articles:
            title = a.get('title', '').strip()
            if not title or title in seen:
                continue
            if game_name_lower not in title.lower():
                continue
            seen.add(title)
            img_src = a.select_one("img")
            games.append({
                "title": title,
                "url": a['href'],
                "img": img_src['src'] if img_src else ""
            })

        print(f"[XianYu Search] Filtered games: {len(games)}")
        if not games:
            return None, None

        text_lines = []
        for idx, g in enumerate(games):
            title_parts = g['title'].split('|')
            game_name_extracted = title_parts[0].strip()
            key_info = []
            for part in title_parts[1:]:
                part = part.strip()
                if any(keyword in part.lower() for keyword in ['v', '版', 'dlc', '中文', '手柄', '更新', '年度版']):
                    key_info.append(part)
            display_text = f"{idx+1}. {game_name_extracted}"
            if key_info:
                display_text += f" | {' | '.join(key_info[:3])}"
            text_lines.append(display_text)

        text_result = "\n".join(text_lines)
        return text_result, games

class SearchSession:
    def __init__(self, user_id, games, task=None):
        self.user_id = user_id
        self.games = games
        self.task = task
        self.processing = False

class XydjWebSearch(NcatBotPlugin):
    name = "xydj_web_search"
    version = "1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sessions = {}

    async def countdown(self, event, group_id):
        await asyncio.sleep(20)
        session = self.sessions.get(group_id)
        if session and not session.processing:
            self._cleanup(group_id)
            await event.reply(
                rtf=MessageArray([Reply(id=event.message_id), PlainText(text="等待超时，操作已取消。请重新搜索")])
            )

    def _cleanup(self, group_id):
        if group_id in self.sessions:
            session = self.sessions[group_id]
            if session.task:
                session.task.cancel()
            del self.sessions[group_id]

    def _build_content(self, chinese_display, 单机_lines):
        content = []
        content.append("【单机版】\n")
        content.append(f"游戏名字：{chinese_display}\n")
        for line in 单机_lines:
            content.append(f"{line}\n")
        return content

    async def _send_final_forward(self, group_id, 单机_lines: list[str], user_id: str = "0", user_nickname: str = "游戏助手"):
        from ncatbot.types.qq import ForwardConstructor
        
        fc = ForwardConstructor()
        
        game_title = ""
        for line in 单机_lines:
            if "游戏名字：" in line:
                game_title = line.split("游戏名字：")[1].strip()
                break
        if not game_title:
            game_title = "游戏资源"

        content_text = "".join(单机_lines)
        fc.attach_text(text=content_text, user_id=user_id, nickname=user_nickname)
        
        try:
            await self.api.qq.post_group_forward_msg(group_id, fc.build())
            print(f"✅ [Forward] 合并转发消息已发送: {game_title}")
            return True
        except Exception as e:
            print(f"❌ [Forward] 发送失败: {e}")
            try:
                await self.api.qq.send_group_text(group_id, content_text)
                return True
            except:
                return False

    async def process_game_resource(self, game, event):
        print(f"[Resource] Processing: {game['title']}")
        try:
            title_parts = game['title'].split('|')
            chinese_display = title_parts[0].strip()
            print(f"[搜索关键词] 中文名: {chinese_display}")

            await event.reply(
                rtf=MessageArray([Reply(id=event.message_id), PlainText(text="🔍 正在获取游戏资源，请稍候...")])
            )

            单机_lines, web_updated_at = await extract_download_info(game['url'], skip_cache=False)
            
            if 单机_lines and any("http" in line for line in 单机_lines):
                await save_game_to_db(chinese_display, game, 单机_lines, web_updated_at)
            
            content = self._build_content(chinese_display, 单机_lines)
            await self._send_final_forward(event.group_id, content, str(event.user_id), event.sender.nickname)

        except Exception as e:
            import traceback
            print(f"[Resource] Processing exception: {e}")
            traceback.print_exc()
            await event.reply(
                rtf=MessageArray([Reply(id=event.message_id), PlainText(text=f"处理失败: {str(e)}")])
            )

    @registrar.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent):
        session = self.sessions.get(event.group_id)
        
        if session and event.user_id == session.user_id:
            if session.processing:
                return
            
            choice = re.sub(r'\[CQ:[^\]]+\]', '', event.raw_message).strip()
            
            if choice == "0":
                await event.reply(
                    rtf=MessageArray([Reply(id=event.message_id), PlainText(text="操作已取消。")])
                )
                self._cleanup(event.group_id)
                return
            
            if not choice.isdigit() or not 1 <= int(choice) <= len(session.games):
                await event.reply(
                    rtf=MessageArray([Reply(id=event.message_id), PlainText(text="回复错误，操作已取消。请重新搜索游戏。")])
                )
                self._cleanup(event.group_id)
                return
            
            choice = int(choice)
            session.processing = True
            if session.task:
                session.task.cancel()
                session.task = None
            
            try:
                game = session.games[choice - 1]
                await self.process_game_resource(game, event)
            except Exception as e:
                await event.reply(
                    rtf=MessageArray([Reply(id=event.message_id), PlainText(text=f"处理失败: {str(e)}")])
                )
            finally:
                self._cleanup(event.group_id)
        
        elif event.raw_message.strip().startswith("搜网"):
            message = event.raw_message.strip()
            if message.startswith("搜网 "):
                game_name = message[3:].strip()
            else:
                game_name = message[2:].strip()
            if not game_name:
                await event.reply(
                    rtf=MessageArray([Reply(id=event.message_id), PlainText(text="使用方法：搜网+游戏名称，例如：搜网 文明6")])
                )
                return
            
            try:
                text_result, games = await search_game(game_name)
                if not text_result:
                    await event.reply(
                        rtf=MessageArray([Reply(id=event.message_id), PlainText(text="未找到，检查游戏名字，搜索游戏字数少一点试试呢")])
                    )
                    return
                
                if len(games) == 1:
                    await self.process_game_resource(games[0], event)
                    return
                
                await event.reply(
                    rtf=MessageArray([Reply(id=event.message_id), PlainText(text=f"🎯 发现 {len(games)} 款游戏\n{text_result}\n⏰ 20秒内回复序号选择 | 回复 0 取消操作")])
                )
                
                session = SearchSession(event.user_id, games)
                session.task = asyncio.create_task(self.countdown(event, event.group_id))
                self.sessions[event.group_id] = session
                
            except Exception as e:
                logging.exception(f"搜索出错: {e}")
                await event.reply(
                    rtf=MessageArray([Reply(id=event.message_id), PlainText(text="发生错误，请稍后重试。")])
                )

    async def on_load(self):
        print(f"{self.name} 插件已加载，版本: {self.version}")
