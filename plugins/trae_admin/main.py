# /home/hjh/BOT/NCBOT/plugins/trae_admin/main.py
import re
import aiohttp
import logging
from ncatbot.plugin import NcatBotPlugin
from ncatbot.event.qq import GroupMessageEvent, PrivateMessageEvent
from ncatbot.types import PlainText, MessageArray
from ncatbot.core.registry import registrar

# 导入公共配置中的 Turso 信息
from common.db_permissions import TURSO_URL, TURSO_TOKEN

logger = logging.getLogger(__name__)

class TraeAdmin(NcatBotPlugin):
    name = "trae_admin"
    version = "1.0.0"
    
    # 固定的管理员 QQ
    ADMIN_QQ = "1783069903"
    
    # 匹配模式：6位数字 ID + "增加上限" 或 "减少上限" + 数字
    # 例如：666666增加上限10个
    REWARD_PATTERN = re.compile(r'^(\d{6})(增加上限|减少上限)(\d+)个?$')
    # 匹配模式：6位旧ID + "修改为" + 6位新ID
    # 例如：123456修改为456789
    MODIFY_VIRTUAL_ID_PATTERN = re.compile(r'^(\d{6})\s*修改为\s*(\d{6})$')

    async def _execute_turso_sql(self, sql: str, args: list = None):
        """执行 Turso SQL (HTTP API)"""
        headers = {
            "Authorization": f"Bearer {TURSO_TOKEN}",
            "Content-Type": "application/json"
        }
        
        # 简单的参数转换逻辑 (参考 trae-email)
        params = []
        if args:
            for arg in args:
                if isinstance(arg, int):
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

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{TURSO_URL.rstrip('/')}/v2/pipeline", headers=headers, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"Turso API 错误: {resp.status} - {text}")
                return await resp.json()

    async def _query_turso_sql(self, sql: str, args: list = None):
        """查询 Turso SQL"""
        data = await self._execute_turso_sql(sql, args)
        if "results" in data and len(data["results"]) > 0:
            res = data["results"][0]
            if "error" in res:
                raise Exception(f"SQL 错误: {res['error']}")
            
            response = res.get("response", {})
            result = response.get("result", {})
            rows = result.get("rows", [])
            
            parsed_rows = []
            for row_data in rows:
                parsed_row = []
                for cell in row_data:
                    val = cell.get("value")
                    if cell.get("type") == "integer":
                        parsed_row.append(int(val))
                    else:
                        parsed_row.append(val)
                parsed_rows.append(parsed_row)
            return parsed_rows
        return []

    async def handle_reward_command(self, event, virtual_id, action, amount):
        """处理奖励发放逻辑"""
        try:
            # 1. 查找 openid
            user_rows = await self._query_turso_sql("SELECT openid FROM users WHERE virtual_id = ?", [virtual_id])
            if not user_rows:
                await event.reply(rtf=MessageArray([PlainText(text=f"❌ 未找到用户 ID: {virtual_id}")]))
                return
            
            openid = user_rows[0][0]
            amount = int(amount)
            
            # 2. 确定增减逻辑
            if action == "增加上限":
                sql = "INSERT INTO user_invitations (openid, bonus_quota) VALUES (?, ?) ON CONFLICT(openid) DO UPDATE SET bonus_quota = bonus_quota + ?"
                params = [openid, amount, amount]
                op_text = "增加"
            else: # 减少上限
                sql = "UPDATE user_invitations SET bonus_quota = MAX(0, bonus_quota - ?) WHERE openid = ?"
                params = [amount, openid]
                op_text = "减少"
                
            # 3. 执行更新
            await self._execute_turso_sql(sql, params)
            
            # 4. 查询最终额度
            final_rows = await self._query_turso_sql("SELECT bonus_quota FROM user_invitations WHERE openid = ?", [openid])
            final_quota = final_rows[0][0] if final_rows else (amount if action == "增加上限" else 0)
            
            await event.reply(rtf=MessageArray([
                PlainText(text=f"✅ 操作成功！\n用户 ID：{virtual_id}\n操作：{op_text} {amount} 个\n当前总奖励额度：{final_quota}")
            ]))
            
        except Exception as e:
            logger.error(f"处理奖励指令失败: {e}")
            await event.reply(rtf=MessageArray([PlainText(text=f"❌ 操作失败: {str(e)}")]))

    async def handle_modify_virtual_id_command(self, event, old_virtual_id, new_virtual_id):
        """处理 virtual_id 修改逻辑（防重复）"""
        try:
            if old_virtual_id == new_virtual_id:
                await event.reply(rtf=MessageArray([PlainText(text="⚠️ 新旧 virtual_id 相同，无需修改")]))
                return

            # 1. 检查旧 ID 是否存在
            old_rows = await self._query_turso_sql(
                "SELECT openid FROM users WHERE virtual_id = ?",
                [old_virtual_id]
            )
            if not old_rows:
                await event.reply(rtf=MessageArray([PlainText(text=f"❌ 未找到旧 ID: {old_virtual_id}")]))
                return

            # 2. 检查新 ID 是否已存在（重复则不修改）
            new_rows = await self._query_turso_sql(
                "SELECT openid FROM users WHERE virtual_id = ?",
                [new_virtual_id]
            )
            if new_rows:
                await event.reply(rtf=MessageArray([
                    PlainText(text=f"⚠️ 新 ID 已存在（重复），未执行修改：{new_virtual_id}")
                ]))
                return

            # 3. 执行更新
            await self._execute_turso_sql(
                "UPDATE users SET virtual_id = ? WHERE virtual_id = ?",
                [new_virtual_id, old_virtual_id]
            )

            await event.reply(rtf=MessageArray([
                PlainText(text=f"✅ 修改成功：{old_virtual_id} -> {new_virtual_id}")
            ]))
        except Exception as e:
            logger.error(f"处理 virtual_id 修改指令失败: {e}")
            await event.reply(rtf=MessageArray([PlainText(text=f"❌ 修改失败: {str(e)}")]))

    @registrar.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent):
        await self._process_message(event)

    @registrar.on_private_message()
    async def on_private_message(self, event: PrivateMessageEvent):
        await self._process_message(event)

    async def _process_message(self, event):
        user_id = str(event.user_id)
        if user_id != self.ADMIN_QQ:
            return

        msg = event.raw_message.strip()

        # 1) 处理 virtual_id 修改命令：123456修改为456789
        modify_match = self.MODIFY_VIRTUAL_ID_PATTERN.match(msg)
        if modify_match:
            old_virtual_id, new_virtual_id = modify_match.groups()
            await self.handle_modify_virtual_id_command(event, old_virtual_id, new_virtual_id)
            return

        # 2) 处理奖励命令：123456增加上限10个
        match = self.REWARD_PATTERN.match(msg)
        if match:
            virtual_id, action, amount = match.groups()
            await self.handle_reward_command(event, virtual_id, action, amount)
