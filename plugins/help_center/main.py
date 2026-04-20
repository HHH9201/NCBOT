import base64
import io
import logging
from pathlib import Path
from typing import Any

import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from ncatbot.core.registry import registrar
from ncatbot.event.qq import GroupMessageEvent, PrivateMessageEvent
from ncatbot.plugin import NcatBotPlugin

from common.permissions import permission_manager

logger = logging.getLogger(__name__)


DEFAULT_MENU: dict[str, Any] = {
    "title": "NCBOT 帮助中心",
    "subtitle": "常用命令一图速览",
    "description": "发送 帮助 / 菜单 / help 即可再次查看",
    "footer": "Tips: 部分命令仅管理员可用，具体以群权限配置为准",
    "aliases": ["帮助", "菜单", "help", "Help"],
    "sections": [
        {
            "title": "资源搜索",
            "accent": "#7C5CFF",
            "items": [
                {"command": "搜库 游戏名", "desc": "优先从本地资源库搜索，速度快"},
                {"command": "搜网 游戏名", "desc": "从资源站搜索并同步收录"},
                {"command": "搜索 游戏名", "desc": "综合搜索入口，适合日常使用"},
            ],
        },
        {
            "title": "邮箱工具",
            "accent": "#23C6B8",
            "items": [
                {"command": "给一个账号", "desc": "快速领取 1 个 Trae 邮箱账号"},
                {"command": "给N个账号", "desc": "单次最多 20 个，按需批量领取"},
                {"command": "账号统计", "desc": "查看邮箱总数、已分配和未分配数量"},
            ],
        },
        {
            "title": "数据查询",
            "accent": "#FFB84D",
            "items": [
                {"command": "史低 游戏名", "desc": "查询 Steam 游戏历史最低价格"},
                {"command": "steam 游戏名", "desc": "与史低同义，支持英文指令"},
                {"command": "当前额度", "desc": "查看当前可用资源额度"},
            ],
        },
        {
            "title": "管理命令",
            "accent": "#FF6B8A",
            "items": [
                {"command": "查询今日人数", "desc": "查看小程序今日新增用户数"},
                {"command": "123456修改为654321", "desc": "修改 6 位虚拟 ID"},
                {"command": "123456增加上限10个", "desc": "给指定虚拟 ID 增加奖励额度"},
            ],
        },
    ],
}


