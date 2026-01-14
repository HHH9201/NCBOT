# /home/hjh/BOT/NCBOT/common/ai.py
import aiohttp
import logging
from typing import List, Dict, Optional, Union
from .config import GLOBAL_CONFIG

class AIService:
    """
    通用 AI 服务封装 (基于 SiliconFlow API)
    """
    
    def __init__(self):
        self.api_url = GLOBAL_CONFIG.get("siliconflow.url", "https://api.siliconflow.cn/v1/chat/completions")
        self.api_key = GLOBAL_CONFIG.get("siliconflow.api_key", "sk-ixmsswryqnmuyifjewdetqnjewdetq")
        self.model = GLOBAL_CONFIG.get("siliconflow.model", "moonshotai/Kimi-K2-Instruct-0905")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.default_proxy = GLOBAL_CONFIG.get("proxy")

    async def chat_completions(self, 
                             messages: List[Dict[str, str]], 
                             temperature: float = 0.7, 
                             max_tokens: int = 512,
                             proxy: Optional[str] = None,
                             model: Optional[str] = None,
                             api_key: Optional[str] = None,
                             **kwargs) -> Optional[str]:
        """
        发送聊天补全请求
        
        :param messages: 消息列表 [{"role": "user", "content": "..."}]
        :param temperature: 温度
        :param max_tokens: 最大token数
        :param proxy: 代理地址
        :param model: 模型名称 (覆盖默认)
        :param api_key: API密钥 (覆盖默认)
        :param kwargs: 其他参数 (如 top_p, stream 等)
        :return: 回复内容
        """
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        payload.update(kwargs)
        
        headers = self.headers.copy()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        actual_proxy = proxy or self.default_proxy

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url, 
                    json=payload, 
                    headers=headers,
                    proxy=actual_proxy,
                    timeout=30
                ) as resp:
                    if resp.status != 200:
                        logging.warning(f"[AI] API请求失败: {resp.status} - {await resp.text()}")
                        return None
                        
                    data = await resp.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        return data["choices"][0]["message"]["content"].strip()
                    return None
                    
        except Exception as e:
            logging.error(f"[AI] API调用异常: {e}")
            return None

    async def simple_chat(self, prompt: str, system_prompt: str = None) -> Optional[str]:
        """简易对话接口"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        return await self.chat_completions(messages)

# 全局单例
ai_service = AIService()
