# /home/hjh/BOT/NCBOT/plugins/PointsMall/sign_in/sign_in_core.py
# 签到获得积分核心功能模块

import sqlite3
import datetime
from datetime import timedelta
import random
import yaml
import os
from typing import Optional, Dict, List, Tuple

class SignInManager:
    """签到积分管理器"""
    
    def __init__(self, db_path: str = "/home/hjh/BOT/NCBOT/mydb/mydb.db"):
        """初始化签到管理器"""
        self.db_path = db_path
        self.config = self.load_config()
        self.init_database()
    
    def load_config(self):
        """加载配置文件"""
        config_path = "/home/hjh/BOT/NCBOT/plugins/PointsMall/config/sign_in.yaml"
        root_config_path = "/home/hjh/BOT/NCBOT/plugins/PointsMall/config/root.yaml"
        
        try:
            # 加载主配置
            with open(config_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)
            
            # 加载root配置
            try:
                with open(root_config_path, 'r', encoding='utf-8') as root_file:
                    root_config = yaml.safe_load(root_file)
                    if root_config and 'root_config' in root_config:
                        config['root_config'] = root_config['root_config']
                    elif root_config:
                        # 如果root.yaml中没有root_config键，直接使用整个文件内容
                        config['root_config'] = root_config
            except FileNotFoundError:
                print("root.yaml配置文件不存在，跳过root配置加载")
            except Exception as e:
                print(f"加载root配置文件失败: {e}，跳过root配置")
            
            return config
            
        except FileNotFoundError:
            # 如果主配置文件不存在，返回默认配置
            return self.get_default_config()
        except Exception as e:
            print(f"加载配置文件失败: {e}，使用默认配置")
            return self.get_default_config()
    
    def get_default_config(self):
        """默认配置"""
        return {
            'points_config': {
                'base_points': 10,
                'consecutive_bonus': 2,
                'max_consecutive_bonus': 50,
                'random_bonus_min': 1,
                'random_bonus_max': 5
            },
            'feature_config': {
                'enable_consecutive_bonus': True,
                'enable_random_bonus': True,
                'enable_special_dates': True,
                'enable_level_system': True,
                'enable_lucky_words': True
            },
            'message_config': {
                'lucky_words': [
                    "🍀 今日好运连连！",
                    "✨ 幸运值MAX！",
                    "🌟 今天也是幸运的一天！",
                    "🎊 恭喜获得额外奖励！",
                    "🎁 幸运女神眷顾着你！"
                ]
            }
        }
    
    def init_database(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 签到记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sign_in_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    sign_date DATE NOT NULL,
                    points_earned INTEGER DEFAULT 0,
                    consecutive_days INTEGER DEFAULT 1,
                    total_points INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, group_id, sign_date)
                )
            ''')
            
            # 用户积分表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    total_points INTEGER DEFAULT 0,
                    consecutive_days INTEGER DEFAULT 0,
                    last_sign_date DATE,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, group_id)
                )
            ''')
            
            # 创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sign_date ON sign_in_records(sign_date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_group ON user_points(user_id, group_id)')
            
            conn.commit()
    
    def get_user_points(self, user_id, group_id):
        """获取用户当前积分"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT total_points, consecutive_days, last_sign_date 
            FROM user_points 
            WHERE user_id = ? AND group_id = ?
        ''', (user_id, group_id))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'total_points': result[0],
                'consecutive_days': result[1],
                'last_sign_date': result[2]
            }
        else:
            return {
                'total_points': 0,
                'consecutive_days': 0,
                'last_sign_date': None
            }
    
    def calculate_points(self, consecutive_days):
        """计算签到获得的积分"""
        points_config = self.config.get('points_config', {})
        feature_config = self.config.get('feature_config', {})
        
        # 基础积分
        base_points = points_config.get('base_points', 10)
        
        # 连续签到奖励
        bonus_points = 0
        if feature_config.get('enable_consecutive_bonus', True):
            consecutive_bonus = points_config.get('consecutive_bonus', 2)
            max_consecutive_bonus = points_config.get('max_consecutive_bonus', 50)
            bonus_points = min(consecutive_days * consecutive_bonus, max_consecutive_bonus)
        
        # 随机奖励（10%概率获得）
        random_bonus = 0
        extra_bonus = 0
        if feature_config.get('enable_random_bonus', True):
            random_bonus_probability = points_config.get('random_bonus_probability', 0.1)
            # 10%概率获得额外随机奖励
            if random.random() < random_bonus_probability:
                random_bonus_min = points_config.get('random_bonus_min', 1)
                random_bonus_max = points_config.get('random_bonus_max', 5)
                extra_bonus = random.randint(random_bonus_min, random_bonus_max)
            
            # 基础随机奖励（每次都获得）
            random_bonus_min = points_config.get('random_bonus_min', 1)
            random_bonus_max = points_config.get('random_bonus_max', 5)
            random_bonus = random.randint(random_bonus_min, random_bonus_max)
        
        total_points = base_points + bonus_points + random_bonus + extra_bonus
        return total_points, extra_bonus
    
    def is_root_user(self, user_id):
        """检查是否为root用户"""
        root_config = self.config.get('root_config', {})
        root_users = root_config.get('root_users', [])
        return str(user_id) in root_users
    
    def sign_in(self, user_id, group_id, user_name):
        """执行签到操作"""
        today = datetime.datetime.now().date()
        
        # 获取用户当前信息
        user_info = self.get_user_points(user_id, group_id)
        last_sign_date = user_info['last_sign_date']
        
        # 检查是否为root用户
        is_root = self.is_root_user(user_id)
        root_config = self.config.get('root_config', {})
        privileges = root_config.get('privileges', {})
        
        # 检查今天是否已经签到（root用户不受限制）
        if last_sign_date == str(today) and not (is_root and privileges.get('unlimited_sign_in', True)):
            return {
                'success': False,
                'message': f'❌ {user_name} 今天已经签到过了！',
                'current_points': user_info['total_points']
            }
        
        # 计算连续签到天数
        if last_sign_date:
            last_date = datetime.datetime.strptime(last_sign_date, '%Y-%m-%d').date()
            if today - last_date == timedelta(days=1):
                consecutive_days = user_info['consecutive_days'] + 1
            else:
                # root用户连续签到天数受保护
                if is_root and privileges.get('consecutive_days_protected', True):
                    consecutive_days = user_info['consecutive_days'] + 1
                else:
                    consecutive_days = 1
        else:
            consecutive_days = 1
        
        # 计算获得的积分（root用户与普通用户积分计算一致）
        points_earned, extra_bonus = self.calculate_points(consecutive_days)
        
        new_total_points = user_info['total_points'] + points_earned
        
        # 更新数据库
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 对于root用户，如果是同一天多次签到，先删除之前的记录
            if is_root and last_sign_date == str(today):
                cursor.execute('''
                    DELETE FROM sign_in_records 
                    WHERE user_id = ? AND group_id = ? AND sign_date = ?
                ''', (user_id, group_id, str(today)))
            
            # 插入签到记录
            cursor.execute('''
                INSERT INTO sign_in_records (user_id, group_id, sign_date, points_earned, consecutive_days, total_points)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, group_id, str(today), points_earned, consecutive_days, new_total_points))
            
            # 更新用户积分总表
            cursor.execute('''
                INSERT OR REPLACE INTO user_points (user_id, group_id, total_points, consecutive_days, last_sign_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, group_id, new_total_points, consecutive_days, str(today)))
            
            conn.commit()
            
            # 生成签到成功消息
            message = self.generate_success_message(user_name, points_earned, consecutive_days, new_total_points, user_id, extra_bonus)
            
            return {
                'success': True,
                'message': message,
                'points_earned': points_earned,
                'consecutive_days': consecutive_days,
                'total_points': new_total_points,
                'extra_bonus': extra_bonus
            }
            
        except Exception as e:
            conn.rollback()
            return {
                'success': False,
                'message': f'❌ 签到失败：{str(e)}',
                'current_points': user_info['total_points']
            }
        finally:
            conn.close()
    
    def generate_success_message(self, user_name, points_earned, consecutive_days, total_points, user_id=None, extra_bonus=0):
        """生成签到成功消息"""
        message_config = self.config.get('message_config', {})
        lucky_words = message_config.get('lucky_words', [
            '🍀 今日好运连连！',
            '✨ 幸运值MAX！',
            '🌟 今天也是幸运的一天！',
            '🎊 恭喜获得额外奖励！',
            '🎁 幸运女神眷顾着你！'
        ])
        
        # 检查是否为root用户
        is_root = user_id and self.is_root_user(user_id)
        root_config = self.config.get('root_config', {})
        privileges = root_config.get('privileges', {})
        
        # 检查是否有特殊日期奖励
        extra_message = self.check_special_date_bonus()
        
        # 获取用户等级信息
        level_info = self.get_level_info(total_points)
        
        # 基础消息（root用户与普通用户消息格式一致，仅添加标识）
        messages = [
            f'🎉 {user_name} 签到成功！',
            f'      等级：{level_info["name"]}',
            f'💰 获得积分：+{points_earned}',
            f'📅 连续签到：{consecutive_days}天',
            f'      总积分：{total_points}'
        ]
        
        # 连续签到奖励提示
        if consecutive_days >= 30:
            messages.append('👑 签到王者！')
        elif consecutive_days >= 7:
            messages.append('🔥 连续签到达人！')
        
        # 额外随机奖励提示
        if extra_bonus > 0:
            messages.append(f'🎊 恭喜获得额外奖励！')
            messages.append(f'    +{extra_bonus}')
        else:
            # 随机幸运语（没有额外奖励时显示）
            messages.append(random.choice(lucky_words))
        
        if extra_message:
            messages.append(extra_message)
        
        return '\n'.join(messages)
    
    def check_special_date_bonus(self):
        """检查特殊日期奖励"""
        feature_config = self.config.get('feature_config', {})
        if not feature_config.get('enable_special_dates', True):
            return ""
        
        special_dates = self.config.get('special_dates', {})
        holidays = special_dates.get('holidays', {})
        
        today = datetime.datetime.now()
        today_str = today.strftime("%m-%d")
        
        if today_str in holidays:
            holiday_info = holidays[today_str]
            return holiday_info.get('message', '')
        
        return ""

    def get_level_info(self, total_points: int) -> Dict[str, str]:
        """根据积分获取等级信息"""
        feature_config = self.config.get('feature_config', {})
        if not feature_config.get('enable_level_system', True):
            return {"name": "用户", "icon": "👤"}
        
        level_config = self.config.get('level_config', {
            0: {"name": "新手", "icon": "🌱"},
            100: {"name": "学徒", "icon": "⭐"},
            500: {"name": "达人", "icon": "🎯"},
            1000: {"name": "专家", "icon": "🏆"},
            2000: {"name": "大师", "icon": "👑"},
            5000: {"name": "传奇", "icon": "💎"}
        })
        
        # 找到适合的等级
        current_level = {"name": "新手", "icon": "🌱"}
        for points_threshold in sorted(level_config.keys()):
            if total_points >= points_threshold:
                current_level = level_config[points_threshold]
        
        return current_level
    
    def get_ranking(self, group_id, limit=10):
        """获取群内积分排行榜"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, total_points, consecutive_days, last_sign_date
            FROM user_points
            WHERE group_id = ?
            ORDER BY total_points DESC, consecutive_days DESC
            LIMIT ?
        ''', (group_id, limit))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
    
    def clear_user_points(self, operator_user_id: str, target_user_id: str, target_user_name: str, group_id: str) -> Dict[str, any]:
        """清空用户积分（仅root用户可用）"""
        # 检查操作者是否为root用户
        if not self.is_root_user(operator_user_id):
            return {
                'success': False,
                'message': '❌ 权限不足：只有root用户才能清空积分！'
            }
        
        # 获取目标用户当前信息
        user_info = self.get_user_points(target_user_id, group_id)
        original_points = user_info['total_points']
        
        if original_points == 0:
            return {
                'success': False,
                'message': f'❌ {target_user_name} 的积分已经是0了，无需清空！'
            }
        
        # 清空积分
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 更新用户积分总表
            cursor.execute('''
                UPDATE user_points 
                SET total_points = 0, consecutive_days = 0, last_sign_date = NULL
                WHERE user_id = ? AND group_id = ?
            ''', (target_user_id, group_id))
            
            # 删除该用户的所有签到记录
            cursor.execute('''
                DELETE FROM sign_in_records 
                WHERE user_id = ? AND group_id = ?
            ''', (target_user_id, group_id))
            
            conn.commit()
            
            # 判断是清空自己还是他人
            if operator_user_id == target_user_id:
                message = f'✅ 成功清空自己的积分！（原积分：{original_points}）'
            else:
                message = f'✅ 成功清空 {target_user_name} 的积分！（原积分：{original_points}）'
            
            return {
                'success': True,
                'message': message,
                'cleared_points': original_points
            }
            
        except Exception as e:
            conn.rollback()
            return {
                'success': False,
                'message': f'❌ 清空积分失败：{str(e)}'
            }
        finally:
            conn.close()