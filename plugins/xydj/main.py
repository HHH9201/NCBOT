# /home/hjh/BOT/NCBOT/plugins/xydj/main.py
# -*- coding: utf-8 -*-
"""
咸鱼单机（单机版）+ ByrutGame（联机版）
双匿名合并转发卡片
"""
import re
import os
import time
import json
import asyncio
import logging
import yaml
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from ncatbot.plugin import BasePlugin
from ncatbot.core import registrar
from ncatbot.event.qq import GroupMessageEvent
from ncatbot.types import PlainText, At, Reply, MessageArray, Image

# 引入全局服务和配置
from common import (
    napcat_service, ai_service, GLOBAL_CONFIG,
    image_to_base64, normalize_text, convert_roman_to_arabic,
    load_yaml, save_yaml, clean_filename,
    DEFAULT_HEADERS, db_manager, AsyncHttpClient
)

# 配置更清爽的日志格式，去掉进程和线程信息
logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    level=logging.INFO
)

# -------------------- 提取配置 --------------------
# 加载插件本地配置
PLUGIN_DIR = Path(__file__).parent
CONFIG_FILE = PLUGIN_DIR / "tool" / "config.yaml"
LOCAL_CONFIG = load_yaml(CONFIG_FILE) if CONFIG_FILE.exists() else {}

BYRUT_BASE = LOCAL_CONFIG.get('byrut_base') or GLOBAL_CONFIG.get('byrut_base') or "https://napcat.1783069903.workers.dev"

# 构建 Cookie (优先使用本地配置)
cookies_dict = LOCAL_CONFIG.get('cookies', {})
if cookies_dict:
    XYDJ_COOKIE = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])
else:
    XYDJ_COOKIE = GLOBAL_CONFIG.get('xydj_cookie', '')

# 代理配置 (优先使用本地，否则使用全局)
PROXY = LOCAL_CONFIG.get('proxy') or GLOBAL_CONFIG.get('proxy')

# 图片路径处理
TOOL_DIR = Path(__file__).parent / "tool"
QQ_IMG = str(TOOL_DIR / LOCAL_CONFIG.get('images', {}).get('qq_img', "xcx.jpg"))
BACKUP_IMG = str(TOOL_DIR / LOCAL_CONFIG.get('images', {}).get('backup_img', "种子.png"))

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

# 快速HTTP客户端：禁用重试，缩短默认超时
FAST_HTTP = AsyncHttpClient(retry_count=1, retry_delay=0.0, timeout=15)

CACHE_FILE = Path(__file__).parent / "tool" / "cache" / "game_name_cache.yaml"
_title_cache = load_yaml(CACHE_FILE)

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
    # 检查缓存
    data = await get_cache(game_name, "search")
    if data:
        print(f"[XianYu Search] Cache hit for: {game_name}")
        return data[0], data[1]
    
    # 提前准备小写游戏名用于过滤
    game_name_lower = game_name.lower()
            
    async with SEARCH_SEMAPHORE:
        url = f"https://www.xianyudanji.to/?cat=1&s={game_name}&order=views"
        print(f"[XianYu Search] Requesting: {url}")
        headers = {"Cookie": XYDJ_COOKIE} if XYDJ_COOKIE else None
        html = await FAST_HTTP.get_text(url, proxy="", headers=headers, timeout=12)
        if not html:
            print(f"[XianYu Search] No HTML returned")
            return None, None
        print(f"[XianYu Search] HTML length: {len(html)}")
        
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
        
        # 存入缓存
        await set_cache_to_db(game_name, [text_result, games], "search")
        
        return text_result, games

