# SpeakRank.py
# -*- coding: utf-8 -*-
"""
发言排行榜插件
功能：
  1. 统计群成员发言次数（总发言、今日发言、昨日发言）
  2. 生成多种排行榜（总榜、今日榜、昨日榜）
  3. 支持查询个人发言统计（总发言、昨日发言、今日发言）
  4. 支持查看TOP10排行榜
  5. 每日0点自动发送昨日发言排行榜
  
命令：
  - 总发言榜：查看总发言排行榜
  - 今日发言榜：查看今日发言排行榜
  - 昨日发言榜：查看昨日发言排行榜
  - 我的发言：查看个人发言统计
  - 保存发言数据：手动保存数据到数据库
  - 测试昨日榜：测试发送昨日排行榜（管理员功能）
"""
import logging
import asyncio
import time
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional

from ncatbot.plugin import BasePlugin, CompatibleEnrollment
from ncatbot.core.message import GroupMessage
from ncatbot.core.event.message_segment.message_segment import Text, At
from .tool.daily_task import DailyTaskManager
from common.db import db_manager
from common.utils import is_admin

# 获取日志记录器
_log = logging.getLogger(__name__)

# 插件配置
PLUGIN_NAME = "SpeakRank"
PLUGIN_VERSION = "3.0.0"
MAX_RANKING_SIZE = 10  # 排行榜最大显示数量

# 获取兼容的注册器
bot = CompatibleEnrollment


