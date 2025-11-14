# plugins/ByrutGame/main.py
import re
import string
import requests
import json
import logging
import asyncio
import urllib3
import yaml
import os
from pathlib import Path
from bs4 import BeautifulSoup
from ncatbot.plugin import BasePlugin, CompatibleEnrollment
from ncatbot.core import GroupMessage, PrivateMessage

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 网络配置
PROXY = {
    "http": "http://127.0.0.1:7890",
    "https": "http://127.0.0.1:7890",
}
BASE = "https://api.hhxyyq.online"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0.0.0 Safari/537.36")

session = requests.Session()
session.headers.update({"User-Agent": UA})
session.proxies.update(PROXY)

# 关闭SSL验证警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 配置会话以更好地处理SSL问题
session.verify = False  # 禁用SSL验证（仅用于测试环境）

# 缓存文件路径
CACHE_FILE = Path(__file__).parent / "game_name_cache.yaml"

# 翻译接口
API_URL = "https://api.siliconflow.cn/v1/chat/completions"
API_HEADERS = {
    "Authorization": "Bearer sk-kkxxqdfvxhxgxefvrrfdkjsfashmjiojtrvydrxlnykdaoxm",
    "Content-Type": "application/json"
}

# 使用CompatibleEnrollment作为装饰器，不要实例化
bot = CompatibleEnrollment

