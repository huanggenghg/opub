# -*- coding: utf-8 -*-
"""运行时环境预检:patchright 可用性、Chromium 安装、Python 版本"""
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
from importlib import import_module, metadata
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


REPAIR_TIMEOUT_SECONDS = 600


def install_patchright_chromium() -> bool:
    """仅由显式修复流程调用；预检不下载安装浏览器。"""
    env = os.environ.copy()
    if not env.get("PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST") and not env.get("PLAYWRIGHT_DOWNLOAD_HOST"):
        env["PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST"] = "https://cdn.playwright.dev"
    try:
        result = subprocess.run(
            [sys.executable, "-m", "patchright", "install", "chromium"],
            env=env,
            timeout=REPAIR_TIMEOUT_SECONDS,
            stdout=sys.stderr,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def sync_python_dependencies(with_video: bool = False) -> bool:
    """兼容旧调用名：显式重装项目声明的依赖，绝不读取旧 requirements 清单。"""
    project_root = Path(__file__).resolve().parent.parent
    extra = "[video]" if with_video else ""
    if (project_root / "pyproject.toml").is_file():
        target = f"{project_root}{extra}"
    else:
        try:
            installed_version = metadata.version("opub")
        except metadata.PackageNotFoundError:
            return False
        if not installed_version:
            return False
        target = f"opub{extra}=={installed_version}"

    try:
        if importlib.util.find_spec("pip") is None:
            bootstrap = subprocess.run(
                [sys.executable, "-m", "ensurepip", "--upgrade"],
                timeout=REPAIR_TIMEOUT_SECONDS,
                stdout=sys.stderr,
            )
            if bootstrap.returncode != 0:
                return False
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--force-reinstall", "--no-input", target],
            timeout=REPAIR_TIMEOUT_SECONDS,
            stdout=sys.stderr,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def repair_environment(with_video: bool = False) -> bool:
    """用户显式请求时修复 Python 依赖并安装 Chromium。"""
    repair_command = "opub --repair-env" + (" --with-video" if with_video else "")
    if not sync_python_dependencies(with_video=with_video):
        print_error("ENV-003", "Python 依赖修复失败", f'确认 opub 版本信息完整且网络可用；若当前解释器缺少 pip，可运行 uv pip install --python "{sys.executable}" pip，再运行 {repair_command} 重试')
        return False
    if not install_patchright_chromium():
        print_error("ENV-004", "Patchright Chromium 安装失败", f"检查网络或浏览器下载镜像后，运行 {repair_command} 重试")
        return False
    return True


async def runtime_preflight() -> bool:
    """只读检查；常规发布绝不安装或更新 Python 包和浏览器。"""
    print("运行环境预检")

    if sys.version_info < (3, 9):
        print_error("ENV-001", "需要 Python 3.9 或更高版本", f"当前为 {'.'.join(map(str, sys.version_info[:3]))}，请安装 Python 3.9+ 后重试")
        return False

    if not patchright_available():
        print_error("ENV-002", "未安装 patchright", "运行 opub --repair-env 修复当前环境")
        return False

    if not patchright_chromium_installed():
        print_error("ENV-004", "未安装匹配的 Patchright Chromium", "运行 opub --repair-env 修复当前环境")
        return False

    print("Patchright Chromium 已安装")
    return True
