# /home/hjh/BOT/NCBOT/common/db_permissions.py
"""
基于 Turso (libSQL) 数据库的资源管理模块
表结构：
- resources: 资源收集表 - 存储网盘资源链接
- game_resources: 游戏资源表 - 存储游戏资源
- ntqq_key: key 表 - 存储 cookie 等密钥
"""
import os
import json
import logging
import asyncio
import aiohttp
import time
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

# 搜索缓存: {cache_key: (result, timestamp)}
_search_cache: Dict[str, Any] = {}
_cache_ttl = 300  # 缓存有效期 5 分钟
_max_cache_size = 100  # 最大缓存条目数

# 统计缓存: {cache_key: (result, timestamp)}
_stats_cache: Dict[str, Any] = {}
_stats_cache_ttl = 300  # 统计缓存 5 分钟

# Turso 数据库配置
TURSO_URL = "https://weixin-hhh9201.aws-ap-northeast-1.turso.io"
TURSO_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzUxMDYxODgsImlkIjoiMDE5ZDRjOTItYzIwMS03ZWNjLTkyNjctOGZkZjlhZmFhZDEyIiwicmlkIjoiZjQ1YTdiNGUtNzAwNC00OTQ1LTkyMDItODEwZTlkYzk3ZDcxIn0.quBZ92hjipfsOXLEl32Y0nYaeHTkFqr_vBiLL4b27on5Jg_tRP_z1KfPVWJz9p3KeousGT11dz4S1ks1kLM8AQ"


