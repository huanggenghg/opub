# -*- coding: utf-8 -*-
"""平台分发:登录校验与各平台发布实现"""
import importlib
import os
from typing import TypedDict

from publish.constants import PLATFORM_NAMES, TITLE_LIMITS
from publish.content import resolve_path, truncate_title


class PlatformResult(TypedDict):
    success: bool
    message: str


class PlatformResultExtras(PlatformResult, total=False):
    share_link: str
    video_link: str
    account_issue: bool
    issue_type: str


_PLATFORM_LOGIN = {
    "douyin":      ("uploader.douyin_uploader.main",      "cookie_auth", "douyin_setup"),
    "xiaohongshu": ("uploader.xiaohongshu_uploader.main", "cookie_auth", "xiaohongshu_setup"),
    "kuaishou":    ("uploader.ks_uploader.main",          "cookie_auth", "ks_setup"),
    "tencent":     ("uploader.tencent_uploader.main",     "cookie_auth", "tencent_setup"),
    "baijiahao":   ("uploader.baijiahao_uploader.main",   "cookie_auth", "baijiahao_setup"),
    "bilibili":    ("uploader.bilibili_uploader.main",    "cookie_auth", "bilibili_setup"),
    "weibo":       ("uploader.weibo_uploader.main",       "cookie_auth", "weibo_setup"),
}


async def ensure_login(platform: str, account_file: str) -> bool:
    """确保平台已登录，未登录则触发登录流程"""
    entry = _PLATFORM_LOGIN.get(platform)
    if entry is None:
        return False

    module_path, check_name, setup_name = entry
    module = importlib.import_module(module_path)

    if os.path.exists(account_file):
        check_func = getattr(module, check_name)
        if await check_func(account_file):
            return True

    setup_func = getattr(module, setup_name)
    return await setup_func(account_file, handle=True)


async def ensure_account_login(platform: str, account_file: str) -> bool:
    resolved_account = resolve_path(account_file)
    return await ensure_login(platform, resolved_account)


def platform_requires_account_login(platform: str) -> bool:
    return platform in _PLATFORM_LOGIN


async def publish_to_douyin(params: dict) -> dict:
    """发布到抖音"""
    from uploader.douyin_uploader.main import DouYinVideo, DouYinNote, DouyinPublishRestrictedError

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
    except DouyinPublishRestrictedError as exc:
        return {
            "success": False,
            "message": f"账号被限制发布: {exc.toast_text}",
            "account_issue": True,
            "issue_type": "publish_restricted",
        }
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
    from utils.excel_writer import write_video_link

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

        result = await uploader.main()
        video_link = result.get("video_link", "") if result else ""

        response = {"success": True, "message": "发布成功"}
        if video_link:
            response["video_link"] = video_link
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


async def publish_to_bilibili(params: dict) -> dict:
    """发布到 B站 (via biliup CLI)"""
    from uploader.bilibili_uploader.main import upload as biliup_upload

    account_file = resolve_path(params["account_file"])

    title = truncate_title(params["title"], "bilibili")
    tags = params["tags"]
    content_type = params["content_type"]

    if content_type != "video":
        return {"success": False, "message": "B站暂只支持视频发布"}

    video_file = resolve_path(params["video_file"])
    if not video_file or not os.path.exists(video_file):
        return {"success": False, "message": f"视频文件不存在: {video_file}"}

    try:
        result = await biliup_upload(
            account_file=account_file,
            video_file=video_file,
            title=title,
            desc=params["desc"],
            tags=tags,
        )
        return result
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


_PUBLISH_DISPATCH = {
    "douyin":      publish_to_douyin,
    "xiaohongshu": publish_to_xiaohongshu,
    "kuaishou":    publish_to_kuaishou,
    "tencent":     publish_to_tencent,
    "baijiahao":   publish_to_baijiahao,
    "bilibili":    publish_to_bilibili,
    "weibo":       publish_to_weibo,
}


async def publish_to_platform(platform: str, params: dict) -> dict:
    """发布到指定平台"""
    handler = _PUBLISH_DISPATCH.get(platform)
    if handler is not None:
        return await handler(params)
    if platform == "tk":
        return {"success": False, "message": "TikTok平台暂未实现"}
    return {"success": False, "message": f"未知平台: {platform}"}
