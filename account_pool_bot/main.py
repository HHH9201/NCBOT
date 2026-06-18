# /home/hjh/BOT/NCBOT/data/plugins/account_pool_bot/main.py
import sys
import traceback

# 调试：记录模块加载过程
try:
    with open("/tmp/account_pool_bot_debug.log", "a") as f:
        f.write(f"[DEBUG] main.py top-level reached. sys.modules has account_pool_bot.main = {id(sys.modules.get('account_pool_bot.main', None))}\n")
except Exception as e:
    pass

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple

try:
    with open("/tmp/account_pool_bot_debug.log", "a") as f:
        f.write("[DEBUG] imports before ncatbot\n")
except Exception:
    pass

from ncatbot.plugin import BasePlugin
from ncatbot.core import registrar
from ncatbot.event.qq import GroupMessageEvent
from ncatbot.types import PlainText, MessageArray

try:
    with open("/tmp/account_pool_bot_debug.log", "a") as f:
        f.write("[DEBUG] imports after ncatbot\n")
except Exception:
    pass

logger = logging.getLogger(__name__)

# ==================== 配置区 ====================
POSTGRES_DSN = "postgresql://postgres:postgres@host.docker.internal:5432/trae_xx"
TARGET_GROUP_ID = "695934967"
TARGET_USER_ID = "1783069903"
CLAIM_PATTERN = re.compile(r'^给(\d{1,2})个账号$')

try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    asyncpg = None  # type: ignore
    ASYNCPG_AVAILABLE = False
    logger.warning("[account_pool_bot] asyncpg 未安装")

class AccountPoolBot(BasePlugin):
    """账号池 Bot 插件"""
    name = "account_pool_bot"
    version = "1.0.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._db_pool: Optional[asyncpg.Pool] = None  # type: ignore

    async def on_load(self):
        if ASYNCPG_AVAILABLE:
            try:
                self._db_pool = await asyncpg.create_pool(
                    POSTGRES_DSN,
                    min_size=1,
                    max_size=5,
                    command_timeout=10,
                )
                logger.info("[account_pool_bot] PostgreSQL 连接池已初始化")
            except Exception as e:
                logger.error("[account_pool_bot] 数据库连接失败: %s", e)
        else:
            logger.error("[account_pool_bot] 缺少 asyncpg，数据库功能不可用")

    async def on_unload(self):
        if self._db_pool is not None:
            await self._db_pool.close()
            self._db_pool = None
            logger.info("[account_pool_bot] PostgreSQL 连接池已关闭")

    @registrar.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent):
        group_id = str(getattr(event, "group_id", ""))
        user_id = str(getattr(event, "user_id", ""))

        if group_id != TARGET_GROUP_ID:
            return
        if user_id != TARGET_USER_ID:
            return

        msg = getattr(event, "raw_message", "").strip()
        match = CLAIM_PATTERN.match(msg)
        if not match:
            return

        count = int(match.group(1))
        if count < 1 or count > 50:
            await event.api.send_group_plain_text(
                str(event.group_id), "⚠️ 单次领取数量需在 1-50 之间"
            )
            return

        await self._handle_claim(event, count)

    async def _handle_claim(self, event: GroupMessageEvent, count: int):
        group_id = str(event.group_id)
        if not ASYNCPG_AVAILABLE or self._db_pool is None:
            await event.api.send_group_plain_text(
                group_id, "❌ 数据库驱动未就绪，请联系管理员检查 asyncpg 安装"
            )
            return

        try:
            accounts = await self._claim_accounts(count)
        except Exception as e:
            logger.error("[account_pool_bot] 领取账号失败: %s", e)
            await event.api.send_group_plain_text(
                group_id, f"❌ 领取失败: {str(e)}"
            )
            return

        if not accounts:
            await event.api.send_group_plain_text(
                group_id, "📭 暂无可领取账号，库中已空"
            )
            return

        lines = []
        for idx, (email, password) in enumerate(accounts, start=1):
            lines.append(f"{idx}. {email}---{password}")

        if len(accounts) < count:
            lines.append(f"\n⚠️ 注意：您请求 {count} 个，但仅剩 {len(accounts)} 个可用")

        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:3900] + "\n...（内容过长已截断）"

        await event.api.send_group_plain_text(group_id, text)

    async def _claim_accounts(self, count: int) -> List[Tuple[str, str]]:
        assert self._db_pool is not None

        async with self._db_pool.acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch(
                    """
                    SELECT id, email, password
                    FROM "account_pool_accounts"
                    WHERE status = 'unclaimed'
                    ORDER BY "createdAt" ASC
                    LIMIT $1
                    FOR UPDATE SKIP LOCKED
                    """,
                    count,
                )

                if not rows:
                    return []

                ids = [r["id"] for r in rows]
                now = datetime.now(timezone.utc)

                await conn.execute(
                    """
                    UPDATE "account_pool_accounts" AS target
                    SET
                        status = 'claimed',
                        "claimedByUserId" = NULL,
                        "claimedAt" = $1,
                        "lastClaimedAt" = $1,
                        "updatedAt" = $1
                    FROM unnest($2::text[]) AS src(id)
                    WHERE target.id = src.id
                    """,
                    now,
                    ids,
                )

                return [(r["email"], r["password"]) for r in rows]
