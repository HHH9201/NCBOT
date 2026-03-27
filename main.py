# /home/hjh/BOT/NCBOT/main.py
"""
NcatBot 5.x 主入口文件
"""
import os
import logging

from ncatbot.app import BotClient

# ========== 配置日志等级 ==========
os.environ['LOG_LEVEL'] = 'DEBUG'
os.environ['FILE_LOG_LEVEL'] = 'DEBUG'

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== 创建 BotClient ==========
bot = BotClient()

# ========== 启动 BotClient ==========
if __name__ == "__main__":
    bot.run()
