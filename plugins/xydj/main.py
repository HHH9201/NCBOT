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
import urllib3
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from ncatbot.plugin import BasePlugin, CompatibleEnrollment
from ncatbot.core.message import GroupMessage
from ncatbot.core import Text, At, Reply, MessageChain, Image

# 引入全局服务和配置
from common import (
    napcat_service, ai_service, GLOBAL_CONFIG,
    image_to_base64, normalize_text, convert_roman_to_arabic,
    load_yaml, save_yaml, clean_filename,
    http_client, DEFAULT_HEADERS
)

# 配置更清爽的日志格式，去掉进程和线程信息
logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    level=logging.INFO
)

# -------------------- 提取配置 --------------------
BYRUT_BASE = GLOBAL_CONFIG.get('byrut_base')
COOKIES = GLOBAL_CONFIG.get('cookies', {})

# 图片路径处理
TOOL_DIR = Path(__file__).parent / "tool"
QQ_IMG = str(TOOL_DIR / GLOBAL_CONFIG.get('images', {}).get('qq_img', "TG.png"))
BACKUP_IMG = str(TOOL_DIR / GLOBAL_CONFIG.get('images', {}).get('backup_img', "种子.png"))

bot = CompatibleEnrollment

urllib3.disable_warnings()

CACHE_FILE = Path(__file__).parent / "game_name_cache.yaml"
_title_cache = load_yaml(CACHE_FILE)

async def translate_to_chinese_title(eng: str) -> str:
    """
    输入英文关键词，返回 Steam 官方中文名；失败则回退原文。
    """
    if not eng:
        return eng

    global _title_cache
    if eng in _title_cache:
        return _title_cache[eng]

    system_prompt = "你是 Steam 中文名称翻译助手，只输出 steam 游戏官方中文名，其余任何文字都不要说。"
    prompt = f"{eng} 的 Steam 官方游戏中文名是什么"
    
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        # 调用AI服务进行翻译
        # 注意：这里需要传递正确的参数，原代码中的PROXY变量已被移除，需要从GLOBAL_CONFIG获取
        proxy = GLOBAL_CONFIG.get('proxy')
        zh = await ai_service.chat_completions(messages, temperature=0.1, max_tokens=30, proxy=proxy)
        
        if not zh:
            zh = eng
    except Exception as e:
        logging.error(f"翻译失败: {e}")
        zh = eng

    _title_cache[eng] = zh
    save_yaml(CACHE_FILE, _title_cache)
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
    english_part = convert_roman_to_arabic(english_part)
    
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


# -------------------- ByrutGame 搜索（异步+代理+SSL 关闭） ----------
async def search_byrut(name: str) -> list:
    """返回 [{href, title, category}, ...] 最多3条"""
    if not name:
        return []

    url = f"{BYRUT_BASE}/index.php?do=search"
    params = {
        "subaction": "search",
        "story": name
    }
    
    try:
        html = await http_client.get_text(url, params=params, verify_ssl=False)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        key = normalize_text(name)
        results, seen = [], set()
        
        for a in soup.select("a.search_res"):
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
            
        return results[:3]   # 最多3条

    except Exception as e:
        logging.error(f"[Byrut] 搜索异常: {e}")
        return []


