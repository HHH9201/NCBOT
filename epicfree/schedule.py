# schedule.py - 定时任务配置管理（适配 NcatBot5）
import json
from pathlib import Path
from typing import Dict, Literal, Optional, Union

# 任务调度配置文件
PLUGIN_DIR = Path(__file__).resolve().parent
DATA_DIR = PLUGIN_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
scheduler_file = DATA_DIR / "scheduler.json"


async def scheduler_manage(
    job_id: str,
    action: Literal["get", "set", "delete"] = "get",
    time: Optional[str] = None,
) -> Optional[Union[str, Dict[str, str]]]:
    """
    管理定时任务配置 (cron 表达式)
    action 'get' -> returns str | None
    action 'set' -> returns Dict | None
    action 'delete' -> returns None
    """
    if scheduler_file.exists():
        try:
            sched_data: Dict[str, str] = json.loads(
                scheduler_file.read_text(encoding="UTF-8")
            )
        except Exception:
            sched_data = {}
    else:
        sched_data = {}

    if action == "get":
        return sched_data.get(job_id)
    elif action == "set":
        if not time:
            raise ValueError("设置定时任务时必须提供时间参数 'time'!")
        sched_data[job_id] = time
    elif action == "delete":
        sched_data.pop(job_id, None)

    scheduler_file.write_text(
        json.dumps(sched_data, ensure_ascii=False, indent=2), encoding="UTF-8"
    )
    if action == "set":
        return {"job_id": job_id, "time": time}
    return None
