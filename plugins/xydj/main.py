# /home/hjh/BOT/NCBOT/plugins/xydj/main.py
# -*- coding: utf-8 -*-
"""
咸鱼单机（全能版）
- 整合了数据库搜索与同步逻辑
- 支持扫码解锁与机器人发消息同步
- 适配 NcatBot 5.0 框架
"""
import re
import asyncio
import logging
import httpx
import base64
from bs4 import BeautifulSoup
from typing import Optional
from ncatbot.plugin import BasePlugin
from ncatbot.event.qq import GroupMessageEvent
from ncatbot.types import PlainText, Reply, MessageArray, Image
from ncatbot.types.qq import ForwardConstructor
from ncatbot.core import registrar

# 引入全局服务和配置
from common import (
    GLOBAL_CONFIG,
)
from common.db_permissions import db_permission_manager

# 配置更清爽的日志格式
logger = logging.getLogger("xydj")

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
                elif pan_name in ("在线", "联机版") or ("联机" in pan_name and "补丁" not in pan_name): target_pan = "online"
                elif "补丁" in pan_name: target_pan = "patch"
                
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
        
        # 过滤必须有下载链接的游戏
        valid_cloud_games = []
        for g_data in cloud_games:
            zh_name = g_data.get("zh_name", "")
            en_name = g_data.get("en_name", "")
            
            # 严格过滤：中/英文名必须包含完整的搜索关键词
            if game_name.lower() not in zh_name.lower() and game_name.lower() not in en_name.lower():
                continue

            # 使用数据库返回的 has_link 字段，避免在此处拉取所有链接字段
            if g_data.get("has_link"):
                valid_cloud_games.append(g_data)
        
        if not valid_cloud_games:
            # 虽然找到了名字匹配的，但都没有主链接，也返回提示以触发网页搜索
            return "暂未收录", None

        for idx, game_data in enumerate(valid_cloud_games):
            zh_name = game_data.get("zh_name", "")
            en_name = game_data.get("en_name", "")
            display_text = f"{idx+1}. {zh_name}"
            if en_name: display_text += f"\n   英文名: {en_name}"
            text_lines.append(display_text)
            
            games.append({
                "from_db": True,
                "id": game_data.get("id"),
                "title": zh_name
            })
        return "\n\n".join(text_lines), games
    except Exception as e:
        logger.error(f"[DB Search] 搜索失败: {e}")
        return "搜索服务异常，请稍后再试", None


def _clean_field_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _looks_like_url(value) -> bool:
    text = _clean_field_text(value)
    return text.startswith(("http://", "https://"))


def _looks_like_datetime(value) -> bool:
    text = _clean_field_text(value)
    if not text:
        return False
    return bool(
        re.search(r"\d{4}年\d{1,2}月\d{1,2}日", text)
        or re.search(r"\d{4}-\d{1,2}-\d{1,2}", text)
        or re.search(r"\d{4}年\d{1,2}月\d{1,2}日\s+\d{1,2}:\d{2}", text)
    )


def _normalize_online_fields(game_data: dict) -> dict:
    """纠正联机字段常见错位，避免旧脏数据导致展示异常。"""
    raw_online_url = _clean_field_text(game_data.get("online_url"))
    raw_patch_url = _clean_field_text(game_data.get("patch_url"))
    raw_online_code = _clean_field_text(game_data.get("online_code"))
    raw_online_at = _clean_field_text(game_data.get("online_at"))

    urls = []
    dates = []
    texts = []
    for value in (raw_online_url, raw_patch_url, raw_online_code, raw_online_at):
        if not value:
            continue
        if _looks_like_url(value):
            if value not in urls:
                urls.append(value)
        elif _looks_like_datetime(value):
            if value not in dates:
                dates.append(value)
        else:
            if value not in texts:
                texts.append(value)

    online_url = raw_online_url if _looks_like_url(raw_online_url) else ""
    patch_url = raw_patch_url if _looks_like_url(raw_patch_url) else ""
    online_at = raw_online_at if _looks_like_datetime(raw_online_at) else ""
    online_code = raw_online_code
    if _looks_like_url(online_code) or _looks_like_datetime(online_code):
        online_code = ""

    if not online_url and urls:
        online_url = urls[0]
    if not patch_url:
        patch_url = next((url for url in urls if url != online_url), "")
    if not online_at and dates:
        online_at = dates[0]
    if not online_code and texts:
        online_code = texts[0]

    return {
        "online_url": online_url,
        "patch_url": patch_url,
        "online_code": online_code,
        "online_at": online_at,
    }