# -------------------- xydj 详情 --------------------
async def extract_download_info(game_url: str):
    # 检查缓存
    data = await get_cache_from_db(game_url, "detail")
    if data:
        # 如果缓存中的解压密码看起来像是误抓的提取码（4位），则忽略缓存重新抓取
        is_bad_cache = False
        for line in data:
            if "解压密码" in line:
                m = re.search(r'【([a-zA-Z0-9]{4})】', line)
                if m:
                    is_bad_cache = True
                    break
        if not is_bad_cache:
            print(f"[XianYu Detail] Cache hit for: {game_url}")
            return data
        else:
            print(f"[XianYu Detail] Bad cache detected for {game_url}, re-fetching...")

    async with SEARCH_SEMAPHORE:
        print(f"[XianYu Detail] Processing: {game_url}")
        try:
            # 咸鱼单机详情页也不使用代理，带上 Cookie
            headers = {"Cookie": XYDJ_COOKIE} if XYDJ_COOKIE else None
            html = await FAST_HTTP.get_text(game_url, proxy="", headers=headers, timeout=20)
            if not html:
                print(f"[XianYu Detail] No HTML returned")
                return ["无法获取页面内容"]
            
            soup = BeautifulSoup(html, "html.parser")
            box = soup.select_one("#ripro_v2_shop_down-5")
            if not box:
                print(f"[XianYu Detail] Download box not found")
                return ["未找到下载区域"]
            
            print(f"[XianYu Detail] Download box found")
            
            # --- 提取逻辑重构 ---
            password_val = "未找到"
            pan_codes = [] # 改为列表，支持多个网盘提取码
            
            # 1. 遍历所有 btn-group 分组（处理网盘提取码和部分解压密码）
            groups = box.select(".btn-group")
            for group in groups:
                a_tag = group.select_one("a[href*='goto?down=']")
                if not a_tag:
                    continue
                
                label = a_tag.get_text(strip=True)
                btn = group.select_one("button[data-clipboard-text]")
                val = (btn.get("data-clipboard-text") or "").strip() if btn else ""
                
                if '解压密码' in label and val:
                    # 只有长度 > 4 的才认为是真正的解压密码
                    if len(val) > 4:
                        password_val = val
                elif any(k in label for k in ['百度', '天翼', '阿里', '迅雷', '夸克']) and val:
                    # 只有 4 位的才认为是提取码
                    if re.fullmatch(r'[A-Za-z0-9]{4}', val):
                        pan_codes.append(f"{label}提取码: 【{val}】")
            
            # 2. 从 .down-info 区域提取（处理你提供的这种新情况）
            if password_val == "未找到":
                info_list = box.select(".down-info li")
                for li in info_list:
                    label_el = li.select_one(".data-label")
                    info_el = li.select_one(".info")
                    if label_el and info_el:
                        label_text = label_el.get_text(strip=True)
                        info_text = info_el.get_text(strip=True)
                        if '解压密码' in label_text and info_text:
                            # 过滤掉“自动复制”之类的提示语，取核心词
                            if "点击" not in info_text and "复制" not in info_text:
                                password_val = info_text
                            else:
                                # 如果有提示语，尝试提取加粗部分或特定词
                                b_tag = info_el.select_one("b")
                                if b_tag:
                                    password_val = b_tag.get_text(strip=True)

            # 3. 兜底：如果还没找到，尝试全局正则（排除干扰）
            if password_val == "未找到":
                box_text = box.get_text(separator="\n", strip=True)
                # 匹配：解压密码：xxx，要求至少5位
                m = re.search(r'解压密码[:：]\s*([^\s\u4e00-\u9fa5]{4,})', box_text)
                if m: password_val = m.group(1).strip()
            
            results = [f"解压密码: 【{password_val}】"]
            
            # 添加网盘提取码
            if pan_codes:
                results.extend(pan_codes)
            else:
                results.append("百度网盘提取码: 未找到")
            
            # 提取下载链接（并行获取重定向）
            link_tasks = []
            link_names = []
            for a in box.select("a[target='_blank'][href*='goto?down=']"):
                name = a.get_text(strip=True)
                if '解压密码' in name:
                    continue
                jump_url = urljoin(game_url, a['href'])
                # 创建任务并行获取
                link_tasks.append(FAST_HTTP.get_redirect_url(jump_url, headers=headers, timeout=10))
                link_names.append(name)
            
            # 并行执行所有重定向请求
            found_any_link = False
            if link_tasks:
                redirect_results = await asyncio.gather(*link_tasks, return_exceptions=True)
                for name, real_url in zip(link_names, redirect_results):
                    if isinstance(real_url, Exception):
                        print(f"[XianYu Detail] 获取链接失败 {name}: {real_url}")
                        continue
                    if not real_url:
                        # 如果获取失败，使用原始URL
                        real_url = f"[跳转失败] {name}"
                    results.append(f"{name}: {real_url}")
                    found_any_link = True

            if not found_any_link:
                results.append("\n未获取到任何网盘链接，可能是 Cookie 已到期，请联系管理员更新。")

            
            print(f"[XianYu Detail] Results: {results}")
            
            # 只有当提取到有效信息时才缓存（避免缓存"未找到"的无效结果）
            # 检查结果中是否包含有效的密码信息
            has_valid_info = False
            for line in results:
                if "密码" in line and "未找到" not in line:
                    has_valid_info = True
                    break
            
            # 如果包含有效信息，或者已经重试过多次，则写入缓存
            # 这里策略是：只要不是全"未找到"，就缓存。如果全是"未找到"，则不缓存（以便下次重试）
            if has_valid_info:
                await set_cache_to_db(game_url, results, "detail")
            else:
                print(f"[XianYu Detail] No valid info found for {game_url}, skipping cache.")
            
            return results
        except Exception as e:
            print(f"[XianYu Detail] Exception: {e}")
            return [f"解析游戏信息时出错: {e}"]


