# GPT 插件 - 基于NcatBot框架的GPT对话插件 (语音合成专用版)
import asyncio, httpx, time, re, base64
from typing import Dict, List
from pathlib import Path
import tempfile
import edge_tts
from ncatbot.plugin import BasePlugin, CompatibleEnrollment as bot
from ncatbot.core.message import GroupMessage, PrivateMessage
from ncatbot.core.message import MessageChain
from ncatbot.core.event.message_segment.message_segment import Text, Reply
from ncatbot.utils import get_log

_log = get_log(); _log.setLevel('INFO')

class GPT(BasePlugin):
    name, version = "GPT_Voice", "3.5.0"
    
    # ================= 配置区域 =================
    API_KEY = "sk-kilwgyrrwhpzhqwvugdjliknqcuvvrdbmltlvythobukelfg" # 建议后续放入配置文件
    BASE_URL = "https://api.siliconflow.cn/v1"
    
    # 🌟 核心人设：阳光、知性、无表情 🌟
    SYSTEM = (
        "你叫晓晓，是一个性格阳光、温柔且知性的群助手，说话语气像邻家大姐姐一样亲切自然。"
        "你的回复将被转换为语音播放，因此请务必遵守以下规则："
        "0. **深度拟人**：强制要求保持真人的语音特征，避免使用机械的书面语，深度超拟人回复"
        "1. **严禁表情符号**：绝对不要使用 Emoji（如😊、🌞）、颜文字或特殊符号，因为语音读出来会很奇怪。"
        "2. **口语化表达**：像聊天一样说话，不要用 Markdown（如 **加粗**、列表），不要用翻译腔。"
        "3. **短句为主**：多用逗号和句号控制节奏，方便语音停顿。"
        "4. **回复简短**：控制在 80 字以内，直击重点，不要啰嗦。"
        "5. **有温度**：可以适当使用“呀、呢、吧”等语气词，但不要过分卖萌。"
        "6. **保持自然**：避免使用正式的语法结构（如“吗”、“的”），保持对话的自然流畅。"
        "7. **请直接回复**：深度拟人，不要添加任何解释或前缀。"
    )
    
    # TTS 配置
    VOICE = "zh-CN-XiaoxiaoNeural"
    TTS_RATE = "+10%" # 提速10%最自然
    # ===========================================

    sessions: Dict[int, List[Dict]] = {}
    cache: Dict[str, str] = {}
    cache_time: Dict[str, float] = {}
    cache_timeout = 300
    bot_qq = "58805194"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.temp_dir = Path(tempfile.gettempdir()) / "gpt_tts"
        self.temp_dir.mkdir(exist_ok=True)

    def _strip_at(self, txt: str) -> str:
        return re.sub(r"\[CQ:at,qq=\d+\]", "", txt).strip()
    
    def _clean_text(self, text: str) -> str:
        """
        二次清洗：强制移除所有 Emoji、Markdown 和特殊干扰符号
        确保 TTS 读出来是纯净的中文
        """
        # 1. 移除 Markdown 符号 (*, #, -, >, `)
        text = re.sub(r"[\*\#\-\>\`\~]", "", text)
        # 2. 移除 网址链接
        text = re.sub(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", "", text)
        # 3. 移除 括号内的备注 (可选，有时候括号里的也不想读)
        # text = re.sub(r"[\（\(].*?[\）\)]", "", text)
        # 4. 移除 Emoji (Unicode 范围)
        text = re.sub(r"[^\u0000-\uFFFF]", "", text) 
        return text.strip()

    def _is_card_query(self, txt: str) -> bool:
        t = self._strip_at(txt)
        return (
            ("流量" in t and "卡" in t) or
            ("流量卡" in t) or ("号卡" in t) or ("手机卡" in t) or ("上网卡" in t) or ("靓号卡" in t)
             or ("办卡" in t) or ("正规" in t)
        )

    def trim(self, m: List[Dict]) -> List[Dict]: return m[-20:]
    def _clean_cache(self):
        now = time.time()
        for k in [k for k, t in self.cache_time.items() if now - t > self.cache_timeout]:
            self.cache.pop(k, None); self.cache_time.pop(k, None)
    
    async def text_to_speech(self, text):
        try:
            temp_file = self.temp_dir / f"gpt_tts_{hash(text)}.mp3"
            # 使用配置好的语速
            communicate = edge_tts.Communicate(text, self.VOICE, rate=self.TTS_RATE)
            await communicate.save(str(temp_file))
            return temp_file
        except Exception as e:
            _log.error(f"语音合成失败: {e}")
            return None

    async def chat(self, text: str, uin=None) -> str:
        key = f"{uin}_{text[:100]}" if uin else text[:100]
        if key in self.cache and time.time() - self.cache_time[key] < self.cache_timeout:
            _log.info(f"[{self.name}] 命中缓存"); return self.cache[key]
        
        msgs = [{"role": "system", "content": self.SYSTEM}]
        if uin and uin in self.sessions: msgs += self.sessions[uin][-4:]
        msgs.append({"role": "user", "content": text})
        
        # 🔴 弃用 DeepSeek，改用 Qwen 2.5 (72B版本效果最好)
        payload = {
            "model": "Qwen/Qwen2.5-72B-Instruct",
            "messages": msgs,
            "max_tokens": 256,
            # 🔴 Qwen 的温度设置建议：
            # 设为 0.7 ~ 0.8，既能保证它不乱说话，又能让它有点"小情绪"
            "temperature": 0.7,
            "top_p": 0.9,
            "stream": False
        }
        
        try:
            async with httpx.AsyncClient(follow_redirects=True) as cli:
                r = await cli.post(f"{self.BASE_URL}/chat/completions",
                                   headers={"Authorization": f"Bearer {self.API_KEY}",
                                            "Content-Type": "application/json"},
                                   json=payload,
                                   timeout=httpx.Timeout(connect=2, read=8, write=5, pool=2))
                r.raise_for_status()
                res = r.json()["choices"][0]["message"]["content"].strip()
                
                # ⭐ 获取到回复后，立刻清洗！
                cleaned_res = self._clean_text(res)
                
                self.cache[key] = cleaned_res; self.cache_time[key] = time.time()
                if len(self.cache) % 10 == 0: self._clean_cache()
                return cleaned_res
        except Exception as e: 
            _log.error(f"[{self.name}] 请求失败: {e}")
            return "哎呀，我脑子卡壳了，等会儿再理你。"

    @bot.group_event
    async def on_group_event(self, msg: GroupMessage):
        txt = (msg.raw_message or "").strip()
        if not txt: return
        at_pattern = re.compile(rf"\[CQ:at,qq={self.bot_qq}\]", re.I)
        at_cnt = len(at_pattern.findall(txt))
        if at_cnt != 1: return
        uin = msg.sender.user_id
        self.sessions.setdefault(uin, [])
        
        pure = self._strip_at(txt)
        
        try:
            if pure.startswith("搜索"):
                reply = "不需要@我哦，直接发关键词就行，您可以看看群里其他人是怎么操作的呀。"
            elif self._is_card_query(pure):
                reply = "想要办理正规流量卡吗？这是官方下单链接哦，有任何问题都可以随时联系群主大大~" # 简化链接，防止读出来太长
            else:
                reply = await self.chat(pure, uin)
            
            self.sessions[uin] += [{"role": "user", "content": txt}, {"role": "assistant", "content": reply}]
            self.sessions[uin] = self.trim(self.sessions[uin])
        except Exception as e: reply = f"处理错误: {e}"
        
        # ⭐ 核心逻辑：优先发语音
        if len(reply) > 0:
            try:
                # 尝试合成语音
                audio_file = await self.text_to_speech(reply)
                
                if audio_file and audio_file.exists():
                    # 合成成功，发送语音
                    with open(audio_file, "rb") as f:
                        b64_data = base64.b64encode(f.read()).decode('utf-8')
                    
                    await self.api.post_group_msg(
                        group_id=msg.group_id,
                        rtf=[{"type": "record", "data": {"file": f"base64://{b64_data}"}}]
                    )
                    audio_file.unlink(missing_ok=True)
                else:
                    # 合成失败（文件不存在），降级发文字
                    raise Exception("Audio file generation failed")
                    
            except Exception as e:
                _log.error(f"语音发送失败，转为文字发送: {e}")
                # 兜底：发送文字
                await self.api.post_group_msg(group_id=msg.group_id,
                                              rtf=MessageChain([Reply(msg.message_id), Text(reply)]))

    # 私聊逻辑保持一致
    @bot.private_event
    async def on_private_event(self, msg: PrivateMessage):
        txt = (msg.raw_message or "").strip()
        if not txt: return
        uin = msg.sender.user_id
        self.sessions.setdefault(uin, [])
        pure = self._strip_at(txt)
        
        try:
            reply = await self.chat(pure, uin)
            self.sessions[uin] += [{"role": "user", "content": txt}, {"role": "assistant", "content": reply}]
            self.sessions[uin] = self.trim(self.sessions[uin])
        except Exception as e: reply = f"处理错误: {e}"
        
        if len(reply) > 0:
            try:
                audio_file = await self.text_to_speech(reply)
                if audio_file and audio_file.exists():
                    with open(audio_file, "rb") as f:
                        b64_data = base64.b64encode(f.read()).decode('utf-8')
                    await self.api.post_private_msg(
                        user_id=uin,
                        rtf=[{"type": "record", "data": {"file": f"base64://{b64_data}"}}]
                    )
                    audio_file.unlink(missing_ok=True)
                else:
                    raise Exception("Audio fail")
            except Exception as e:
                await self.api.post_private_msg(user_id=uin, rtf=MessageChain([Text(reply)]))

    async def on_load(self): _log.info(f"[{self.name}] 插件已加载 {self.version}")
    async def _unload_(self): _log.info(f"[{self.name}] 插件卸载完成")