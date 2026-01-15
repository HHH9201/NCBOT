# -*- coding: utf-8 -*-
"""
每日定时任务模块
功能：每天0点自动发送昨日发言排行榜
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from ncatbot.core.api import BotAPI
from common.db import db_manager

_log = logging.getLogger(__name__)


class DailyTaskManager:
    """每日任务管理器"""
    
    def __init__(self, plugin_instance):
        self.plugin = plugin_instance
        self.bot_api: Optional[BotAPI] = None
        self._task = None
        self._running = False
    
    def set_bot_api(self, bot_api: BotAPI):
        """设置BotAPI实例"""
        self.bot_api = bot_api
    
    async def start_daily_task(self):
        """启动每日定时任务"""
        if self._running:
            _log.warning("[DailyTask] 每日任务已在运行中")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._daily_routine())
        _log.info("[DailyTask] 每日定时任务已启动")
    
    async def stop_daily_task(self):
        """停止每日定时任务"""
        if not self._running:
            return
        
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        _log.info("[DailyTask] 每日定时任务已停止")
    
    async def _daily_routine(self):
        """每日例行任务"""
        while self._running:
            try:
                # 计算到下一个0点的时间
                now = datetime.now()
                next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                wait_seconds = (next_midnight - now).total_seconds()
                
                _log.info(f"[DailyTask] 等待 {wait_seconds} 秒到下一个0点")
                await asyncio.sleep(wait_seconds)
                
                # 发送昨日排行榜
                await self._send_yesterday_rankings()
                
            except asyncio.CancelledError:
                _log.info("[DailyTask] 每日任务被取消")
                break
            except Exception as e:
                _log.error(f"[DailyTask] 每日任务执行失败: {e}")
                # 出错后等待1小时再试
                await asyncio.sleep(3600)
    
    async def _send_yesterday_rankings(self):
        """发送昨日发言排行榜"""
        try:
            if not self.bot_api:
                _log.error("[DailyTask] BotAPI未设置，无法发送消息")
                return
            
            # 获取所有有数据的群组
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT DISTINCT group_id FROM daily_speak_rank')
                group_ids = [row[0] for row in cursor.fetchall()]
            
            _log.info(f"[DailyTask] 开始发送昨日排行榜，共 {len(group_ids)} 个群组")
            
            # 为每个群组发送昨日排行榜
            for group_id in group_ids:
                try:
                    ranking_text = self.plugin._format_ranking(group_id, "yesterday")
                    
                    # 智能发送消息
                    await napcat_service.smart_send_group_msg(
                        group_id,
                        ranking_text,
                        self.bot_api
                    )
                    
                    # 避免发送太快
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    _log.error(f"[DailyTask] 发送群 {group_id} 排行榜失败: {e}")
            
            _log.info("[DailyTask] 昨日排行榜发送完成")
            
        except Exception as e:
            _log.error(f"[DailyTask] 发送昨日排行榜失败: {e}")
    
    async def test_send_ranking(self, group_id: str):
        """测试发送昨日排行榜（用于手动测试）"""
        try:
            if not self.bot_api:
                _log.error("[DailyTask] BotAPI未设置，无法发送消息")
                return False
            
            ranking_text = self.plugin._format_ranking(group_id, "yesterday")
            
            await self.bot_api.send_group_msg(
                group_id=int(group_id),
                message=ranking_text
            )
            
            _log.info(f"[DailyTask] 测试发送群{group_id}昨日排行榜成功")
            return True
            
        except Exception as e:
            _log.error(f"[DailyTask] 测试发送群{group_id}昨日排行榜失败: {e}")
            return False