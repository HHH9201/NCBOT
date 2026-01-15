# /home/hjh/BOT/NCBOT/common/utils.py
import os
import base64
import string
import logging
import yaml
import re
from typing import Any, Dict

def image_to_base64(image_path: str) -> str:
    """
    将图片文件转换为base64编码字符串
    
    Args:
        image_path: 图片文件的绝对路径
        
    Returns:
        str: base64编码的图片字符串 (带data:image/png;base64前缀)，如果失败返回None
    """
    try:
        if not os.path.exists(image_path):
            logging.warning(f"图片文件不存在: {image_path}")
            return None
        
        with open(image_path, 'rb') as f:
            image_data = f.read()
            base64_encoded = base64.b64encode(image_data).decode('utf-8')
            return f"data:image/png;base64,{base64_encoded}"
    except Exception as e:
        logging.error(f"图片转base64失败: {e}")
        return None

def normalize_text(txt: str) -> str:
    """
    标准化文本：去除标点符号，转小写，规范化空格
    """
    if not txt:
        return ""
    for p in string.punctuation:
        txt = txt.replace(p, " ")
    return " ".join(txt.lower().split())

def convert_roman_to_arabic(text: str) -> str:
    """
    将文本中的罗马数字转换为阿拉伯数字 (1-20)
    """
    roman_to_arabic_map = {
        'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5',
        'VI': '6', 'VII': '7', 'VIII': '8', 'IX': '9', 'X': '10',
        'XI': '11', 'XII': '12', 'XIII': '13', 'XIV': '14', 'XV': '15',
        'XVI': '16', 'XVII': '17', 'XVIII': '18', 'XIX': '19', 'XX': '20'
    }
    # 整词替换，忽略大小写
    for roman, arabic in roman_to_arabic_map.items():
        text = re.sub(rf'\b{roman}\b', arabic, text, flags=re.I)
    return text

def load_yaml(path: str, default: Dict = None) -> Dict:
    """
    安全加载 YAML 文件
    """
    if default is None:
        default = {}
    
    if not os.path.exists(path):
        return default
        
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            return data if data is not None else default
    except Exception as e:
        logging.error(f"加载 YAML 失败 [{path}]: {e}")
        return default

def save_yaml(path: str, data: Any):
    """
    安全保存 YAML 文件
    """
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=True)
    except Exception as e:
        logging.error(f"保存 YAML 失败 [{path}]: {e}")

def clean_filename(filename: str) -> str:
    """
    清理文件名中的非法字符
    """
    return re.sub(r'[\\/*?:"<>|]', "", filename).strip()
