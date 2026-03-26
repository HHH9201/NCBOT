# /home/hjh/BOT/NCBOT/plugins/xydj/tool/utils.py
# -*- coding: utf-8 -*-
"""
工具函数模块
"""
import re
import os
from pathlib import Path
from typing import Tuple, List, Dict
from common import image_to_base64, GLOBAL_CONFIG

TOOL_DIR = Path(__file__).parent
QQ_IMG = str(TOOL_DIR / GLOBAL_CONFIG.get('images', {}).get('qq_img', "xcx.jpg"))

def _is_mainly_english(text: str) -> bool:
    return len(re.findall(r'[a-zA-Z]', text)) > len(re.findall(r'[\u4e00-\u9fff]', text))

def extract_english_name(title: str) -> tuple[str, str]:
    """从标题中提取英文名和中文展示名"""
    segments = title.split('|')
    
    english_part = ""
    for segment in reversed(segments):
        segment = segment.strip()
        if _is_mainly_english(segment):
            english_part = segment
            break
    
    if not english_part:
        english_part = segments[-1] if segments else title
    
    chinese_display_parts = []
    for segment in segments:
        segment = segment.strip()
        if _is_mainly_english(segment):
            break
        chinese_display_parts.append(segment)
    
    if not chinese_display_parts:
        chinese_display_parts = [segments[0]] if segments else [title]
    
    chinese_display = ' | '.join(chinese_display_parts)
    
    english_part = re.sub(r'\([^)]*\)', '', english_part)
    english_part = re.sub(r'\[[^\]]*\]', '', english_part)
    english_part = english_part.split('/')[0]
    english_part = re.sub(r'[^\w\s]', ' ', english_part)
    english_part = re.sub(r'\s+', ' ', english_part).strip()
    
    words = english_part.split()
    if len(words) > 4:
        english_part = ' '.join(words[:4])
    
    return english_part.strip(), chinese_display.strip()

def format_game_list(games: List[Dict]) -> str:
    """格式化游戏列表为文本"""
    text_lines = []
    for idx, g in enumerate(games):
        title_parts = g['title'].split('|')
        game_name_extracted = title_parts[0].strip()
        
        key_info = []
        for part in title_parts[1:]:
            part = part.strip()
            if any(keyword in part.lower() for keyword in ['v', '版', 'dlc', '中文', '手柄', '更新', '年度版']):
                key_info.append(part)
        
        display_text = f"{idx+1}. {game_name_extracted}"
        if key_info:
            display_text += f" | {' | '.join(key_info[:3])}"
        
        text_lines.append(display_text)
    
    return "\n".join(text_lines)

def build_forward_nodes(单机_lines: list, 联机_lines: list, user_id: str, user_nickname: str) -> list:
    """构建转发消息节点"""
    from common import napcat_service
    
    nodes = []
    
    # 赞助节点
    sponsor_msgs = [{"type": "text", "data": {"text": "帮我微信登录一下，退出即可，谢谢谢谢谢！"}}]
    qq_img_base64 = image_to_base64(QQ_IMG)
    if qq_img_base64:
        sponsor_msgs.append({"type": "image", "data": {"file": qq_img_base64}})
    
    nodes.append(napcat_service.construct_node(user_id, user_nickname, sponsor_msgs))
    
    # 单机版节点
    单机_msgs = [{"type": "text", "data": {"text": line}} for line in 单机_lines]
    nodes.append(napcat_service.construct_node(user_id, user_nickname, 单机_msgs))
    
    # 联机版节点
    if 联机_lines:
        联机_msgs = []
        for line in 联机_lines:
            if "备用图片：" in line:
                try:
                    parts = line.split("备用图片：")
                    if len(parts) > 1:
                        image_path = parts[1].strip()
                        if os.path.exists(image_path):
                            img_base64 = image_to_base64(image_path)
                            if img_base64:
                                联机_msgs.append({"type": "image", "data": {"file": img_base64}})
                                continue
                except Exception as e:
                    print(f"图片处理异常: {e}")
            
            联机_msgs.append({"type": "text", "data": {"text": line}})
        
        nodes.append(napcat_service.construct_node(user_id, user_nickname, 联机_msgs))
    
    return nodes

def get_game_title(单机_lines: list, 联机_lines: list) -> str:
    """从内容中提取游戏标题"""
    for line in 单机_lines:
        if "游戏名字：" in line:
            return line.split("游戏名字：")[1].strip()
    for line in 联机_lines:
        if "游戏名字：" in line:
            return line.split("游戏名字：")[1].strip()
    return "游戏资源"

def build_summary(单机_lines: list, 联机_lines: list) -> str:
    """构建资源统计摘要"""
    single_count = len([line for line in 单机_lines if "链接" in line])
    multi_count = len([line for line in 联机_lines if "种子链接" in line])
    total_count = single_count + multi_count
    
    summary = f"共找到 {total_count} 个资源链接"
    if single_count > 0:
        summary += f" (单机: {single_count} 个)"
    if multi_count > 0:
        summary += f" (联机: {multi_count} 个)"
    
    return summary