# -------------------- ByrutGame 搜索（异步+代理+SSL 关闭） ----------
async def search_byrut(name: str) -> list:
    """返回 [{href, title, category}, ...] 最多3条"""
    if not name:
        return []

    # 检查缓存
    data = await get_cache_from_db(name, "byrut_search")
    if data:
        print(f"[Byrut Search] Cache hit for: {name}")
        return data

    async with SEARCH_SEMAPHORE:
        url = f"{BYRUT_BASE}/index.php?do=search"
        print(f"[Byrut Search] Requesting: {url} with name={name}")
        params = {
            "subaction": "search",
            "story": name
        }
        
        try:
            html = await FAST_HTTP.get_text(url, params=params, verify_ssl=False, timeout=12, proxy=PROXY)
            if not html:
                print(f"[Byrut Search] No HTML returned")
                # 缓存空结果
                await set_cache_to_db(name, [], "byrut_search")
                return []
            
            print(f"[Byrut Search] HTML length: {len(html)}")

            soup = BeautifulSoup(html, "html.parser")
            key = normalize_text(name)
            results, seen = [], set()
            
            articles = soup.select("a.search_res")
            print(f"[Byrut Search] Found {len(articles)} articles")
            
            for a in articles:
                href = a["href"]
                if "po-seti" not in href.lower():   # ← 只留联机
                    continue
                title_tag = a.select_one(".search_res_title")
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)
                if key not in normalize_text(title):
                    continue
                if href in seen:
                    continue
                seen.add(href)
                category = (
                    "联机版"
                    if any(k in href.lower() for k in ["po-seti", "onlayn", "multiplayer"])
                    else "单机版"
                )
                results.append({"href": href, "title": title, "category": category})
            
            print(f"[Byrut Search] Filtered results: {len(results)}")
            final_results = results[:3]
            
            # 存入缓存
            await set_cache_to_db(name, final_results, "byrut_search")
            
            return final_results

        except Exception as e:
            logging.error(f"[Byrut] 搜索异常: {e}")
            print(f"[Byrut Search] Exception: {e}")
            return []


# -------------------- 备用方案函数 --------------------
def _apply_backup_solution(item: dict, error_type: str) -> None:
    """应用备用方案，当主API不可用时提供基本功能"""
    logging.info(f"[Byrut] {error_type}，应用备用方案")
    print(f"[Byrut Backup] Applying backup solution due to: {error_type}")
    
    # 使用原始链接作为备用下载链接
    backup_torrent_url = item.get('href', '')
    
    # 替换域名
    if "napcat.1783069903.workers.dev" in backup_torrent_url:
        backup_torrent_url = backup_torrent_url.replace("https://napcat.1783069903.workers.dev", "https://byrutgame.org")
    
    # 检查备用图片是否存在
    backup_image = str(TOOL_DIR / "种子.png")
    if not os.path.exists(backup_image):
        # 如果文件不存在，使用文字标识
        backup_image = None
        logging.warning(f"[Byrut] 备用图片文件不存在: {backup_image}")
    
    # 更新项目信息
    item.update({
        "update_time": f"API连接失败，使用备用资源 ({error_type})", 
        "torrent_url": backup_torrent_url,
        "backup_image": backup_image,
        "backup_mode": True  # 标记为备用模式
    })

