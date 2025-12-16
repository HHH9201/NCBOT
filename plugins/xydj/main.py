# -*- coding: utf-8 -*-
"""
咸鱼单机（单机版）+ ByrutGame（联机版）
双匿名合并转发卡片
"""
import re
import os
import json
import asyncio
import logging
import yaml
import string
import base64
import aiohttp
import aiofiles
import requests
import urllib3
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from ncatbot.plugin import BasePlugin, CompatibleEnrollment
from ncatbot.core.message import GroupMessage
from ncatbot.core import Text, At, Reply, MessageChain, Image

# 配置更清爽的日志格式，去掉进程和线程信息

# API配置
API_URL = "https://api.siliconflow.cn/v1/chat/completions"
API_HEADERS = {
    "Authorization": "Bearer sk-ixmsswryqnmuyifjewdetqnjewdetq",
    "Content-Type": "application/json"
}

bot = CompatibleEnrollment


# -------------------- 基础配置 --------------------
QQ_IMG = "/home/hjh/BOT/NCBOT/plugins/xydj/tool/TG.png"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
COOKIES = {
    "_ok4_": "k7Ss53TvUyeXcsWfWBuG3EDFCuhFBobWvQAsWPR4u7n/Fx1oJgJ582qBY9G6J2s2mjP6qe3nvbV2HpnvLzDf8bo1kDTJie9uhaXfKSSh1qmvZC0OvV41h5ex++Iw3moO",
    "ripro_notice_cookie": "1",
    "TDC_itoken": "619377261%3A1765550565",
    "PHPSESSID": "10ul6aj41hfuguh3j71fvvn4g4",
    "wordpress_logged_in_c1baf48ff9d49282e5cd4050fece6d34": "HHH9201%7C1766760171%7C5mAlNcIYZrvtS4Cxg5ckAeyivEqEGcYux4YtHtolbnS%7Cb012109b8803e7f36bc7bd9cf4f0a475a7dd72465b8f78c60e7c228c698f3316"
}
PROXY = "http://127.0.0.1:7899"
BYRUT_BASE = "https://napcat.1783069903.workers.dev"
session = requests.Session()
session.headers.update(HEADERS)
session.proxies.update({"http": PROXY, "https": PROXY})
session.verify = False
urllib3.disable_warnings()

CACHE_FILE = Path(__file__).parent / "game_name_cache.yaml"

# -------------------- 工具函数 --------------------
def load_cache():
    try:
        if CACHE_FILE.exists():
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
    except Exception as e:
        logging.warning(f"加载缓存失败: {e}")
    return {}

def save_cache(c):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            yaml.dump(c, f, allow_unicode=True, sort_keys=True)
    except Exception as e:
        logging.error(f"保存缓存失败: {e}")

def normalize(txt):
    for p in string.punctuation:
        txt = txt.replace(p, " ")
    return " ".join(txt.lower().split())

# ------------------------------------------------------------------
# 2. 把英文关键词翻译成中文官方名（供界面展示，不用于搜索）
# ------------------------------------------------------------------
_title_cache = {}          # 重启即失效的内存缓存，如需持久化可改 redis

def translate_to_chinese_title(eng: str) -> str:
    """
    输入英文关键词，返回 Steam 官方中文名；失败则回退原文。
    缓存 1 小时，避免重复请求。
    """
    if not eng:
        return  eng

    global  _title_cache
    if eng in _title_cache:
        return _title_cache[eng]

    payload = {
        "model": "moonshotai/Kimi-K2-Instruct-0905",
        "messages": [
            {"role": "system", "content": "你是 Steam 中文名称翻译助手，只输出 steam 游戏官方中文名，其余任何文字都不要说。"},
            {"role": "user", "content": f"{eng} 的 Steam 官方游戏中文名是什么"}
        ],
        "temperature": 0.1,
        "max_tokens": 30
    }
    try:
        resp = requests.post(API_URL, json=payload, headers=API_HEADERS,
                             proxies=PROXY, timeout=10)
        resp.raise_for_status()
        zh = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logging.warning("中文翻译失败: %s", e)
        zh = eng          # 失败就回退原文

    _title_cache[eng] =  zh
    return zh