# -------------------- 备用方案函数 --------------------
def _apply_backup_solution(item: dict, error_type: str) -> None:
    """应用备用方案，当主API不可用时提供基本功能"""
    logging.info(f"[Byrut] {error_type}，应用备用方案")
    
    # 使用原始链接作为备用下载链接
    backup_torrent_url = item.get('href', '')
    
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
    # 检查是否已经是正确的链接
    if href.startswith("https://byrutgame.org"):
        proxy_url = href
    else:
        detail_path = href.replace("https://napcat.1783069903.workers.dev", "")
        if not detail_path.startswith("/"):
            detail_path = "/" + detail_path
        proxy_url = f"https://byrutgame.org{detail_path}"
    
    try:
        # 使用 http_client 获取内容，自动处理重试和 User-Agent 轮换
        # 传递 verify_ssl=False 以避免 SSL 错误
        html = await http_client.get_text(proxy_url, verify_ssl=False)
        
        if not html:
            _apply_backup_solution(item, "无法获取页面内容")
            return

    except Exception as e:
        logging.error(f"[Byrut] 详情页请求异常: {e}")
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
        if "游戏名字：" in line:
            parts = line.split("游戏名字：")
            if len(parts) > 1:
                game_title = parts[1].strip()
                break
    if not game_title:
        for line in 联机_lines:
            if "游戏名字：" in line:
                parts = line.split("游戏名字：")
                if len(parts) > 1:
                    game_title = parts[1].strip()
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
    # 计算资源数量
    single_count = len([line for line in 单机_lines if "链接" in line])
    multi_count = len([line for line in 联机_lines if "种子链接" in line])
    total_count = single_count + multi_count
    
    summary = f"共找到 {total_count} 个资源链接"
    if single_count > 0:
        summary += f" (单机: {single_count} 个)"
    if multi_count > 0:
        summary += f" (联机: {multi_count} 个)"
    
    # 5. 使用全局 NapCat 服务发送
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

    async def countdown(self, msg, group_id):
        await asyncio.sleep(40)
        session = self.sessions.get(group_id)
        if session and not session.processing:
            self._cleanup(group_id)
            await self.api.post_group_msg(
                group_id=group_id,
                rtf=MessageChain([Reply(msg.message_id), Text("等待超时，操作已取消。请重新搜索")])
            )

    def _cleanup(self, group_id):
        if group_id in self.sessions:
            session = self.sessions[group_id]
            if session.task:
                session.task.cancel()
            del self.sessions[group_id]

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
        # 获取当前群组的会话
        session = self.sessions.get(msg.group_id)
        
        # 检查是否是等待回复的状态，并且发送者是命令发起人
        if session and msg.user_id == session.user_id:
            if session.processing:
                return
            
            choice = re.sub(r'\[CQ:[^\]]+\]', '', msg.raw_message).strip()
            
            # 取消操作
            if choice == "0":
                await self.api.post_group_msg(
                    group_id=msg.group_id, rtf=MessageChain([Reply(msg.message_id), Text("操作已取消。")])
                )
                self._cleanup(msg.group_id)
                return
            
            # 验证选择
            if not choice.isdigit() or not 1 <= int(choice) <= len(session.games):
                await self.api.post_group_msg(
                    group_id=msg.group_id, rtf=MessageChain([Reply(msg.message_id), Text("回复错误，操作已取消。请重新搜索游戏。")])
                )
                self._cleanup(msg.group_id)
                return
            
            choice = int(choice)
            await self.api.post_group_msg(
                group_id=msg.group_id, rtf=MessageChain([Reply(msg.message_id), Text(f"已选择第 {choice} 个游戏，请等待大概1分钟！！！")])
            )
            
            session.processing = True
            # 取消超时计时器
            if session.task:
                session.task.cancel()
                session.task = None
            
            try:
                game = session.games[choice - 1]
                await self.process_game_resource(game, msg)
            except Exception as e:
                await self.api.post_group_msg(
                    group_id=msg.group_id, rtf=MessageChain([Reply(msg.message_id), Text(f"处理失败: {str(e)}")])
                )
            finally:
                self._cleanup(msg.group_id)
        
        # 处理新的搜索命令
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
                    await self.process_single_game(games[0], msg)
                    return
                
                # 多个游戏结果，创建新会话
                await self.api.post_group_msg(
                    group_id=msg.group_id, rtf=MessageChain([Reply(msg.message_id), Text(f"🎯 发现 {len(games)} 款游戏\n{text_result}\n⏰ 30秒内回复序号选择 | 回复 0 取消操作")])
                )
                
                # 创建会话并保存
                session = SearchSession(msg.user_id, games)
                session.task = asyncio.create_task(self.countdown(msg, msg.group_id))
                self.sessions[msg.group_id] = session
                
            except Exception as e:
                logging.exception(f"搜索出错: {e}")
                await self.api.post_group_msg(
                    group_id=msg.group_id, rtf=MessageChain([Reply(msg.message_id), Text("发生错误，请稍后重试。")])
                )

    async def on_load(self):
        print(f"{self.name} 插件已加载，版本: {self.version}")
