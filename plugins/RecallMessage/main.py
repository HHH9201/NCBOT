# /home/h/BOT/NC/plugins/RecallMessage/main.py
"""
群消息撤回监控插件
当群内有人撤回消息时，发送转发消息包含撤回的内容
撤回自己发送的消息时不转发
"""

import asyncio
from typing import Dict
from ncatbot.plugin import BasePlugin, CompatibleEnrollment
from ncatbot.core import GroupMessage
from ncatbot.utils import get_log

# 创建兼容回调函数注册器实例
bot = CompatibleEnrollment

# 创建日志记录器
_log = get_log()

class RecallMessage(BasePlugin):
    """群消息撤回监控插件"""
    
    # 插件元数据
    name = "RecallMessage"  # 插件名称，必须与目录名一致
    version = "1.0.0"  # 插件版本
    
    def __init__(self, event_bus=None, **kwargs):
        """初始化插件"""
        super().__init__(event_bus=event_bus, **kwargs)
        self.message_cache: Dict[str, dict] = {}  # 消息缓存，key为message_id，value为消息内容
        self.bot_qq = None  # 机器人QQ号
    
    async def on_load(self):
        """插件加载时调用"""
        _log.info("RecallMessage 插件已加载")
    
    async def on_unload(self):
        """插件卸载时调用"""
        _log.info("RecallMessage 插件已卸载")
    
    @bot.group_event
    async def on_group_message(self, msg: GroupMessage):
        """
        处理群消息事件
        缓存所有群消息以便撤回时使用
        
        Args:
            msg: 群消息对象
        """
        try:
            # 获取机器人QQ号（第一次运行时设置）
            if self.bot_qq is None:
                self.bot_qq = msg.self_id
            
            # 缓存消息内容
            message_id = str(msg.message_id)
            message_content = self._extract_message_content(msg)
            
            if message_content:
                self.message_cache[message_id] = {
                    'content': message_content,
                    'sender_id': msg.user_id,
                    'group_id': msg.group_id,
                    'time': msg.time
                }
                
                # 限制缓存大小，避免内存占用过大
                if len(self.message_cache) > 1000:
                    # 移除最早的消息
                    oldest_key = next(iter(self.message_cache))
                    del self.message_cache[oldest_key]
                    
        except Exception as e:
            _log.error(f"处理群消息时发生错误: {e}")
    
    @bot.notice_event
    async def on_notice(self, notice: dict):
        """
        处理通知事件，包括消息撤回
        
        Args:
            notice: 通知事件字典
        """
        try:
            notice_type = notice.get("notice_type")
            
            # 只处理群消息撤回事件
            if notice_type != "group_recall":
                return
            
            # 获取撤回消息的信息
            message_id = str(notice.get("message_id"))
            operator_id = notice.get("operator_id")  # 操作者QQ号（撤回消息的人）
            user_id = notice.get("user_id")  # 消息发送者QQ号
            group_id = notice.get("group_id")
            
            # 检查是否是机器人自己撤回的消息
            if operator_id == self.bot_qq:
                return
            
            # 从缓存中获取被撤回的消息内容
            cached_message = self.message_cache.get(message_id)
            
            if cached_message:
                # 检查是否是撤回自己发送的消息
                if operator_id == user_id:
                    # 撤回自己发送的消息，不转发
                    return
                
                # 构建转发消息内容
                recall_content = cached_message['content']
                sender_name = await self._get_member_name(group_id, user_id)
                operator_name = await self._get_member_name(group_id, operator_id)
                
                # 创建转发消息
                forward_messages = [
                    f"⚠️ 消息撤回提醒",
                    f"👤 发送者: {sender_name} ({user_id})",
                    f"🔧 操作者: {operator_name} ({operator_id})",
                    f"📝 撤回内容:",
                    f"{recall_content}",
                    f"💡 提示: 此消息已被撤回"
                ]
                
                # 发送转发消息
                await self._send_forward_message(group_id, forward_messages)
                
                # 从缓存中移除已处理的消息
                del self.message_cache[message_id]
                
                _log.info(f"已处理消息撤回事件: 消息ID {message_id}, 操作者 {operator_id}")
                
        except Exception as e:
            _log.error(f"处理撤回事件时发生错误: {e}")
    
    def _extract_message_content(self, msg) -> str:
        """
        从消息对象中提取文本内容
        
        Args:
            msg: 消息对象
            
        Returns:
            str: 提取的文本内容
        """
        try:
            # 优先使用 raw_message，如果为空则尝试从 message 中提取
            if hasattr(msg, 'raw_message') and msg.raw_message:
                return msg.raw_message
            
            # 如果 raw_message 为空，尝试从 message 数组中提取文本
            if hasattr(msg, 'message') and isinstance(msg.message, list):
                text_parts = []
                for item in msg.message:
                    if item.get('type') == 'text' and item.get('data', {}).get('text'):
                        text_parts.append(item['data']['text'])
                return ' '.join(text_parts)
            
            # 处理 message_format 为 array 的情况
            if hasattr(msg, 'message_format') and msg.message_format == 'array':
                if hasattr(msg, 'message') and isinstance(msg.message, list):
                    text_parts = []
                    for item in msg.message:
                        if isinstance(item, dict) and item.get('type') == 'text' and item.get('data', {}).get('text'):
                            text_parts.append(item['data']['text'])
                    return ' '.join(text_parts)
            
            return ""
            
        except Exception as e:
            _log.error(f"提取消息内容时发生错误: {e}")
            return ""
    
    async def _get_member_name(self, group_id, user_id):
        """
        获取群成员昵称
        
        Args:
            group_id: 群号
            user_id: 用户QQ号
            
        Returns:
            str: 成员昵称或QQ号
        """
        try:
            # 尝试获取群成员信息
            member_info = await self.api.get_group_member_info(group_id, user_id)
            if member_info and 'card' in member_info and member_info['card']:
                return member_info['card']  # 群名片
            elif member_info and 'nickname' in member_info:
                return member_info['nickname']  # 昵称
            else:
                return str(user_id)  # 回退到QQ号
                
        except Exception:
            # 如果获取失败，直接返回QQ号
            return str(user_id)
    
    async def _send_forward_message(self, group_id, messages):
        """
#         发送转发消息
        
#         Args:
#             group_id: 群号
#             messages: 消息内容列表
#         """
#         try:
#             # 构建转发消息节点
#             forward_nodes = []
            
#             for message in messages:
#                 node = {
#                     "type": "node",
#                     "data": {
#                         "content": [{"type": "text", "data": {"text": message}}]
#                     }
#                 }
#                 forward_nodes.append(node)
            
#             # 发送转发消息
#             await self.api.post_group_forward_msg(group_id, forward_nodes)
            
#         except Exception as e:
#             _log.error(f"发送转发消息时发生错误: {e}")
#             # 如果转发消息失败，尝试发送普通消息
#             try:
#                 combined_message = "\n".join(messages)
#                 await self.api.post_group_msg(group_id, combined_message)
#             except Exception as inner_e:
#                 _log.error(f"发送普通消息也失败: {inner_e}")