# -------------------- ByrutGame 详情（异步+代理+SSL 关闭） ----------
async def fetch_byrut_detail(item: dict) -> None:
    href = item["href"]
    
    # 检查缓存
    data = await get_cache_from_db(href, "byrut_detail")
    if data:
        print(f"[Byrut Detail] Cache hit for: {href}")
        update_time, torrent_url = data
        item.update({"update_time": update_time, "torrent_url": torrent_url})
        return

    async with SEARCH_SEMAPHORE:
        print(f"[Byrut Detail] Processing: {href}")
        # 检查是否已经是正确的链接
        if href.startswith("https://byrutgame.org"):
            proxy_url = href
        else:
            detail_path = href.replace("https://napcat.1783069903.workers.dev", "")
            if not detail_path.startswith("/"):
                detail_path = "/" + detail_path
            proxy_url = f"https://byrutgame.org{detail_path}"
        
        print(f"[Byrut Detail] Proxy URL: {proxy_url}")
        
        try:
            # 使用 http_client 获取内容，自动处理重试和 User-Agent 轮换
            # 传递 verify_ssl=False 以避免 SSL 错误
            html = await FAST_HTTP.get_text(proxy_url, verify_ssl=False, timeout=15, proxy=PROXY)
            
            if not html:
                print(f"[Byrut Detail] No HTML returned")
                _apply_backup_solution(item, "无法获取页面内容")
                return

        except Exception as e:
            logging.error(f"[Byrut] 详情页请求异常: {e}")
            print(f"[Byrut Detail] Exception: {e}")
            _apply_backup_solution(item, f"请求异常: {e}")
            return

        soup = BeautifulSoup(html, "html.parser")
        update_node = soup.select_one("div.tupd")
        update_text = update_node.get_text(strip=True) if update_node else ""
        m = re.search(r"(\d{1,2}\s+[а-яА-Я]+\s+\d{4},\s*\d{1,2}:\d{2})", update_text)
        
        if m:
            russian_date = m.group(1)
            # 俄文月份映射
            month_map = {
                'января': '1', 'февраля': '2', 'марта': '3', 'апреля': '4',
                'мая': '5', 'июня': '6', 'июля': '7', 'августа': '8',
                'сентября': '9', 'октября': '10', 'ноября': '11', 'декабря': '12'
            }
            
            # 解析俄文日期
            parts = russian_date.split()
            if len(parts) >= 3:
                day = parts[0]
                month_ru = parts[1].lower()
                year = parts[2].replace(',', '')
                
                # 转换为中文格式
                if month_ru in month_map:
                    month = month_map[month_ru]
                    # 提取时间部分
                    time_match = re.search(r'(\d{1,2}:\d{2})', russian_date)
                    time_str = time_match.group(1) if time_match else ""
                    
                    # 格式化为中文日期格式
                    update_time = f"{year}-{month}-{day} {time_str}".strip()
                else:
                    update_time = russian_date  # 如果转换失败，保持原样
            else:
                update_time = russian_date
        else:
            update_time = "未知"

        tor_tag = soup.select_one("a.itemtop_games") or soup.select_one("a:-soup-contains('Скачать торрент')")
        torrent_url = tor_tag["href"] if tor_tag else None
        if torrent_url and torrent_url.startswith("/"):
            torrent_url = f"https://byrutgame.org{torrent_url}"

        item.update({"update_time": update_time, "torrent_url": torrent_url})
        
        # 存入缓存
        await set_cache_to_db(href, (update_time, torrent_url), "byrut_detail")


