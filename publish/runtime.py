# -*- coding: utf-8 -*-
"""运行时环境预检:patchright 可用性、Chromium 安装、Python 版本"""
import asyncio
import json
import os
import subprocess
import sys
from importlib import import_module
from pathlib import Path


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
        print("运行环境检查失败: 需要 Python 3.9 或更高版本", file=sys.stderr)
        return False

    if not patchright_available():
        print("运行环境检查失败: 未安装 patchright", file=sys.stderr)
        return False

    if not sync_python_dependencies():
        print("运行环境检查失败: 依赖同步失败,请手动运行 pip install -r requirements.txt", file=sys.stderr)
        return False
    print("Python 依赖已同步")

    if patchright_chromium_installed():
        print("Patchright Chromium 已安装")
        return True

    print("Patchright Chromium 未安装，正在安装...")
    if install_patchright_chromium():
        print("Patchright Chromium 安装成功")
        return True

    print("运行环境检查失败: Patchright Chromium 安装失败", file=sys.stderr)
    return False
