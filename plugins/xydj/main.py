# /home/hjh/BOT/NCBOT/plugins/xydj/main.py
# NcatBot 5.x 游戏搜索插件（简化版）
import re
import asyncio
import logging
from typing import Optional, List, Dict
from pathlib import Path

from ncatbot.plugin import BasePlugin
from ncatbot.core import registrar
from ncatbot.event.qq import GroupMessageEvent

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SearchSession:
    """搜索会话管理"""
    def __init__(self, user_id, games, task=None):
        self.user_id = user_id
        self.games = games
        self.task = task
        self.processing = False


class Xydj(BasePlugin):
    """游戏搜索插件 - 咸鱼单机 + ByrutGame 游戏搜索"""
    name = "xydj"
    version = "1.0.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sessions: Dict[int, SearchSession] = {}  # group_id -> SearchSession

    async def countdown(self, event: GroupMessageEvent):
        """超时倒计时"""
        await asyncio.sleep(20)
        session = self.sessions.get(event.group_id)
        if session and not session.processing:
            self._cleanup(event.group_id)
            await event.reply("等待超时，操作已取消。请重新搜索")

    def _cleanup(self, group_id: int):
        """清理会话"""
        if group_id in self.sessions:
            session = self.sessions[group_id]
            if session.task:
                session.task.cancel()
            del self.sessions[group_id]

    @registrar.on_group_command("搜索")
    async def search_game(self, event: GroupMessageEvent):
        """搜索游戏命令"""
        # 提取游戏名称
        game_name = event.raw_message.strip()[2:].strip()
        if not game_name:
            await event.reply("使用方法：搜索+游戏名称，例如：搜索 文明6")
            return

        await event.reply(f"🔍 正在搜索游戏: {game_name}...")

        # 简化版：直接返回提示
        # 实际功能需要接入 common 模块的 HTTP 客户端和数据库
        await event.reply(
            f"🎮 搜索功能正在迁移中...\n"
            f"搜索关键词: {game_name}\n"
            f"请稍后使用完整版功能"
        )

    @registrar.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent):
        """处理群消息（数字选择）"""
        session = self.sessions.get(event.group_id)

        # 检查是否是等待回复的状态
        if not session or event.user_id != session.user_id:
            return

        if session.processing:
            return

        choice = re.sub(r'\[CQ:[^\]]+\]', '', event.raw_message).strip()

        # 取消操作
        if choice == "0":
            await event.reply("操作已取消。")
            self._cleanup(event.group_id)
            return

        # 验证选择
        if not choice.isdigit() or not 1 <= int(choice) <= len(session.games):
            await event.reply("回复错误，操作已取消。请重新搜索游戏。")
            self._cleanup(event.group_id)
            return

        choice = int(choice)
        await event.reply(f"已选择第 {choice} 个游戏")

        session.processing = True
        if session.task:
            session.task.cancel()
            session.task = None

        try:
            # 简化版：仅显示提示
            await event.reply("游戏资源获取功能正在迁移中...")
        except Exception as e:
            await event.reply(f"处理失败: {str(e)}")
        finally:
            self._cleanup(event.group_id)

    async def on_load(self):
        logger.info(f"🚀 {self.name} v{self.version} 已加载")
        logger.info("注意：此为简化版，完整功能需要接入 common 模块")
