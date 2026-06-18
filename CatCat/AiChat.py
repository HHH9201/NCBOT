from ncatbot.utils.logger import get_log

import time
import os
import aiofiles

from .responses.CatCatRes import cat_cat_response

_log = get_log()

# 插件目录的绝对路径
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))


async def _read_history(history_file, max_lines):
    """读取历史记录，返回 (所有行, 最后一条时间戳)。文件不存在则初始化。"""
    try:
        async with aiofiles.open(history_file, "r", encoding="utf-8") as f:
            lines = await f.readlines()
    except FileNotFoundError:
        os.makedirs(os.path.dirname(history_file), exist_ok=True)
        async with aiofiles.open(history_file, "w", encoding="utf-8") as f:
            await f.write(f"{time.time()} manager(10101): init catcat\n")
        return [], 0.0

    last_time = 0.0
    if lines:
        try:
            last_time = float(lines[-1].split(maxsplit=1)[0])
        except (ValueError, IndexError):
            last_time = 0.0
    return lines, last_time


async def _append_history(history_file, text, max_lines):
    """追加一行到历史记录，超过 max_lines 自动截断保留最新部分。"""
    async with aiofiles.open(history_file, "a", encoding="utf-8") as f:
        await f.write(f"{text}\n")

    # 截断：仅在追加后行数翻倍于上限时执行，避免每次都读写
    try:
        async with aiofiles.open(history_file, "r", encoding="utf-8") as f:
            lines = await f.readlines()
        if len(lines) > max_lines * 2:
            keep = lines[-max_lines:]
            async with aiofiles.open(history_file, "w", encoding="utf-8") as f:
                await f.writelines(keep)
    except Exception as e:
        _log.warning(f"截断历史文件失败: {e}")


async def gene_response(llm_config, msg, cat_prompt, bot_id=""):
    """生成 AI 回复
    参数:
        llm_config: dict，含 api_key/base_url/model/temperature/max_tokens/thinking/cooldown/max_history_lines
        msg: GroupMessageEvent
        cat_prompt: 猫娘 prompt
        bot_id: 机器人 QQ 号
    """
    cooldown = llm_config.get("cooldown", 10)
    reply_cooldown = llm_config.get("reply_cooldown", 120)
    reply_probability = llm_config.get("reply_probability", 0.3)
    max_lines = llm_config.get("max_history_lines", 200)
    history_file = os.path.join(PLUGIN_DIR, "logs", f"{msg.group_id}_history.log")

    lines, last_group_message_time = await _read_history(history_file, max_lines)

    # 读取上次回复时间（从独立文件，重启后仍生效）
    last_reply_file = os.path.join(PLUGIN_DIR, "logs", f"{msg.group_id}_last_reply.txt")
    last_reply_time = 0.0
    try:
        async with aiofiles.open(last_reply_file, "r") as f:
            last_reply_time = float((await f.read()).strip() or 0)
    except (FileNotFoundError, ValueError):
        pass

    force_reply = False
    # 直接用 raw_message 作为内容，避免消息段解析兼容性问题
    raw = msg.raw_message or ""
    # 过滤纯 CQ 码消息（表情/图片/戳一戳等），不回复也不记录
    import re
    text_only = re.sub(r"\[CQ:[^\]]+\]", "", raw).strip()
    if not text_only:
        # 纯表情/图片等，不处理
        return
    text_content = text_only
    # 判断是否 @ 了机器人（兼容 CQ 码和纯文本两种格式）
    if str(bot_id) and (f"[CQ:at,qq={bot_id}]" in raw or f"@{bot_id}" in raw):
        force_reply = True

    # 引用回复且未 @ 猫猫，视为对特定消息的针对性回应（如审批指令），不介入
    if not force_reply and "[CQ:reply" in raw:
        return

    text_content = f"{msg.sender.nickname}({msg.sender.user_id}): {text_content}"

    # 追加消息到历史记录（真实时间戳）
    current_time = time.time()
    current_line = f"{current_time} {text_content}\n"
    await _append_history(history_file, current_line.rstrip("\n"), max_lines)
    # 同步加入内存列表，确保传给 AI 的历史包含当前消息
    lines.append(current_line)

    # 防刷屏：消息间隔小于冷却秒数且非 @触发 不回复
    if current_time - last_group_message_time < cooldown and not force_reply:
        return

    # 回复后冷却：猫猫回复一次后，此时间内不再自动回复（@触发不受此限）
    if not force_reply and current_time - last_reply_time < reply_cooldown:
        return

    # 非 @触发时，按概率随机决定是否回复
    import random
    if not force_reply and random.random() > reply_probability:
        return

    _log.info("开始生成回复……")

    # 读取最近 max_lines 条历史（用 maxsplit=2 保留完整内容）
    recent_lines = lines[-max_lines:] if lines else []
    result = []
    for line in reversed(recent_lines):
        if len(result) >= 10:
            break
        parts = line.strip().split(maxsplit=2)
        if len(parts) < 3:
            continue
        # 用完整内容做去重 key（而非第一个词）
        content_key = parts[2]
        if not any(content_key in r for r in result):
            result.append(line)
    chat_history = reversed(result)

    response = await cat_cat_response(llm_config, chat_history, cat_prompt)
    if not response:
        return

    # 追加回复到历史记录（换行转义为 \\ 便于单行存储）
    escaped = response.replace("\n", "\\")
    await _append_history(history_file, f"{time.time()} 猫猫({bot_id}): {escaped}", max_lines)

    # 记录本次回复时间（用于回复后冷却判断）
    try:
        async with aiofiles.open(last_reply_file, "w") as f:
            await f.write(str(time.time()))
    except Exception as e:
        _log.warning(f"写入回复时间失败: {e}")

    _log.info(f"猫猫：{response}")
    # 去掉结尾的句号（中英文）
    return response.rstrip("。.")
