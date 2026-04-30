"""Douyin uploader with config file support.

Usage:
    1. Edit douyin_config.ini to set your video/title/tags
    2. Run: python examples/upload_to_douyin.py
"""

import asyncio
import configparser
from datetime import datetime
from pathlib import Path

from conf import BASE_DIR
from uploader.douyin_uploader.main import (
    DOUYIN_PUBLISH_STRATEGY_IMMEDIATE,
    DOUYIN_PUBLISH_STRATEGY_SCHEDULED,
    DouYinNote,
    DouYinVideo,
)


def load_config():
    """Load configuration from douyin_config.ini"""
    config_path = Path(BASE_DIR) / "douyin_config.ini"

    if not config_path.exists():
        raise FileNotFoundError(
            f"配置文件不存在: {config_path}\n"
            "请先创建配置文件，可以参考以下内容:\n"
            """
[douyin]
video_file = videos/demo.mp4
title = 视频标题
tags = 标签1,标签2
publish_strategy = immediate
"""
        )

    parser = configparser.ConfigParser()
    parser.read(config_path, encoding="utf-8")

    return parser


def parse_tags(tags_str: str) -> list[str]:
    """Parse comma-separated tags into list"""
    if not tags_str or not tags_str.strip():
        return []
    return [tag.strip() for tag in tags_str.split(",") if tag.strip()]


def parse_path(path_str: str) -> Path | None:
    """Parse path string, return None if empty"""
    if not path_str or not path_str.strip():
        return None
    return Path(BASE_DIR) / path_str.strip()


def parse_bool(value: str) -> bool:
    """Parse boolean string"""
    return value.strip().lower() in ("true", "yes", "1")


def upload_video_to_douyin():
    """Upload video to Douyin based on config file"""
    config = load_config()

    # 读取配置
    account_file = parse_path(config.get("douyin", "account_file", fallback="cookies/douyin_uploader/account.json"))
    video_file = parse_path(config.get("douyin", "video_file"))
    title = config.get("douyin", "title", fallback="").strip()
    tags = parse_tags(config.get("douyin", "tags", fallback=""))
    description = config.get("douyin", "description", fallback="").strip() or title
    thumbnail_landscape = parse_path(config.get("douyin", "thumbnail_landscape", fallback=""))
    thumbnail_portrait = parse_path(config.get("douyin", "thumbnail_portrait", fallback=""))
    publish_strategy_str = config.get("douyin", "publish_strategy", fallback="immediate").strip().lower()
    publish_time_str = config.get("douyin", "publish_time", fallback="").strip()

    # 验证必要参数
    if not video_file:
        raise ValueError("配置文件中缺少 video_file 参数")
    if not video_file.exists():
        raise FileNotFoundError(f"视频文件不存在: {video_file}")
    if not title:
        raise ValueError("配置文件中缺少 title 参数")

    # 解析发布策略
    if publish_strategy_str == "scheduled":
        publish_strategy = DOUYIN_PUBLISH_STRATEGY_SCHEDULED
        if not publish_time_str:
            raise ValueError("定时发布需要设置 publish_time 参数")
        publish_date = datetime.strptime(publish_time_str, "%Y-%m-%d %H:%M")
    else:
        publish_strategy = DOUYIN_PUBLISH_STRATEGY_IMMEDIATE
        publish_date = 0

    print(f"准备上传视频:")
    print(f"  文件: {video_file}")
    print(f"  标题: {title}")
    print(f"  标签: {tags}")
    print(f"  发布策略: {publish_strategy_str}")
    if publish_strategy_str == "scheduled":
        print(f"  发布时间: {publish_time_str}")

    # 执行上传
    app = DouYinVideo(
        title=title,
        file_path=video_file,
        tags=tags,
        publish_date=publish_date,
        thumbnail_landscape_path=thumbnail_landscape or "",
        thumbnail_portrait_path=thumbnail_portrait or "",
        account_file=account_file,
        publish_strategy=publish_strategy,
    )
    asyncio.run(app.douyin_upload_video())


def upload_note_to_douyin():
    """Upload note (images) to Douyin based on config file"""
    config = load_config()

    # 读取配置
    account_file = parse_path(config.get("douyin", "account_file", fallback="cookies/douyin_uploader/account.json"))
    note_images_str = config.get("douyin", "note_images", fallback="")
    note_content = config.get("douyin", "note_content", fallback="").strip()
    note_tags = parse_tags(config.get("douyin", "note_tags", fallback=""))
    publish_strategy_str = config.get("douyin", "publish_strategy", fallback="immediate").strip().lower()
    publish_time_str = config.get("douyin", "publish_time", fallback="").strip()

    # 解析图片路径
    image_paths = [parse_path(p) for p in note_images_str.split(",") if p.strip()]
    image_paths = [p for p in image_paths if p]  # 过滤 None

    # 验证必要参数
    if not image_paths:
        raise ValueError("配置文件中缺少 note_images 参数")
    for img_path in image_paths:
        if not img_path.exists():
            raise FileNotFoundError(f"图片文件不存在: {img_path}")
    if not note_content:
        raise ValueError("配置文件中缺少 note_content 参数")

    # 解析发布策略
    if publish_strategy_str == "scheduled":
        publish_strategy = DOUYIN_PUBLISH_STRATEGY_SCHEDULED
        if not publish_time_str:
            raise ValueError("定时发布需要设置 publish_time 参数")
        publish_date = datetime.strptime(publish_time_str, "%Y-%m-%d %H:%M")
    else:
        publish_strategy = DOUYIN_PUBLISH_STRATEGY_IMMEDIATE
        publish_date = 0

    print(f"准备上传图文:")
    print(f"  图片数量: {len(image_paths)}")
    print(f"  内容: {note_content}")
    print(f"  标签: {note_tags}")

    # 执行上传
    app = DouYinNote(
        image_paths=image_paths,
        note=note_content,
        tags=note_tags,
        publish_date=publish_date,
        account_file=account_file,
        publish_strategy=publish_strategy,
    )
    asyncio.run(app.douyin_upload_note())


if __name__ == "__main__":
    config = load_config()

    # 根据配置决定上传视频还是图文
    upload_note = parse_bool(config.get("douyin", "upload_note", fallback="false"))

    if upload_note:
        upload_note_to_douyin()
    else:
        upload_video_to_douyin()
