from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence

from conf import BASE_DIR
from uploader.bilibili_uploader.runtime import run_biliup_command
from uploader.douyin_uploader.main import (
    DOUYIN_PUBLISH_STRATEGY_IMMEDIATE,
    DOUYIN_PUBLISH_STRATEGY_SCHEDULED,
    DouYinNote,
    DouYinVideo,
    cookie_auth as douyin_cookie_auth,
    douyin_setup,
)
from uploader.ks_uploader.main import (
    KUAISHOU_PUBLISH_STRATEGY_IMMEDIATE,
    KUAISHOU_PUBLISH_STRATEGY_SCHEDULED,
    KSNote,
    KSVideo,
    cookie_auth as kuaishou_cookie_auth,
    ks_setup,
)
from uploader.xiaohongshu_uploader.main import (
    XIAOHONGSHU_PUBLISH_STRATEGY_IMMEDIATE,
    XIAOHONGSHU_PUBLISH_STRATEGY_SCHEDULED,
    XiaoHongShuNote,
    XiaoHongShuVideo,
    cookie_auth as xiaohongshu_cookie_auth,
    xiaohongshu_setup,
)

SCHEDULE_FORMAT = "%Y-%m-%d %H:%M"


@dataclass
class DouyinVideoUploadRequest:
    account_name: str
    video_file: Path
    title: str
    description: str
    tags: list[str]
    publish_date: datetime | int
    thumbnail_file: Path | None = None
    product_link: str = ""
    product_title: str = ""
    publish_strategy: str = DOUYIN_PUBLISH_STRATEGY_IMMEDIATE
    debug: bool = True
    headless: bool = True


@dataclass
class DouyinNoteUploadRequest:
    account_name: str
    image_files: list[Path]
    title: str
    note: str
    tags: list[str]
    publish_date: datetime | int
    publish_strategy: str = DOUYIN_PUBLISH_STRATEGY_IMMEDIATE
    debug: bool = True
    headless: bool = True


@dataclass
class KuaishouVideoUploadRequest:
    account_name: str
    video_file: Path
    title: str
    description: str
    tags: list[str]
    publish_date: datetime | int
    thumbnail_file: Path | None = None
    publish_strategy: str = KUAISHOU_PUBLISH_STRATEGY_IMMEDIATE
    debug: bool = True
    headless: bool = True


@dataclass
class KuaishouNoteUploadRequest:
    account_name: str
    image_files: list[Path]
    title: str
    note: str
    tags: list[str]
    publish_date: datetime | int
    publish_strategy: str = KUAISHOU_PUBLISH_STRATEGY_IMMEDIATE
    debug: bool = True
    headless: bool = True


@dataclass
class XiaohongshuVideoUploadRequest:
    account_name: str
    video_file: Path
    title: str
    description: str
    tags: list[str]
    publish_date: datetime | int
    thumbnail_file: Path | None = None
    publish_strategy: str = XIAOHONGSHU_PUBLISH_STRATEGY_IMMEDIATE
    debug: bool = True
    headless: bool = True


@dataclass
class XiaohongshuNoteUploadRequest:
    account_name: str
    image_files: list[Path]
    title: str
    note: str
    tags: list[str]
    publish_date: datetime | int
    publish_strategy: str = XIAOHONGSHU_PUBLISH_STRATEGY_IMMEDIATE
    debug: bool = True
    headless: bool = True


@dataclass
class BilibiliVideoUploadRequest:
    account_name: str
    video_file: Path
    title: str
    description: str
    tid: int
    tags: list[str]
    publish_date: datetime | int


def has_interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def resolve_runtime_home() -> Path:
    return Path(BASE_DIR)


def resolve_account_file(platform: str, account_name: str) -> Path:
    account_file = resolve_runtime_home() / "cookies" / f"{platform}_{account_name}.json"
    account_file.parent.mkdir(exist_ok=True)
    return account_file


async def _ensure_login(platform: str, account_file: Path, headless: bool = False) -> bool:
    """检查 cookie 有效性，无效则自动触发登录。返回 True 表示已登录。"""
    check_funcs = {
        "douyin": ("uploader.douyin_uploader.main", "cookie_auth"),
        "kuaishou": ("uploader.ks_uploader.main", "cookie_auth"),
        "xiaohongshu": ("uploader.xiaohongshu_uploader.main", "cookie_auth"),
        "weibo": ("uploader.weibo_uploader.main", "cookie_auth"),
        "tencent": ("uploader.tencent_uploader.main", "cookie_auth"),
        "baijiahao": ("uploader.baijiahao_uploader.main", "cookie_auth"),
        "tk": ("uploader.tk_uploader.main", "cookie_auth"),
    }

    # Bilibili 特殊处理
    if platform == "bilibili":
        from uploader.bilibili_uploader.runtime import run_biliup_command
        result = run_biliup_command(["-u", str(account_file), "renew"])
        if result.returncode == 0:
            return True
        print(f"Cookie invalid, triggering login for bilibili...")
        result = run_biliup_command(["-u", str(account_file), "login"], interactive=True)
        return result.returncode == 0

    module_path, func_name = check_funcs.get(platform, (None, None))
    if not module_path:
        print(f"No check function for platform: {platform}", file=sys.stderr)
        return False

    import importlib
    module = importlib.import_module(module_path)
    check_func = getattr(module, func_name)

    # 检查 cookie
    if await check_func(str(account_file)):
        return True

    # Cookie 无效，自动触发登录
    print(f"Cookie invalid, triggering login for {platform}...")
    setup_funcs = {
        "douyin": ("uploader.douyin_uploader.main", "douyin_setup"),
        "kuaishou": ("uploader.ks_uploader.main", "ks_setup"),
        "xiaohongshu": ("uploader.xiaohongshu_uploader.main", "xiaohongshu_setup"),
        "weibo": ("uploader.weibo_uploader.main", "weibo_setup"),
        "tencent": ("uploader.tencent_uploader.main", "tencent_setup"),
        "baijiahao": ("uploader.baijiahao_uploader.main", "baijiahao_setup"),
        "tk": ("uploader.tk_uploader.main", "tiktok_setup"),
    }

    setup_path, setup_name = setup_funcs.get(platform, (None, None))
    if not setup_path:
        print(f"No login function for platform: {platform}", file=sys.stderr)
        return False

    setup_module = importlib.import_module(setup_path)
    setup_func = getattr(setup_module, setup_name)

    # baijiahao 和 tk 的 setup 签名不同
    if platform in ("baijiahao", "tk"):
        result = await setup_func(str(account_file), handle=True)
    else:
        result = await setup_func(str(account_file), handle=True, return_detail=True, headless=headless)

    if isinstance(result, dict):
        return result.get("success", False)
    return bool(result)


