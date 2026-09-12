# -*- coding: utf-8 -*-
"""发布编排:单视频发布、整体流程、入口函数"""
import argparse
import asyncio
import os
import shutil
import sys
import webbrowser
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version as pkg_version
from typing import Any, Dict, Optional, Sequence

from publish.config import (
    PublishOverrides,
    default_account_file,
    default_params_from_overrides,
)
from publish.constants import PLATFORM_NAMES
from publish.auth import classify_login_exception
from publish.content import fill_empty_content, get_video_content, get_video_files, resolve_path
from publish.dispatch import (
    ensure_account_login,
    platform_requires_account_login,
    publish_to_platform,
)
from publish.errors import (
    EXIT_ALL_FAIL,
    EXIT_AUTH_ERROR,
    EXIT_CONFIG_ERROR,
    EXIT_ENV_ERROR,
    EXIT_LICENSE_ERROR,
    EXIT_OK,
    EXIT_PARTIAL_FAIL,
    print_error,
)
from publish.licensing import (
    print_license_error,
    require_valid_license,
    run_activation,
    show_license_status,
)
from publish.licensing.deployment import LICENSE_PURCHASE_URL
from publish.reporter import print_header, print_results, print_summary
from publish.output import record_result, record_plan, record_run, run_with_json
from publish.validation import ValidationError, validate_inputs, validate_schedule
from publish.history import HistoryError, HistoryStore
from publish.runtime import runtime_preflight


def exit_code_from_results(all_results: Dict[str, Dict[str, Any]]) -> int:
    results = [r for item_results in all_results.values() for r in item_results.values()]
    if not results:
        return EXIT_ALL_FAIL
    failures = [r for r in results if not r["success"]]
    if not failures:
        return EXIT_OK
    if len(failures) == len(results):
        if all(r.get("account_issue") for r in failures):
            return EXIT_AUTH_ERROR
        return EXIT_ALL_FAIL
    return EXIT_PARTIAL_FAIL


def _auth_failure(platform_name: str, login_error: Optional[str] = None) -> Dict[str, Any]:
    message = f"登录失败: {platform_name}"
    if login_error:
        message += f" - {login_error}"
    return {
        "success": False,
        "message": message,
        "account_issue": True,
        "error_code": "AUTH-001",
    }


def _is_safe_login_expiry(result: Dict[str, Any]) -> bool:
    return (
        result.get("success") is False
        and result.get("account_issue") is True
        and result.get("issue_type") == "login_expired"
        and result.get("safe_to_retry") is True
    )


async def publish_one_item(video_params: Dict[str, Any]) -> Dict[str, Any]:
    enabled_platforms = list(dict.fromkeys(video_params["enabled_platforms"]))
    if enabled_platforms != video_params["enabled_platforms"]:
        video_params = {**video_params, "enabled_platforms": enabled_platforms}

    print_header(video_params)

    results = {}
    total = len(enabled_platforms)
    history = video_params.get("_history")

    def save_result(platform, result, retryable=False, persist=True):
        results[platform] = result
        record_result(video_params, platform, result)
        if history and persist:
            store, run_id, index = history
            store.finish(run_id, index, platform, result, retryable=retryable)

    for i, platform in enumerate(enabled_platforms, 1):
        platform_name = PLATFORM_NAMES.get(platform, platform)
        if history:
            store, run_id, index = history
            runnable = video_params.get('_runnable_platforms')
            decision = store.claim(run_id, index, platform, allow_submit=runnable is None or platform in runnable)
            if decision['state'] != 'claimed':
                cached = {**decision['result'], 'reused': decision['state'] == 'success'}
                save_result(platform, cached, persist=False)
                print(f"[{i}/{total}] {platform_name}: {'沿用已成功结果' if cached['success'] else cached['message']}")
                continue

        if platform not in PLATFORM_NAMES:
            result = {"success": False, "message": f"未知平台: {platform}"}
            save_result(platform, result, retryable=True)
            print(f"[{i}/{total}] 发布到 {platform_name}...")
            print(f"  ❌ 失败: {result['message']}")
            continue

        account_key = f"{platform}_account"
        account_file = str(video_params["platforms"].get(account_key, "") or "").strip()
        if "," in account_file:
            account_file = ""

        if not account_file:
            default_file = default_account_file(platform)
            if default_file is None:
                result = {
                    "success": False,
                    "message": f"未配置 {platform} 账号",
                    "account_issue": True,
                    "error_code": "AUTH-002",
                }
                save_result(platform, result, retryable=True)
                print("  ❌ 失败: 未配置账号")
                continue
            print(f"  ℹ️ 未发现 {platform_name} 账号文件，将触发扫码登录: {default_file}")
            account_file = default_file

        print(f"[{i}/{total}] 发布到 {platform_name}...")
        platform_params = {
            **video_params,
            "account_file": account_file,
        }

        if platform_requires_account_login(platform):
            login_error = None
            try:
                login_ok = await ensure_account_login(platform, account_file)
            except Exception as exc:
                login_ok = False
                login_error = classify_login_exception(exc).to_result()
            if not login_ok:
                result = login_error or _auth_failure(platform_name)
                save_result(platform, result, retryable=True)
                print_error(result["error_code"], result["message"], result.get("action") or f"引导用户在弹出的浏览器中完成 {platform_name} 扫码登录后重试")
                continue

        result = await publish_to_platform(platform, platform_params)
        retryable = result.get('safe_to_retry') is True
        auth_failure_reported = False
        if _is_safe_login_expiry(result):
            login_error = None
            try:
                login_ok = await ensure_account_login(platform, account_file, force=True)
            except Exception as exc:
                login_ok = False
                login_error = classify_login_exception(exc).to_result()
            if login_ok:
                result = await publish_to_platform(platform, platform_params)
                retryable = result.get('safe_to_retry') is True
            else:
                result = login_error or _auth_failure(platform_name)
                print_error(result["error_code"], result["message"], result.get("action") or f"引导用户在弹出的浏览器中完成 {platform_name} 扫码登录后重试")
                auth_failure_reported = True

        save_result(platform, result, retryable=retryable)
        if auth_failure_reported:
            continue
        if result.get("success"):
            print("  ✅ 成功")
        else:
            print(f"  ❌ 失败: {result['message']}")

    print_results(results)
    return results


