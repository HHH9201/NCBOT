# /home/hjh/BOT/NCBOT/plugins/PointsMall/utils/help_generator.py
# 帮助文档生成器

from typing import List, Dict
from .message_formatter import message_formatter

class HelpGenerator:
    """帮助文档生成器"""
    
    def __init__(self):
        self.commands = {
            'sign_in': {
                'title': '签到相关命令',
                'commands': [
                    {
                        'command': '签到 / 打卡',
                        'description': '每日签到获取积分',
                        'example': '签到'
                    },
                    {
                        'command': '积分查询 / 查看积分',
                        'description': '查看自己的积分信息',
                        'example': '积分查询'
                    },
                    {
                        'command': '排行榜 [类型]',
                        'description': '查看积分排行榜（总榜/今日/本周/本月/连续）',
                        'example': '排行榜 今日'
                    }
                ]
            },
            'mall': {
                'title': '商城相关命令',
                'commands': [
                    {
                        'command': '抽奖',
                        'description': '消耗积分参与抽奖',
                        'example': '抽奖'
                    },
                    {
                        'command': '转账 @用户 积分',
                        'description': '向其他用户转账积分',
                        'example': '转账 @小明 100'
                    },
                    {
                        'command': '商品列表',
                        'description': '查看可兑换的商品',
                        'example': '商品列表'
                    },
                    {
                        'command': '兑换 商品名称',
                        'description': '使用积分兑换商品',
                        'example': '兑换 虚拟礼物'
                    }
                ]
            },
            'admin': {
                'title': '管理员命令',
                'commands': [
                    {
                        'command': '积分清空 [用户] [群组]',
                        'description': '清空指定用户或群组的积分（仅管理员）',
                        'example': '积分清空 @用户 123456789'
                    },
                    {
                        'command': '系统统计',
                        'description': '查看系统运行统计信息',
                        'example': '系统统计'
                    },
                    {
                        'command': '数据导出 [类型]',
                        'description': '导出用户数据（csv/excel/json）',
                        'example': '数据导出 csv'
                    }
                ]
            }
        }
    
    def generate_help_message(self, category: str = None) -> str:
        """生成帮助消息"""
        if category and category in self.commands:
            return self._generate_category_help(category)
        else:
            return self._generate_full_help()
    
    def _generate_category_help(self, category: str) -> str:
        """生成特定类别的帮助"""
        category_info = self.commands[category]
        commands = category_info['commands']
        
        message = f"📚 {category_info['title']}\n"
        message += "="*40 + "\n"
        
        for cmd in commands:
            message += f"🔹 {cmd['command']}\n"
            message += f"   描述：{cmd['description']}\n"
            message += f"   示例：{cmd['example']}\n\n"
        
        return message
    
    def _generate_full_help(self) -> str:
        """生成完整帮助消息"""
        message = "🤖 积分商城使用帮助\n"
        message += "="*50 + "\n\n"
        
        for category, category_info in self.commands.items():
            message += f"📋 {category_info['title']}\n"
            message += "-"*30 + "\n"
            
            for cmd in category_info['commands']:
                message += f"• {cmd['command']} - {cmd['description']}\n"
            
            message += "\n"
        
        message += "💡 提示：发送 '帮助 [类别]' 查看详细命令说明\n"
        message += "   例如：'帮助 签到' 查看签到相关命令"
        
        return message
    
    def generate_quick_guide(self) -> str:
        """生成快速使用指南"""
        message = "🚀 积分商城快速使用指南\n"
        message += "="*40 + "\n"
        message += "1️⃣ 每日签到：发送 '签到' 获取积分\n"
        message += "2️⃣ 查看积分：发送 '积分查询' 查看当前积分\n"
        message += "3️⃣ 参与抽奖：发送 '抽奖' 消耗积分抽奖\n"
        message += "4️⃣ 转账积分：发送 '转账 @用户 积分' 给好友转账\n"
        message += "5️⃣ 查看排行：发送 '排行榜' 查看积分排名\n"
        message += "\n💎 积分规则：\n"
        message += "• 每日签到可获得基础积分\n"
        message += "• 连续签到有额外奖励\n"
        message += "• 随机获得惊喜奖励\n"
        message += "\n🎁 商城功能：\n"
        message += "• 抽奖赢取大奖\n"
        message += "• 积分兑换商品\n"
        message += "• 好友间转账\n"
        
        return message
    
    def generate_feature_intro(self) -> str:
        """生成功能介绍"""
        message = "🌟 积分商城功能介绍\n"
        message += "="*40 + "\n"
        
        features = [
            {
                'icon': '📅',
                'name': '每日签到',
                'desc': '每日签到获取积分，连续签到奖励更多'
            },
            {
                'icon': '🏆',
                'name': '积分排行',
                'desc': '多维度排行榜，展示积分排名'
            },
            {
                'icon': '🎰',
                'name': '幸运抽奖',
                'desc': '消耗积分参与抽奖，赢取丰厚奖励'
            },
            {
                'icon': '💸',
                'name': '积分转账',
                'desc': '好友间转账积分，方便快捷'
            },
            {
                'icon': '🎁',
                'name': '商品兑换',
                'desc': '使用积分兑换虚拟商品和礼物'
            },
            {
                'icon': '⚙️',
                'name': '多群组支持',
                'desc': '支持不同群组的个性化配置'
            }
        ]
        
        for feature in features:
            message += f"{feature['icon']} {feature['name']}\n"
            message += f"   {feature['desc']}\n\n"
        
        return message

# 创建全局帮助生成器实例
help_generator = HelpGenerator()