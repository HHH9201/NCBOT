import logging
import os
from typing import Any, Dict

import yaml

from .config import ROOT_DIR

logger = logging.getLogger(__name__)
PERMISSIONS_FILE = ROOT_DIR / "data" / "group_permissions.yaml"


class GroupPermissionManager:
    def __init__(self):
        self._config: Dict[str, Any] = {}
        self._last_mtime = 0.0
        self._load_config()

    def _default_config(self) -> Dict[str, Any]:
        return {
            "default": {"plugins": {}, "features": {}},
            "groups": {},
            "blacklist": [],
            "whitelist": [],
        }

    def _load_config(self):
        try:
            if not PERMISSIONS_FILE.exists():
                self._config = self._default_config()
                return

            mtime = os.path.getmtime(PERMISSIONS_FILE)
            if mtime <= self._last_mtime:
                return

            with open(PERMISSIONS_FILE, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}
            self._last_mtime = mtime
        except Exception as e:
            logger.error("[Permission] 加载配置失败: %s", e)
            self._config = self._default_config()

    def _group_key(self, group_id) -> str:
        return str(group_id).strip()

    def is_group_allowed(self, group_id) -> bool:
        self._load_config()
        group_id = self._group_key(group_id)

        blacklist = self._config.get("blacklist", [])
        if group_id in blacklist:
            return False

        whitelist = self._config.get("whitelist", [])
        return not whitelist or group_id in whitelist

    def is_plugin_enabled(self, group_id, plugin_name: str) -> bool:
        self._load_config()
        if not self.is_group_allowed(group_id):
            return False

        group_id = self._group_key(group_id)
        groups_config = self._config.get("groups", {})
        group_plugins = groups_config.get(group_id, {}).get("plugins", {})
        if plugin_name in group_plugins:
            return bool(group_plugins[plugin_name])

        default_plugins = self._config.get("default", {}).get("plugins", {})
        return bool(default_plugins.get(plugin_name, True))

    def has_group_config(self, group_id) -> bool:
        self._load_config()
        group_id = self._group_key(group_id)
        return group_id in self._config.get("groups", {})

    def set_all_plugins(self, group_id, enabled: bool):
        self._load_config()
        group_id = self._group_key(group_id)
        groups_config = self._config.setdefault("groups", {})
        group_config = groups_config.setdefault(group_id, {})
        default_plugins = self._config.get("default", {}).get("plugins", {})
        existing_plugins = group_config.get("plugins", {})
        plugin_names = set(default_plugins) | set(existing_plugins)
        group_config["plugins"] = {name: enabled for name in plugin_names}
        PERMISSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PERMISSIONS_FILE, "w", encoding="utf-8") as f:
            yaml.safe_dump(self._config, f, allow_unicode=True, sort_keys=False)
        self._last_mtime = os.path.getmtime(PERMISSIONS_FILE)


permission_manager = GroupPermissionManager()