def parse_tags(raw_tags: str | None) -> list[str]:
    if not raw_tags:
        return []

    tags: list[str] = []
    for item in raw_tags.split(","):
        cleaned = item.strip().lstrip("#")
        if cleaned:
            tags.append(cleaned)
    return tags


def parse_image_files(raw_files: Iterable[Path]) -> list[Path]:
    return [Path(file) for file in raw_files]


def parse_schedule(raw_schedule: str | None) -> datetime | int:
    if not raw_schedule:
        return 0
    return datetime.strptime(raw_schedule, SCHEDULE_FORMAT)


async def login_douyin_account(account_name: str, headless: bool = True) -> dict:
    account_file = resolve_account_file("douyin", account_name)
    return await douyin_setup(str(account_file), handle=True, return_detail=True, headless=headless)


async def check_douyin_account(account_name: str) -> bool:
    account_file = resolve_account_file("douyin", account_name)
    if not account_file.exists():
        return False
    return await douyin_cookie_auth(str(account_file))


async def login_kuaishou_account(account_name: str, headless: bool = True) -> dict:
    account_file = resolve_account_file("kuaishou", account_name)
    return await ks_setup(str(account_file), handle=True, return_detail=True, headless=headless)


async def check_kuaishou_account(account_name: str) -> bool:
    account_file = resolve_account_file("kuaishou", account_name)
    if not account_file.exists():
        return False
    return await kuaishou_cookie_auth(str(account_file))


async def login_xiaohongshu_account(account_name: str, headless: bool = True) -> dict:
    account_file = resolve_account_file("xiaohongshu", account_name)
    return await xiaohongshu_setup(str(account_file), handle=True, return_detail=True, headless=headless)


async def check_xiaohongshu_account(account_name: str) -> bool:
    account_file = resolve_account_file("xiaohongshu", account_name)
    if not account_file.exists():
        return False
    return await xiaohongshu_cookie_auth(str(account_file))


async def login_bilibili_account(account_name: str) -> dict:
    account_file = resolve_account_file("bilibili", account_name)
    if not has_interactive_terminal():
        return {
            "success": False,
            "message": (
                "Bilibili login requires a local interactive terminal. "
                f"Please run `sau bilibili login --account {account_name}` yourself in a local terminal. "
                "If the terminal QR code does not render completely, open `./qrcode.png` and scan that image."
            ),
            "account_file": str(account_file),
        }

    result = run_biliup_command(["-u", str(account_file), "login"], interactive=True)
    success = result.returncode == 0
    return {
        "success": success,
        "message": (result.stderr or result.stdout or "").strip() or "Bilibili login completed" if success else (result.stderr or result.stdout or "").strip() or "Bilibili login failed",
        "account_file": str(account_file),
    }


async def check_bilibili_account(account_name: str) -> bool:
    account_file = resolve_account_file("bilibili", account_name)
    if not account_file.exists():
        return False
    result = run_biliup_command(["-u", str(account_file), "renew"])
    return result.returncode == 0


async def upload_video(request: DouyinVideoUploadRequest) -> Path:
    account_file = resolve_account_file("douyin", request.account_name)
    is_ready = await douyin_setup(str(account_file), handle=False)
    if not is_ready:
        raise RuntimeError(
            f"Douyin cookie is missing or expired: {account_file}. Run `sau douyin login --account {request.account_name}` first."
        )

    app = DouYinVideo(
        request.title,
        str(request.video_file),
        request.tags,
        request.publish_date,
        str(account_file),
        desc=request.description,
        thumbnail_portrait_path=str(request.thumbnail_file) if request.thumbnail_file else None,
        productLink=request.product_link,
        productTitle=request.product_title,
        publish_strategy=request.publish_strategy,
        debug=request.debug,
        headless=request.headless,
    )
    await app.douyin_upload_video()
    return account_file


async def upload_note(request: DouyinNoteUploadRequest) -> Path:
    account_file = resolve_account_file("douyin", request.account_name)
    is_ready = await douyin_setup(str(account_file), handle=False)
    if not is_ready:
        raise RuntimeError(
            f"Douyin cookie is missing or expired: {account_file}. Run `sau douyin login --account {request.account_name}` first."
        )

    app = DouYinNote(
        image_paths=[str(path) for path in request.image_files],
        title=request.title,
        note=request.note,
        tags=request.tags,
        publish_date=request.publish_date,
        account_file=str(account_file),
        publish_strategy=request.publish_strategy,
        debug=request.debug,
        headless=request.headless,
    )
    await app.douyin_upload_note()
    return account_file


