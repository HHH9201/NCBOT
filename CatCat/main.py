# main.py - 适配 ncatbot5，支持任意 OpenAI 兼容接口

import os
import yaml

from ncatbot.plugin import BasePlugin
from ncatbot.event.qq import GroupMessageEvent, PrivateMessageEvent
from ncatbot.types import PlainText, MessageArray
from ncatbot.core import registrar
from ncatbot.utils.logger import get_log

from .AiChat import gene_response

_log = get_log()

# 插件目录的绝对路径
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

# LLM 接口配置（兼容 OpenAI 协议的任意厂商）
llm_config = {
    "api_key": "",
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-chat",
    "temperature": 1.3,
    "max_tokens": 256,
    "thinking": False,
    "cooldown": 10,
    "max_history_lines": 200,
}
cat_prompt = ""
super_user = ""
bot_id = ""
# 猫猫开关（运行时可由管理员私聊切换）
cat_enabled = True


class CatCat(BasePlugin):
    name = "CatCat"
    version = "1.2.0"

    @registrar.on_group_message()
    async def on_group_message(self, msg: GroupMessageEvent):
        global bot_id

        # 猫猫被关闭时直接忽略
        if not cat_enabled:
            return

        # 获取机器人 QQ 号（缓存）
        if not bot_id:
            try:
                info = await self.api.qq.query.get_login_info()
                bot_id = str(info.user_id)
            except Exception as e:
                _log.warning(f"获取机器人QQ号失败: {e}")

        # 测试命令
        if msg.raw_message == "测试CatCat":
            await self.api.qq.post_group_msg(
                msg.group_id,
                rtf=MessageArray([PlainText(text="NCatBot插件CatCat测试成功喵")]),
            )
            return

        _log.info(f"{msg.sender.nickname}({msg.sender.user_id}): {msg.raw_message[:10]}")
        response = await gene_response(llm_config, msg, cat_prompt, bot_id)
        if response:
            await self.api.qq.post_group_msg(
                msg.group_id,
                rtf=MessageArray([PlainText(text=response)]),
            )

    @registrar.on_private_message()
    async def on_private_message(self, msg: PrivateMessageEvent):
        global cat_prompt, cat_enabled
        if str(msg.user_id) != str(super_user):
            return

        text = msg.raw_message.strip()

        # 开关猫猫
        if text == "猫猫开":
            cat_enabled = True
            await self.api.qq.post_private_msg(
                msg.sender.user_id,
                rtf=MessageArray([PlainText(text="猫猫已开启喵~")]),
            )
            return
        if text == "猫猫关":
            cat_enabled = False
            await self.api.qq.post_private_msg(
                msg.sender.user_id,
                rtf=MessageArray([PlainText(text="猫猫已关闭，需要时发\"猫猫开\"唤醒")]),
            )
            return
        if text == "猫猫状态":
            status = "开启" if cat_enabled else "关闭"
            await self.api.qq.post_private_msg(
                msg.sender.user_id,
                rtf=MessageArray([PlainText(text=f"猫猫当前状态：{status}")]),
            )
            return

        if text == "prompt":
            await self.api.qq.post_private_msg(
                msg.sender.user_id,
                rtf=MessageArray([PlainText(text=cat_prompt)]),
            )
        elif text == "config":
            info = (
                f"模型: {llm_config['model']}\n"
                f"接口: {llm_config['base_url']}\n"
                f"温度: {llm_config['temperature']}\n"
                f"max_tokens: {llm_config['max_tokens']}\n"
                f"思考模式: {'开' if llm_config.get('thinking') else '关'}\n"
                f"冷却: {llm_config.get('cooldown', 10)}秒\n"
                f"历史上限: {llm_config.get('max_history_lines', 200)}行\n"
                f"api_key: {'已配置' if llm_config['api_key'] else '未配置'}"
            )
            await self.api.qq.post_private_msg(
                msg.sender.user_id,
                rtf=MessageArray([PlainText(text=info)]),
            )
        elif text[:10] == "set_prompt":
            cat_prompt = text[10:]
            prompt_path = os.path.join(PLUGIN_DIR, "config", "cat_prompt.txt")
            with open(prompt_path, "w", encoding="utf-8") as f:
                f.write(cat_prompt.strip())
            await self.api.qq.post_private_msg(
                msg.sender.user_id,
                rtf=MessageArray([PlainText(text="设置成功")]),
            )

    async def on_load(self):
        global llm_config, super_user, cat_prompt
        # 从 config/config.yaml 中读取配置
        config_path = os.path.join(PLUGIN_DIR, "config", "config.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}

        llm_config = {
            "api_key": config_data.get("api_key", ""),
            "base_url": config_data.get("base_url", "https://api.deepseek.com"),
            "model": config_data.get("model", "deepseek-chat"),
            "temperature": config_data.get("temperature", 1.3),
            "max_tokens": config_data.get("max_tokens", 256),
            "thinking": config_data.get("thinking", False),
            "cooldown": config_data.get("cooldown", 10),
            "reply_cooldown": config_data.get("reply_cooldown", 120),
            "reply_probability": config_data.get("reply_probability", 0.3),
            "max_history_lines": config_data.get("max_history_lines", 200),
        }
        super_user = config_data.get("manager_id", "")

        prompt_path = os.path.join(PLUGIN_DIR, "config", "cat_prompt.txt")
        with open(prompt_path, "r", encoding="utf-8") as f:
            cat_prompt = f.read()

        # 创建日志目录
        logs_dir = os.path.join(PLUGIN_DIR, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        os.makedirs(os.path.join(logs_dir, "chat_api"), exist_ok=True)

        _log.info(
            f"[CatCat] 插件已加载 v{self.version} | 模型: {llm_config['model']} @ {llm_config['base_url']}"
        )
