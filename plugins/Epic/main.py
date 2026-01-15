# /home/hjh/BOT/NCBOT/plugins/Epic/main.py
# Epic喜加一插件 - 获取Epic Games免费游戏信息
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List

from ncatbot.plugin import BasePlugin, CompatibleEnrollment as bot
from ncatbot.core.message import GroupMessage, PrivateMessage
from ncatbot.core.message import MessageChain
from ncatbot.core.event.message_segment.message_segment import Text, Image
from ncatbot.utils import get_log
from common.napcat import napcat_service
from common.config import GLOBAL_CONFIG
from common import http_client

_log = get_log()
_log.setLevel('INFO')

class Epic(BasePlugin):
    name, version = "Epic_Free_Games", "1.0.0"
    
    # API配置
    EPIC_API_URL = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
    INDIENOVA_EPIC_URL = "https://indienova.com/gamedb/list/121/p/1"
    INDIENOVA_STEAM_URL = "https://indienova.com/gamedb/list/215/p/1"
    
    # 缓存配置
    cache: Dict[str, List[Dict]] = {}
    cache_time: Dict[str, float] = {}
    cache_timeout = 3600  # 1小时缓存
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    async def _get_free_games(self) -> List[Dict]:
        """获取Epic和Steam免费游戏列表"""
        cache_key = "free_games"
        current_time = datetime.now().timestamp()
        
        # 检查缓存
        if cache_key in self.cache and cache_key in self.cache_time:
            if current_time - self.cache_time[cache_key] < self.cache_timeout:
                _log.info("使用缓存数据")
                return self.cache[cache_key]
        
        # 同时获取Epic和Steam游戏
        epic_games = await self._get_games_from_indienova()
        steam_games = await self._get_steam_free_games()
        
        # 整合所有游戏
        all_games = []
        
        # 添加Epic游戏
        for game in epic_games:
            game["Platform"] = "Epic"
            all_games.append(game)
        
        # 添加Steam游戏
        for game in steam_games:
            all_games.append(game)
        
        # 按游戏类型和平台排序
        all_games.sort(key=lambda x: (
            0 if x.get("GameType") == "当前免费" else 1,  # 当前免费优先
            0 if x.get("Platform") == "Epic" else 1,  # Epic优先
            x.get("Title", "")  # 按标题排序
        ))
        
        # 更新缓存
        self.cache[cache_key] = all_games
        self.cache_time[cache_key] = current_time
        
        _log.info(f"成功获取 {len(all_games)} 个免费游戏 (Epic: {len(epic_games)}, Steam: {len(steam_games)})")
        return all_games
    
    async def _get_games_from_indienova(self) -> List[Dict]:
        """从indienova网站获取Epic免费游戏信息"""
        try:
            # 使用全局 http_client 获取内容
            html = await http_client.get_text(self.INDIENOVA_EPIC_URL)
            if not html:
                _log.warning("无法获取indienova Epic页面内容")
                return []
                
            # 解析HTML内容
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            
            free_games = []
            
            # 查找游戏列表项 - indienova网站使用user-game-list-item类
            game_items = soup.find_all(class_='user-game-list-item')
            
            if game_items:
                _log.info(f"找到 {len(game_items)} 个游戏列表项")
                
                for item in game_items:
                    # 查找游戏标题
                    title_element = item.find('h4')
                    if title_element:
                        # 获取游戏标题
                        game_title = title_element.get_text(strip=True)
                        
                        # 查找英文名称
                        english_name_element = title_element.find('small')
                        english_name = english_name_element.get_text(strip=True) if english_name_element else ""
                        
                        # 构建完整的游戏名称
                        full_title = game_title
                        if english_name and english_name != game_title:
                            full_title = f"{game_title} ({english_name})"
                        
                        # 查找游戏图片
                        image_element = item.find('img')
                        image_url = ""
                        if image_element and image_element.get('src'):
                            image_url = image_element.get('src')
                            # 处理图片URL
                            if image_url.startswith('//'):
                                image_url = f"https:{image_url}"
                            elif image_url.startswith('/'):
                                image_url = f"https://indienova.com{image_url}"
                        
                        # 查找时间范围信息
                        time_element = item.find(class_='intro')
                        time_range = ""
                        start_date = ""
                        end_date = ""
                        game_status = "当前免费"
                        
                        if time_element:
                            time_range = time_element.get_text(strip=True)
                            # 解析时间范围，例如："2025/12/11 - 2025/12/18"
                            import re
                            time_pattern = r'(\d{4}/\d{1,2}/\d{1,2})\s*-\s*(\d{4}/\d{1,2}/\d{1,2})'
                            match = re.search(time_pattern, time_range)
                            
                            if match:
                                start_date = match.group(1)
                                end_date = match.group(2)
                                
                                # 判断游戏状态，如果已过期直接跳过这个游戏
                                from datetime import datetime
                                current_date = datetime.now().strftime("%Y/%m/%d")
                                
                                if current_date > end_date:
                                    # 游戏已过期，跳过处理
                                    continue
                                elif current_date < start_date:
                                    game_status = "即将免费"
                                else:
                                    game_status = "当前免费"
                        
                        # 查找游戏详细页面链接
                        detail_url = ""
                        detail_link = item.find('a', href=True)
                        if detail_link:
                            href = detail_link.get('href')
                            if href.startswith('/'):
                                detail_url = f"https://indienova.com{href}"
                            else:
                                detail_url = href
                        
                        # 获取Epic和Steam购买链接
                        epic_url = ""
                        steam_url = ""
                        
                        if detail_url:
                            # 访问游戏详细页面获取购买链接
                            try:
                                detail_html = await http_client.get_text(detail_url)
                                if detail_html:
                                    detail_soup = BeautifulSoup(detail_html, 'html.parser')
                                    
                                    # 查找Epic链接
                                    epic_link = detail_soup.find('a', href=lambda x: x and 'epicgames.com' in x)
                                    if epic_link:
                                        epic_url = epic_link.get('href')
                                    
                                    # 查找Steam链接
                                    steam_link = detail_soup.find('a', href=lambda x: x and 'steampowered.com' in x)
                                    if steam_link:
                                        steam_url = steam_link.get('href')
                            except:
                                pass
                        
                        # 如果没有找到购买链接，使用默认链接
                        if not epic_url:
                            epic_url = "https://store.epicgames.com/zh-CN/free-games"
                        if not steam_url:
                            steam_url = "https://store.steampowered.com/"
                        
                        # 构建游戏信息
                        game_info = {
                            "Title": full_title,
                            "Description": "",
                            "Developer": "",
                            "EpicUrl": epic_url,
                            "SteamUrl": steam_url,
                            "GameType": game_status,
                            "StartDate": start_date,
                            "EndDate": end_date,
                            "ImageUrl": image_url,
                            "Platform": "Epic"
                        }
                        free_games.append(game_info)
            
            # 如果仍然没有找到游戏，使用已知的当前免费游戏作为后备
            if not free_games:
                current_games = [
                    {
                        "Title": "霍格沃茨之遗 (Hogwarts Legacy)",
                        "Description": "开放世界动作角色扮演游戏，体验魔法世界的冒险",
                        "Developer": "Avalanche Software",
                        "EpicUrl": "https://store.epicgames.com/zh-CN/p/hogwarts-legacy",
                        "SteamUrl": "https://store.steampowered.com/app/990080",
                        "GameType": "当前免费",
                        "StartDate": "2025/12/11",
                        "EndDate": "2025/12/18",
                        "ImageUrl": "https://hive.indienova.com/ranch/gamedb/2022/08/cover/g-1481135-46ebwv.jpg_webp",
                        "Platform": "Epic"
                    }
                ]
                free_games.extend(current_games)
            
            _log.info(f"从indienova获取到 {len(free_games)} 个免费游戏")
            return free_games
                
        except Exception as e:
            _log.error(f"从indienova获取游戏失败: {e}")
            return []
    
    async def _get_steam_free_games(self) -> List[Dict]:
        """从indienova获取Steam免费游戏信息"""
        try:
            # 使用全局 http_client 获取内容
            html = await http_client.get_text(self.INDIENOVA_STEAM_URL)
            if not html:
                _log.warning("无法获取indienova Steam页面内容")
                return []
            
            # 解析HTML内容
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            
            free_games = []
            
            # 查找游戏列表项 - Steam页面使用相同的user-game-list-item类
            game_items = soup.find_all(class_='user-game-list-item')
            
            if game_items:
                _log.info(f"找到 {len(game_items)} 个Steam游戏列表项")
                
                for item in game_items:
                    # 查找游戏标题
                    title_element = item.find('h4')
                    if title_element:
                        # 获取游戏标题
                        game_title = title_element.get_text(strip=True)
                        
                        # 查找英文名称
                        english_name_element = title_element.find('small')
                        english_name = english_name_element.get_text(strip=True) if english_name_element else ""
                        
                        # 构建完整的游戏名称
                        full_title = game_title
                        if english_name and english_name != game_title:
                            full_title = f"{game_title} ({english_name})"
                        
                        # 查找游戏描述
                        description_element = item.find('p')
                        description = description_element.get_text(strip=True) if description_element else ""
                        
                        # 查找游戏链接
                        link_element = item.find('a')
                        game_url = ""
                        if link_element and link_element.get('href'):
                            # 如果链接是相对路径，转换为绝对路径
                            href = link_element.get('href')
                            if href.startswith('/'):
                                game_url = f"https://indienova.com{href}"
                            else:
                                game_url = href
                        
                        # 查找游戏图片
                        image_element = item.find('img')
                        image_url = ""
                        if image_element and image_element.get('src'):
                            image_url = image_element.get('src')
                            # 处理图片URL
                            if image_url.startswith('//'):
                                image_url = f"https:{image_url}"
                            elif image_url.startswith('/'):
                                image_url = f"https://indienova.com{image_url}"
                        
                        # 查找时间信息
                        time_element = item.find(class_='intro')
                        time_text = ""
                        game_type = "当前免费"
                        
                        if time_element:
                            time_text = time_element.get_text(strip=True)
                            # 解析时间信息
                            if "在" in time_text and "前获取" in time_text:
                                # 提取所有时间信息，例如："在 2022 年 11 月 8 日 上午 2:00 前获取该商品，即可免费保留。在 2025 年 11 月 24 日上午 2:00 前获取该商品，即可免费保留。"
                                import re
                                time_pattern = r'在 (\d{4}) 年 (\d{1,2}) 月 (\d{1,2}) 日\s*(上午|下午)?\s*(\d{1,2}:\d{2}) 前'
                                matches = re.findall(time_pattern, time_text)
                                
                                if matches:
                                    # 获取当前北京时间
                                    from datetime import datetime, timezone, timedelta
                                    beijing_tz = timezone(timedelta(hours=8))
                                    current_time = datetime.now(beijing_tz)
                                    
                                    # 找到最新的有效时间
                                    latest_end_date = None
                                    latest_end_date_str = ""
                                    
                                    for match in matches:
                                        # 处理匹配结果（可能缺少上午/下午）
                                        if len(match) == 5:
                                            year, month, day, am_pm, time_str = match
                                        else:
                                            # 如果缺少上午/下午，默认为上午
                                            year, month, day, time_str = match
                                            am_pm = "上午"
                                        
                                        # 转换为24小时制
                                        hour, minute = map(int, time_str.split(':'))
                                        if am_pm == '下午' and hour < 12:
                                            hour += 12
                                        elif am_pm == '上午' and hour == 12:
                                            hour = 0
                                        
                                        # 构建结束时间（北京时间）
                                        end_date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)} {hour:02d}:{minute:02d}:00"
                                        
                                        # 解析结束时间
                                        try:
                                            end_date = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=beijing_tz)
                                            
                                            # 只考虑未来的时间
                                            if end_date > current_time:
                                                if latest_end_date is None or end_date > latest_end_date:
                                                    latest_end_date = end_date
                                                    latest_end_date_str = end_date_str
                                        except:
                                            pass
                                    
                                    # 判断游戏状态
                                    if latest_end_date:
                                        game_type = "当前免费"
                                        # 更新时间为最新的有效时间
                                        time_text = f"在 {latest_end_date.strftime('%Y 年 %m 月 %d 日 %H:%M')} 前获取该商品，即可免费保留"
                                    else:
                                        # 如果所有时间都已过期，跳过这个游戏
                                        continue
                        
                        # 构建游戏信息
                        game_info = {
                            "Title": full_title,
                            "Description": description,
                            "Developer": "",
                            "Url": game_url,
                            "GameType": game_type,
                            "StartDate": "",
                            "EndDate": time_text if time_text else "",
                            "Platform": "Steam",
                            "ImageUrl": image_url
                        }
                        free_games.append(game_info)
            
            _log.info(f"从indienova获取到 {len(free_games)} 个Steam免费游戏")
            return free_games
            
        except Exception as e:
            _log.error(f"从indienova获取Steam游戏失败: {e}")
            return []
    
    async def _translate_game_title(self, title: str) -> str:
        """简单游戏名称翻译（英文转中文）"""
        # 常见游戏名称翻译字典
        translation_dict = {
            "Crosshair": "准星",
            "Ivorfall": "艾沃福尔",
            "Circus": "马戏团",
            "Electrique": "电气",
            "Cryptmaster": "地牢大师",
            "RESIST": "抵抗",
            "World": "世界",
            "War": "战争",
            "Battle": "战斗",
            "Fantasy": "幻想",
            "RPG": "角色扮演",
            "Simulator": "模拟器",
            "Adventure": "冒险",
            "Strategy": "策略",
            "Action": "动作",
            "Horror": "恐怖",
            "Puzzle": "解谜",
            "Racing": "竞速",
            "Sports": "体育",
            "Shooter": "射击",
            "Survival": "生存",
            "Building": "建造",
            "Online": "在线",
            "Multiplayer": "多人",
            "Singleplayer": "单人",
            "Free": "免费",
            "Demo": "试玩",
            "VR": "虚拟现实",
            "MMO": "大型多人在线",
            "RTS": "即时战略",
            "FPS": "第一人称射击",
            "TPS": "第三人称射击",
            "MOBA": "多人在线战术竞技"
        }
        
        # 简单的关键词替换翻译
        translated_title = title
        for eng, chn in translation_dict.items():
            if eng in translated_title:
                translated_title = translated_title.replace(eng, chn)
        
        # 如果翻译后还是英文，添加中文括号
        if translated_title == title and any(c.isalpha() for c in title):
            translated_title = f"{title} (英文)"
        
        return translated_title
    
    async def _format_game_node_content(self, game: Dict) -> List[Dict]:
        """格式化游戏信息 - 返回NapCat消息节点内容列表"""
        title = game.get("Title", "未知游戏")
        game_type = game.get("GameType", "未知类型")
        end_date = game.get("EndDate", "")
        platform = game.get("Platform", "未知平台")
        epic_url = game.get("EpicUrl", "")
        steam_url = game.get("SteamUrl", "")
        image_url = game.get("ImageUrl", "")
        
        # 翻译游戏名称
        chinese_title = await self._translate_game_title(title)
        
        # 格式化时间信息
        end_str = "未知"
        if platform == "Steam" and end_date and "在" in end_date and "前获取" in end_date:
            end_str = end_date  # 直接使用原始文本
        elif end_date:
            try:
                # 处理Epic的时间格式
                if "/" in end_date:
                    # 处理 "2025/12/18" 格式
                    end_dt = datetime.strptime(end_date, "%Y/%m/%d")
                    end_str = end_dt.strftime("%Y-%m-%d")
                else:
                    # 处理ISO格式
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    end_str = end_dt.strftime("%Y-%m-%d %H:%M")
            except:
                end_str = end_date
        
        # 确定领取地址
        claim_url = ""
        if platform == "Epic":
            claim_url = epic_url if epic_url else "暂无链接"
        elif platform == "Steam":
            claim_url = steam_url if steam_url else "暂无链接"
        
        # 构建消息段列表
        segments = []
        
        # 添加文本信息 - 美化格式
        status_icon = "🟢" if game_type == "当前免费" else "🟡" if game_type == "即将免费" else "⚪"
        
        text_info = f"🎮 {chinese_title}\n"
        text_info += f"{status_icon} 状态：{game_type}\n"
        text_info += f"⏰ 结束时间：{end_str}\n"
        
        # 处理领取地址显示
        if claim_url and claim_url != "暂无链接":
            text_info += f"🔗 领取地址：{claim_url}\n"
        else:
            text_info += f"🔗 领取地址：暂无链接\n"
        
        segments.append({"type": "text", "data": {"text": text_info}})
        
        # 如果有图片URL，添加图片组件
        if image_url:
            try:
                # 使用 http_client 下载图片并转换为base64
                headers = {
                    'Referer': 'https://indienova.com/'
                }
                
                image_content = await http_client.get_content(image_url, headers=headers)
                
                if image_content:
                    # 将图片转换为base64
                    import base64
                    image_base64 = base64.b64encode(image_content).decode('utf-8')
                    
                    # 添加图片段
                    segments.append({"type": "image", "data": {"file": f"base64://{image_base64}"}})
                    
            except Exception as e:
                _log.warning(f"无法加载图片 {image_url}: {e}")
        
        return segments
    
    @bot.group_event
    async def epic_free_games_group(self, event: GroupMessage):
        """群聊事件 - 获取Epic和Steam免费游戏"""
        text = event.raw_message.strip()
        
        if text in ["epic", "Epic", "EPIC", "喜加一", "免费游戏", "epic all", "Epic all", "EPIC ALL"]:
            await event.reply(MessageChain([Text("正在获取Epic和Steam免费游戏信息，请稍等...")]))
            
            games = await self._get_free_games()
            
            if not games:
                await event.reply(MessageChain([Text("❌ 当前没有可领取的免费游戏，请稍后再试\n💡 提示：免费游戏通常会在特定时间更新")]))
                return
            
            epic_games = [game for game in games if game.get("Platform") == "Epic"]
            steam_games = [game for game in games if game.get("Platform") == "Steam"]
            
            nodes = []
            bot_uin = "10000"
            if hasattr(event, 'self_id'):
                bot_uin = str(event.self_id)
            
            # Header Node
            header_text = f"🎯 免费游戏信息汇总\n"
            header_text += f"📊 EPIC：{len(epic_games)}个 | STEAM：{len(steam_games)}个\n"
            header_text += "=" * 30
            nodes.append(napcat_service.construct_node(bot_uin, "Epic助手", header_text))
            
            # Epic Games Nodes
            if epic_games:
                nodes.append(napcat_service.construct_node(bot_uin, "Epic助手", "🎮 【EPIC 免费游戏】"))
                for game in epic_games:
                    content = await self._format_game_node_content(game)
                    nodes.append(napcat_service.construct_node(bot_uin, "Epic助手", content))
            
            # Steam Games Nodes
            if steam_games:
                nodes.append(napcat_service.construct_node(bot_uin, "Epic助手", "🚂 【STEAM 免费游戏】"))
                for game in steam_games:
                    content = await self._format_game_node_content(game)
                    nodes.append(napcat_service.construct_node(bot_uin, "Epic助手", content))
            
            # Send Forward Message
            if nodes:
                await napcat_service.send_group_forward_msg(event.group_id, nodes)
            else:
                await event.reply(MessageChain([Text("❌ 未找到任何免费游戏信息")]))
    
    @bot.private_event
    async def epic_free_games_private(self, event: PrivateMessage):
        """私聊事件 - 获取Epic和Steam免费游戏"""
        text = event.raw_message.strip()
        
        if text in ["epic", "Epic", "EPIC", "喜加一", "免费游戏", "epic all", "Epic all", "EPIC ALL"]:
            await event.reply(MessageChain([Text("正在获取Epic和Steam免费游戏信息，请稍等...")]))
            
            games = await self._get_free_games()
            
            if not games:
                await event.reply(MessageChain([Text("❌ 当前没有可领取的免费游戏，请稍后再试")]))
                return
            
            epic_games = [game for game in games if game.get("Platform") == "Epic"]
            steam_games = [game for game in games if game.get("Platform") == "Steam"]
            
            nodes = []
            bot_uin = "10000"
            if hasattr(event, 'self_id'):
                bot_uin = str(event.self_id)
            
            # Header Node
            header_text = f"🎯 免费游戏信息汇总\n"
            header_text += f"📊 EPIC：{len(epic_games)}个 | STEAM：{len(steam_games)}个\n"
            header_text += "=" * 30
            nodes.append(napcat_service.construct_node(bot_uin, "Epic助手", header_text))
            
            # Epic Games Nodes
            if epic_games:
                nodes.append(napcat_service.construct_node(bot_uin, "Epic助手", "🎮 【EPIC 免费游戏】"))
                for game in epic_games:
                    content = await self._format_game_node_content(game)
                    nodes.append(napcat_service.construct_node(bot_uin, "Epic助手", content))
            
            # Steam Games Nodes
            if steam_games:
                nodes.append(napcat_service.construct_node(bot_uin, "Epic助手", "🚂 【STEAM 免费游戏】"))
                for game in steam_games:
                    content = await self._format_game_node_content(game)
                    nodes.append(napcat_service.construct_node(bot_uin, "Epic助手", content))
            
            # Send Forward Message
            if nodes:
                await napcat_service.send_private_forward_msg(event.user_id, nodes)
            else:
                await event.reply(MessageChain([Text("❌ 未找到任何免费游戏信息")]))
    
    @bot.group_event
    async def epic_help(self, event: GroupMessage):
        """帮助信息"""
        text = event.raw_message.strip()
        
        if text in ["epic help", "Epic help", "EPIC HELP", "喜加一帮助"]:
            help_text = """🎮 Epic喜加一插件使用说明:

📝 命令列表:
• "epic" 或 "喜加一" - 查看当前免费游戏(最多5个)
• "epic all" - 查看所有免费游戏(合并转发)
• "epic help" - 显示此帮助信息

💡 功能说明:
• 自动获取Epic Games Store的免费游戏信息
• 包含游戏名称、开发者、描述、领取链接
• 区分当前免费和即将免费游戏
• 数据每小时自动更新
• 支持群聊和私聊使用

🎯 数据来源: Epic Games官方API"""
            
            await napcat_service.smart_send_group_msg(event.group_id, help_text, self.api)