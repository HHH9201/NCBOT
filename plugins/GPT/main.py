# GPT 插件 - 基于NcatBot框架的GPT对话插件
import asyncio, httpx, time, re
from typing import Dict, List
from ncatbot.plugin import BasePlugin, CompatibleEnrollment as bot
from ncatbot.core.message import GroupMessage, PrivateMessage
from ncatbot.core.message import MessageChain
from ncatbot.core.event.message_segment.message_segment import Text, Reply
from ncatbot.utils import get_log

_log = get_log(); _log.setLevel('INFO')

class GPT(BasePlugin):
    name, version = "GPT", "3.2.1"
    API_KEY = "sk-kilwgyrrwhpzhqwvugdjliknqcuvvrdbmltlvythobukelfg"
    BASE_URL = "https://api.siliconflow.cn/v1"
    FALLBACK_API_KEY = API_KEY
    FALLBACK_BASE_URL = BASE_URL
    SYSTEM = "你是一个智能群助手，全程只使用中文友好、简洁、快速、准确并且喜欢附带颜文字地回答用户的问题。"
    sessions: Dict[int, List[Dict]] = {}
    cache: Dict[str, str] = {}
    cache_time: Dict[str, float] = {}
    cache_timeout = 300
    bot_qq = "58805194"

    def trim(self, m: List[Dict]) -> List[Dict]: return m[-20:]
    def _clean_cache(self):
        now = time.time()
        for k in [k for k, t in self.cache_time.items() if now - t > self.cache_timeout]:
            self.cache.pop(k, None); self.cache_time.pop(k, None)

    async def chat(self, text: str, uin=None) -> str:
        key = f"{uin}_{text[:100]}" if uin else text[:100]
        if key in self.cache and time.time() - self.cache_time[key] < self.cache_timeout:
            _log.info(f"[{self.name}] 命中缓存"); return self.cache[key]
        msgs = [{"role": "system", "content": self.SYSTEM}]
        if uin and uin in self.sessions: msgs += self.sessions[uin][-4:]
        msgs.append({"role": "user", "content": text})
        payload = {"model": "Qwen/Qwen3-30B-A3B-Instruct-2507", "messages": msgs, "max_tokens": 256,
                   "temperature": .5, "top_p": .8, "stream": False}
        for url, key, name in [(self.BASE_URL, self.API_KEY, "MoonShot"),
                               (self.FALLBACK_BASE_URL, self.FALLBACK_API_KEY, "DeepSeek")]:
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
                    self.cache[key] = res; self.cache_time[key] = time.time()
                    if len(self.cache) % 10 == 0: self._clean_cache()
                    return res
            except Exception as e: _log.error(f"[{self.name}] {name} 失败: {e}")
        return "❌ GPT 调用失败，请稍后再试。"

    @bot.group_event
    async def on_group_event(self, msg: GroupMessage):
        txt = (msg.raw_message or "").strip()
        if not txt: return
        at_pattern = re.compile(rf"\[CQ:at,qq={self.bot_qq}\]", re.I)
        at_cnt = len(at_pattern.findall(txt))
        if at_cnt != 1: return
        uin = msg.sender.user_id
        self.sessions.setdefault(uin, [])
        try:
            reply = await self.chat(txt, uin)
            self.sessions[uin] += [{"role": "user", "content": txt}, {"role": "assistant", "content": reply}]
            self.sessions[uin] = self.trim(self.sessions[uin])
        except Exception as e: reply = f"处理错误: {e}"
        await self.api.post_group_msg(group_id=msg.group_id,
                                      rtf=MessageChain([Reply(msg.message_id), Text(reply)]))

    @bot.private_event
    async def on_private_event(self, msg: PrivateMessage):
        txt = (msg.raw_message or "").strip()
        if not txt: return
        uin = msg.sender.user_id
        self.sessions.setdefault(uin, [])
        try:
            reply = await self.chat(txt, uin)
            self.sessions[uin] += [{"role": "user", "content": txt}, {"role": "assistant", "content": reply}]
            self.sessions[uin] = self.trim(self.sessions[uin])
        except Exception as e: reply = f"处理错误: {e}"
        await self.api.post_private_msg(user_id=uin, rtf=MessageChain([Text(reply)]))

    async def on_load(self): _log.info(f"[{self.name}] 插件已加载 {self.version}")
    async def _unload_(self): _log.info(f"[{self.name}] 插件卸载完成")