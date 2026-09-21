from __future__ import annotations

import json
from pathlib import Path
from utils.fs import ensure_dir


def _detect_mode() -> Path:
    """所有 Agent 固定共享当前系统用户的 ~/.opub 数据目录。"""
    return (Path.home() / ".opub").resolve()


BASE_DIR = _detect_mode()

# 首次运行自动创建数据目录
try:
    ensure_dir(BASE_DIR)
    ensure_dir((BASE_DIR / "cookies"))
except OSError:
    pass  # 权限不足时静默忽略，后续操作会报具体错误


def _load_config() -> dict:
    config_path = BASE_DIR / "config.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass  # 配置文件损坏时使用默认值
    return {}


_config = _load_config()

LOCAL_CHROME_HEADLESS = _config.get("chrome_headless", False)
LOCAL_CHROME_PATH = _config.get("chrome_path", "")
DEBUG_MODE = _config.get("debug", False)
ZHIPU_API_KEY = _config.get("zhipu_api_key", "")
ZHIPU_VISION_MODEL = _config.get("zhipu_vision_model", "glm-4v-plus")