def has_any_pan_link(game_data: dict) -> bool:
    """判断资源详情里是否至少存在一个可发送的网盘链接。"""
    link_keys = (
        "baidu_url",
        "quark_url",
        "uc_url",
        "online_url",
        "patch_url",
        "pan123_url",
        "mobile_url",
        "tianyi_url",
        "xunlei_url",
    )
    for key in link_keys:
        value = game_data.get(key)
        if _looks_like_url(value):
            return True
    return False

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
        self.backend_url = GLOBAL_CONFIG.get("backend.url", "http://127.0.0.1:8978").rstrip("/")
        self.app_id = GLOBAL_CONFIG.get("app.id", "card_sender")
        self.app_secret = GLOBAL_CONFIG.get("app.secret", "")
        self.http_client: Optional[httpx.AsyncClient] = None

    async def _get_backend_client(self) -> httpx.AsyncClient:
        if self.http_client is None:
            self.http_client = httpx.AsyncClient(
                base_url=self.backend_url,
                timeout=30,
                headers={
                    "app-id": self.app_id,
                    "app-secret": self.app_secret,
                },
            )
        return self.http_client

    async def get_user_info(self, user_id):
        """获取用户信息，返回数据字典或 None"""
        try:
            # 修正接口路径：从 /api/admin/user_info 统一到正式权限校验接口
            # 注意：此处必须使用 resolve_openid 或直接查询 users 表的接口
            # 经过之前的优化，后端 /api/admin/user_info 应该已经支持通过 qq_id 查询
            client = await self._get_backend_client()
            resp = await client.get("/api/admin/user_info", params={
                "platform": "qq_id",
                "platform_id": user_id,
            })

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

    async def _has_bound_user(self, user_id: str) -> bool:
        """确认当前 QQ 是否已经和后端用户体系完成绑定。"""
        user_info = await self.get_user_info(user_id)
        return bool(user_info)

    def _build_game_messages(self, game_data):
        """构建三段式消息内容：单机、联机、图片"""
        messages = []
        online_fields = _normalize_online_fields(game_data)
        
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
        for key, pan_name, code_key in sp_pans:
            url = game_data.get(key)
            if url:
                sp_content.append(f"{pan_name}：{url}\n")
                code = game_data.get(code_key)
                if code:
                    sp_content.append(f"{pan_name}提取码：【{code}】\n")
                count += 1
                if count > 3: break
                
        updated_at = game_data.get("updated_at", "")
        if updated_at:
            sp_content.append(f"最近更新时间：{updated_at}\n")
            
        messages.append("".join(sp_content))
        
        # 2. 联机版
        online_url = online_fields["online_url"]
        patch_url = online_fields["patch_url"]
        if online_url or patch_url:
            ol_content = ["【联机版】\n"]
            ol_content.append(f"游戏中文名字：{zh_name}\n")
            
            # online_code 在这里承载联机版版本/附加说明，旧数据可能有错位，已在上方做过纠正。
            online_version = online_fields["online_code"]
            if online_version:
                ol_content.append(f"版本信息：【{online_version}】\n")
            
            if online_url:
                ol_content.append(f"联机版：{online_url}\n")
            if patch_url:
                ol_content.append(f"联机补丁：{patch_url}\n")
                
            online_at = online_fields["online_at"]
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

    async def process_game_resource(self, game, event):
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
            else:
                # 核心优化：如果来自数据库，此时只有 id，需要拉取完整详情
                if "db_data" not in game and "id" in game:
                    logger.info(f"[DB Detail] 延迟拉取完整资源详情: {game['title']} (ID: {game['id']})")
                    full_data = await db_permission_manager.get_game_resource_by_id(game["id"])
                    if not full_data:
                        await event.reply("❌ 数据库资源已失效。")
                        return
                    game["db_data"] = full_data

                # 数据库命中但没有任何网盘链接时，自动回退到网站抓取并回存数据库
                if not has_any_pan_link(game["db_data"]):
                    logger.info(f"[DB Detail] 数据库无可用网盘链接，回退网站抓取: {game['title']}")
                    await event.reply("数据库资源缺少可用链接，正在从网站抓取最新资源，请稍候...")

                    detail_url = game["db_data"].get("detail_url")
                    db_data = None
                    if detail_url:
                        db_data = await scrape_game_detail_and_save(game["title"], detail_url)

                    if not db_data:
                        _text_result, web_games = await search_game_from_web(game["title"])
                        if web_games:
                            db_data = await scrape_game_detail_and_save(game["title"], web_games[0]["detail_url"])

                    if not db_data or not has_any_pan_link(db_data):
                        await event.reply("❌ 数据库和网站都没有获取到可用资源链接。")
                        return

                    game["db_data"] = db_data

            # 1. 构造同步 Payload (机器人排版)
            messages = self._build_game_messages(game["db_data"])
            # 同步给后端时，取所有文字部分合并，不包含图片
            content_text = "\n".join([m for m in messages if isinstance(m, str)])
            
            # 2. 请求 Ticket
            ticket_id = None
            res_data = {}
            logger.info(f"[PopReady] Sending Payload: {content_text[:50]}...")
            client = await self._get_backend_client()
            # 优先从池子拿
            resp = await client.post(
                "/api/task/pop_ready",
                json={
                    "platform": "qq_id",
                    "platform_id": user_id,
                    "app_id": self.app_id,
                    "resource_payload": content_text,
                },
            )
            if resp.status_code != 200:
                # 池子没有则创建
                resp = await client.post(
                    "/api/task/create",
                    json={
                        "platform": "qq_id",
                        "platform_id": user_id,
                        "app_id": self.app_id,
                        "resource_payload": content_text,
                    },
                )

            if resp.status_code == 200:
                res_data = resp.json()
                ticket_id = res_data.get("ticket")

            if ticket_id:
                # 3. 以 Ticket 实际状态为准；只有 verified/claimed 才允许直接发送资源。
                try:
                    status_resp = await client.get("/api/user/get_result", params={"ticket": ticket_id}, timeout=5)
                    if status_resp.status_code == 200:
                        status_data = status_resp.json()
                        status = status_data.get("status")
                        bound_user = await self._has_bound_user(user_id)
                        if status == "claimed" or (status == "verified" and bound_user):
                            logger.info(f"[Auth] Ticket {ticket_id} 已验证且用户已绑定，直接发送资源。")
                            await self._send_final_forward(event.group_id, messages, user_id, event.sender.nickname)
                            return
                        logger.info(
                            f"[Auth] Ticket {ticket_id} 当前状态: {status or 'unknown'} | 绑定状态: {'yes' if bound_user else 'no'}，继续等待扫码验证。"
                        )
                    else:
                        logger.warning(f"[Auth] 查询 Ticket 状态失败: HTTP {status_resp.status_code}")
                except Exception as e:
                    logger.warning(f"[Auth] 查询 Ticket 状态异常，回退扫码流程: {e}")

                # 4. 下载并发送二维码
                qrcode_url = res_data.get("qrcode_url")
                msg_parts = [Reply(id=event.message_id)]
                try:
                    img_resp = await client.get(f"/api/task/qrcode/{ticket_id}", timeout=15)
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

                msg_parts.append(PlainText(text="\n✅ 首次搜索需要扫码完成绑定验证；验证成功后，后续再搜索将无需扫码，可直接获取资源。请长按二维码点击“点击获取”，完成后我将立即在此发送资源链接。QQ 内也可以直接长按二维码。"))
                
                try:
                    await event.reply(rtf=MessageArray(msg_parts))
                except Exception as e:
                    logger.error(f"发送二维码消息失败: {e}")
                    # 尝试只发送文字提示
                    await event.reply(f"⚠️ 二维码发送失败，请尝试访问: {qrcode_url}\n首次搜索需要先扫码完成绑定验证；验证成功后，后续搜索将无需扫码，我会直接发送资源。")

                # 5. 启动轮询
                asyncio.create_task(self._wait_and_send_resource(event.group_id, ticket_id, game, user_id, event.sender.nickname))
                return

            await event.reply("❌ 创建验证任务失败，请稍后重试。")
        except Exception as e:
            logger.error(f"处理资源失败: {e}")

    async def _wait_and_send_resource(self, group_id, ticket_id, game, user_id, nickname):
        messages = self._build_game_messages(game["db_data"])
        
        for _ in range(45):
            await asyncio.sleep(4)
            try:
                client = await self._get_backend_client()
                resp = await client.get("/api/user/get_result", params={"ticket": ticket_id})
                res = resp.json()
                status = res.get("status") if isinstance(res, dict) else None
                bound_user = await self._has_bound_user(user_id)
                if status == "claimed" or (status == "verified" and bound_user):
                    # 发送群消息
                    await self._send_final_forward(group_id, messages, user_id, nickname)
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
                self._cleanup(event.group_id)
                await self.process_game_resource(game, event)
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
                await self.process_game_resource(games[0], event)
                return
            
            if len(games) > 1:
                await event.reply(rtf=MessageArray([PlainText(text=f"🎯 发现 {len(games)} 款游戏\n{text_result}\n⏰ 20秒内回复序号选择 | 回复 0 取消")]))
                session = SearchSession(event.user_id, games, original_msg_id=event.message_id)
                session.task = asyncio.create_task(self.countdown(event, event.group_id))
                self.sessions[event.group_id] = session

    async def on_load(self):
        logger.info(f"[{self.name}] 插件已加载，版本: {self.version}")
        await self._get_backend_client()

    async def on_unload(self):
        if self.http_client is not None:
            await self.http_client.aclose()
            self.http_client = None
