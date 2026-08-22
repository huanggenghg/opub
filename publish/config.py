# -*- coding: utf-8 -*-
"""发布参数构建:PublishOverrides 是唯一参数源,cookies/ 账号自动发现"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from conf import BASE_DIR


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
    note: bool = False
    images: Optional[str] = None
    convert_to_video: bool = False
    video_duration: float = 5.0


def _split_csv(value: Optional[str]) -> list:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


PLATFORM_ACCOUNT_SUBDIRS = {
    "douyin": "douyin_uploader",
    "kuaishou": "ks_uploader",
    "xiaohongshu": "xiaohongshu_uploader",
    "weibo": "weibo_uploader",
    "tencent": "tencent_uploader",
    "baijiahao": "baijiahao_uploader",
    "bilibili": "bilibili_uploader",
    "tk": "tk_uploader",
}


def default_account_file(platform: str) -> Optional[str]:
    """未发现账号文件时的默认保存路径,登录流程会把扫码结果写到这里"""
    subdir = PLATFORM_ACCOUNT_SUBDIRS.get(platform)
    if subdir is None:
        return None
    account_dir = BASE_DIR / "cookies" / subdir
    account_dir.mkdir(parents=True, exist_ok=True)
    return str(account_dir / "account.json")


def _discover_account_files() -> Dict[str, str]:
    cookies_dir = BASE_DIR / "cookies"
    platform_prefixes = {
        "douyin": "douyin_",
        "kuaishou": "kuaishou_",
        "xiaohongshu": "xiaohongshu_",
        "weibo": "weibo_",
        "tencent": "tencent_",
        "baijiahao": "baijiahao_",
        "bilibili": "bilibili_",
        "tk": "tk_",
    }

    platforms = {}
    for platform, prefix in platform_prefixes.items():
        flat_files = sorted(cookies_dir.glob(f"{prefix}*.json"))
        subdir = PLATFORM_ACCOUNT_SUBDIRS[platform]
        subdir_files = sorted((cookies_dir / subdir).glob("*.json")) if (cookies_dir / subdir).exists() else []
        account_files = flat_files + [file for file in subdir_files if file not in flat_files]
        if account_files:
            rel_paths = [str(file.relative_to(BASE_DIR)) for file in account_files]
            platforms[f"{platform}_account"] = ", ".join(rel_paths)
    return platforms


def default_params_from_overrides(overrides: Optional[PublishOverrides] = None) -> Dict[str, Any]:
    overrides = overrides or PublishOverrides()
    params: Dict[str, Any] = {
        "content_type": "note" if overrides.note else "video",
        "title": overrides.title or "",
        "desc": overrides.desc or "",
        "tags": _split_csv(overrides.tags),
        "video_file": overrides.video or "",
        "images": _split_csv(overrides.images),
        "publish_strategy": "scheduled" if overrides.schedule else "immediate",
        "publish_time": overrides.schedule,
        "enabled_platforms": _split_csv(overrides.platforms),
        "platforms": _discover_account_files(),
        "convert_to_video": overrides.convert_to_video,
        "video_duration": overrides.video_duration,
        "start_from": overrides.start_from if overrides.start_from else 1,
    }
    if overrides.force:
        params["force"] = True
    return params