class TursoResourceManager:
    """基于 Turso 数据库的资源管理器 - 使用 HTTP API"""

    def __init__(self, url: str = TURSO_URL, auth_token: str = TURSO_TOKEN):
        self.url = url.rstrip('/')
        self.auth_token = auth_token
        self._session: Optional[aiohttp.ClientSession] = None
        self._local_mode = False  # 本地回退模式
        self._initialized = False

    async def initialize(self):
        """异步初始化"""
        if self._initialized:
            return

        try:
            self._session = aiohttp.ClientSession()
            # 测试连接
            await self._execute_sql("SELECT 1")
            # 初始化表
            await self._init_tables()
            logger.info("[DB Resource] Turso HTTP API 连接成功")
        except Exception as e:
            logger.error(f"[DB Resource] Turso 连接失败: {e}，切换到本地模式")
            self._local_mode = True
            if self._session:
                await self._session.close()
                self._session = None
            self._init_local_storage()

        self._initialized = True

    async def _init_tables(self):
        """初始化数据库表 (Turso)"""
        # 创建资源收集表 - 存储网盘资源链接
        await self._execute_sql("""
            CREATE TABLE IF NOT EXISTS resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                quark_link TEXT,
                uc_link TEXT,
                baidu_link TEXT,
                aliyun_link TEXT,
                tianyi_link TEXT,
                xunlei_link TEXT,
                group_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 创建游戏资源表 - 存储游戏资源
        await self._execute_sql("""
            CREATE TABLE IF NOT EXISTS game_resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT,
                genre TEXT,
                zh_name TEXT UNIQUE NOT NULL,
                en_name TEXT,
                image_url TEXT,
                version TEXT,
                details TEXT,
                password TEXT,
                baidu_url TEXT,
                baidu_code TEXT,
                quark_url TEXT,
                quark_code TEXT,
                uc_url TEXT,
                uc_code TEXT,
                online_url TEXT,
                online_code TEXT,
                patch_url TEXT,
                online_at TEXT,
                detail_url TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                pan123_url TEXT,
                pan123_code TEXT,
                mobile_url TEXT,
                mobile_code TEXT,
                tianyi_url TEXT,
                tianyi_code TEXT,
                xunlei_url TEXT,
                xunlei_code TEXT
            )
        """)

        # 创建 key 表 - 存储 cookie 等密钥
        await self._execute_sql("""
            CREATE TABLE IF NOT EXISTS ntqq_key (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                xydj TEXT,
                app_id TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 初始化 key 表（插入默认空记录）
        await self._init_key_table()

        # 创建索引优化查询性能
        await self._init_indexes()

        # 初始化 FTS5 全文搜索
        await self._init_fts5()

    async def _init_fts5(self):
        """初始化 FTS5 全文搜索虚拟表和触发器"""
        try:
            # 1. 创建 FTS5 虚拟表
            # 使用 unicode61 分词器以支持中文搜索
            await self._execute_sql("""
                CREATE VIRTUAL TABLE IF NOT EXISTS game_resources_fts USING fts5(
                    zh_name,
                    en_name,
                    content='game_resources',
                    content_rowid='id',
                    tokenize='unicode61'
                )
            """)

            # 2. 创建同步触发器
            # INSERT 触发器
            await self._execute_sql("""
                CREATE TRIGGER IF NOT EXISTS game_resources_ai AFTER INSERT ON game_resources BEGIN
                    INSERT INTO game_resources_fts(rowid, zh_name, en_name) VALUES (new.id, new.zh_name, new.en_name);
                END
            """)

            # DELETE 触发器
            await self._execute_sql("""
                CREATE TRIGGER IF NOT EXISTS game_resources_ad AFTER DELETE ON game_resources BEGIN
                    INSERT INTO game_resources_fts(game_resources_fts, rowid, zh_name, en_name) VALUES('delete', old.id, old.zh_name, old.en_name);
                END
            """)

            # UPDATE 触发器
            await self._execute_sql("""
                CREATE TRIGGER IF NOT EXISTS game_resources_au AFTER UPDATE ON game_resources BEGIN
                    INSERT INTO game_resources_fts(game_resources_fts, rowid, zh_name, en_name) VALUES('delete', old.id, old.zh_name, old.en_name);
                    INSERT INTO game_resources_fts(rowid, zh_name, en_name) VALUES (new.id, new.zh_name, new.en_name);
                END
            """)

            # 3. 同步现有数据（如果 FTS5 表为空）
            count_res = await self._query("SELECT COUNT(*) FROM game_resources_fts")
            if count_res and count_res[0][0] == 0:
                logger.info("[DB Resource] 正在同步现有数据到 FTS5 虚拟表...")
                await self._execute_sql("""
                    INSERT INTO game_resources_fts(rowid, zh_name, en_name)
                    SELECT id, zh_name, en_name FROM game_resources
                """)
                logger.info("[DB Resource] FTS5 数据同步完成")

            logger.info("[DB Resource] FTS5 全文搜索初始化完成")
        except Exception as e:
            logger.warning(f"[DB Resource] 初始化 FTS5 失败: {e}")

    async def _init_indexes(self):
        """初始化索引，优化查询性能"""
        try:
            # game_resources 索引
            await self._execute_sql("CREATE INDEX IF NOT EXISTS idx_game_resources_zh_name ON game_resources(zh_name)")
            await self._execute_sql("CREATE INDEX IF NOT EXISTS idx_game_resources_en_name ON game_resources(en_name)")
            await self._execute_sql("CREATE INDEX IF NOT EXISTS idx_game_resources_updated_at ON game_resources(updated_at DESC)")
            # 核心优化：为爬虫查重添加索引
            await self._execute_sql("CREATE INDEX IF NOT EXISTS idx_game_resources_detail_url ON game_resources(detail_url)")
            
            # game_name 索引 (优化 game_name 表的高频查询)
            await self._execute_sql("CREATE INDEX IF NOT EXISTS idx_game_name_zh_name ON game_name(zh_name)")
            
            # users 索引
            await self._execute_sql("CREATE INDEX IF NOT EXISTS idx_users_openid ON users(openid)")
            await self._execute_sql("CREATE INDEX IF NOT EXISTS idx_users_qq_id ON users(qq_id)")
            await self._execute_sql("CREATE INDEX IF NOT EXISTS idx_users_virtual_id ON users(virtual_id)")
            
            # resources 索引
            await self._execute_sql("CREATE INDEX IF NOT EXISTS idx_resources_name ON resources(name)")
            await self._execute_sql("CREATE INDEX IF NOT EXISTS idx_resources_created_at ON resources(created_at DESC)")
            
            # ntqq_key 索引
            await self._execute_sql("CREATE INDEX IF NOT EXISTS idx_ntqq_key_name ON ntqq_key(name)")
            
            logger.info("[DB Resource] 数据库索引初始化完成")
        except Exception as e:
            logger.warning(f"[DB Resource] 初始化索引失败: {e}")

    async def _init_key_table(self):
        """初始化 key 表，插入默认记录"""
        try:
            # 检查是否已有记录
            result = await self._query("SELECT COUNT(*) FROM ntqq_key")
            count = result[0][0] if result else 0
            
            if count == 0:
                # 插入默认空记录（id=1）
                await self._execute(
                    "INSERT INTO ntqq_key (id, xydj, updated_at) VALUES (1, '', datetime('now'))"
                )
                logger.info("[DB Resource] 初始化 key 表完成")
        except Exception as e:
            logger.warning(f"[DB Resource] 初始化 key 表失败: {e}")

    def _init_local_storage(self):
        """初始化本地存储（回退模式）"""
        import sqlite3
        from pathlib import Path

        db_path = Path("/home/hjh/BOT/NCBOT/data/resources.db")
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self._local_conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._local_cursor = self._local_conn.cursor()

        # 创建资源收集表
        self._local_cursor.execute("""
            CREATE TABLE IF NOT EXISTS resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                quark_link TEXT,
                uc_link TEXT,
                baidu_link TEXT,
                aliyun_link TEXT,
                tianyi_link TEXT,
                xunlei_link TEXT,
                group_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 创建游戏资源表
        self._local_cursor.execute("""
            CREATE TABLE IF NOT EXISTS game_resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT,
                genre TEXT,
                zh_name TEXT UNIQUE NOT NULL,
                en_name TEXT,
                image_url TEXT,
                version TEXT,
                details TEXT,
                password TEXT,
                baidu_url TEXT,
                baidu_code TEXT,
                quark_url TEXT,
                quark_code TEXT,
                uc_url TEXT,
                uc_code TEXT,
                online_url TEXT,
                online_code TEXT,
                patch_url TEXT,
                online_at TEXT,
                detail_url TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                pan123_url TEXT,
                pan123_code TEXT,
                mobile_url TEXT,
                mobile_code TEXT,
                tianyi_url TEXT,
                tianyi_code TEXT,
                xunlei_url TEXT,
                xunlei_code TEXT
            )
        """)

        # 创建 key 表 - 存储 cookie 等密钥
        self._local_cursor.execute("""
            CREATE TABLE IF NOT EXISTS ntqq_key (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                xydj TEXT,
                app_id TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 初始化 key 表（插入默认空记录）
        self._local_cursor.execute("SELECT COUNT(*) FROM ntqq_key")
        count = self._local_cursor.fetchone()[0]
        if count == 0:
            self._local_cursor.execute(
                "INSERT INTO ntqq_key (id, xydj, updated_at) VALUES (1, '', datetime('now'))"
            )

        self._local_conn.commit()

        logger.info("[DB Resource] 本地 SQLite 数据库初始化完成")

    async def _execute_sql(self, sql: str, args: list = None):
        """执行 SQL 语句 (Turso HTTP API)"""
        if args is None:
            args = []

        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json"
        }

        # 构建参数
        params = []
        for arg in args:
            if isinstance(arg, bool):
                params.append({"type": "integer", "value": str(int(arg))})
            elif isinstance(arg, int):
                params.append({"type": "integer", "value": str(arg)})
            elif isinstance(arg, str):
                params.append({"type": "text", "value": arg})
            else:
                params.append({"type": "text", "value": str(arg)})

        payload = {
            "requests": [
                {
                    "type": "execute",
                    "stmt": {
                        "sql": sql,
                        "args": params
                    }
                }
            ]
        }

        async with self._session.post(
            f"{self.url}/v2/pipeline",
            headers=headers,
            json=payload
        ) as response:
            if response.status != 200:
                text = await response.text()
                raise Exception(f"Turso API error: {response.status} - {text}")

            data = await response.json()

            if "results" in data and len(data["results"]) > 0:
                result = data["results"][0]
                if "error" in result:
                    raise Exception(f"SQL error: {result['error']}")
                return result
            return {}

    async def _query_sql(self, sql: str, args: list = None) -> List:
        """查询 SQL (Turso HTTP API)"""
        result = await self._execute_sql(sql, args)

        if "response" in result and "result" in result["response"]:
            result_data = result["response"]["result"]
            if "rows" in result_data:
                # 解析行数据
                rows = []
                for row_data in result_data["rows"]:
                    row = []
                    for cell in row_data:
                        if cell.get("type") == "integer":
                            row.append(int(cell.get("value", 0)))
                        elif cell.get("type") == "text":
                            row.append(cell.get("value"))
                        elif cell.get("type") == "null":
                            row.append(None)
                        else:
                            row.append(cell.get("value"))
                    rows.append(row)
                return rows
        return []

    async def _execute(self, sql: str, params: tuple = ()):
        """执行 SQL 语句"""
        if self._local_mode:
            self._local_cursor.execute(sql, params)
            self._local_conn.commit()
            return self._local_cursor
        else:
            # 转换参数格式
            args = list(params)
            return await self._execute_sql(sql, args)

    async def _query(self, sql: str, params: tuple = ()) -> List:
        """查询数据"""
        if self._local_mode:
            self._local_cursor.execute(sql, params)
            return self._local_cursor.fetchall()
        else:
            args = list(params)
            return await self._query_sql(sql, args)

    # ========== 资源收集相关方法 ==========
    async def save_resource(self, name: str, links: Dict[str, Optional[str]],
                           group_id: str) -> int:
        """保存网盘资源到数据库

        按名字去重，如果已存在则更新链接

        Args:
            name: 资源名称
            links: 包含各种网盘链接的字典
            group_id: 群号

        Returns:
            记录ID
        """
        await self.initialize()

        # 先检查是否已存在相同名称的资源
        check_sql = "SELECT id, quark_link, uc_link, baidu_link, aliyun_link, tianyi_link, xunlei_link FROM resources WHERE name = ?"

        if self._local_mode:
            self._local_cursor.execute(check_sql, (name,))
            existing = self._local_cursor.fetchone()
        else:
            existing_result = await self._query(check_sql, (name,))
            existing = existing_result[0] if existing_result else None

        if existing:
            # 已存在，更新链接（只更新不为空的链接）
            resource_id = existing[0]
            existing_links = {
                'quark': existing[1],
                'uc': existing[2],
                'baidu': existing[3],
                'aliyun': existing[4],
                'tianyi': existing[5],
                'xunlei': existing[6]
            }

            # 合并链接：新链接优先，如果新链接为空则保留旧链接
            merged_links = {
                'quark': links.get('quark') or existing_links['quark'],
                'uc': links.get('uc') or existing_links['uc'],
                'baidu': links.get('baidu') or existing_links['baidu'],
                'aliyun': links.get('aliyun') or existing_links['aliyun'],
                'tianyi': links.get('tianyi') or existing_links['tianyi'],
                'xunlei': links.get('xunlei') or existing_links['xunlei']
            }

            update_sql = """
                UPDATE resources SET
                    quark_link = ?,
                    uc_link = ?,
                    baidu_link = ?,
                    aliyun_link = ?,
                    tianyi_link = ?,
                    xunlei_link = ?
                WHERE id = ?
            """
            update_params = (
                merged_links['quark'],
                merged_links['uc'],
                merged_links['baidu'],
                merged_links['aliyun'],
                merged_links['tianyi'],
                merged_links['xunlei'],
                resource_id
            )

            if self._local_mode:
                self._local_cursor.execute(update_sql, update_params)
                self._local_conn.commit()
            else:
                await self._execute(update_sql, update_params)

            logger.info(f"[DB Resource] 更新资源链接: {name[:30]}...")
            return resource_id
        else:
            # 不存在，插入新记录
            insert_sql = """
                INSERT INTO resources (name, quark_link, uc_link, baidu_link,
                                      aliyun_link, tianyi_link, xunlei_link,
                                      group_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            insert_params = (
                name,
                links.get('quark'),
                links.get('uc'),
                links.get('baidu'),
                links.get('aliyun'),
                links.get('tianyi'),
                links.get('xunlei'),
                str(group_id)
            )

            if self._local_mode:
                self._local_cursor.execute(insert_sql, insert_params)
                self._local_conn.commit()
                return self._local_cursor.lastrowid
            else:
                await self._execute(insert_sql, insert_params)
                result = await self._query("SELECT last_insert_rowid()")
                resource_id = result[0][0] if result else 0
                logger.info(f"[DB Resource] 新增资源: {name[:30]}...")
                return resource_id

    async def get_resources(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """获取资源列表

        Args:
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            资源列表
        """
        await self.initialize()

        sql = """
            SELECT id, name, quark_link, uc_link, baidu_link,
                   aliyun_link, tianyi_link, xunlei_link,
                   group_id, created_at
            FROM resources
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """

        if self._local_mode:
            self._local_cursor.execute(sql, (limit, offset))
            rows = self._local_cursor.fetchall()
        else:
            rows = await self._query(sql, (limit, offset))

        resources = []
        for row in rows:
            resources.append({
                "id": row[0],
                "name": row[1],
                "quark_link": row[2],
                "uc_link": row[3],
                "baidu_link": row[4],
                "aliyun_link": row[5],
                "tianyi_link": row[6],
                "xunlei_link": row[7],
                "group_id": row[8],
                "created_at": row[9]
            })

        return resources

    async def search_resources(self, keyword: str, limit: int = 50) -> List[Dict[str, Any]]:
        """搜索资源

        Args:
            keyword: 搜索关键词
            limit: 返回数量限制

        Returns:
            匹配的资源列表
        """
        await self.initialize()

        sql = """
            SELECT id, name, quark_link, uc_link, baidu_link,
                   aliyun_link, tianyi_link, xunlei_link,
                   group_id, created_at
            FROM resources
            WHERE name LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
        """

        search_pattern = f"%{keyword}%"

        if self._local_mode:
            self._local_cursor.execute(sql, (search_pattern, limit))
            rows = self._local_cursor.fetchall()
        else:
            rows = await self._query(sql, (search_pattern, limit))

        resources = []
        for row in rows:
            resources.append({
                "id": row[0],
                "name": row[1],
                "quark_link": row[2],
                "uc_link": row[3],
                "baidu_link": row[4],
                "aliyun_link": row[5],
                "tianyi_link": row[6],
                "xunlei_link": row[7],
                "group_id": row[8],
                "created_at": row[9]
            })

        return resources

    async def delete_resource(self, resource_id: int):
        """删除资源

        Args:
            resource_id: 资源ID
        """
        await self.initialize()

        sql = "DELETE FROM resources WHERE id = ?"

        if self._local_mode:
            self._local_cursor.execute(sql, (resource_id,))
            self._local_conn.commit()
        else:
            await self._execute(sql, (resource_id,))

        logger.info(f"[DB Resource] 删除资源 ID: {resource_id}")

    async def get_resource_stats(self) -> Dict[str, Any]:
        """获取资源统计信息（带缓存优化）

        Returns:
            统计信息字典
        """
        global _stats_cache

        cache_key = "resource_stats"
        now = time.time()

        # 检查缓存
        if cache_key in _stats_cache:
            result, timestamp = _stats_cache[cache_key]
            if now - timestamp < _stats_cache_ttl:
                logger.debug(f"[DB Cache] 统计缓存命中")
                return result

        await self.initialize()

        # 使用单次查询获取所有统计信息，减少数据库往返
        combined_sql = """
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN quark_link IS NOT NULL THEN 1 ELSE 0 END) as quark,
                SUM(CASE WHEN uc_link IS NOT NULL THEN 1 ELSE 0 END) as uc,
                SUM(CASE WHEN baidu_link IS NOT NULL THEN 1 ELSE 0 END) as baidu,
                SUM(CASE WHEN aliyun_link IS NOT NULL THEN 1 ELSE 0 END) as aliyun,
                SUM(CASE WHEN tianyi_link IS NOT NULL THEN 1 ELSE 0 END) as tianyi,
                SUM(CASE WHEN xunlei_link IS NOT NULL THEN 1 ELSE 0 END) as xunlei
            FROM resources
        """

        if self._local_mode:
            self._local_cursor.execute(combined_sql)
            row = self._local_cursor.fetchone()
            total, quark_count, uc_count, baidu_count, aliyun_count, tianyi_count, xunlei_count = row
        else:
            result = await self._query(combined_sql)
            if result:
                row = result[0]
                total, quark_count, uc_count, baidu_count, aliyun_count, tianyi_count, xunlei_count = row
            else:
                total = quark_count = uc_count = baidu_count = aliyun_count = tianyi_count = xunlei_count = 0

        result = {
            "total": total or 0,
            "quark": quark_count or 0,
            "uc": uc_count or 0,
            "baidu": baidu_count or 0,
            "aliyun": aliyun_count or 0,
            "tianyi": tianyi_count or 0,
            "xunlei": xunlei_count or 0
        }

        # 存入缓存
        _stats_cache[cache_key] = (result, now)
        return result

    # ========== 游戏资源相关方法 ==========
    async def get_game_resource(self, name: str) -> Optional[Dict[str, Any]]:
        """从数据库获取游戏资源

        Args:
            name: 游戏名称

        Returns:
            游戏资源数据，不存在则返回None
        """
        await self.initialize()

        sql = """
            SELECT id, platform, genre, zh_name, en_name, image_url, version, details, 
                   password, baidu_url, baidu_code, quark_url, quark_code, uc_url, uc_code,
                   online_url, online_code, patch_url, online_at, detail_url, updated_at,
                   pan123_url, pan123_code, mobile_url, mobile_code, tianyi_url, tianyi_code,
                   xunlei_url, xunlei_code
            FROM game_resources 
            INDEXED BY idx_game_resources_zh_name
            WHERE zh_name = ?
        """

        if self._local_mode:
            self._local_cursor.execute(sql, (name,))
            row = self._local_cursor.fetchone()
        else:
            result = await self._query(sql, (name,))
            row = result[0] if result else None

        if row:
            return {
                "id": row[0],
                "platform": row[1],
                "genre": row[2],
                "zh_name": row[3],
                "en_name": row[4],
                "image_url": row[5],
                "version": row[6],
                "details": row[7],
                "password": row[8],
                "baidu_url": row[9],
                "baidu_code": row[10],
                "quark_url": row[11],
                "quark_code": row[12],
                "uc_url": row[13],
                "uc_code": row[14],
                "online_url": row[15],
                "online_code": row[16],
                "patch_url": row[17],
                "online_at": row[18],
                "detail_url": row[19],
                "updated_at": row[20],
                "pan123_url": row[21],
                "pan123_code": row[22],
                "mobile_url": row[23],
                "mobile_code": row[24],
                "tianyi_url": row[25],
                "tianyi_code": row[26],
                "xunlei_url": row[27],
                "xunlei_code": row[28]
            }
        return None

    async def save_game_resource(self, name: str, data: Dict[str, Any]) -> bool:
        """保存或更新游戏资源到数据库

        Args:
            name: 游戏名称
            data: 游戏资源数据

        Returns:
            是否成功
        """
        await self.initialize()

        now = datetime.now().isoformat()

        # 定义所有可能的字段 (对应云端数据库字段)
        all_fields = [
            'platform', 'genre', 'en_name', 'image_url', 'version', 'details',
            'password', 'baidu_url', 'baidu_code', 'quark_url', 'quark_code',
            'uc_url', 'uc_code', 'online_url', 'online_code', 'patch_url',
            'online_at', 'detail_url', 'pan123_url', 'pan123_code',
            'mobile_url', 'mobile_code', 'tianyi_url', 'tianyi_code',
            'xunlei_url', 'xunlei_code'
        ]

        try:
            # 优化：优先根据 detail_url 查找，且合并查询以减少网络往返和扫描风险
            detail_url = data.get('detail_url')
            existing = None
            
            if self._local_mode:
                # 使用单次查询同时匹配 detail_url 和 zh_name，并利用索引
                query_sql = "SELECT id, zh_name FROM game_resources WHERE detail_url = ? OR zh_name = ? LIMIT 1"
                self._local_cursor.execute(query_sql, (detail_url, name))
                existing = self._local_cursor.fetchone()
                
                if existing:
                    resource_id, db_zh_name = existing
                    # 更新现有记录
                    update_fields = []
                    update_values = []
                    for field in all_fields:
                        if field in data:
                            update_fields.append(f"{field} = ?")
                            update_values.append(data.get(field))
                    update_fields.append("updated_at = ?")
                    update_values.append(now)
                    update_values.append(resource_id)  # WHERE 条件
                    
                    sql = f"UPDATE game_resources SET {', '.join(update_fields)} WHERE id = ?"
                    self._local_cursor.execute(sql, update_values)
                else:
                    # 插入新记录
                    insert_fields = ['zh_name', 'updated_at']
                    insert_values = [name, now]
                    for field in all_fields:
                        if field in data:
                            insert_fields.append(field)
                            insert_values.append(data.get(field))
                    
                    placeholders = ', '.join(['?' for _ in insert_values])
                    sql = f"INSERT INTO game_resources ({', '.join(insert_fields)}) VALUES ({placeholders})"
                    self._local_cursor.execute(sql, insert_values)
                
                self._local_conn.commit()
            else:
                # Turso 模式：合并查询并利用索引 (强制使用 detail_url 索引加速查重)
                query_sql = """
                    SELECT id, zh_name FROM game_resources 
                    INDEXED BY idx_game_resources_detail_url 
                    WHERE detail_url = ? OR zh_name = ? 
                    LIMIT 1
                """
                existing_result = await self._query(query_sql, (detail_url, name))
                existing = existing_result[0] if existing_result else None
                
                if existing:
                    resource_id, db_zh_name = existing
                    # 更新现有记录
                    update_sets = []
                    values = []
                    for field in all_fields:
                        if field in data:
                            update_sets.append(f"{field} = ?")
                            values.append(data.get(field))
                    update_sets.append("updated_at = ?")
                    values.append(now)
                    values.append(resource_id) # WHERE 条件
                    
                    sql = f"UPDATE game_resources SET {', '.join(update_sets)} WHERE id = ?"
                    await self._execute(sql, tuple(values))
                else:
                    # 插入新记录
                    fields = ['zh_name', 'updated_at']
                    values = [name, now]
                    for field in all_fields:
                        if field in data:
                            fields.append(field)
                            values.append(data.get(field))
                    
                    fields_str = ', '.join(fields)
                    placeholders = ', '.join(['?' for _ in values])
                    sql = f"INSERT INTO game_resources ({fields_str}) VALUES ({placeholders})"
                    await self._execute(sql, tuple(values))

            logger.info(f"[DB Game] 保存游戏资源: {name}, 标识匹配: {'已更新' if existing else '新插入'}")
            return True
        except Exception as e:
            logger.error(f"[DB Game] 保存游戏资源失败: {e}")
            return False

    async def delete_game_resource(self, name: str) -> bool:
        """删除游戏资源

        Args:
            name: 游戏名称

        Returns:
            是否成功
        """
        await self.initialize()

        sql = "DELETE FROM game_resources INDEXED BY idx_game_resources_zh_name WHERE zh_name = ?"

        try:
            if self._local_mode:
                self._local_cursor.execute(sql, (name,))
                self._local_conn.commit()
            else:
                await self._execute(sql, (name,))

            logger.info(f"[DB Game] 删除游戏资源: {name}")
            return True
        except Exception as e:
            logger.error(f"[DB Game] 删除游戏资源失败: {e}")
            return False

    def _get_cache_key(self, keyword: str, limit: int) -> str:
        """生成缓存键"""
        return f"search:{keyword.lower()}:{limit}"

    def _get_from_cache(self, cache_key: str):
        """从缓存获取结果"""
        global _search_cache
        if cache_key not in _search_cache:
            return None

        result, timestamp = _search_cache[cache_key]
        if time.time() - timestamp > _cache_ttl:
            # 缓存过期，删除
            del _search_cache[cache_key]
            return None
        return result

    def _set_cache(self, cache_key: str, result: List[Dict[str, Any]]):
        """设置缓存"""
        global _search_cache

        # 清理过期缓存
        now = time.time()
        expired_keys = [k for k, (_, ts) in _search_cache.items() if now - ts > _cache_ttl]
        for k in expired_keys:
            del _search_cache[k]

        # 如果缓存满了，删除最旧的条目
        if len(_search_cache) >= _max_cache_size:
            oldest_key = min(_search_cache.keys(), key=lambda k: _search_cache[k][1])
            del _search_cache[oldest_key]

        _search_cache[cache_key] = (result, now)

    async def search_game_resources(self, keyword: str, limit: int = 50) -> List[Dict[str, Any]]:
        """搜索游戏资源（带缓存优化 + FTS5 全文搜索）

        Args:
            keyword: 搜索关键词
            limit: 返回数量限制

        Returns:
            匹配的游戏资源列表
        """
        await self.initialize()

        # 1. 检查缓存
        cache_key = self._get_cache_key(keyword, limit)
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            logger.debug(f"[DB Cache] 缓存命中: {keyword}")
            return cached_result

        rows = []
        is_short = False
        
        # 2. 尝试使用 FTS5 MATCH 搜索 (性能最高，消耗最低，支持分词)
        try:
            # 清理关键词并构造 FTS5 查询语句
            # 使用引号包裹以支持精确匹配，添加 * 支持前缀匹配
            import re
            clean_keyword = re.sub(r'[^\w\s]', ' ', keyword).strip()
            
            # 如果关键词太短（小于2个字符），且不是数字，则不进行全表模糊搜索
            is_short = len(clean_keyword) < 2 and not clean_keyword.isdigit()
            
            if clean_keyword:
                fts_query = f'"{clean_keyword}" OR {clean_keyword}*'
                
                sql_fts = """
                    SELECT gr.id, gr.platform, gr.genre, gr.zh_name, gr.en_name, gr.image_url, gr.version, gr.details,
                           gr.password, gr.baidu_url, gr.baidu_code, gr.quark_url, gr.quark_code, gr.uc_url, gr.uc_code,
                           gr.online_url, gr.online_code, gr.patch_url, gr.online_at, gr.detail_url, gr.updated_at,
                           gr.pan123_url, gr.pan123_code, gr.mobile_url, gr.mobile_code, gr.tianyi_url, gr.tianyi_code,
                           gr.xunlei_url, gr.xunlei_code
                    FROM game_resources gr
                    JOIN game_resources_fts fts ON gr.id = fts.rowid
                    WHERE game_resources_fts MATCH ?
                    ORDER BY rank, updated_at DESC
                    LIMIT ?
                """
                
                if self._local_mode:
                    self._local_cursor.execute(sql_fts, (fts_query, limit))
                    rows = self._local_cursor.fetchall()
                else:
                    rows = await self._query(sql_fts, (fts_query, limit))
                
                if rows:
                    logger.debug(f"[DB Search] FTS5 命中: {keyword}, 找到 {len(rows)} 条")
        except Exception as e:
            logger.warning(f"[DB Search] FTS5 搜索异常，回退到 LIKE 模式: {e}")

        # 3. 如果 FTS5 未命中，回退到传统 LIKE 模糊搜索 (兜底逻辑)
        if not rows and not is_short:
            # 首先尝试前缀匹配 (可以利用索引，速度快)
            prefix_pattern = f"{keyword}%"
            sql_prefix = """
                SELECT id, platform, genre, zh_name, en_name, image_url, version, details,
                       password, baidu_url, baidu_code, quark_url, quark_code, uc_url, uc_code,
                       online_url, online_code, patch_url, online_at, detail_url, updated_at,
                       pan123_url, pan123_code, mobile_url, mobile_code, tianyi_url, tianyi_code,
                       xunlei_url, xunlei_code
                FROM game_resources
                INDEXED BY idx_game_resources_zh_name
                WHERE zh_name LIKE ? OR en_name LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
            """

            if self._local_mode:
                self._local_cursor.execute(sql_prefix, (prefix_pattern, prefix_pattern, limit))
                rows = self._local_cursor.fetchall()
            else:
                rows = await self._query(sql_prefix, (prefix_pattern, prefix_pattern, limit))

            # 如果前缀匹配结果太少，且关键词长度足够，才尝试全模糊匹配 (全表扫描)
            if len(rows) < 3 and len(keyword) >= 3: # 提高到 3 个字符才执行全模糊
                full_pattern = f"%{keyword}%"
                sql_full = """
                     SELECT id, platform, genre, zh_name, en_name, image_url, version, details,
                            password, baidu_url, baidu_code, quark_url, quark_code, uc_url, uc_code,
                            online_url, online_code, patch_url, online_at, detail_url, updated_at,
                            pan123_url, pan123_code, mobile_url, mobile_code, tianyi_url, tianyi_code,
                            xunlei_url, xunlei_code
                     FROM game_resources
                    WHERE (zh_name LIKE ? OR en_name LIKE ?)
                      AND zh_name NOT LIKE ?
                      AND (en_name IS NULL OR en_name NOT LIKE ?)
                    ORDER BY updated_at DESC
                    LIMIT ?
                """

                if self._local_mode:
                    self._local_cursor.execute(sql_full, (full_pattern, full_pattern, prefix_pattern, prefix_pattern, limit - len(rows)))
                    additional_rows = self._local_cursor.fetchall()
                else:
                    additional_rows = await self._query(sql_full, (full_pattern, full_pattern, prefix_pattern, prefix_pattern, limit - len(rows)))

                rows = list(rows) + list(additional_rows)

        games = []
        for row in rows:
            # ... existing game dict construction ...
            games.append({
                "id": row[0],
                "platform": row[1],
                "genre": row[2],
                "zh_name": row[3],
                "en_name": row[4],
                "image_url": row[5],
                "version": row[6],
                "details": row[7],
                "password": row[8],
                "baidu_url": row[9],
                "baidu_code": row[10],
                "quark_url": row[11],
                "quark_code": row[12],
                "uc_url": row[13],
                "uc_code": row[14],
                "online_url": row[15],
                "online_code": row[16],
                "patch_url": row[17],
                "online_at": row[18],
                "detail_url": row[19],
                "updated_at": row[20],
                "pan123_url": row[21],
                "pan123_code": row[22],
                "mobile_url": row[23],
                "mobile_code": row[24],
                "tianyi_url": row[25],
                "tianyi_code": row[26],
                "xunlei_url": row[27],
                "xunlei_code": row[28]
            })

        # 存入缓存
        self._set_cache(cache_key, games)
        logger.debug(f"[DB Search] 搜索结果已缓存: {keyword}, 找到 {len(games)} 条")

        return games

    async def get_cookie(self, key_name: str = "xydj") -> str:
        """从 key 表获取 cookie
        
        Args:
            key_name: 密钥名称（默认为 xydj）
            
        Returns:
            cookie 字符串，不存在则返回空字符串
        """
        await self.initialize()
        
        sql = "SELECT xydj FROM ntqq_key WHERE id = 1"
        
        try:
            if self._local_mode:
                self._local_cursor.execute(sql)
                row = self._local_cursor.fetchone()
            else:
                result = await self._query(sql)
                row = result[0] if result else None
            
            if row and row[0]:
                return row[0]
        except Exception as e:
            logger.error(f"[DB Key] 获取 cookie 失败: {e}")
        
        return ""

    async def save_cookie(self, cookie: str, key_name: str = "xydj") -> bool:
        """保存 cookie 到 key 表
        
        Args:
            cookie: cookie 字符串
            key_name: 密钥名称（默认为 xydj）
            
        Returns:
            是否成功
        """
        await self.initialize()
        
        sql = """
            INSERT INTO ntqq_key (id, xydj, updated_at) 
            VALUES (1, ?, datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                xydj = excluded.xydj,
                updated_at = excluded.updated_at
        """
        
        try:
            if self._local_mode:
                self._local_cursor.execute(sql, (cookie,))
                self._local_conn.commit()
            else:
                await self._execute(sql, (cookie,))
            
            logger.info(f"[DB Key] 保存 cookie 成功")
            return True
        except Exception as e:
            logger.error(f"[DB Key] 保存 cookie 失败: {e}")
            return False


# 全局资源管理器实例（保持向后兼容的变量名）
db_permission_manager = TursoResourceManager()