async def run_publish_with_params(params: Dict[str, Any]) -> int:
    params = {**params, "enabled_platforms": list(dict.fromkeys(params["enabled_platforms"]))}
    video_files = get_video_files(params.get("video_file", "")) if params["content_type"] == "video" else []
    try:
        validate_inputs(params, video_files)
    except ValidationError as exc:
        print_error(exc.code, str(exc), exc.action)
        return EXIT_CONFIG_ERROR

    params["images"] = [resolve_path(path) for path in params.get("images", [])]
    dry_run = params.get("dry_run", False)
    prepared = []
    if params["content_type"] == "note":
        title, desc = fill_empty_content(params["title"], params["desc"])
        if not (title and str(title).strip()):
            print_error("CFG-001", "图文发布缺少标题", "提供 --title")
            return EXIT_CONFIG_ERROR
        prepared.append({**params, "title": title, "desc": desc})
    else:
        selected = video_files[params.get("start_from", 1) - 1:]
        for video_file in selected:
            options = {"force": params.get("force", False)}
            if dry_run:
                options.update(auto_generate=False, force=False)
            title, desc = get_video_content(video_file, params["title"], params["desc"], **options)
            if not (title and str(title).strip()):
                print_error("CFG-001", f"视频 {os.path.basename(video_file)} 标题解析后为空", "提供 --title，或补充视频同名 JSON；--dry-run 不自动生成文案")
                return EXIT_CONFIG_ERROR
            prepared.append({**params, "video_file": video_file, "title": title, "desc": desc})

    if not await runtime_preflight():
        return EXIT_ENV_ERROR

    if params.get("convert_to_video"):
        from utils.image_to_video import check_moviepy_installed, convert_images_to_video_for_publish
        if not check_moviepy_installed() or not shutil.which("ffmpeg"):
            print_error("ENV-005", "图文转视频依赖不完整", "运行 opub --repair-env --with-video，并安装 ffmpeg 后重试")
            return EXIT_ENV_ERROR
        if not dry_run:
            try:
                item = prepared[0]
                video_path = convert_images_to_video_for_publish(
                    image_paths=item["images"], title=item["title"], duration=item["video_duration"],
                )
                prepared[0] = {**item, "content_type": "video", "video_file": video_path, "images": [], "convert_to_video": False}
            except Exception as exc:
                print_error("ENV-005", f"图片转视频失败: {exc}", "检查图片、ffmpeg 和磁盘空间后重试")
                return EXIT_ENV_ERROR

    if dry_run:
        record_plan(prepared)
        print(f"[opub] 检查通过：{len(prepared)} 份素材，未执行登录或发布")
        for item in prepared:
            print(f"  {item['title']} → {', '.join(item['enabled_platforms'])}")
        return EXIT_OK

    return await execute_prepared(prepared)


