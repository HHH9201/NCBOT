# /home/hjh/BOT/NCBOT/common/db.py
import sqlite3
import logging
from typing import Optional
from .config import GLOBAL_CONFIG

class DBManager:
    """
    通用数据库管理器 (SQLite)
    """
    
    @property
    def db_path(self) -> str:
        return GLOBAL_CONFIG.get("database.path")

    def get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        try:
            return sqlite3.connect(self.db_path)
        except Exception as e:
            logging.error(f"[DB] 连接数据库失败: {e}")
            raise

    def execute_query(self, query: str, params: tuple = ()) -> Optional[list]:
        """执行查询"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                return cursor.fetchall()
        except Exception as e:
            logging.error(f"[DB] 执行查询失败: {e} | SQL: {query}")
            return None

    def execute_update(self, query: str, params: tuple = ()) -> bool:
        """执行更新/插入/删除"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"[DB] 执行更新失败: {e} | SQL: {query}")
            return False

# 全局单例
db_manager = DBManager()
