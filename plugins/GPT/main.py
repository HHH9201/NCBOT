# GPT 插件 - 智能联网Agent + 深度拟人TTS + 阳光晓晓
import asyncio, time, re, base64, logging
from typing import Dict, List
from pathlib import Path
import tempfile
import edge_tts
from datetime import datetime

# 引入全局服务
from common import ai_service, GLOBAL_CONFIG

# 🌟 新增：搜索库
try:
    from duckduckgo_search import DDGS
    HAS_DDGS = True
except ImportError:
    HAS_DDGS = False
    logging.warning("缺少 duckduckgo_search 依赖，搜索功能将不可用")

from ncatbot.plugin import BasePlugin, CompatibleEnrollment as bot
from ncatbot.core.message import GroupMessage, PrivateMessage
from ncatbot.core.message import MessageChain
from ncatbot.core.event.message_segment.message_segment import Text, Reply
from ncatbot.utils import get_log

_log = get_log(); _log.setLevel('INFO')

class GPT(BasePlugin):
    name, version = "GPT_Agent_Voice", "6.0.0"
    
    sessions: Dict[int, List[Dict]] = {}
    cache: Dict[str, str] = {}
    cache_time: Dict[str, float] = {}
    cache_timeout = 300
    bot_qq = "58805194"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.temp_dir = Path(tempfile.gettempdir()) / "gpt_tts"
        self.temp_dir.mkdir(exist_ok=True)
        
        # 加载配置
        self.api_key = GLOBAL_CONFIG.get("gpt.api_key")
        self.model_name = GLOBAL_CONFIG.get("gpt.model", "Qwen/Qwen2.5-72B-Instruct")
        self.voice = GLOBAL_CONFIG.get("gpt.voice", "zh-CN-XiaoxiaoNeural")
        self.tts_rate = "+10%"

    # ---------------- 🧠 1. AI 意图判断大脑 ----------------
    
    async def _analyze_search_intent(self, text: str) -> str:
        """
        让 AI 判断用户的这句话是否需要联网搜索。
        返回: 'NO' (不需要) 或 '搜索关键词' (需要)
        """
        # 如果用户明确说"搜索xxx"，直接提取
        if text.startswith("搜索"):
            return text[2:].strip()

        # 构造一个轻量级的 Prompt 让模型做判断题
        current_time = datetime.now().strftime("%Y年%m月%d日")
        system_prompt = (
            f"你是搜索意图分析员。当前日期是 {current_time}。"
            "判断用户输入是否涉及：实时新闻、天气、特定数据、具体人物动态、汇率股价或未来事件。"
            "如果是，请输出最精准的搜索关键词（不要标点，不要废话）。"
            "如果只是普通闲聊、问候、情感建议或通用知识，输出 NO。"
            "例子：'马斯克最近干了啥' -> 马斯克最新动态"
            "例子：'讲个笑话' -> NO"
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ]
        
        try:
            res = await ai_service.chat_completions(
                messages, 
                model=self.model_name,
                api_key=self.api_key,
                temperature=0.0,
                max_tokens=30
            )
            
            if not res or ("NO" in res.upper() and len(res) < 10):
                return "NO"
            return res.strip()
        except Exception:
            return "NO"

    # ---------------- 🔍 2. 联网搜索手脚 ----------------

    def _search_web(self, query: str) -> str:
        _log.info(f"正在联网搜索: {query}")
        try:
            with DDGS() as ddgs:
                # 搜索前3条结果
                results = list(ddgs.text(query, max_results=3))
            
            if not results: return ""
            
            summary = "【联网参考资料】:\n"
            for i, res in enumerate(results):
                summary += f"{i+1}. {res['body']}\n"
            return summary
        except Exception as e:
            _log.error(f"搜索失败: {e}")
            return ""

    # ---------------- 🗣️ 3. 拟人对话生成 ----------------

    def _get_system_prompt(self):
        """动态生成人设，注入当前时间"""
        current_date = datetime.now().strftime("%Y年%m月%d日")
        return (
            f"你叫晓晓，当前日期是【{current_date}】。"
            "你是一个性格阳光、温柔且知性的群助手，说话语气像邻家大姐姐一样亲切自然。"
            "你的回复将被转换为语音播放，必须严格遵守以下规则："
            "0. **深度拟人**：强制保持真人语音特征，拒绝机械感，拒绝书面语。"
            "1. **严禁表情**：绝不要使用 Emoji、Markdown、网址链接。"
            "2. **口语化**：像聊天一样说话，多用逗号句号控制呼吸节奏。"
            "3. **回复简短**：除非解释复杂事实，否则控制在 100 字以内，直击重点。"
            "4. **有温度**：适当使用语气词（呀、呢），但不要过分卖萌。"
            "5. **结合事实**：如果提供了【联网参考资料】，请基于资料回答，但必须用晓晓的口吻转述，不要照读新闻。"
        )

    def _clean_text(self, text: str) -> str:
        """清洗文本，防止 TTS 读出乱码"""
        text = re.sub(r"[\*\#\-\>\`\~]", "", text)
        text = re.sub(r"http[s]?://\S+", "", text)
        text = re.sub(r"[^\u0000-\uFFFF]", "", text)
        text = re.sub(r"\[\d+\]", "", text) # 去掉 [1] 这种引用标
        return text.strip()

    async def chat(self, text: str, uin=None, search_context: str = "") -> str:
        key = f"{uin}_{text[:100]}"
        # 只有非搜索请求才走缓存
        if not search_context and key in self.cache and time.time() - self.cache_time[key] < self.cache_timeout:
            _log.info(f"[{self.name}] 命中缓存"); return self.cache[key]
        
        # 组装 Prompt
        msgs = [{"role": "system", "content": self._get_system_prompt()}]
        if uin and uin in self.sessions: msgs += self.sessions[uin][-4:]
        
        final_prompt = text
        if search_context:
            final_prompt = (
                f"用户问题：{text}\n"
                f"这是你刚刚联网查到的资料：\n{search_context}\n"
                f"任务：请消化这些资料，然后用晓晓（知性大姐姐）的口吻，自然地告诉用户答案。不要像读新闻稿，要像聊天。"
            )
        
        msgs.append({"role": "user", "content": final_prompt})
        
        try:
            res = await ai_service.chat_completions(
                msgs,
                model=self.model_name,
                api_key=self.api_key,
                temperature=0.7,
                max_tokens=512,
                top_p=0.9
            )
            
            if not res:
                raise Exception("API返回空内容")

            cleaned_res = self._clean_text(res)
            
            if not search_context:
                self.cache[key] = cleaned_res; self.cache_time[key] = time.time()
            
            return cleaned_res
        except Exception as e: 
            _log.error(f"API请求失败: {e}")
            return "哎呀，脑子卡壳了，等会儿再理你。"

    # ---------------- 🎙️ 语音合成 ----------------

    async def text_to_speech(self, text):
        try:
            temp_file = self.temp_dir / f"gpt_tts_{hash(text)}.mp3"
            communicate = edge_tts.Communicate(text, self.VOICE, rate=self.TTS_RATE)
            await communicate.save(str(temp_file))
            return temp_file
        except Exception as e:
            _log.error(f"语音合成失败: {e}")
            return None

    # ---------------- 📩 消息处理入口 ----------------

    async def _handle_message(self, msg, is_group=True):
        txt = (msg.raw_message or "").strip()
        if not txt: return
        
        if is_group:
            if len(re.findall(rf"\[CQ:at,qq={self.bot_qq}\]", txt)) != 1: return
            uin = msg.sender.user_id
        else:
            uin = msg.sender.user_id
            
        self.sessions.setdefault(uin, [])
        pure = re.sub(r"\[CQ:at,qq=\d+\]", "", txt).strip()
        
        try:
            # 1. 办卡拦截 (保持原逻辑)
            if self._is_card_query(pure):
                reply = "想要办理正规流量卡吗？这是官方下单链接哦，有任何问题都可以随时联系群主大大~"
            
            else:
                # 2. AI 意图分析
                intent = await self._analyze_search_intent(pure)
                search_result = ""
                
                if intent != "NO":
                    # 3. 如果需要，执行搜索
                    search_result = await asyncio.to_thread(self._search_web, intent)
                
                # 4. 生成回复
                reply = await self.chat(pure, uin, search_context=search_result)
            
            # 记录历史
            self.sessions[uin] += [{"role": "user", "content": pure}, {"role": "assistant", "content": reply}]
            if len(self.sessions[uin]) > 20: self.sessions[uin] = self.sessions[uin][-20:]
            
            # 5. 发送 (语音优先)
            if reply and len(reply) > 0:
                audio_file = await self.text_to_speech(reply)
                if audio_file and audio_file.exists():
                    with open(audio_file, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    
                    target = {"group_id": msg.group_id} if is_group else {"user_id": uin}
                    func = self.api.post_group_msg if is_group else self.api.post_private_msg
                    
                    await func(**target, rtf=[{"type": "record", "data": {"file": f"base64://{b64}"}}])
                    audio_file.unlink(missing_ok=True)
                else:
                    raise Exception("Audio fail")

        except Exception as e:
            # 兜底发文字
            reply_text = reply if 'reply' in locals() else f"处理出错: {e}"
            target = {"group_id": msg.group_id} if is_group else {"user_id": uin}
            func = self.api.post_group_msg if is_group else self.api.post_private_msg
            await func(**target, rtf=MessageChain([Text(reply_text)]))

    # 辅助函数
    def _is_card_query(self, txt: str) -> bool:
        t = re.sub(r"\[CQ:at,qq=\d+\]", "", txt).strip()
        return (("流量" in t and "卡" in t) or ("流量卡" in t) or ("号卡" in t) or ("办卡" in t))

    def trim(self, m: List[Dict]) -> List[Dict]: return m[-20:]
    def _clean_cache(self):
        now = time.time()
        for k in [k for k, t in self.cache_time.items() if now - t > self.cache_timeout]:
            self.cache.pop(k, None); self.cache_time.pop(k, None)

    @bot.group_event
    async def on_group_event(self, msg: GroupMessage): await self._handle_message(msg, True)

    @bot.private_event
    async def on_private_event(self, msg: PrivateMessage): await self._handle_message(msg, False)

    async def on_load(self): _log.info(f"[{self.name}] 插件已加载")