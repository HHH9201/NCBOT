# /home/hjh/BOT/NCBOT/plugins/xydj/db_search.py
# -*- coding: utf-8 -*-
"""
咸鱼单机 - 数据库搜索版
- 只在数据库进行搜索
- 需要发送小程序码给用户（提示看广告）
- 不去网站进行搜索
"""
import re
import asyncio
import logging
import httpx
import base64
from typing import Optional
from ncatbot.plugin import NcatBotPlugin
from ncatbot.event.qq import GroupMessageEvent
from ncatbot.types import PlainText, Reply, MessageArray
from ncatbot.core.registry import registrar

# 引入全局服务和配置
from common import (
    GLOBAL_CONFIG,
)
from common.db_permissions import db_permission_manager

logger = logging.getLogger(__name__)

# -------------------- 预编译正则表达式 --------------------
RE_CQ_CODE = re.compile(r'\[CQ:[^\]]+\]')

async def search_game_from_db(game_name: str):
    """从数据库搜索游戏（模糊匹配中英文）"""
    print(f"[DB Search] 正在从数据库搜索: {game_name}")
    
    try:
        cloud_games = await db_permission_manager.search_game_resources(game_name)
        if not cloud_games:
            print(f"[DB Search] 数据库未找到: {game_name}")
            return None, None
        
        print(f"[DB Search] 数据库找到 {len(cloud_games)} 条记录")
        
        text_lines = []
        games = []
        
        for idx, game_data in enumerate(cloud_games):
            zh_name = game_data.get("zh_name", game_data.get("name", ""))
            en_name = game_data.get("en_name", "")
            version = game_data.get("version", "")
            updated_at = game_data.get("updated_at", "")
            
            display_text = f"{idx+1}. {zh_name}"
            if en_name:
                display_text += f"\n   英文名: {en_name}"
            if version:
                display_text += f"\n   版本: {version}"
            if updated_at:
                display_text += f"\n   更新时间: {updated_at}"
            
            text_lines.append(display_text)
            
            games.append({
                "from_db": True,
                "db_data": game_data,
                "title": zh_name,
                "en_name": en_name,
                "version": version,
                "image_url": game_data.get("image_url", ""),
                "details": game_data.get("details", ""),
                "updated_at": updated_at
            })
        
        text_result = "\n\n".join(text_lines)
        return text_result, games
    except Exception as e:
        logging.error(f"[DB Search] 从数据库搜索游戏失败: {e}")
        return None, None

class SearchSession:
    def __init__(self, user_id, games, task=None):
        self.user_id = user_id
        self.games = games
        self.task = task
        self.processing = False

