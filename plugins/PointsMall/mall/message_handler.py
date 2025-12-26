# /home/hjh/BOT/NCBOT/plugins/PointsMall/mall/message_handler.py
# 商城消息处理模块

import re
import json
import requests
from .mall_core import PointsMallManager

class MallMessageHandler:
    def __init__(self):
        self.mall_manager = PointsMallManager()
        self.forward_url = "http://101.35.164.122:3006/send_group_forward_msg"
        self.forward_headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer he031701'
        }
    
    def handle_mall_command(self, user_id: str, group_id: str, user_name: str, message_text: str) -> str:
        """处理商城相关命令"""
        
        # 商城帮助
        if "商城帮助" in message_text or "积分商城帮助" in message_text:
            return self.get_mall_help_message()
        
        # 查看商品列表
        elif "商品列表" in message_text or "商城" in message_text:
            return self.get_items_list()
        
        # 兑换商品
        elif "兑换" in message_text:
            return self.handle_exchange(user_id, group_id, user_name, message_text)
        
        # 积分转账
        elif "转账" in message_text or "转积分" in message_text:
            return self.handle_transfer(user_id, group_id, user_name, message_text)
        
        # 抽奖
        elif "抽奖" in message_text or "大转盘" in message_text:
            return self.handle_lottery(user_id, group_id, user_name)
        
        # 发红包
        elif "发红包" in message_text:
            return self.handle_send_red_packet(user_id, group_id, user_name, message_text)
        
        # 抢红包
        elif "抢红包" in message_text or "开红包" in message_text:
            return self.handle_claim_red_packet(user_id, group_id, user_name)
        
        # 我的兑换记录
        elif "我的兑换" in message_text or "兑换记录" in message_text:
            return self.get_exchange_history(user_id, group_id)
        
        # 我的抽奖记录
        elif "抽奖记录" in message_text:
            return self.get_lottery_history(user_id, group_id)
        
        else:
            return None
    
    def get_mall_help_message(self) -> str:
        """获取商城帮助信息"""
        return """🛍️ 积分商城使用指南

📋 基础命令：
• 商城/商品列表 - 查看可兑换商品
• 兑换[商品名] - 兑换指定商品
• 转账[QQ号][金额] - 向指定用户转账积分
• 抽奖 - 消耗50积分参与抽奖
• 发红包[金额][数量] - 发送随机红包
• 抢红包 - 抢当前群的红包

📊 查询命令：
• 我的兑换 - 查看兑换记录
• 抽奖记录 - 查看抽奖记录
• 红包记录 - 查看红包记录

💡 提示：
• 每日最多兑换10次商品
• 转账需双方都在群内
• 红包24小时内有效
• 抽奖有机会获得大量积分"""
    
    def get_items_list(self) -> str:
        """获取商品列表"""
        items = self.mall_manager.get_items()
        
        if not items:
            return "🛒 商城暂无商品，请联系管理员添加商品"
        
        # 按分类分组
        categories = {}
        for item in items:
            category = item['category']
            if category not in categories:
                categories[category] = []
            categories[category].append(item)
        
        message_lines = ["🛍️ 积分商城 - 商品列表"]
        message_lines.append("=" * 40)
        
        for category, category_items in categories.items():
            message_lines.append(f"\n📦 {category}：")
            for item in category_items:
                stock_info = "无限" if item['stock'] == -1 else f"剩余{item['stock']}"
                message_lines.append(f"  • {item['name']} - {item['price']}积分 ({stock_info})")
                if item['description']:
                    message_lines.append(f"    说明：{item['description']}")
        
        message_lines.append("\n💡 使用『兑换[商品名]』进行兑换")
        
        return "\n".join(message_lines)
    
    def handle_exchange(self, user_id: str, group_id: str, user_name: str, message_text: str) -> str:
        """处理商品兑换"""
        # 提取商品名称
        match = re.search(r'兑换\s*(\S+)', message_text)
        if not match:
            return "❌ 请指定要兑换的商品名称，如：兑换改名卡"
        
        item_name = match.group(1)
        
        # 获取商品信息
        items = self.mall_manager.get_items()
        target_item = None
        
        for item in items:
            if item['name'] == item_name:
                target_item = item
                break
        
        if not target_item:
            return f"❌ 未找到商品：{item_name}，请检查商品名称是否正确"
        
        # 执行兑换
        result = self.mall_manager.exchange_item(user_id, group_id, target_item['id'])
        
        if result['success']:
            return f"🎉 {user_name} {result['message']}\n💎 剩余积分：{result['remaining_points']}"
        else:
            return f"❌ {result['message']}"
    
    def handle_transfer(self, user_id: str, group_id: str, user_name: str, message_text: str) -> str:
        """处理积分转账"""
        # 提取转账对象和金额
        match = re.search(r'转账\s*(\d+)\s*(\d+)', message_text)
        if not match:
            return "❌ 格式错误，请使用：转账[QQ号][金额]"
        
        to_user_id = match.group(1)
        points = int(match.group(2))
        
        if points <= 0:
            return "❌ 转账金额必须大于0"
        
        # 执行转账
        result = self.mall_manager.transfer_points(user_id, to_user_id, group_id, points)
        
        if result['success']:
            return f"💸 {user_name} {result['message']}\n💎 剩余积分：{result['remaining_points']}"
        else:
            return f"❌ {result['message']}"
    
    def handle_lottery(self, user_id: str, group_id: str, user_name: str) -> str:
        """处理抽奖"""
        result = self.mall_manager.lottery(user_id, group_id)
        
        if result['success']:
            return f"🎲 {user_name} {result['message']}\n💎 剩余积分：{result['remaining_points']}"
        else:
            return f"❌ {result['message']}"
    
    def handle_send_red_packet(self, user_id: str, group_id: str, user_name: str, message_text: str) -> str:
        """处理发送红包"""
        # 简化实现，实际需要更复杂的红包逻辑
        return "🧧 红包功能开发中，敬请期待！"
    
    def handle_claim_red_packet(self, user_id: str, group_id: str, user_name: str) -> str:
        """处理抢红包"""
        return "🧧 红包功能开发中，敬请期待！"
    
    def get_exchange_history(self, user_id: str, group_id: str) -> str:
        """获取兑换记录"""
        try:
            with self.mall_manager.conn:
                cursor = self.mall_manager.conn.cursor()
                cursor.execute('''
                    SELECT item_name, price, quantity, exchange_date 
                    FROM exchange_records 
                    WHERE user_id = ? AND group_id = ? 
                    ORDER BY exchange_date DESC 
                    LIMIT 10
                ''', (user_id, group_id))
                
                records = cursor.fetchall()
                
                if not records:
                    return "📝 暂无兑换记录"
                
                message_lines = ["📋 最近10次兑换记录："]
                for record in records:
                    item_name, price, quantity, exchange_date = record
                    total_cost = price * quantity
                    message_lines.append(f"• {exchange_date} - {item_name} x{quantity} ({total_cost}积分)")
                
                return "\n".join(message_lines)
                
        except Exception as e:
            return f"❌ 获取兑换记录失败：{e}"
    
    def get_lottery_history(self, user_id: str, group_id: str) -> str:
        """获取抽奖记录"""
        try:
            with self.mall_manager.conn:
                cursor = self.mall_manager.conn.cursor()
                cursor.execute('''
                    SELECT prize_name, points_won, cost_points, lottery_date 
                    FROM lottery_records 
                    WHERE user_id = ? AND group_id = ? 
                    ORDER BY lottery_date DESC 
                    LIMIT 10
                ''', (user_id, group_id))
                
                records = cursor.fetchall()
                
                if not records:
                    return "🎲 暂无抽奖记录"
                
                message_lines = ["📋 最近10次抽奖记录："]
                total_profit = 0
                
                for record in records:
                    prize_name, points_won, cost_points, lottery_date = record
                    profit = points_won - cost_points
                    total_profit += profit
                    
                    profit_text = f"盈利{profit}" if profit > 0 else f"亏损{-profit}"
                    message_lines.append(f"• {lottery_date} - {prize_name} ({profit_text})")
                
                message_lines.append(f"\n💰 总盈亏：{'盈利' if total_profit > 0 else '亏损'}{abs(total_profit)}积分")
                
                return "\n".join(message_lines)
                
        except Exception as e:
            return f"❌ 获取抽奖记录失败：{e}"