# ------------------------------------------------------------------
# 1. 提取英文关键词 + 中文展示名（返回 tuple）
# ------------------------------------------------------------------
def extract_english_name(title: str) -> tuple[str, str]:

    segments = title.split('|')
    
    # 寻找最简洁的英文游戏名
    english_part = ""
    for segment in reversed(segments):  # 从后往前找英文段
        segment = segment.strip()
        # 如果这段主要是英文字符，就认为是英文段
        if len(re.findall(r'[a-zA-Z]', segment)) > len(re.findall(r'[\u4e00-\u9fff]', segment)):
            english_part = segment
            break
    
    # 如果没找到英文段，用最后一段
    if not english_part:
        english_part = segments[-1] if segments else title
    
    # 中文展示名：从第一个中文段开始，到英文段之前的所有段
    chinese_display_parts = []
    for segment in segments:
        segment = segment.strip()
        # 如果这段主要是英文字符，就停止收集
        if len(re.findall(r'[a-zA-Z]', segment)) > len(re.findall(r'[\u4e00-\u9fff]', segment)):
            break
        chinese_display_parts.append(segment)
    
    # 如果没找到中文段，用第一段
    if not chinese_display_parts:
        chinese_display_parts = [segments[0]] if segments else [title]
    
    chinese_display = ' | '.join(chinese_display_parts)
    
    # 清理英文部分：去掉版本号、年份、特殊符号等
    # 去掉括号及其内容
    english_part = re.sub(r'\([^)]*\)', '', english_part)
    english_part = re.sub(r'\[[^\]]*\]', '', english_part)
    # 去掉斜杠后的重复内容
    english_part = english_part.split('/')[0]
    # 去掉特殊符号和多余空格
    english_part = re.sub(r'[^\w\s]', ' ', english_part)
    english_part = re.sub(r'\s+', ' ', english_part).strip()
    
    # 只保留前3-4个核心单词
    words = english_part.split()
    if len(words) > 4:
        english_part = ' '.join(words[:4])
    
    # 罗马→阿拉伯数字（仅英文关键词）
    roman_to_arabic = {
        'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5',
        'VI': '6', 'VII': '7', 'VIII': '8', 'IX': '9', 'X': '10',
        'XI': '11', 'XII': '12', 'XIII': '13', 'XIV': '14', 'XV': '15',
        'XVI': '16', 'XVII': '17', 'XVIII': '18', 'XIX': '19', 'XX': '20'
    }
    # 整词替换，忽略大小写
    for roman, arabic in roman_to_arabic.items():
        english_part = re.sub(rf'\b{roman}\b', arabic, english_part, flags=re.I)
    
    return english_part.strip(), chinese_display.strip()

# 删除 get_text_size 函数，不再使用

async def fetch_text(url, **kwargs):
    async with aiohttp.ClientSession(cookies=COOKIES, headers=HEADERS) as session:
        async with session.get(url, **kwargs) as resp:
            return await resp.text()

async def get_real_url(jump_url: str) -> str:
    async with aiohttp.ClientSession(cookies=COOKIES, headers=HEADERS) as s:
        async with s.head(jump_url, allow_redirects=False) as r:
            if 300 <= r.status < 400:
                return r.headers['Location']
        async with s.get(jump_url) as r:
            return str(r.url)

# -------------------- xydj 搜索 --------------------
async def search_game(game_name: str):
    url = f"https://www.xianyudanji.to/?cat=1&s={game_name}&order=views"
    html = await fetch_text(url, timeout=15)
    soup = BeautifulSoup(html, "lxml")
    games, seen = [], set()
    for a in soup.select("article.post-grid a[href][title]"):
        title = a['title'].strip()
        img_tag = a.select_one("img")
        img_src = img_tag['src'] if img_tag else ""
        if not title or title in seen or game_name not in title:
            continue
        seen.add(title)
        games.append({"title": title, "url": a['href'], "img": img_src})
    if not games:
        return None, None
    
    # 直接返回文本格式的游戏列表，不生成图片
    text_lines = []
    
    for idx, g in enumerate(games):
        # 提取游戏名和版本信息
        title_parts = g['title'].split('|')
        game_name = title_parts[0].strip()
        
        # 提取关键信息，保持简洁
        key_info = []
        for part in title_parts[1:]:
            part = part.strip()
            if any(keyword in part.lower() for keyword in ['v', '版', 'dlc', '中文', '手柄', '更新', '年度版']):
                key_info.append(part)
        
        # 构建美观的格式
        display_text = f"🔹 {idx+1}. {game_name}"
        if key_info:
            display_text += f" | {' | '.join(key_info[:3])}"
        
        text_lines.append(display_text)
    
    text_result = "\n".join(text_lines)
    
    return text_result, games

