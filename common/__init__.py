# /home/hjh/BOT/NCBOT/common/__init__.py
from .config import GLOBAL_CONFIG, Config
from .napcat import napcat_service, NapCatService
from .ai import ai_service, AIService
from .db import db_manager, DBManager

__all__ = [
    "GLOBAL_CONFIG", "Config",
    "napcat_service", "NapCatService",
    "ai_service", "AIService",
    "db_manager", "DBManager"
]
