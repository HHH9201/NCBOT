# 真人群聊AI插件 - 模仿真人聊天行为的AI插件
import asyncio
import httpx
import time
import re
import random
from typing import Dict, List
from datetime import datetime
from ncatbot.plugin import BasePlugin, CompatibleEnrollment as bot
from ncatbot.core.message import GroupMessage
from ncatbot.core.message import MessageChain
from ncatbot.core.event.message_segment.message_segment import Text, Reply
from ncatbot.utils import get_log

_log = get_log(); _log.setLevel('INFO')

class RealPersonAI(BasePlugin):
    name, version = "RealPersonAI", "1.0.0"
    
    # API配置 - 使用与GPT插件相同的配置
    API_KEY = "sk-kilwgyrrwhpzhqwvugdjliknqcuvvrdbmltlvythobukelfg"
    BASE_URL = "https://api.siliconflow.cn/v1"
    FALLBACK_API_KEY = API_KEY
    FALLBACK_BASE_URL = BASE_URL
    
    # 人格设定 - 更加贴近真人的设定
    PERSONALITIES = [
        "你是一个普通的大学生，性格活泼开朗，喜欢网上冲浪，说话比较随意但很有趣。你经常会用一些网络流行语和表情包。",
        "你是一个上班族，平时工作压力比较大，喜欢在群里吐槽和聊天。你说话比较成熟，但偶尔也会很幽默。",
        "你是一个二次元爱好者，喜欢看动漫和玩游戏。你说话会带一些二次元梗，但并不过度中二。",
        "你是一个技术宅，对电脑和手机很了解。你喜欢分享一些实用的小技巧，说话比较理性但也很友善。",
        "你是一个文艺青年，喜欢看书、听音乐、看电影。你说话比较有深度，但并不会让人觉得装。"
    ]
    
    # 触发关键词 - 让AI更自然地参与对话
    TRIGGER_KEYWORDS = [
        "哈哈哈", "笑死", "真的假的", "不会吧", "太真实了", "我也是", "同意", "确实",
        "游戏", "动漫", "电影", "音乐", "学习", "工作", "生活", "感情", "天气", "吃饭"
    ]
    
    # 随机回复概率 (5%的概率主动回复)
    ACTIVE_REPLY_CHANCE = 0.05
    
    # 冷却时间 - 防止过于频繁回复
    COOLDOWN_TIME = 60  # 60秒内不重复回复
    
    # 存储用户会话和回复记录
    sessions: Dict[int, List[Dict]] = {}
    last_reply_time: Dict[int, float] = {}
    message_history: Dict[int, List[str]] = {}
    cache: Dict[str, str] = {}
    cache_time: Dict[str, float] = {}
    cache_timeout = 300
    
    # 当前使用的人格
    current_personality = None
    
    def __init__(self):
        super().__init__()
        # 随机选择一个人格
        self.current_personality = random.choice(self.PERSONALITIES)
        _log.info(f"[{self.name}] 当前人格: {self.current_personality[:50]}...")
    
    def trim(self, m: List[Dict]) -> List[Dict]: 
        return m[-15:]  # 保留最近15条消息
    
    def _clean_cache(self):
        now = time.time()
        for k in [k for k, t in self.cache_time.items() if now - t > self.cache_timeout]:
            self.cache.pop(k, None)
            self.cache_time.pop(k, None)
    
    def _should_active_reply(self, group_id: int, message: str) -> bool:
        """判断是否应该主动回复"""
        now = time.time()
        
        # 检查冷却时间
        if group_id in self.last_reply_time and now - self.last_reply_time[group_id] < self.COOLDOWN_TIME:
            return False
        
        # 检查是否包含触发关键词
        has_trigger = any(keyword in message for keyword in self.TRIGGER_KEYWORDS)
        
        # 随机概率触发
        random_trigger = random.random() < self.ACTIVE_REPLY_CHANCE
        
        # 如果有关键词或者随机触发，就回复
        return has_trigger or random_trigger
    
    def _add_realistic_elements(self, text: str) -> str:
        """添加真人聊天元素"""
        # 随机添加一些口语化表达
        expressions = ["哈哈", "emm", "嗯", "啊这", "233", "w", "hhh", "笑死"]
        
        # 随机添加一些网络用语
        netspeak = ["（笑）", "（狗头）", "（捂脸）", "（叹气）", "（思考）"]
        
        # 随机选择是否添加这些元素
        if random.random() < 0.3:  # 30%的概率添加
            if random.random() < 0.5:
                text += random.choice(expressions)
            else:
                text += random.choice(netspeak)
        
        # 随机替换一些词语为更口语化的表达
        replacements = {
            "是的": "嗯嗯",
            "好的": "ok",
            "可以": "行",
            "不知道": "不太清楚",
            "明白": "懂了"
        }
        
        for old, new in replacements.items():
            if random.random() < 0.2:  # 20%的概率替换
                text = text.replace(old, new)
        
        return text
    
    async def chat(self, text: str, uin=None, context="") -> str:
        """与AI对话"""
        key = f"{uin}_{text[:100]}" if uin else text[:100]
        if key in self.cache and time.time() - self.cache_time[key] < self.cache_timeout:
            _log.info(f"[{self.name}] 命中缓存")
            return self.cache[key]
        
        # 构建消息
        msgs = [{"role": "system", "content": self.current_personality}]
        
        # 添加上下文
        if context:
            msgs.append({"role": "user", "content": f"群聊上下文: {context}"})
        
        # 添加历史会话
        if uin and uin in self.sessions:
            msgs += self.sessions[uin][-8:]  # 保留最近8条
        
        msgs.append({"role": "user", "content": text})
        
        # 设置参数
        payload = {
            "model": "Qwen/Qwen3-30B-A3B-Instruct-2507", 
            "messages": msgs, 
            "max_tokens": 200,
            "temperature": 0.7,  # 稍微提高温度，让回复更自然
            "top_p": 0.9,
            "stream": False
        }
        
        # 尝试调用API
        for url, key, name in [(self.BASE_URL, self.API_KEY, "主API"),
                               (self.FALLBACK_BASE_URL, self.FALLBACK_API_KEY, "备用API")]:
            try:
                async with httpx.AsyncClient(follow_redirects=True) as cli:
                    r = await cli.post(f"{url}/chat/completions",
                                       headers={"Authorization": f"Bearer {key}",
                                                "Content-Type": "application/json"},
                                       json={"model": "Qwen/Qwen3-30B-A3B-Instruct-2507",
                                             **{k: v for k, v in payload.items() if k != "model"}},
                                       timeout=httpx.Timeout(connect=2, read=8, write=5, pool=2))
                    r.raise_for_status()
                    res = r.json()["choices"][0]["message"]["content"].strip()
                    
                    # 添加真人元素
                    res = self._add_realistic_elements(res)
                    
                    # 缓存结果
                    self.cache[key] = res
                    self.cache_time[key] = time.time()
                    if len(self.cache) % 10 == 0:
                        self._clean_cache()
                    
                    return res
            except Exception as e:
                _log.error(f"[{self.name}] {name} 失败: {e}")
        
        return "emm... 网络好像有点问题，稍后再说吧~"
    
    @bot.group_event
    async def on_group_event(self, msg: GroupMessage):
        """处理群消息"""
        txt = (msg.raw_message or "").strip()
        if not txt:
            return
        
        group_id = msg.group_id
        user_id = msg.sender.user_id
        
        # 记录消息历史
        if group_id not in self.message_history:
            self.message_history[group_id] = []
        
        self.message_history[group_id].append(f"{msg.sender.nickname}: {txt}")
        
        # 只保留最近10条消息作为上下文
        if len(self.message_history[group_id]) > 10:
            self.message_history[group_id] = self.message_history[group_id][-10:]
        
        # 检查是否需要主动回复
        if self._should_active_reply(group_id, txt):
            # 构建上下文
            context = "\\n".join(self.message_history[group_id][-3:])  # 最近3条消息
            
            try:
                # 生成回复
                reply_text = await self.chat(txt, user_id, context)
                
                # 更新会话记录
                self.sessions.setdefault(user_id, [])
                self.sessions[user_id] += [{"role": "user", "content": txt}, 
                                         {"role": "assistant", "content": reply_text}]
                self.sessions[user_id] = self.trim(self.sessions[user_id])
                
                # 更新最后回复时间
                self.last_reply_time[group_id] = time.time()
                
                # 随机决定是否使用引用回复
                if random.random() < 0.3:  # 30%概率引用回复
                    await self.api.post_group_msg(
                        group_id=group_id,
                        rtf=MessageChain([Reply(msg.message_id), Text(reply_text)])
                    )
                else:
                    await self.api.post_group_msg(
                        group_id=group_id,
                        rtf=MessageChain([Text(reply_text)])
                    )
                
                _log.info(f"[{self.name}] 主动回复群{group_id}: {reply_text[:50]}...")
                
            except Exception as e:
                _log.error(f"[{self.name}] 回复失败: {e}")
    
    async def on_load(self): 
        _log.info(f"[{self.name}] 插件已加载 {self.version}")
        _log.info(f"[{self.name}] 当前人格: {self.current_personality[:50]}...")
        _log.info(f"[{self.name}] 主动回复概率: {self.ACTIVE_REPLY_CHANCE * 100}%")
        _log.info(f"[{self.name}] 冷却时间: {self.COOLDOWN_TIME}秒")
    
    async def _unload_(self): 
        _log.info(f"[{self.name}] 插件卸载完成")