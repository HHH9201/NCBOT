# /home/hjh/BOT/NCBOT/common/napcat.py
import aiohttp
import logging
from typing import List, Dict, Union, Optional
import os
import base64
from .config import GLOBAL_CONFIG

class NapCatService:
    """
    NapCat 协议服务封装
    主要提供伪造合并转发消息等 NcatBot 原生不支持的高级功能
    """
    
    def __init__(self):
        self.api_url = GLOBAL_CONFIG.get("napcat.url", "http://101.35.164.122:3006").rstrip('/')
        self.token = GLOBAL_CONFIG.get("napcat.token", "he031701")
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.token}'
        }

    async def send_group_forward_msg(self, group_id: Union[int, str], nodes: List[Dict], **kwargs) -> bool:
        """
        发送群组伪造合并转发消息
        
        :param group_id: 群组ID
        :param nodes: 消息节点列表
        :param kwargs: 其他可选参数 (如 source, summary, prompt, news 等)
        :return: 是否发送成功
        """
        url = f"{self.api_url}/send_group_forward_msg"
        payload = {
            "group_id": int(group_id),
            "messages": nodes
        }
        payload.update(kwargs)
        
        import asyncio
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, headers=self.headers, timeout=30) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            if result.get('status') == 'ok':
                                logging.info(f"[NapCat] 合并转发消息发送成功 -> Group: {group_id}")
                                return True
                            else:
                                logging.warning(f"[NapCat] 合并转发消息发送失败: {result}")
                        else:
                            logging.warning(f"[NapCat] HTTP请求失败: {resp.status}")
                            
            except Exception as e:
                logging.error(f"[NapCat] 发送合并转发消息异常 (尝试 {attempt+1}/{max_retries}): {e}")
            
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                
        return False

    @staticmethod
    def construct_node(user_id: str, nickname: str, content: Union[str, List[Dict]]) -> Dict:
        """
        构造单个转发节点
        
        :param user_id: 发送者QQ号
        :param nickname: 发送者昵称
        :param content: 消息内容（字符串或消息段列表）
        :return: 节点字典
        """
        node_data = {
            "uin": user_id,
            "nickname": nickname,
            "content": content
        }
        return {"type": "node", "data": node_data}
    
    @staticmethod
    def image_to_base64(image_path: str) -> Optional[str]:
        """
        将本地图片转换为Base64格式 (用于NapCat发送)
        """
        if not os.path.exists(image_path):
            logging.warning(f"[NapCat] 图片文件不存在: {image_path}")
            return None
            
        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()
                base64_encoded = base64.b64encode(image_data).decode('utf-8')
                return f"data:image/png;base64,{base64_encoded}"
        except Exception as e:
            logging.error(f"[NapCat] 图片转Base64失败: {e}")
            return None

# 全局单例
napcat_service = NapCatService()
