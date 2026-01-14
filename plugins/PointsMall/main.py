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
from mall.message_handler import MallMessageHandler
from utils.help_generator import help_generator
from utils.error_handler import error_handler
from common.napcat import napcat_service

# admin_tools模块已禁用，如需启用请取消注释下方导入
# from utils.admin_tools import admin_tools

bot = CompatibleEnrollment

class PointsMall(BasePlugin):
    """PointsMall插件 - 群友签到获得积分"""
    name = "PointsMall"
    version = "1.0.0"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sign_handler = SignInMessageHandler()
        self.mall_handler = MallMessageHandler()
    
    @bot.group_event
    async def on_group_message(self, msg: GroupMessage):
        """处理群消息事件"""
        try:
            user_id = str(msg.sender.user_id)
            group_id = str(msg.group_id)
            user_name = msg.sender.nickname or '群友'
            message_text = msg.raw_message.strip()
            
            # 处理签到相关消息
            result = self.sign_handler.handle_sign_in(user_id, group_id, user_name, message_text)
            
            if result:
                await self._send_reply(msg, result)
                return
            
            # 处理商城相关消息
            result = self.mall_handler.handle_mall_command(user_id, group_id, user_name, message_text)
            
            if result:
                await self._send_reply(msg, result)
                return
            
            # 处理帮助命令
            if "帮助" in message_text or "help" in message_text.lower():
                if "快速" in message_text or "guide" in message_text.lower():
                    result = help_generator.generate_quick_guide()
                elif "功能" in message_text or "feature" in message_text.lower():
                    result = help_generator.generate_feature_intro()
                else:
                    # 提取帮助类别
                    category = None
                    if "签到" in message_text:
                        category = 'sign_in'
                    elif "商城" in message_text or "抽奖" in message_text or "转账" in message_text:
                        category = 'mall'
                    elif "管理" in message_text or "admin" in message_text.lower():
                        category = 'admin'
                    
                    result = help_generator.generate_help_message(category)
                
                await self._send_reply(msg, result)
                return
            
            # 处理管理员命令
            if self._is_admin(user_id):
                if "系统统计" in message_text:
                    stats = admin_tools.get_system_statistics()
                    if 'error' in stats:
                        result = f"❌ 获取系统统计失败: {stats['error']}"
                    else:
                        from utils.message_formatter import message_formatter
                        result = message_formatter.format_statistics_message(stats)
                    
                    await self._send_reply(msg, result)
                    return
                
                elif "数据导出" in message_text:
                    # 解析导出参数
                    format_type = 'csv'
                    if 'csv' in message_text:
                        format_type = 'csv'
                    elif 'excel' in message_text:
                        format_type = 'excel'
                    elif 'json' in message_text:
                        format_type = 'json'
                    
                    result = admin_tools.export_user_data(format_type)
                    await self._send_reply(msg, result)
                    return
                
                elif "数据库备份" in message_text:
                    result = admin_tools.backup_database()
                    await self._send_reply(msg, result)
                    return
                    
        except Exception as e:
            error_handler.log_error(e, {
                'operation': 'on_group_message',
                'user_id': user_id,
                'group_id': group_id,
                'message_text': message_text
            })
            
            # 发送错误消息
            error_msg = "❌ 系统繁忙，请稍后重试"
            await self._send_reply(msg, error_msg)
    def _is_admin(self, user_id: str) -> bool:
        """检查是否为管理员"""
        # 这里可以添加管理员检查逻辑
        # 例如从配置文件读取管理员列表
        admin_users = ['123456789']  # 示例管理员ID
        return user_id in admin_users
    
    async def _send_reply(self, msg: GroupMessage, content: str):
        """发送回复消息"""
        # 检查消息长度，如果超过阈值则使用转发消息
        if len(content) > 200:
            # 尝试获取机器人QQ号，默认10000
            bot_uin = "10000"
            
            nodes = [napcat_service.construct_node(bot_uin, "PointsMall", content)]
            
            # 发送转发消息
            success = await napcat_service.send_group_forward_msg(msg.group_id, nodes)
            if success:
                return

        # 使用消息格式化器优化消息格式
        from utils.message_formatter import message_formatter
        formatted_content = message_formatter.truncate_message(content)
        
        # 使用消息链发送回复
        chain = MessageChain([
            Reply(msg.message_id),
            Text(formatted_content)
        ])
        
        await self.api.post_group_msg(
            group_id=msg.group_id,
            rtf=chain
        )
    
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