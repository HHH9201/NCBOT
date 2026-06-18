from ..utils.api_utils import call_chat_api


def format_group_chat(messages):
    """
    将原始群聊记录转换为 API 接受的格式
    输入示例：
        [
            166658.6419105 manager(10101): init catcat
            166658.6430702 何山(7894652): @猫猫 你是谁,
        ]
    """
    formatted_messages = ""
    for message in messages:
        formatted_messages += f"{' '.join(message.split()[1:])}\n"
    return [{"role": "user", "content": formatted_messages}]


async def cat_cat_response(llm_config, chat_history, prompt):
    """
    参数：
        llm_config: dict，包含 api_key / base_url / model / temperature / max_tokens
        chat_history: 群聊记录
        prompt: 助理 prompt
    """
    try:
        messages = [
            {"role": "system", "content": prompt},
            *format_group_chat(chat_history),
            {"role": "user", "content": "请直接回复上面群聊中最后一条消息（只输出回复正文，不要解释、不要复述问题）："},
        ]

        response = await call_chat_api(
            api_key=llm_config.get("api_key", ""),
            base_url=llm_config.get("base_url", "https://api.deepseek.com"),
            model=llm_config.get("model", "deepseek-chat"),
            messages=messages,
            temperature=llm_config.get("temperature", 1.3),
            max_tokens=llm_config.get("max_tokens", 256),
            thinking=llm_config.get("thinking", False),
        )
        return response.strip('"') if response else ""
    except Exception as e:
        print(f"CatCat响应生成错误: {str(e)}")
