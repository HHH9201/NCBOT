# /home/hjh/BOT/NCBOT/common/config.py
import os
import yaml
from pathlib import Path
from typing import Dict, Any

# 项目根目录
ROOT_DIR = Path("/home/hjh/BOT/NCBOT")
CONFIG_FILE = ROOT_DIR / "config.yaml"

# 默认配置
DEFAULT_CONFIG = {
    "napcat": {
        "url": "http://101.35.164.122:3006",
        "token": "he031701"
    },
    "siliconflow": {
        "url": "https://api.siliconflow.cn/v1/chat/completions",
        "api_key": "sk-ixmsswryqnmuyifjewdetqnjewdetq",
        "model": "moonshotai/Kimi-K2-Instruct-0905"
    },
    "database": {
        "path": str(ROOT_DIR / "mydb" / "mydb.db")
    },
    "proxy": "http://127.0.0.1:7899",
    "admin_qq": ["123456789"]
}

class Config:
    def __init__(self):
        self._config = DEFAULT_CONFIG.copy()
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