# -------------------- xydj 详情 --------------------
async def extract_download_info(game_url: str):
    try:
        html = await fetch_text(game_url, timeout=15)
        soup = BeautifulSoup(html, "lxml")
        box = soup.select_one("#ripro_v2_shop_down-5")
        if not box:
            return ["未找到下载区域"]
        results = []
        
        # 提取解压密码 - 支持两种不同的HTML格式
        password_found = False
        
        # 方法1: 从按钮组中提取解压密码（第一种格式）
        # 查找按钮组中包含"解压密码"文本的按钮
        password_btns = box.select('div.btn-group button.go-copy[data-clipboard-text]')
        for btn in password_btns:
            btn_text = btn.get_text(strip=True)
            # 检查按钮文本或相邻的链接文本是否包含"解压密码"
            adjacent_link = btn.find_previous_sibling('a') if btn else None
            link_text = adjacent_link.get_text(strip=True) if adjacent_link else ""
            
            if ('解压密码' in btn_text or '解压密码' in link_text):
                        clipboard_text = btn.get('data-clipboard-text', '').strip()
                        if clipboard_text:  # 确保密码不为空
                            results.append(f"解压密码: 【{clipboard_text}】")
                            password_found = True
                            break
        
        # 方法2: 从down-info区域提取解压密码（第二种格式）
        if not password_found:
            down_info = box.select_one('div.down-info')
            if down_info:
                # 查找包含"解压密码"的li元素
                password_lis = down_info.select('ul.infos li')
                for li in password_lis:
                    data_label = li.select_one('p.data-label')
                    if data_label and '解压密码' in data_label.get_text():
                        info_p = li.select_one('p.info')
                        if info_p:
                            # 提取密码文本，可能包含在span或b标签内
                            password_span = info_p.select_one('span')
                            password_b = info_p.select_one('b')
                            
                            if password_span:
                                password = password_span.get_text(strip=True)
                            elif password_b:
                                password = password_b.get_text(strip=True)
                            else:
                                password = info_p.get_text(strip=True)
                            
                            # 验证密码格式并添加到结果
                            if password and password != "解压密码=安装密码、激活码":  # 排除说明文字
                                results.append(f"解压密码: 【{password}】")
                                password_found = True
                                break
        
        # 方法3: 通用备用方案 - 查找任何可能包含密码的元素
        if not password_found:
            # 查找所有可能包含密码的元素
            potential_password_elements = box.select('[data-clipboard-text]')
            for element in potential_password_elements:
                clipboard_text = element.get('data-clipboard-text', '').strip()
                element_text = element.get_text(strip=True)
                
                # 判断是否为有效密码格式
                if (clipboard_text and 
                        len(clipboard_text) >= 4 and 
                        not any(keyword in clipboard_text for keyword in ['百度', '网盘', '提取', 'https', 'http']) and
                        ('密码' in element_text or '解压' in element_text)):
                        results.append(f"解压密码: 【{clipboard_text}】")
                        password_found = True
                        break
        
        # 如果所有方法都失败了
        if not password_found:
            results.append("解压密码: 未找到")
        
        # 提取百度网盘提取码
        bdpan_btn = None
        btn_groups = box.select('div.btn-group')
        if btn_groups:
            # 查找包含"百度网盘"的按钮组
            for group in btn_groups:
                a_tag = group.select_one('a[href*="goto?down="]')
                if a_tag and '百度网盘' in a_tag.get_text():
                    bdpan_btn = group.select_one('button.go-copy[data-clipboard-text]')
                    break
        
        if bdpan_btn and bdpan_btn.has_attr('data-clipboard-text'):
            results.append(f"百度网盘提取码: {bdpan_btn['data-clipboard-text'].strip()}")
        else:
            results.append("百度网盘提取码: 未找到")
            
        # 提取下载链接
        for a in box.select("a[target='_blank'][href*='goto?down=']"):
            name = a.get_text(strip=True)
            if '解压密码' in name:
                continue
            jump_url = urljoin(game_url, a['href'])
            real_url = await get_real_url(jump_url)
            results.append(f"{name}: {real_url}")
        return results
    except Exception as e:
        return [f"解析游戏信息时出错: {e}"]

# -------------------- 网络请求配置和错误处理 ----------
# 代理配置检查
if PROXY and not PROXY.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
    logging.warning(f"[Network] 代理配置格式可能不正确: {PROXY}")
    PROXY = None  # 禁用可能有问题的代理

# 增强的请求头配置（移除Brotli支持以避免解码错误）
# 添加更完整的请求头以模拟真实浏览器，避免403错误
HEADERS.update({
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate',  # 移除br(brotli)支持
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
    'Referer': "https://byrutgame.org",  # 添加Referer头
    'Origin': "https://byrutgame.org",  # 添加Origin头
    'DNT': '1',  # 不追踪请求
    'Connection': 'keep-alive',  # 保持连接
    'Upgrade-Insecure-Requests': '1',  # 升级不安全请求
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1'
})