class ByrutGame(BasePlugin):
    name = "ByrutGame"
    version = "1.0"

    def __init__(self, event_bus, **kwargs):
        super().__init__(event_bus, **kwargs)
        self._cache = self._load_cache()

    def _load_cache(self):
        """加载游戏名称缓存"""
        try:
            if CACHE_FILE.exists():
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
        except Exception as e:
            logging.warning(f"加载缓存失败: {e}")
        return {}

    def _save_cache(self):
        """保存游戏名称缓存"""
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                yaml.dump(self._cache, f, allow_unicode=True, sort_keys=True)
        except Exception as e:
            logging.error(f"保存缓存失败: {e}")

    def _get_cached_english_name(self, chinese_name):
        """从缓存获取英文名称"""
        return self._cache.get(chinese_name)

    def _cache_english_name(self, chinese_name, english_name):
        """缓存中英文名称映射"""
        if chinese_name and english_name and chinese_name != english_name:
            self._cache[chinese_name] = english_name
            self._save_cache()

    async def on_load(self):
        """插件加载时执行"""
        print(f"[{self.name}] 插件已注册到 NcatBot 插件系统，准备接收消息")
        print(f"[{self.name}] 已加载 {len(self._cache)} 条游戏名称缓存")



    @bot.group_event
    async def on_group(self, message):
        """群聊事件处理"""
        raw = message.raw_message
        if raw.startswith("联机 "):
            await self.do_search(raw[4:].strip(), message, is_private=False)
        elif raw.startswith("联机"):
            await self.do_search(raw[2:].strip(), message, is_private=False)
        elif raw.startswith("测试翻译 "):
            # 测试翻译功能
            test_text = raw[5:].strip()
            try:
                translated = self.translate(test_text)
                converted = self.convert_numbers_to_arabic(translated)
                await message.reply(f"原始: {test_text}\n翻译: {translated}\n数字转换: {converted}")
            except Exception as e:
                await message.reply(f"翻译测试失败: {e}")

    def translate(self, chinese: str) -> str:
        """翻译中文游戏名称为英文，优先使用缓存"""
        # 先检查缓存
        cached_name = self._get_cached_english_name(chinese)
        if cached_name:
            print(f"从缓存获取: {chinese} -> {cached_name}")
            return cached_name
        
        # 缓存中没有，调用API翻译
        payload = {
            "model": "moonshotai/Kimi-K2-Instruct-0905",
            "messages": [
                {"role": "system", "content": "你是Steam游戏名称翻译专家，专门将中文游戏名称准确翻译为Steam官方英文名称。规则：1. 只输出官方英文名称，不要添加任何解释 2. 遇到中文别名或简称时，必须映射到Steam官方完整名称 3. 如果无法确定官方名称，可以进行联网搜索 4. 所有的罗马数字（如V、VI、VII等）和英文数字（如Five、Six等）都必须转换成对应的阿拉伯数字（如5、6、7等），例如：Grand Theft Auto V 必须转换为 Grand Theft Auto 5"},
                {"role": "user", "content": f"{chinese} 在 Steam 上的英文正式名称是什么，必须将罗马数字和英文数字转换为阿拉伯数字"}
            ],
            "temperature": 0.1,
            "max_tokens": 30
        }
        try:
            resp = requests.post(API_URL, json=payload, headers=API_HEADERS, proxies=PROXY, timeout=10)
            resp.raise_for_status()
            result = resp.json()["choices"][0]["message"]["content"].strip()
            
            # 使用专门的数字转换函数确保所有数字都被转换为阿拉伯数字
            result = self.convert_numbers_to_arabic(result)
            
            # 缓存翻译结果
            self._cache_english_name(chinese, result)
            print(f"翻译并缓存: {chinese} -> {result}")
            
            return result
            
        except Exception as e:
            print(f"翻译失败: {e}")
            raise Exception("翻译失败")

    async def translate_to_chinese(self, text):
        """将俄文日期转换为标准格式"""
        if not text or text.strip() == "":
            return text
            
        # 俄文月份映射
        month_map = {
            'января': '1', 'февраля': '2', 'марта': '3', 'апреля': '4',
            'мая': '5', 'июня': '6', 'июля': '7', 'августа': '8',
            'сентября': '9', 'октября': '10', 'ноября': '11', 'декабря': '12',
            'Января': '1', 'Февраля': '2', 'Марта': '3', 'Апреля': '4',
            'Мая': '5', 'Июня': '6', 'Июля': '7', 'Августа': '8',
            'Сентября': '9', 'Октября': '10', 'Ноября': '11', 'Декабря': '12'
        }
        
        # 匹配俄文日期格式: 17 мая 2021, 17:21
        import re
        match = re.search(r'(\d{1,2})\s+([а-яА-Я]+)\s+(\d{4}),\s*(\d{1,2}):(\d{2})', text)
        if match:
            day, month_ru, year, hour, minute = match.groups()
            month = month_map.get(month_ru.lower(), month_ru)
            return f"{year}-{month}-{day.zfill(2)} {hour.zfill(2)}:{minute}"
        
        return text

    def translate_to_chinese_title(self, eng: str) -> str:
        """
        把英文游戏名翻译成steam游戏中文官方名
        缓存 1 小时，避免重复请求
        """
        if not eng:
            return eng
        # 用内存当缓存，重启失效即可；如需持久化可改 redis
        cache = getattr(self, "_title_cache", {})
        if eng in cache:
            return cache[eng]
        payload = {
            "model": "moonshotai/Kimi-K2-Instruct-0905",
            "messages": [
                {"role": "system", "content": "你是 Steam 中文名称翻译助手，只输出steam游戏中文名，其余任何文字都不要说。"},
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
        # 写缓存
        if not hasattr(self, "_title_cache"):
            self._title_cache = {}
        self._title_cache[eng] = zh
        return zh

    def normalize(self, txt):
        for p in string.punctuation:
            txt = txt.replace(p, " ")
        return " ".join(txt.lower().split())

    def convert_numbers_to_arabic(self, text: str) -> str:
        """
        将文本中的罗马数字和英文数字转换为阿拉伯数字
        """
        # 罗马数字到阿拉伯数字的映射
        roman_to_arabic = {
            'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5',
            'VI': '6', 'VII': '7', 'VIII': '8', 'IX': '9', 'X': '10',
            'XI': '11', 'XII': '12', 'XIII': '13', 'XIV': '14', 'XV': '15',
            'XVI': '16', 'XVII': '17', 'XVIII': '18', 'XIX': '19', 'XX': '20',
            'XXI': '21', 'XXII': '22', 'XXIII': '23', 'XXIV': '24', 'XXV': '25'
        }
        
        # 英文数字到阿拉伯数字的映射
        english_to_arabic = {
            'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5',
            'six': '6', 'seven': '7', 'eight': '8', 'nine': '9', 'ten': '10',
            'eleven': '11', 'twelve': '12', 'thirteen': '13', 'fourteen': '14', 'fifteen': '15',
            'sixteen': '16', 'seventeen': '17', 'eighteen': '18', 'nineteen': '19', 'twenty': '20'
        }
        
        result = text
        
        # 替换罗马数字（确保是独立的单词）
        for roman, arabic in roman_to_arabic.items():
            pattern = rf'\b{roman}\b'
            result = re.sub(pattern, arabic, result, flags=re.IGNORECASE)
        
        # 替换英文数字（确保是独立的单词）
        for english, arabic in english_to_arabic.items():
            pattern = rf'\b{english}\b'
            result = re.sub(pattern, arabic, result, flags=re.IGNORECASE)
        
        return result

    async def do_search(self, keyword: str, message, is_private: bool):
        """执行搜索并发送结果"""
        try:
            english_name = self.translate(keyword)
            print(f"翻译结果: {keyword} -> {english_name}")
            
            # 如果翻译失败（返回原文），直接使用原文进行搜索
            if english_name == keyword:
                print(f"翻译失败，使用原文搜索: {keyword}")
                await message.reply(f"翻译失败，将使用原文'{keyword}'进行搜索,如不正确，请百度搜索并输入steam中游戏的英文名称重新搜索")
                await self.search_and_display(keyword, keyword, message)
            else:
                await self.search_and_display(english_name, keyword, message)
        except Exception as e:
            print(f"搜索失败: {e}")
            # 翻译异常时，直接使用原文进行搜索
            print(f"翻译异常，使用原文搜索: {keyword}")
            await message.reply(f"翻译异常，将使用原文'{keyword}'进行搜索,如不正确，请百度搜索并输入steam中游戏的英文名称重新搜索")
            await self.search_and_display(keyword, keyword, message)

    async def search_and_display(self, name: str, original_keyword: str, message):
        search_url = f"{BASE}/index.php"
        params = {"do": "search", "subaction": "search", "story": name}
        try:
            resp = session.get(search_url, params=params, timeout=30)
            resp.raise_for_status()
        except requests.exceptions.SSLError as e:
            await message.reply(f"搜索失败：SSL连接错误，可能是网络问题或服务器证书问题，请稍后重试或者尝试使用【单机{original_keyword}】搜索，【搜索】前缀改为【单机】前缀即可")
            return
        except requests.exceptions.ConnectionError as e:
            await message.reply("搜索失败：网络连接错误，请尝试使用【单机{original_keyword}】搜索，【搜索】前缀改为【单机】前缀即可")
            return
        except requests.exceptions.Timeout as e:
            await message.reply("搜索失败：连接超时，请尝试使用【单机{original_keyword}】搜索，【搜索】前缀改为【单机】前缀即可")
            return
        except Exception as e:
            await message.reply(f"搜索失败：请尝试使用【单机{original_keyword}】搜索，【搜索】前缀改为【单机】前缀即可")
            return
        
        soup = BeautifulSoup(resp.text, "html.parser")

        key = self.normalize(name)
        results, seen = [], set()
        for a in soup.select("a.search_res"):
            title = a.select_one(".search_res_title").get_text(strip=True)
            if key not in self.normalize(title):
                continue
            href = a["href"]
            if href in seen:
                continue
            seen.add(href)
            # 根据链接路径判断游戏类型
            if "po-seti" in href.lower():
                category = "联机版"
            elif "onlayn" in href.lower() or "multiplayer" in href.lower():
                category = "联机版"
            else:
                category = "单机版"
            results.append({"href": href, "title": title, "category": category})

        total_count = len(results)
        
        # 如果没有找到结果，提示用户
        if total_count == 0:
            await message.reply(f"未找到与'{original_keyword}'相关的游戏，请尝试使用其他关键词或检查拼写")
            return
            
        display_count = min(5, total_count)

        for idx, item in enumerate(results[:display_count], 1):
            print(f"\n>>> 正在处理第 {idx} 条（{item['category']}）：{item['title']}")
            await self.fetch_detail(item)

        print("\n========== 全部提取完成 ==========")
        # 构造转发消息
        messages = []
        
        # 先添加提示消息（如果有）
        if total_count > 5:
            messages.append(
                f"💡 提示: 找到 {total_count} 个结果，建议增加更具体的关键词重新搜索，如文明5，文明6等，如不匹配则请尝试使用【单机{original_keyword}】进行搜索，【搜索】前缀改为【单机】前缀即可"
            )
        
        # 添加游戏信息
        for it in results[:display_count]:
            msg = (
                f"解压密码：online-fix.me\n"
                f"【{it['category']}】：{it['title']}\n"
                f"最近更新时间: {it['update_time']}\n"
                f"下载链接: {it['torrent_url']}"
            )
            messages.append(msg)

        # 发送转发消息
        await self.send_forward_message(message.group_id, messages)

    async def fetch_detail(self, item):
        detail_path = item["href"].replace("https://byrutgame.org", "")
        if not detail_path.startswith("/"):
            detail_path = "/" + detail_path
        proxy_url = f"{BASE}{detail_path}"

        try:
            html = session.get(proxy_url, timeout=30).text
        except requests.exceptions.SSLError:
            item.update({
                "update_time": "获取失败",
                "torrent_url": None
            })
            return
        except requests.exceptions.RequestException:
            item.update({
                "update_time": "获取失败",
                "torrent_url": None
            })
            return
        s = BeautifulSoup(html, "html.parser")

        update_node = s.select_one("div.tupd")
        update_text = update_node.get_text(strip=True) if update_node else ""
        m = re.search(r"(\d{1,2}\s+[а-яА-Я]+\s+\d{4},\s*\d{1,2}:\d{2})", update_text)
        update_time = m.group(1) if m else "未知"

        tor_tag = s.select_one("a.itemtop_games") or s.select_one("a:-soup-contains('Скачать торрент')")
        torrent_url = tor_tag["href"] if tor_tag else None
        if torrent_url and torrent_url.startswith("/"):
            torrent_url = f"{BASE}{torrent_url}"

        translated_update = await self.translate_to_chinese(update_time)
        item.update({
            "update_time": translated_update,
            "torrent_url": torrent_url
        })
        # ---- 新增 ---- 
        zh_title = self.translate_to_chinese_title(item["title"])
        print(f"游戏标题翻译: {item['title']} -> {zh_title}")
        item["title"] = zh_title
        # ----------------

    async def send_forward_message(self, group_id, messages):
        url = "http://localhost/:3006/send_group_forward_msg"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer he031701'
        }

        payload_messages = []
        
        # 添加固定的赞助消息节点
        txt = "觉得好用的话可以赞助一下服务器的费用，5毛1快不嫌少，5元10元不嫌多"
        fixed_message_node = {"type": "node", "data": {"content": [
            {"type": "text", "data": {"text": txt}},
            {"type": "image", "data": {"file": "/home/h/BOT/NC/plugins/xydj/tool/QQ.jpg"}}
        ]}}    

        payload_messages.append(fixed_message_node)

        for text in messages:
            node = {"type": "node", "data": {"content": []}}
            if text:
                node["data"]["content"].append({"type": "text", "data": {"text": text}})
            payload_messages.append(node)

        try:
            payload = json.dumps({
                "group_id": group_id,
                "messages": payload_messages
            })

            response = requests.post(
                url, 
                headers=headers, 
                data=payload, 
                timeout=30,
                proxies=None
            )
            
            logging.info("[Forward] status: %d", response.status_code)
            logging.info("[Forward] resp : %s", response.text)
            
            if response.status_code == 200:
                resp_data = response.json()
                if resp_data.get("status") == "failed":
                    logging.error("消息发送失败：%s", resp_data.get("message", "未知错误"))
                else:
                    logging.info("消息发送成功")
            else:
                logging.error("消息发送失败，状态码：%d，响应内容：%s", response.status_code, response.text)
                
        except Exception as e:
            logging.error("发送转发消息时发生未知错误：%s", str(e))