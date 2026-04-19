# /home/hjh/BOT/NCBOT/common/permissions.py
"""
群聊功能权限管理模块
支持按群号配置每个插件/功能的开关
"""
import yaml
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional
from functools import wraps

from .config import ROOT_DIR

logger = logging.getLogger(__name__)

# 权限配置文件路径
PERMISSIONS_FILE = ROOT_DIR / "config" / "group_permissions.yaml"


class GroupPermissionManager:
    """群聊权限管理器"""

    def __init__(self):
        self._config: Dict[str, Any] = {}
        self._last_mtime = 0
        self._load_config()

    def _load_config(self):
        """加载权限配置"""
        try:
            if PERMISSIONS_FILE.exists():
                mtime = os.path.getmtime(PERMISSIONS_FILE)
                if mtime > self._last_mtime:
                    with open(PERMISSIONS_FILE, 'r', encoding='utf-8') as f:
                        self._config = yaml.safe_load(f) or {}
                    self._last_mtime = mtime
                    logger.info(f"[Permission] 成功加载/更新权限配置")
            else:
                logger.warning(f"[Permission] 配置文件不存在: {PERMISSIONS_FILE}")
                self._config = self._get_default_config()
        except Exception as e:
            logger.error(f"[Permission] 加载配置失败: {e}")
            self._config = self._get_default_config()

    def _save_config(self):
        """保存权限配置"""
        try:
            PERMISSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(PERMISSIONS_FILE, 'w', encoding='utf-8') as f:
                yaml.safe_dump(
                    self._config,
                    f,
                    allow_unicode=True,
                    sort_keys=False,
                )
            self._last_mtime = os.path.getmtime(PERMISSIONS_FILE)
            logger.info("[Permission] 权限配置已保存")
        except Exception as e:
            logger.error(f"[Permission] 保存配置失败: {e}")
            raise

    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "default": {
                "plugins": {},
                "features": {}
            },
            "groups": {},
            "blacklist": [],
            "whitelist": []
        }

    def reload(self):
        """重新加载配置"""
        self._last_mtime = 0  # 强制重新加载
        self._load_config()
        logger.info("[Permission] 权限配置已重新加载")

    def _get_group_id_str(self, group_id) -> str:
        """统一处理群号格式"""
        return str(group_id).strip()

    def is_group_allowed(self, group_id) -> bool:
        """
        检查群是否被允许使用机器人

        :param group_id: 群号
        :return: True 表示允许，False 表示禁止
        """
        self._load_config()  # 检查是否需要热重载
        group_id_str = self._get_group_id_str(group_id)

        # 检查黑名单
        blacklist = self._config.get("blacklist", [])
        if group_id_str in blacklist:
            return False

        # 检查白名单（如果配置了白名单，只有白名单内的群可以使用）
        whitelist = self._config.get("whitelist", [])
        if whitelist and group_id_str not in whitelist:
            return False

        return True

    def is_plugin_enabled(self, group_id, plugin_name: str) -> bool:
        """
        检查插件在指定群是否启用

        :param group_id: 群号
        :param plugin_name: 插件名称
        :return: True 表示启用，False 表示禁用
        """
        self._load_config()  # 检查是否需要热重载
        group_id_str = self._get_group_id_str(group_id)

        # 先检查群是否被允许
        if not self.is_group_allowed(group_id):
            return False

        # 获取群的特定配置
        groups_config = self._config.get("groups", {})
        group_config = groups_config.get(group_id_str, {})

        # 检查群特定的插件配置
        group_plugins = group_config.get("plugins", {})
        if plugin_name in group_plugins:
            return group_plugins[plugin_name]

        # 回退到默认配置
        default_config = self._config.get("default", {})
        default_plugins = default_config.get("plugins", {})

        return default_plugins.get(plugin_name, True)

    def is_feature_enabled(self, group_id, plugin_name: str, feature_name: str) -> bool:
        """
        检查功能在指定群是否启用

        :param group_id: 群号
        :param plugin_name: 插件名称
        :param feature_name: 功能名称
        :return: True 表示启用，False 表示禁用
        """
        # 先检查插件是否启用
        if not self.is_plugin_enabled(group_id, plugin_name):
            return False

        group_id_str = self._get_group_id_str(group_id)

        # 获取群的特定配置
        groups_config = self._config.get("groups", {})
        group_config = groups_config.get(group_id_str, {})

        # 检查群特定的功能配置
        group_features = group_config.get("features", {})
        plugin_features = group_features.get(plugin_name, {})
        if feature_name in plugin_features:
            return plugin_features[feature_name]

        # 回退到默认配置
        default_config = self._config.get("default", {})
        default_features = default_config.get("features", {})
        plugin_default_features = default_features.get(plugin_name, {})

        return plugin_default_features.get(feature_name, True)

    def has_group_config(self, group_id) -> bool:
        """判断群是否有显式配置"""
        self._load_config()
        group_id_str = self._get_group_id_str(group_id)
        return group_id_str in self._config.get("groups", {})

    def ensure_group(self, group_id) -> Dict[str, Any]:
        """确保群配置节点存在"""
        self._load_config()
        group_id_str = self._get_group_id_str(group_id)
        groups_config = self._config.setdefault("groups", {})
        group_config = groups_config.setdefault(group_id_str, {})
        group_config.setdefault("plugins", {})
        group_config.setdefault("features", {})
        return group_config

    def set_all_plugins(self, group_id, enabled: bool):
        """为指定群批量设置所有已知插件的开关"""
        group_config = self.ensure_group(group_id)
        default_plugins = self._config.get("default", {}).get("plugins", {})
        existing_plugins = group_config.get("plugins", {})
        plugin_names = set(default_plugins) | set(existing_plugins)
        group_config["plugins"] = {name: enabled for name in plugin_names}
        self._save_config()

    def get_group_config(self, group_id) -> Dict[str, Any]:
        """
        获取指定群的完整配置

        :param group_id: 群号
        :return: 配置字典
        """
        self._load_config()
        group_id_str = self._get_group_id_str(group_id)

        # 基础配置
        default_config = self._config.get("default", {})
        groups_config = self._config.get("groups", {})
        group_specific = groups_config.get(group_id_str, {})

        # 合并配置
        result = {
            "allowed": self.is_group_allowed(group_id),
            "plugins": {},
            "features": {}
        }

        # 合并插件配置
        default_plugins = default_config.get("plugins", {})
        group_plugins = group_specific.get("plugins", {})
        all_plugins = set(default_plugins.keys()) | set(group_plugins.keys())

        for plugin in all_plugins:
            result["plugins"][plugin] = self.is_plugin_enabled(group_id, plugin)

        # 合并功能配置
        default_features = default_config.get("features", {})
        group_features = group_specific.get("features", {})

        for plugin_name in all_plugins:
            result["features"][plugin_name] = {}
            plugin_default = default_features.get(plugin_name, {})
            plugin_group = group_features.get(plugin_name, {})
            all_features = set(plugin_default.keys()) | set(plugin_group.keys())

            for feature in all_features:
                result["features"][plugin_name][feature] = self.is_feature_enabled(
                    group_id, plugin_name, feature
                )

        return result

    def list_enabled_plugins(self, group_id) -> list:
        """
        列出指定群启用的所有插件

        :param group_id: 群号
        :return: 启用的插件名称列表
        """
        config = self.get_group_config(group_id)
        return [name for name, enabled in config["plugins"].items() if enabled]


