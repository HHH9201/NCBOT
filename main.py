

import os
import logging
import re

# ========= 导入必要模块 ==========
from ncatbot.core import BotClient, GroupMessage, PrivateMessage

# ========== 创建 BotClient ==========
bot = BotClient()

# ========== 配置日志等级 ==========
# 设置环境变量来配置日志等级
os.environ['LOG_LEVEL'] = 'DEBUG'
os.environ['FILE_LOG_LEVEL'] = 'DEBUG'

# 目标群组ID
TARGET_GROUP_ID = "695934967"

# 自定义日志过滤器 - 过滤掉其他群组的日志和框架噪音
class GroupLogFilter(logging.Filter):
    def filter(self, record):
        # 检查日志消息是否包含群组信息
        log_message = record.getMessage()
        
        # 如果日志包含群组ID，检查是否是目标群组
        if "group_id" in log_message.lower():
            # 使用正则表达式提取群组ID
            group_match = re.search(r"group_id['\"]?\s*[:=]\s*(\d+)", log_message)
            if group_match:
                group_id = group_match.group(1)
                # 只记录目标群组的日志
                return group_id == TARGET_GROUP_ID
        
        # 过滤掉框架级别的噪音日志
        noise_patterns = [
            'looping',
            '已发布事件',
            'heartbeat',
            'meta_event',
            'status',
            'interval',
            'post_type',
            'self_id',
            '命令前缀集合',
            'ncatbot.group_message_event',
            'ncatbot.heartbeat_event',
            'ncatbot.startup_event'
        ]
        
        # 如果日志包含噪音关键词，过滤掉
        for pattern in noise_patterns:
            if pattern in log_message.lower():
                return False
        
        # 对于不包含群组信息和噪音的日志，全部记录
        return True

# 配置Python日志记录器
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 为所有日志记录器添加过滤器
for handler in logging.getLogger().handlers:
    handler.addFilter(GroupLogFilter())

# ========= 注册回调函数 ==========
@bot.group_event()
async def on_group_message(msg: GroupMessage):
    # 在事件处理的最开始就进行群组过滤
    # 只处理指定群组695934967的消息，其他群组直接返回
    if str(msg.group_id) != TARGET_GROUP_ID:
        # 不记录任何日志，完全忽略其他群组的消息
        return
    
    logger.debug(f"收到目标群组 {msg.group_id} 的消息: {msg.raw_message}")
    
    if msg.raw_message == "测试":
        await msg.reply(text="NcatBot 测试成功喵~")

@bot.private_event()
async def on_private_message(msg: PrivateMessage):
    if msg.raw_message == "测试":
        await bot.api.post_private_msg(msg.user_id, text="NcatBot 测试成功喵~")

# ========== 启动 BotClient ==========
if __name__ == "__main__":
    # 启动Bot
    bot.run(bt_uin="58805194", enable_webui_interaction=False)