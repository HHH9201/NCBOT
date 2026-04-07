# /home/hjh/BOT/NCBOT/plugins/xydj/main.py
# -*- coding: utf-8 -*-
"""
咸鱼单机（仅数据库版）
"""
import re
import os
import time
import json
import asyncio
import logging
import httpx
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from ncatbot.plugin import NcatBotPlugin
from ncatbot.event.qq import GroupMessageEvent
from ncatbot.types import PlainText, Reply, MessageArray
from ncatbot.core.registry import registrar
from dotenv import load_dotenv

# 加载根目录 .env 配置
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
load_dotenv(env_path)

# 引入全局服务和配置
from common import (
    GLOBAL_CONFIG, load_yaml, save_yaml, DEFAULT_HEADERS, db_manager, AsyncHttpClient,
    convert_roman_to_arabic
)
from common.db_permissions import db_permission_manager

# 配置日志
logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    level=logging.INFO
)

# 快速HTTP客户端
FAST_HTTP = AsyncHttpClient(retry_count=3, retry_delay=1.0, timeout=30)

CACHE_FILE = Path(__file__).parent / "tool" / "cache" / "game_name_cache.yaml"
_title_cache = load_yaml(CACHE_FILE)

# -------------------- 缓存与并发控制 --------------------
CACHE_TTL = 3600
from collections import OrderedDict

class LRUCache:
    """简单的LRU缓存实现"""
    def __init__(self, capacity: int = 1000):
        self.capacity = capacity
        self.cache = OrderedDict()
        self.lock = asyncio.Lock()
    
    async def get(self, key: str):
        async with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
            return None
    
    async def set(self, key: str, value):
        async with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            else:
                if len(self.cache) >= self.capacity:
                    self.cache.popitem(last=False)
            self.cache[key] = value

_memory_cache = LRUCache(capacity=500)

# -------------------- 预编译正则表达式 --------------------
RE_ENGLISH_CHARS = re.compile(r'[a-zA-Z]')
RE_CHINESE_CHARS = re.compile(r'[\u4e00-\u9fff]')
RE_PARENTHESIS = re.compile(r'\([^)]*\)')
RE_BRACKETS = re.compile(r'\[[^\]]*\]')
RE_NON_WORD_CHARS = re.compile(r'[^\w\s]')
RE_MULTIPLE_SPACES = re.compile(r'\s+')

# -------------------- 数据库缓存工具 --------------------
_db_initialized = False

def init_cache_db():
    """初始化缓存表"""
    global _db_initialized
    if _db_initialized: return
    try:
        sql = "CREATE TABLE IF NOT EXISTS xydj_cache (key TEXT PRIMARY KEY, value TEXT, type TEXT, timestamp REAL)"
        db_manager.execute_update(sql)
        _db_initialized = True
    except Exception as e:
        logging.error(f"[DB] 初始化缓存表失败: {e}")

async def search_game_in_db(keyword: str) -> list:
    """从数据库搜索游戏"""
    games = []
    try:
        cloud_games = await db_permission_manager.search_game_resources(keyword)
        if cloud_games:
            for game_data in cloud_games:
                # 检查是否有任何有效的网盘链接
                has_link = False
                for p in ["baidu", "quark", "uc", "online", "pan123", "mobile", "tianyi", "xunlei"]:
                    if game_data.get(f"{p}_url"):
                        has_link = True
                        break
                
                if not has_link: continue

                game = {
                    "title": game_data.get("zh_name", ""),
                    "url": game_data.get("detail_url", ""),
                    "img": game_data.get("image_url", ""),
                    "password": game_data.get("password", ""),
                    "updated_at": game_data.get("updated_at", ""),
                    "from_db": True
                }
                games.append(game)
    except Exception as e:
        logging.error(f"[DB] 搜索游戏失败: {e}")
    return games

async def get_cache(key: str, cache_type: str):
    cache_key = f"{cache_type}:{key}"
    mem_result = await _memory_cache.get(cache_key)
    if mem_result is not None: return mem_result
    
    try:
        sql = "SELECT value, timestamp FROM xydj_cache WHERE key = ? AND type = ?"
        rows = await asyncio.to_thread(db_manager.execute_query, sql, (key, cache_type))
        if rows:
            val_json, ts = rows[0]
            if time.time() - ts < CACHE_TTL:
                value = json.loads(val_json)
                await _memory_cache.set(cache_key, value)
                return value
    except Exception: pass
    return None