async def execute_prepared(items, store=None, run_id=None, runnable=None):
    store = store or HistoryStore()
    if run_id is None:
        for item in items:
            accounts = dict(item.get('platforms', {}))
            for platform in item['enabled_platforms']:
                key = f'{platform}_account'
                value = str(accounts.get(key, '') or '')
                accounts[key] = resolve_path(value) if value and ',' not in value else default_account_file(platform)
            item['platforms'] = accounts
        run_id = store.create(items)
        mode = 'publish'
    else:
        mode = 'resume'
    record_run(run_id, mode)
    print(f"[opub] 任务编号: {run_id}；恢复命令: opub --resume {run_id}")
    all_results = {}
    for index, item in enumerate(items):
        eligible = None if runnable is None else {p for i, p in runnable if i == index}
        all_results[str(index)] = await publish_one_item({
            **item, '_history': (store, run_id, index), '_runnable_platforms': eligible,
        })
    print_summary(all_results)
    return exit_code_from_results(all_results)


async def resume_publish(run_id):
    record_run(run_id, 'resume')
    store = HistoryStore()
    items = store.load(run_id)
    runnable = store.runnable_entries(run_id)
    try:
        for index, item in enumerate(items):
            platforms = [p for p in item['enabled_platforms'] if (index, p) in runnable]
            if platforms:
                validate_schedule({**item, 'enabled_platforms': platforms})
    except ValidationError as exc:
        print_error(exc.code, str(exc), exc.action)
        return EXIT_CONFIG_ERROR
    if runnable and not await runtime_preflight():
        return EXIT_ENV_ERROR
    return await execute_prepared(items, store, run_id, runnable)


async def run_publish(overrides: Optional[PublishOverrides] = None) -> int:
    overrides = overrides or PublishOverrides()

    if not overrides.platforms:
        print_error("CFG-002", "未指定启用平台", "提供 --platforms，逗号分隔平台标识（见 opub --help）")
        return EXIT_CONFIG_ERROR
    if overrides.note and overrides.video:
        print_error("CFG-001", "--note 与 --video 互斥", "二选一：图文用 --note --images，视频用 --video")
        return EXIT_CONFIG_ERROR
    if not overrides.note and not overrides.video:
        print_error("CFG-001", "缺少发布素材", "提供 --video（视频发布）或 --note --images（图文发布）")
        return EXIT_CONFIG_ERROR

    params = default_params_from_overrides(overrides)
    return await run_publish_with_params(params)


def run_publish_sync(overrides: Optional[PublishOverrides] = None) -> int:
    return asyncio.run(run_publish(overrides))


SCHEDULE_FORMAT = "%Y-%m-%d %H:%M"
_PUBLISH_OPTION_NAMES = frozenset(
    {
        "--platforms",
        "--video",
        "--note",
        "--images",
        "--convert-to-video",
        "--video-duration",
        "--title",
        "--desc",
        "--tags",
        "--schedule",
        "--start-from",
        "--force",
        "--dry-run",
    }
)


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
        prog="opub",
        description="把视频/图文一键发布到抖音/小红书/快手/微博/B站/视频号/百家号。必填 --platforms，素材提供 --video（视频）或 --note --images（图文）。",
        allow_abbrev=False,
    )
    try:
        _version = pkg_version("opub")
    except PackageNotFoundError:
        _version = "0.0.0.dev0"
    parser.add_argument("--version", action="version", version=f"opub {_version}")
    license_group = parser.add_mutually_exclusive_group()
    license_group.add_argument("--license-status", action="store_true", help="检查本机许可证状态")
    license_group.add_argument("--activate", action="store_true", help="购买或恢复本机永久许可证")
    license_group.add_argument("--repair-env", action="store_true", help="修复当前解释器中的依赖并安装 Chromium（不执行发布）")
    license_group.add_argument("--resume", metavar="RUN_ID", help="恢复已有任务：跳过成功项，保护结果未确认的项")
    parser.add_argument("--with-video", action="store_true", help="与 --repair-env 一起使用，同时安装图文转视频依赖")
    parser.add_argument("--code", default=None, help="爱发电发放的激活码，仅与 --activate 一起使用")
    parser.add_argument("--platforms", default=None, help="启用的平台，逗号分隔（必填）")
    parser.add_argument("--video", default=None, help="视频文件或目录路径")
    parser.add_argument("--note", action="store_true", help="图文模式：以 --images 的图片发布图文")
    parser.add_argument("--images", default=None, help="图文图片路径，逗号分隔（图文模式必填）")
    parser.add_argument("--convert-to-video", action="store_true", help="图文转视频后发布（仅 --note 模式生效）")
    parser.add_argument("--video-duration", type=float, default=5, help="图转视频每张图片时长（秒，默认 5）")
    parser.add_argument("--title", default=None, help="标题（由用户提供；仅用户明确同意自动生成时可留空，失败报 CFG-001）")
    parser.add_argument("--desc", default=None, help="描述（由用户提供；仅用户明确同意自动生成时可留空）")
    parser.add_argument("--tags", default=None, help="话题标签，逗号分隔")
    parser.add_argument("--schedule", type=_schedule_value, default=None, help=f"定时发布时间，格式 {schedule_help}")
    parser.add_argument("--start-from", type=int, default=None, help="新任务的目录起始序号，1 起；恢复已有任务请用 --resume")
    parser.add_argument("--force", action="store_true", help="强制重新生成视频配置")
    parser.add_argument("--output", choices=("text", "json"), default="text", help="结果输出格式（默认 text；json 模式过程日志写入 stderr）")
    parser.add_argument("--dry-run", action="store_true", help="只检查输入和环境，输出计划，不登录、不发布或生成素材")
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
        note=args.note,
        images=args.images,
        convert_to_video=args.convert_to_video,
        video_duration=args.video_duration,
        dry_run=args.dry_run,
    )