# -------------------- ByrutGame 搜索（异步+代理+SSL 关闭） ----------
async def search_byrut(name: str) -> list:
    """返回 [{href, title, category}, ...] 最多3条"""
    params = {"do": "search", "subaction": "search", "story": name}
    url = "https://byrutgame.org/index.php"
    
    # 重试机制配置
    max_retries = 3
    retry_delay = 2
    text = None  # 用于存储成功获取的文本
    
    for attempt in range(max_retries):
        connector = aiohttp.TCPConnector(ssl=False, force_close=True)
        timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_connect=10, sock_read=10)
        session = None
        
        try:
            # 每次重试都创建全新的session和connector，避免session closed问题
            # 为了避免403，我们传递一个空的cookies字典，让服务器认为我们接受cookies
            session = aiohttp.ClientSession(
                connector=connector, 
                timeout=timeout, 
                headers=HEADERS,
                cookies={}  # 添加空cookies，避免服务器拒绝无cookies请求
            )
            
            # 构建请求参数
            request_params = {"params": params, "timeout": timeout}
            if PROXY:
                request_params["proxy"] = PROXY
            
            # 打印调试日志
            full_url = f"{url}?{ '&'.join([f'{k}={v}' for k, v in params.items()]) }"
            logging.debug(f"[Byrut] 发送请求：{full_url}")
            logging.debug(f"[Byrut] 请求headers：{HEADERS}")
            logging.debug(f"[Byrut] 请求proxy：{PROXY}")
            
            async with session.get(url, **request_params) as resp:
                # 打印响应日志
                logging.debug(f"[Byrut] 响应状态码：{resp.status}")
                logging.debug(f"[Byrut] 响应headers：{dict(resp.headers)}")
                
                if resp.status == 403:
                    logging.warning(f"[Byrut] 403 Forbidden (尝试 {attempt + 1}/{max_retries})")
                    # 尝试获取错误响应内容，分析403原因
                    error_content = await resp.text()
                    logging.debug(f"[Byrut] 403错误响应内容：{error_content[:500]}...")
                    
                    # 403时尝试更换User-Agent
                    if attempt < max_retries - 1:
                        # 轮换User-Agent
                        import random
                        user_agents = [
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/121.0",
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15"
                        ]
                        # 创建临时headers副本，轮换User-Agent
                        temp_headers = HEADERS.copy()
                        temp_headers['User-Agent'] = random.choice(user_agents)
                        session.headers.update(temp_headers)
                        logging.debug(f"[Byrut] 尝试更换User-Agent: {temp_headers['User-Agent']}")
                        
                        await asyncio.sleep(retry_delay * (attempt + 1))  # 指数退避
                        continue
                    return []          # 空 = 未找到
                elif resp.status != 200:
                    logging.warning(f"[Byrut] 反代返回状态码：{resp.status} (尝试 {attempt + 1}/{max_retries})")
                    # 尝试获取错误响应内容
                    error_content = await resp.text()
                    logging.debug(f"[Byrut] 错误响应内容：{error_content[:500]}...")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    return []          # 空 = 未找到
                text = await resp.text()
                logging.debug(f"[Byrut] 成功获取响应，长度：{len(text)} 字符")
                break  # 成功获取数据，跳出重试循环
                
        except aiohttp.ClientConnectorError as e:
            logging.error(f"[Byrut] 连接错误 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))  # 指数退避
                continue
            # 最后一次尝试失败，返回空结果
            logging.error("[Byrut] 所有重试尝试失败，返回空结果")
            return []
        except asyncio.TimeoutError as e:
            logging.error(f"[Byrut] 请求超时 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                continue
            return []
        except aiohttp.ClientPayloadError as e:
            logging.error(f"[Byrut] 数据传输错误 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                continue
            return []
        except Exception as e:
            logging.exception(f"[Byrut] 搜索请求失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                continue
            return []
        finally:
            # 确保session被正确关闭
            if session and not session.closed:
                await session.close()
            # 确保connector被正确关闭
            if connector and not connector.closed:
                await connector.close()
    
    # 如果没有获取到文本，返回空结果
    if text is None:
        return []

    soup = BeautifulSoup(text, "html.parser")
    key = normalize(name)
    results, seen = [], set()
    for a in soup.select("a.search_res"):
        href = a["href"]
        if "po-seti" not in href.lower():   # ← 只留联机
            continue
        title_tag = a.select_one(".search_res_title")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        if key not in normalize(title):
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
    return results[:3]   # 最多3条


# -------------------- 备用方案函数 --------------------
def _apply_backup_solution(item: dict, error_type: str) -> None:
    """应用备用方案，当主API不可用时提供基本功能"""
    logging.info(f"[Byrut] {error_type}，应用备用方案")
    
    # 使用原始链接作为备用下载链接
    backup_torrent_url = item.get('href', '')
    
    # 检查备用图片是否存在
    backup_image = "/home/hjh/BOT/NCBOT/plugins/xydj/tool/种子.png"
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
    # 检查是否已经是正确的链接
    if href.startswith("https://byrutgame.org"):
        # 已经是正确链接，直接使用
        proxy_url = href
    else:
        # 不是正确链接，转换为正确链接
        detail_path = href.replace("https://napcat.1783069903.workers.dev", "")
        if not detail_path.startswith("/"):
            detail_path = "/" + detail_path
        proxy_url = f"https://byrutgame.org{detail_path}"
    
    # 重试机制配置
    max_retries = 3
    retry_delay = 2
    html = None
    
    for attempt in range(max_retries):
        connector = aiohttp.TCPConnector(ssl=False, force_close=True)
        timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_connect=10, sock_read=10)
        session = None
        
        try:
            # 每次重试都创建全新的session和connector
            # 为了避免403，我们传递一个空的cookies字典，让服务器认为我们接受cookies
            session = aiohttp.ClientSession(
                connector=connector, 
                timeout=timeout, 
                headers=HEADERS,
                cookies={}  # 添加空cookies，避免服务器拒绝无cookies请求
            )
            
            # 构建请求参数
            request_params = {"timeout": timeout}
            if PROXY:
                request_params["proxy"] = PROXY
            
            # 打印调试日志
            logging.debug(f"[Byrut] 发送详情页请求：{proxy_url}")
            logging.debug(f"[Byrut] 请求headers：{HEADERS}")
            logging.debug(f"[Byrut] 请求proxy：{PROXY}")
            
            async with session.get(proxy_url, **request_params) as resp:
                # 打印响应日志
                logging.debug(f"[Byrut] 详情页响应状态码：{resp.status}")
                logging.debug(f"[Byrut] 详情页响应headers：{dict(resp.headers)}")
                
                if resp.status == 403:
                    logging.warning(f"[Byrut] 详情页403 Forbidden (尝试 {attempt + 1}/{max_retries})")
                    # 尝试获取错误响应内容，分析403原因
                    error_content = await resp.text()
                    logging.debug(f"[Byrut] 详情页403错误响应内容：{error_content[:500]}...")
                    
                    # 403时尝试更换User-Agent
                    if attempt < max_retries - 1:
                        # 轮换User-Agent
                        import random
                        user_agents = [
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/121.0",
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15"
                        ]
                        # 创建临时headers副本，轮换User-Agent
                        temp_headers = HEADERS.copy()
                        temp_headers['User-Agent'] = random.choice(user_agents)
                        session.headers.update(temp_headers)
                        logging.debug(f"[Byrut] 尝试更换User-Agent: {temp_headers['User-Agent']}")
                        
                        await asyncio.sleep(retry_delay * (attempt + 1))  # 指数退避
                        continue
                    # 最后一次尝试失败，使用备用方案
                    _apply_backup_solution(item, "HTTP 403 Forbidden错误")
                    return
                elif resp.status != 200:
                    logging.warning(f"[Byrut] 详情页状态码：{resp.status} (尝试 {attempt + 1}/{max_retries})")
                    # 尝试获取错误响应内容
                    error_content = await resp.text()
                    logging.debug(f"[Byrut] 详情页错误响应内容：{error_content[:500]}...")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    # 最后一次尝试失败，使用备用方案
                    _apply_backup_solution(item, "HTTP状态码错误")
                    return
                html = await resp.text()
                logging.debug(f"[Byrut] 成功获取详情页响应，长度：{len(html)} 字符")
                break  # 成功获取数据，跳出重试循环
                
        except aiohttp.ClientConnectorError as e:
            logging.error(f"[Byrut] 详情页连接错误 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))  # 指数退避
                continue
            # 最后一次尝试失败，使用备用方案
            _apply_backup_solution(item, "连接错误")
            return
        except asyncio.TimeoutError as e:
            logging.error(f"[Byrut] 详情页请求超时 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                continue
            _apply_backup_solution(item, "请求超时")
            return
        except aiohttp.ClientPayloadError as e:
            logging.error(f"[Byrut] 详情页数据传输错误 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                continue
            _apply_backup_solution(item, "数据传输错误")
            return
        except Exception as e:
            logging.exception(f"[Byrut] 详情页请求失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                continue
            _apply_backup_solution(item, "未知错误")
            return
        finally:
            # 确保session被正确关闭
            if session and not session.closed:
                await session.close()
            # 确保connector被正确关闭
            if connector and not connector.closed:
                await connector.close()
    
    # 如果没有获取到HTML，使用备用方案
    if html is None:
        _apply_backup_solution(item, "无法获取页面内容")
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


def image_to_base64(image_path):
    """将图片文件转换为base64编码字符串"""
    try:
        if not os.path.exists(image_path):
            logging.warning(f"图片文件不存在: {image_path}")
            return None
        
        with open(image_path, 'rb') as f:
            image_data = f.read()
            base64_encoded = base64.b64encode(image_data).decode('utf-8')
            return f"data:image/png;base64,{base64_encoded}"
    except Exception as e:
        logging.error(f"图片转base64失败: {e}")
        return None

async def send_final_forward(group_id, 赞助内容: list[str], 单机_lines: list[str], 联机_lines: list[str], user_id: str = "0", user_nickname: str = "游戏助手"):
    """一次性构造：赞助 + 单机版 + 联机版（节点内不再写游戏名）"""
    nodes = []

    # 1. 赞助节点
    # 使用 base64 编码的图片
    base_dir = "/home/hjh/BOT/NCBOT"
    abs_qq_img_path = QQ_IMG
    qq_img_base64 = image_to_base64(abs_qq_img_path)
    
    sponsor_content = [{"type": "text", "data": {"text": 赞助内容[0]}}]
    if qq_img_base64:
        sponsor_content.append({"type": "image", "data": {"file": qq_img_base64}})
    
    # 从消息中提取游戏名称，用于标题和摘要
    game_title = ""
    for line in 单机_lines:
        if "游戏名字" in line:
            game_title = line.split("游戏名字：")[1].strip()
            break
    if not game_title:
        for line in 联机_lines:
            if "游戏名字" in line:
                game_title = line.split("游戏名字：")[1].strip()
                break
    if not game_title:
        game_title = "游戏资源"

    # 1. 赞助节点
    nodes.append({
        "type": "node",
        "data": {
            "uin": user_id,
            "nickname": user_nickname,
            "content": sponsor_content
        }
    })

    # 2. 单机版节点（去掉标题行，只写网盘信息）
    单机_nodes = [{"type": "text", "data": {"text": line}} for line in 单机_lines]
    nodes.append({
        "type": "node",
        "data": {
            "uin": user_id,
            "nickname": user_nickname,
            "content": 单机_nodes
        }
    })

    # 3. 联机版节点（直接使用处理好的内容，不再重复添加标题）
    联机_nodes = []
    # 直接追加处理好的内容
    if 联机_lines:
        联机_nodes.extend([{"type": "text", "data": {"text": line}} for line in 联机_lines])
        
        # ③ 检查是否有备用图片需要添加
        for line in 联机_lines:
            if "备用图片" in line and line.split("备用图片：")[1].strip():
                image_path = line.split("备用图片：")[1].strip()
                if os.path.exists(image_path):
                    # 使用 base64 编码的图片
                    if not os.path.isabs(image_path):
                        base_dir = "/home/hjh/BOT/NCBOT"
                        abs_image_path = os.path.join(base_dir, "tool", os.path.basename(image_path))
                    else:
                        abs_image_path = image_path
                    
                    # 转换为 base64
                    backup_img_base64 = image_to_base64(abs_image_path)
                    if backup_img_base64:
                        联机_nodes.append({"type": "image", "data": {"file": backup_img_base64}})
                    break
    nodes.append({
        "type": "node",
        "data": {
            "uin": user_id,
            "nickname": user_nickname,
            "content": 联机_nodes
        }
    })

    # 4. 一次性发出
    url = "http://101.35.164.122:3006/send_group_forward_msg"
    headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer he031701'}
    
    # 计算资源数量
    single_count = len([line for line in 单机_lines if "链接" in line])
    multi_count = len([line for line in 联机_lines if "种子链接" in line])
    total_count = single_count + multi_count
    
    summary = f"共找到 {total_count} 个资源链接"
    if single_count > 0:
        summary += f" (单机: {single_count} 个)"
    if multi_count > 0:
        summary += f" (联机: {multi_count} 个)"
    
    payload = {
        "group_id": group_id,
        "messages": nodes,
        "source": game_title,
        "summary": summary,
        "prompt": f"[{game_title}]",
        "news": [{"text": "点击查看游戏资源详情"}]
    }

    # 5. 增强错误处理和网络容错
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get('status') == 'ok':
                            logging.info(f"[Byrut] 转发消息发送成功")
                            return True
                        else:
                            logging.warning(f"[Byrut] 转发消息发送失败: {result}")
                    else:
                        logging.warning(f"[Byrut] HTTP状态码错误: {resp.status}")
                        
                    if attempt < max_retries - 1:
                        logging.info(f"[Byrut] 重试发送转发消息 (尝试 {attempt + 2}/{max_retries})")
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        logging.error(f"[Byrut] 转发消息发送失败，已达到最大重试次数")
                        return False
                        
        except asyncio.TimeoutError as e:
            logging.error(f"[Byrut] 转发消息发送超时 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                continue
        except aiohttp.ClientConnectorError as e:
            logging.error(f"[Byrut] 转发消息连接错误 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))  # 指数退避
                continue
        except Exception as e:
            logging.exception(f"[Byrut] 转发消息发送异常 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                continue
    
    return False


# -------------------- 插件主类 --------------------
class Xydj(BasePlugin):
    name = "xydj"
    version = "1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message_queue = asyncio.Queue()
        self.waiting_for_reply = False
        self.processing = False
        self.user_who_sent_command = None
        self.filtered_games = []
        self.timer_task = None
        self._cache = load_cache()

    async def countdown(self, msg, group_id):
        await asyncio.sleep(40)
        if self.waiting_for_reply:
            self._cleanup()
            await self.api.post_group_msg(
                group_id=group_id,
                rtf=MessageChain([Reply(msg.message_id), Text("等待超时，操作已取消。请重新搜索")])
            )

    def _cleanup(self):
        self.waiting_for_reply = False
        self.processing = False
        if self.timer_task:
            self.timer_task.cancel()
            self.timer_task = None

    async def process_game_resource(self, game, msg):
        """统一处理游戏资源获取和发送的函数（并行处理单机版和联机版资源）"""
        try:
            # 获取处理后的名字和中文展示名
            english_keyword, chinese_display = extract_english_name(game['title'])
            # 打印搜索用的英文名到控制台
            print(f"[搜索关键词] 中文名: {chinese_display}, 英文名: {english_keyword}")

            # 并行处理单机版和联机版资源
            async def process_single_player():
                """处理单机版资源"""
                单机内容 = []
                单机_lines = await extract_download_info(game['url'])
                if 单机_lines:
                    单机内容.append("🎮 【单机版】\n")
                    单机内容.append(f"📌 游戏名字：{chinese_display}\n")   # ← 中文展示名
                    # 逐行加 \n 保证密码/链接后都换行
                    for line in 单机_lines:
                        if "解压密码" in line:
                            单机内容.append(f"🔑 {line}\n")
                        elif "百度网盘" in line:
                            单机内容.append(f"💾 {line}\n")
                        elif "链接" in line:
                            单机内容.append(f"🌐 {line}\n")
                        else:
                            单机内容.append(f"📋 {line}\n")
                else:
                    单机内容.append("🎮 【单机版】\n")
                    单机内容.append("❌ 未找到相关资源\n")
                return 单机内容

            async def process_multi_player():
                """处理联机版资源"""
                # Byrut 联机版（用英文关键词搜，展示用完整标题）
                byrut_results = await search_byrut(english_keyword)   # 搜索仍走英文
                # 打印搜索到的href到控制台
                for item in byrut_results:
                    print(f"[Byrut] 找到联机资源: {item['href']}")
                    await fetch_byrut_detail(item)
                
                # 联机版内容（英文展示名 + 更新时间 + 种子）
                联机内容 = []
                if byrut_results:
                    联机内容.append("🎮 【联机版】\n")
                    联机内容.append(f"📌 游戏名字：{english_keyword}\n")   # ← 英文展示名
                    
                    for idx, item in enumerate(byrut_results, 1):
                        if len(byrut_results) > 1:
                            联机内容.append(f"\n{idx}. 资源 {idx}\n")
                        
                        联机内容.append(f"🔑 解压密码：【online-fix.me】\n")
                        联机内容.append(f"⏰ 更新时间：{item['update_time']}\n")
                        
                        if item.get('torrent_url'):
                            联机内容.append(f"🌐 种子链接：{item['torrent_url']}\n")
                        else:
                            联机内容.append(f"❌ 种子链接：暂无\n")
                        
                        # 如果有备用图片，添加图片标记
                        if item.get('backup_image'):
                            联机内容.append(f"🖼️ 备用图片：{item['backup_image']}\n")
                    
                    联机内容.append("💡 使用提示：下载种子后使用BT客户端打开即可\n")
                else:
                    联机内容.append("🎮 【联机版】\n")
                    联机内容.append("❌ 未找到相关资源\n")
                    联机内容.append("🔑 通用解压密码：【online-fix.me】\n")
                    联机内容.append("📚 查看教程：《搜索和使用联机游戏》\n")
                    联机内容.append("🌐 https://www.yuque.com/lanmeng-ijygo/ey7ah4/fe9hfep86cw7coku?singleDoc#\n")
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
            赞助内容 = ["正规流量卡不是物联卡，官方客服可查套餐，官方APP可自己查余额\n有问题请扣主人~~：\nhttps://ym.ksjhaoka.com/?s=q9thdGIs326398"]
            
            # 如果两条都空，再提示「部分未找到」
            if not 单机内容 and not 联机内容:
                await self.api.post_group_msg(
                    group_id=msg.group_id,
                    rtf=MessageChain([Reply(msg.message_id), Text("【联机版】未找到任何资源，可能关键词不匹配或服务器异常")])
                )
                return
            
            # 否则「有多少发多少」
            await send_final_forward(msg.group_id, 赞助内容, 单机内容, 联机内容, str(msg.user_id), msg.sender.nickname)
        except Exception as e:
            await self.api.post_group_msg(
                group_id=msg.group_id, rtf=MessageChain([Reply(msg.message_id), Text(f"处理失败: {str(e)}")])
            )

    async def process_single_game(self, game, msg):
        """处理单个游戏的自动转发"""
        await self.process_game_resource(game, msg)

    @bot.group_event
    async def on_group_message(self, msg: GroupMessage):
        await self.message_queue.put(msg)
        if self.waiting_for_reply and msg.user_id == self.user_who_sent_command:
            if self.processing:
                return
            choice = re.sub(r'\[CQ:[^\]]+\]', '', msg.raw_message).strip()
            if choice == "0":
                await self.api.post_group_msg(
                    group_id=msg.group_id, rtf=MessageChain([Reply(msg.message_id), Text("操作已取消。")])
                )
                self._cleanup()
                return
            if not choice.isdigit() or not 1 <= int(choice) <= len(self.filtered_games):
                await self.api.post_group_msg(
                    group_id=msg.group_id, rtf=MessageChain([Reply(msg.message_id), Text("回复错误，操作已取消。请重新搜索游戏。")])
                )
                self._cleanup()
                return
            choice = int(choice)
            await self.api.post_group_msg(
                group_id=msg.group_id, rtf=MessageChain([Reply(msg.message_id), Text(f"已选择第 {choice} 个游戏，请等待大概1分钟！！！")])
            )
            self.processing = True
            self._cleanup()
            try:
                game = self.filtered_games[choice - 1]
                await self.process_game_resource(game, msg)
            except Exception as e:
                await self.api.post_group_msg(
                    group_id=msg.group_id, rtf=MessageChain([Reply(msg.message_id), Text(f"处理失败: {str(e)}")])
                )
            finally:
                self._cleanup()
        elif msg.raw_message.strip().startswith("搜索"):
            game_name = msg.raw_message.strip()[2:].strip()
            if not game_name:
                await self.api.post_group_msg(
                    group_id=msg.group_id, rtf=MessageChain([Reply(msg.message_id), Text("使用方法：搜索+游戏名称，例如：搜索 文明6")])
                )
                return
            try:
                text_result, games = await search_game(game_name)
                if not text_result:
                    await self.api.post_group_msg(
                        group_id=msg.group_id, rtf=MessageChain([Reply(msg.message_id), Text("未找到，检查游戏名字，搜索游戏字数少一点试试呢")])
                    )
                    return
                
                # 如果只有一个游戏结果，直接自动处理
                if len(games) == 1:
                    await self.api.post_group_msg(
                        group_id=msg.group_id, rtf=MessageChain([Reply(msg.message_id), Text("搜索到1个游戏，自动为您获取资源信息，请等待大概1分钟！！！")])
                    )
                    # 直接处理单个游戏
                    await self.process_single_game(games[0], msg)
                    return
                
                # 多个游戏结果，需要用户选择（直接发送文本，不发送图片）
                await self.api.post_group_msg(
                    group_id=msg.group_id, rtf=MessageChain([Reply(msg.message_id), Text(f"🎯 发现 {len(games)} 款游戏\n{text_result}\n⏰ 30秒内回复序号选择 | 回复 0 取消操作")])
                )
                self.waiting_for_reply = True
                self.user_who_sent_command = msg.user_id
                self.filtered_games = games
                self.timer_task = asyncio.create_task(self.countdown(msg, msg.group_id))
            except Exception as e:
                await self.api.post_group_msg(
                    group_id=msg.group_id, rtf=MessageChain([Reply(msg.message_id), Text("发生错误，请稍后重试。")])
                )

    async def on_load(self):
        print(f"{self.name} 插件已加载，版本: {self.version}")