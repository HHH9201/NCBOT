# /home/hjh/BOT/NCBOT/common/config.py
import copy
import os
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv


def _detect_root_dir() -> Path:
    env_root = os.getenv("NCBOT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


# 项目根目录
ROOT_DIR = _detect_root_dir()
ENV_FILE = ROOT_DIR / ".env"
CONFIG_FILE = ROOT_DIR / "config.yaml"

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)


# 默认配置
DEFAULT_CONFIG = {
    "napcat": {
        "url": os.getenv("NAPCAT_URL", "http://127.0.0.1:3001"),
        "token": os.getenv("NAPCAT_TOKEN", ""),
    },
    "siliconflow": {
        "url": "https://api.siliconflow.cn/v1/chat/completions",
        "api_key": os.getenv("SILICONFLOW_API_KEY", ""),
        "model": "moonshotai/Kimi-K2-Instruct-0905",
    },
    "modelscope": {
        "api_key": os.getenv("MODELSCOPE_API_KEY", ""),
        "model": "ZhipuAI/GLM-4.7-Flash",
    },
    "backend": {
        "url": os.getenv("BACKEND_URL", "http://127.0.0.1:8978"),
    },
    "app": {
        "id": os.getenv("APP_ID", "card_sender"),
        "secret": os.getenv("APP_SECRET", ""),
    },
    "database": {
        "path": str(ROOT_DIR / "mydb" / "mydb.db"),
    },
    "paths": {
        "root": str(ROOT_DIR),
        "data_dir": str(ROOT_DIR / "data"),
    },
    "admin_qq": _split_csv(os.getenv("ADMIN_QQ")),
}

class Config:
    def __init__(self):
        self._config = copy.deepcopy(DEFAULT_CONFIG)
        self._load_config()

    def _load_config(self):
        """加载配置文件"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    user_config = yaml.safe_load(f)
                    if user_config:
                        self._merge_config(self._config, user_config)
            except Exception as e:
                print(f"[Config] 加载配置文件失败: {e}")

    def _merge_config(self, base: Dict, update: Dict):
        """递归合并配置"""
        for k, v in update.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                self._merge_config(base[k], v)
            else:
                base[k] = v

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项 (支持 'section.key' 格式)"""
        keys = key.split('.')
        value = self._config
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

# 全局单例
GLOBAL_CONFIG = Config()
