# -*- coding: utf-8 -*-
import asyncio
import hashlib
import hmac
import base64
import json
import ssl
import time
from datetime import datetime
from time import mktime
from urllib.parse import urlencode, urlparse
from wsgiref.handlers import format_date_time
import websockets
import os
from ncatbot.plugin import BasePlugin
from ncatbot.core import BotClient, GroupMessage, MessageChain, Record
from ncatbot.utils import get_log

_log = get_log()
_log.setLevel('INFO')

class VoiceAssistant(BasePlugin):
    name, version = "VoiceAssistant", "1.0.0"

    # iFLYTEK API Config
    APPID = "06aca218"
    APISecret = "MTBjZDJjMzc0MDIxOTRmNTg5ZDU5NTJk"
    APIKey = "917d70088b35d73808a111e0ebaacfea"
    TTS_URL = "wss://cbm01.cn-huabei-1.xf-yun.com/v1/private/mcd9m97e6"
    
    # Plugin Config
    RESPONSE_TEXT = "测试成功，你好啊，我是语音助手"
    
    def __init__(self, event_bus=None, **kwargs):
        super().__init__(event_bus=event_bus, **kwargs)
        self.bot_api = None
        self.tool_dir = os.path.join(os.path.dirname(__file__), "tool")
        if not os.path.exists(self.tool_dir):
            os.makedirs(self.tool_dir)
            
    def _create_url(self):
        url_parts = urlparse(self.TTS_URL)
        host = url_parts.netloc
        path = url_parts.path
        
        now = datetime.now()
        date = format_date_time(mktime(now.timetuple()))
        
        signature_origin = f"host: {host}\ndate: {date}\nGET {path} HTTP/1.1"
        signature_sha = hmac.new(
            self.APISecret.encode('utf-8'),
            signature_origin.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        signature_sha_base64 = base64.b64encode(signature_sha).decode(encoding='utf-8')
        
        authorization_origin = f'api_key="{self.APIKey}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature_sha_base64}"'
        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')
        
        v = {
            "authorization": authorization,
            "date": date,
            "host": host
        }
        return self.TTS_URL + '?' + urlencode(v)

    async def _generate_voice(self, text, output_file):
        url = self._create_url()
        try:
            async with websockets.connect(url, ssl=True) as ws:
                # Send request
                data = {
                    "header": {
                        "app_id": self.APPID,
                        "status": 2
                    },
                    "parameter": {
                        "oral": {
                            "oral_level": "mid",
                            "spark_assist": 1
                        },
                        "tts": {
                            "vcn": "x5_lingyuyan_flow",
                            "speed": 50,
                            "volume": 50,
                            "pitch": 50,
                            "bgs": 0,
                            "reg": 0,
                            "rdn": 0,
                            "rhy": 0,
                            "scn": 0,
                            "version": 0,
                            "L5SilLen": 0,
                            "ParagraphSilLen": 0,
                            "audio": {
                                "encoding": "lame", # Using lame for mp3 format directly
                                "sample_rate": 16000,
                                "channels": 1,
                                "bit_depth": 16,
                                "frame_size": 0
                            },
                            "pybuf": {
                                "encoding": "utf8",
                                "compress": "raw",
                                "format": "plain"
                            }
                        }
                    },
                    "payload": {
                        "text": {
                            "encoding": "utf8",
                            "compress": "raw",
                            "format": "plain", # Changed to plain text format
                            "status": 2,
                            "seq": 0,
                            "text": text # Base64 encoding is not required for plain text format per some docs, but let's check if we need to encode it
                        }
                    }
                }
                # Double check payload encoding
                # Usually payload text needs base64 encoding
                data["payload"]["text"]["text"] = base64.b64encode(text.encode("utf-8")).decode("utf-8")
                
                await ws.send(json.dumps(data))
                
                # Receive response
                with open(output_file, 'wb') as f:
                    while True:
                        msg = await ws.recv()
                        msg_json = json.loads(msg)
                        
                        code = msg_json['header']['code']
                        if code != 0:
                            _log.error(f"TTS Error: {msg_json}")
                            return False
                            
                        if 'payload' in msg_json:
                            audio = msg_json['payload']['audio']['audio']
                            audio_content = base64.b64decode(audio)
                            f.write(audio_content)
                            
                        status = msg_json['header']['status']
                        if status == 2: # End of stream
                            break
                return True
        except Exception as e:
            _log.error(f"TTS Exception: {e}")
            return False

# Event Handler Registration
bot = BotClient()

@bot.group_event()
async def on_group_message(msg: GroupMessage):
    # Check if message is voice message
    is_voice = False
    
    # Check msg.message for record type
    if hasattr(msg, 'message'):
        for segment in msg.message:
            if isinstance(segment, dict) and segment.get('type') == 'record':
                is_voice = True
                break
            # Some implementations might use object with type attribute
            elif hasattr(segment, 'type') and segment.type == 'record':
                is_voice = True
                break
    
    # Also check raw_message for CQ code
    if not is_voice and msg.raw_message and "[CQ:record" in msg.raw_message:
        is_voice = True
        
    if is_voice:
        plugin_instance = VoiceAssistant()
        output_file = os.path.join(plugin_instance.tool_dir, "response.mp3")
        
        if not os.path.exists(output_file):
            _log.info("Generating voice response...")
            success = await plugin_instance._generate_voice(plugin_instance.RESPONSE_TEXT, output_file)
            if not success:
                _log.error("Failed to generate voice response")
                return
        
        _log.info(f"Sending voice response to group {msg.group_id}")
        
        try:
            # Use bot.api if available (initialized by run()), otherwise try to use msg.reply if appropriate
            # In plugin mode, 'bot' global variable should have 'api' attribute set after startup
            if hasattr(bot, 'api') and bot.api:
                 await bot.api.post_group_file(group_id=msg.group_id, record=output_file)
            else:
                 _log.warning("Bot API not initialized, cannot send voice.")
                 
        except Exception as e:
            _log.error(f"Failed to send voice: {e}")
