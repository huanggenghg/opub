# -*- coding: utf-8 -*-
"""发布编排:单视频发布、整体流程、入口函数"""
import argparse
import asyncio
import os
import sys
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from conf import BASE_DIR
from publish.config import (
    PublishOverrides,
    apply_overrides,
    default_params_from_overrides,
    parse_config,
    read_config,
    reset_publish_task_fields,
)
from publish.constants import PLATFORM_NAMES
from publish.content import fill_empty_content, get_video_content, get_video_files
from publish.dispatch import (
    ensure_account_login,
    platform_requires_account_login,
    publish_to_platform,
)
from publish.errors import EXIT_CONFIG_ERROR, print_error
from publish.reporter import print_header, print_results, print_summary
from publish.runtime import runtime_preflight


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

            if platform_requires_account_login(platform):
                login_error = None
                try:
                    login_ok = await ensure_account_login(platform, account_file)
                except Exception as exc:
                    login_ok = False
                    login_error = str(exc) or exc.__class__.__name__
                if not login_ok:
                    msg = f"登录失败: {platform_name}"
                    if login_error:
                        msg += f" - {login_error}"
                    results[result_key] = {
                        "success": False,
                        "message": msg,
                        "account_issue": True,
                        "issue_type": "login_failed",
                    }
                    print(f"  ❌ 失败: {msg}")
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
        print_error("CFG-002", "未配置启用平台", "在 publish_config.ini [platforms] enabled= 设置，或使用 --platforms 覆盖")
        return EXIT_CONFIG_ERROR

    # 注意：标题为空时，会在视频处理流程中自动生成或使用模板填充
    # 不在此处检查标题，让 get_video_content() 处理

    # 处理图文转视频
    if params["content_type"] == "note" and params["convert_to_video"]:
        if not params["images"]:
            print_error("CFG-004", "图文转视频需要提供图片", "在 publish_config.ini [common] images= 设置图片路径（英文逗号分隔）")
            return EXIT_CONFIG_ERROR

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
            print_error("ENV-005", f"图片转视频失败: {e}", "安装 ffmpeg 后重试（macOS: brew install ffmpeg; Ubuntu: sudo apt-get install ffmpeg）")
            return 11  # ENV 错误，Task 4 会替换为 EXIT_ENV_ERROR 常量

    # 图文模式(不转视频):不依赖 video_file,直接以 images 发布
    if params["content_type"] == "note":
        if not params["images"]:
            print_error("CFG-004", "图文模式需要提供图片", "在 publish_config.ini [common] images= 设置图片路径（英文逗号分隔）")
            return EXIT_CONFIG_ERROR

        if not await runtime_preflight():
            print("❌ 错误: 运行环境检查失败")
            return 1

        title, desc = fill_empty_content(params["title"], params["desc"])
        note_params = {**params, "title": title, "desc": desc}
        print(f"\n========== 图文发布 ==========")
        print(f"标题: {title}")
        if params["tags"]:
            print(f"标签: {params['tags']}")
        print(f"图片数: {len(params['images'])}")
        print(f"启用平台: {', '.join(params['enabled_platforms'])}\n")

        all_results = {"note": await publish_one_item(note_params)}
        print_summary(all_results)
        fail_count = sum(1 for results in all_results.values() for result in results.values() if not result["success"])
        return 0 if fail_count == 0 else 1

    # 获取视频文件列表
    video_files = get_video_files(params["video_file"])
    if not video_files:
        print_error("CFG-003", f"未找到视频文件: {params['video_file']}", "检查 [common] video_file= 路径或使用 --video 覆盖")
        return EXIT_CONFIG_ERROR

    if not await runtime_preflight():
        print_error("ENV-004", "运行环境检查失败", "按上方 ENV 错误码中的建议命令安装后重试")
        return 11  # Task 4 替换为 EXIT_ENV_ERROR

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
    print_summary(all_results)
    fail_count = sum(1 for results in all_results.values() for result in results.values() if not result["success"])
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
        reset_task_fields_after_run = True
    else:
        if overrides is None or overrides.platforms is None or overrides.video is None:
            print_error("CFG-001", f"配置文件不存在: {config_path}", "提供 --config 指定配置文件，或同时指定 --platforms 和 --video")
            return EXIT_CONFIG_ERROR
        params = default_params_from_overrides()
        reset_task_fields_after_run = False

    params = apply_overrides(params, overrides)
    try:
        return await run_publish_with_params(params)
    finally:
        if reset_task_fields_after_run:
            reset_publish_task_fields(config_path)


def run_publish_sync(
    config_file: str = "publish_config.ini",
    overrides: Optional[PublishOverrides] = None,
) -> int:
    return asyncio.run(run_publish(config_file, overrides))


SCHEDULE_FORMAT = "%Y-%m-%d %H:%M"


def _schedule_value(value: str) -> datetime:
    try:
        return datetime.strptime(value, SCHEDULE_FORMAT)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid schedule '{value}'. Expected format: {SCHEDULE_FORMAT}"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    schedule_help = SCHEDULE_FORMAT.replace("%", "%%")
    parser = argparse.ArgumentParser(
        prog="hgsau",
        description="CLI for social-auto-upload.",
    )
    try:
        _version = pkg_version("hgsau")
    except PackageNotFoundError:
        _version = "0.0.0.dev0"
    parser.add_argument("--version", action="version", version=f"hgsau {_version}")
    parser.add_argument("--config", default="publish_config.ini", help="Config file path (default: publish_config.ini)")
    parser.add_argument("--platforms", default=None, help="Override enabled platforms, comma-separated")
    parser.add_argument("--video", default=None, help="Override video file/directory path")
    parser.add_argument("--title", default=None, help="Override title")
    parser.add_argument("--desc", default=None, help="Override description")
    parser.add_argument("--tags", default=None, help="Override tags, comma-separated")
    parser.add_argument("--schedule", type=_schedule_value, default=None, help=f"Override schedule time in {schedule_help}")
    parser.add_argument("--start-from", type=int, default=None, help="Start from video index (1-based)")
    parser.add_argument("--force", action="store_true", help="Force regenerate video config")
    return parser


def _build_overrides(args: argparse.Namespace) -> PublishOverrides:
    return PublishOverrides(
        platforms=args.platforms,
        video=args.video,
        title=args.title,
        desc=args.desc,
        tags=args.tags,
        schedule=args.schedule,
        start_from=args.start_from,
        force=args.force,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return asyncio.run(run_publish(args.config, _build_overrides(args)))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