async def send_final_forward(group_id, 赞助内容: list[str], 单机_lines: list[str], 联机_lines: list[str], user_id: str = "0", user_nickname: str = "游戏助手"):
    """一次性构造：赞助 + 单机版 + 联机版（节点内不再写游戏名）"""
    nodes = []

    # 1. 赞助节点
    sponsor_msgs = [{"type": "text", "data": {"text": 赞助内容[0]}}]
    qq_img_base64 = get_image_base64_cached(QQ_IMG)
    if qq_img_base64:
        sponsor_msgs.append({"type": "image", "data": {"file": qq_img_base64}})
    
    nodes.append(napcat_service.construct_node(user_id, user_nickname, sponsor_msgs))

    # 提取游戏名
    game_title = ""
    for line in 单机_lines:
        if "游戏名字：" in line:
            game_title = line.split("游戏名字：")[1].strip()
            break
    if not game_title:
        for line in 联机_lines:
            if "游戏名字：" in line:
                game_title = line.split("游戏名字：")[1].strip()
                break
    if not game_title:
        game_title = "游戏资源"

    # 2. 单机版节点
    单机_msgs = [{"type": "text", "data": {"text": line}} for line in 单机_lines]
    nodes.append(napcat_service.construct_node(user_id, user_nickname, 单机_msgs))

    # 3. 联机版节点
    if 联机_lines:
        联机_msgs = []
        for line in 联机_lines:
            # 检查是否是备用图片行
            if "备用图片：" in line:
                try:
                    parts = line.split("备用图片：")
                    if len(parts) > 1:
                        image_path = parts[1].strip()
                        if os.path.exists(image_path):
                            img_base64 = get_image_base64_cached(image_path)
                            if img_base64:
                                联机_msgs.append({"type": "image", "data": {"file": img_base64}})
                                continue  # 成功添加图片后跳过添加文本
                except Exception as e:
                    print(f"图片处理异常: {e}")
            
            # 默认作为文本添加
            联机_msgs.append({"type": "text", "data": {"text": line}})
                    
        nodes.append(napcat_service.construct_node(user_id, user_nickname, 联机_msgs))

    # 计算资源数量
    single_count = len([line for line in 单机_lines if "链接" in line])
    multi_count = len([line for line in 联机_lines if "种子链接" in line])
    total_count = single_count + multi_count
    
    summary = f"共找到 {total_count} 个资源链接"
    if single_count > 0:
        summary += f" (单机: {single_count} 个)"
    if multi_count > 0:
        summary += f" (联机: {multi_count} 个)"

    return await napcat_service.send_group_forward_msg(
        group_id=group_id,
        nodes=nodes,
        source=game_title,
        summary=summary,
        prompt=f"[{game_title[:30]}]",
        news=[{"text": "点击查看游戏资源详情"}]
    )


class SearchSession:
    def __init__(self, user_id, games, task=None):
        self.user_id = user_id
        self.games = games
        self.task = task
        self.processing = False

