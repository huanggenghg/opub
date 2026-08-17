from __future__ import annotations

import json
import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.resolve()


def _detect_mode() -> Path:
    """SAU_HOME 环境变量始终优先。
    开发模式：项目根有 .git 目录 → BASE_DIR = 项目根
    pip 模式：→ BASE_DIR = ~/.opub/"""
    sau_home = os.environ.get("SAU_HOME", "").strip()
    if sau_home:
        return Path(sau_home).resolve()
    if (_PROJECT_ROOT / ".git").is_dir():
        return _PROJECT_ROOT
    home_dir = Path.home() / ".opub"
    return home_dir


BASE_DIR = _detect_mode()

# 首次运行自动创建数据目录
try:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "cookies").mkdir(exist_ok=True)
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