class XydjDbSearch(NcatBotPlugin):
    name = "xydj_db_search"
    version = "1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sessions = {}
        self.backend_url = GLOBAL_CONFIG.get("backend.url", "http://127.0.0.1:8978").rstrip("/")
        self.app_id = GLOBAL_CONFIG.get("app.id", "card_sender")
        self.app_secret = GLOBAL_CONFIG.get("app.secret", "")
        self.http_client: Optional[httpx.AsyncClient] = None

    async def _get_backend_client(self) -> httpx.AsyncClient:
        if self.http_client is None:
            self.http_client = httpx.AsyncClient(
                base_url=self.backend_url,
                timeout=15,
                headers={
                    "app-id": self.app_id,
                    "app-secret": self.app_secret,
                },
            )
        return self.http_client

    async def countdown(self, event, group_id):
        await asyncio.sleep(20)
        session = self.sessions.get(group_id)
        if session and not session.processing:
            self._cleanup(group_id)
            await event.reply(
                rtf=MessageArray([Reply(id=event.message_id), PlainText(text="等待超时，操作已取消。请重新搜索")])
            )

    def _cleanup(self, group_id):
        if group_id in self.sessions:
            session = self.sessions[group_id]
            if session.task:
                session.task.cancel()
            del self.sessions[group_id]

    def _build_complete_game_content(self, game_data):
        """从数据库数据构建完整的游戏资源内容"""
        content = []
        content.append("【单机版】\n")
        
        zh_name = game_data.get("zh_name", game_data.get("name", ""))
        content.append(f"游戏名字：{zh_name}\n")
        
        en_name = game_data.get("en_name", "")
        if en_name:
            content.append(f"英文名：{en_name}\n")
        
        version = game_data.get("version", "")
        if version:
            content.append(f"版本：{version}\n")
        
        details = game_data.get("details", "")
        if details:
            content.append(f"详情：{details}\n")
        
        image_url = game_data.get("image_url", "")
        if image_url:
            content.append(f"图片链接：{image_url}\n")
        
        password = game_data.get("password", "")
        if password:
            content.append(f"解压密码：【{password}】\n")
        
        pan_links = []
        if game_data.get("baidu_url"):
            pan_links.append(f"百度网盘：{game_data['baidu_url']}")
            if game_data.get("baidu_code"):
                pan_links.append(f"百度网盘提取码：【{game_data['baidu_code']}】")
        
        if game_data.get("quark_url"):
            pan_links.append(f"夸克网盘：{game_data['quark_url']}")
            if game_data.get("quark_code"):
                pan_links.append(f"夸克网盘提取码：【{game_data['quark_code']}】")
        
        if game_data.get("uc_url"):
            pan_links.append(f"UC网盘：{game_data['uc_url']}")
            if game_data.get("uc_code"):
                pan_links.append(f"UC网盘提取码：【{game_data['uc_code']}】")
        
        if game_data.get("pan123_url"):
            pan_links.append(f"123网盘：{game_data['pan123_url']}")
            if game_data.get("pan123_code"):
                pan_links.append(f"123网盘提取码：【{game_data['pan123_code']}】")
        
        if game_data.get("tianyi_url"):
            pan_links.append(f"天翼网盘：{game_data['tianyi_url']}")
            if game_data.get("tianyi_code"):
                pan_links.append(f"天翼网盘提取码：【{game_data['tianyi_code']}】")
        
        if game_data.get("xunlei_url"):
            pan_links.append(f"迅雷网盘：{game_data['xunlei_url']}")
            if game_data.get("xunlei_code"):
                pan_links.append(f"迅雷网盘提取码：【{game_data['xunlei_code']}】")
        
        if game_data.get("mobile_url"):
            pan_links.append(f"移动端：{game_data['mobile_url']}")
            if game_data.get("mobile_code"):
                pan_links.append(f"移动端提取码：【{game_data['mobile_code']}】")
        
        if game_data.get("online_url"):
            pan_links.append(f"联机版：{game_data['online_url']}")
            if game_data.get("online_code"):
                pan_links.append(f"联机版提取码：【{game_data['online_code']}】")
        
        if game_data.get("patch_url"):
            pan_links.append(f"联机补丁：{game_data['patch_url']}")
        
        for link in pan_links:
            content.append(f"{link}\n")
        
        updated_at = game_data.get("updated_at", "")
        if updated_at:
            content.append(f"最后更新时间：{updated_at}\n")
        
        return content

    async def _send_final_forward(self, group_id, 单机_lines: list[str], user_id: str = "0", user_nickname: str = "游戏助手"):
        from ncatbot.types.qq import ForwardConstructor
        
        fc = ForwardConstructor()
        
        game_title = ""
        for line in 单机_lines:
            if "游戏名字：" in line:
                game_title = line.split("游戏名字：")[1].strip()
                break
        if not game_title:
            game_title = "游戏资源"

        content_text = "".join(单机_lines)
        fc.attach_text(text=content_text, user_id=user_id, nickname=user_nickname)
        
        try:
            await self.api.qq.post_group_forward_msg(group_id, fc.build())
            print(f"✅ [Forward] 合并转发消息已发送: {game_title}")
            return True
        except Exception as e:
            print(f"❌ [Forward] 发送失败: {e}")
            try:
                await self.api.qq.send_group_text(group_id, content_text)
                return True
            except:
                return False

    async def process_game_resource(self, game, event):
        print(f"[Resource] Processing: {game['title']}")
        try:
            zh_name = game.get("title", "")
            print(f"[搜索关键词] 中文名: {zh_name}")

            # 构造小程序展示需要的资源载荷
            db_data = game.get("db_data", {})
            resource_payload = {
                "name": zh_name,
                "password": db_data.get("password", ""),
                "baidu_url": db_data.get("baidu_url", ""),
                "baidu_code": db_data.get("baidu_code", ""),
                "quark_url": db_data.get("quark_url", ""),
                "quark_code": db_data.get("quark_code", ""),
                "uc_url": db_data.get("uc_url", ""),
                "uc_code": db_data.get("uc_code", ""),
                "pan123_url": db_data.get("pan123_url", ""),
                "pan123_code": db_data.get("pan123_code", ""),
                "tianyi_url": db_data.get("tianyi_url", ""),
                "tianyi_code": db_data.get("tianyi_code", ""),
                "xunlei_url": db_data.get("xunlei_url", ""),
                "xunlei_code": db_data.get("xunlei_code", ""),
                "mobile_url": db_data.get("mobile_url", ""),
                "mobile_code": db_data.get("mobile_code", "")
            }

            client = await self._get_backend_client()
            try:
                response = await client.post(
                    "/api/task/pop_ready",
                    json={
                        "platform": "qq_id",
                        "platform_id": str(event.user_id),
                        "app_id": self.app_id,
                        "resource_payload": resource_payload
                    },
                    timeout=10.0
                )
                
                if response.status_code != 200:
                    print(f"[Resource] 池子暂无现成票据 (Code: {response.status_code})，回退到实时生成...")
                    response = await client.post(
                        "/api/task/create",
                        json={
                            "platform": "qq_id",
                            "platform_id": str(event.user_id),
                            "app_id": self.app_id,
                            "resource_payload": resource_payload
                        },
                        timeout=15.0
                    )
                
                if response.status_code == 200:
                    data = response.json()
                    ticket_id = data.get("ticket")
                    qrcode_url = data.get("qrcode_url")
                    
                    if ticket_id and qrcode_url:
                        # 强制通过后端本地代理下载二维码，统一转换为 base64 发送
                        try:
                            print(f"[Resource] 正在从本地代理下载二维码: {ticket_id}")
                            img_resp = await client.get(f"/api/task/qrcode/{ticket_id}", timeout=15)
                            if img_resp.status_code == 200:
                                img_b64 = f"base64://{base64.b64encode(img_resp.content).decode()}"
                                print(f"[Resource] 二维码代理下载并转换为 base64 成功")
                                await event.reply(image=img_b64)
                            else:
                                print(f"[Resource] 代理下载失败 (Code: {img_resp.status_code})，尝试原始 URL")
                                await event.reply(image=qrcode_url)
                        except Exception as download_e:
                            print(f"[Resource] 代理下载异常: {download_e}")
                            await event.reply(image=qrcode_url)
                        
                            asyncio.create_task(self._wait_and_send_resource(
                                event, event.group_id, ticket_id, game
                            ))
                        return
                
                await event.reply(
                    rtf=MessageArray([Reply(id=event.message_id), PlainText(text="❌ 系统正忙，请 10 秒后再次搜索重试。")])
                )
            
            except httpx.ConnectError as ce:
                print(f"[Resource] 后端连接失败，启用降级模式: {ce}")
                await event.reply(
                    rtf=MessageArray([Reply(id=event.message_id), PlainText(text="⚠️ 后端服务暂时不可用，为您直接发送游戏资源...")])
                )
                if game.get("from_db") and game.get("db_data"):
                    content = self._build_complete_game_content(game["db_data"])
                    await self._send_final_forward(event.group_id, content, str(event.user_id), event.sender.nickname)
                else:
                    await event.reply(
                        rtf=MessageArray([Reply(id=event.message_id), PlainText(text="❌ 获取游戏资源失败，请稍后重试。")])
                    )
                return

        except Exception as e:
            import traceback
            print(f"[Resource] Processing exception: {e}")
            traceback.print_exc()
            await event.reply(
                rtf=MessageArray([Reply(id=event.message_id), PlainText(text=f"处理失败: {str(e)}")])
            )

    async def _wait_and_send_resource(self, event, group_id, ticket_id, game):
        max_retries = 45
        delay = 4
        
        await event.reply(
            rtf=MessageArray([Reply(id=event.message_id), PlainText(text="✅ 请扫码在小程序内点击“修成正果”，完成后我将立即在此发送资源链接！")])
        )

        for _ in range(max_retries):
            await asyncio.sleep(delay)
            try:
                client = await self._get_backend_client()
                resp = await client.get("/api/user/get_result", params={"ticket": ticket_id}, timeout=5)
                response = resp.json()
                
                print(f"[Poll Ticket] Ticket: {ticket_id}, Status Response: {response}")
                        
                if response:
                    if isinstance(response, dict) and response.get("detail") == "记录不存在或已过期":
                        print(f"⚠️ [Poll Warning] 遇到后端进程数据不同步(404)，正在等待重试...")
                        continue

                    status = response.get("status")
                    if status in ["verified", "claimed"]:
                        print(f"🎊 [Poll Success] Ticket {ticket_id} 验证通过, 状态: {status}")
                        
                        if game.get("from_db") and game.get("db_data"):
                            content = self._build_complete_game_content(game["db_data"])
                            await self._send_final_forward(group_id, content, str(event.user_id), event.sender.nickname)
                            await event.reply(rtf=MessageArray([PlainText(text="🎉 验证成功！资源已在上方以合并转发形式发出，请查收。")]))
                        else:
                            await event.reply(rtf=MessageArray([PlainText(text="❌ 验证成功但资源获取失败，请联系管理员。")]))
                        return
            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                print(f"[Poll Ticket] 轮询出错: {e}\n{error_details}")
                
        await event.reply(
            rtf=MessageArray([Reply(id=event.message_id), PlainText(text="⏳ 验证超时，你好像还没看完广告哦。如果已看请重新搜索。")])
        )

    @registrar.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent):
        session = self.sessions.get(event.group_id)
        
        if session and event.user_id == session.user_id:
            if session.processing:
                return
            
            choice = re.sub(r'\[CQ:[^\]]+\]', '', event.raw_message).strip()
            
            if choice == "0":
                await event.reply(
                    rtf=MessageArray([Reply(id=event.message_id), PlainText(text="操作已取消。")])
                )
                self._cleanup(event.group_id)
                return
            
            if not choice.isdigit() or not 1 <= int(choice) <= len(session.games):
                await event.reply(
                    rtf=MessageArray([Reply(id=event.message_id), PlainText(text="回复错误，操作已取消。请重新搜索游戏。")])
                )
                self._cleanup(event.group_id)
                return
            
            choice = int(choice)
            session.processing = True
            if session.task:
                session.task.cancel()
                session.task = None
            
            try:
                game = session.games[choice - 1]
                await self.process_game_resource(game, event)
            except Exception as e:
                await event.reply(
                    rtf=MessageArray([Reply(id=event.message_id), PlainText(text=f"处理失败: {str(e)}")])
                )
            finally:
                self._cleanup(event.group_id)
        
        elif event.raw_message.strip().startswith("搜库"):
            message = event.raw_message.strip()
            if message.startswith("搜库 "):
                game_name = message[3:].strip()
            else:
                game_name = message[2:].strip()
            if not game_name:
                await event.reply(
                    rtf=MessageArray([Reply(id=event.message_id), PlainText(text="使用方法：搜库+游戏名称，例如：搜库 文明6")])
                )
                return
            
            try:
                text_result, games = await search_game_from_db(game_name)
                if not text_result:
                    await event.reply(
                        rtf=MessageArray([Reply(id=event.message_id), PlainText(text="数据库未找到，请先用“搜网”命令从网站搜索并保存到数据库。")])
                    )
                    return
                
                if len(games) == 1:
                    await self.process_game_resource(games[0], event)
                    return
                
                await event.reply(
                    rtf=MessageArray([Reply(id=event.message_id), PlainText(text=f"🎯 发现 {len(games)} 款游戏\n{text_result}\n⏰ 20秒内回复序号选择 | 回复 0 取消操作")])
                )
                
                session = SearchSession(event.user_id, games)
                session.task = asyncio.create_task(self.countdown(event, event.group_id))
                self.sessions[event.group_id] = session
                
            except Exception as e:
                logging.exception(f"搜索出错: {e}")
                await event.reply(
                    rtf=MessageArray([Reply(id=event.message_id), PlainText(text="发生错误，请稍后重试。")])
                )

    async def on_load(self):
        print(f"{self.name} 插件已加载，版本: {self.version}")
        await self._get_backend_client()

    async def on_unload(self):
        if self.http_client is not None:
            await self.http_client.aclose()
            self.http_client = None
