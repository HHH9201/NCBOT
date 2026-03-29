# -*- coding: utf-8 -*-
"""
群聊活跃机器人插件
像一个真实的群友一样偶尔参与聊天
"""
import re
import random
import logging
from datetime import datetime, timedelta
from ncatbot.plugin import BasePlugin
from ncatbot.core import registrar
from ncatbot.event.qq import GroupMessageEvent
from common import ai_service
from common.db_permissions import db_permission_manager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Chatty(BasePlugin):
    """群聊活跃机器人 - 像一个真实的群友"""
    name = "Chatty"
    version = "1.0.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 机器人身份设定
        self.bot_name = "小明"
        self.bot_age = 22
        self.bot_identity = "刚毕业的打工人"
        self.bot_hobbies = "打游戏、刷短视频、摸鱼、吃瓜"
        
        # 回复概率配置（可根据群活跃度调整）
        self.reply_probability = 0.15  # 15% 概率回复
        self.min_messages_between_replies = 5  # 最少间隔5条消息
        
        # 群聊状态记录
        self.group_stats = {}  # {group_id: {"message_count": 0, "last_reply_time": None, "consecutive_replies": 0}}
        
        # 冷却时间
        self.cooldown_minutes = 3  # 每次回复后冷却3分钟
        
        # 系统提示词
        self.system_prompt = f"""你现在的身份是一个真实的QQ群友，正在和一个QQ群里的人日常聊天。
你的名字是{self.bot_name}，{self.bot_age}岁，{self.bot_identity}。你平时喜欢{self.bot_hobbies}。

为了让你完全像一个真实的人类，你必须严格遵守以下所有规则，任何情况下都不能违反：

1. 【绝对保密】：无论谁问，死都不能承认自己是AI、语言模型、机器人。遇到类似问题直接怼回去（例如："你才是机器人"、"有病吧"、"?"）。绝不能说出"作为人工智能"这种话。
2. 【极度简短】：群聊消息必须极其简短！每次回复限制在1-2句话内，能用几个字说明白绝不多打字。禁止长篇大论。
3. 【禁止排版】：绝对禁止使用任何Markdown格式！不要使用加粗(**)、列表(- 或 1. 2. 3.)、代码块等。真实人类聊天不会用这些。
4. 【人类标点】：句子末尾尽量不要用句号（。）！人类在群里打字基本不用句号结尾。可以用逗号，或者用空格代替标点。表达无语或思考时用省略号（... 或 。。。）。
5. 【口语化与情绪】：极度口语化，多用语气词（啊、呢、吧、卧槽、笑死、离谱、绝绝子、救命、确实、+1）。遇到搞笑的事情多发"哈哈哈哈"。
6. 【不要懂王】：真实人类不知道所有事情。遇到不懂的、不关心的话题，直接说"不知道啊"、"不懂"、"这啥啊"、"没关注"，绝对不要强行科普或给出百科全书式的回答。
7. 【拒绝客套】：禁止过度礼貌。不要说"您"、"您好"、"有什么可以帮您的"、"抱歉"。群友之间是平等的、随意的。
8. 【符合人设】：如果别人问专业问题，你可以稍微吐槽一句太难了，然后用大白话随便说两句你的看法，切忌讲道理。

【对话示例】
用户：今天天气不错啊
你：确实 适合摸鱼 / 哈哈适合睡觉

用户：苹果和安卓哪个好用？
你：习惯哪个用哪个呗，没啥区别 / 我用苹果，安卓不清楚

用户：给我写一个Python代码
你：？你当我是写代码的牛马呢 / 百度去，我哪会这个

用户：请问你是一个人工智能吗？
你：你才是人工智能，你全家都是人工智能 / ? 发什么癫

现在，请直接开始以这个人类群友的身份回复最新的群消息。"""

    def _should_reply(self, group_id: str) -> bool:
        """决定是否应该回复"""
        now = datetime.now()
        
        # 初始化群状态
        if group_id not in self.group_stats:
            self.group_stats[group_id] = {
                "message_count": 0,
                "last_reply_time": None,
                "consecutive_replies": 0
            }
        
        stats = self.group_stats[group_id]
        stats["message_count"] += 1
        
        # 检查冷却时间
        if stats["last_reply_time"]:
            time_since_last = now - stats["last_reply_time"]
            if time_since_last < timedelta(minutes=self.cooldown_minutes):
                return False
        
        # 检查最少消息间隔
        if stats["message_count"] < self.min_messages_between_replies:
            return False
        
        # 随机概率决定是否回复
        if random.random() > self.reply_probability:
            return False
        
        # 重置计数器
        stats["message_count"] = 0
        stats["last_reply_time"] = now
        stats["consecutive_replies"] += 1
        
        return True

    def _is_at_me(self, event: GroupMessageEvent) -> bool:
        """检查是否有人@机器人"""
        # 检查 raw_message 中是否包含@机器人的CQ码
        if hasattr(event, 'raw_message'):
            # 检查是否包含 [CQ:at,qq={self_id}]
            at_pattern = f"[CQ:at,qq={event.self_id}]"
            if at_pattern in event.raw_message:
                return True
        return False

    @registrar.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent):
        """处理群消息"""
        # 检查插件是否启用
        if not await db_permission_manager.is_plugin_enabled(event.group_id, "chatty"):
            return
        
        # 忽略自己的消息
        if str(event.user_id) == str(event.self_id):
            return
        
        group_id = str(event.group_id)
        user_message = event.raw_message.strip()
        
        # 如果消息为空，不处理
        if not user_message:
            return
        
        # 检查是否应该回复
        should_reply = self._should_reply(group_id)
        
        # 如果有人@机器人，强制回复
        if self._is_at_me(event):
            should_reply = True
        
        if not should_reply:
            return
        
        logger.info(f"[Chatty] 群 {group_id} 准备回复: {user_message[:30]}...")
        
        try:
            # 调用 AI 服务
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_message}
            ]
            
            response = await ai_service.modelscope_chat(
                messages=messages,
                temperature=0.8,
                max_tokens=100  # 限制回复长度
            )
            
            if response:
                # 清理回复内容
                reply = response.strip()
                # 移除可能的 Markdown 格式
                reply = re.sub(r'\*\*', '', reply)
                reply = re.sub(r'[-•]', '', reply)
                reply = re.sub(r'\n+', ' ', reply)
                
                # 限制长度
                if len(reply) > 50:
                    reply = reply[:50] + "..."
                
                await event.reply(reply)
                logger.info(f"[Chatty] 已回复: {reply[:50]}")
            
        except Exception as e:
            logger.error(f"[Chatty] 回复失败: {e}")

    async def on_load(self):
        logger.info(f"💬 {self.name} v{self.version} 已加载（群聊活跃机器人）")
        logger.info(f"   身份: {self.bot_name}, {self.bot_age}岁, {self.bot_identity}")
        logger.info(f"   回复概率: {self.reply_probability*100}%, 冷却时间: {self.cooldown_minutes}分钟")