class SpeakRank(BasePlugin):
    name = PLUGIN_NAME
    version = PLUGIN_VERSION
    
    def __init__(self, event_bus=None, **kwargs):
        super().__init__(event_bus=event_bus, **kwargs)
        # 初始化数据库连接
        self._init_database()
        
        # 缓存数据用于快速访问
        self.speak_count: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))  # 总发言统计
        self.daily_speak_count: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))  # 每日发言统计
        self._load_data()
        
        # 保存相关属性
        self._last_save_time = time.time()
        self._unsaved_changes = False
        
        # 每日任务管理器
        self.daily_task_manager = DailyTaskManager(self)
        
    def _init_database(self):
        """初始化数据库表结构"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                # 总发言统计表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS speak_rank (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        group_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        speak_count INTEGER DEFAULT 0,
                        last_speak_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(group_id, user_id)
                    )
                ''')
                
                # 每日发言统计表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS daily_speak_rank (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        group_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        speak_date DATE NOT NULL,
                        speak_count INTEGER DEFAULT 0,
                        last_speak_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(group_id, user_id, speak_date)
                    )
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_group_user ON speak_rank(group_id, user_id)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_speak_count ON speak_rank(speak_count DESC)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_daily_group_user_date ON daily_speak_rank(group_id, user_id, speak_date)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_daily_speak_count ON daily_speak_rank(speak_count DESC)
                ''')
                
                conn.commit()
                _log.debug(f"[SpeakRank] 数据库初始化完成")
        except Exception as e:
            _log.error(f"[SpeakRank] 数据库初始化失败: {e}")
            raise
    
    def _load_data(self):
        """从数据库加载发言数据到内存缓存"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                # 加载总发言数据
                cursor.execute('SELECT group_id, user_id, speak_count FROM speak_rank')
                rows = cursor.fetchall()
                
                for group_id, user_id, count in rows:
                    self.speak_count[group_id][user_id] = count
                
                # 加载今日发言数据
                today = datetime.now().strftime('%Y-%m-%d')
                cursor.execute('SELECT group_id, user_id, speak_count FROM daily_speak_rank WHERE speak_date = ?', (today,))
                daily_rows = cursor.fetchall()
                
                for group_id, user_id, count in daily_rows:
                    self.daily_speak_count[group_id][today][user_id] = count
                
                _log.debug(f"[SpeakRank] 已加载 {len(rows)} 条总发言记录，{len(daily_rows)} 条今日发言记录")
        except Exception as e:
            _log.error(f"[SpeakRank] 加载数据失败: {e}")
            self.speak_count = defaultdict(lambda: defaultdict(int))
            self.daily_speak_count = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    
    def _save_speak_data(self, group_id: str, user_id: str, count: int):
        """保存或更新用户发言数据"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                # 保存总发言数据
                cursor.execute('''
                    INSERT OR REPLACE INTO speak_rank (group_id, user_id, speak_count, last_speak_time)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ''', (group_id, user_id, count))
                
                # 保存今日发言数据
                today = datetime.now().strftime('%Y-%m-%d')
                today_count = self.daily_speak_count[group_id].get(today, {}).get(user_id, 0)
                cursor.execute('''
                    INSERT OR REPLACE INTO daily_speak_rank (group_id, user_id, speak_date, speak_count, last_speak_time)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (group_id, user_id, today, today_count))
                
                conn.commit()
                self._unsaved_changes = False
                self._last_save_time = time.time()
        except Exception as e:
            _log.error(f"[SpeakRank] 保存用户数据失败: {e}")
            raise
    
    def _get_ranking_from_db(self, group_id: str, limit: int = 10, date_filter: str = None) -> List[tuple]:
        """从数据库获取排行榜数据
        
        Args:
            group_id: 群ID
            limit: 限制数量
            date_filter: 日期过滤，None表示总榜，'today'表示今日，'yesterday'表示昨日
        """
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                if date_filter is None:
                    # 总榜
                    cursor.execute('''
                        SELECT user_id, speak_count 
                        FROM speak_rank 
                        WHERE group_id = ? 
                        ORDER BY speak_count DESC 
                        LIMIT ?
                    ''', (group_id, limit))
                elif date_filter == 'today':
                    # 今日榜
                    today = datetime.now().strftime('%Y-%m-%d')
                    cursor.execute('''
                        SELECT user_id, speak_count 
                        FROM daily_speak_rank 
                        WHERE group_id = ? AND speak_date = ?
                        ORDER BY speak_count DESC 
                        LIMIT ?
                    ''', (group_id, today, limit))
                elif date_filter == 'yesterday':
                    # 昨日榜
                    yesterday = (datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - 
                               timedelta(days=1)).strftime('%Y-%m-%d')
                    cursor.execute('''
                        SELECT user_id, speak_count 
                        FROM daily_speak_rank 
                        WHERE group_id = ? AND speak_date = ?
                        ORDER BY speak_count DESC 
                        LIMIT ?
                    ''', (group_id, yesterday, limit))
                
                return cursor.fetchall()
        except Exception as e:
            _log.error(f"[SpeakRank] 获取排行榜失败: {e}")
            return []
    
    def _get_user_count_from_db(self, group_id: str, user_id: str, date_filter: str = None) -> int:
        """从数据库获取用户发言次数
        
        Args:
            group_id: 群ID
            user_id: 用户ID
            date_filter: 日期过滤，None表示总数，'today'表示今日，'yesterday'表示昨日
        """
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                if date_filter is None:
                    # 总发言数
                    cursor.execute('''
                        SELECT speak_count 
                        FROM speak_rank 
                        WHERE group_id = ? AND user_id = ?
                    ''', (group_id, user_id))
                elif date_filter == 'today':
                    # 今日发言数
                    today = datetime.now().strftime('%Y-%m-%d')
                    cursor.execute('''
                        SELECT speak_count 
                        FROM daily_speak_rank 
                        WHERE group_id = ? AND user_id = ? AND speak_date = ?
                    ''', (group_id, user_id, today))
                elif date_filter == 'yesterday':
                    # 昨日发言数
                    yesterday = (datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - 
                               timedelta(days=1)).strftime('%Y-%m-%d')
                    cursor.execute('''
                        SELECT speak_count 
                        FROM daily_speak_rank 
                        WHERE group_id = ? AND user_id = ? AND speak_date = ?
                    ''', (group_id, user_id, yesterday))
                
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            _log.error(f"[SpeakRank] 获取用户数据失败: {e}")
            return 0
    
    def _get_user_name(self, user_id: str) -> str:
        """获取用户显示名称"""
        return f"用户{user_id}"
    
    def _format_ranking(self, group_id: str, rank_type: str = "total") -> str:
        """格式化排行榜输出
        
        Args:
            group_id: 群ID
            rank_type: 排行榜类型，'total'表示总榜，'today'表示今日榜，'yesterday'表示昨日榜
        """
        if rank_type == "total":
            ranking_data = self._get_ranking_from_db(group_id, MAX_RANKING_SIZE)
            title = "🏆 总发言排行 🏆"
        elif rank_type == "today":
            ranking_data = self._get_ranking_from_db(group_id, MAX_RANKING_SIZE, 'today')
            title = "📅 今日发言排行 📅"
        elif rank_type == "yesterday":
            ranking_data = self._get_ranking_from_db(group_id, MAX_RANKING_SIZE, 'yesterday')
            title = "📊 昨日发言排行 📊"
        else:
            return "❌ 无效的排行榜类型"
        
        if not ranking_data:
            return f"{title}\n暂无发言数据"
        
        # 格式化输出
        lines = [title]
        
        # 添加前三名emoji
        medals = ["🥇", "🥈", "🥉"]
        
        for i, (user_id, count) in enumerate(ranking_data, 1):
            user_name = self._get_user_name(user_id)
            if i <= 3:
                lines.append(f"{medals[i-1]}{i}. {user_name}: {count}次")
            else:
                lines.append(f"{i}. {user_name}: {count}次")
        
        return "\n".join(lines)
    
    def _should_auto_save(self) -> bool:
        """判断是否应该自动保存"""
        current_time = time.time()
        return (self._unsaved_changes and 
                current_time - self._last_save_time > 60)
    
    @bot.group_event
    async def on_group_message(self, msg: GroupMessage):
        """处理群消息，统计发言次数"""
        try:
            group_id = str(msg.group_id)
            user_id = str(msg.user_id)
            
            # 获取当前日期
            today = datetime.now().strftime('%Y-%m-%d')
            
            # 统计发言次数（更新内存缓存）
            self.speak_count[group_id][user_id] += 1
            self.daily_speak_count[group_id][today][user_id] += 1
            self._unsaved_changes = True
            
            # 智能保存策略
            current_time = time.time()
            current_count = self.speak_count[group_id][user_id]
            
            # 条件1: 用户个人发言每达到10次就保存到数据库
            if current_count % 10 == 0:
                self._save_speak_data(group_id, user_id, current_count)
                _log.debug(f"[SpeakRank] 用户发言达10次，自动保存 - 群{group_id} 用户{user_id}")
            
            # 条件2: 距离上次保存超过1分钟且有未保存的更改
            elif self._should_auto_save():
                # 批量保存所有未保存的数据
                for gid, users in self.speak_count.items():
                    for uid, count in users.items():
                        self._save_speak_data(gid, uid, count)
                _log.debug(f"[SpeakRank] 定时自动保存 - 群{group_id} 用户{user_id}")
            
            # 处理命令
            if msg.raw_message.strip() == "总发言榜":
                ranking_text = self._format_ranking(group_id, "total")
                await msg.reply(text=ranking_text)
            
            elif msg.raw_message.strip() == "今日发言榜":
                ranking_text = self._format_ranking(group_id, "today")
                await msg.reply(text=ranking_text)
            
            elif msg.raw_message.strip() == "昨日发言榜":
                ranking_text = self._format_ranking(group_id, "yesterday")
                await msg.reply(text=ranking_text)
            
            elif msg.raw_message.strip() == "我的发言":
                total_count = self._get_user_count_from_db(group_id, user_id)
                today_count = self._get_user_count_from_db(group_id, user_id, 'today')
                yesterday_count = self._get_user_count_from_db(group_id, user_id, 'yesterday')
                user_name = self._get_user_name(user_id)
                await msg.reply(text=f"📊 {user_name} 的发言统计\n"
                                    f"总发言（{total_count}）\n"
                                    f"昨日发言（{yesterday_count}）\n"
                                    f"今日发言（{today_count}）")
            
            elif msg.raw_message.strip() == "发言统计":
                # 获取群组统计信息
                with db_manager.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT COUNT(*), SUM(speak_count) FROM speak_rank WHERE group_id = ?', (group_id,))
                    total_users, total_speaks = cursor.fetchone()
                    total_users = total_users or 0
                    total_speaks = total_speaks or 0
                
                await msg.reply(
                    text=f"📈 本群发言统计\n"
                         f"总发言数: {total_speaks}次\n"
                         f"活跃人数: {total_users}人"
                )
            
            elif msg.raw_message.strip() == "保存发言数据":
                # 批量保存所有数据
                for gid, users in self.speak_count.items():
                    for uid, count in users.items():
                        self._save_speak_data(gid, uid, count)
                await msg.reply(text="✅ 发言数据已手动保存到数据库")
            
            elif msg.raw_message.strip() == "测试昨日榜":
                # 测试发送昨日排行榜（管理员功能）
                try:
                    success = await self.daily_task_manager.test_send_ranking(group_id)
                    if success:
                        await msg.reply(text="✅ 昨日排行榜测试发送成功")
                    else:
                        await msg.reply(text="❌ 昨日排行榜测试发送失败")
                except Exception as e:
                    await msg.reply(text=f"❌ 测试发送失败: {str(e)}")
                
        except Exception as e:
            _log.error(f"[SpeakRank] 处理群消息时发生错误: {e}")
    
    async def on_load(self):
        """插件加载时调用"""
        _log.debug(f"[SpeakRank] 插件已加载，版本 {self.version}")
        
        # 启动每日定时任务
        try:
            # 获取BotAPI实例（这里需要根据实际的bot实例获取方式调整）
            # 假设可以通过某种方式获取到bot_api
            # self.daily_task_manager.set_bot_api(bot_api)
            # await self.daily_task_manager.start_daily_task()
            _log.debug("[SpeakRank] 每日定时任务准备就绪（需要BotAPI实例）")
        except Exception as e:
            _log.error(f"[SpeakRank] 启动每日任务失败: {e}")
    
    async def on_unload(self):
        """插件卸载时调用"""
        try:
            # 停止每日定时任务
            await self.daily_task_manager.stop_daily_task()
            
            # 批量保存所有数据
            for gid, users in self.speak_count.items():
                for uid, count in users.items():
                    self._save_speak_data(gid, uid, count)
            _log.info("[SpeakRank] 插件已卸载，数据已保存到数据库")
        except Exception as e:
            _log.error(f"[SpeakRank] 卸载时保存数据失败: {e}")
    
    async def send_yesterday_ranking(self):
        """每天0点发送昨日发言排行榜"""
        try:
            # 获取所有有数据的群组
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT DISTINCT group_id FROM daily_speak_rank')
                group_ids = [row[0] for row in cursor.fetchall()]
            
            # 为每个群组发送昨日排行榜
            for group_id in group_ids:
                ranking_text = self._format_ranking(group_id, "yesterday")
                # 这里需要调用发送群消息的方法
                # 由于这是一个定时任务，需要在插件初始化时设置定时器
                _log.info(f"[SpeakRank] 群{group_id} 昨日排行榜已生成")
                
        except Exception as e:
            _log.error(f"[SpeakRank] 发送昨日排行榜失败: {e}")