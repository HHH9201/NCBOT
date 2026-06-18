import os
from pathlib import Path


def _detect_root_dir() -> Path:
    env_root = os.getenv("NCBOT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


ROOT_DIR = _detect_root_dir()