async def set_cache(key: str, value: Any, cache_type: str):
    cache_key = f"{cache_type}:{key}"
    await _memory_cache.set(cache_key, value)
    async def _save_to_db():
        try:
            sql = "INSERT OR REPLACE INTO xydj_cache (key, value, type, timestamp) VALUES (?, ?, ?, ?)"
            val_json = json.dumps(value)
            await asyncio.to_thread(db_manager.execute_update, sql, (key, val_json, cache_type, time.time()))
        except Exception: pass
    asyncio.create_task(_save_to_db())

# -------------------- 工具函数 --------------------
def _is_mainly_english(text: str) -> bool:
    return len(RE_ENGLISH_CHARS.findall(text)) > len(RE_CHINESE_CHARS.findall(text))

def extract_english_name(title: str) -> tuple[str, str]:
    segments = title.split('|')
    english_part = ""
    for segment in reversed(segments):
        segment = segment.strip()
        if _is_mainly_english(segment):
            english_part = segment
            break
    if not english_part: english_part = segments[-1] if segments else title
    
    chinese_display_parts = []
    for segment in segments:
        segment = segment.strip()
        if _is_mainly_english(segment): break
        chinese_display_parts.append(segment)
    
    chinese_display = ' | '.join(chinese_display_parts) if chinese_display_parts else (segments[0] if segments else title)
    
    english_part = RE_PARENTHESIS.sub('', english_part)
    english_part = RE_BRACKETS.sub('', english_part)
    english_part = english_part.split('/')[0]
    english_part = RE_NON_WORD_CHARS.sub(' ', english_part)
    english_part = RE_MULTIPLE_SPACES.sub(' ', english_part).strip()
    
    words = english_part.split()
    if len(words) > 4: english_part = ' '.join(words[:4])
    english_part = convert_roman_to_arabic(english_part)
    
    return english_part.strip(), chinese_display.strip()

# -------------------- 搜索逻辑 --------------------
async def search_game(game_name: str):
    """搜索游戏（仅从数据库）"""
    data = await get_cache(game_name, "search")
    if data: return data[0], data[1]

    english_keyword, chinese_display = extract_english_name(game_name)
    games = await search_game_in_db(english_keyword)
    if not games: games = await search_game_in_db(game_name)

    if not games:
        await set_cache(game_name, [None, None], "search")
        return None, None

    text_lines = []
    for idx, g in enumerate(games):
        title = g['title']
        title_parts = title.split('|')
        name_ext = title_parts[0].strip()
        key_info = [p.strip() for p in title_parts[1:] if any(k in p.lower() for k in ['v', '版', 'dlc', '中文', '手柄', '更新', '年度版'])]
        display = f"{idx+1}. {name_ext}"
        if key_info: display += f" | {' | '.join(key_info[:3])}"
        text_lines.append(display)

    text_result = "\n".join(text_lines)
    await set_cache(game_name, [text_result, games], "search")
    return text_result, games

# -------------------- 会话管理 --------------------
class SearchSession:
    def __init__(self, user_id, games, task=None):
        self.user_id = user_id
        self.games = games
        self.task = task
        self.processing = False

