# -*- coding: utf-8 -*-
"""
资源收集插件
自动提取群聊中的网盘链接并存储到数据库
使用 group_permissions 表的 resource_collector 字段控制（0=允许, 1=拒绝）
默认拒绝，需要手动开启
不回复任何消息
"""
import re
import logging
from typing import Optional, Dict
from ncatbot.plugin import BasePlugin
from ncatbot.core import registrar
from ncatbot.event.qq import GroupMessageEvent
from common.db_permissions import db_permission_manager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ResourceCollector(BasePlugin):
    """资源收集插件 - 静默收集网盘资源"""
    name = "ResourceCollector"
    version = "1.0.0"

    def _extract_resource_name(self, message: str) -> str:
        """提取资源名称（第一行或前50个字符）"""
        lines = message.strip().split('\n')
        if lines:
            # 取第一行，去掉链接部分
            first_line = lines[0]
            # 去掉链接
            first_line = re.sub(r'https?://\S+', '', first_line)
            # 去掉多余空格
            first_line = first_line.strip()
            if first_line:
                return first_line[:100]  # 限制长度
        return "未知资源"

    def _extract_links(self, message: str) -> Dict[str, Optional[str]]:
        """提取各种网盘链接"""
        links = {
            "quark": None,    # 夸克
            "uc": None,       # UC
            "baidu": None,    # 百度
            "aliyun": None,   # 阿里云
            "tianyi": None,   # 天翼
            "xunlei": None    # 迅雷
        }

        # 夸克网盘
        quark_match = re.search(r'https?://pan\.quark\.cn/s/[a-zA-Z0-9]+', message)
        if quark_match:
            links["quark"] = quark_match.group(0)

        # UC网盘
        uc_match = re.search(r'https?://drive\.uc\.cn/s/[a-zA-Z0-9]+', message)
        if uc_match:
            links["uc"] = uc_match.group(0)

        # 百度网盘
        baidu_match = re.search(r'https?://pan\.baidu\.com/s/[a-zA-Z0-9_-]+', message)
        if baidu_match:
            links["baidu"] = baidu_match.group(0)

        # 阿里云盘
        aliyun_match = re.search(r'https?://www\.alipan\.com/s/[a-zA-Z0-9]+', message)
        if aliyun_match:
            links["aliyun"] = aliyun_match.group(0)

        # 天翼云盘
        tianyi_match = re.search(r'https?://cloud\.189\.cn/t/[a-zA-Z0-9]+', message)
        if tianyi_match:
            links["tianyi"] = tianyi_match.group(0)

        # 迅雷云盘
        xunlei_match = re.search(r'https?://pan\.xunlei\.com/s/[a-zA-Z0-9]+', message)
        if xunlei_match:
            links["xunlei"] = xunlei_match.group(0)

        return links

    def _has_any_link(self, links: Dict[str, Optional[str]]) -> bool:
        """检查是否有任何链接"""
        return any(link is not None for link in links.values())

    async def _save_resource(self, resource_name: str, links: Dict[str, Optional[str]],
                            group_id: str):
        """保存资源到数据库"""
        try:
            # 使用 db_permission_manager 的 save_resource 方法
            resource_id = await db_permission_manager.save_resource(
                name=resource_name,
                links=links,
                group_id=group_id
            )

            if resource_id:
                logger.info(f"[Resource] 已保存资源: {resource_name[:30]}... (ID: {resource_id})")

        except Exception as e:
            logger.error(f"[Resource] 保存资源失败: {e}")

    @registrar.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent):
        """处理群消息 - 静默收集资源"""
        # 检查该群是否允许资源收集（使用权限系统）
        # resource_collector: 0=允许, 1=拒绝（默认）
        is_enabled = await db_permission_manager.is_plugin_enabled(
            event.group_id, "resource_collector", auto_create=True
        )
        if not is_enabled:
            return

        # 获取消息内容
        message = event.raw_message.strip()
        if not message:
            return

        # 提取链接
        links = self._extract_links(message)

        # 如果没有链接，不处理
        if not self._has_any_link(links):
            return

        # 提取资源名称
        resource_name = self._extract_resource_name(message)

        # 保存到数据库（静默处理，不回复）
        await self._save_resource(
            resource_name=resource_name,
            links=links,
            group_id=str(event.group_id)
        )

    async def on_load(self):
        """插件加载时初始化"""
        try:
            await db_permission_manager.initialize()
            logger.info(f"📦 {self.name} v{self.version} 已加载")
            logger.info("   模式: 静默收集，不回复消息")
            logger.info("   默认: 拒绝收集（需要在群权限中开启）")
        except Exception as e:
            logger.error(f"[Resource] 插件加载失败: {e}")