async def upload_kuaishou_video(request: KuaishouVideoUploadRequest) -> Path:
    account_file = resolve_account_file("kuaishou", request.account_name)
    is_ready = await ks_setup(str(account_file), handle=False)
    if not is_ready:
        raise RuntimeError(
            f"Kuaishou cookie is missing or expired: {account_file}. Run `sau kuaishou login --account {request.account_name}` first."
        )

    app = KSVideo(
        title=request.title,
        file_path=str(request.video_file),
        desc=request.description,
        tags=request.tags,
        publish_date=request.publish_date,
        account_file=str(account_file),
        thumbnail_path=str(request.thumbnail_file) if request.thumbnail_file else None,
        publish_strategy=request.publish_strategy,
        debug=request.debug,
        headless=request.headless,
    )
    await app.main()
    return account_file


async def upload_kuaishou_note(request: KuaishouNoteUploadRequest) -> Path:
    account_file = resolve_account_file("kuaishou", request.account_name)
    is_ready = await ks_setup(str(account_file), handle=False)
    if not is_ready:
        raise RuntimeError(
            f"Kuaishou cookie is missing or expired: {account_file}. Run `sau kuaishou login --account {request.account_name}` first."
        )

    app = KSNote(
        image_paths=[str(path) for path in request.image_files],
        title=request.title,
        note=request.note,
        tags=request.tags,
        publish_date=request.publish_date,
        account_file=str(account_file),
        publish_strategy=request.publish_strategy,
        debug=request.debug,
        headless=request.headless,
    )
    await app.main()
    return account_file


async def upload_xiaohongshu_video(request: XiaohongshuVideoUploadRequest) -> dict:
    account_file = resolve_account_file("xiaohongshu", request.account_name)
    is_ready = await xiaohongshu_setup(str(account_file), handle=False)
    if not is_ready:
        raise RuntimeError(
            f"Xiaohongshu cookie is missing or expired: {account_file}. Run `sau xiaohongshu login --account {request.account_name}` first."
        )

    app = XiaoHongShuVideo(
        title=request.title,
        file_path=str(request.video_file),
        desc=request.description,
        tags=request.tags,
        publish_date=request.publish_date,
        account_file=str(account_file),
        thumbnail_path=str(request.thumbnail_file) if request.thumbnail_file else None,
        publish_strategy=request.publish_strategy,
        debug=request.debug,
        headless=request.headless,
    )
    result = await app.main()
    return result


async def upload_xiaohongshu_note(request: XiaohongshuNoteUploadRequest) -> dict:
    account_file = resolve_account_file("xiaohongshu", request.account_name)
    is_ready = await xiaohongshu_setup(str(account_file), handle=False)
    if not is_ready:
        raise RuntimeError(
            f"Xiaohongshu cookie is missing or expired: {account_file}. Run `sau xiaohongshu login --account {request.account_name}` first."
        )

    app = XiaoHongShuNote(
        image_paths=[str(path) for path in request.image_files],
        title=request.title,
        desc=request.note,
        note=request.note,
        tags=request.tags,
        publish_date=request.publish_date,
        account_file=str(account_file),
        publish_strategy=request.publish_strategy,
        debug=request.debug,
        headless=request.headless,
    )
    result = await app.main()
    return result


async def upload_bilibili_video(request: BilibiliVideoUploadRequest) -> Path:
    account_file = resolve_account_file("bilibili", request.account_name)
    if not account_file.exists():
        raise RuntimeError(
            f"Bilibili account file is missing: {account_file}. Run `sau bilibili login --account {request.account_name}` first."
        )

    arguments = [
        "-u",
        str(account_file),
        "upload",
        str(request.video_file),
        "--title",
        request.title,
        "--desc",
        request.description,
        "--tid",
        str(request.tid),
    ]
    if request.tags:
        arguments.extend(["--tag", ",".join(request.tags)])
    if isinstance(request.publish_date, datetime):
        arguments.extend(["--dtime", str(int(request.publish_date.timestamp()))])

    result = run_biliup_command(arguments)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "").strip() or "Bilibili upload failed")
    return account_file


def existing_file_path(value: str) -> Path:
    path = Path(value)
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"File not found: {value}")
    return path


def schedule_value(value: str):
    try:
        return parse_schedule(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid schedule '{value}'. Expected format: {SCHEDULE_FORMAT}"
        ) from exc


def add_runtime_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    headless_group = parser.add_mutually_exclusive_group()
    headless_group.add_argument("--headed", dest="headless", action="store_false", help="Run with browser UI")
    headless_group.add_argument("--headless", dest="headless", action="store_true", help="Run in headless mode")
    parser.set_defaults(headless=True)