# -------------------- 插件主类 --------------------
class Xydj(NcatBotPlugin):
    name = "xydj"
    version = "1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sessions = {}
        init_cache_db()

    async def on_load(self):
        print(f"{self.name} 插件已加载，仅数据库模式，版本: {self.version}")

    def _cleanup(self, group_id):
        if group_id in self.sessions:
            session = self.sessions[group_id]
            if session.task: session.task.cancel()
            del self.sessions[group_id]

    async def countdown(self, event, group_id, session_obj):
        await asyncio.sleep(20)
        curr = self.sessions.get(group_id)
        if curr is session_obj and not curr.processing:
            self._cleanup(group_id)
            await event.reply(rtf=MessageArray([Reply(id=event.message_id), PlainText(text="等待超时，操作已取消。")]))

    async def process_game_resource(self, game, event):
        """处理并发送游戏资源"""
        try:
            english_keyword, chinese_display = extract_english_name(game['title'])
            db_games = await search_game_in_db(english_keyword)
            if not db_games: db_games = await search_game_in_db(chinese_display)
            
            content = await self._get_resource_content(chinese_display, db_games)
            if content:
                await self._send_final_forward(event.group_id, content, str(event.user_id), event.sender.nickname)
            else:
                await event.reply(rtf=MessageArray([Reply(id=event.message_id), PlainText(text="❌ 很抱歉，数据库中暂无该资源的有效链接。")]))
        except Exception as e:
            logging.error(f"处理资源失败: {e}")
            await event.reply(rtf=MessageArray([Reply(id=event.message_id), PlainText(text="处理失败，请稍后重试")]))

    async def _get_resource_content(self, chinese_display, db_games):
        """从数据库构建内容，过滤空字段"""
        if not db_games: return None
        data = db_games[0]
        lines = []
        
        password = data.get('password')
        if password: lines.append(f"解压密码: 【{password}】")
            
        platforms = [("baidu", "百度"), ("quark", "夸克"), ("uc", "UC"), ("online", "在线"), 
                     ("pan123", "123"), ("mobile", "移动"), ("tianyi", "天翼"), ("xunlei", "迅雷")]
        
        # 尝试从字段构建
        found_any = False
        for prefix, name in platforms:
            url = await db_permission_manager._query(f"SELECT {prefix}_url, {prefix}_code FROM game_resources WHERE zh_name = ?", (data['title'],))
            # 注意：db_games 里的数据是 search_game_in_db 查出来的，它没有返回所有字段
            # 重新查一遍详情
            res = await db_permission_manager.get_game_resource(data['title'])
            if res:
                for p_prefix, p_name in platforms:
                    p_url = res.get(f"{p_prefix}_url")
                    p_code = res.get(f"{p_prefix}_code")
                    if p_url:
                        found_any = True
                        line = f"{p_name}网盘: {p_url}"
                        if p_code: line += f" (提取码: {p_code})"
                        lines.append(line)
                break # 查到一次详情就够了

        if not lines: return None
        final = [f"【单机版】\n", f"游戏名字：{chinese_display}\n"]
        for l in lines: final.append(f"{l}\n")
        return final

    async def _send_final_forward(self, group_id, content, user_id, nickname):
        from ncatbot.types.qq import ForwardConstructor
        fc = ForwardConstructor()
        text = "".join(content)
        fc.attach_text(text=text, user_id=user_id, nickname=nickname)
        try:
            await self.api.qq.post_group_forward_msg(group_id, fc.build())
        except Exception:
            await self.api.qq.send_group_text(group_id, text)

    @registrar.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent):
        msg = event.raw_message.strip()
        session = self.sessions.get(event.group_id)
        
        if session and event.user_id == session.user_id:
            if session.processing: return
            choice = re.sub(r'\[CQ:[^\]]+\]', '', msg).strip()
            if choice == "0":
                await event.reply(rtf=MessageArray([Reply(id=event.message_id), PlainText(text="操作已取消。")]))
                self._cleanup(event.group_id)
                return
            if not choice.isdigit() or not 1 <= int(choice) <= len(session.games):
                await event.reply(rtf=MessageArray([Reply(id=event.message_id), PlainText(text="无效序号，请重新搜索。")]))
                self._cleanup(event.group_id)
                return
            
            session.processing = True
            if session.task: session.task.cancel()
            try:
                await self.process_game_resource(session.games[int(choice)-1], event)
            finally:
                self._cleanup(event.group_id)
        
        elif msg.startswith("搜索11"):
            name = msg[2:].strip()
            if not name:
                await event.reply(rtf=MessageArray([Reply(id=event.message_id), PlainText(text="使用方法：搜索+游戏名称")]))
                return
            try:
                res, games = await search_game(name)
                if not res:
                    await event.reply(rtf=MessageArray([Reply(id=event.message_id), PlainText(text="未找到资源")]))
                    return
                if len(games) == 1:
                    await self.process_game_resource(games[0], event)
                else:
                    await event.reply(rtf=MessageArray([Reply(id=event.message_id), PlainText(text=f"🎯 发现 {len(games)} 款游戏\n{res}\n⏰ 20秒内回复序号选择 | 回复 0 取消")]))
                    session = SearchSession(event.user_id, games)
                    session.task = asyncio.create_task(self.countdown(event, event.group_id, session))
                    self.sessions[event.group_id] = session
            except Exception:
                await event.reply(rtf=MessageArray([Reply(id=event.message_id), PlainText(text="搜索出错，请重试")]))
