# config.py - Epic 限免插件配置管理
import yaml
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PLUGIN_DIR / "config.yaml"

_DEFAULT_CONFIG = {
    "proxy_type": None,
    "proxy_host": "127.0.0.1",
    "proxy_port": 7890,
    "proxy_username": None,
    "proxy_password": None,
    "superuser_only": False,
}


def load_config() -> dict:
    """加载配置文件，不存在则使用默认值创建"""
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(_DEFAULT_CONFIG, f, allow_unicode=True, sort_keys=False)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return dict(_DEFAULT_CONFIG)


class ScopedConfig:
    """Epic 限免配置"""

    def __init__(self, data: dict):
        self.proxy_type = data.get("proxy_type")
        self.proxy_host = data.get("proxy_host", "127.0.0.1")
        self.proxy_port = data.get("proxy_port", 7890)
        self.proxy_username = data.get("proxy_username")
        self.proxy_password = data.get("proxy_password")
        self.superuser_only = data.get("superuser_only", False)


plugin_config = ScopedConfig(load_config())