def _contains_explicit_option(argv: Sequence[str], option_names: frozenset[str]) -> bool:
    return any(argument.split("=", 1)[0] in option_names for argument in argv)


def _print_license_purchase_guidance() -> None:
    print(
        "[opub] 无需提前注册爱发电：请使用你自己的手机号或邮箱完成验证，"
        "首次购买时爱发电会自动生成账号。"
    )
    print(
        "[opub] 付款后复制爱发电发放的激活码；"
        "请勿向 Agent 提供验证码或账号密码。"
    )


def _open_license_purchase_page() -> None:
    try:
        opened = bool(webbrowser.open(LICENSE_PURCHASE_URL))
    except Exception:
        opened = False
    except KeyboardInterrupt:
        opened = False
    if not opened:
        print(f"[opub] 无法自动打开购买页，请手动打开: {LICENSE_PURCHASE_URL}")
    _print_license_purchase_guidance()


def _stdin_is_interactive() -> bool:
    try:
        return bool(sys.stdin.isatty())
    except (EOFError, OSError, ValueError):
        return False
    except KeyboardInterrupt:
        return False


def _read_activation_code() -> str:
    try:
        return input("请输入爱发电发放的激活码: ").strip()
    except (EOFError, OSError):
        return ""
    except KeyboardInterrupt:
        return ""


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    arguments = list(argv) if argv is not None else sys.argv[1:]
    args = parser.parse_args(arguments)
    if args.dry_run:
        record_plan([])
    if args.resume and _contains_explicit_option(arguments, _PUBLISH_OPTION_NAMES):
        parser.error("恢复任务不能混入新的发布参数；要更换素材或文案请创建新任务")
    if args.with_video and not args.repair_env:
        parser.error("--with-video 只能与 --repair-env 一起使用")
    if args.repair_env:
        if args.code is not None or _contains_explicit_option(arguments, _PUBLISH_OPTION_NAMES):
            parser.error("环境修复不能与发布参数或激活码一起使用")
        from publish.runtime import repair_environment

        if repair_environment(with_video=args.with_video):
            print("[opub] 环境修复完成")
            return EXIT_OK
        return EXIT_ENV_ERROR
    if args.code is not None and not args.activate:
        parser.error("--code 只能与 --activate 一起使用")
    if (args.activate or args.license_status) and _contains_explicit_option(
        arguments, _PUBLISH_OPTION_NAMES
    ):
        parser.error("许可命令不能与发布参数一起使用")
    if args.license_status:
        return show_license_status()
    if args.activate:
        if args.code is not None:
            return run_activation(args.code)

        _open_license_purchase_page()
        activation_code = _read_activation_code() if _stdin_is_interactive() else ""
        if not activation_code:
            print_error(
                "LIC-001",
                "尚未提供激活码",
                "付款取得激活码后运行 opub --activate --code OPUB0-你的激活码",
            )
            return EXIT_LICENSE_ERROR
        return run_activation(activation_code)

    if not args.dry_run:
        valid, code = require_valid_license()
        if not valid:
            print_license_error(code or "LIC-002")
            return EXIT_LICENSE_ERROR

    try:
        if args.resume:
            return asyncio.run(resume_publish(args.resume))
        return asyncio.run(run_publish(_build_overrides(args)))
    except HistoryError as exc:
        print_error(exc.code, str(exc), exc.action)
        return EXIT_ALL_FAIL
    except Exception as exc:
        print_error("RUN-001", f"运行时异常: {exc}", "将以上错误信息反馈给用户；重试前请先检查配置与环境")
        return EXIT_ALL_FAIL


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = list(argv) if argv is not None else sys.argv[1:]
    # A small preliminary parser selects output even when the full parser fails.
    output_parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False, exit_on_error=False)
    output_parser.add_argument("--output", default="text")
    output_args = argparse.Namespace(output="text")
    try:
        output_args, _ = output_parser.parse_known_args(arguments, namespace=output_args)
    except argparse.ArgumentError:
        # Preserve an earlier valid mode; the full parser emits the actual error.
        pass
    if output_args.output == "json" and not any(a in {"--help", "-h", "--version"} for a in arguments):
        return run_with_json(lambda: _main(arguments))
    return _main(arguments)
