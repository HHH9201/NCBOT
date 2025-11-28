# /home/hjh/BOT/NCBOT/plugins/PointsMall/sign_in/message_handler.py
# 消息处理模块

import json
import requests
from .sign_in_core import SignInManager

class SignInMessageHandler:
    def __init__(self):
        self.sign_manager = SignInManager()
        self.forward_url = "http://101.35.164.122:3006/send_group_forward_msg"
        self.forward_headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer he031701'
        }
    
    def handle_sign_in(self, user_id, group_id, user_name, message_text):
        """处理签到消息"""
        if "签到" in message_text or "打卡" in message_text:
            result = self.sign_manager.sign_in(user_id, group_id, user_name)
            return result['message']
        
        elif "积分" in message_text and ("查询" in message_text or "查看" in message_text):
            user_info = self.sign_manager.get_user_points(user_id, group_id)
            
            # root用户与普通用户积分查询显示一致
            return f"💎 {user_name} 的积分信息：\n" \
                   f"总积分：{user_info['total_points']}\n" \
                   f"连续签到：{user_info['consecutive_days']}天\n" \
                   f"最后签到：{user_info['last_sign_date'] or '从未签到'}"
        
        elif "排行榜" in message_text and "积分" in message_text:
            return self.get_ranking_message(group_id)
        
        elif "积分清空" in message_text:
            return self.handle_clear_points(user_id, group_id, user_name, message_text)
        
        else:
            return None
    
    def get_ranking_message(self, group_id):
        """生成排行榜消息"""
        rankings = self.sign_manager.get_ranking(group_id, 10)
        
        if not rankings:
            return "📊 暂无签到记录，快来成为第一个签到的人吧！"
        
        message_lines = ["🏆 群内积分排行榜 TOP10"]
        message_lines.append("=" * 30)
        
        for i, (user_id, total_points, consecutive_days, last_sign_date) in enumerate(rankings, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🏅"
            
            # 检查是否为root用户
            is_root = self.sign_manager.is_root_user(user_id)
            root_icon = "🔱" if is_root else ""
            
            message_lines.append(
                f"{medal} 第{i}名{root_icon} - 积分：{total_points} | 连续：{consecutive_days}天"
            )
        
        message_lines.append("=" * 30)
        message_lines.append("💪 继续努力，争取上榜！")
        
        return "\n".join(message_lines)
    
    def send_long_message(self, group_id, messages):
        """发送长消息（使用转发消息）"""
        if isinstance(messages, str):
            messages = [messages]
        
        nodes = []
        for i, msg in enumerate(messages):
            node = {
                "type": "node",
                "data": {
                    "name": f"签到助手",
                    "uin": "123456789",
                    "content": msg
                }
            }
            nodes.append(node)
        
        payload = {
            "group_id": group_id,
            "messages": nodes
        }
        
        try:
            response = requests.post(
                self.forward_url,
                headers=self.forward_headers,
                json=payload,
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            print(f"发送转发消息失败：{e}")
            return False
    
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