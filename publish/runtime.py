# -*- coding: utf-8 -*-
"""运行时环境预检:patchright 可用性、Chromium 安装、Python 版本"""
import asyncio
import json
import os
import subprocess
import sys
from importlib import import_module
from pathlib import Path

from publish.errors import print_error


def run_async_for_test(coro):
    return asyncio.run(coro)


def patchright_available() -> bool:
    try:
        import_module("patchright")
        return True
    except ImportError:
        return False


def playwright_browser_cache_dirs() -> list:
    cache_dirs = []
    playwright_browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if playwright_browsers_path:
        cache_dirs.append(Path(playwright_browsers_path).expanduser())
    cache_dirs.extend(
        [
            Path.home() / "Library" / "Caches" / "ms-playwright",
            Path.home() / "AppData" / "Local" / "ms-playwright",
            Path.home() / ".cache" / "ms-playwright",
        ]
    )
    return cache_dirs


def patchright_chromium_installed() -> bool:
    try:
        import patchright
    except ImportError:
        return False

    package_file = getattr(patchright, "__file__", None)
    if not package_file:
        return False

    browsers_file = Path(package_file).resolve().parent / "driver" / "package" / "browsers.json"
    if not browsers_file.exists():
        return False

    try:
        with open(browsers_file, "r", encoding="utf-8") as f:
            browsers_data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False

    revision = None
    for browser in browsers_data.get("browsers", []):
        if browser.get("name") == "chromium" and browser.get("installByDefault", True):
            revision = browser.get("revision")
            break

    if not revision:
        return False

    browser_dir_name = f"chromium-{revision}"
    return any((cache_dir / browser_dir_name).exists() for cache_dir in playwright_browser_cache_dirs())


def install_patchright_chromium() -> bool:
    env = os.environ.copy()
    if not env.get("PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST") and not env.get("PLAYWRIGHT_DOWNLOAD_HOST"):
        env["PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST"] = "https://cdn.playwright.dev"
    result = subprocess.run(
        [sys.executable, "-m", "patchright", "install", "chromium"],
        env=env,
    )
    return result.returncode == 0


def sync_python_dependencies() -> bool:
    """同步 requirements.txt 里的 python 依赖。已装且版本匹配的包会跳过,缺失/版本不符的会装。"""
    req_path = Path(__file__).resolve().parent.parent / "requirements.txt"
    if not req_path.exists():
        return True

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(req_path), "--quiet"],
        cwd=str(req_path.parent),
    )
    return result.returncode == 0


async def runtime_preflight() -> bool:
    print("运行环境预检")

    if sys.version_info < (3, 9):
        print_error("ENV-001", "需要 Python 3.9 或更高版本", f"当前为 {'.'.join(map(str, sys.version_info[:3]))}，请安装 Python 3.9+ 后重试")
        return False

    if not patchright_available():
        print_error("ENV-002", "未安装 patchright", "运行 pip install opub --upgrade 重新安装")
        return False

    if not sync_python_dependencies():
        print_error("ENV-003", "Python 依赖同步失败", "运行 pip install -r requirements.txt 后重试")
        return False
    print("Python 依赖已同步")

    if patchright_chromium_installed():
        print("Patchright Chromium 已安装")
        return True

    print("Patchright Chromium 未安装，正在安装...")
    if install_patchright_chromium():
        print("Patchright Chromium 安装成功")
        return True

    print_error(
        "ENV-004",
        "Patchright Chromium 安装失败",
        '运行 PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST="https://cdn.playwright.dev" patchright install chromium',
    )
    return False
