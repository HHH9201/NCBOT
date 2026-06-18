# /home/hjh/BOT/NCBOT/plugins/xydj/main.py
# -*- coding: utf-8 -*-
"""
咸鱼单机（本地数据库版）
- 只从本地 SQLite 数据库搜索游戏资源
- 适配 NcatBot 5.0 框架
- 支持 1w+ 数据量优化
"""
import re
import asyncio
import logging
import sqlite3
import time
import json
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from ncatbot.plugin import BasePlugin
from ncatbot.event.qq import GroupMessageEvent
from ncatbot.types import PlainText, Reply, MessageArray, Image
from ncatbot.types.qq import ForwardConstructor
from ncatbot.core import registrar

logger = logging.getLogger("xydj")
DB_PATH = Path(__file__).resolve().parent / "tool" / "games.db"
CHECKIN_COOKIES_PATH = Path(__file__).resolve().parent / "qd" / "xydj" / "all_cookies.json"
CHECKIN_NOTIFY_GROUP = 695934967
CHECKIN_NOTIFY_FILE = Path(__file__).resolve().parent / "qd" / "xydj" / "checkin_notify.json"

FIELDS = ["rowid", "zh_name", "en_name", "version", "image", "update_time", "baidu_pan", "quark_pan", "xunlei", "extract_password", "online_link", "online_password", "online_last_update"]

# 罗马数字映射
ROMAN_TO_ARABIC = {
    'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5',
    'VI': '6', 'VII': '7', 'VIII': '8', 'IX': '9', 'X': '10',
    'XI': '11', 'XII': '12', 'XIII': '13', 'XIV': '14', 'XV': '15'
}
ARABIC_TO_ROMAN = {v: k for k, v in ROMAN_TO_ARABIC.items()}

# 中文数字映射
CHINESE_TO_ARABIC = {
    '一': '1', '二': '2', '三': '3', '四': '4', '五': '5',
    '六': '6', '七': '7', '八': '8', '九': '9', '十': '10'
}
ARABIC_TO_CHINESE = {v: k for k, v in CHINESE_TO_ARABIC.items()}

# 预编译正则表达式
RE_DIGITS = re.compile(r'\d+')
RE_ROMAN = re.compile(r'\b[IVX]+\b')
RE_CHINESE_NUM = re.compile(r'[一二三四五六七八九十]')

# 数据库连接（单例）
_db_conn = None
_db_ready = False

def get_db():
    """获取数据库连接（复用）"""
    global _db_conn, _db_ready
    if _db_conn is None:
        _db_conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _db_conn.row_factory = sqlite3.Row
        # 性能优化设置
        _db_conn.execute("PRAGMA journal_mode=WAL")
        _db_conn.execute("PRAGMA synchronous=NORMAL")
        _db_conn.execute("PRAGMA cache_size=20000")
        _db_conn.execute("PRAGMA temp_store=MEMORY")
        _db_conn.execute("PRAGMA mmap_size=30000000")
        _db_conn.execute("PRAGMA page_size=4096")
    return _db_conn

def init_db():
    """初始化数据库索引"""
    global _db_ready
    try:
        conn = get_db()
        # 创建索引
        conn.execute("CREATE INDEX IF NOT EXISTS idx_zh_name ON games(zh_name)")
        # 创建复合索引
        conn.execute("CREATE INDEX IF NOT EXISTS idx_has_link ON games(baidu_pan, quark_pan, xunlei)")

        # 检查 FTS 表是否存在
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='games_fts'")
        if not cursor.fetchone():
            # 尝试使用 trigram 分词器以获得更好的中文模糊搜索支持
            try:
                conn.execute("""
                    CREATE VIRTUAL TABLE games_fts USING fts5(
                        zh_name,
                        content='games',
                        content_rowid='rowid',
                        tokenize='trigram'
                    )
                """)
            except Exception:
                # 如果 trigram 不支持，回退到默认分词器
                conn.execute("""
                    CREATE VIRTUAL TABLE games_fts USING fts5(
                        zh_name,
                        content='games',
                        content_rowid='rowid'
                    )
                """)
            # 批量插入数据到 FTS（使用 rowid 而不是 id）
            conn.execute("""
                INSERT INTO games_fts(rowid, zh_name)
                SELECT rowid, zh_name FROM games
            """)

        conn.commit()
        _db_ready = True
        logger.info("数据库索引初始化完成")
    except Exception as e:
        logger.error(f"数据库索引初始化失败: {e}")

