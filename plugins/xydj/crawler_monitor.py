import json
import os
import asyncio
import sys
from datetime import datetime
from typing import Optional
from ncatbot.plugin import NcatBotPlugin
from ncatbot.core.logger import logger

sys.path.insert(0, "/www/wwwroot/WxTool/crawler")

try:
    from crawler_status import get_pending_notification, mark_as_notified, STATUS_FILE
    HAS_CRAWLER_STATUS = True
except ImportError:
    HAS_CRAWLER_STATUS = False
    STATUS_FILE = "/www/wwwroot/WxTool/crawler/logs/crawler_status.json"

MONITOR_GROUP_ID = "695934967"

class CrawlerMonitorPlugin(NcatBotPlugin):
    def __init__(self):
        super().__init__(
            name="crawler_monitor",
            description="爬虫执行监控",
            version="1.0.0",
            author="System"
        )
        self.monitor_task = None
        self.running = False

    async def on_load(self):
        logger.info(f"[Crawler Monitor] 插件已加载，监控群: {MONITOR_GROUP_ID}")
        self.running = True
        self.monitor_task = asyncio.create_task(self.monitor_loop())

    async def on_unload(self):
        self.running = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("[Crawler Monitor] 插件已卸载")

    async def monitor_loop(self):
        """持续监控爬虫状态文件"""
        logger.info("[Crawler Monitor] 监控循环已启动")
        while self.running:
            try:
                await asyncio.sleep(10)
                if not HAS_CRAWLER_STATUS:
                    continue
                notification = get_pending_notification()
                if notification:
                    logger.info(f"[Crawler Monitor] 发现待通知: {notification}")
                    await self.send_notification(notification)
                    mark_as_notified()
                    logger.info(f"[Crawler Monitor] 通知已发送并标记")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Crawler Monitor] 监控异常: {e}")
                import traceback
                traceback.print_exc()

    async def send_notification(self, notification: dict):
        """发送通知到指定群"""
        try:
            crawler_name = notification.get("crawler_name", "未知")
            success = notification.get("success", False)
            message = notification.get("message", "")
            updated_count = notification.get("updated_count", 0)
            new_count = notification.get("new_count", 0)
            timestamp = notification.get("timestamp", "")

            if success:
                emoji = "✅"
                title = f"{emoji} 【{crawler_name}】执行成功"
            else:
                emoji = "❌"
                title = f"{emoji} 【{crawler_name}】执行失败"

            lines = [title]
            lines.append("─" * 30)
            lines.append(f"📝 状态: {'成功' if success else '失败'}")
            lines.append(f"📄 详情: {message}")
            
            if updated_count > 0 or new_count > 0:
                lines.append(f"📊 统计: 更新 {updated_count} 条, 新增 {new_count} 条")
            
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    time_str = timestamp
                lines.append(f"⏰ 时间: {time_str}")

            full_message = "\n".join(lines)

            try:
                await self.api.qq.send_group_text(MONITOR_GROUP_ID, full_message)
                logger.info(f"[Crawler Monitor] 已发送通知到群 {MONITOR_GROUP_ID}")
            except Exception as e:
                logger.error(f"[Crawler Monitor] 发送通知失败: {e}")
                import traceback
                traceback.print_exc()
        except Exception as e:
            logger.error(f"[Crawler Monitor] 构建通知失败: {e}")
            import traceback
            traceback.print_exc()

plugin = CrawlerMonitorPlugin()
