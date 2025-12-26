# /home/hjh/BOT/NCBOT/plugins/PointsMall/utils/message_formatter.py
# 消息格式化和用户体验优化工具

import re
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

class MessageFormatter:
    """消息格式化器"""
    
    def __init__(self):
        self.emoji_map = {
            'success': '✅',
            'error': '❌',
            'warning': '⚠️',
            'info': 'ℹ️',
            'points': '💰',
            'ranking': '🏆',
            'gift': '🎁',
            'lottery': '🎰',
            'transfer': '💸',
            'red_packet': '🧧',
            'sign_in': '📅',
            'user': '👤',
            'group': '👥',
            'time': '⏰',
            'calendar': '📆',
            'trophy': '🏅',
            'star': '⭐',
            'fire': '🔥',
            'rocket': '🚀',
            'heart': '❤️',
            'clap': '👏',
            'party': '🎉',
            'confetti': '🎊',
            'medal': '🥇',
            'crown': '👑',
            'diamond': '💎',
            'money': '💵',
            'bank': '🏦',
            'chart': '📊'
        }
        
        self.color_codes = {
            'success': '#00FF00',
            'error': '#FF0000',
            'warning': '#FFA500',
            'info': '#1E90FF',
            'points': '#FFD700',
            'ranking': '#FF69B4'
        }
    
    def format_sign_in_message(self, result: Dict[str, Any], user_name: str) -> str:
        """格式化签到消息"""
        if not result.get('success'):
            return f"{self.emoji_map['error']} {result['message']}"
        
        points_info = result['points_info']
        message = f"{self.emoji_map['sign_in']} {user_name} 签到成功！\n"
        message += f"{self.emoji_map['points']} 今日获得积分：{points_info['total_points']}\n"
        
        if points_info['base_points'] > 0:
            message += f"   • 基础积分：{points_info['base_points']}\n"
        
        if points_info['consecutive_bonus'] > 0:
            message += f"   • 连续签到奖励：+{points_info['consecutive_bonus']}\n"
        
        if points_info['random_bonus'] > 0:
            message += f"   • 随机奖励：+{points_info['random_bonus']}\n"
        
        if points_info['extra_bonus'] > 0:
            message += f"   • 额外惊喜：+{points_info['extra_bonus']} {self.emoji_map['party']}\n"
        
        message += f"{self.emoji_map['calendar']} 连续签到：{result['consecutive_days']}天\n"
        message += f"{self.emoji_map['money']} 总积分：{result['total_points']}\n"
        
        if result.get('special_message'):
            message += f"\n{result['special_message']}"
        
        return message
    
    def format_ranking_message(self, rankings: List[Dict[str, Any]], rank_type: str, group_name: str = None) -> str:
        """格式化排行榜消息"""
        rank_titles = {
            'total': '总积分排行榜',
            'daily': '今日积分排行榜',
            'weekly': '本周积分排行榜',
            'monthly': '本月积分排行榜',
            'consecutive': '连续签到排行榜'
        }
        
        title = rank_titles.get(rank_type, '排行榜')
        message = f"{self.emoji_map['ranking']} {title}"
        
        if group_name:
            message += f" - {group_name}"
        
        message += "\n" + "="*30 + "\n"
        
        if not rankings:
            message += f"{self.emoji_map['info']} 暂无数据\n"
            return message
        
        for i, rank in enumerate(rankings, 1):
            medal = self._get_medal_emoji(i)
            user_name = rank.get('user_name', '未知用户')
            points = rank.get('points', 0)
            
            if rank_type == 'consecutive':
                value_text = f"连续{points}天"
            else:
                value_text = f"{points}积分"
            
            message += f"{medal} 第{i}名：{user_name} - {value_text}\n"
        
        message += "="*30
        return message
    
    def format_lottery_message(self, result: Dict[str, Any]) -> str:
        """格式化抽奖消息"""
        if not result.get('success'):
            return f"{self.emoji_map['error']} {result['message']}"
        
        message = f"{self.emoji_map['lottery']} 抽奖结果\n"
        message += "="*20 + "\n"
        message += f"🎉 {result['prize_name']}！\n"
        
        if result.get('prize_points', 0) > 0:
            message += f"{self.emoji_map['points']} 获得积分：+{result['prize_points']}\n"
        
        message += f"{self.emoji_map['money']} 消耗积分：-{result['cost_points']}\n"
        message += f"{self.emoji_map['bank']} 剩余积分：{result.get('remaining_points', 0)}\n"
        
        return message
    
    def format_transfer_message(self, result: Dict[str, Any], from_user: str, to_user: str) -> str:
        """格式化转账消息"""
        if not result.get('success'):
            return f"{self.emoji_map['error']} {result['message']}"
        
        message = f"{self.emoji_map['transfer']} 转账成功！\n"
        message += "="*20 + "\n"
        message += f"👤 转账人：{from_user}\n"
        message += f"👤 收款人：{to_user}\n"
        message += f"💰 转账金额：{result['amount']}积分\n"
        message += f"💸 手续费：{result.get('fee', 0)}积分\n"
        message += f"🏦 剩余积分：{result.get('remaining_balance', 0)}\n"
        
        return message
    
    def format_points_query(self, user_info: Dict[str, Any], user_name: str) -> str:
        """格式化积分查询消息"""
        message = f"{self.emoji_map['user']} {user_name} 的积分信息\n"
        message += "="*25 + "\n"
        message += f"{self.emoji_map['points']} 当前积分：{user_info.get('total_points', 0)}\n"
        message += f"{self.emoji_map['calendar']} 连续签到：{user_info.get('consecutive_days', 0)}天\n"
        message += f"{self.emoji_map['chart']} 总签到天数：{user_info.get('total_sign_days', 0)}天\n"
        
        if user_info.get('last_sign_date'):
            message += f"{self.emoji_map['time']} 最后签到：{user_info['last_sign_date']}\n"
        
        return message
    
    def format_help_message(self, commands: List[Dict[str, str]]) -> str:
        """格式化帮助消息"""
        message = f"{self.emoji_map['info']} 积分商城使用帮助\n"
        message += "="*30 + "\n"
        
        for cmd in commands:
            message += f"🔹 {cmd['command']}\n"
            message += f"    {cmd['description']}\n\n"
        
        message += "="*30
        return message
    
    def format_error_message(self, error_type: str, error_message: str, suggestion: str = None) -> str:
        """格式化错误消息"""
        message = f"{self.emoji_map['error']} 操作失败\n"
        message += "="*20 + "\n"
        message += f"错误类型：{error_type}\n"
        message += f"错误信息：{error_message}\n"
        
        if suggestion:
            message += f"\n💡 建议：{suggestion}\n"
        
        return message
    
    def format_success_message(self, title: str, content: str, details: List[str] = None) -> str:
        """格式化成功消息"""
        message = f"{self.emoji_map['success']} {title}\n"
        message += "="*20 + "\n"
        message += f"{content}\n"
        
        if details:
            for detail in details:
                message += f"• {detail}\n"
        
        return message
    
    def format_statistics_message(self, stats: Dict[str, Any]) -> str:
        """格式化统计消息"""
        message = f"{self.emoji_map['chart']} 系统统计信息\n"
        message += "="*30 + "\n"
        
        if 'user_stats' in stats:
            user_stats = stats['user_stats']
            message += f"👥 用户统计：\n"
            message += f"   • 总用户数：{user_stats.get('total_users', 0)}\n"
            message += f"   • 活跃用户：{user_stats.get('active_users', 0)}\n"
            message += f"   • 今日签到：{user_stats.get('today_sign_ins', 0)}\n"
            message += "\n"
        
        if 'points_stats' in stats:
            points_stats = stats['points_stats']
            message += f"💰 积分统计：\n"
            message += f"   • 总积分：{points_stats.get('total_points', 0)}\n"
            message += f"   • 今日发放：{points_stats.get('today_points', 0)}\n"
            message += f"   • 平均积分：{points_stats.get('avg_points', 0)}\n"
            message += "\n"
        
        if 'system_stats' in stats:
            system_stats = stats['system_stats']
            message += f"⚙️ 系统统计：\n"
            message += f"   • 运行时间：{system_stats.get('uptime', '未知')}\n"
            message += f"   • 数据库大小：{system_stats.get('db_size', '未知')}\n"
        
        return message
    
    def _get_medal_emoji(self, rank: int) -> str:
        """根据排名获取奖牌表情"""
        if rank == 1:
            return self.emoji_map['medal']
        elif rank == 2:
            return '🥈'
        elif rank == 3:
            return '🥉'
        else:
            return f"{rank}."
    
    def truncate_message(self, message: str, max_length: int = 500) -> str:
        """截断过长的消息"""
        if len(message) <= max_length:
            return message
        
        # 保留重要信息，截断多余内容
        lines = message.split('\n')
        truncated_lines = []
        current_length = 0
        
        for line in lines:
            if current_length + len(line) + 1 <= max_length - 20:  # 保留空间给截断提示
                truncated_lines.append(line)
                current_length += len(line) + 1
            else:
                break
        
        truncated_message = '\n'.join(truncated_lines)
        truncated_message += f"\n... (消息过长，已截断)"
        
        return truncated_message
    
    def add_timestamp(self, message: str) -> str:
        """添加时间戳"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return f"{message}\n\n{self.emoji_map['time']} 更新时间：{timestamp}"

# 创建全局消息格式化器实例
message_formatter = MessageFormatter()