def row_to_dict(row) -> dict:
    """数据库行转字典"""
    d = {k: row[i] for i, k in enumerate(FIELDS)}
    # 映射字段以保持兼容
    d['baidu'] = d['baidu_pan']
    d['kuake'] = d['quark_pan']
    d['extract_code'] = d['extract_password']
    return d

def convert_number(text: str) -> Tuple[str, ...]:
    """转换数字：阿拉伯数字 ↔ 罗马数字 ↔ 中文数字"""
    variants = {text}
    
    # 1. 阿拉伯数字 -> 罗马 & 中文
    for num in RE_DIGITS.findall(text):
        if num in ARABIC_TO_ROMAN:
            variants.add(text.replace(num, ARABIC_TO_ROMAN[num]))
        if num in ARABIC_TO_CHINESE:
            variants.add(text.replace(num, ARABIC_TO_CHINESE[num]))
            
    # 2. 罗马数字 -> 阿拉伯
    for roman in RE_ROMAN.findall(text):
        if roman in ROMAN_TO_ARABIC:
            arabic = ROMAN_TO_ARABIC[roman]
            variants.add(text.replace(roman, arabic))
            # 进一步尝试转中文
            if arabic in ARABIC_TO_CHINESE:
                variants.add(text.replace(roman, ARABIC_TO_CHINESE[arabic]))
                
    # 3. 中文数字 -> 阿拉伯
    for cn_num in RE_CHINESE_NUM.findall(text):
        if cn_num in CHINESE_TO_ARABIC:
            arabic = CHINESE_TO_ARABIC[cn_num]
            variants.add(text.replace(cn_num, arabic))
            # 进一步尝试转罗马
            if arabic in ARABIC_TO_ROMAN:
                variants.add(text.replace(cn_num, ARABIC_TO_ROMAN[arabic]))
                
    return tuple(variants)

# 预编译查询语句（使用 rowid 替代 id）
_FTS_QUERY = """
    SELECT g.rowid, g.zh_name, g.en_name, g.version, g.image,
           g.update_time, g.baidu_pan, g.quark_pan, g.xunlei, g.extract_password,
           g.online_link, g.online_password, g.online_last_update
    FROM games g
    JOIN games_fts fts ON g.rowid = fts.rowid
    WHERE games_fts MATCH ?
    AND (g.baidu_pan != '' OR g.quark_pan != '' OR g.xunlei != '' OR g.online_link != '')
    LIMIT 20
"""

_LIKE_QUERY_SINGLE = """
    SELECT rowid, zh_name, en_name, version, image,
           update_time, baidu_pan, quark_pan, xunlei, extract_password,
           online_link, online_password, online_last_update
    FROM games
    WHERE zh_name LIKE ?
    AND (baidu_pan != '' OR quark_pan != '' OR xunlei != '' OR online_link != '')
    LIMIT 20
"""