def build_parser() -> argparse.ArgumentParser:
    schedule_help = SCHEDULE_FORMAT.replace("%", "%%")
    parser = argparse.ArgumentParser(
        prog="sau",
        description="CLI for social-auto-upload.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # === status 子命令 ===
    status_parser = subparsers.add_parser("status", help="Check environment and login status")

    # === login 子命令 ===
    login_parser = subparsers.add_parser("login", help="Login to a platform")
    login_parser.add_argument("--platform", required=True,
                              choices=["douyin", "kuaishou", "xiaohongshu", "bilibili", "weibo", "tencent", "baijiahao", "tk"],
                              help="Platform to login")
    login_parser.add_argument("--account", required=True, help="Account name")
    login_parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")

    # === generate 子命令 ===
    generate_parser = subparsers.add_parser("generate", help="Generate video title/description from content analysis")
    generate_parser.add_argument("--dir", required=True, help="Video directory path")
    generate_parser.add_argument("--force", action="store_true", help="Force overwrite existing config files")

    douyin_parser = subparsers.add_parser("douyin", help="Douyin operations")
    douyin_actions = douyin_parser.add_subparsers(dest="action", required=True)

    for action_name in ("login", "check"):
        action_parser = douyin_actions.add_parser(action_name, help=f"Douyin {action_name}")
        action_parser.add_argument("--account", required=True, help="Douyin user-defined account_name")
        if action_name == "login":
            add_runtime_flags(action_parser)

    upload_video_parser = douyin_actions.add_parser("upload-video", help="Upload one video to Douyin")
    upload_video_parser.add_argument("--account", required=True, help="Douyin user-defined account_name")
    upload_video_parser.add_argument("--file", required=True, type=existing_file_path, help="Video file path")
    upload_video_parser.add_argument("--title", required=True, help="Video title")
    upload_video_parser.add_argument("--desc", default="", help="Optional video description")
    upload_video_parser.add_argument("--tags", default="", help="Comma-separated tags, such as tag1,tag2")
    upload_video_parser.add_argument("--schedule", type=schedule_value, help=f"Schedule time in {schedule_help}")
    upload_video_parser.add_argument("--thumbnail", type=existing_file_path, help="Optional thumbnail path")
    upload_video_parser.add_argument("--product-link", default="", help="Optional product link")
    upload_video_parser.add_argument("--product-title", default="", help="Optional product title")
    add_runtime_flags(upload_video_parser)

    upload_note_parser = douyin_actions.add_parser("upload-note", help="Upload one note to Douyin")
    upload_note_parser.add_argument("--account", required=True, help="Douyin user-defined account_name")
    upload_note_parser.add_argument("--images", required=True, nargs="+", type=existing_file_path, help="Image file paths")
    upload_note_parser.add_argument("--title", required=True, help="Note title")
    upload_note_parser.add_argument("--note", default="", help="Optional note content")
    upload_note_parser.add_argument("--tags", default="", help="Comma-separated tags, such as tag1,tag2")
    upload_note_parser.add_argument("--schedule", type=schedule_value, help=f"Schedule time in {schedule_help}")
    add_runtime_flags(upload_note_parser)

    kuaishou_parser = subparsers.add_parser("kuaishou", help="Kuaishou operations")
    kuaishou_actions = kuaishou_parser.add_subparsers(dest="action", required=True)

    for action_name in ("login", "check"):
        action_parser = kuaishou_actions.add_parser(action_name, help=f"Kuaishou {action_name}")
        action_parser.add_argument("--account", required=True, help="Kuaishou user-defined account_name")
        if action_name == "login":
            add_runtime_flags(action_parser)

    kuaishou_upload_video_parser = kuaishou_actions.add_parser("upload-video", help="Upload one video to Kuaishou")
    kuaishou_upload_video_parser.add_argument("--account", required=True, help="Kuaishou user-defined account_name")
    kuaishou_upload_video_parser.add_argument("--file", required=True, type=existing_file_path, help="Video file path")
    kuaishou_upload_video_parser.add_argument("--title", required=True, help="Video title")
    kuaishou_upload_video_parser.add_argument("--desc", default="", help="Optional video description")
    kuaishou_upload_video_parser.add_argument("--tags", default="", help="Comma-separated tags, such as tag1,tag2")
    kuaishou_upload_video_parser.add_argument("--schedule", type=schedule_value, help=f"Schedule time in {schedule_help}")
    kuaishou_upload_video_parser.add_argument("--thumbnail", type=existing_file_path, help="Optional thumbnail path")
    add_runtime_flags(kuaishou_upload_video_parser)

    kuaishou_upload_note_parser = kuaishou_actions.add_parser("upload-note", help="Upload one note to Kuaishou")
    kuaishou_upload_note_parser.add_argument("--account", required=True, help="Kuaishou user-defined account_name")
    kuaishou_upload_note_parser.add_argument("--images", required=True, nargs="+", type=existing_file_path, help="Image file paths")
    kuaishou_upload_note_parser.add_argument("--title", required=True, help="Note title")
    kuaishou_upload_note_parser.add_argument("--note", default="", help="Optional note content")
    kuaishou_upload_note_parser.add_argument("--tags", default="", help="Comma-separated tags, such as tag1,tag2")
    kuaishou_upload_note_parser.add_argument("--schedule", type=schedule_value, help=f"Schedule time in {schedule_help}")
    add_runtime_flags(kuaishou_upload_note_parser)

    xiaohongshu_parser = subparsers.add_parser("xiaohongshu", help="Xiaohongshu operations")
    xiaohongshu_actions = xiaohongshu_parser.add_subparsers(dest="action", required=True)

    for action_name in ("login", "check"):
        action_parser = xiaohongshu_actions.add_parser(action_name, help=f"Xiaohongshu {action_name}")
        action_parser.add_argument("--account", required=True, help="Xiaohongshu user-defined account_name")
        if action_name == "login":
            add_runtime_flags(action_parser)

    xiaohongshu_upload_video_parser = xiaohongshu_actions.add_parser("upload-video", help="Upload one video to Xiaohongshu")
    xiaohongshu_upload_video_parser.add_argument("--account", required=True, help="Xiaohongshu user-defined account_name")
    xiaohongshu_upload_video_parser.add_argument("--file", required=True, type=existing_file_path, help="Video file path")
    xiaohongshu_upload_video_parser.add_argument("--title", required=True, help="Video title")
    xiaohongshu_upload_video_parser.add_argument("--desc", default="", help="Optional video description")
    xiaohongshu_upload_video_parser.add_argument("--tags", default="", help="Comma-separated tags, such as tag1,tag2")
    xiaohongshu_upload_video_parser.add_argument("--schedule", type=schedule_value, help=f"Schedule time in {schedule_help}")
    xiaohongshu_upload_video_parser.add_argument("--thumbnail", type=existing_file_path, help="Optional thumbnail path")
    add_runtime_flags(xiaohongshu_upload_video_parser)

    xiaohongshu_upload_note_parser = xiaohongshu_actions.add_parser("upload-note", help="Upload one note to Xiaohongshu")
    xiaohongshu_upload_note_parser.add_argument("--account", required=True, help="Xiaohongshu user-defined account_name")
    xiaohongshu_upload_note_parser.add_argument("--images", required=True, nargs="+", type=existing_file_path, help="Image file paths")
    xiaohongshu_upload_note_parser.add_argument("--title", required=True, help="Note title")
    xiaohongshu_upload_note_parser.add_argument("--note", default="", help="Optional note content")
    xiaohongshu_upload_note_parser.add_argument("--tags", default="", help="Comma-separated tags, such as tag1,tag2")
    xiaohongshu_upload_note_parser.add_argument("--schedule", type=schedule_value, help=f"Schedule time in {schedule_help}")
    add_runtime_flags(xiaohongshu_upload_note_parser)

    # === publish 子命令 ===
    publish_parser = subparsers.add_parser("publish", help="Publish to multiple platforms via config file")
    publish_parser.add_argument("--config", default="publish_config.ini", help="Config file path (default: publish_config.ini)")
    publish_parser.add_argument("--platforms", default=None, help="Override enabled platforms, comma-separated")
    publish_parser.add_argument("--video", default=None, help="Override video file/directory path")
    publish_parser.add_argument("--title", default=None, help="Override title")
    publish_parser.add_argument("--desc", default=None, help="Override description")
    publish_parser.add_argument("--tags", default=None, help="Override tags, comma-separated")
    publish_parser.add_argument("--schedule", type=schedule_value, default=None, help=f"Override schedule time in {schedule_help}")
    publish_parser.add_argument("--start-from", type=int, default=None, help="Start from video index (1-based)")
    publish_parser.add_argument("--force", action="store_true", help="Force regenerate video config")

    bilibili_parser = subparsers.add_parser("bilibili", help="Bilibili operations")
    bilibili_actions = bilibili_parser.add_subparsers(dest="action", required=True)

    for action_name in ("login", "check"):
        action_parser = bilibili_actions.add_parser(action_name, help=f"Bilibili {action_name}")
        action_parser.add_argument("--account", required=True, help="Bilibili user-defined account_name")

    bilibili_upload_video_parser = bilibili_actions.add_parser("upload-video", help="Upload one video to Bilibili")
    bilibili_upload_video_parser.add_argument("--account", required=True, help="Bilibili user-defined account_name")
    bilibili_upload_video_parser.add_argument("--file", required=True, type=existing_file_path, help="Video file path")
    bilibili_upload_video_parser.add_argument("--title", required=True, help="Video title")
    bilibili_upload_video_parser.add_argument("--desc", required=True, help="Video description")
    bilibili_upload_video_parser.add_argument("--tid", required=True, type=int, help="Bilibili category id")
    bilibili_upload_video_parser.add_argument("--tags", default="", help="Comma-separated tags, such as tag1,tag2")
    bilibili_upload_video_parser.add_argument("--schedule", type=schedule_value, help=f"Schedule time in {schedule_help}")
    return parser


async def dispatch(args: argparse.Namespace) -> int:
    # === 处理 status 命令 ===
    if args.command == "status":
        import shutil
        import subprocess

        # Python 版本
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        print(f"Python: {py_ver} ✓")

        # 浏览器驱动
        patchright_path = shutil.which("patchright")
        if patchright_path:
            print(f"Browser: patchright found at {patchright_path}")
        else:
            print("Browser: patchright not found (run: patchright install chromium)")

        # 配置目录
        from conf import BASE_DIR
        config_path = BASE_DIR / "config.json"
        if config_path.exists():
            print(f"Config: {config_path}")
        else:
            print(f"Config: {config_path} (not found, using defaults)")

        # Cookies 状态
        cookies_dir = BASE_DIR / "cookies"
        platforms = {
            "weibo": "weibo_uploader",
            "kuaishou": "ks_uploader",
            "douyin": "douyin_uploader",
            "xiaohongshu": "xiaohongshu_uploader",
            "bilibili": "bilibili_uploader",
            "tencent": "tencent_uploader",
            "baijiahao": "baijiahao_uploader",
            "tk": "tk_uploader",
        }
        ready = []
        for name, subdir in platforms.items():
            cookie_dir = cookies_dir / subdir
            if cookie_dir.exists():
                accounts = list(cookie_dir.glob("*.json"))
                if accounts:
                    acct_names = [a.stem for a in accounts]
                    print(f"  {name}: {', '.join(acct_names)}")
                    ready.append(name)
                else:
                    print(f"  {name}: no accounts")
            else:
                print(f"  {name}: no accounts")

        if ready:
            print(f"Platforms ready: {', '.join(ready)}")
        else:
            print("Platforms ready: none (login required)")

        return 0

    # === 处理 login 命令 ===
    if args.command == "login":
        platform = args.platform
        account = args.account
        account_file = resolve_account_file(platform, account)
        headless = args.headless

        setup_map = {
            "douyin": ("uploader.douyin_uploader.main", "douyin_setup"),
            "kuaishou": ("uploader.ks_uploader.main", "ks_setup"),
            "xiaohongshu": ("uploader.xiaohongshu_uploader.main", "xiaohongshu_setup"),
            "weibo": ("uploader.weibo_uploader.main", "weibo_setup"),
            "tencent": ("uploader.tencent_uploader.main", "tencent_setup"),
            "baijiahao": ("uploader.baijiahao_uploader.main", "baijiahao_setup"),
            "tk": ("uploader.tk_uploader.main", "tiktok_setup"),
            "bilibili": ("uploader.bilibili_uploader.runtime", "run_biliup_command"),
        }

        entry = setup_map.get(platform)
        if not entry:
            print(f"Unsupported platform: {platform}", file=sys.stderr)
            return 1

        import importlib
        module = importlib.import_module(entry[0])
        func = getattr(module, entry[1])

        # bilibili 特殊处理
        if platform == "bilibili":
            result = func(["-u", str(account_file), "login"], interactive=True)
            return 0 if result.returncode == 0 else 1

        # baijiahao 和 tk 的 setup 签名不同
        if platform in ("baijiahao", "tk"):
            result = await func(str(account_file), handle=True)
        else:
            result = await func(str(account_file), handle=True, return_detail=True, headless=headless)

        if isinstance(result, dict):
            if result.get("success"):
                print(f"Login successful: {platform}")
                return 0
            else:
                print(f"Login failed: {result.get('message', 'unknown error')}", file=sys.stderr)
                return 1
        elif isinstance(result, bool):
            return 0 if result else 1
        else:
            return 0

    # === 处理 generate 命令 ===
    if args.command == "generate":
        import os
        import shutil

        from utils.video_analyzer import (
            analyze_frames_with_glm4v,
            extract_all_frames_parallel,
            get_video_files,
            save_video_config,
            config_exists,
            get_frame_files,
            cleanup_frames_dir,
        )

        directory = args.dir
        if not os.path.isdir(directory):
            print(f"错误: 目录不存在: {directory}", file=sys.stderr)
            return 1

        video_files = get_video_files(directory)
        if not video_files:
            print(f"未找到视频文件: {directory}")
            return 0

        total = len(video_files)
        print(f"找到 {total} 个视频文件")
        print("=" * 50)

        # === 阶段1: 并发提取所有视频帧 ===
        print("\n[阶段1] 提取视频帧...")

        frames_results = {}
        failed_extractions = []

        def extraction_callback(video_file, frames_dir, error):
            basename = os.path.basename(video_file)
            if error:
                print(f"  ❌ {basename}: {error}")
                failed_extractions.append(video_file)
            else:
                print(f"  ✓ {basename}")

        frames_results = extract_all_frames_parallel(
            video_files,
            progress_callback=extraction_callback
        )

        if failed_extractions:
            print(f"\n警告: {len(failed_extractions)} 个视频帧提取失败")

        # === 阶段2: 串行分析每个视频的帧 ===
        print("\n[阶段2] 分析视频内容...")
        print("提示: 此阶段使用智谱 GLM-4V 模型分析视频帧")
        print("-" * 50)

        results = {"success": 0, "skip": 0, "error": 0, "files": []}

        for idx, video_file in enumerate(video_files, 1):
            basename = os.path.basename(video_file)

            # 检查是否已存在配置文件
            if not args.force and config_exists(video_file):
                print(f"[{idx}/{total}] 跳过 {basename} (配置已存在)")
                results["skip"] += 1
                # 清理帧文件夹
                frames_dir = frames_results.get(video_file, "")
                if frames_dir:
                    cleanup_frames_dir(frames_dir)
                continue

            frames_dir = frames_results.get(video_file, "")
            if not frames_dir:
                print(f"[{idx}/{total}] 跳过 {basename} (帧提取失败)")
                results["error"] += 1
                continue

            frame_files = get_frame_files(frames_dir)
            if not frame_files:
                print(f"[{idx}/{total}] 跳过 {basename} (无有效帧)")
                results["error"] += 1
                cleanup_frames_dir(frames_dir)
                continue

            print(f"\n[{idx}/{total}] 分析: {basename}")
            print(f"  帧图像: {len(frame_files)} 张")

            try:
                # 调用 GLM-4V 分析
                title, desc = analyze_frames_with_glm4v(frame_files, basename)

                # 保存配置
                config_file = save_video_config(video_file, title, desc)
                print(f"  ✓ 标题: {title}")
                print(f"  ✓ 描述: {desc[:50]}{'...' if len(desc) > 50 else ''}")
                print(f"  ✓ 配置: {os.path.basename(config_file)}")

                results["success"] += 1
                results["files"].append({
                    "video": basename,
                    "config": os.path.basename(config_file),
                    "title": title
                })

            except RuntimeError as e:
                print(f"  ❌ 错误: {e}")
                results["error"] += 1
            except Exception as e:
                print(f"  ❌ 未知错误: {e}")
                results["error"] += 1

            # 清理帧文件夹
            cleanup_frames_dir(frames_dir)

        # 清理临时目录
        from conf import BASE_DIR
        temp_frames_dir = os.path.join(BASE_DIR, 'temp_frames')
        if os.path.exists(temp_frames_dir):
            shutil.rmtree(temp_frames_dir, ignore_errors=True)

        print("\n" + "=" * 50)
        print(f"生成完成: 成功 {results['success']}, 跳过 {results['skip']}, 错误 {results['error']}")
        return 0

    # === 处理 publish 命令 ===
    if args.command == "publish":
        from publish_all import read_config, parse_config, get_video_files, get_video_content, print_header, print_results, publish_to_platform, PLATFORM_NAMES, resolve_path

        config_file = args.config
        config_path = Path(config_file)
        if not config_path.is_absolute():
            config_path = Path(resolve_path(config_file))
        if not config_path.exists():
            print(f"Config file not found: {config_path}", file=sys.stderr)
            return 1

        config = read_config(config_file)
        params = parse_config(config)

        # CLI 参数覆盖配置文件
        if args.platforms is not None:
            params["enabled_platforms"] = [p.strip() for p in args.platforms.split(",") if p.strip()]
        if args.video is not None:
            params["video_file"] = args.video
        if args.title is not None:
            params["title"] = args.title
        if args.desc is not None:
            params["desc"] = args.desc
        if args.tags is not None:
            params["tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]
        if args.schedule is not None:
            params["publish_strategy"] = "scheduled"
            params["publish_time"] = args.schedule
        if args.start_from is not None:
            params["start_from"] = args.start_from
        if args.force:
            params["force"] = True

        if not params["enabled_platforms"]:
            print("No platforms enabled", file=sys.stderr)
            return 1

        # 图文转视频处理
        if params["content_type"] == "note" and params.get("convert_to_video"):
            if not params.get("images"):
                print("Image-to-video conversion requires images", file=sys.stderr)
                return 1
            print("Converting images to video...")
            try:
                from utils.image_to_video import convert_images_to_video_for_publish
                video_path = convert_images_to_video_for_publish(
                    image_paths=params["images"],
                    title=params["title"],
                    duration=params["video_duration"],
                )
                params["content_type"] = "video"
                params["video_file"] = video_path
                print(f"Video generated: {video_path}\n")
            except Exception as e:
                print(f"Image-to-video conversion failed: {e}", file=sys.stderr)
                return 1

        video_files = get_video_files(params["video_file"])
        if not video_files:
            print("No video files found", file=sys.stderr)
            return 1

        print(f"Found {len(video_files)} video file(s)")
        for vf in video_files:
            print(f"  - {Path(vf).name}")
        print()

        all_results = {}
        start_from = params.get("start_from", 1)
        if start_from > 1:
            print(f"\n[SKIP] Starting from video {start_from} (skipping {start_from - 1})\n")

        for video_idx, video_file in enumerate(video_files, 1):
            if video_idx < start_from:
                continue

            print(f"\n========== Video [{video_idx}/{len(video_files)}] ==========")
            print(f"File: {Path(video_file).name}")

            title, desc = get_video_content(video_file, params["title"], params["desc"])
            video_params = {**params, "video_file": video_file, "title": title, "desc": desc}

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
                    print(f"[{i}/{total}] Publishing to {platform_name}...")
                    results[platform] = {"success": False, "message": f"未配置 {platform} 账号"}
                    print(f"  ✗ Failed: 未配置账号")
                    continue

                for acct_idx, account_file in enumerate(account_files):
                    if len(account_files) > 1:
                        print(f"[{i}/{total}] Publishing to {platform_name} (account {acct_idx + 1}/{len(account_files)})...")
                    else:
                        print(f"[{i}/{total}] Publishing to {platform_name}...")

                    # 自动检查登录状态，未登录则触发登录
                    if not await _ensure_login(platform, Path(account_file)):
                        result_key = platform if len(account_files) == 1 else f"{platform}_{acct_idx + 1}"
                        results[result_key] = {"success": False, "message": f"登录失败: {platform}"}
                        print(f"  ✗ Failed: login required but failed")
                        continue

                    platform_params = {**video_params, "account_file": account_file}

                    result = await publish_to_platform(platform, platform_params)
                    result_key = platform if len(account_files) == 1 else f"{platform}_{acct_idx + 1}"
                    results[result_key] = result

                    if result["success"]:
                        print(f"  ✓ Success")
                    else:
                        print(f"  ✗ Failed: {result['message']}")

            print_results(results)
            all_results[video_file] = results

        # 总体汇总
        print("\n========== Summary ==========")
        success_count = sum(1 for results in all_results.values() for r in results.values() if r["success"])
        fail_count = sum(1 for results in all_results.values() for r in results.values() if not r["success"])
        print(f"Success: {success_count}")
        print(f"Failed: {fail_count}")

        return 0

    if args.command == "douyin":
        if args.action == "login":
            result = await login_douyin_account(args.account, headless=args.headless)
            if not result["success"]:
                raise RuntimeError(result["message"])
            print(f"Douyin login flow completed: {result['account_file']}")
            return 0

        if args.action == "check":
            is_valid = await check_douyin_account(args.account)
            print("valid" if is_valid else "invalid")
            return 0 if is_valid else 1

        publish_strategy = DOUYIN_PUBLISH_STRATEGY_SCHEDULED if args.schedule else DOUYIN_PUBLISH_STRATEGY_IMMEDIATE

        if args.action == "upload-video":
            request = DouyinVideoUploadRequest(
                account_name=args.account,
                video_file=args.file,
                title=args.title,
                description=args.desc,
                tags=parse_tags(args.tags),
                publish_date=args.schedule or 0,
                thumbnail_file=args.thumbnail,
                product_link=args.product_link,
                product_title=args.product_title,
                publish_strategy=publish_strategy,
                debug=args.debug,
                headless=args.headless,
            )
            await upload_video(request)
            print(f"Douyin video upload submitted: {request.video_file}")
            return 0

        if args.action == "upload-note":
            request = DouyinNoteUploadRequest(
                account_name=args.account,
                image_files=parse_image_files(args.images),
                title=args.title,
                note=args.note,
                tags=parse_tags(args.tags),
                publish_date=args.schedule or 0,
                publish_strategy=publish_strategy,
                debug=args.debug,
                headless=args.headless,
            )
            await upload_note(request)
            print(f"Douyin note upload submitted: {len(request.image_files)} images")
            return 0

        raise RuntimeError(f"Unsupported Douyin action: {args.action}")

    if args.command == "kuaishou":
        if args.action == "login":
            result = await login_kuaishou_account(args.account, headless=args.headless)
            if not result["success"]:
                raise RuntimeError(result["message"])
            print(f"Kuaishou login flow completed: {result['account_file']}")
            return 0

        if args.action == "check":
            is_valid = await check_kuaishou_account(args.account)
            print("valid" if is_valid else "invalid")
            return 0 if is_valid else 1

        publish_strategy = KUAISHOU_PUBLISH_STRATEGY_SCHEDULED if args.schedule else KUAISHOU_PUBLISH_STRATEGY_IMMEDIATE

        if args.action == "upload-video":
            request = KuaishouVideoUploadRequest(
                account_name=args.account,
                video_file=args.file,
                title=args.title,
                description=args.desc,
                tags=parse_tags(args.tags),
                publish_date=args.schedule or 0,
                thumbnail_file=args.thumbnail,
                publish_strategy=publish_strategy,
                debug=args.debug,
                headless=args.headless,
            )
            await upload_kuaishou_video(request)
            print(f"Kuaishou video upload submitted: {request.video_file}")
            return 0

        if args.action == "upload-note":
            request = KuaishouNoteUploadRequest(
                account_name=args.account,
                image_files=parse_image_files(args.images),
                title=args.title,
                note=args.note,
                tags=parse_tags(args.tags),
                publish_date=args.schedule or 0,
                publish_strategy=publish_strategy,
                debug=args.debug,
                headless=args.headless,
            )
            await upload_kuaishou_note(request)
            print(f"Kuaishou note upload submitted: {len(request.image_files)} images")
            return 0

        raise RuntimeError(f"Unsupported Kuaishou action: {args.action}")

    if args.command == "xiaohongshu":
        if args.action == "login":
            result = await login_xiaohongshu_account(args.account, headless=args.headless)
            if not result["success"]:
                raise RuntimeError(result["message"])
            print(f"Xiaohongshu login flow completed: {result['account_file']}")
            return 0

        if args.action == "check":
            is_valid = await check_xiaohongshu_account(args.account)
            print("valid" if is_valid else "invalid")
            return 0 if is_valid else 1

        publish_strategy = (
            XIAOHONGSHU_PUBLISH_STRATEGY_SCHEDULED if args.schedule else XIAOHONGSHU_PUBLISH_STRATEGY_IMMEDIATE
        )

        if args.action == "upload-video":
            request = XiaohongshuVideoUploadRequest(
                account_name=args.account,
                video_file=args.file,
                title=args.title,
                description=args.desc,
                tags=parse_tags(args.tags),
                publish_date=args.schedule or 0,
                thumbnail_file=args.thumbnail,
                publish_strategy=publish_strategy,
                debug=args.debug,
                headless=args.headless,
            )
            await upload_xiaohongshu_video(request)
            print(f"Xiaohongshu video upload submitted: {request.video_file}")
            return 0

        if args.action == "upload-note":
            request = XiaohongshuNoteUploadRequest(
                account_name=args.account,
                image_files=parse_image_files(args.images),
                title=args.title,
                note=args.note,
                tags=parse_tags(args.tags),
                publish_date=args.schedule or 0,
                publish_strategy=publish_strategy,
                debug=args.debug,
                headless=args.headless,
            )
            await upload_xiaohongshu_note(request)
            print(f"Xiaohongshu note upload submitted: {len(request.image_files)} images")
            return 0

        raise RuntimeError(f"Unsupported Xiaohongshu action: {args.action}")

    if args.command == "bilibili":
        if args.action == "login":
            result = await login_bilibili_account(args.account)
            if not result["success"]:
                raise RuntimeError(result["message"])
            print(f"Bilibili login flow completed: {result['account_file']}")
            return 0

        if args.action == "check":
            is_valid = await check_bilibili_account(args.account)
            print("valid" if is_valid else "invalid")
            return 0 if is_valid else 1

        if args.action == "upload-video":
            request = BilibiliVideoUploadRequest(
                account_name=args.account,
                video_file=args.file,
                title=args.title,
                description=args.desc,
                tid=args.tid,
                tags=parse_tags(args.tags),
                publish_date=args.schedule or 0,
            )
            await upload_bilibili_video(request)
            print(f"Bilibili video upload submitted: {request.video_file}")
            return 0

        raise RuntimeError(f"Unsupported Bilibili action: {args.action}")

    raise RuntimeError(f"Unsupported command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return asyncio.run(dispatch(args))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
