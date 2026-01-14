# NCatBot 三角洲行动每日密码插件
# /home/h/BOT/NC/plugins/sjzmm/main.py
import os
import logging
import re
from typing import Optional, Dict, List
from pathlib import Path
import aiohttp

from ncatbot.plugin import BasePlugin, CompatibleEnrollment
from ncatbot.core.message import GroupMessage, PrivateMessage
from ncatbot.core.message import MessageChain
from ncatbot.core.event.message_segment.message_segment import Text, Reply

# 引入全局配置
from common.config import GLOBAL_CONFIG

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = CompatibleEnrollment


class sjzmm(BasePlugin):
    """三角洲行动每日密码插件 - 获取游戏中的每日密码信息"""
    name = "sjzmm"
    version = "1.0.0"
    api_url = "http://api-v2.yuafeng.cn/API/sjzmm.php"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 缓存最新的密码信息
        self.password_data = None
        self.last_update_time = None
        
    async def _fetch_password_data(self) -> Optional[Dict[str, List[Dict]]]:
        """
        从API获取最新的每日密码数据
        :return: 格式化后的密码数据字典，包含更新时间和密码列表
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.api_url, timeout=10) as response:
                    if response.status == 200:
                        content = await response.text()
                        return self._parse_response(content)
                    else:
                        logger.error(f"API请求失败，状态码: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"获取密码数据时发生错误: {e}")
            return None
    
    def _parse_response(self, content: str) -> Optional[Dict[str, List[Dict]]]:
        """
        解析API返回的文本内容
        :param content: API返回的文本
        :return: 格式化后的密码数据字典
        """
        try:
            # 解析更新时间
            update_time_match = re.search(r'更新时间：(.*?)\n', content)
            update_time = update_time_match.group(1) if update_time_match else "未知"
            
            # 解析各个地点的密码信息
            password_list = []
            # 提取每个地点的信息块
            location_blocks = re.split(r'\n\d+\.', content)[1:]
            
            for block in location_blocks:
                block = block.strip()
                if not block:
                    continue
                
                # 提取地点名称
                location_match = re.search(r'【(.*?)】', block)
                location_name = location_match.group(1) if location_match else "未知地点"
                
                # 提取具体点位
                position_match = re.search(r'具体点位：(.*?)\n', block)
                position = position_match.group(1) if position_match else "未知点位"
                
                # 提取每日密码
                password_match = re.search(r'每日密码：(\d+)', block)
                password = password_match.group(1) if password_match else "未知密码"
                
                # 提取地点图片
                image_match = re.search(r'地点图片：(.*)', block)
                images = []
                if image_match:
                    image_urls = image_match.group(1).split(',')
                    for url in image_urls:
                        url = url.strip().strip('`')
                        if url:
                            images.append(url)
                
                password_list.append({
                    "location": location_name,
                    "position": position,
                    "password": password,
                    "images": images
                })
            
            return {
                "update_time": update_time,
                "passwords": password_list
            }
        except Exception as e:
            logger.error(f"解析API响应时发生错误: {e}")
            return None
    
    def _generate_password_message(self, data: Dict[str, List[Dict]]) -> str:
        """
        生成密码信息的文本消息
        :param data: 密码数据字典
        :return: 格式化的文本消息
        """
        lines = []
        lines.append(f"🎮 三角洲行动每日密码 (更新时间：{data['update_time']})")
        lines.append("========================")
        
        for i, item in enumerate(data['passwords'], 1):
            lines.append(f"{i}. 【{item['location']}】")
            lines.append(f"具体点位：{item['position']}")
            lines.append(f"🔑 每日密码：{item['password']}")
            lines.append("========================")
        
        return '\n'.join(lines)
    
    @bot.group_event()
    async def group_sjzmm(self, msg: GroupMessage):
        """
        群聊中处理获取三角洲行动每日密码的命令
        """
        try:
            text = msg.raw_message.strip()
            
            # 检查是否为密码查询命令
            if text.lower() in ["sjzmm", "三角洲密码", "每日密码", "密码"]:
                logger.info(f"群 {msg.group_id} 用户 {msg.sender.user_id} 请求每日密码")
                
                # 获取密码数据
                data = await self._fetch_password_data()
                
                if data:
                    # 缓存数据
                    self.password_data = data
                    self.last_update_time = data['update_time']
                    
                    # 生成消息
                    message_text = self._generate_password_message(data)
                    
                    # 发送消息链，包含回复和文本
                    chain = MessageChain([
                        Reply(msg.message_id),
                        Text(message_text)
                    ])
                    
                    await self.api.post_group_msg(
                        group_id=msg.group_id,
                        rtf=chain
                    )
                else:
                    # 发送错误消息
                    error_chain = MessageChain([
                        Reply(msg.message_id),
                        Text("❌ 获取每日密码失败，请稍后重试")
                    ])
                    await self.api.post_group_msg(
                        group_id=msg.group_id,
                        rtf=error_chain
                    )
        except Exception as e:
            logger.error(f"处理群消息时发生错误: {e}")
            # 出错时不抛出异常，确保插件继续运行
            try:
                await self.api.post_group_msg(
                    group_id=msg.group_id,
                    rtf=MessageChain([Reply(msg.message_id), Text("处理请求时发生错误，请稍后重试")])
                )
            except:
                # 避免嵌套异常
                pass
    
    @bot.private_event()
    async def private_sjzmm(self, msg: PrivateMessage):
        """
        私聊中处理获取三角洲行动每日密码的命令
        """
        try:
            text = msg.raw_message.strip()
            
            # 检查是否为密码查询命令
            if text.lower() in ["sjzmm", "三角洲密码", "每日密码", "密码"]:
                logger.info(f"用户 {msg.user_id} 私聊请求每日密码")
                
                # 获取密码数据
                data = await self._fetch_password_data()
                
                if data:
                    # 缓存数据
                    self.password_data = data
                    self.last_update_time = data['update_time']
                    
                    # 生成消息
                    message_text = self._generate_password_message(data)
                    
                    # 发送消息
                    chain = MessageChain([Text(message_text)])
                    await self.api.post_private_msg(
                        user_id=msg.user_id,
                        rtf=chain
                    )
                else:
                    # 发送错误消息
                    error_chain = MessageChain([Text("❌ 获取每日密码失败，请稍后重试")])
                    await self.api.post_private_msg(
                        user_id=msg.user_id,
                        rtf=error_chain
                    )
        except Exception as e:
            logger.error(f"处理私聊消息时发生错误: {e}")
            # 出错时不抛出异常，确保插件继续运行
            try:
                await self.api.post_private_msg(
                    user_id=msg.user_id,
                    rtf=MessageChain([Text("处理请求时发生错误，请稍后重试")])
                )
            except:
                # 避免嵌套异常
                pass
    
    async def on_load(self):
        """
        插件加载时执行
        """
        logger.info(f"🚀 {self.name} 插件已加载 (版本: {self.version})")
        logger.info(f"📡 API地址: {self.api_url}")
        return True
    
    async def _unload_(self):
        """
        插件卸载时执行
        """
        logger.info(f"👋 {self.name} 插件已卸载")
        return True