@lru_cache(maxsize=512)
def search_game(name: str) -> tuple:
    """搜索游戏（优化版）"""
    if not _db_ready:
        return "数据库未就绪", []
    
    start_time = time.time()
    try:
        conn = get_db()
        
        # 获取搜索变体（原始词 + 转换后的词）
        variants = convert_number(name)
        all_games = []
        seen_ids = set()
        
        # 构建 FTS 查询：所有变体用 OR 连接
        fts_terms = []
        for variant in variants:
            # 处理 FTS 特殊字符
            term = variant.replace('"', '""')
            if ' ' in term:
                term = f'"{term}"'
            fts_terms.append(term)
        
        # 用 OR 连接所有变体进行 FTS 搜索
        fts_query = " OR ".join(fts_terms)
        cursor = conn.execute(_FTS_QUERY, (fts_query,))
        for row in cursor:
            if row[0] not in seen_ids:
                seen_ids.add(row[0])
                all_games.append(row_to_dict(row))
        
        # 如果 FTS 没找到，用 LIKE 兜底
        if not all_games:
            for variant in variants:
                pattern = f"%{variant}%"
                cursor = conn.execute(_LIKE_QUERY_SINGLE, (pattern,))
                for row in cursor:
                    if row[0] not in seen_ids:
                        seen_ids.add(row[0])
                        all_games.append(row_to_dict(row))
                        if len(all_games) >= 20:
                            break
                if len(all_games) >= 20:
                    break
        
        elapsed = (time.time() - start_time) * 1000
        logger.info(f"搜索 '{name}' (变体: {variants}) 完成，找到 {len(all_games)} 条结果，耗时 {elapsed:.1f}ms")
        
        return (None, all_games) if all_games else (None, [])
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        return "搜索服务异常，请稍后再试", []

@lru_cache(maxsize=1024)
def get_game(game_id: int) -> Optional[dict]:
    """获取游戏详情（带缓存）"""
    try:
        conn = get_db()
        cursor = conn.execute(
            "SELECT rowid, zh_name, en_name, version, image, update_time, baidu_pan, quark_pan, xunlei, extract_password, online_link, online_password, online_last_update FROM games WHERE rowid = ?",
            (game_id,)
        )
        row = cursor.fetchone()
        return row_to_dict(row) if row else None
    except Exception as e:
        logger.error(f"获取游戏失败: {e}")
        return None

def build_message(game: Dict[str, Any]) -> list:
    """构建游戏资源消息"""
    content_parts = [f"【游戏资源】\n游戏中文名字：{game['zh_name']}"]

    if game.get("version"):
        content_parts.append(f"\n版本：{game['version']}")

    if game.get("en_name"):
        content_parts.append(f"\n英文名：{game['en_name']}")

    content_parts.append("\n")

    # 单机版资源
    has_single = game.get("baidu") or game.get("kuake") or game.get("xunlei")
    if has_single:
        content_parts.append("\n📦 单机版：")
        if game.get("baidu"):
            content_parts.append(f"\n百度网盘：{game['baidu']}")
        if game.get("kuake"):
            content_parts.append(f"\n夸克网盘：{game['kuake']}")
        if game.get("xunlei"):
            content_parts.append(f"\n迅雷网盘：{game['xunlei']}")
        if game.get("extract_code"):
            content_parts.append(f"\n提取码：{game['extract_code']}")
        if game.get("update_time"):
            content_parts.append(f"\n更新时间：{game['update_time']}")

    # 联机版资源
    if game.get("online_link"):
        if has_single:
            content_parts.append("\n")
        content_parts.append("\n🌐 联机版：")
        content_parts.append(f"\n下载链接：{game['online_link']}")
        # 密码默认为 online-fix.me
        password = game.get("online_password") if game.get("online_password") else "online-fix.me"
        content_parts.append(f"\n版本/密码：{password}")
        if game.get("online_last_update"):
            content_parts.append(f"\n更新时间：{game['online_last_update']}")

    content_parts.append("\n")

    messages = ["".join(content_parts)]

    # 添加网站推荐消息（第二条）
    site_info = """
📌 自己找游戏：
🎮 单机游戏：https://www.gamer520.com/
🌐 联机游戏：https://byruthub.org/
（密码不正确可以自行查找）
"""
    messages.append(site_info)

    # 添加图片（第三条）
    if game.get("image"):
        messages.append({"type": "image", "url": game["image"]})

    # 添加文档信息（第四条）
    doc_info = """
📚 常见问题文档：

《bt种子使用》https://www.yuque.com/lanmeng-ijygo/ey7ah4/ng90x573gk7xh0wm?singleDoc#
《文件损坏怎么办？》https://www.yuque.com/lanmeng-ijygo/ey7ah4/qqfafhy1g42z42wg?singleDoc#
《设置中文方法》https://www.yuque.com/lanmeng-ijygo/ey7ah4/kdsnhprf6bprtgz5?singleDoc#
《压缩包下载安装》https://www.yuque.com/lanmeng-ijygo/ey7ah4/xobm6lsb326lu5kx?singleDoc#
《常见问题解决》https://www.yuque.com/lanmeng-ijygo/ey7ah4/ko0igrc5te8p4fn2?singleDoc#
《游戏打不开/报错/黑屏》https://www.yuque.com/lanmeng-ijygo/ey7ah4/fwfmdu3erlku9a1e?singleDoc#
《搜索和使用联机游戏》https://www.yuque.com/lanmeng-ijygo/ey7ah4/fe9hfep86cw7coku?singleDoc#

发送关键字查看详细文档：
联机补丁 | 种子 | 文件损坏 | 设置中文 | 压缩包 | 常见问题 | 游戏打不开 | 枪火存档
"""
    messages.append(doc_info)

    return messages


