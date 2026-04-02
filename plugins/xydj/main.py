# /home/hjh/BOT/NCBOT/plugins/xydj/main.py
# -*- coding: utf-8 -*-
"""
咸鱼单机（单机版）
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
from urllib.parse import urljoin
from ncatbot.plugin import NcatBotPlugin
from ncatbot.event.qq import GroupMessageEvent
from ncatbot.types import PlainText, At, Reply, MessageArray, Image
from ncatbot.types.qq import Json, ForwardConstructor, Share
from ncatbot.core.registry import registrar

# 引入全局服务和配置
from common import (
    napcat_service, ai_service, GLOBAL_CONFIG,
    image_to_base64, normalize_text, convert_roman_to_arabic,
    load_yaml, save_yaml, clean_filename,
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

# 图片Base64缓存
_image_base64_cache: Dict[str, str] = {}

def get_image_base64_cached(image_path: str) -> Optional[str]:
    """获取图片Base64，带缓存"""
    if image_path in _image_base64_cache:
        return _image_base64_cache[image_path]
    
    result = image_to_base64(image_path)
    if result:
        _image_base64_cache[image_path] = result
    return result

# 快速HTTP客户端：增加重试和超时时间
FAST_HTTP = AsyncHttpClient(retry_count=3, retry_delay=1.0, timeout=30)

CACHE_FILE = Path(__file__).parent / "tool" / "cache" / "game_name_cache.yaml"
_title_cache = load_yaml(CACHE_FILE)

import aiohttp

# -------------------- 缓存与并发控制 --------------------
# 缓存有效期 (1小时)
CACHE_TTL = 3600

# 全局并发限制信号量
SEARCH_SEMAPHORE = asyncio.Semaphore(5)

# LRU 内存缓存（限制1000条，避免内存无限增长）
from functools import lru_cache
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
                # 移动到末尾（最近使用）
                self.cache.move_to_end(key)
                return self.cache[key]
            return None
    
    async def set(self, key: str, value):
        async with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            else:
                if len(self.cache) >= self.capacity:
                    # 移除最旧的
                    self.cache.popitem(last=False)
            self.cache[key] = value
    
    async def clear(self):
        async with self.lock:
            self.cache.clear()

# 内存缓存实例
_memory_cache = LRUCache(capacity=500)

# -------------------- 预编译正则表达式 --------------------
RE_ENGLISH_CHARS = re.compile(r'[a-zA-Z]')
RE_CHINESE_CHARS = re.compile(r'[\u4e00-\u9fff]')
RE_PARENTHESIS = re.compile(r'\([^)]*\)')
RE_BRACKETS = re.compile(r'\[[^\]]*\]')
RE_NON_WORD_CHARS = re.compile(r'[^\w\s]')
RE_MULTIPLE_SPACES = re.compile(r'\s+')
RE_EXTRACT_CODE = re.compile(r'【([a-zA-Z0-9]{4})】')
RE_PASSWORD_PATTERN = re.compile(r'解压密码[:：]\s*([^\s\u4e00-\u9fa5]{4,})')
RE_RUSSIAN_DATE = re.compile(r"(\d{1,2}\s+[а-яА-Я]+\s+\d{4},\s*\d{1,2}:\d{2})")
RE_TIME_PATTERN = re.compile(r'(\d{1,2}:\d{2})')
RE_CQ_CODE = re.compile(r'\[CQ:[^\]]+\]')

# -------------------- 数据库缓存工具 --------------------
_db_initialized = False

def init_cache_db():
    """初始化缓存表（带缓存检查）"""
    global _db_initialized
    if _db_initialized:
        return

    try:
        # 检查表是否存在
        check_sql = "SELECT name FROM sqlite_master WHERE type='table' AND name='xydj_cache'"
        result = db_manager.execute_query(check_sql)
        if result:
            _db_initialized = True
            return

        # 创建表
        sql = """
        CREATE TABLE IF NOT EXISTS xydj_cache (
            key TEXT PRIMARY KEY,
            value TEXT,
            type TEXT,
            timestamp REAL
        )
        """
        db_manager.execute_update(sql)
        _db_initialized = True
        print("[DB] 缓存表初始化完成")
    except Exception as e:
        logging.error(f"[DB] 初始化缓存表失败: {e}")


async def search_game_in_db(keyword: str) -> list:
    """从数据库搜索游戏（使用 TursoPermissionManager，自动处理云端/本地）"""
    games = []

    try:
        # 使用 TursoPermissionManager 搜索（自动处理云端/本地）
        cloud_games = await db_permission_manager.search_game_resources(keyword)
        if cloud_games:
            for game_data in cloud_games:
                # 解析各个网盘的链接和提取码
                pan_types = []
                pan_codes = []
                download_links = []

                # 检查百度网盘（必须有真实链接才显示）
                if game_data.get("baidu_url"):
                    pan_types.append("百度")
                    if game_data.get("baidu_code"):
                        pan_codes.append(game_data["baidu_code"])
                    download_links.append(f"百度网盘: {game_data['baidu_url']}")

                # 检查夸克网盘（必须有真实链接才显示）
                if game_data.get("quark_url"):
                    pan_types.append("夸克")
                    if game_data.get("quark_code"):
                        pan_codes.append(game_data["quark_code"])
                    download_links.append(f"夸克网盘: {game_data['quark_url']}")

                # 检查UC网盘（必须有真实链接才显示）
                if game_data.get("uc_url"):
                    pan_types.append("UC")
                    if game_data.get("uc_code"):
                        pan_codes.append(game_data["uc_code"])
                    download_links.append(f"UC网盘: {game_data['uc_url']}")

                # 跳过没有有效网盘链接的游戏
                if not download_links:
                    continue

                game = {
                    "title": game_data.get("name", ""),
                    "url": game_data.get("source_url", ""),
                    "img": "",
                    "pan_count": len(pan_types),
                    "pan_types": pan_types,
                    "pan_codes": pan_codes,
                    "decompress_password": game_data.get("password", ""),
                    "download_links": download_links,
                    "updated_at": game_data.get("updated_at", ""),
                    "from_db": True
                }
                games.append(game)
            print(f"[DB] 从数据库找到 {len(games)} 条记录，关键词: {keyword}")
    except Exception as e:
        logging.error(f"[DB] 从数据库搜索游戏失败: {e}")

    return games


async def save_game_to_db(keyword: str, game: dict, detail_info: list = None, web_updated_at: str = ""):
    """保存游戏信息到数据库（使用 TursoPermissionManager，自动处理云端/本地）"""
    try:
        # 解析详情信息
        decompress_password = ""
        # 存储每个网盘的信息：{网盘名称: {"url": "链接", "code": "提取码"}}
        pan_links = {}

        if detail_info:
            for line in detail_info:
                # 提取解压密码
                if "解压密码" in line and "【" in line:
                    match = re.search(r'【([^】]+)】', line)
                    if match:
                        decompress_password = match.group(1)

                # 提取网盘名称和提取码（格式：百度网盘提取码: 【xxx】）
                pan_code_match = re.search(r'(百度网盘|夸克网盘|UC网盘)提取码[:：]\s*【([^】]+)】', line)
                if pan_code_match:
                    pan_name = pan_code_match.group(1)
                    pan_code = pan_code_match.group(2)
                    if pan_name not in pan_links:
                        pan_links[pan_name] = {}
                    pan_links[pan_name]["code"] = pan_code

                # 提取网盘链接（格式：百度网盘: http://...）
                pan_url_match = re.search(r'(百度网盘|夸克网盘|UC网盘)[:：]\s*(https?://\S+)', line)
                if pan_url_match:
                    pan_name = pan_url_match.group(1)
                    pan_url = pan_url_match.group(2)
                    if pan_name not in pan_links:
                        pan_links[pan_name] = {}
                    pan_links[pan_name]["url"] = pan_url

        # 构建保存的数据（新字段名，不带 xydj_ 前缀）
        save_data = {
            "password": decompress_password,
        }

        # 添加网页更新时间
        if web_updated_at:
            save_data["web_updated_at"] = web_updated_at

        # 保存游戏详情页 URL（用于后续获取资源）
        if game.get("url"):
            save_data["source_url"] = game["url"]

        # 为每个网盘添加独立的字段
        # 网盘名称映射为英文字段名
        pan_name_mapping = {
            "百度网盘": "baidu",
            "夸克网盘": "quark",
            "UC网盘": "uc",
        }

        for pan_name, pan_info in pan_links.items():
            field_prefix = pan_name_mapping.get(pan_name, pan_name)
            # 存储网盘链接
            if pan_info.get("url"):
                save_data[f"{field_prefix}_url"] = pan_info["url"]
            # 存储提取码
            if pan_info.get("code"):
                save_data[f"{field_prefix}_code"] = pan_info["code"]

        # 使用 TursoPermissionManager 保存（自动处理云端/本地）
        await db_permission_manager.save_game_resource(
            name=game.get("title", ""),
            data=save_data
        )
        print(f"[DB] 保存游戏到数据库: {game.get('title', '')}, 字段: {list(save_data.keys())}")

    except Exception as e:
        logging.error(f"[DB] 保存游戏到数据库失败: {e}")

async def get_cache(key: str, cache_type: str):
    """获取缓存（先查内存，再查数据库）"""
    cache_key = f"{cache_type}:{key}"
    
    # 1. 先查内存缓存
    mem_result = await _memory_cache.get(cache_key)
    if mem_result is not None:
        print(f"[Cache] Memory hit for: {key}")
        return mem_result
    
    # 2. 再查数据库
    try:
        sql = "SELECT value, timestamp FROM xydj_cache WHERE key = ? AND type = ?"
        rows = await asyncio.to_thread(db_manager.execute_query, sql, (key, cache_type))
        if rows:
            val_json, ts = rows[0]
            if time.time() - ts < CACHE_TTL:
                value = json.loads(val_json)
                # 写入内存缓存
                await _memory_cache.set(cache_key, value)
                return value
    except Exception as e:
        logging.error(f"读取缓存失败: {e}")
    return None

async def set_cache(key: str, value: Any, cache_type: str):
    """写入缓存（内存+数据库）"""
    cache_key = f"{cache_type}:{key}"
    
    # 1. 写入内存缓存
    await _memory_cache.set(cache_key, value)
    
    # 2. 异步写入数据库（不阻塞主流程）
    async def _save_to_db():
        try:
            sql = "INSERT OR REPLACE INTO xydj_cache (key, value, type, timestamp) VALUES (?, ?, ?, ?)"
            val_json = json.dumps(value)
            await asyncio.to_thread(db_manager.execute_update, sql, (key, val_json, cache_type, time.time()))
        except Exception as e:
            logging.error(f"写入缓存失败: {e}")
    
    # 后台执行数据库写入
    asyncio.create_task(_save_to_db())

# 兼容旧接口
async def get_cache_from_db(key: str, cache_type: str):
    """从数据库获取缓存（兼容旧接口）"""
    return await get_cache(key, cache_type)

async def set_cache_to_db(key: str, value: Any, cache_type: str):
    """写入缓存到数据库（兼容旧接口）"""
    await set_cache(key, value, cache_type)

# 翻译缓存待保存标记
_title_cache_dirty = False

async def translate_to_chinese_title(eng: str, use_modelscope: bool = True) -> str:
    """
    输入英文关键词，返回 Steam 官方中文名；失败则回退原文。
    
    :param eng: 英文游戏名
    :param use_modelscope: 是否使用 ModelScope API (默认True)，否则使用 SiliconFlow
    """
    if not eng:
        return eng

    global _title_cache, _title_cache_dirty
    if eng in _title_cache:
        return _title_cache[eng]

    system_prompt = "你是 Steam 中文名称翻译助手，只输出 steam 游戏官方中文名，其余任何文字都不要说。"
    prompt = f"{eng} 的 Steam 官方游戏中文名是什么"
    
    try:
        if use_modelscope:
            # 使用 ModelScope API
            zh = await ai_service.modelscope_simple_chat(
                prompt=prompt,
                system_prompt=system_prompt
            )
        else:
            # 使用 SiliconFlow API
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
            proxy = GLOBAL_CONFIG.get('proxy')
            zh = await ai_service.chat_completions(messages, temperature=0.1, max_tokens=30, proxy=proxy)
        
        if not zh:
            zh = eng
    except Exception as e:
        logging.error(f"翻译失败: {e}")
        zh = eng

    _title_cache[eng] = zh
    _title_cache_dirty = True
    return zh

async def save_title_cache():
    """保存翻译缓存到文件"""
    global _title_cache_dirty
    if _title_cache_dirty:
        save_yaml(CACHE_FILE, _title_cache)
        _title_cache_dirty = False
        print("[Cache] 翻译缓存已保存")

# ------------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------------
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
    
    if not english_part:
        english_part = segments[-1] if segments else title
    
    chinese_display_parts = []
    for segment in segments:
        segment = segment.strip()
        if _is_mainly_english(segment):
            break
        chinese_display_parts.append(segment)
    
    if not chinese_display_parts:
        chinese_display_parts = [segments[0]] if segments else [title]
    
    chinese_display = ' | '.join(chinese_display_parts)
    
    english_part = RE_PARENTHESIS.sub('', english_part)
    english_part = RE_BRACKETS.sub('', english_part)
    english_part = english_part.split('/')[0]
    english_part = RE_NON_WORD_CHARS.sub(' ', english_part)
    english_part = RE_MULTIPLE_SPACES.sub(' ', english_part).strip()
    
    words = english_part.split()
    if len(words) > 4:
        english_part = ' '.join(words[:4])
    
    english_part = convert_roman_to_arabic(english_part)
    
    return english_part.strip(), chinese_display.strip()

# -------------------- xydj 搜索 --------------------
# 游戏名称过滤关键词（预编译）
GAME_FILTER_KEYWORDS = {'v', '版', 'dlc', '中文', '手柄', '更新', '年度版', '豪华版', '终极版'}

async def search_game(game_name: str):
    # 1. 先检查内存缓存
    data = await get_cache(game_name, "search")
    if data:
        print(f"[XianYu Search] Memory cache hit for: {game_name}")
        return data[0], data[1]

    # 2. 直接去网站搜索游戏列表（不先查数据库）
    # 数据库只在用户选择游戏后查询链接
    print(f"[XianYu Search] Database miss, fetching from website: {game_name}")

    # 提前准备小写游戏名用于过滤
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

        # 检查是否遇到安全验证
        if "安全验证" in html or "guardok" in html:
            print(f"[XianYu Search] 遇到安全验证，cookie可能已失效")
            return "❌ 遇到网站安全验证，请联系管理员更新cookie", None

        soup = BeautifulSoup(html, "html.parser")
        games = []
        seen = set()
        articles = soup.select("article.post-grid a[href][title]")
        print(f"[XianYu Search] Found {len(articles)} articles")

        # 提前过滤，减少循环内判断
        for a in articles:
            title = a.get('title', '').strip()
            if not title or title in seen:
                continue
            # 快速过滤：标题必须包含搜索词
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
            # 即使没找到也缓存空结果，防止重复无效查询
            await set_cache_to_db(game_name, [None, None], "search")
            return None, None

        # 直接返回文本格式的游戏列表，不生成图片
        text_lines = []

        for idx, g in enumerate(games):
            # 提取游戏名和版本信息
            title_parts = g['title'].split('|')
            game_name_extracted = title_parts[0].strip()

            # 提取关键信息，保持简洁
            key_info = []
            for part in title_parts[1:]:
                part = part.strip()
                if any(keyword in part.lower() for keyword in ['v', '版', 'dlc', '中文', '手柄', '更新', '年度版']):
                    key_info.append(part)

            # 构建美观的格式
            display_text = f"{idx+1}. {game_name_extracted}"
            if key_info:
                display_text += f" | {' | '.join(key_info[:3])}"

            text_lines.append(display_text)

        text_result = "\n".join(text_lines)

        # 存入内存缓存
        await set_cache(game_name, [text_result, games], "search")

        # 保存到数据库（先保存基本信息，详情在获取后更新）
        for game in games:
            await save_game_to_db(game_name, game, None)

        return text_result, games


async def search_game_force_update(game_name: str):
    """强制从网站搜索游戏（跳过所有缓存，用于/更新命令）"""
    # 强制从网站搜索（跳过内存缓存和数据库查询）
    print(f"[Force Update] Fetching from website (skip all cache): {game_name}")

    # 提前准备小写游戏名用于过滤
    game_name_lower = game_name.lower()

    async with SEARCH_SEMAPHORE:
        url = f"https://www.xianyudanji.to/?cat=1&s={game_name}&order=views"
        print(f"[Force Update] Requesting: {url}")
        cookie = await get_xydj_cookie()
        headers = {"Cookie": cookie} if cookie else None
        html = await FAST_HTTP.get_text(url, headers=headers, timeout=12)
        if not html:
            print(f"[Force Update] No HTML returned")
            return None, None
        print(f"[Force Update] HTML length: {len(html)}")

        # 检查是否遇到安全验证
        if "安全验证" in html or "guardok" in html:
            print(f"[Force Update] 遇到安全验证，cookie可能已失效")
            return "❌ 遇到网站安全验证，请联系管理员更新cookie", None

        soup = BeautifulSoup(html, "html.parser")
        games = []
        seen = set()
        articles = soup.select("article.post-grid a[href][title]")
        print(f"[Force Update] Found {len(articles)} articles")

        # 提前过滤，减少循环内判断
        for a in articles:
            title = a.get('title', '').strip()
            if not title or title in seen:
                continue
            # 快速过滤：标题必须包含搜索词
            if game_name_lower not in title.lower():
                continue
            seen.add(title)
            img_src = a.select_one("img")
            games.append({
                "title": title,
                "url": a['href'],
                "img": img_src['src'] if img_src else ""
            })

        print(f"[Force Update] Filtered games: {len(games)}")
        if not games:
            return None, None

        # 直接返回文本格式的游戏列表，不生成图片
        text_lines = []

        for idx, g in enumerate(games):
            # 提取游戏名和版本信息
            title_parts = g['title'].split('|')
            game_name_extracted = title_parts[0].strip()

            # 提取关键信息，保持简洁
            key_info = []
            for part in title_parts[1:]:
                part = part.strip()
                if any(keyword in part.lower() for keyword in ['v', '版', 'dlc', '中文', '手柄', '更新', '年度版']):
                    key_info.append(part)

            # 构建美观的格式
            display_text = f"{idx+1}. {game_name_extracted}"
            if key_info:
                display_text += f" | {' | '.join(key_info[:3])}"

            text_lines.append(display_text)

        text_result = "\n".join(text_lines)

        # 存入内存缓存
        await set_cache(game_name, [text_result, games], "search")

        # 不在这里保存到数据库，等用户选择后再保存（在process_game_resource中）

        return text_result, games

# -------------------- xydj 详情 --------------------
async def extract_download_info(game_url: str, skip_cache: bool = False):
    """
    从游戏详情页提取下载信息
    返回格式：(["解压密码: 【xxx】", "百度网盘提取码: 【xxx】", ...], "2025年08月04日")
    返回一个元组：(详情列表, 网页更新时间)
    
    Args:
        game_url: 游戏详情页URL
        skip_cache: 是否跳过缓存（强制更新模式使用）
    """
    # 检查缓存（缓存现在存储元组）
    if not skip_cache:
        cached_data = await get_cache_from_db(game_url, "detail")
        if cached_data and isinstance(cached_data, (list, tuple)) and len(cached_data) == 2:
            results, web_updated_at = cached_data
            # 如果缓存中的解压密码看起来像是误抓的提取码（4位），则忽略缓存重新抓取
            is_bad_cache = False
            for line in results:
                if "解压密码" in line:
                    m = re.search(r'【([a-zA-Z0-9]{4})】', line)
                    if m:
                        is_bad_cache = True
                        break
            if not is_bad_cache:
                print(f"[XianYu Detail] Cache hit for: {game_url}")
                return results, web_updated_at
            else:
                print(f"[XianYu Detail] Bad cache detected for {game_url}, re-fetching...")
    else:
        print(f"[XianYu Detail] Skip cache (force update mode): {game_url}")

    async with SEARCH_SEMAPHORE:
        print(f"[XianYu Detail] Processing: {game_url}")
        try:
            # 带上 Cookie 请求详情页
            cookie = await get_xydj_cookie()
            headers = {"Cookie": cookie} if cookie else None
            html = await FAST_HTTP.get_text(game_url, headers=headers, timeout=20)
            if not html:
                print(f"[XianYu Detail] No HTML returned")
                return ["无法获取页面内容"], ""
            
            soup = BeautifulSoup(html, "html.parser")
            
            # 检查是否遇到安全验证
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
            web_updated_at = ""  # 网页更新时间
            
            # ========== 1. 提取最近更新时间 ==========
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
            
            # ========== 2. 提取解压密码（优先检查两种方式）==========
            
            # 方式一：检查 pan-download-card 中是否有"解压密码"卡片
            for card in box.select(".pan-download-card"):
                a_tag = card.select_one("a.pan-download-link")
                if not a_tag:
                    continue
                
                name_span = a_tag.select_one("span.pan-name")
                if name_span:
                    pan_name = name_span.get_text(strip=True)
                    # 如果网盘名称是"解压密码"，则提取其中的密码
                    if pan_name == "解压密码":
                        pwd_span = card.select_one("span.pan-pwd")
                        if pwd_span:
                            # 从 data-clipboard-text 获取
                            pwd_code = pwd_span.get("data-clipboard-text", "").strip()
                            if pwd_code:
                                password_val = pwd_code
                                print(f"[XianYu Detail] 从解压密码卡片获取: {password_val}")
                                break
            
            # 方式二：检查 down-info 区域
            if not password_val and down_info:
                # 查找包含"解压密码"的 li 元素
                for li in down_info.select("li"):
                    label = li.select_one(".data-label")
                    if label and "解压密码" in label.get_text(strip=True):
                        info = li.select_one(".info")
                        if info:
                            # 提取文本内容
                            pwd_text = info.get_text(strip=True)
                            # 尝试提取纯数字密码（如 437368）
                            if re.fullmatch(r'\d+', pwd_text):
                                password_val = pwd_text
                                print(f"[XianYu Detail] 从down-info获取数字密码: {password_val}")
                            else:
                                # 尝试从 b/span 标签中提取
                                b_tag = info.select_one("b")
                                if b_tag:
                                    pwd_text = b_tag.get_text(strip=True)
                                    if re.fullmatch(r'\d+', pwd_text):
                                        password_val = pwd_text
                                        print(f"[XianYu Detail] 从down-info b标签获取: {password_val}")
                            break
            
            # ========== 3. 提取网盘信息（排除解压密码卡片）==========
            for card in box.select(".pan-download-card"):
                a_tag = card.select_one("a.pan-download-link")
                if not a_tag:
                    continue
                    
                pan_name = ""
                pan_link = a_tag.get('href', '').strip()
                
                # 从链接文本判断网盘类型
                name_span = a_tag.select_one("span.pan-name")
                if name_span:
                    pan_name = name_span.get_text(strip=True)
                
                # 跳过"解压密码"卡片，这不是网盘
                if pan_name == "解压密码":
                    continue
                
                # 获取提取码 - 从 data-clipboard-text 属性
                pwd_span = card.select_one("span.pan-pwd")
                pwd_code = ""
                if pwd_span:
                    # 优先从 data-clipboard-text 获取
                    pwd_code = pwd_span.get("data-clipboard-text", "").strip()
                    # 如果属性没有，尝试从文本中提取 "密码：xxx"
                    if not pwd_code:
                        pwd_text = pwd_span.get_text(strip=True)
                        pwd_match = re.search(r'密码[：:]\s*([a-zA-Z0-9]+)', pwd_text)
                        if pwd_match:
                            pwd_code = pwd_match.group(1)
                
                # 只保留真正的网盘链接（百度、夸克、UC）
                if pan_link and pan_name and any(keyword in pan_name for keyword in ['百度', '夸克', 'UC']):
                    pan_cards.append({
                        "name": pan_name,
                        "link": pan_link,
                        "code": pwd_code
                    })
            
            # ========== 4. 构建结果 ==========
            # 添加解压密码（如果找到）
            if password_val:
                results.append(f"解压密码: 【{password_val}】")
            # 如果没找到解压密码，不添加任何提示（按用户要求，禁止把提取码写在解压密码上）
            
            # 添加网盘信息
            if pan_cards:
                for card in pan_cards:
                    # 添加提取码
                    if card.get("code"):
                        results.append(f"{card['name']}提取码: 【{card['code']}】")
                    
                    # 添加网盘链接（需要获取真实链接）
                    if card.get("link"):
                        # 获取重定向后的真实链接
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

            # 5. 缓存结果（现在缓存元组）
            has_valid_info = any("【" in line and "未找到" not in line for line in results)
            if has_valid_info:
                await set_cache_to_db(game_url, [results, web_updated_at], "detail")

            return results, web_updated_at
            
        except Exception as e:
            print(f"[XianYu Detail] Exception: {e}")
            return [f"解析游戏信息时出错: {e}"], ""


async def send_final_forward(group_id, 单机_lines: list[str], user_id: str = "0", user_nickname: str = "游戏助手"):
    """一次性构造：单机版资源"""
    nodes = []

    # 提取游戏名
    game_title = ""
    for line in 单机_lines:
        if "游戏名字：" in line:
            game_title = line.split("游戏名字：")[1].strip()
            break
    if not game_title:
        game_title = "游戏资源"

    # 单机版节点
    单机_msgs = [{"type": "text", "data": {"text": line}} for line in 单机_lines]
    nodes.append(napcat_service.construct_node(user_id, user_nickname, 单机_msgs))

    # 计算资源数量（统计包含 http 的网盘链接行）
    single_count = len([line for line in 单机_lines if "http" in line])
    
    summary = f"共找到 {single_count} 个资源链接"

    return await napcat_service.send_group_forward_msg(
        group_id=group_id,
        nodes=nodes,
        source=game_title,
        summary=summary,
        prompt=f"[{game_title[:30]}]",
        news=[{"text": "点击查看游戏资源详情"}]
    )


class SearchSession:
    def __init__(self, user_id, games, task=None, force_update=False):
        self.user_id = user_id
        self.games = games
        self.task = task
        self.processing = False
        self.force_update = force_update  # 是否强制更新模式

# -------------------- 插件主类 --------------------
class Xydj(NcatBotPlugin):
    name = "xydj"
    version = "1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sessions = {}  # group_id -> SearchSession
        # 初始化数据库缓存表
        init_cache_db()

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

    async def process_game_resource(self, game, event, force_update=False):
        """统一处理游戏资源获取和发送的函数
        
        逻辑流程：
        1. 先检查数据库是否有该游戏的链接
        2. 创建 ticket 让用户看广告
        3. 后台轮询：如果数据库有链接直接发，没有则去网站获取并存入数据库再发
        
        Args:
            game: 游戏数据（来自网站搜索）
            event: 消息事件
            force_update: 是否强制从网站更新（覆盖数据库）
        """
        print(f"[Resource] Processing: {game['title']}, force_update: {force_update}")
        try:
            # 获取处理后的名字和中文展示名
            english_keyword, chinese_display = extract_english_name(game['title'])
            # 打印搜索用的英文名到控制台
            print(f"[搜索关键词] 中文名: {chinese_display}, 英文名: {english_keyword}")

            # ============== 创建 Ticket ==================
            # 先创建 ticket 让用户看广告，资源在后台获取
            api_base = "https://hhxyyq.online"
            try:
                # 拼接游戏标题作为资源占位
                resource_text = f"游戏：{chinese_display}"
                payload = {
                    "platform": "qq_id",
                    "platform_id": str(event.user_id),
                    "app_id": "ncatbot_xydj",
                    "resource_payload": resource_text
                }
                import traceback
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(f"{api_base}/api/task/create", json=payload, timeout=10) as response:
                            res = await response.json()
                            print(f"[Resource] API Response: {res}")
                except Exception as req_e:
                    print(f"[Resource] aiohttp Request Exception: {req_e}")
                    traceback.print_exc()
                    raise req_e

                # 直接获取资源并发送（跳过票据和小程序流程）
                单机内容 = await self._get_resource_content(
                    game, english_keyword, chinese_display,
                    force_update, [], None, ""
                )

                if 单机内容:
                    await send_final_forward(event.group_id, 单机内容, str(event.user_id), event.sender.nickname)
                else:
                    await event.reply(
                        rtf=MessageArray([Reply(id=event.message_id), PlainText(text="❌ 获取资源失败，请稍后重试。")])
                    )

                # 以下代码已注释，跳过票据和小程序流程
                # ticket_id = res.get("ticket")
                # ... 原票据和卡片发送代码 ...

            except Exception as api_e:
                print(f"[Resource] API Error: {api_e}")
                await event.reply(rtf=MessageArray([Reply(id=event.message_id), PlainText(text=f"服务器通信失败: {str(api_e)}")]))
                return

        except Exception as e:
            print(f"[Resource] Processing exception: {e}")
            await event.reply(
                rtf=MessageArray([Reply(id=event.message_id), PlainText(text=f"处理失败: {str(e)}")])
            )

    async def _wait_and_send_resource(self, event, group_id, ticket_id, game, english_keyword, chinese_display, user_id, user_nickname, force_update=False):
        """轮询查询后端 Ticket 状态，如果验证通过则获取并发送资源
        
        逻辑流程：
        1. 先检查数据库是否有该游戏的链接
        2. 如果没有，在用户看广告的同时去网站获取并存入数据库
        3. 用户看完广告后，发送资源
        """
        max_retries = 30  # 最大轮询次数，比如30次（即2分钟）
        delay = 4         # 每次轮询间隔4秒
        
        # 告诉用户正在等待验证
        await event.reply(
            rtf=MessageArray([Reply(id=event.message_id), PlainText(text="✅ 请点击上方小程序链接（或卡片），在小程序内完成任务（例如看个广告）即可获取资源哦~ 我在这等你！")])
        )
        
        # 先检查数据库是否有链接（在看广告期间可以并行执行）
        db_games = await search_game_in_db(english_keyword)
        has_db_link = len(db_games) > 0 and db_games[0].get('download_links')
        
        # 如果数据库没有链接且不是强制更新模式，预先去网站获取（用户看广告时并行执行）
        fetched_lines = None
        web_updated_at = ""
        if not has_db_link and not force_update:
            print(f"[Wait Resource] 数据库无链接，预取网站数据: {chinese_display}")
            try:
                fetched_lines, web_updated_at = await extract_download_info(game['url'], skip_cache=False)
                if fetched_lines:
                    # 保存到数据库
                    await save_game_to_db(english_keyword, game, fetched_lines, web_updated_at)
                    print(f"[Wait Resource] 已预取并保存到数据库: {chinese_display}")
            except Exception as e:
                print(f"[Wait Resource] 预取数据失败: {e}")
        
        for i in range(max_retries):
            await asyncio.sleep(delay)
            try:
                # 调用后端接口查询 ticket 状态
                query_url = f"https://hhxyyq.online/api/user/get_result?ticket={ticket_id}"
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(query_url, timeout=5) as resp:
                        response = await resp.json()
                        
                if response and response.get("success"):
                    status = response.get("status")
                    if status == "claimed" or status == "verified":
                        # 验证通过，获取资源并发送
                        单机内容 = await self._get_resource_content(
                            game, english_keyword, chinese_display, 
                            force_update, db_games, fetched_lines, web_updated_at
                        )
                        
                        if 单机内容:
                            await send_final_forward(group_id, 单机内容, user_id, user_nickname)
                        else:
                            await event.reply(
                                rtf=MessageArray([Reply(id=event.message_id), PlainText(text="❌ 获取资源失败，请稍后重试。")])
                            )
                        return
            except Exception as e:
                import traceback
                print(f"[Poll Ticket] 轮询出错: {e}")
                traceback.print_exc()
                pass
                
        # 轮询超时
        await event.reply(
            rtf=MessageArray([Reply(id=event.message_id), PlainText(text="⏳ 等待超时啦，好像你还没有完成任务，资源未发放，需要重新搜索哦。")])
        )
    
    async def _get_resource_content(self, game, english_keyword, chinese_display, force_update, db_games, fetched_lines, web_updated_at):
        """获取资源内容，优先从数据库获取，没有则从网站获取"""
        单机_lines = []
        
        # 如果是强制更新模式，直接从网站获取
        if force_update:
            print(f"[Get Resource] 强制更新模式，从网站获取: {chinese_display}")
            单机_lines, _ = await extract_download_info(game['url'], skip_cache=True)
            if 单机_lines:
                await save_game_to_db(english_keyword, game, 单机_lines, web_updated_at)
            return self._build_resource_content(chinese_display, 单机_lines)
        
        # 1. 先检查数据库
        if db_games and db_games[0].get('download_links'):
            print(f"[Get Resource] 使用数据库数据: {chinese_display}")
            game_data = db_games[0]
            if game_data.get('decompress_password'):
                单机_lines.append(f"解压密码: 【{game_data['decompress_password']}】")
            for link in game_data.get('download_links', []):
                单机_lines.append(link)
            return self._build_resource_content(chinese_display, 单机_lines)
        
        # 2. 数据库没有，使用预取的数据
        if fetched_lines:
            print(f"[Get Resource] 使用预取数据: {chinese_display}")
            return self._build_resource_content(chinese_display, fetched_lines)
        
        # 3. 预取也失败了，最后尝试从网站获取
        print(f"[Get Resource] 最后尝试从网站获取: {chinese_display}")
        单机_lines, _ = await extract_download_info(game['url'], skip_cache=False)
        if 单机_lines:
            await save_game_to_db(english_keyword, game, 单机_lines, web_updated_at)
        return self._build_resource_content(chinese_display, 单机_lines)
    
    def _build_resource_content(self, chinese_display, 单机_lines):
        """构建资源发送内容"""
        if not 单机_lines:
            return None

        单机内容 = []
        单机内容.append("【单机版】\n")
        单机内容.append(f"游戏名字：{chinese_display}\n")
        for line in 单机_lines:
            单机内容.append(f"{line}\n")

        return 单机内容

    @registrar.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent):
        # 获取当前群组的会话
        session = self.sessions.get(event.group_id)
        
        # 检查是否是等待回复的状态，并且发送者是命令发起人
        if session and event.user_id == session.user_id:
            if session.processing:
                return
            
            choice = re.sub(r'\[CQ:[^\]]+\]', '', event.raw_message).strip()
            
            # 取消操作
            if choice == "0":
                await event.reply(
                rtf=MessageArray([Reply(id=event.message_id), PlainText(text="操作已取消。")])
                )
                self._cleanup(event.group_id)
                return
            
            # 验证选择
            if not choice.isdigit() or not 1 <= int(choice) <= len(session.games):
                await event.reply(
                rtf=MessageArray([Reply(id=event.message_id), PlainText(text="回复错误，操作已取消。请重新搜索游戏。")])
                )
                self._cleanup(event.group_id)
                return
            
            choice = int(choice)
            # 取消原来的无脑直接发送链接
            # await event.reply(
            #     rtf=MessageArray([Reply(id=event.message_id), PlainText(text=f"已选择第 {choice} 个游戏,我帮你找游戏，你帮我点一下：\n#小程序://工具铺/AN8wdJKGPenxRri\n点击登录退出即可,谢谢谢谢谢~")])
            # )
            
            session.processing = True
            # 取消超时计时器
            if session.task:
                session.task.cancel()
                session.task = None
            
            try:
                game = session.games[choice - 1]
                # 如果是强制更新模式，传递 force_update=True
                await self.process_game_resource(game, event, force_update=getattr(session, 'force_update', False))
            except Exception as e:
                await event.reply(
                rtf=MessageArray([Reply(id=event.message_id), PlainText(text=f"处理失败: {str(e)}")])
                )
            finally:
                self._cleanup(event.group_id)
        
        # 处理新的搜索命令
        elif event.raw_message.strip().startswith("搜索"):
            game_name = event.raw_message.strip()[2:].strip()
            if not game_name:
                await event.reply(
                rtf=MessageArray([Reply(id=event.message_id), PlainText(text="使用方法：搜索+游戏名称，例如：搜索 文明6")])
                )
                return
            
            try:
                text_result, games = await search_game(game_name)
                if not text_result:
                    await event.reply(
                rtf=MessageArray([Reply(id=event.message_id), PlainText(text="未找到，检查游戏名字，搜索游戏字数少一点试试呢")])
                    )
                    return
                
                # 如果只有一个游戏结果，直接自动处理
                if len(games) == 1:
                    # await event.reply(
                    # rtf=MessageArray([Reply(id=event.message_id), PlainText(text="我帮你找游戏，你帮我点一下：#小程序://工具铺/AN8wdJKGPenxRri  点击登录退出即可,谢谢谢谢谢~")])
                    # )
                    await self.process_game_resource(games[0], event)
                    return
                
                # 多个游戏结果，创建新会话
                await event.reply(
                rtf=MessageArray([Reply(id=event.message_id), PlainText(text=f"🎯 发现 {len(games)} 款游戏\n{text_result}\n⏰ 20秒内回复序号选择 | 回复 0 取消操作")])
                )
                
                # 创建会话并保存
                session = SearchSession(event.user_id, games)
                session.task = asyncio.create_task(self.countdown(event, event.group_id))
                self.sessions[event.group_id] = session
                
            except Exception as e:
                logging.exception(f"搜索出错: {e}")
                await event.reply(
                rtf=MessageArray([Reply(id=event.message_id), PlainText(text="发生错误，请稍后重试。")])
                )
        
        # 处理 /更新 命令 - 强制从网站搜索并覆盖数据库
        elif event.raw_message.strip().startswith("/更新"):
            game_name = event.raw_message.strip()[3:].strip()
            if not game_name:
                await event.reply(
                rtf=MessageArray([Reply(id=event.message_id), PlainText(text="使用方法：/更新+游戏名称，例如：/更新 只狼")])
                )
                return
            
            try:
                # 强制从网站搜索，跳过数据库查询
                await event.reply(
                rtf=MessageArray([Reply(id=event.message_id), PlainText(text=f"🔄 正在强制更新【{game_name}】的游戏数据...")])
                )
                
                text_result, games = await search_game_force_update(game_name)
                if not text_result:
                    await event.reply(
                rtf=MessageArray([Reply(id=event.message_id), PlainText(text="未找到，检查游戏名字，搜索游戏字数少一点试试呢")])
                    )
                    return
                
                # 如果只有一个游戏结果，直接自动处理（强制更新模式）
                if len(games) == 1:
                    # await event.reply(
                    # rtf=MessageArray([Reply(id=event.message_id), PlainText(text="我帮你找游戏，你帮我点一下：#小程序://工具铺/AN8wdJKGPenxRri  点击登录退出即可,谢谢谢谢谢~")])
                    # )
                    await self.process_game_resource(games[0], event, force_update=True)
                    return
                
                # 多个游戏结果，创建新会话（标记为强制更新模式）
                await event.reply(
                rtf=MessageArray([Reply(id=event.message_id), PlainText(text=f"🎯 发现 {len(games)} 款游戏\n{text_result}\n⏰ 20秒内回复序号选择 | 回复 0 取消操作")])
                )
                
                # 创建会话并保存，标记为强制更新模式
                session = SearchSession(event.user_id, games)
                session.force_update = True  # 标记强制更新
                session.task = asyncio.create_task(self.countdown(event, event.group_id))
                self.sessions[event.group_id] = session
                
            except Exception as e:
                logging.exception(f"强制更新出错: {e}")
                await event.reply(
                rtf=MessageArray([Reply(id=event.message_id), PlainText(text="发生错误，请稍后重试。")])
                )

    async def on_load(self):
        print(f"{self.name} 插件已加载，版本: {self.version}")
