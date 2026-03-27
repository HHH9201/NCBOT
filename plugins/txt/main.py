# /home/hjh/BOT/NCBOT/plugins/txt/main.py
# NcatBot 5.x 文档查询插件
import os
import yaml
import logging
from typing import Dict, List, Optional
from pathlib import Path

from ncatbot.plugin import BasePlugin
from ncatbot.core import registrar
from ncatbot.event.qq import GroupMessageEvent
from ncatbot.types import Reply

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class txt(BasePlugin):
    """文档查询插件 - 关键词查询文档内容"""
    name = "txt"
    version = "1.0.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 初始化配置
        self.DOC_MAP: Dict[str, str] = {}
        self.keywords_config: Dict = {}
        self.case_sensitive: bool = False
        self.default_reply_enabled: bool = True
        self.default_reply_message: str = "请发送 '文档' 查看所有可用的关键词列表"

        # 加载配置
        self._load_config()
        # 初始化缓存
        self._init_cache()

    def _load_config(self):
        """从配置文件加载关键词和设置"""
        config_path = os.path.join(os.path.dirname(__file__), "tool", "keywords.yaml")
        try:
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    self.keywords_config = yaml.safe_load(f) or {}

                # 加载关键词映射
                if "keywords" in self.keywords_config:
                    self.DOC_MAP = self.keywords_config["keywords"]

                # 加载其他设置
                self.case_sensitive = self.keywords_config.get("case_sensitive", False)
                default_reply = self.keywords_config.get("default_reply", {})
                self.default_reply_enabled = default_reply.get("enabled", True)
                self.default_reply_message = default_reply.get("message", self.default_reply_message)

                logger.info(f"成功加载配置，共 {len(self.DOC_MAP)} 个关键词")
            else:
                logger.warning(f"配置文件不存在: {config_path}，使用默认配置")
                self._set_default_config()
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            self._set_default_config()

    def _set_default_config(self):
        """设置默认配置"""
        self.DOC_MAP = {
            "种子": "《bt种子使用》https://www.yuque.com/lanmeng-ijygo/ey7ah4/ng90x573gk7xh0wm?singleDoc# ",
            "文件损坏": "《文件损坏怎么办？》https://www.yuque.com/lanmeng-ijygo/ey7ah4/qqfafhy1g42z42wg?singleDoc# ",
            "设置中文": "《设置中文方法》https://www.yuque.com/lanmeng-ijygo/ey7ah4/kdsnhprf6bprtgz5?singleDoc#",
            "压缩包": "《这么多压缩包怎么下载、怎么安装？》https://www.yuque.com/lanmeng-ijygo/ey7ah4/xobm6lsb326lu5kx?singleDoc# ",
            "常见问题": "《详细的常见问题解决》https://www.yuque.com/lanmeng-ijygo/ey7ah4/ko0igrc5te8p4fn2?singleDoc#",
            "游戏打不开": "《游戏打不开、提示报错、黑屏等问题》https://www.yuque.com/lanmeng-ijygo/ey7ah4/fwfmdu3erlku9a1e?singleDoc# ",
            "联机补丁": "《搜索和使用联机游戏》https://www.yuque.com/lanmeng-ijygo/ey7ah4/fe9hfep86cw7coku?singleDoc#",
            "枪火存档": "枪火重生学习版存档位置：点击，C盘，用户，公用，公用文档，onlinefix，1217060，Saves，替换存档文件",
            "文档": "发送关键字查看文档:\n1.联机补丁\n2.种子\n3.文件损坏\n4.设置中文\n5.压缩包下载\n6.常见问题\n7.游戏打不开\n8.枪火存档"
        }

    def _init_cache(self):
        """初始化缓存"""
        # 预处理关键词，提高匹配效率
        self._keyword_cache: Dict[str, str] = {}
        for keyword, doc_info in self.DOC_MAP.items():
            cache_key = keyword.lower() if not self.case_sensitive else keyword
            self._keyword_cache[cache_key] = doc_info

    def _find_matching_keyword(self, text: str) -> Optional[str]:
        """查找匹配的关键词，返回对应的文档信息"""
        # 根据配置决定是否区分大小写
        search_text = text.lower() if not self.case_sensitive else text

        # 优先匹配完全匹配的关键词
        for keyword, doc_info in self.DOC_MAP.items():
            keyword_search = keyword.lower() if not self.case_sensitive else keyword
            if keyword_search == search_text:
                return doc_info

        # 其次匹配包含的关键词（按顺序，优先匹配前面的）
        for keyword, doc_info in self.DOC_MAP.items():
            keyword_search = keyword.lower() if not self.case_sensitive else keyword
            if keyword_search in search_text:
                return doc_info

        return None

    @registrar.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent):
        """收到群消息即扫描关键词"""
        try:
            text = event.raw_message.strip()
            if not text:
                return

            # 查找匹配的关键词
            doc_info = self._find_matching_keyword(text)

            if doc_info:
                content = f"📄 {doc_info}"
                await event.reply(content)
                logger.debug(f"已回复关键词: {text}, 文档信息: {doc_info}")
            elif self.default_reply_enabled and "文档" in text:
                # 如果包含"文档"但没有匹配到具体关键词，发送默认提示
                await event.reply(self.default_reply_message)
        except Exception as e:
            logger.error(f"处理消息时发生错误: {e}")
            try:
                await event.reply("处理请求时发生错误，请稍后重试")
            except:
                pass

    async def on_load(self):
        logger.info(f"🚀 {self.name} v{self.version} 已加载")
        logger.info(f"当前配置: 区分大小写={self.case_sensitive}, 默认回复={self.default_reply_enabled}")
        logger.info(f"可用关键词数量: {len(self.DOC_MAP)}")
