from ncatbot.plugin import BasePlugin
from ncatbot.core import GroupMessage
from ncatbot.plugin_system.builtin_plugin.unified_registry import UnifiedRegistry
import asyncio
from common.napcat import napcat_service

class CasePlugin(BasePlugin):
    name = "case"
    version = "1.0"

    async def _send_fake_forward_msg(self, group_id: int, content: str):
        """真正发消息的异步实现"""
        try:
            node = napcat_service.construct_node("10000", "系统消息", content)
            success = await napcat_service.send_group_forward_msg(group_id, [node])
            if success:
                print(f"[case] 成功发送伪造合并转发消息到群 {group_id}")
            else:
                print(f"[case] 发送失败")
        except Exception as e:
            print(f"[case] 发送伪造合并转发消息失败: {e}")

    def on_group_message(self, message: GroupMessage):
        """框架自动收录的群消息回调（同步函数）"""
        print(f"[case] 收到群消息: raw_message={message.raw_message!r}, chain={message.chain}")
        # 从消息链里提取纯文本
        text = "".join(
            seg.data.get("text", "") for seg in message.chain if seg.type == "text"
        ).strip()
        print(f"[case] 提取到的纯文本: {text!r}")
        if text == "1":
            asyncio.create_task(self._send_fake_forward_msg(message.group_id, "2"))
        else:
            print(f"[case] 文本不匹配，跳过")

    def on_load(self):
        """插件加载时注册群消息回调"""
        UnifiedRegistry().register_group_message(self.on_group_message)
        print("[case] 群消息回调已注册")

case = CasePlugin(None)