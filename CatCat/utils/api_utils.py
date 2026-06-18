from ncatbot.utils.logger import get_log
import aiohttp
import json
import os

_log = get_log()

# 插件目录的绝对路径（utils 上一级是 CatCat 根目录）
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


async def call_chat_api(api_key, base_url, model, messages, temperature=1.3, max_tokens=256, thinking=False):
    """通用 OpenAI 兼容接口调用
    参数:
        api_key: API 密钥
        base_url: 接口基础地址（如 https://api.deepseek.com 或 https://api.openai.com/v1）
        model: 模型名（如 deepseek-chat / gpt-4o-mini / glm-4-flash）
        messages: 消息列表
        temperature: 温度
        max_tokens: 最大输出 token
        thinking: 是否开启思考模式（DeepSeek V4 系列，默认关闭以加速响应）
    """
    # 拼接 chat completions 端点（兼容 base_url 是否带 /v1）
    url = base_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = url + "/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    data = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    # DeepSeek V4 系列默认开启思考模式会显著增加延迟，聊天场景关闭
    if thinking is False:
        data["thinking"] = {"type": "disabled"}

    try:
        async with aiohttp.ClientSession() as session:
            # 记录请求日志
            log_path = os.path.join(PLUGIN_DIR, "logs", "chat_api", "messages.log")
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
                f.write("\n")
            async with session.post(url, json=data, headers=headers) as response:
                if response.status == 200:
                    result = await response.json()
                    try:
                        return result['choices'][0]['message']['content']
                    except KeyError:
                        raise KeyError(f"提取回复时出错，回复内容：{result}")
                else:
                    error_text = await response.text()
                    _log.error(f"API调用失败：{url} 状态码 {response.status}，响应：{error_text}")
    except aiohttp.ClientError as e:
        _log.error(f"网络请求出错：{str(e)}")
    except Exception as e:
        _log.error(f"未知错误：{str(e)}")
