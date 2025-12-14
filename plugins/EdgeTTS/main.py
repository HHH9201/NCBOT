# /home/hjh/BOT/NCBOT/plugins/EdgeTTS/main.py
# EdgeTTS语音合成插件 - 纯净版 (锁定：阳光晓晓)
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

# 使用CompatibleEnrollment作为装饰器
bot = CompatibleEnrollment

class EdgeTTS(BasePlugin):
    name = "SunnyXiaoxiao"
    version = "3.0 (Pure)"
    
    # 唯一指定音色：微软晓晓
    VOICE = "zh-CN-XiaoxiaoNeural"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 设置临时目录
        self.temp_dir = Path(tempfile.gettempdir()) / "edge_tts"
        self.temp_dir.mkdir(exist_ok=True)
    
    async def text_to_speech(self, text):
        """文本转语音核心逻辑"""
        try:
            # 创建临时文件路径
            temp_file = self.temp_dir / f"tts_{hash(text)}.mp3"
            
            # 🌞 核心调教：rate="+12%"
            # 这个参数是“阳光感”的来源，语速稍快一点，听起来像在开心聊天
            communicate = edge_tts.Communicate(text, self.VOICE, rate="+12%")
            
            await communicate.save(str(temp_file))
            return temp_file
        except Exception as e:
            logging.error(f"合成失败: {e}")
            return None
    
    @bot.group_event
    async def on_group_message(self, msg: GroupMessage):
        """处理群组消息"""
        # 只在指定群生效
        if str(msg.group_id) != "695934967":
            return
        
        raw = msg.raw_message.strip()
        
        # 触发指令：语音 [内容]
        if raw.startswith("语音"):
            # 提取内容
            content = raw[2:].strip()
            
            if not content:
                await msg.reply(text="想让我说什么呀？例如：语音 早上好")
                return
            
            # 长度限制
            if len(content) > 500:
                await msg.reply(text="太长啦，我念不过来~")
                return
            
            try:
                # 1. 合成
                audio_file = await self.text_to_speech(content)
                
                if audio_file and audio_file.exists():
                    try:
                        # 2. 转 Base64 (为了兼容你的Docker环境)
                        with open(audio_file, "rb") as f:
                            b64_data = base64.b64encode(f.read()).decode('utf-8')
                        
                        # 3. 发送
                        logging.info(f"正在发送语音: {content[:10]}...")
                        await self.api.post_group_msg(
                            group_id=msg.group_id,
                            rtf=[{
                                "type": "record",
                                "data": {"file": f"base64://{b64_data}"}
                            }]
                        )
                    except Exception as e:
                        logging.error(f"发送出错: {e}")
                        await msg.reply(text="发送失败了捏")
                    finally:
                        # 4. 删掉临时文件
                        audio_file.unlink(missing_ok=True)
                else:
                    await msg.reply(text="生成语音失败了")
                    
            except Exception as e:
                logging.error(f"运行异常: {e}")