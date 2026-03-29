# -*- coding: utf-8 -*-
"""
Steam 游戏价格监控插件
支持查询史低价格、当前价格、折扣信息
"""
import re
import json
import logging
import aiohttp
from datetime import datetime
from typing import Dict, Optional, List
from ncatbot.plugin import BasePlugin
from ncatbot.core import registrar
from ncatbot.event.qq import GroupMessageEvent, PrivateMessageEvent
from common.db_permissions import db_permission_manager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Steam(BasePlugin):
    """Steam 游戏价格监控插件"""
    name = "Steam"
    version = "1.0.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.steam_api_url = "https://store.steampowered.com/api"
        self.steamdb_api = "https://steamdb.info/api"

    async def search_game(self, game_name: str) -> Optional[Dict]:
        """搜索 Steam 游戏"""
        try:
            # 使用 Steam 搜索 API
            search_url = f"{self.steam_api_url}/storesearch/"
            params = {
                "term": game_name,
                "l": "schinese",
                "cc": "CN"
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return None

                    data = await resp.json()

                    if not data.get("items"):
                        return None

                    # 返回第一个匹配的结果
                    return data["items"][0]

        except Exception as e:
            logger.error(f"搜索游戏失败: {e}")
            return None

    async def get_game_details(self, app_id: str) -> Optional[Dict]:
        """获取游戏详情和价格信息"""
        try:
            # 使用 Steam Store API 获取价格信息
            details_url = f"{self.steam_api_url}/appdetails"
            params = {
                "appids": app_id,
                "cc": "CN",
                "l": "schinese",
                "filters": "price_overview,basic"
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(details_url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return None

                    data = await resp.json()

                    if not data or not data.get(app_id, {}).get("success"):
                        return None

                    return data[app_id]["data"]

        except Exception as e:
            logger.error(f"获取游戏详情失败: {e}")
            return None

    async def get_lowest_price(self, app_id: str) -> Optional[Dict]:
        """获取史低价格信息（使用 SteamDB 或 ITAD API）"""
        try:
            # 首先获取当前价格
            details = await self.get_game_details(app_id)
            if not details:
                return None

            price_info = details.get("price_overview", {})
            current_price = price_info.get("final", 0) / 100
            original_price = price_info.get("initial", 0) / 100
            discount_percent = price_info.get("discount_percent", 0)

            # 尝试从 SteamDB 获取史低数据
            lowest_price = None
            lowest_date = None

            try:
                # SteamDB 价格历史 API
                steamdb_url = f"https://steamdb.info/api/PriceHistory/?appid={app_id}&cc=cn"

                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        steamdb_url,
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                            "Accept": "application/json"
                        },
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data and "data" in data and "final" in data["data"]:
                                # 解析价格历史数据
                                price_history = data["data"]["final"]
                                if price_history and len(price_history) > 0:
                                    # 找到最低价格
                                    lowest_entry = min(price_history, key=lambda x: x[1] if len(x) > 1 else float('inf'))
                                    if len(lowest_entry) >= 2:
                                        lowest_price = lowest_entry[1] / 100
                                        # 转换时间戳
                                        timestamp = lowest_entry[0]
                                        lowest_date = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
            except Exception as e:
                logger.warning(f"从 SteamDB 获取史低失败: {e}")

            # 如果 SteamDB 失败，尝试使用 IsThereAnyDeal API
            if lowest_price is None:
                try:
                    itad_url = "https://api.isthereanydeal.com/v01/game/overview/"
                    params = {
                        "key": "",  # ITAD API 需要密钥，这里留空使用免费版
                        "region": "cn",
                        "country": "CN",
                        "appid": app_id,
                        "shop": "steam"
                    }

                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            itad_url,
                            params=params,
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if data and "data" in data:
                                    game_data = data["data"]
                                    if "lowest" in game_data:
                                        lowest_price = game_data["lowest"].get("price", 0)
                                        lowest_date = game_data["lowest"].get("recorded", "未知")
                except Exception as e:
                    logger.warning(f"从 ITAD 获取史低失败: {e}")

            return {
                "current_price": current_price,
                "original_price": original_price,
                "discount_percent": discount_percent,
                "currency": price_info.get("currency", "CNY"),
                "lowest_price": lowest_price,
                "lowest_date": lowest_date
            }

        except Exception as e:
            logger.error(f"获取史低价格失败: {e}")
            return None

    def format_price_info(self, game_name: str, details: Dict, price_info: Dict) -> str:
        """格式化价格信息"""
        if not price_info:
            return f"❌ 无法获取《{game_name}》的价格信息"

        lines = [f"🎮 {game_name}", ""]

        # 当前价格
        current = price_info.get("current_price", 0)
        original = price_info.get("original_price", 0)
        discount = price_info.get("discount_percent", 0)

        if discount > 0:
            lines.append(f"💰 当前价格: ¥{current:.2f} (-{discount}%)")
            lines.append(f"📌 原价: ¥{original:.2f}")
        else:
            lines.append(f"💰 当前价格: ¥{current:.2f}")

        # 史低信息（如果有）
        lowest = price_info.get("lowest_price")
        if lowest:
            lowest_date = price_info.get("lowest_date", "未知")
            lines.append(f"📉 历史最低: ¥{lowest:.2f} ({lowest_date})")

            # 判断当前是否史低
            if current <= lowest:
                lines.append("🔥 当前是史低价格！")
            else:
                diff = current - lowest
                lines.append(f"💡 比史低贵 ¥{diff:.2f}")
        else:
            lines.append("📉 史低数据: 暂不可用")

        # Steam 链接
        app_id = details.get("steam_appid", "")
        if app_id:
            lines.append(f"")
            lines.append(f"🔗 https://store.steampowered.com/app/{app_id}/")

        return "\n".join(lines)

    @registrar.on_group_command("史低", "steam")
    async def query_lowest_price(self, event: GroupMessageEvent):
        """查询游戏史低价格"""
        # 检查插件是否启用
        if not await db_permission_manager.is_plugin_enabled(event.group_id, "steam"):
            return

        # 解析命令: 史低 <游戏名>
        message = event.raw_message.strip()
        match = re.match(r"(?:史低|steam)\s*(.+)", message, re.IGNORECASE)

        if not match:
            await event.reply("用法: 史低 <游戏名>\n示例: 史低 只狼")
            return

        game_name = match.group(1).strip()

        if not game_name:
            await event.reply("请输入游戏名称\n示例: 史低 只狼")
            return

        # 发送等待消息
        await event.reply(f"🔍 正在查询《{game_name}》的价格信息...")

        try:
            # 搜索游戏
            game_info = await self.search_game(game_name)

            if not game_info:
                await event.reply(f"❌ 未找到游戏《{game_name}》，请检查游戏名称")
                return

            app_id = str(game_info.get("id", ""))
            game_name_found = game_info.get("name", game_name)

            # 获取详情和价格
            details = await self.get_game_details(app_id)
            price_info = await self.get_lowest_price(app_id)

            # 格式化并发送结果
            result = self.format_price_info(game_name_found, details or {}, price_info or {})
            await event.reply(result)

        except Exception as e:
            logger.error(f"查询价格失败: {e}")
            await event.reply(f"❌ 查询失败: {e}")

    @registrar.on_private_command("史低", "steam")
    async def private_query_lowest_price(self, event: PrivateMessageEvent):
        """私聊查询游戏史低价格"""
        # 解析命令
        message = event.raw_message.strip()
        match = re.match(r"(?:史低|steam)\s*(.+)", message, re.IGNORECASE)

        if not match:
            await event.reply("用法: 史低 <游戏名>\n示例: 史低 只狼")
            return

        game_name = match.group(1).strip()

        if not game_name:
            await event.reply("请输入游戏名称\n示例: 史低 只狼")
            return

        # 发送等待消息
        await event.reply(f"🔍 正在查询《{game_name}》的价格信息...")

        try:
            # 搜索游戏
            game_info = await self.search_game(game_name)

            if not game_info:
                await event.reply(f"❌ 未找到游戏《{game_name}》，请检查游戏名称")
                return

            app_id = str(game_info.get("id", ""))
            game_name_found = game_info.get("name", game_name)

            # 获取详情和价格
            details = await self.get_game_details(app_id)
            price_info = await self.get_lowest_price(app_id)

            # 格式化并发送结果
            result = self.format_price_info(game_name_found, details or {}, price_info or {})
            await event.reply(result)

        except Exception as e:
            logger.error(f"查询价格失败: {e}")
            await event.reply(f"❌ 查询失败: {e}")

    async def on_load(self):
        logger.info(f"🎮 {self.name} v{self.version} 已加载（Steam 价格监控）")
