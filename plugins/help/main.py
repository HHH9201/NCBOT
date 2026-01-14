# /home/hjh/BOT/NCBOT/plugins/help/main.py
# NCatBot 帮助插件 - 基于NcatBot框架的帮助系统
import yaml
import logging
import aiohttp
from pathlib import Path
from typing import Dict, List

from ncatbot.plugin import BasePlugin, CompatibleEnrollment
from ncatbot.core.message import GroupMessage, PrivateMessage
from ncatbot.core.message import MessageChain
from ncatbot.core.event.message_segment.message_segment import Text, Reply

# 引入全局服务
from common import napcat_service

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = CompatibleEnrollment

class Help(BasePlugin):
    """NcatBot帮助插件 - 提供插件使用说明和命令列表"""
    name = "Help"
    version = "1.1.0"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 配置文件路径修正到 tool 目录
        self.config_file = Path(__file__).parent / "tool" / "help_config.yaml"
        self.help_data: Dict = {}
        self.plugin_list: List[Dict] = []
        
        # 加载配置
        self._load_config()
        self._init_plugin_list()
    
    def _load_config(self):
        """加载帮助配置文件"""
        try:
            if self.config_file.exists():
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self.help_data = yaml.safe_load(f) or {}
                logger.info(f"成功加载帮助配置，共 {len(self.help_data.get('plugins', {}))} 个插件")
            else:
                logger.warning(f"配置文件不存在: {self.config_file}")
                self.help_data = {}
        except Exception as e:
            logger.error(f"加载帮助配置失败: {e}")
            self.help_data = {}

    def _init_plugin_list(self):
        """初始化插件列表"""
        plugins = self.help_data.get("plugins", {})
        self.plugin_list = []
        
        for name, info in plugins.items():
            self.plugin_list.append({
                "name": name,
                "description": info.get("description", "暂无描述"),
                "commands": info.get("commands", []),
                "example": info.get("example", "")
            })

    def _generate_help_message(self) -> str:
        """生成文本版帮助消息"""
        lines = []
        
        title = self.help_data.get("title", "🤖 帮助中心")
        lines.append(f"✨ {title} ✨")
        lines.append("══════════")
        
        desc = self.help_data.get("description")
        if desc:
            lines.append(f"📌 {desc}\n")
        
        for plugin in self.plugin_list:
            lines.append(f"🎪 {plugin['name']}")
            if plugin['description']:
                lines.append(f"说明：{plugin['description']}")
            
            cmds = plugin['commands']
            if cmds:
                lines.append(f"命令：{' | '.join(cmds)}")
            
            if plugin['example']:
                lines.append(f"示例：{plugin['example']}")
            
            lines.append("─" * 15)
        
        footer = self.help_data.get("footer")
        if footer:
            lines.append(f"\n{footer}")
            
        return "\n".join(lines)

    async def _send_forward_msg(self, group_id: int, content_str: str):
        """发送伪造合并转发消息"""
        nodes = [{
            "type": "node",
            "data": {
                "name": "帮助助手",
                "uin": "10000",
                "content": content_str
            }
        }]
        
        return await napcat_service.send_group_forward_msg(group_id, nodes)

    @bot.group_event
    async def group_help(self, msg: GroupMessage):
        """群组帮助命令"""
        text = msg.raw_message.strip()
        if text.lower() not in ["帮助", "菜单", "help"]:
            return

        help_msg = self._generate_help_message()
        
        # 策略：如果行数超过 20 行，使用合并转发，否则直接发送
        if len(help_msg.split('\n')) > 20:
            success = await self._send_forward_msg(msg.group_id, help_msg)
            if success:
                return
            # 如果转发失败，降级为普通发送（继续执行下方代码）
            
        await self.api.post_group_msg(
            group_id=msg.group_id,
            rtf=MessageChain([
                Reply(msg.message_id),
                Text(help_msg)
            ])
        )

    @bot.private_event
    async def private_help(self, msg: PrivateMessage):
        """私聊帮助命令"""
        text = msg.raw_message.strip()
        if text.lower() not in ["帮助", "菜单", "help"]:
            return

        help_msg = self._generate_help_message()
        await self.api.post_private_msg(
            user_id=msg.user_id,
            rtf=MessageChain([Text(help_msg)])
        )

    async def on_load(self):
        logger.info(f"🚀 {self.name} v{self.version} 已加载")
