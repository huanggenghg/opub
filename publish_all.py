# -*- coding: utf-8 -*-
"""
多平台统一发布脚本
一次配置，发布到多个平台
"""
import asyncio
import configparser
import json
import os
import random
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, Optional

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

from conf import BASE_DIR

# 内容模板文件路径
CONTENT_TEMPLATES_FILE = Path(__file__).resolve().parent / "templates" / "content_templates.json"

# 平台名称映射
PLATFORM_NAMES = {
    "douyin": "抖音",
    "xiaohongshu": "小红书",
    "kuaishou": "快手",
    "bilibili": "B站",
    "tencent": "微信视频号",
    "baijiahao": "百家号",
    "tk": "TikTok",
    "weibo": "微博",
}

# 平台标题长度限制
TITLE_LIMITS = {
    "douyin": 30,
    "xiaohongshu": 20,
    "kuaishou": 30,
    "bilibili": 80,
    "tencent": 30,
    "baijiahao": 30,
    "tk": 150,
    "weibo": 2000,
}


@dataclass
class PublishOverrides:
    platforms: Optional[str] = None
    video: Optional[str] = None
    title: Optional[str] = None
    desc: Optional[str] = None
    tags: Optional[str] = None
    schedule: Optional[datetime] = None
    start_from: Optional[int] = None
    force: bool = False


