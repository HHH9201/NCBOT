# /home/hjh/BOT/NCBOT/plugins/trae-email/main.py
# -*- coding: utf-8 -*-
"""
Trae Email 账号分配插件
当用户说"给一个账号"时，从数据库分配一个邮箱账号给用户
支持定时检查账号数量，不足时自动注册补充
"""
import logging
import asyncio
import os
from datetime import datetime
from ncatbot.plugin import NcatBotPlugin
from ncatbot.event.qq import GroupMessageEvent
from ncatbot.types import PlainText, MessageArray
from ncatbot.core.registry import registrar
import aiohttp
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# 从 common 模块导入统一的数据库配置
from common.db_permissions import TURSO_URL, TURSO_TOKEN


class TraeEmailManager:
    """基于 Turso 数据库的邮箱账号管理器"""

    def __init__(self, url: str = TURSO_URL, auth_token: str = TURSO_TOKEN):
        self.url = url.rstrip('/')
        self.auth_token = auth_token
        self._session: Optional[aiohttp.ClientSession] = None
        self._initialized = False

    async def initialize(self):
        """异步初始化"""
        if self._initialized:
            return

        self._session = aiohttp.ClientSession()
        # 测试连接并初始化表
        await self._init_tables()
        self._initialized = True
        logger.info("[TraeEmail] Turso 连接成功")

    async def _init_tables(self):
        """初始化数据库表"""
        # 1. 初始化主表
        await self._execute_sql("""
            CREATE TABLE IF NOT EXISTS email_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                status TEXT DEFAULT 'available',
                qq_id TEXT,
                used_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 2. 检查并添加 qq_id 字段 (针对已存在的表)
        try:
            await self._execute_sql("ALTER TABLE email_accounts ADD COLUMN qq_id TEXT")
            logger.info("[TraeEmail] 已为 email_accounts 添加 qq_id 字段")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                pass
            else:
                logger.error(f"[TraeEmail] 检查 qq_id 字段失败: {e}")

    async def _execute_sql(self, sql: str, args: list = None):
        """执行 SQL 语句 (Turso HTTP API)"""
        if args is None:
            args = []

        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json"
        }

        params = []
        for arg in args:
            if isinstance(arg, bool):
                params.append({"type": "integer", "value": str(int(arg))})
            elif isinstance(arg, int):
                params.append({"type": "integer", "value": str(arg)})
            elif isinstance(arg, str):
                params.append({"type": "text", "value": arg})
            elif arg is None:
                params.append({"type": "null"})
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

    async def _query_sql(self, sql: str, args: list = None) -> list:
        """查询 SQL (Turso HTTP API)"""
        result = await self._execute_sql(sql, args)

        if "response" in result and "result" in result["response"]:
            result_data = result["response"]["result"]
            if "rows" in result_data:
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

    async def get_unassigned_account(self) -> Optional[Dict[str, Any]]:
        """获取一个未分配的账号"""
        await self.initialize()

        sql = """
            SELECT id, account, password 
            FROM email_accounts 
            WHERE status = 'available' 
            ORDER BY id ASC 
            LIMIT 1
        """
        rows = await self._query_sql(sql)

        if rows:
            return {
                "id": rows[0][0],
                "email": rows[0][1],
                "key": rows[0][2]
            }
        return None

    async def assign_account(self, account_id: int, user_id: str) -> bool:
        """标记账号为已分配"""
        await self.initialize()

        from datetime import datetime
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        sql = """
            UPDATE email_accounts 
            SET status = 'used', 
                used_at = ?,
                qq_id = ?
            WHERE id = ?
        """

        try:
            await self._execute_sql(sql, [now, user_id, account_id])
            logger.info(f"[TraeEmail] 账号 {account_id} 已分配给用户 {user_id}")
            return True
        except Exception as e:
            logger.error(f"[TraeEmail] 分配账号失败: {e}")
            return False

    async def add_account(self, email: str, key: str) -> bool:
        """添加新账号到数据库"""
        await self.initialize()

        sql = """
            INSERT INTO email_accounts (account, password, status) 
            VALUES (?, ?, 'available')
            ON CONFLICT(account) DO UPDATE SET
                password = excluded.password,
                status = 'available',
                used_at = NULL,
                qq_id = NULL
        """

        try:
            await self._execute_sql(sql, [email, key])
            logger.info(f"[TraeEmail] 添加账号: {email}")
            return True
        except Exception as e:
            logger.error(f"[TraeEmail] 添加账号失败: {e}")
            return False

    async def get_stats(self) -> Dict[str, int]:
        """获取账号统计信息"""
        await self.initialize()

        total_sql = "SELECT COUNT(*) FROM email_accounts"
        assigned_sql = "SELECT COUNT(*) FROM email_accounts WHERE status = 'used'"
        unassigned_sql = "SELECT COUNT(*) FROM email_accounts WHERE status = 'available'"

        total_result = await self._query_sql(total_sql)
        assigned_result = await self._query_sql(assigned_sql)
        unassigned_result = await self._query_sql(unassigned_sql)

        return {
            "total": total_result[0][0] if total_result else 0,
            "assigned": assigned_result[0][0] if assigned_result else 0,
            "unassigned": unassigned_result[0][0] if unassigned_result else 0
        }

    async def get_unassigned_count(self) -> int:
        """获取未分配账号数量"""
        await self.initialize()
        unassigned_sql = "SELECT COUNT(*) FROM email_accounts WHERE status = 'available'"
        result = await self._query_sql(unassigned_sql)
        return result[0][0] if result else 0


# 全局账号管理器实例
email_manager = TraeEmailManager()


class TraeEmail(NcatBotPlugin):
    name = "trae-email"
    version = "1.0"

    # 允许获取账号的用户白名单
    ALLOWED_USERS = {"1783069903", "2356131127"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @registrar.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent):
        raw_msg = event.raw_message.strip()

        # 处理"给我一个账号"命令
        if raw_msg == "给一个账号":
            # 检查用户是否在白名单中
            user_id = str(event.user_id)
            if user_id not in self.ALLOWED_USERS:
                logger.warning(f"[TraeEmail] 用户 {user_id} 尝试获取账号但被拒绝（不在白名单中）")
                await event.reply(
                    rtf=MessageArray([
                        PlainText(text="❌ 你没有权限获取账号")
                    ])
                )
                return

            try:
                # 先检查账号数量，不足时自动注册
                unassigned_count = await email_manager.get_unassigned_count()
                if unassigned_count < 30:
                    logger.info(f"[TraeEmail] 账号数量不足({unassigned_count}<30)，开始自动注册...")
                    await self.check_and_register_accounts()

                # 获取未分配的账号
                account = await email_manager.get_unassigned_account()

                if not account:
                    await event.reply(
                        rtf=MessageArray([
                            PlainText(text="❌ 暂无可用账号，请联系管理员添加")
                        ])
                    )
                    return

                # 标记为已分配
                success = await email_manager.assign_account(
                    account["id"],
                    str(event.user_id)
                )

                if success:
                    await event.reply(
                        rtf=MessageArray([
                            PlainText(
                                text=f"邮箱：{account['email']}\n"
                                f"密码：{account['key']}"
                            )
                        ])
                    )
                else:
                    await event.reply(
                        rtf=MessageArray([
                            PlainText(text="❌ 账号分配失败，请稍后重试")
                        ])
                    )

            except Exception as e:
                logger.error(f"[TraeEmail] 处理账号请求失败: {e}")
                await event.reply(
                    rtf=MessageArray([
                        PlainText(text="❌ 系统错误，请稍后重试")
                    ])
                )

        # 处理"账号统计"命令（管理员功能）
        elif raw_msg == "账号统计":
            try:
                stats = await email_manager.get_stats()
                await event.reply(
                    rtf=MessageArray([
                        PlainText(
                            text=f"📊 账号统计\n\n"
                            f"总账号数：{stats['total']}\n"
                            f"已分配：{stats['assigned']}\n"
                            f"未分配：{stats['unassigned']}"
                        )
                    ])
                )
            except Exception as e:
                logger.error(f"[TraeEmail] 获取统计失败: {e}")
                await event.reply(
                    rtf=MessageArray([
                        PlainText(text="❌ 获取统计失败")
                    ])
                )

    async def on_load(self):
        # 初始化数据库
        await email_manager.initialize()
        print(f"{self.name} 插件已加载，版本: {self.version}")

    async def check_and_register_accounts(self):
        """定时检查账号数量，不足时自动注册"""
        try:
            unassigned_count = await email_manager.get_unassigned_count()
            logger.info(f"[TraeEmail] 当前未分配账号数量: {unassigned_count}")

            if unassigned_count < 30:
                logger.info(f"[TraeEmail] 账号数量不足({unassigned_count}<30)，开始自动注册20个账号...")
                await self.run_register_script()
            else:
                logger.info(f"[TraeEmail] 账号数量充足，无需注册")
        except Exception as e:
            logger.error(f"[TraeEmail] 检查账号数量失败: {e}")

    async def run_register_script(self):
        """执行注册脚本添加账号"""
        try:
            # 获取脚本路径
            script_path = os.path.join(os.path.dirname(__file__), "jb.py")

            if not os.path.exists(script_path):
                logger.error(f"[TraeEmail] 注册脚本不存在: {script_path}")
                return

            # 运行注册脚本（注册20个账号）
            process = await asyncio.create_subprocess_exec(
                "python3", script_path,
                "--count", "20",
                "--headless",
                "--interval", "3",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info(f"[TraeEmail] 注册脚本执行成功")
                # 解析输出并添加账号到数据库
                await self.parse_and_add_accounts()
            else:
                logger.error(f"[TraeEmail] 注册脚本执行失败: {stderr.decode()}")

        except Exception as e:
            logger.error(f"[TraeEmail] 执行注册脚本失败: {e}")

    async def parse_and_add_accounts(self):
        """解析注册脚本生成的账号文件并添加到数据库"""
        try:
            accounts_file = os.path.join(os.path.dirname(__file__), "trae_accounts.txt")

            if not os.path.exists(accounts_file):
                logger.warning(f"[TraeEmail] 账号文件不存在: {accounts_file}")
                return

            added_count = 0
            with open(accounts_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            email = None
            password = None

            for line in lines:
                line = line.strip()
                if line.startswith("邮箱:") or line.startswith("邮箱："):
                    email = line.split(":", 1)[1].strip() if ":" in line else line.split("：", 1)[1].strip()
                elif line.startswith("密码:") or line.startswith("密码："):
                    password = line.split(":", 1)[1].strip() if ":" in line else line.split("：", 1)[1].strip()

                    if email and password:
                        success = await email_manager.add_account(email, password)
                        if success:
                            added_count += 1
                        email = None
                        password = None

            logger.info(f"[TraeEmail] 成功添加 {added_count} 个账号到数据库")

            # 删除已处理的账号文件
            try:
                os.remove(accounts_file)
                logger.info(f"[TraeEmail] 已删除账号文件: {accounts_file}")
            except Exception as e:
                logger.warning(f"[TraeEmail] 删除账号文件失败: {e}")

        except Exception as e:
            logger.error(f"[TraeEmail] 解析账号文件失败: {e}")
