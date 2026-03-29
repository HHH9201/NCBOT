# -*- coding: utf-8 -*-
"""
AI 对话插件
当有人 @ 机器人时，自动调用 AI 进行对话回复
支持上下文记忆功能
"""
import logging
from typing import Optional, Dict, List
from datetime import datetime, timedelta

from ncatbot.plugin import BasePlugin
from ncatbot.core import registrar
from ncatbot.event.qq import GroupMessageEvent, PrivateMessageEvent
from ncatbot.types import MessageArray, PlainText, At, Reply

from common import ai_service, GLOBAL_CONFIG
from common.db_permissions import db_permission_manager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class AIChat(BasePlugin):
    """AI 对话插件 - 当被 @ 时自动回复"""
    name = "AIChat"
    version = "1.1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 系统提示词
        self.system_prompt = (
            "你是一个友好、 helpful 的 AI 助手。"
            "你的回答应该简洁明了，适合在群聊中阅读。"
            "如果用户的问题不清楚，可以礼貌地请他们补充细节。"
        )
        
        # 对话历史记录 {chat_id: [{"role": "user"/"assistant", "content": "...", "timestamp": datetime}, ...]}
        self.conversation_history: Dict[str, List[Dict]] = {}
        
        # 配置
        self.max_history = 10  # 最多保留10轮对话
        self.history_timeout = 30  # 30分钟无对话则清空历史

    def _get_chat_id(self, event) -> str:
        """生成对话ID（群聊用group_id，私聊用user_id）"""
        if hasattr(event, 'group_id'):
            return f"group_{event.group_id}"
        else:
            return f"private_{event.user_id}"

    def _clean_old_history(self, chat_id: str):
        """清理过期的对话历史"""
        if chat_id not in self.conversation_history:
            return
        
        history = self.conversation_history[chat_id]
        now = datetime.now()
        
        # 过滤掉超时的消息
        valid_history = []
        for msg in history:
            if now - msg.get('timestamp', now) < timedelta(minutes=self.history_timeout):
                valid_history.append(msg)
        
        # 只保留最近 max_history 轮
        if len(valid_history) > self.max_history * 2:
            valid_history = valid_history[-self.max_history * 2:]
        
        self.conversation_history[chat_id] = valid_history

    def _add_to_history(self, chat_id: str, role: str, content: str):
        """添加消息到历史记录"""
        if chat_id not in self.conversation_history:
            self.conversation_history[chat_id] = []
        
        self.conversation_history[chat_id].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now()
        })
        
        # 清理旧历史
        self._clean_old_history(chat_id)

    def _build_messages_with_history(self, chat_id: str, current_message: str) -> List[Dict]:
        """构建包含历史的消息列表"""
        messages = [{"role": "system", "content": self.system_prompt}]
        
        # 添加历史对话
        if chat_id in self.conversation_history:
            for msg in self.conversation_history[chat_id]:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        # 添加当前消息
        messages.append({"role": "user", "content": current_message})
        
        return messages

    def _extract_message_without_at(self, event: GroupMessageEvent) -> str:
        """
        提取消息中除了 @ 机器人之外的内容
        """
        message_text = ""
        
        # 遍历消息段，提取纯文本内容
        for segment in event.message:
            if isinstance(segment, PlainText):
                message_text += segment.text
            # 忽略 @ 段和其他非文本段
        
        # 清理前后空白
        return message_text.strip()

    def _is_at_bot(self, event: GroupMessageEvent) -> bool:
        """
        检查消息是否 @ 了机器人
        """
        # 从配置文件中获取机器人QQ号 (支持 bot_uin 或 bot.qq)
        bot_id = GLOBAL_CONFIG.get("bot_uin", "") or GLOBAL_CONFIG.get("bot.qq", "")

        for segment in event.message:
            if isinstance(segment, At):
                # 检查 @ 的目标是否是机器人自己
                if str(segment.user_id) == str(bot_id):
                    return True

        return False

    async def _get_ai_response(self, chat_id: str, user_message: str) -> Optional[str]:
        """
        调用 AI 服务获取回复 (使用 ModelScope API，支持上下文)
        """
        try:
            logger.info(f"[AI] 开始调用 AI 服务，用户消息: {user_message[:50]}...")
            
            # 构建包含历史的消息
            messages = self._build_messages_with_history(chat_id, user_message)
            
            # 调用 AI
            response = await ai_service.modelscope_chat(
                messages=messages,
                temperature=0.7,
                max_tokens=1024
            )
            
            logger.info(f"[AI] AI 返回: {response}")
            
            # 保存到历史
            if response:
                self._add_to_history(chat_id, "user", user_message)
                self._add_to_history(chat_id, "assistant", response)
            
            return response
        except Exception as e:
            logger.error(f"[AI] AI 调用失败: {e}")
            import traceback
            logger.error(f"[AI] 详细错误: {traceback.format_exc()}")
            return None

    @registrar.on_group_message()
    async def handle_group_at(self, event: GroupMessageEvent):
        """
        处理群组中被 @ 的消息
        """
        # 检查是否 @ 了机器人
        if not self._is_at_bot(event):
            return
        
        # 检查插件是否启用（会自动添加新群到数据库）
        if not await db_permission_manager.is_plugin_enabled(event.group_id, "ai_chat"):
            return
        
        # 提取用户消息（去掉 @ 部分）
        user_message = self._extract_message_without_at(event)
        
        # 如果 @ 后没有内容，给出提示
        if not user_message:
            await event.reply("你好！有什么我可以帮你的吗？")
            return
        
        # 获取对话ID
        chat_id = self._get_chat_id(event)
        
        logger.info(f"收到群聊 @ 消息: {user_message[:50]}...")
        
        # 调用 AI 获取回复（带上下文）
        ai_response = await self._get_ai_response(chat_id, user_message)
        
        if ai_response:
            # 回复消息
            await event.reply(ai_response)
        else:
            await event.reply("抱歉，我暂时无法回答，请稍后再试~")

    @registrar.on_private_message()
    async def handle_private_message(self, event: PrivateMessageEvent):
        """
        处理私聊消息（私聊不需要 @，直接回复）
        """
        user_message = event.raw_message.strip()
        
        if not user_message:
            return
        
        # 跳过命令消息（让其他插件处理）
        command_prefixes = ["查看权限", "设置插件", "设置全部", "黑名单", "白名单", "权限帮助", "所有群权限"]
        for prefix in command_prefixes:
            if user_message.startswith(prefix):
                logger.info(f"检测到命令消息，跳过AI处理: {user_message[:30]}...")
                return
        
        # 获取对话ID
        chat_id = self._get_chat_id(event)
        
        logger.info(f"收到私聊消息: {user_message[:50]}...")

        # 调用 AI 获取回复（带上下文）
        ai_response = await self._get_ai_response(chat_id, user_message)

        if ai_response:
            await event.reply(ai_response)
        else:
            await event.reply("抱歉，我暂时无法回答，请稍后再试~")

    async def on_load(self):
        logger.info(f"🤖 {self.name} v{self.version} 已加载（支持上下文记忆）")