# 全局权限管理器实例
permission_manager = GroupPermissionManager()


# 装饰器工具函数
def check_group_permission(plugin_name: str, feature_name: Optional[str] = None):
    """
    权限检查装饰器

    用法:
        @check_group_permission("xydj")
        async def on_group_message(self, event): ...

        @check_group_permission("xydj", "search")
        async def search_game(self, event): ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(self, event, *args, **kwargs):
            # 获取群号
            group_id = getattr(event, 'group_id', None)
            if group_id is None:
                # 私聊消息，检查私聊权限
                if plugin_name == "ai_chat":
                    # AI 对话插件的私聊功能
                    default_config = permission_manager._config.get("default", {})
                    default_features = default_config.get("features", {})
                    ai_chat_features = default_features.get("ai_chat", {})
                    if not ai_chat_features.get("private_chat", True):
                        return None
                return await func(self, event, *args, **kwargs)

            # 检查群是否被允许
            if not permission_manager.is_group_allowed(group_id):
                logger.debug(f"[Permission] 群 {group_id} 在黑名单中或被白名单排除")
                return None

            # 检查插件是否启用
            if not permission_manager.is_plugin_enabled(group_id, plugin_name):
                logger.debug(f"[Permission] 插件 {plugin_name} 在群 {group_id} 中已禁用")
                return None

            # 检查功能是否启用
            if feature_name and not permission_manager.is_feature_enabled(group_id, plugin_name, feature_name):
                logger.debug(f"[Permission] 功能 {plugin_name}.{feature_name} 在群 {group_id} 中已禁用")
                return None

            # 权限检查通过，执行原函数
            return await func(self, event, *args, **kwargs)
        return wrapper
    return decorator


def require_plugin_enabled(plugin_name: str):
    """
    要求插件启用的装饰器（简化版）

    用法:
        @require_plugin_enabled("welcome")
        async def on_notice(self, event): ...
    """
    return check_group_permission(plugin_name)
