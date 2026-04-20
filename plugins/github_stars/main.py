# /home/hjh/BOT/NCBOT/plugins/github_stars/main.py
import os
import re
import json
import aiohttp
import asyncio
import logging
from ncatbot.plugin import NcatBotPlugin
from ncatbot.event.qq import GroupMessageEvent, PrivateMessageEvent
from ncatbot.types import PlainText, MessageArray
from ncatbot.core.registry import registrar

logger = logging.getLogger(__name__)

class GitHubStar(NcatBotPlugin):
    name = "github_stars"
    version = "1.0.2"
    
    ADMIN_QQ = "1783069903"
    NOTIFY_GROUP_ID = "695934967"
    TOKEN_FILE = os.path.join(os.path.dirname(__file__), "tokens.txt")
    WATCH_FILE = os.path.join(os.path.dirname(__file__), "watched_repos.json")
    
    # 匹配命令：gh star <owner>/<repo> add|remove
    STAR_PATTERN = re.compile(r'^gh star ([\w\-\.]+)/([\w\-\.]+) (add|remove)$')
    # 匹配命令：gh token add <token>
    TOKEN_ADD_PATTERN = re.compile(r'^gh token add (ghp_[\w]+)$')
    # 匹配命令：gh token list
    TOKEN_LIST_PATTERN = re.compile(r'^gh token list$')
    # 匹配命令：gh watch <owner>/<repo>
    WATCH_PATTERN = re.compile(r'^gh watch ([\w\-\.]+)/([\w\-\.]+)$')
    # 匹配命令：gh unwatch <owner>/<repo>
    UNWATCH_PATTERN = re.compile(r'^gh unwatch ([\w\-\.]+)/([\w\-\.]+)$')
    # 匹配命令：gh watch list
    WATCH_LIST_PATTERN = re.compile(r'^gh watch list$')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.running = True
        self.monitor_task = None

    async def on_load(self):
        logger.info(f"[{self.name}] 插件加载，启动 Star 监控任务...")
        self.monitor_task = asyncio.create_task(self.monitor_stars())

    async def on_unload(self):
        self.running = False
        if self.monitor_task:
            self.monitor_task.cancel()
        logger.info(f"[{self.name}] 插件卸载，停止监控任务")

    def _load_tokens(self):
        """从文件加载 tokens"""
        if not os.path.exists(self.TOKEN_FILE):
            return []
        with open(self.TOKEN_FILE, "r") as f:
            return [line.strip() for line in f if line.strip()]

    def _save_token(self, token):
        """保存 token 到文件"""
        tokens = self._load_tokens()
        if token not in tokens:
            with open(self.TOKEN_FILE, "a") as f:
                f.write(token + "\n")
            return True
        return False

    async def _manage_star(self, token, owner, repo, action):
        """对单个 token 执行 star/unstar 操作"""
        url = f"https://api.github.com/user/starred/{owner}/{repo}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                if action == "add":
                    async with session.put(url, headers=headers) as resp:
                        return resp.status == 204
                else: # remove
                    async with session.delete(url, headers=headers) as resp:
                        return resp.status == 204
            except Exception as e:
                logger.error(f"GitHub API Error ({token[:10]}...): {e}")
                return False

    def _load_watched_repos(self):
        """加载监控列表"""
        if not os.path.exists(self.WATCH_FILE):
            return {}
        try:
            with open(self.WATCH_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载监控文件失败: {e}")
            return {}

    def _save_watched_repos(self, data):
        """保存监控列表"""
        try:
            with open(self.WATCH_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"保存监控文件失败: {e}")

    async def get_star_count(self, owner, repo):
        """获取项目当前 Star 数"""
        url = f"https://api.github.com/repos/{owner}/{repo}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("stargazers_count")
            except Exception as e:
                logger.error(f"获取 Star 数失败 {owner}/{repo}: {e}")
        return None

    async def monitor_stars(self):
        """后台轮询监控任务"""
        while self.running:
            watched = self._load_watched_repos()
            if watched:
                for full_name, last_count in watched.items():
                    owner, repo = full_name.split("/")
                    current_count = await self.get_star_count(owner, repo)
                    
                    if current_count is not None and current_count > last_count:
                        # Star 增加了！推送通知
                        diff = current_count - last_count
                        msg = f"🌟 GitHub Star 变动通知！\n项目：{full_name}\n新增：{diff} 个 Star\n当前总计：{current_count}"
                        
                        # 推送到指定群
                        await self.api.qq.post_group_msg(group_id=self.NOTIFY_GROUP_ID, text=msg)
                        
                        # 更新记录
                        watched[full_name] = current_count
                        self._save_watched_repos(watched)
                    
                    # 避免触发速率限制
                    await asyncio.sleep(5)
            
            # 每 5 分钟检查一次
            await asyncio.sleep(300)

    async def _reply(self, event, text):
        """统一回复逻辑，不使用 @ 提到用户"""
        if isinstance(event, GroupMessageEvent):
            await self.api.qq.post_group_msg(group_id=event.group_id, text=text)
        elif isinstance(event, PrivateMessageEvent):
            await self.api.qq.post_private_msg(user_id=event.user_id, text=text)

    async def handle_star_command(self, event, owner, repo, action):
        """处理批量 star/unstar"""
        tokens = self._load_tokens()
        if not tokens:
            await self._reply(event, "❌ 令牌池为空，请先添加 GitHub Token")
            return

        await self._reply(event, f"🚀 开始为 {owner}/{repo} 执行 {action} star，总计 {len(tokens)} 个账号...")
        
        success_count = 0
        tasks = [self._manage_star(token, owner, repo, action) for token in tokens]
        results = await asyncio.gather(*tasks)
        success_count = sum(1 for r in results if r)

        await self._reply(event, f"✅ 操作完成！\n项目：{owner}/{repo}\n动作：{action}\n成功：{success_count}\n失败：{len(tokens) - success_count}")

    async def handle_token_add(self, event, token):
        """添加 token"""
        if self._save_token(token):
            await self._reply(event, "✅ Token 添加成功！")
        else:
            await self._reply(event, "⚠️ Token 已存在，请勿重复添加")

    async def handle_token_list(self, event):
        """列出 token 统计"""
        tokens = self._load_tokens()
        count = len(tokens)
        if count == 0:
            await self._reply(event, "📪 令牌池目前为空")
        else:
            # 仅展示前3个 token 的脱敏信息
            preview = "\n".join([f"- {t[:10]}...{t[-4:]}" for t in tokens[:3]])
            if count > 3:
                preview += f"\n... 以及其他 {count-3} 个"
            await self._reply(event, f"📊 令牌池统计：\n当前共有 {count} 个有效 Token\n\n预览：\n{preview}")

    async def handle_watch_command(self, event, owner, repo):
        """添加项目监控"""
        full_name = f"{owner}/{repo}"
        watched = self._load_watched_repos()
        
        if full_name in watched:
            await self._reply(event, f"⚠️ 项目 {full_name} 已经在监控列表中了")
            return

        current_count = await self.get_star_count(owner, repo)
        if current_count is None:
            await self._reply(event, f"❌ 无法获取项目 {full_name} 的信息，请检查名称是否正确")
            return

        watched[full_name] = current_count
        self._save_watched_repos(watched)
        await self._reply(event, f"✅ 已开始监控 {full_name}\n当前 Star 数：{current_count}")

    async def handle_unwatch_command(self, event, owner, repo):
        """取消项目监控"""
        full_name = f"{owner}/{repo}"
        watched = self._load_watched_repos()
        
        if full_name not in watched:
            await self._reply(event, f"⚠️ 监控列表中没有项目 {full_name}")
            return

        del watched[full_name]
        self._save_watched_repos(watched)
        await self._reply(event, f"✅ 已停止监控 {full_name}")

    async def handle_watch_list(self, event):
        """列出监控中的项目"""
        watched = self._load_watched_repos()
        if not watched:
            await self._reply(event, "📪 监控列表目前为空")
            return

        list_text = "📊 监控项目列表：\n"
        for full_name, last_count in watched.items():
            list_text += f"- {full_name} (上次记录: {last_count})\n"
        
        await self._reply(event, list_text.strip())

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

        msg = event.raw_message.strip().lower()

        # 0) gh help
        if msg == "gh help":
            help_text = (
                "🌟 GitHub Star 管理帮助\n"
                "------------------\n"
                "1. 增加/减少 Star:\n"
                "   gh star <owner>/<repo> add\n"
                "   gh star <owner>/<repo> remove\n"
                "2. 监控项目 Star:\n"
                "   gh watch <owner>/<repo> (开启监控)\n"
                "   gh unwatch <owner>/<repo> (停止监控)\n"
                "   gh watch list (监控列表)\n"
                "3. Token 管理:\n"
                "   gh token add <token>\n"
                "   gh token list\n"
                "------------------\n"
                "注：仅限管理员使用"
            )
            await self._reply(event, help_text)
            return

        # 1) gh star <owner>/<repo> add|remove
        star_match = self.STAR_PATTERN.match(msg)
        if star_match:
            owner, repo, action = star_match.groups()
            await self.handle_star_command(event, owner, repo, action)
            return

        # 2) gh watch/unwatch/list
        watch_match = self.WATCH_PATTERN.match(msg)
        if watch_match:
            owner, repo = watch_match.groups()
            await self.handle_watch_command(event, owner, repo)
            return

        unwatch_match = self.UNWATCH_PATTERN.match(msg)
        if unwatch_match:
            owner, repo = unwatch_match.groups()
            await self.handle_unwatch_command(event, owner, repo)
            return

        if self.WATCH_LIST_PATTERN.match(msg):
            await self.handle_watch_list(event)
            return

        # 3) gh token add <token>
        token_match = self.TOKEN_ADD_PATTERN.match(msg)
        if token_match:
            token = token_match.group(1)
            await self.handle_token_add(event, token)
            return

        # 3) gh token list
        if self.TOKEN_LIST_PATTERN.match(msg):
            await self.handle_token_list(event)
            return
