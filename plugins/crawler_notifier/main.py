import os
import json
import asyncio
import logging
from ncatbot.plugin import BasePlugin
from ncatbot.types import PlainText, MessageArray

# 设置日志
logger = logging.getLogger("crawler_notifier")

# 爬虫状态文件路径
STATUS_FILE = "/www/wwwroot/Game-crawler/logs/crawler_status.json"
# 默认通知群号
DEFAULT_GROUP_ID = "695934967"

class CrawlerNotifierPlugin(BasePlugin):
    name = "crawler_notifier"
    version = "1.0.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.running = True
        self.task = None

    async def on_load(self):
        logger.info(f"[{self.name}] 插件已加载，开始后台监控...")
        # 启动后台轮询任务
        self.task = asyncio.create_task(self.monitor_crawler_status())

    async def on_unload(self):
        self.running = False
        if self.task:
            self.task.cancel()
        logger.info(f"[{self.name}] 插件已卸载")

    async def monitor_crawler_status(self):
        """监控爬虫状态文件并发送通知"""
        while self.running:
            try:
                if os.path.exists(STATUS_FILE):
                    with open(STATUS_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    # 检查是否有待通知的结果
                    if not data.get("notified", False):
                        message = data.get("message", "爬虫任务已结束")
                        crawler_name = data.get("crawler_name", "未知爬虫")
                        success = data.get("success", True)
                        
                        status_str = "✅ 任务完成" if success else "🚨 紧急报警 (脚本已停止)"
                        
                        # 如果是 Cookie 问题，增加高亮提醒
                        alert_prefix = ""
                        if "Cookie" in message or "验证" in message:
                            alert_prefix = "⚠️ 【重要】检测到 Cookie 过期或触发验证，爬虫已自动熔断！\n\n"
                        
                        notify_text = f"📢 【爬虫任务通知】\n🔍 任务：{crawler_name}\n📊 状态：{status_str}\n{alert_prefix}📝 结果：{message}"
                        
                        # 发送群消息
                        logger.info(f"正在发送爬虫通知: {message}")
                        await self.api.qq.post_group_msg(
                            group_id=DEFAULT_GROUP_ID,
                            rtf=MessageArray([PlainText(text=notify_text)])
                        )
                        
                        # 标记为已通知
                        data["notified"] = True
                        with open(STATUS_FILE, "w", encoding="utf-8") as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                        
            except Exception as e:
                logger.error(f"监控爬虫状态出错: {e}")
            
            # 每 10 秒检查一次
            await asyncio.sleep(10)