# -------------------- 插件主类 --------------------
class Xydj(BasePlugin):
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
            await self.api.qq.post_group_msg(
                group_id=group_id,
                rtf=MessageArray([Reply(id=event.message_id), PlainText(text="等待超时，操作已取消。请重新搜索")])
            )

    def _cleanup(self, group_id):
        if group_id in self.sessions:
            session = self.sessions[group_id]
            if session.task:
                session.task.cancel()
            del self.sessions[group_id]

    async def process_game_resource(self, game, event):
        """统一处理游戏资源获取和发送的函数（并行处理单机版和联机版资源）"""
        print(f"[Resource] Processing: {game['title']}")
        try:
            # 获取处理后的名字和中文展示名
            english_keyword, chinese_display = extract_english_name(game['title'])
            # 打印搜索用的英文名到控制台
            print(f"[搜索关键词] 中文名: {chinese_display}, 英文名: {english_keyword}")

            # 并行处理单机版和联机版资源
            async def process_single_player():
                """处理单机版资源"""
                print(f"[Single Player] Starting for: {game['url']}")
                单机内容 = []
                单机_lines = await extract_download_info(game['url'])
                if 单机_lines:
                    print(f"[Single Player] Found lines: {len(单机_lines)}")
                    单机内容.append("【单机版】\n")
                    单机内容.append(f"游戏名字：{chinese_display}\n")   # ← 中文展示名
                    # 逐行加 \n 保证密码/链接后都换行
                    for line in 单机_lines:
                        单机内容.append(f"{line}\n")
                else:
                    print(f"[Single Player] No lines found")
                    单机内容.append("【单机版】\n")
                    单机内容.append("未找到相关资源\n")
                return 单机内容

            async def process_multi_player():
                """处理联机版资源"""
                print(f"[Multi Player] Starting search for: {english_keyword}")
                # Byrut 联机版（用英文关键词搜，展示用完整标题）
                byrut_results = await search_byrut(english_keyword)   # 搜索仍走英文
                
                # 并行获取详情（带超时控制）
                if byrut_results:
                    print(f"[Byrut] Found {len(byrut_results)} items, fetching details in parallel...")
                    tasks = []
                    for item in byrut_results:
                        print(f"[Byrut] 找到联机资源: {item['href']}")
                        # 为每个详情请求添加超时保护
                        tasks.append(asyncio.wait_for(fetch_byrut_detail(item), timeout=30))
                    
                    # 并发执行所有详情页请求，使用 return_exceptions 防止一个失败影响其他
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # 处理异常结果
                    for idx, result in enumerate(results):
                        if isinstance(result, Exception):
                            print(f"[Byrut] 获取详情 {idx+1} 失败: {result}")
                            # 为失败的项目应用备用方案
                            _apply_backup_solution(byrut_results[idx], f"获取超时或异常: {result}")
                
                # 联机版内容（英文展示名 + 更新时间 + 种子）
                联机内容 = []
                if byrut_results:
                    print(f"[Multi Player] Found {len(byrut_results)} results")
                    联机内容.append("【联机版】\n")
                    联机内容.append(f"游戏名字：{english_keyword}\n")   # ← 英文展示名
                    
                    for idx, item in enumerate(byrut_results, 1):
                        if len(byrut_results) > 1:
                            联机内容.append(f"\n{idx}. 资源 {idx}\n")
                        
                        联机内容.append(f"解压密码：【online-fix.me】\n")
                        联机内容.append(f"更新时间：{item['update_time']}\n")
                        
                        if item.get('torrent_url'):
                            联机内容.append(f"种子链接：{item['torrent_url']}\n")
                        else:
                            联机内容.append(f"种子链接：暂无\n")
                        
                        # 如果有备用图片，添加图片标记
                        if item.get('backup_image'):
                            联机内容.append(f"备用图片：{item['backup_image']}\n")
                    
                    联机内容.append("使用提示：下载种子后使用BT客户端打开即可\n")
                else:
                    print(f"[Multi Player] No results found")
                    联机内容.append("【联机版】\n")
                    联机内容.append("未找到相关资源\n")
                    联机内容.append("通用解压密码：【online-fix.me】\n")
                    联机内容.append("查看教程：搜索和使用联机游戏\n")
                    联机内容.append("https://www.yuque.com/lanmeng-ijygo/ey7ah4/fe9hfep86cw7coku?singleDoc#\n")
                return 联机内容

            # 并行执行单机版和联机版资源获取
            单机内容, 联机内容 = await asyncio.gather(
                process_single_player(),
                process_multi_player(),
                return_exceptions=True  # 捕获异常，确保一个任务失败不会影响另一个
            )
            
            # 处理可能的异常
            if isinstance(单机内容, Exception):
                print(f"单机版资源获取失败: {单机内容}")
                单机内容 = ["【单机版】获取资源时出错\n"]
            
            if isinstance(联机内容, Exception):
                print(f"联机版资源获取失败: {联机内容}")
                联机内容 = ["【联机版】获取资源时出错"]
            
            # 4. 一次性转发
            赞助内容 = ["💡 提示：资源来自网络，仅供学习交流，收集资源不易，有帮助的话可以赞助一下！非常感谢！"]
            
            # 如果两条都空，再提示「部分未找到」
            if not 单机内容 and not 联机内容:
                print(f"[Resource] Both empty, sending warning")
                await self.api.qq.post_group_msg(
                    group_id=event.group_id,
                    rtf=MessageArray([Reply(id=event.message_id), PlainText(text="【联机版】未找到任何资源，可能关键词不匹配或服务器异常")])
                )
                return
            
            # 否则「有多少发多少」
            print(f"[Resource] Sending final forward message")
            await send_final_forward(event.group_id, 赞助内容, 单机内容, 联机内容, str(event.user_id), event.sender.nickname)
        except Exception as e:
            print(f"[Resource] Processing exception: {e}")
            await self.api.qq.post_group_msg(
                group_id=event.group_id, rtf=MessageArray([Reply(id=event.message_id), PlainText(text=f"处理失败: {str(e)}")])
            )

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
                await self.api.qq.post_group_msg(
                    group_id=event.group_id, rtf=MessageArray([Reply(id=event.message_id), PlainText(text="操作已取消。")])
                )
                self._cleanup(event.group_id)
                return
            
            # 验证选择
            if not choice.isdigit() or not 1 <= int(choice) <= len(session.games):
                await self.api.qq.post_group_msg(
                    group_id=event.group_id, rtf=MessageArray([Reply(id=event.message_id), PlainText(text="回复错误，操作已取消。请重新搜索游戏。")])
                )
                self._cleanup(event.group_id)
                return
            
            choice = int(choice)
            await self.api.qq.post_group_msg(
                group_id=event.group_id, rtf=MessageArray([Reply(id=event.message_id), PlainText(text=f"已选择第 {choice} 个游戏,我帮你找游戏，你帮我点一下：\n#小程序://工具铺/AN8wdJKGPenxRri\n点击登录退出即可,谢谢谢谢谢~")])
            )
            
            session.processing = True
            # 取消超时计时器
            if session.task:
                session.task.cancel()
                session.task = None
            
            try:
                game = session.games[choice - 1]
                await self.process_game_resource(game, event)
            except Exception as e:
                await self.api.qq.post_group_msg(
                    group_id=event.group_id, rtf=MessageArray([Reply(id=event.message_id), PlainText(text=f"处理失败: {str(e)}")])
                )
            finally:
                self._cleanup(event.group_id)
        
        # 处理新的搜索命令
        elif event.raw_message.strip().startswith("搜索"):
            game_name = event.raw_message.strip()[2:].strip()
            if not game_name:
                await self.api.qq.post_group_msg(
                    group_id=event.group_id, rtf=MessageArray([Reply(id=event.message_id), PlainText(text="使用方法：搜索+游戏名称，例如：搜索 文明6")])
                )
                return
            
            try:
                text_result, games = await search_game(game_name)
                if not text_result:
                    await self.api.qq.post_group_msg(
                        group_id=event.group_id, rtf=MessageArray([Reply(id=event.message_id), PlainText(text="未找到，检查游戏名字，搜索游戏字数少一点试试呢")])
                    )
                    return
                
                # 如果只有一个游戏结果，直接自动处理
                if len(games) == 1:
                    await self.api.qq.post_group_msg(
                        group_id=event.group_id, rtf=MessageArray([Reply(id=event.message_id), PlainText(text="我帮你找游戏，你帮我点一下：#小程序://工具铺/AN8wdJKGPenxRri  点击登录退出即可,谢谢谢谢谢~")])
                    )
                    await self.process_game_resource(games[0], event)
                    return
                
                # 多个游戏结果，创建新会话
                await self.api.qq.post_group_msg(
                    group_id=event.group_id, rtf=MessageArray([Reply(id=event.message_id), PlainText(text=f"🎯 发现 {len(games)} 款游戏\n{text_result}\n⏰ 20秒内回复序号选择 | 回复 0 取消操作")])
                )
                
                # 创建会话并保存
                session = SearchSession(event.user_id, games)
                session.task = asyncio.create_task(self.countdown(event, event.group_id))
                self.sessions[event.group_id] = session
                
            except Exception as e:
                logging.exception(f"搜索出错: {e}")
                await self.api.qq.post_group_msg(
                    group_id=event.group_id, rtf=MessageArray([Reply(id=event.message_id), PlainText(text="发生错误，请稍后重试。")])
                )

    async def on_load(self):
        print(f"{self.name} 插件已加载，版本: {self.version}")
