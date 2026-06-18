# main.py - 牛子PK插件，适配 NcatBot5
import asyncio
import re
from pathlib import Path

import json
import yaml

from ncatbot.plugin import BasePlugin
from ncatbot.event.qq import GroupMessageEvent, PrivateMessageEvent
from ncatbot.types import PlainText, MessageArray
from ncatbot.core import registrar
from ncatbot.utils.logger import get_log

from .src.main import KEYWORDS, message_processor as chinchin

_log = get_log()

# 插件目录的绝对路径
PLUGIN_DIR = Path(__file__).resolve().parent
# 启用状态配置文件
CONF_PATH = PLUGIN_DIR / "data" / "chinchin.json"

USAGE = """

指令表:
    开启(关闭)牛子秘境
    牛子帮助
    启用(禁用)牛子pk
    牛子
    pk @用户
    🔒(suo/嗦/锁)我
    🔒(suo/嗦/锁) @用户
    打胶
    看他牛子(看看牛子) @用户
    注册牛子
    牛子排名(牛子排行)
    牛友(牛子好友/牛子朋友)
    关注牛子(添加牛友)
    取关牛子(删除牛友)
    牛子转生
    牛子成就
    牛子仙境
    牛子修炼(牛子练功/牛子修仙)

""".strip()


def _load_enablelist():
    if CONF_PATH.is_file():
        try:
            return json.loads(CONF_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"all": False, "group": []}


def _save_enablelist(data):
    CONF_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONF_PATH.write_text(json.dumps(data), encoding="utf-8")


# 收集所有业务命令关键字（不含管理命令）
_ALL_BUSINESS_KEYWORDS = []
for _k in [
    "chinchin", "pk", "lock_me", "lock", "glue", "see_chinchin",
    "sign_up", "ranking", "rebirth", "badge", "farm", "farm_start",
    "friends", "friends_add", "friends_delete", "help",
]:
    _ALL_BUSINESS_KEYWORDS.extend(KEYWORDS.get(_k, []))

# 管理命令关键字
_ENABLE_CMDS = {"启用牛子pk", "开启牛子pk", "启用dicky-pk", "开启dicky-pk"}
_DISABLE_CMDS = {"禁用牛子pk", "关闭牛子pk", "禁用dicky-pk", "关闭dicky-pk"}

_CQ_AT_PATTERN = re.compile(r"\[CQ:at,qq=(\d+)\]")
_CQ_PATTERN = re.compile(r"\[CQ:[^\]]+\]")


def _match_business_command(text: str) -> bool:
    """检查文本是否匹配任何业务命令关键字（模糊匹配）"""
    text = text.strip()
    for keyword in _ALL_BUSINESS_KEYWORDS:
        if text.startswith(keyword):
            return True
    return False


