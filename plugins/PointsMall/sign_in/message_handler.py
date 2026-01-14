# /home/hjh/BOT/NCBOT/plugins/PointsMall/sign_in/message_handler.py
# 消息处理模块
#

import json
import sys
import os

# 添加工具路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.message_formatter import message_formatter
from utils.error_handler import error_handler
from common.napcat import napcat_service

from .sign_in_core import SignInManager

class SignInMessageHandler:
    def __init__(self):
        self.sign_manager = SignInManager()
    
    def handle_sign_in(self, user_id, group_id, user_name, message_text):
        """处理签到消息"""
        try:
            if "签到" in message_text or "打卡" in message_text:
                result = self.sign_manager.sign_in(user_id, group_id, user_name)
                return message_formatter.format_sign_in_message(result, user_name)
            
            elif "积分" in message_text and ("查询" in message_text or "查看" in message_text):
                user_info = self.sign_manager.get_user_points(user_id, group_id)
                return message_formatter.format_points_query(user_info, user_name)
            
            elif "排行榜" in message_text:
                return self.get_ranking_message(group_id, message_text)
            
            elif "积分清空" in message_text:
                return self.handle_clear_points(user_id, group_id, user_name, message_text)
            
            else:
                return None
                
        except Exception as e:
            error_handler.log_error(e, {
                'operation': 'handle_sign_in',
                'user_id': user_id,
                'group_id': group_id,
                'message_text': message_text
            })
            return message_formatter.format_error_message(
                '系统错误', 
                '处理消息时发生错误',
                '请稍后重试'
            )
    
    def get_ranking_message(self, group_id, message_text):
        """生成排行榜消息"""
        # 确定排行类型
        ranking_type = "total"
        if "今日" in message_text or "今天" in message_text:
            ranking_type = "daily"
        elif "本周" in message_text or "周榜" in message_text:
            ranking_type = "weekly"
        elif "本月" in message_text or "月榜" in message_text:
            ranking_type = "monthly"
        elif "连续" in message_text or "连续签到" in message_text:
            ranking_type = "consecutive"
        
        # 获取排行标题
        titles = {
            "total": "🏆 群内积分总榜 TOP10",
            "daily": "📊 今日积分排行 TOP10",
            "weekly": "📈 本周积分排行 TOP10",
            "monthly": "📅 本月积分排行 TOP10",
            "consecutive": "🔥 连续签到排行 TOP10"
        }
        
        rankings = self.sign_manager.get_ranking(group_id, 10, ranking_type)
        
        if not rankings:
            return f"📊 暂无{ranking_type}签到记录，快来成为第一个签到的人吧！"
        
        message_lines = [titles.get(ranking_type, "🏆 群内排行榜 TOP10")]
        message_lines.append("=" * 40)
        
        for i, ranking in enumerate(rankings, 1):
            if ranking_type == "total":
                user_id, total_points, consecutive_days, last_sign_date = ranking
                points_display = f"{total_points}分"
                extra_info = f"({consecutive_days}天)"
            elif ranking_type == "daily":
                user_id, daily_points, consecutive_days, last_sign_date = ranking
                points_display = f"{daily_points}分"
                extra_info = f"(连续{consecutive_days}天)"
            elif ranking_type == "weekly":
                user_id, weekly_points, consecutive_days, last_sign_date = ranking
                points_display = f"{weekly_points}分"
                extra_info = f"(连续{consecutive_days}天)"
            elif ranking_type == "monthly":
                user_id, monthly_points, consecutive_days, last_sign_date = ranking
                points_display = f"{monthly_points}分"
                extra_info = f"(连续{consecutive_days}天)"
            elif ranking_type == "consecutive":
                user_id, consecutive_days, total_points, last_sign_date = ranking
                points_display = f"{consecutive_days}天"
                extra_info = f"({total_points}分)"
            
            # 这里需要根据user_id获取用户名，暂时用user_id代替
            user_name = f"用户{user_id[-4:]}"  # 简化显示
            
            # 根据排名添加图标
            if i == 1:
                icon = "🥇"
            elif i == 2:
                icon = "🥈"
            elif i == 3:
                icon = "🥉"
            else:
                icon = f"{i}."
            
            message_lines.append(f"{icon} {user_name} - {points_display} {extra_info}")
        
        # 添加排行说明
        message_lines.append("\n💡 使用『今日排行』、『周榜』、『月榜』、『连续排行』查看不同维度排行")
        
        return "\n".join(message_lines)
    
    async def send_long_message(self, group_id, messages):
        """发送长消息（使用转发消息）"""
        if isinstance(messages, str):
            messages = [messages]
        
        nodes = []
        for i, msg in enumerate(messages):
            nodes.append(napcat_service.construct_node("10000", "签到助手", msg))
        
        return await napcat_service.send_group_forward_msg(group_id, nodes)
    
    def handle_clear_points(self, user_id, group_id, user_name, message_text):
        """处理积分清空命令"""
        import re
        
        # 检查是否有@他人
        at_pattern = r'\[CQ:at,qq=(\d+)\]'
        at_matches = re.findall(at_pattern, message_text)
        
        if at_matches:
            # @他人清空积分
            target_user_id = at_matches[0]
            target_user_name = f"用户{target_user_id}"  # 这里需要获取真实用户名，暂时用用户ID代替
            
            result = self.sign_manager.clear_user_points(user_id, target_user_id, target_user_name, group_id)
            return result['message']
        else:
            # 清空自己的积分
            result = self.sign_manager.clear_user_points(user_id, user_id, user_name, group_id)
            return result['message']
    
    def get_help_message(self):
        """获取帮助信息"""
        return """
🎯 签到插件使用说明

📌 基本命令：
• 签到/打卡 - 每日签到获得积分
• 积分查询 - 查看个人积分信息
• 积分排行榜 - 查看群内积分排行

🔱 root用户特权：
• 积分清空 - 清空自己的积分
• @某人 积分清空 - 清空指定用户的积分

💡 积分规则：
• 基础签到：10积分
• 连续签到奖励：每天+2积分（最高50）
• 随机奖励：1-5积分
• 连续7天签到有额外惊喜！

🎁 连续签到奖励：
• 7天：额外称号奖励
• 30天：超级签到王者称号

快来签到，赢取积分吧！ 🚀
"""