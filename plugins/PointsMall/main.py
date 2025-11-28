# /home/hjh/BOT/NCBOT/plugins/PointsMall/main.py
# PointsMall插件入口文件 - 使用装饰器模式的签到积分插件

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ncatbot.plugin import BasePlugin, CompatibleEnrollment
from ncatbot.core.message import GroupMessage
from ncatbot.core.message import MessageChain
from ncatbot.core.event.message_segment.message_segment import Text, Reply

from sign_in.message_handler import SignInMessageHandler

bot = CompatibleEnrollment

class PointsMall(BasePlugin):
    """PointsMall插件 - 群友签到获得积分"""
    name = "PointsMall"
    version = "1.0.0"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sign_handler = SignInMessageHandler()
    
    @bot.group_event
    async def on_group_message(self, msg: GroupMessage):
        """处理群消息事件"""
        user_id = str(msg.sender.user_id)
        group_id = str(msg.group_id)
        user_name = msg.sender.nickname or '群友'
        message_text = msg.raw_message.strip()
        
        # 处理签到相关消息
        result = self.sign_handler.handle_sign_in(user_id, group_id, user_name, message_text)
        
        if result:
            # 使用消息链发送回复
            chain = MessageChain([
                Reply(msg.message_id),
                Text(result)
            ])
            
            await self.api.post_group_msg(
                group_id=msg.group_id,
                rtf=chain
            )
            return
        
        # 处理帮助命令
        help_commands = ['积分帮助', '签到帮助', '帮助']
        if message_text in help_commands or message_text == '帮助':
            help_msg = self.sign_handler.get_help_message()
            chain = MessageChain([
                Reply(msg.message_id),
                Text(help_msg)
            ])
            
            await self.api.post_group_msg(
                group_id=msg.group_id,
                rtf=chain
            )
            return
    
    def get_plugin_info(self):
        """获取插件信息"""
        return {
            'name': 'PointsMall',
            'version': '1.0.0',
            'description': '群友签到获得积分插件',
            'author': 'NCBOT',
            'commands': ['签到', '打卡', '积分查询', '积分排行榜', '积分帮助']
        }

# 兼容旧版本导入
PointsMallPlugin = PointsMall