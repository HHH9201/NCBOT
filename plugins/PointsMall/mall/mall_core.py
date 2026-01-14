# /home/hjh/BOT/NCBOT/plugins/PointsMall/mall/mall_core.py
# 积分商城核心模块

import json
import datetime
import random
from typing import Dict, List, Optional, Tuple
import yaml
import os
import sys
from pathlib import Path

# 添加配置管理器路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.config_manager import ConfigManager
from utils.error_handler import error_handler, error_decorator
from common.db import db_manager

class PointsMallManager:
    """积分商城管理器"""
    
    def __init__(self):
        """初始化商城管理器"""
        self.config_manager = ConfigManager()
        self.init_database()
    
    def load_config(self):
        """加载商城配置"""
        config_path = Path(__file__).parent.parent / "config" / "mall.yaml"
        
        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                return yaml.safe_load(file)
        except FileNotFoundError:
            return self.get_default_config()
        except Exception as e:
            print(f"加载商城配置失败: {e}，使用默认配置")
            return self.get_default_config()
    
    def get_config(self, group_id: str = None) -> Dict:
        """获取商城配置（支持多群组）"""
        return self.config_manager.get_config(group_id, 'mall')
    
    def get_default_config(self):
        """默认商城配置"""
        return {
            'mall_config': {
                'exchange_rate': 1.0,  # 积分兑换比例
                'daily_limit': 10,     # 每日兑换限制
                'enable_gift': True,   # 启用礼物功能
                'enable_lottery': True # 启用抽奖功能
            },
            'lottery_config': {
                'cost_per_try': 50,    # 每次抽奖消耗积分
                'prizes': [
                    {'name': '一等奖', 'points': 500, 'probability': 0.01},
                    {'name': '二等奖', 'points': 200, 'probability': 0.05},
                    {'name': '三等奖', 'points': 100, 'probability': 0.1},
                    {'name': '四等奖', 'points': 50, 'probability': 0.2},
                    {'name': '五等奖', 'points': 20, 'probability': 0.3},
                    {'name': '谢谢参与', 'points': 0, 'probability': 0.34}
                ]
            }
        }
    
    def init_database(self):
        """初始化商城数据库表"""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # 商品表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS mall_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    price INTEGER NOT NULL,
                    stock INTEGER DEFAULT -1,  -- -1表示无限库存
                    category TEXT NOT NULL,
                    enabled BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 兑换记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS exchange_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    item_id INTEGER NOT NULL,
                    item_name TEXT NOT NULL,
                    price INTEGER NOT NULL,
                    quantity INTEGER DEFAULT 1,
                    exchange_date DATE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (item_id) REFERENCES mall_items(id)
                )
            ''')
            
            # 转账记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS transfer_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_user_id TEXT NOT NULL,
                    to_user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    points INTEGER NOT NULL,
                    transfer_date DATE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 抽奖记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS lottery_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    prize_name TEXT NOT NULL,
                    points_won INTEGER DEFAULT 0,
                    cost_points INTEGER NOT NULL,
                    lottery_date DATE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 红包记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS red_packet_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    total_points INTEGER NOT NULL,
                    packet_count INTEGER NOT NULL,
                    packet_type TEXT NOT NULL,  -- random/fixed
                    claimed_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expired_at TIMESTAMP
                )
            ''')
            
            # 红包领取记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS red_packet_claims (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    packet_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    points_received INTEGER NOT NULL,
                    claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (packet_id) REFERENCES red_packet_records(id)
                )
            ''')
            
            # 创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_exchange_user_date ON exchange_records(user_id, exchange_date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_transfer_from_date ON transfer_records(from_user_id, transfer_date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_lottery_user_date ON lottery_records(user_id, lottery_date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_red_packet_group ON red_packet_records(group_id, created_at)')
            
            conn.commit()
    
    def add_item(self, name: str, description: str, price: int, category: str, stock: int = -1) -> bool:
        """添加商品"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO mall_items (name, description, price, category, stock)
                    VALUES (?, ?, ?, ?, ?)
                ''', (name, description, price, category, stock))
                conn.commit()
                return True
        except Exception as e:
            print(f"添加商品失败: {e}")
            return False
    
    def get_items(self, category: str = None) -> List[Dict]:
        """获取商品列表"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                if category:
                    cursor.execute('''
                        SELECT id, name, description, price, stock, category 
                        FROM mall_items 
                        WHERE category = ? AND enabled = 1
                        ORDER BY price ASC
                    ''', (category,))
                else:
                    cursor.execute('''
                        SELECT id, name, description, price, stock, category 
                        FROM mall_items 
                        WHERE enabled = 1
                        ORDER BY category, price ASC
                    ''')
                
                items = []
                for row in cursor.fetchall():
                    items.append({
                        'id': row[0],
                        'name': row[1],
                        'description': row[2],
                        'price': row[3],
                        'stock': row[4],
                        'category': row[5]
                    })
                return items
        except Exception as e:
            print(f"获取商品列表失败: {e}")
            return []
    
    def exchange_item(self, user_id: str, group_id: str, item_id: int, quantity: int = 1) -> Dict:
        """兑换商品（支持多群组配置）"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # 获取商品信息
                cursor.execute('SELECT name, price, stock FROM mall_items WHERE id = ? AND enabled = 1', (item_id,))
                item = cursor.fetchone()
                
                if not item:
                    return {'success': False, 'message': '商品不存在或已下架'}
                
                item_name, price, stock = item
                total_cost = price * quantity
                
                # 检查库存
                if stock != -1 and stock < quantity:
                    return {'success': False, 'message': f'库存不足，当前仅剩{stock}件'}
                
                # 检查用户积分
                cursor.execute('SELECT total_points FROM user_points WHERE user_id = ? AND group_id = ?', (user_id, group_id))
                user_points = cursor.fetchone()
                
                if not user_points or user_points[0] < total_cost:
                    return {'success': False, 'message': '积分不足，无法兑换'}
                
                # 检查每日兑换限制
                today = datetime.date.today()
                cursor.execute('''
                    SELECT SUM(quantity) FROM exchange_records 
                    WHERE user_id = ? AND group_id = ? AND exchange_date = ?
                ''', (user_id, group_id, str(today)))
                
                daily_exchanges = cursor.fetchone()[0] or 0
                mall_config = self.get_config(group_id).get('mall_config', {})
                daily_limit = mall_config.get('daily_limit', 10)
                
                if daily_exchanges + quantity > daily_limit:
                    return {'success': False, 'message': f'今日兑换次数已达上限，还可兑换{daily_limit - daily_exchanges}次'}
                
                # 执行兑换
                cursor.execute('''
                    UPDATE user_points SET total_points = total_points - ? 
                    WHERE user_id = ? AND group_id = ?
                ''', (total_cost, user_id, group_id))
                
                # 更新库存
                if stock != -1:
                    cursor.execute('UPDATE mall_items SET stock = stock - ? WHERE id = ?', (quantity, item_id))
                
                # 记录兑换
                cursor.execute('''
                    INSERT INTO exchange_records 
                    (user_id, group_id, item_id, item_name, price, quantity, exchange_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, group_id, item_id, item_name, price, quantity, str(today)))
                
                conn.commit()
                
                return {
                    'success': True, 
                    'message': f'兑换成功！消耗{total_cost}积分获得{quantity}个{item_name}',
                    'remaining_points': user_points[0] - total_cost
                }
        except Exception as e:
            return {'success': False, 'message': f'兑换失败：{str(e)}'}
    
    def transfer_points(self, from_user_id: str, to_user_id: str, group_id: str, points: int) -> Dict:
        """积分转账"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # 检查是否是自己转账给自己
                if from_user_id == to_user_id:
                    return {'success': False, 'message': '不能转账给自己'}
                
                # 检查转账人积分
                cursor.execute('SELECT total_points FROM user_points WHERE user_id = ? AND group_id = ?', 
                             (from_user_id, group_id))
                from_user_points = cursor.fetchone()
                
                if not from_user_points or from_user_points[0] < points:
                    return {'success': False, 'message': '积分不足'}
                
                if points <= 0:
                    return {'success': False, 'message': '转账积分必须大于0'}
                
                # 执行转账
                cursor.execute('''
                    UPDATE user_points SET total_points = total_points - ? 
                    WHERE user_id = ? AND group_id = ?
                ''', (points, from_user_id, group_id))
                
                # 确保收款人记录存在
                cursor.execute('''
                    INSERT OR IGNORE INTO user_points (user_id, group_id, total_points, consecutive_days, last_sign_date)
                    VALUES (?, ?, 0, 0, NULL)
                ''', (to_user_id, group_id))
                
                cursor.execute('''
                    UPDATE user_points SET total_points = total_points + ? 
                    WHERE user_id = ? AND group_id = ?
                ''', (points, to_user_id, group_id))
                
                # 记录转账
                today = datetime.date.today()
                cursor.execute('''
                    INSERT INTO transfer_records (from_user_id, to_user_id, group_id, points, transfer_date)
                    VALUES (?, ?, ?, ?, ?)
                ''', (from_user_id, to_user_id, group_id, points, str(today)))
                
                conn.commit()
                
                return {
                    'success': True, 
                    'message': f'转账成功！向对方转账{points}积分',
                    'remaining_points': from_user_points[0] - points
                }
                
        except Exception as e:
            print(f"积分转账失败: {e}")
            return {'success': False, 'message': '转账失败，请稍后重试'}
    
    def lottery(self, user_id: str, group_id: str) -> Dict:
        """抽奖（支持多群组配置）"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # 检查用户积分
                cursor.execute('SELECT total_points FROM user_points WHERE user_id = ? AND group_id = ?', (user_id, group_id))
                user_points = cursor.fetchone()
                
                if not user_points:
                    return {'success': False, 'message': '您还没有积分，请先签到获取积分'}
                
                # 获取抽奖配置
                mall_config = self.get_config(group_id)
                lottery_config = mall_config.get('lottery_config', {})
                cost_per_try = lottery_config.get('cost_per_try', 50)
                
                if user_points[0] < cost_per_try:
                    return {'success': False, 'message': f'积分不足，抽奖需要{cost_per_try}积分'}
                
                # 执行抽奖
                prizes = lottery_config.get('prizes', [])
                if not prizes:
                    return {'success': False, 'message': '抽奖配置错误，请联系管理员'}
                
                # 计算概率总和
                total_probability = sum(prize.get('probability', 0) for prize in prizes)
                if total_probability <= 0:
                    return {'success': False, 'message': '抽奖配置错误，请联系管理员'}
                
                # 随机选择奖品
                random_value = random.random() * total_probability
                cumulative_probability = 0
                selected_prize = None
                
                for prize in prizes:
                    cumulative_probability += prize.get('probability', 0)
                    if random_value <= cumulative_probability:
                        selected_prize = prize
                        break
                
                if not selected_prize:
                    selected_prize = prizes[-1]  # 默认选择最后一个
                
                # 扣除积分
                cursor.execute('''
                    UPDATE user_points SET total_points = total_points - ? 
                    WHERE user_id = ? AND group_id = ?
                ''', (cost_per_try, user_id, group_id))
                
                # 如果抽中积分奖励，则添加积分
                prize_points = selected_prize.get('points', 0)
                if prize_points > 0:
                    cursor.execute('''
                        UPDATE user_points SET total_points = total_points + ? 
                        WHERE user_id = ? AND group_id = ?
                    ''', (prize_points, user_id, group_id))
                
                # 记录抽奖
                today = datetime.date.today()
                cursor.execute('''
                    INSERT INTO lottery_records (user_id, group_id, prize_name, points_won, cost_points, lottery_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, group_id, selected_prize['name'], prize_points, cost_per_try, str(today)))
                
                conn.commit()
                
                return {
                    'success': True, 
                    'message': f'抽中：{selected_prize["name"]}',
                    'remaining_points': user_points[0] - cost_per_try + prize_points
                }
        
        except Exception as e:
            print(f"抽奖失败: {e}")
            return {'success': False, 'message': '抽奖失败，请稍后重试'}

    def get_exchange_history(self, user_id: str, group_id: str, limit: int = 10) -> List[Tuple]:
        """获取兑换记录"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT item_name, price, quantity, exchange_date 
                    FROM exchange_records 
                    WHERE user_id = ? AND group_id = ? 
                    ORDER BY exchange_date DESC 
                    LIMIT ?
                ''', (user_id, group_id, limit))
                return cursor.fetchall()
        except Exception as e:
            print(f"获取兑换记录失败: {e}")
            return []

    def get_lottery_history(self, user_id: str, group_id: str, limit: int = 10) -> List[Tuple]:
        """获取抽奖记录"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT prize_name, points_won, cost_points, lottery_date 
                    FROM lottery_records 
                    WHERE user_id = ? AND group_id = ? 
                    ORDER BY lottery_date DESC 
                    LIMIT ?
                ''', (user_id, group_id, limit))
                return cursor.fetchall()
        except Exception as e:
            print(f"获取抽奖记录失败: {e}")
            return []