def load_content_templates() -> list:
    """加载内容模板"""
    if CONTENT_TEMPLATES_FILE.exists():
        with open(CONTENT_TEMPLATES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("templates", [])
    return []


def fill_empty_content(title: str, desc: str) -> tuple:
    """如果标题或描述为空，从模板随机填充"""
    title_empty = not title or not title.strip()
    desc_empty = not desc or not desc.strip()

    if title_empty or desc_empty:
        templates = load_content_templates()
        if templates:
            random_template = random.choice(templates)
            if title_empty:
                title = random_template.get("title", "")
            if desc_empty:
                desc = random_template.get("desc", "")
            print(f"[AUTO] 标题/描述为空，已自动填充: {title}")

    return title, desc


def get_video_content(
    video_file: str,
    default_title: str,
    default_desc: str,
    auto_generate: bool = True,
    force: bool = False,
) -> tuple:
    """
    获取视频的标题和描述

    优先级：
    1. 视频同名的 JSON 配置文件（最高优先）
    2. 自动生成配置（如果启用且无配置文件）
    3. 模板随机填充
    4. 配置文件默认值

    Args:
        video_file: 视频文件路径
        default_title: 默认标题（来自 publish_config.ini）
        default_desc: 默认描述（来自 publish_config.ini）
        auto_generate: 是否自动生成配置（默认 True）
        force: 是否强制重新生成，忽略已有同名配置

    Returns:
        (title, desc) 元组
    """
    from utils.video_analyzer import load_video_config, config_exists

    # 1. 最高优先：视频同名 JSON 配置文件
    config = load_video_config(video_file)
    if config and not force:
        title = config.get("title", "")
        desc = config.get("desc", "")
        if title or desc:
            print(f"[AUTO] 使用视频配置文件: {os.path.basename(video_file).rsplit('.', 1)[0]}.json")
            return title, desc

    # 2. 自动生成配置（如果启用且无配置文件）
    if auto_generate and (force or not config_exists(video_file)):
        print(f"[AUTO] 视频无配置文件，正在自动生成...")
        try:
            from utils.video_analyzer import (
                analyze_frames_with_glm4v,
                extract_frames,
                save_video_config,
                get_frame_files,
                cleanup_frames_dir,
            )

            # 提取帧
            frames_dir = extract_frames(video_file, num_frames=3)
            frame_files = get_frame_files(frames_dir)

            if frame_files:
                # 调用 GLM-4V 分析
                video_name = os.path.basename(video_file)
                title, desc = analyze_frames_with_glm4v(frame_files, video_name)

                # 保存配置文件
                save_video_config(video_file, title, desc)
                print(f"[AUTO] 配置已生成: {title}")

                # 清理临时文件
                cleanup_frames_dir(frames_dir)

                return title, desc
            else:
                print(f"[AUTO] 帧提取失败，使用模板填充")

            # 清理临时文件
            cleanup_frames_dir(frames_dir)

        except Exception as e:
            print(f"[AUTO] 自动生成失败: {e}，使用模板填充")

    # 3. 次优先：模板随机填充
    templates = load_content_templates()
    if templates:
        random_template = random.choice(templates)
        title = random_template.get("title", "")
        desc = random_template.get("desc", "")
        print(f"[AUTO] 使用模板填充标题和描述: {title}")
        return title, desc

    # 4. 最低优先：配置文件默认值
    return default_title, default_desc


def read_config(config_file: str = "publish_config.ini") -> dict:
    """读取配置文件"""
    config_path = Path(config_file)
    if not config_path.is_absolute():
        config_path = BASE_DIR / config_path
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    parser = configparser.ConfigParser()
    parser.read(config_path, encoding="utf-8")

    config = {
        "common": dict(parser["common"]),
        "platforms": dict(parser["platforms"]),
    }
    return config


def _split_csv(value: Optional[str]) -> list:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _discover_account_files() -> Dict[str, str]:
    cookies_dir = BASE_DIR / "cookies"
    platform_prefixes = {
        "douyin": "douyin_",
        "kuaishou": "kuaishou_",
        "xiaohongshu": "xiaohongshu_",
        "weibo": "weibo_",
        "tencent": "tencent_",
        "baijiahao": "baijiahao_",
        "tk": "tk_",
    }
    platform_subdirs = {
        "douyin": "douyin_uploader",
        "kuaishou": "ks_uploader",
        "xiaohongshu": "xiaohongshu_uploader",
        "weibo": "weibo_uploader",
        "tencent": "tencent_uploader",
        "baijiahao": "baijiahao_uploader",
        "tk": "tk_uploader",
    }

    platforms = {}
    for platform, prefix in platform_prefixes.items():
        flat_files = sorted(cookies_dir.glob(f"{prefix}*.json"))
        subdir = platform_subdirs[platform]
        subdir_files = sorted((cookies_dir / subdir).glob("*.json")) if (cookies_dir / subdir).exists() else []
        account_files = flat_files + [file for file in subdir_files if file not in flat_files]
        if account_files:
            rel_paths = [str(file.relative_to(BASE_DIR)) for file in account_files]
            platforms[f"{platform}_account"] = ", ".join(rel_paths)
    return platforms


def default_params_from_overrides() -> Dict[str, Any]:
    return {
        "content_type": "video",
        "title": "",
        "desc": "",
        "tags": [],
        "video_file": "",
        "images": [],
        "publish_strategy": "immediate",
        "publish_time": None,
        "enabled_platforms": [],
        "platforms": _discover_account_files(),
        "convert_to_video": False,
        "video_duration": 5,
        "start_from": 1,
    }


def apply_overrides(params: Dict[str, Any], overrides: Optional[PublishOverrides]) -> Dict[str, Any]:
    merged = dict(params)
    if overrides is None:
        return merged

    if overrides.platforms is not None:
        merged["enabled_platforms"] = _split_csv(overrides.platforms)
    if overrides.video is not None:
        merged["video_file"] = overrides.video
    if overrides.title is not None:
        merged["title"] = overrides.title
    if overrides.desc is not None:
        merged["desc"] = overrides.desc
    if overrides.tags is not None:
        merged["tags"] = _split_csv(overrides.tags)
    if overrides.schedule is not None:
        merged["publish_strategy"] = "scheduled"
        merged["publish_time"] = overrides.schedule
    if overrides.start_from is not None:
        merged["start_from"] = overrides.start_from
    if overrides.force:
        merged["force"] = True

    return merged


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


async def runtime_preflight() -> bool:
    print("运行环境预检")

    if sys.version_info < (3, 9):
        print("运行环境检查失败: 需要 Python 3.9 或更高版本", file=sys.stderr)
        return False

    if not patchright_available():
        print("运行环境检查失败: 未安装 patchright", file=sys.stderr)
        return False

    if patchright_chromium_installed():
        print("Patchright Chromium 已安装")
        return True

    print("Patchright Chromium 未安装，正在安装...")
    if install_patchright_chromium():
        print("Patchright Chromium 安装成功")
        return True

    print("运行环境检查失败: Patchright Chromium 安装失败", file=sys.stderr)
    return False


def parse_config(config: dict) -> dict:
    """解析配置，处理字段格式"""
    common = config["common"]
    platforms = config["platforms"]

    # 解析启用平台
    enabled_platforms = [p.strip() for p in platforms.get("enabled", "").split(",") if p.strip()]

    # 解析标签
    tags = [t.strip() for t in common.get("tags", "").split(",") if t.strip()]

    # 解析图片路径
    images_str = common.get("images", "")
    images = [img.strip() for img in images_str.split(",") if img.strip()]

    # 解析发布时间
    publish_strategy = common.get("publish_strategy", "immediate")
    publish_time_str = common.get("publish_time", "").strip()
    publish_time = None
    if publish_strategy == "scheduled" and publish_time_str:
        try:
            publish_time = datetime.strptime(publish_time_str, "%Y-%m-%d %H:%M")
        except ValueError:
            print(f"⚠️ 发布时间格式错误: {publish_time_str}，将使用立即发布")
            publish_strategy = "immediate"

    # 解析描述内容，支持 \n 换行
    desc = common.get("desc", "").replace("\\n", "\n")

    # 解析标题
    title = common.get("title", "")

    # 注意：标题/描述为空时，在视频处理流程中由 get_video_content() 统一处理
    # 不在此处填充，支持自动生成配置功能

    # 解析图文转视频配置
    convert_to_video = common.get("convert_to_video", "false").strip().lower() in ("true", "yes", "1")
    video_duration = float(common.get("video_duration", "5").strip() or 5)

    # 解析起始视频序号（用于断点续传）
    start_from = int(common.get("start_from", "1").strip() or 1)

    return {
        "content_type": common.get("content_type", "video"),
        "title": title,
        "desc": desc,
        "tags": tags,
        "video_file": common.get("video_file", ""),
        "images": images,
        "publish_strategy": publish_strategy,
        "publish_time": publish_time,
        "enabled_platforms": enabled_platforms,
        "platforms": platforms,
        "convert_to_video": convert_to_video,
        "video_duration": video_duration,
        "start_from": start_from,
    }


def get_video_files(video_path: str) -> list:
    """获取视频文件列表，支持文件夹或单个文件"""
    if not video_path:
        return []

    path = resolve_path(video_path)

    if os.path.isfile(path):
        # 单个文件
        return [path]

    if os.path.isdir(path):
        # 文件夹，获取所有视频文件
        video_extensions = ['.mp4', '.mov', '.mkv', '.avi', '.flv', '.mpeg', '.ogg', '.vob', '.webm', '.wmv', '.rmvb']
        video_files = []
        for file in os.listdir(path):
            file_lower = file.lower()
            if any(file_lower.endswith(ext) for ext in video_extensions):
                video_files.append(os.path.join(path, file))
        # 按文件名排序
        video_files.sort()
        return video_files

    return []


def truncate_title(title: str, platform: str) -> str:
    """根据平台限制截断标题"""
    limit = TITLE_LIMITS.get(platform, 50)
    if len(title) > limit:
        return title[:limit]
    return title


def resolve_path(file_path: str) -> str:
    """解析相对路径为绝对路径"""
    if not file_path:
        return ""
    path = Path(file_path)
    if path.is_absolute():
        return str(path)
    return str(BASE_DIR / file_path)


async def ensure_login(platform: str, account_file: str) -> bool:
    """确保平台已登录，未登录则触发登录流程"""
    account_file = resolve_path(account_file)

    # 文件不存在，直接触发登录
    if not os.path.exists(account_file):
        pass
    else:
        # 文件存在，先检查 cookie 是否有效
        check_map = {
            "douyin": ("uploader.douyin_uploader.main", "cookie_auth"),
            "xiaohongshu": ("uploader.xiaohongshu_uploader.main", "cookie_auth"),
            "kuaishou": ("uploader.ks_uploader.main", "cookie_auth"),
            "weibo": ("uploader.weibo_uploader.main", "cookie_auth"),
            "tencent": ("uploader.tencent_uploader.main", "cookie_auth"),
            "baijiahao": ("uploader.baijiahao_uploader.main", "cookie_auth"),
            "tk": ("uploader.tk_uploader.main", "cookie_auth"),
        }

        check_entry = check_map.get(platform)
        if check_entry:
            import importlib
            module_path, func_name = check_entry
            module = importlib.import_module(module_path)
            check_func = getattr(module, func_name)
            if await check_func(account_file):
                return True

    # cookie 无效，触发登录（保留原有的 setup 调用逻辑）
    if platform == "douyin":
        from uploader.douyin_uploader.main import douyin_setup
        return await douyin_setup(account_file, handle=True)
    elif platform == "xiaohongshu":
        from uploader.xiaohongshu_uploader.main import xiaohongshu_setup
        return await xiaohongshu_setup(account_file, handle=True)
    elif platform == "kuaishou":
        from uploader.ks_uploader.main import ks_setup
        return await ks_setup(account_file, handle=True)
    elif platform == "tencent":
        from uploader.tencent_uploader.main import tencent_setup
        return await tencent_setup(account_file, handle=True)
    elif platform == "baijiahao":
        from uploader.baijiahao_uploader.main import baijiahao_setup
        return await baijiahao_setup(account_file, handle=True)
    elif platform == "weibo":
        from uploader.weibo_uploader.main import weibo_setup
        return await weibo_setup(account_file, handle=True)
    else:
        return False


async def ensure_account_login(platform: str, account_file: str) -> bool:
    resolved_account = resolve_path(account_file)
    return await ensure_login(platform, resolved_account)


def platform_requires_account_login(platform: str) -> bool:
    return platform not in {"bilibili", "tk"}


async def publish_to_douyin(params: dict) -> dict:
    """发布到抖音"""
    from uploader.douyin_uploader.main import DouYinVideo, DouYinNote

    account_file = resolve_path(params["account_file"])

    title = truncate_title(params["title"], "douyin")
    tags = params["tags"]
    publish_strategy = params["publish_strategy"]
    publish_time = params["publish_time"]
    content_type = params["content_type"]

    try:
        if content_type == "video":
            video_file = resolve_path(params["video_file"])
            if not video_file or not os.path.exists(video_file):
                return {"success": False, "message": f"视频文件不存在: {video_file}"}

            uploader = DouYinVideo(
                title=title,
                file_path=video_file,
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
                desc=params["desc"],
                publish_strategy=publish_strategy,
            )
            await uploader.main()
            return {"success": True, "message": "发布成功"}
        else:
            images = params["images"]
            if not images:
                return {"success": False, "message": "图文模式需要提供图片"}

            image_paths = [resolve_path(img) for img in images]
            for img_path in image_paths:
                if not os.path.exists(img_path):
                    return {"success": False, "message": f"图片文件不存在: {img_path}"}

            uploader = DouYinNote(
                image_paths=image_paths,
                note=params["desc"],
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
                title=title,
                publish_strategy=publish_strategy,
            )
            await uploader.douyin_upload_note()
            return {"success": True, "message": "发布成功"}
    except Exception as e:
        return {"success": False, "message": str(e)}


async def publish_to_xiaohongshu(params: dict) -> dict:
    """发布到小红书"""
    from uploader.xiaohongshu_uploader.main import XiaoHongShuVideo, XiaoHongShuNote

    account_file = resolve_path(params["account_file"])

    title = truncate_title(params["title"], "xiaohongshu")
    tags = params["tags"]
    publish_strategy = params["publish_strategy"]
    publish_time = params["publish_time"]
    content_type = params["content_type"]

    try:
        if content_type == "video":
            video_file = resolve_path(params["video_file"])
            if not video_file or not os.path.exists(video_file):
                return {"success": False, "message": f"视频文件不存在: {video_file}"}

            uploader = XiaoHongShuVideo(
                title=title,
                file_path=video_file,
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
                desc=params["desc"],
                publish_strategy=publish_strategy,
            )
        else:
            images = params["images"]
            if not images:
                return {"success": False, "message": "图文模式需要提供图片"}

            image_paths = [resolve_path(img) for img in images]
            for img_path in image_paths:
                if not os.path.exists(img_path):
                    return {"success": False, "message": f"图片文件不存在: {img_path}"}

            uploader = XiaoHongShuNote(
                image_paths=image_paths,
                note=params["desc"],
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
                title=title,
                desc=params["desc"],
                publish_strategy=publish_strategy,
            )

        result = await uploader.main()
        share_link = result.get("share_link", "") if result else ""
        note_id = result.get("note_id", "") if result else ""

        response = {"success": True, "message": "发布成功"}
        if share_link:
            response["share_link"] = share_link
        if note_id:
            response["note_id"] = note_id

        return response
    except Exception as e:
        return {"success": False, "message": str(e)}


async def publish_to_kuaishou(params: dict) -> dict:
    """发布到快手"""
    from uploader.ks_uploader.main import KSVideo, KSNote

    account_file = resolve_path(params["account_file"])

    title = truncate_title(params["title"], "kuaishou")
    tags = params["tags"]
    publish_strategy = params["publish_strategy"]
    publish_time = params["publish_time"]
    content_type = params["content_type"]

    try:
        if content_type == "video":
            video_file = resolve_path(params["video_file"])
            if not video_file or not os.path.exists(video_file):
                return {"success": False, "message": f"视频文件不存在: {video_file}"}

            uploader = KSVideo(
                title=title,
                file_path=video_file,
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
                desc=params["desc"],
                publish_strategy=publish_strategy,
            )
        else:
            images = params["images"]
            if not images:
                return {"success": False, "message": "图文模式需要提供图片"}

            image_paths = [resolve_path(img) for img in images]
            for img_path in image_paths:
                if not os.path.exists(img_path):
                    return {"success": False, "message": f"图片文件不存在: {img_path}"}

            uploader = KSNote(
                image_paths=image_paths,
                note=params["desc"],
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
                title=title,
                publish_strategy=publish_strategy,
            )

        result = await uploader.main()
        share_link = result.get("share_link", "") if result else ""
        video_id = result.get("video_id", "") if result else ""

        response = {"success": True, "message": "发布成功"}
        if share_link:
            response["share_link"] = share_link
        if video_id:
            response["video_id"] = video_id

        return response
    except Exception as e:
        return {"success": False, "message": str(e)}


async def publish_to_tencent(params: dict) -> dict:
    """发布到微信视频号"""
    from uploader.tencent_uploader.main import TencentVideo

    account_file = resolve_path(params["account_file"])

    title = truncate_title(params["title"], "tencent")
    tags = params["tags"]
    publish_strategy = params["publish_strategy"]
    publish_time = params["publish_time"]
    content_type = params["content_type"]

    try:
        if content_type == "video":
            video_file = resolve_path(params["video_file"])
            if not video_file or not os.path.exists(video_file):
                return {"success": False, "message": f"视频文件不存在: {video_file}"}

            uploader = TencentVideo(
                title=title,
                file_path=video_file,
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
                desc=params["desc"],
                publish_strategy=publish_strategy,
            )
        else:
            return {"success": False, "message": "微信视频号不支持图文发布，请使用 convert_to_video=true 转为视频发布"}

        await uploader.main()
        return {"success": True, "message": "发布成功"}
    except Exception as e:
        return {"success": False, "message": str(e)}


async def publish_to_baijiahao(params: dict) -> dict:
    """发布到百家号"""
    from uploader.baijiahao_uploader.main import BaiJiaHaoVideo

    account_file = resolve_path(params["account_file"])

    title = truncate_title(params["title"], "baijiahao")
    tags = params["tags"]
    publish_strategy = params["publish_strategy"]
    publish_time = params["publish_time"]
    content_type = params["content_type"]

    try:
        if content_type == "video":
            video_file = resolve_path(params["video_file"])
            if not video_file or not os.path.exists(video_file):
                return {"success": False, "message": f"视频文件不存在: {video_file}"}

            uploader = BaiJiaHaoVideo(
                title=title,
                file_path=video_file,
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
            )
        else:
            return {"success": False, "message": "百家号不支持图文发布，请使用 convert_to_video=true 转为视频发布"}

        await uploader.main()
        return {"success": True, "message": "发布成功"}
    except Exception as e:
        return {"success": False, "message": str(e)}


async def publish_to_weibo(params: dict) -> dict:
    """发布到微博"""
    from uploader.weibo_uploader.main import WeiboVideo, WeiboNote
    from utils.excel_writer import write_video_link

    account_file = resolve_path(params["account_file"])

    title = truncate_title(params["title"], "weibo")
    tags = params["tags"]
    publish_strategy = params["publish_strategy"]
    publish_time = params["publish_time"]
    content_type = params["content_type"]

    try:
        if content_type == "video":
            video_file = resolve_path(params["video_file"])
            if not video_file or not os.path.exists(video_file):
                return {"success": False, "message": f"视频文件不存在: {video_file}"}

            uploader = WeiboVideo(
                title=title,
                file_path=video_file,
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
                desc=params["desc"],
                publish_strategy=publish_strategy,
            )
        else:
            images = params["images"]
            if not images:
                return {"success": False, "message": "图文模式需要提供图片"}

            image_paths = [resolve_path(img) for img in images]
            for img_path in image_paths:
                if not os.path.exists(img_path):
                    return {"success": False, "message": f"图片文件不存在: {img_path}"}

            uploader = WeiboNote(
                image_paths=image_paths,
                note=params["desc"],
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
                title=title,
                publish_strategy=publish_strategy,
            )

        result = await uploader.main()
        video_link = result.get("video_link", "") if result else ""

        response = {"success": True, "message": "发布成功"}
        if video_link:
            response["video_link"] = video_link
            # 写入 Excel
            try:
                write_result = write_video_link(video_link)
                if write_result["success"]:
                    print(f"  📝 视频链接已写入 Excel: {video_link}")
                else:
                    print(f"  ⚠️ 写入 Excel 失败: {write_result['message']}")
            except Exception as e:
                print(f"  ⚠️ 写入 Excel 异常: {e}")

        return response
    except Exception as e:
        return {"success": False, "message": str(e)}


async def publish_to_platform(platform: str, params: dict) -> dict:
    """发布到指定平台"""
    if platform == "douyin":
        return await publish_to_douyin(params)
    elif platform == "xiaohongshu":
        return await publish_to_xiaohongshu(params)
    elif platform == "kuaishou":
        return await publish_to_kuaishou(params)
    elif platform == "bilibili":
        return {"success": False, "message": "B站平台暂未实现"}
    elif platform == "tencent":
        return await publish_to_tencent(params)
    elif platform == "baijiahao":
        return await publish_to_baijiahao(params)
    elif platform == "tk":
        return {"success": False, "message": "TikTok平台暂未实现"}
    elif platform == "weibo":
        return await publish_to_weibo(params)
    else:
        return {"success": False, "message": f"未知平台: {platform}"}


def print_header(params: dict):
    """打印发布信息头部"""
    content_type_name = "图文" if params["content_type"] == "note" else "视频"
    print("\n========== 多平台发布 ==========")
    print(f"内容类型: {content_type_name}")
    if params["content_type"] == "note" and params["convert_to_video"]:
        print("图文转视频: 是")
    print(f"标题: {params['title']}")
    if params["tags"]:
        print(f"标签: {params['tags']}")
    print(f"启用平台: {', '.join(params['enabled_platforms'])}")
    print()


def print_results(results: dict):
    """打印发布结果汇总"""
    print("\n========== 发布结果 ==========")
    for platform, result in results.items():
        platform_name = PLATFORM_NAMES.get(platform, platform)
        status = "✅ 成功" if result["success"] else f"❌ 失败: {result['message']}"
        print(f"{platform_name}: {status}")


async def publish_one_item(video_params: Dict[str, Any]) -> Dict[str, Any]:
    print_header(video_params)

    results = {}
    total = len(video_params["enabled_platforms"])

    for i, platform in enumerate(video_params["enabled_platforms"], 1):
        platform_name = PLATFORM_NAMES.get(platform, platform)

        # 获取账号文件（支持逗号分隔多账号）
        account_key = f"{platform}_account"
        account_file_str = video_params["platforms"].get(account_key, "")
        account_files = [af.strip() for af in account_file_str.split(",") if af.strip()]

        if not account_files:
            print(f"[{i}/{total}] 发布到 {platform_name}...")
            results[platform] = {"success": False, "message": f"未配置 {platform} 账号"}
            print("  ❌ 失败: 未配置账号")
            continue

        for acct_idx, account_file in enumerate(account_files):
            if len(account_files) > 1:
                print(f"[{i}/{total}] 发布到 {platform_name} (账号 {acct_idx + 1}/{len(account_files)})...")
            else:
                print(f"[{i}/{total}] 发布到 {platform_name}...")

            platform_params = {
                **video_params,
                "account_file": account_file,
            }

            result_key = platform if len(account_files) == 1 else f"{platform}_{acct_idx + 1}"

            if platform_requires_account_login(platform) and not await ensure_account_login(platform, account_file):
                results[result_key] = {"success": False, "message": f"登录失败: {platform_name}"}
                print("  失败: 登录失败")
                continue

            result = await publish_to_platform(platform, platform_params)
            results[result_key] = result

            if result["success"]:
                print("  ✅ 成功")
            else:
                print(f"  ❌ 失败: {result['message']}")

    print_results(results)
    return results


async def run_publish_with_params(params: Dict[str, Any]) -> int:
    if not params["enabled_platforms"]:
        print("❌ 错误: 未配置启用平台")
        return 1

    # 注意：标题为空时，会在视频处理流程中自动生成或使用模板填充
    # 不在此处检查标题，让 get_video_content() 处理

    # 处理图文转视频
    if params["content_type"] == "note" and params["convert_to_video"]:
        if not params["images"]:
            print("❌ 错误: 图文转视频需要提供图片")
            return 1

        print("正在将图片转换为视频...")
        try:
            from utils.image_to_video import convert_images_to_video_for_publish

            video_path = convert_images_to_video_for_publish(
                image_paths=params["images"],
                title=params["title"],
                duration=params["video_duration"],
            )
            # 更新参数，切换为视频模式
            params["content_type"] = "video"
            params["video_file"] = video_path
            print(f"[OK] 视频已生成: {video_path}\n")
        except Exception as e:
            print(f"[ERROR] 图片转视频失败: {e}")
            return 1

    # 获取视频文件列表
    video_files = get_video_files(params["video_file"])
    if not video_files:
        print("❌ 错误: 未找到视频文件")
        return 1

    if not await runtime_preflight():
        print("❌ 错误: 运行环境检查失败")
        return 1

    print(f"找到 {len(video_files)} 个视频文件:")
    for vf in video_files:
        print(f"  - {os.path.basename(vf)}")
    print()

    # 遍历每个视频文件进行发布
    all_results = {}
    start_from = params.get("start_from", 1)
    if start_from > 1:
        print(f"\n[SKIP] 从第 {start_from} 个视频开始发布（跳过前 {start_from - 1} 个）\n")

    for video_idx, video_file in enumerate(video_files, 1):
        # 跳过已发布的视频
        if video_idx < start_from:
            continue

        print(f"\n========== 视频 [{video_idx}/{len(video_files)}] ==========")
        print(f"文件: {os.path.basename(video_file)}")

        # 使用视频配置文件或默认配置/模板填充
        title, desc = get_video_content(
            video_file,
            params["title"],
            params["desc"],
            force=params.get("force", False),
        )

        # 更新参数
        video_params = {
            **params,
            "video_file": video_file,
            "title": title,
            "desc": desc,
        }

        all_results[video_file] = await publish_one_item(video_params)

    # 打印总体汇总
    print("\n========== 总体发布汇总 ==========")
    success_count = sum(1 for results in all_results.values() for result in results.values() if result["success"])
    fail_count = sum(1 for results in all_results.values() for result in results.values() if not result["success"])
    print(f"成功: {success_count} 次")
    print(f"失败: {fail_count} 次")

    return 0 if fail_count == 0 else 1


async def run_publish(
    config_file: str = "publish_config.ini",
    overrides: Optional[PublishOverrides] = None,
) -> int:
    config_path = Path(config_file)
    if not config_path.is_absolute():
        config_path = BASE_DIR / config_path

    if config_path.exists():
        config = read_config(str(config_path))
        params = parse_config(config)
    else:
        if overrides is None or overrides.platforms is None or overrides.video is None:
            print(f"❌ 错误: 配置文件不存在: {config_path}")
            print("请提供配置文件，或同时指定 --platforms 和 --video")
            return 1
        params = default_params_from_overrides()

    params = apply_overrides(params, overrides)
    return await run_publish_with_params(params)


def run_publish_sync(
    config_file: str = "publish_config.ini",
    overrides: Optional[PublishOverrides] = None,
) -> int:
    return asyncio.run(run_publish(config_file, overrides))


async def main() -> int:
    """主函数"""
    return await run_publish()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