class SearchSession:
    __slots__ = ['user_id', 'games', 'task']
    
    def __init__(self, user_id, games, task=None):
        self.user_id = user_id
        self.games = games
        self.task = task


class Xydj(BasePlugin):
    name = "xydj"
    version = "3.1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sessions = {}

    async def send_reply(self, event, text: str, msg_id: int = None):
        """统一回复方法"""
        if msg_id:
            await self.api.qq.post_group_msg(
                group_id=event.group_id, 
                rtf=MessageArray([Reply(id=msg_id), PlainText(text=text)])
            )
        else:
            await event.reply(rtf=MessageArray([PlainText(text=text)]))

    async def send_forward(self, group_id, messages, user_id, nickname):
        """发送合并转发消息：文字和图片一起发送，图片超时时跳过"""
        fc = ForwardConstructor()
        has_content = False

        for msg in messages:
            if isinstance(msg, str):
                fc.attach_text(msg, user_id, nickname)
                has_content = True
            elif isinstance(msg, dict) and msg.get("type") == "image":
                try:
                    fc.attach_image(msg["url"], user_id, nickname)
                    has_content = True
                except Exception as e:
                    logger.warning(f"添加图片到合并转发失败，跳过该图片: {e}")

        if has_content:
            try:
                await self.api.qq.post_group_forward_msg(group_id, fc.build())
            except Exception as e:
                logger.warning(f"合并转发发送失败，降级为普通消息: {e}")
                # 降级：逐条发送文字消息
                for msg in messages:
                    if isinstance(msg, str):
                        try:
                            await self.api.qq.post_group_msg(
                                group_id=group_id,
                                rtf=MessageArray([PlainText(text=msg)])
                            )
                            await asyncio.sleep(0.5)
                        except Exception as e2:
                            logger.error(f"降级发送文字消息失败: {e2}")
                    elif isinstance(msg, dict) and msg.get("type") == "image":
                        # 降级时跳过图片，避免超时
                        logger.info("降级模式下跳过图片发送")

    async def process_game(self, game: Dict[str, Any], event: GroupMessageEvent):
        """处理游戏资源发送"""
        try:
            user_id = str(event.user_id)
            if "baidu" not in game:
                game = get_game(game["rowid"])
                if not game:
                    await self.send_reply(event, "❌ 获取游戏详情失败。")
                    return

            # 检查是否有单机版或联机版资源
            has_resource = (game.get("baidu") or game.get("kuake") or game.get("xunlei") or
                           game.get("online_link"))
            if not has_resource:
                await self.send_reply(event, "❌ 该游戏暂无可用下载链接。")
                return

            messages = build_message(game)
            await self.send_forward(event.group_id, messages, user_id, event.sender.nickname)
        except Exception as e:
            logger.error(f"处理资源失败: {e}")
            await self.send_reply(event, "❌ 发送资源失败，请稍后再试。")

    def cleanup(self, group_id):
        """清理会话"""
        session = self.sessions.pop(group_id, None)
        if session and session.task:
            session.task.cancel()

    async def timeout(self, event, group_id):
        """超时处理"""
        await asyncio.sleep(20)
        self.cleanup(group_id)
        await self.send_reply(event, "⏰ 操作超时，已取消。")

    def get_message_text(self, event: GroupMessageEvent) -> str:
        """获取消息文本"""
        return event.raw_message.strip() if hasattr(event, "raw_message") and event.raw_message else ""

    @registrar.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent):
        msg = self.get_message_text(event)
        
        # 处理序号选择
        session = self.sessions.get(event.group_id)
        if session and event.user_id == session.user_id:
            if msg == "0":
                self.cleanup(event.group_id)
                await self.send_reply(event, "操作已取消")
                return
            if msg.isdigit():
                idx = int(msg) - 1
                if 0 <= idx < len(session.games):
                    game = session.games[idx]
                    self.cleanup(event.group_id)
                    await self.process_game(game, event)
                return

        # 处理搜索命令
        if msg.startswith("搜索"):
            game_name = msg[2:].strip()
            if not game_name:
                return
            
            if len(game_name) > 50:
                await self.send_reply(event, "❌ 搜索词过长，请缩短至50字以内")
                return
            
            error_msg, games = search_game(game_name)
            
            if error_msg or not games:
                not_found_msg = error_msg or """暂未收录该游戏，可自行去以下网站查找：
🎮 单机游戏：https://www.gamer520.com/
🌐 联机游戏：https://byruthub.org/"""
                await self.send_reply(event, not_found_msg, event.message_id)
                return
            
            if len(games) == 1:
                await self.process_game(games[0], event)
                return
            
            # 构建结果列表
            text_lines = []
            for i, g in enumerate(games[:20]):
                line = f"{i+1}. {g['zh_name']}"
                if g.get('en_name'):
                    line += f"\n   英文名: {g['en_name']}"
                if g.get('version'):
                    line += f"\n   版本: {g['version']}"
                text_lines.append(line)
            
            result_text = f"🎯 发现 {len(games)} 款游戏"
            if len(games) > 20:
                result_text += "（显示前20个）"
            result_text += "\n\n" + "\n\n".join(text_lines) + "\n⏰ 20秒内回复序号选择 | 回复 0 取消"
            
            await self.send_reply(event, result_text)
            
            session = SearchSession(event.user_id, games)
            session.task = asyncio.create_task(self.timeout(event, event.group_id))
            self.sessions[event.group_id] = session

    # ==================== 签到通知 ====================

    async def _checkin_notifier(self):
        """每天 8:00-9:00 检查签到结果文件并发送通知"""
        while True:
            now = datetime.now()
            # 计算下一个 8:00
            target = now.replace(hour=8, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            logger.info(f"[签到通知] 下次检查时间: {target.strftime('%Y-%m-%d %H:%M:%S')}, 等待 {wait_seconds:.0f} 秒")
            await asyncio.sleep(wait_seconds)

            # 8:00 到了，在接下来 1 小时内每 5 分钟检查一次（共 12 次）
            for i in range(12):
                try:
                    if CHECKIN_NOTIFY_FILE.exists():
                        with open(CHECKIN_NOTIFY_FILE, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        msg = data.get('message', '')
                        group_id = data.get('group_id', CHECKIN_NOTIFY_GROUP)
                        if msg:
                            await self.api.qq.post_group_msg(
                                group_id=group_id,
                                rtf=MessageArray([PlainText(text=msg)])
                            )
                            logger.info(f"签到通知已发送到群 {group_id}")
                        # 发送后删除文件
                        CHECKIN_NOTIFY_FILE.unlink()
                        break  # 发送成功，退出本轮检查
                except Exception as e:
                    logger.error(f"检查签到通知文件失败: {e}")
                await asyncio.sleep(300)  # 5 分钟后再次检查

    async def on_load(self):
        logger.info(f"[{self.name}] 插件已加载，版本: {self.version}")
        try:
            init_db()
            get_db()
            logger.info("数据库初始化完成")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
        # 启动签到结果通知检查任务
        asyncio.create_task(self._checkin_notifier())

    async def on_unload(self):
        global _db_conn
        for group_id in list(self.sessions.keys()):
            self.cleanup(group_id)
        if _db_conn:
            _db_conn.close()
            _db_conn = None