class HelpCenter(NcatBotPlugin):
    name = "help_center"
    version = "1.0.0"

    FONT_CANDIDATES = [
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.plugin_dir = Path(__file__).resolve().parent
        self.menu_path = self.plugin_dir / "menu.yaml"
        self.cache_dir = self.plugin_dir / "cache"
        self.cache_path = self.cache_dir / "help_menu.png"

    async def on_load(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info("%s v%s 已加载", self.name, self.version)

    @registrar.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent):
        if not permission_manager.is_plugin_enabled(event.group_id, "help_center"):
            return
        await self._maybe_send_help(event)

    @registrar.on_private_message()
    async def on_private_message(self, event: PrivateMessageEvent):
        await self._maybe_send_help(event)

    async def _maybe_send_help(self, event):
        menu = self._load_menu()
        aliases = {str(item).strip().lower() for item in menu.get("aliases", []) if str(item).strip()}
        if event.raw_message.strip().lower() not in aliases:
            return

        try:
            image_b64 = self._get_help_image_base64(menu)
            await event.reply(image=image_b64)
        except Exception as exc:
            logger.exception("[help_center] 帮助图发送失败: %s", exc)
            await event.reply("帮助图生成失败，请稍后重试。")

    def _load_menu(self) -> dict[str, Any]:
        if not self.menu_path.exists():
            return DEFAULT_MENU

        try:
            with open(self.menu_path, "r", encoding="utf-8") as f:
                user_menu = yaml.safe_load(f) or {}
            return self._merge_menu(DEFAULT_MENU, user_menu)
        except Exception as exc:
            logger.warning("[help_center] 读取菜单配置失败，改用默认配置: %s", exc)
            return DEFAULT_MENU

    def _merge_menu(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._merge_menu(merged[key], value)
            else:
                merged[key] = value
        return merged

    def _get_help_image_base64(self, menu: dict[str, Any]) -> str:
        if self._should_regenerate():
            image = self._render_menu(menu)
            image.save(self.cache_path, format="PNG")

        with open(self.cache_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        return f"base64://{encoded}"

    def _should_regenerate(self) -> bool:
        if not self.cache_path.exists():
            return True

        cache_mtime = self.cache_path.stat().st_mtime
        source_paths = [Path(__file__)]
        if self.menu_path.exists():
            source_paths.append(self.menu_path)

        return any(path.stat().st_mtime > cache_mtime for path in source_paths)

    def _render_menu(self, menu: dict[str, Any]) -> Image.Image:
        width = 1240
        margin = 52
        card_gap = 24
        card_width = (width - margin * 2 - card_gap) // 2

        title_font = self._load_font(56)
        subtitle_font = self._load_font(28)
        desc_font = self._load_font(22)
        section_font = self._load_font(30)
        command_font = self._load_font(24)
        body_font = self._load_font(21)
        footer_font = self._load_font(20)

        sections = menu.get("sections", []) or []
        card_heights = [
            self._measure_section_height(section, card_width, section_font, command_font, body_font)
            for section in sections
        ]

        header_height = 260
        row_gap = 24
        rows: list[int] = []
        for index in range(0, len(card_heights), 2):
            rows.append(max(card_heights[index:index + 2]))

        total_height = header_height + margin + sum(rows) + max(0, len(rows) - 1) * row_gap + 110
        canvas = Image.new("RGBA", (width, total_height), "#0B1020")
        self._paint_background(canvas)

        draw = ImageDraw.Draw(canvas)
        self._draw_header(
            draw=draw,
            menu=menu,
            width=width,
            margin=margin,
            title_font=title_font,
            subtitle_font=subtitle_font,
            desc_font=desc_font,
        )

        top = header_height
        for row_index in range(0, len(sections), 2):
            row_sections = sections[row_index:row_index + 2]
            row_height = rows[row_index // 2]
            for col_index, section in enumerate(row_sections):
                left = margin + col_index * (card_width + card_gap)
                self._draw_section_card(
                    canvas=canvas,
                    section=section,
                    left=left,
                    top=top,
                    width=card_width,
                    height=row_height,
                    section_font=section_font,
                    command_font=command_font,
                    body_font=body_font,
                )
            top += row_height + row_gap

        footer_text = str(menu.get("footer", DEFAULT_MENU["footer"]))
        self._draw_text(
            draw,
            footer_text,
            footer_font,
            fill="#B9C4E0",
            xy=(margin, total_height - 66),
        )

        return canvas

    def _paint_background(self, canvas: Image.Image) -> None:
        width, height = canvas.size
        draw = ImageDraw.Draw(canvas)
        top_color = (11, 16, 32)
        bottom_color = (20, 27, 45)
        for y in range(height):
            ratio = y / max(height - 1, 1)
            color = tuple(
                int(top_color[i] + (bottom_color[i] - top_color[i]) * ratio)
                for i in range(3)
            )
            draw.line([(0, y), (width, y)], fill=color)

        glow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        glow = ImageDraw.Draw(glow_layer)
        glow.ellipse((-80, -20, 380, 320), fill=(124, 92, 255, 70))
        glow.ellipse((width - 360, 30, width + 40, 400), fill=(35, 198, 184, 64))
        glow.ellipse((width // 2 - 170, height - 240, width // 2 + 200, height + 60), fill=(255, 107, 138, 42))
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(44))
        canvas.alpha_composite(glow_layer)

    def _draw_header(
        self,
        draw: ImageDraw.ImageDraw,
        menu: dict[str, Any],
        width: int,
        margin: int,
        title_font: ImageFont.FreeTypeFont,
        subtitle_font: ImageFont.FreeTypeFont,
        desc_font: ImageFont.FreeTypeFont,
    ) -> None:
        panel_height = 180
        panel = (margin, 40, width - margin, 40 + panel_height)
        draw.rounded_rectangle(panel, radius=34, fill=(17, 24, 39, 196), outline=(255, 255, 255, 28), width=1)
        draw.rounded_rectangle((margin + 26, 64, margin + 166, 100), radius=18, fill=(124, 92, 255, 220))
        self._draw_text(draw, "HELP CENTER", subtitle_font, fill="white", xy=(margin + 48, 68))
        self._draw_text(draw, str(menu.get("title", DEFAULT_MENU["title"])), title_font, fill="white", xy=(margin + 30, 108))
        self._draw_text(draw, str(menu.get("subtitle", DEFAULT_MENU["subtitle"])), subtitle_font, fill="#DCE6FF", xy=(margin + 30, 170))

        desc_lines = self._wrap_text(str(menu.get("description", DEFAULT_MENU["description"])), desc_font, 420)
        desc_x = width - margin - 430
        desc_y = 96
        for line in desc_lines:
            self._draw_text(draw, line, desc_font, fill="#C1CCE7", xy=(desc_x, desc_y))
            desc_y += 30

    def _measure_section_height(
        self,
        section: dict[str, Any],
        card_width: int,
        section_font: ImageFont.FreeTypeFont,
        command_font: ImageFont.FreeTypeFont,
        body_font: ImageFont.FreeTypeFont,
    ) -> int:
        height = 96
        content_width = card_width - 52

        for item in section.get("items", []) or []:
            command_lines = self._wrap_text(str(item.get("command", "")), command_font, content_width - 28)
            desc_lines = self._wrap_text(str(item.get("desc", "")), body_font, content_width)
            height += 28 + len(command_lines) * 30 + 8 + len(desc_lines) * 26 + 16

        return max(height + 18, 200)

    def _draw_section_card(
        self,
        canvas: Image.Image,
        section: dict[str, Any],
        left: int,
        top: int,
        width: int,
        height: int,
        section_font: ImageFont.FreeTypeFont,
        command_font: ImageFont.FreeTypeFont,
        body_font: ImageFont.FreeTypeFont,
    ) -> None:
        card = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(card)
        accent = self._hex_to_rgba(str(section.get("accent", "#7C5CFF")), 255)

        draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=28, fill=(16, 23, 37, 208), outline=(255, 255, 255, 26), width=1)
        draw.rounded_rectangle((18, 18, width - 18, 26), radius=4, fill=accent)
        draw.rounded_rectangle((22, 42, 66, 86), radius=16, fill=(255, 255, 255, 16))
        self._draw_text(draw, str(section.get("title", "菜单"))[:1], section_font, fill="white", xy=(34, 44))
        self._draw_text(draw, str(section.get("title", "菜单")), section_font, fill="white", xy=(84, 46))

        current_y = 106
        max_command_width = width - 104
        max_desc_width = width - 52

        for item in section.get("items", []) or []:
            command_lines = self._wrap_text(str(item.get("command", "")), command_font, max_command_width)
            desc_lines = self._wrap_text(str(item.get("desc", "")), body_font, max_desc_width)

            draw.rounded_rectangle((24, current_y + 6, 34, current_y + 16), radius=5, fill=accent)

            text_y = current_y - 6
            for line in command_lines:
                self._draw_text(draw, line, command_font, fill="#F8FBFF", xy=(48, text_y))
                text_y += 30

            desc_y = text_y + 2
            for line in desc_lines:
                self._draw_text(draw, line, body_font, fill="#B7C5E0", xy=(24, desc_y))
                desc_y += 26

            current_y = desc_y + 18

        canvas.alpha_composite(card, dest=(left, top))

    def _wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        if not text:
            return [""]

        dummy = Image.new("RGB", (10, 10))
        draw = ImageDraw.Draw(dummy)
        lines: list[str] = []
        current = ""

        for char in text:
            candidate = current + char
            bbox = draw.textbbox((0, 0), candidate, font=font)
            if bbox[2] - bbox[0] <= max_width or not current:
                current = candidate
                continue
            lines.append(current.rstrip())
            current = char

        if current:
            lines.append(current.rstrip())
        return lines or [text]

    def _draw_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        fill: str | tuple[int, int, int] | tuple[int, int, int, int],
        xy: tuple[int, int],
    ) -> None:
        draw.text(xy, text, font=font, fill=fill)

    def _load_font(self, size: int) -> ImageFont.FreeTypeFont:
        for font_path in self.FONT_CANDIDATES:
            if Path(font_path).exists():
                try:
                    return ImageFont.truetype(font_path, size=size)
                except Exception:
                    continue
        return ImageFont.load_default()

    def _hex_to_rgba(self, color: str, alpha: int) -> tuple[int, int, int, int]:
        color = color.lstrip("#")
        if len(color) != 6:
            return (124, 92, 255, alpha)
        return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


