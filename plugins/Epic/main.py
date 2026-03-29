# /home/hjh/BOT/NCBOT/plugins/Epic/main.py
# NcatBot 5.x Epic 喜加一插件
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional

from ncatbot.plugin import BasePlugin
from ncatbot.core import registrar
from ncatbot.event.qq import GroupMessageEvent

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from common.db_permissions import db_permission_manager


class Epic(BasePlugin):
    """Epic 喜加一插件 - 获取 Epic Games 免费游戏信息"""
    name = "Epic"
    version = "1.0.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # API 配置
        self.api_url = "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    async def fetch_free_games(self) -> Optional[List[Dict]]:
        """获取 Epic 免费游戏列表"""
        try:
            params = {
                "locale": "zh-CN",
                "country": "CN",
                "allowCountries": "CN"
            }
            
            # 使用 api.misc 进行 HTTP 请求
            response = await self.api.misc.get(self.api_url, params=params, headers=self.headers)
            
            if response.status_code != 200:
                logger.error(f"Epic API 请求失败: {response.status_code}")
                return None
            
            data = response.json()
            games = data.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", [])
            
            free_games = []
            for game in games:
                promotions = game.get("promotions", {})
                if not promotions:
                    continue
                
                # 检查是否有免费促销
                promotional_offers = promotions.get("promotionalOffers", [])
                upcoming_offers = promotions.get("upcomingPromotionalOffers", [])
                
                if promotional_offers or upcoming_offers:
                    free_games.append(game)
            
            return free_games
            
        except Exception as e:
            logger.error(f"获取 Epic 免费游戏失败: {e}")
            return None

    def format_game_info(self, game: Dict) -> str:
        """格式化游戏信息"""
        title = game.get("title", "未知游戏")
        description = game.get("description", "暂无描述")
        
        # 获取促销信息
        promotions = game.get("promotions", {})
        promotional_offers = promotions.get("promotionalOffers", [])
        upcoming_offers = promotions.get("upcomingPromotionalOffers", [])
        
        status = ""
        if promotional_offers:
            offer = promotional_offers[0].get("promotionalOffers", [{}])[0]
            start = offer.get("startDate", "")
            end = offer.get("endDate", "")
            status = f"\n⏰ 当前免费 | 截止: {end[:10] if end else '未知'}"
        elif upcoming_offers:
            offer = upcoming_offers[0].get("promotionalOffers", [{}])[0]
            start = offer.get("startDate", "")
            status = f"\n⏰ 即将免费 | 开始: {start[:10] if start else '未知'}"
        
        # 获取商品页面链接
        product_slug = game.get("productSlug", "")
        url = f"https://store.epicgames.com/zh-CN/p/{product_slug}" if product_slug else ""
        
        return f"🎮 {title}{status}\n📝 {description[:50]}...\n🔗 {url}\n"

    @registrar.on_group_command("喜加一", "epic")
    async def epic_free_games(self, event: GroupMessageEvent):
        """获取 Epic 喜加一游戏"""
        # 检查插件是否启用（会自动添加新群到数据库）
        if not await db_permission_manager.is_plugin_enabled(event.group_id, "epic"):
            return
        
        await event.reply("🔍 正在获取 Epic 免费游戏信息...")
        
        games = await self.fetch_free_games()
        
        if not games:
            await event.reply("❌ 获取 Epic 免费游戏信息失败，请稍后重试")
            return
        
        if len(games) == 0:
            await event.reply("📭 当前没有免费游戏")
            return
        
        # 格式化输出
        lines = ["🎁 Epic 喜加一游戏列表:\n"]
        for game in games:
            lines.append(self.format_game_info(game))
        
        result = "\n".join(lines)
        
        # 如果内容过长，使用合并转发
        if len(result) > 500:
            from ncatbot.types.qq import ForwardConstructor
            fc = ForwardConstructor()
            fc.attach_text(result)
            await self.api.qq.post_group_forward_msg(event.group_id, fc.build())
        else:
            await event.reply(result)

    async def on_load(self):
        logger.info(f"🚀 {self.name} v{self.version} 已加载")
