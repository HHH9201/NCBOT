# NCatBot 帮助插件 - 基于NcatBot框架的帮助系统
import yaml
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional

from ncatbot.plugin import BasePlugin, CompatibleEnrollment
from ncatbot.core.message import GroupMessage, PrivateMessage
from ncatbot.core.message import MessageChain
from ncatbot.core.event.message_segment.message_segment import Text, Reply

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = CompatibleEnrollment


class Help(BasePlugin):
    """NcatBot帮助插件 - 提供插件使用说明和命令列表"""
    name = "Help"
    version = "1.0.0"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 初始化配置
        self.config_file = Path(__file__).with_name("help_config.yaml")
        self.help_data: Dict = {}
        self.plugin_list: List[Dict] = []
        
        # 加载帮助配置
        self._load_config()
        
        # 初始化插件列表
        self._init_plugin_list()
    
    def _load_config(self):
        """加载帮助配置文件"""
        default_config = {
            "title": "🤖 NcatBot 帮助中心",
            "description": "欢迎使用NcatBot！以下是可用的插件和命令列表：",
            "footer": "💡 提示：发送 '帮助' 或 '菜单' 查看此信息",
            "plugins": {
                "GPT": {
                    "description": "🤖 AI对话功能 - 与智能AI进行对话",
                    "commands": ["@机器人 你的问题"],
                    "example": "@机器人 今天天气怎么样？"
                },
                "JM": {
                    "description": "🖼️ 精美图片功能 - 获取精美图片",
                    "commands": ["JM", "美图"],
                    "example": "JM"
                },
                "txt": {
                    "description": "📄 文档查询功能 - 查询游戏相关文档",
                    "commands": ["文档", "帮助文档"],
                    "example": "文档"
                },
                "welcome": {
                    "description": "👋 欢迎新成员 - 自动欢迎新加入群成员",
                    "commands": ["设置欢迎", "查看欢迎"],
                    "example": "设置欢迎 欢迎新成员！"
                },
                "xydj": {
                    "description": "🎲 幸运抽奖功能 - 参与抽奖活动",
                    "commands": ["抽奖", "xydj"],
                    "example": "抽奖"
                },
                "RecallMessage": {
                    "description": "🗑️ 消息撤回功能 - 撤回机器人发送的消息",
                    "commands": ["撤回", "删除"],
                    "example": "撤回"
                }
            }
        }
        
        try:
            if self.config_file.exists():
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self.help_data = yaml.safe_load(f)
                logger.info(f"成功加载帮助配置，共 {len(self.help_data.get('plugins', {}))} 个插件")
            else:
                self.help_data = default_config
                self._save_config()
                logger.info("使用默认帮助配置")
        except Exception as e:
            logger.error(f"加载帮助配置失败: {e}")
            self.help_data = default_config
    
    def _save_config(self):
        """保存帮助配置到文件"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                yaml.dump(self.help_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            return True
        except Exception as e:
            logger.error(f"保存帮助配置失败: {e}")
            return False
    
    def _init_plugin_list(self):
        """初始化插件列表"""
        plugins = self.help_data.get("plugins", {})
        self.plugin_list = []
        
        for plugin_name, plugin_info in plugins.items():
            self.plugin_list.append({
                "name": plugin_name,
                "description": plugin_info.get("description", "暂无描述"),
                "commands": plugin_info.get("commands", []),
                "example": plugin_info.get("example", "")
            })
    
    def _generate_help_message(self, is_private: bool = False) -> str:
        """生成紧凑版帮助消息 - 每行之间不空行"""
        lines = []
        
        # 添加标题
        title = self.help_data.get("title", "🤖 帮助中心")
        lines.append(f"✨ {title} ✨")
        lines.append("══════════")
        
        # 添加描述
        description = self.help_data.get("description", "")
        if description:
            lines.append(f"📌 {description.strip()}")
        
        # 添加插件列表
        for plugin in self.plugin_list:
            # 插件名称
            lines.append(f"🎪 {plugin['name']}")
            
            # 插件描述 - 移除图标，只保留核心描述
            if plugin['description']:
                desc = plugin['description']
                # 提取核心描述（移除图标和破折号）
                if '功能' in desc:
                    # 提取"功能"后的描述
                    parts = desc.split('功能')
                    if len(parts) > 1:
                        desc = parts[1].replace('-', '').replace('•', '').strip()
                    else:
                        desc = desc.replace('🤖', '').replace('🖼️', '').replace('📄', '').replace('👋', '').replace('🎲', '').replace('🗑️', '').replace('-', '').replace('•', '').strip()
                else:
                    desc = desc.replace('🤖', '').replace('🖼️', '').replace('📄', '').replace('👋', '').replace('🎲', '').replace('🗑️', '').replace('-', '').replace('•', '').strip()
                
                if desc:
                    lines.append(f"说明：{desc}")
            
            # 命令显示
            if plugin['commands']:
                commands = plugin['commands']
                if len(commands) == 1 and '|' in commands[0]:
                    lines.append(f"使用命令: {commands[0]}")
                else:
                    commands_str = " | ".join(commands)
                    lines.append(f"使用命令: {commands_str}")
            
            # 示例
            if plugin['example']:
                example = plugin['example']
                lines.append(f"示例: 『{example}』")
            
            # 插件间分隔线
            lines.append("══════════")
        
        # 添加页脚
        footer = self.help_data.get("footer", "")
        if footer:
            # 移除页脚中的图标
            clean_footer = footer.replace('💡', '').replace('✨', '').strip()
            if clean_footer:
                lines.append(f"✨ {clean_footer} ✨")
        
        return "\n".join(lines)
    
    @bot.group_event
    async def group_help(self, msg: GroupMessage):
        """群组中的帮助命令"""
        try:
            text = msg.raw_message.strip()
            
            # 检查是否为帮助命令
            help_commands = ["帮助", "菜单", "help"]
            if text.lower() in [cmd.lower() for cmd in help_commands]:
                help_message = self._generate_help_message(is_private=False)
                
                # 发送帮助消息
                chain = MessageChain([
                    Reply(msg.message_id),
                    Text(help_message)
                ])
                
                await self.api.post_group_msg(
                    group_id=msg.group_id,
                    rtf=chain
                )
                
                logger.info(f"群 {msg.group_id} 用户 {msg.sender.user_id} 请求帮助")
        
        except Exception as e:
            logger.error(f"群组帮助命令处理失败: {e}")
            # 发送错误提示
            try:
                error_chain = MessageChain([
                    Reply(msg.message_id),
                    Text("❌ 获取帮助信息失败，请稍后重试")
                ])
                await self.api.post_group_msg(
                    group_id=msg.group_id,
                    rtf=error_chain
                )
            except:
                pass
    
    @bot.private_event
    async def private_help(self, msg: PrivateMessage):
        """私聊中的帮助命令"""
        try:
            text = msg.raw_message.strip()
            
            # 检查是否为帮助命令
            help_commands = ["帮助", "菜单", "help"]
            if text.lower() in [cmd.lower() for cmd in help_commands]:
                help_message = self._generate_help_message(is_private=True)
                
                # 发送帮助消息
                chain = MessageChain([Text(help_message)])
                
                await self.api.post_private_msg(
                    user_id=msg.user_id,
                    rtf=chain
                )
                
                logger.info(f"用户 {msg.user_id} 私聊请求帮助")
        
        except Exception as e:
            logger.error(f"私聊帮助命令处理失败: {e}")
            # 发送错误提示
            try:
                error_chain = MessageChain([Text("❌ 获取帮助信息失败，请稍后重试")])
                await self.api.post_private_msg(
                    user_id=msg.user_id,
                    rtf=error_chain
                )
            except:
                pass
    
    async def on_load(self):
        """插件加载时执行"""
        logger.info(f"🚀 {self.name} 插件已加载 (版本: {self.version})")
        logger.info(f"📋 已加载 {len(self.plugin_list)} 个插件的帮助信息")
        return True
    
    async def _unload_(self):
        """插件卸载时执行"""
        logger.info(f"👋 {self.name} 插件已卸载")
        return True