class DickyPK(BasePlugin):
    name = "dicky_pk"
    version = "1.0.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.enablelist = _load_enablelist()
        self.super_users = set()

    def _is_enabled(self, group_id) -> bool:
        if not self.enablelist["all"]:
            return False
        return int(group_id) in self.enablelist["group"]

    def _set_enable(self, group_id, en: bool):
        gid = int(group_id)
        if en:
            if gid not in self.enablelist["group"]:
                self.enablelist["group"].append(gid)
        else:
            self.enablelist["group"] = [g for g in self.enablelist["group"] if g != gid]
        _save_enablelist(self.enablelist)

    @staticmethod
    def _get_at_id(raw_message: str):
        """从原始消息中提取第一个 at 的 QQ 号"""
        match = _CQ_AT_PATTERN.search(raw_message)
        if match:
            return int(match.group(1))
        return None

    @staticmethod
    def _get_plain_text(raw_message: str) -> str:
        """去除 CQ 码，获取纯文本"""
        return _CQ_PATTERN.sub("", raw_message).strip()

    def _make_send_message(self):
        """创建 send_message 回调，供 message_processor 使用"""
        async def _send(qq: int, group: int, message: str):
            try:
                await self.api.qq.post_group_msg(group_id=group, text=message)
            except Exception as e:
                _log.error(f"[dicky_pk] 发送消息失败: {e}")

        def send_message(qq: int, group: int, message: str):
            loop = asyncio.get_running_loop()
            loop.create_task(_send(qq, group, message))

        return send_message

    @staticmethod
    def _make_get_at_segment():
        """创建 get_at_segment 回调"""
        def get_at_segment(qq: int):
            return f"[CQ:at,qq={qq}]"
        return get_at_segment

    def _dicky_run(self, msg: str, event: GroupMessageEvent):
        uid = int(event.user_id)
        gid = int(event.group_id)
        at_id = self._get_at_id(event.raw_message)
        sender = event.sender
        nickname = sender.card if sender.card else sender.nickname
        chinchin(
            msg, uid, gid, at_id, nickname, True,
            self._make_get_at_segment(), self._make_send_message()
        )

    @registrar.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent):
        text = self._get_plain_text(event.raw_message)
        if not text:
            return

        # 管理命令：启用/禁用牛子pk（群管理/群主/超级用户）
        role = getattr(event.sender, "role", "") or ""
        is_admin = role in ("owner", "admin") or str(event.user_id) in self.super_users
        if is_admin:
            if text in _ENABLE_CMDS:
                if not self.enablelist["all"]:
                    return
                self._set_enable(event.group_id, True)
                await self.api.qq.post_group_msg(
                    group_id=event.group_id,
                    rtf=MessageArray([PlainText(text="已启用群聊小游戏: Dicky-PK")]),
                )
                return
            if text in _DISABLE_CMDS:
                if not self.enablelist["all"]:
                    return
                self._set_enable(event.group_id, False)
                await self.api.qq.post_group_msg(
                    group_id=event.group_id,
                    rtf=MessageArray([PlainText(text="已禁用群聊小游戏: Dicky-PK")]),
                )
                return

        # 业务命令
        if not self._is_enabled(event.group_id):
            return
        if not _match_business_command(text):
            return
        # 牛子帮助特殊处理：发送详细指令表
        if text.startswith("牛子帮助"):
            await self.api.qq.post_group_msg(
                group_id=event.group_id,
                rtf=MessageArray([PlainText(text=USAGE)]),
            )
            return
        self._dicky_run(text, event)

    @registrar.on_private_message()
    async def on_private_message(self, event: PrivateMessageEvent):
        text = self._get_plain_text(event.raw_message)
        if not text:
            return
        if str(event.user_id) not in self.super_users:
            return
        if text == "开启牛子秘境":
            self.enablelist["all"] = True
            _save_enablelist(self.enablelist)
            await self.api.qq.post_private_msg(
                user_id=event.user_id,
                rtf=MessageArray([PlainText(text="牛子秘境已开启.")]),
            )
        elif text == "关闭牛子秘境":
            self.enablelist["group"].clear()
            self.enablelist["all"] = False
            _save_enablelist(self.enablelist)
            await self.api.qq.post_private_msg(
                user_id=event.user_id,
                rtf=MessageArray([PlainText(text="牛子秘境已关闭.")]),
            )
        elif text == "牛子帮助":
            await self.api.qq.post_private_msg(
                user_id=event.user_id,
                rtf=MessageArray([PlainText(text=USAGE)]),
            )

    async def on_load(self):
        # 从 NCBOT 配置读取超级用户（root 字段）
        try:
            # data/plugins/dicky_pk -> parents[2] = data
            root_dir = PLUGIN_DIR.parents[2]
            config_path = root_dir / "config.yaml"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                root = cfg.get("root", "")
                if root:
                    self.super_users.add(str(root))
        except Exception as e:
            _log.warning(f"[dicky_pk] 读取超级用户配置失败: {e}")
        _log.info(
            f"[dicky_pk] 插件已加载 v{self.version} | 超级用户: {self.super_users or '无'}"
        )
