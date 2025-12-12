

# ========= 设置日志环境变量 ==========
import os
import logging
# 设置终端日志级别为DEBUG，确保能看到所有日志
os.environ["LOG_LEVEL"] = "DEBUG"
# 设置文件日志级别为DEBUG
os.environ["FILE_LOG_LEVEL"] = "DEBUG"
# 设置自定义日志格式，保留颜色支持，显示详细日志信息
os.environ["LOG_FORMAT"] = "\033[36m[%(asctime)s.%(msecs)03d]\033[0m \033[32m%(levelname)-8s\033[0m \033[35m%(name)s\033[0m \033[33m%(filename)s:%(lineno)d\033[0m ➜ %(message)s"


# ========= 自定义日志过滤器 ==========
class QQFilter(logging.Filter):
    def __init__(self, allowed_qqs=None, allowed_groups=None):
        super().__init__()
        self.allowed_qqs = set(allowed_qqs) if allowed_qqs else set()
        self.allowed_groups = set(allowed_groups) if allowed_groups else set()
    
    def filter(self, record):
        # 获取日志消息
        msg = record.getMessage()
        
        # 过滤掉特定的日志消息
        if "命令前缀集合" in msg:
            return False
        if "用户发言达" in msg and "自动保存" in msg:
            return False
        if "SpeakRank" in record.name:
            return False
        
        # 允许所有其他日志
        return True


# ========= 导入必要模块 ==========
from ncatbot.core import BotClient, GroupMessage, PrivateMessage
from ncatbot.utils import get_log



# ========== 创建 BotClient ==========
bot = BotClient()
_log = get_log()

# ========= 注册回调函数 ==========
@bot.group_event()
async def on_group_message(msg: GroupMessage):
    if msg.raw_message == "测试":
        await msg.reply(text="NcatBot 测试成功喵~")

@bot.private_event()
async def on_private_message(msg: PrivateMessage):
    if msg.raw_message == "测试":
        await bot.api.post_private_msg(msg.user_id, text="NcatBot 测试成功喵~")

# ========== 启动 BotClient ==========
if __name__ == "__main__":
    # 配置日志过滤器
    root_logger = logging.getLogger()
    
    # 创建过滤器实例
    qq_filter = QQFilter()
    
    # 移除所有现有的StreamHandler，重新添加带过滤器的
    for handler in root_logger.handlers[:]:
        if isinstance(handler, logging.StreamHandler):
            root_logger.removeHandler(handler)
    
    # 添加带过滤器的StreamHandler，设置日志级别为DEBUG
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)  # 设置为DEBUG级别，确保能看到所有日志
    ch.addFilter(qq_filter)  # 使用addFilter而不是setFilter
    
    # 保持原有的日志格式
    formatter = logging.Formatter(os.environ["LOG_FORMAT"], datefmt="%H:%M:%S")
    ch.setFormatter(formatter)
    
    root_logger.addHandler(ch)
    
    # 启动Bot
    bot.run(bt_uin="58805194", enable_webui_interaction=False)