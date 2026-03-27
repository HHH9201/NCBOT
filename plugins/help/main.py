# /home/hjh/BOT/NCBOT/plugins/help/main.py
# NcatBot 5.x 帮助插件
import yaml
import logging
from pathlib import Path
from typing import Dict, List

from ncatbot.plugin import BasePlugin
from ncatbot.core import registrar
from ncatbot.event.qq import GroupMessageEvent, PrivateMessageEvent
from ncatbot.types import MessageArray, PlainText, Reply

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Help(BasePlugin):
    """NcatBot帮助插件 - 提供插件使用说明和命令列表"""
    name = "Help"
    version = "1.2.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 配置文件路径
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

    @registrar.on_group_command("帮助", "菜单", "help")
    async def group_help(self, event: GroupMessageEvent):
        """群组帮助命令"""
        help_msg = self._generate_help_message()

        # 策略：如果行数超过 20 行，使用合并转发，否则直接发送
        if len(help_msg.split('\n')) > 20:
            # 使用伪造转发
            from ncatbot.types.qq import ForwardConstructor
            fc = ForwardConstructor()
            fc.attach_text(help_msg)
            await self.api.qq.post_group_forward_msg(event.group_id, fc.build())
            return

        # 直接发送
        await event.reply(help_msg)

    @registrar.on_private_command("帮助", "菜单", "help")
    async def private_help(self, event: PrivateMessageEvent):
        """私聊帮助命令"""
        help_msg = self._generate_help_message()
        await event.reply(help_msg)

    async def on_load(self):
        logger.info(f"🚀 {self.name} v{self.version} 已加载")
