# NcatBot 插件开发模板

## 📋 模板概述

本模板提供了完整的 NcatBot 插件开发框架，集成了两种消息发送方法：
- **直接消息发送**：使用 NcatBot 原生 API
- **伪造转发消息**：使用 NapCat API

## 🚀 快速开始模板代码

### 基础插件结构

```python
# /home/hjh/BOT/NCBOT/plugins/your_plugin/main.py
import asyncio
from pathlib import Path
import aiohttp
from typing import Dict, List, Optional, Union

from ncatbot import BasePlugin
from ncatbot.bot import Bot
from ncatbot.message import GroupMessage, MessageChain, Text
from ncatbot.api import Api


class YourPluginName(BasePlugin):
    """你的插件描述"""
    name = "YourPluginName"
    version = "1.0.0"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 插件配置
        self.config_file = Path(__file__).with_name("config.yaml")
        self.config: Dict = {}
        
        # 加载配置
        self._load_config()
        
        # NapCat伪造转发消息配置
        self.napcat_url = "http://101.35.164.122:3006/send_group_forward_msg"
        self.napcat_headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer he031701'
        }
    
    def _load_config(self):
        """加载插件配置"""
        default_config = {
            "enabled_groups": ["695934967"],  # 允许的群组ID列表
            "admin_qq": ["123456789"],       # 管理员QQ号列表
            "max_message_length": 500,       # 最大消息长度
            "use_fake_forward": True,        # 是否使用伪造转发
            "fake_forward_threshold": 200    # 触发伪造转发的消息长度阈值
        }
        
        # 这里可以添加配置文件读取逻辑
        self.config = default_config
```

### 消息发送方法模板

```python
# 方法1：直接消息发送 (NcatBot)
async def send_direct_message(self, group_id: int, content: str) -> bool:
    """使用NcatBot直接发送消息"""
    try:
        result = await self.bot.api.post_group_msg(
            group_id=group_id,
            message=MessageChain([Text(content)])
        )
        
        if result and result.get("status") == "ok":
            print(f"[{self.name}] 直接消息发送成功到群 {group_id}")
            return True
        else:
            print(f"[{self.name}] 直接消息发送失败: {result}")
            return False
            
    except Exception as e:
        print(f"[{self.name}] 直接消息发送异常: {e}")
        return False

# 方法2：伪造转发消息 (NapCat)
async def send_fake_forward_message(self, group_id: int, content: str, 
                                   sender_name: str = "系统消息", 
                                   sender_qq: str = "10000") -> bool:
    """使用NapCat伪造转发消息"""
    try:
        messages = [{
            "type": "node",
            "data": {
                "name": sender_name,
                "uin": sender_qq,
                "content": content
            }
        }]
        
        payload = {
            "group_id": group_id,
            "messages": messages
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.napcat_url, 
                headers=self.napcat_headers, 
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                result = await resp.json()
                
                if result.get("status") == "ok":
                    print(f"[{self.name}] 伪造转发消息发送成功到群 {group_id}")
                    return True
                else:
                    print(f"[{self.name}] 伪造转发消息发送失败: {result}")
                    return False
                    
    except asyncio.TimeoutError:
        print(f"[{self.name}] 伪造转发消息发送超时")
        return False
    except Exception as e:
        print(f"[{self.name}] 伪造转发消息发送异常: {e}")
        return False

# 方法3：智能发送（推荐）
async def smart_send_message(self, group_id: int, content: str, 
                            force_method: Optional[str] = None) -> bool:
    """智能消息发送方法：根据内容和配置自动选择发送方式"""
    if force_method == "direct":
        return await self.send_direct_message(group_id, content)
    elif force_method == "fake_forward":
        return await self.send_fake_forward_message(group_id, content)
    
    # 自动选择发送方式
    if len(content) > self.config.get("fake_forward_threshold", 200) and \
       self.config.get("use_fake_forward", True):
        return await self.send_fake_forward_message(group_id, content)
    else:
        return await self.send_direct_message(group_id, content)
```

### 权限检查方法模板

```python
def is_group_allowed(self, group_id: Union[int, str]) -> bool:
    """检查群组是否在允许列表中"""
    allowed_groups = self.config.get("enabled_groups", [])
    return str(group_id) in allowed_groups

def is_admin(self, qq_id: Union[int, str]) -> bool:
    """检查用户是否为管理员"""
    admin_qq = self.config.get("admin_qq", [])
    return str(qq_id) in admin_qq
```

### 事件处理模板

```python
@Bot.group_event
async def on_group_message(self, msg: GroupMessage):
    """群组消息事件处理示例"""
    # 检查群组权限
    if not self.is_group_allowed(msg.group_id):
        return
    
    raw_message = msg.raw_message.strip()
    
    # 示例命令处理
    if raw_message.startswith("命令前缀"):
        content = raw_message[4:].strip()
        
        # 使用智能发送
        await self.smart_send_message(msg.group_id, content)
        
    elif raw_message == "帮助":
        help_text = """🤖 插件帮助信息
        
命令列表：
• 命令前缀 [内容] - 主要功能
• 帮助 - 显示帮助信息"""
        
        await self.smart_send_message(msg.group_id, help_text)
```

### 插件注册模板

```python
# 插件注册
def create_plugin():
    return YourPluginName()
```

### 配置文件模板 (config.yaml)

```yaml
# /home/hjh/BOT/NCBOT/plugins/your_plugin/config.yaml


# 消息发送配置
max_message_length: 500        # 最大消息长度限制
use_fake_forward: true         # 是否启用伪造转发功能
fake_forward_threshold: 200    # 触发伪造转发的消息长度阈值
```

### __init__.py 模板

```python
# /home/hjh/BOT/NCBOT/plugins/your_plugin/__init__.py
"""插件初始化文件"""

from .main import YourPluginName

__all__ = ["YourPluginName"]
```

## ⚠️ 重要注意事项

### 1. 文件结构规范
- 每个插件必须包含 `main.py` 和 `__init__.py`
- 资源文件放在 `tool/` 目录下
- 文件第一行必须包含绝对路径注释
- 禁止创建测试文件和文档文件

### 2. 消息发送选择指南
- **直接消息**：适合短消息（<200字符），快速响应
- **伪造转发**：适合长消息（>200字符），系统通知
- **智能发送**：自动选择，推荐使用

### 3. 错误处理要求
- 所有网络操作必须包含异常处理
- 使用 try-catch 包装 API 调用
- 记录详细的错误日志

### 4. 性能优化建议
- 使用异步编程（async/await）
- 避免阻塞操作
- 合理设置超时时间

### 5. 配置管理规范
- 配置文件使用 YAML 格式
- 提供默认配置值
- 支持运行时配置更新

## 🔧 开发步骤

1. **创建插件目录**：`plugins/your_plugin_name/`
2. **复制模板代码**：根据上述模板创建文件
3. **修改插件信息**：类名、版本号、描述
4. **配置权限**：设置允许的群组和管理员
5. **实现业务逻辑**：在事件处理中添加功能
6. **测试验证**：使用提供的测试命令

## 📝 使用示例

基于此模板，可以快速开发以下类型插件：
- 信息查询插件（天气、股票等）
- 娱乐插件（抽签、游戏等）
- 工具插件（翻译、计算等）
- 管理插件（群管、统计等）

只需关注业务逻辑实现，消息发送和事件处理框架已经完备。