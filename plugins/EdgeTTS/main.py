# /home/hjh/BOT/NCBOT/plugins/EdgeTTS/main.py
# EdgeTTS语音合成插件 - 拟人日常版 (去除播音腔)
import logging
import tempfile
import base64
from pathlib import Path

import edge_tts
from ncatbot.plugin import BasePlugin, CompatibleEnrollment
from ncatbot.core import GroupMessage

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

bot = CompatibleEnrollment

class EdgeTTS(BasePlugin):
    name = "NaturalXiaoxiao"
    version = "Final_Real"
    
    # 依然选晓晓，因为她的采样质量最高，最不容易甚至破音
    VOICE = "zh-CN-XiaoxiaoNeural"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.temp_dir = Path(tempfile.gettempdir()) / "edge_tts"
        self.temp_dir.mkdir(exist_ok=True)
    
    async def text_to_speech(self, text):
        try:
            temp_file = self.temp_dir / f"tts_{hash(text)}.mp3"
            
            # 🧬 核心调校：只加 10% 语速
            # 不要 SSML，不要 pitch，不要 style。
            # rate="+10%" 刚好打破了“念稿子”的节奏，听起来像真人在跟你打字时的默读语速。
            communicate = edge_tts.Communicate(text, self.VOICE, rate="+10%")
            
            await communicate.save(str(temp_file))
            return temp_file
        except Exception as e:
            logging.error(f"合成失败: {e}")
            return None
    
    @bot.group_event
    async def on_group_message(self, msg: GroupMessage):
        if str(msg.group_id) != "695934967": return
        raw = msg.raw_message.strip()
        
        if raw.startswith("语音"):
            content = raw[2:].strip()
            if not content: return
            
            try:
                audio_file = await self.text_to_speech(content)
                if audio_file and audio_file.exists():
                    try:
                        with open(audio_file, "rb") as f:
                            b64_data = base64.b64encode(f.read()).decode('utf-8')
                        
                        await self.api.post_group_msg(
                            group_id=msg.group_id,
                            rtf=[{"type": "record", "data": {"file": f"base64://{b64_data}"}}]
                        )
                    except Exception as e:
                        logging.error(f"发送出错: {e}")
                    finally:
                        audio_file.unlink(missing_ok=True)
            except Exception as e:
                logging.error(f"运行异常: {e}")