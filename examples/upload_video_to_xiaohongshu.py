"""
Xiaohongshu uploader with config file support.

Usage:
    1. Edit xiaohongshu_config.ini to set your video/title/tags
    2. Run: python examples/upload_video_to_xiaohongshu.py
"""

import asyncio
import configparser
from datetime import datetime
from pathlib import Path

from conf import BASE_DIR
from uploader.xiaohongshu_uploader.main import (
    XIAOHONGSHU_PUBLISH_STRATEGY_IMMEDIATE,
    XIAOHONGSHU_PUBLISH_STRATEGY_SCHEDULED,
    XiaoHongShuNote,
    XiaoHongShuVideo,
)


def load_config():
    """Load configuration from xiaohongshu_config.ini"""
    config_path = Path(BASE_DIR) / "xiaohongshu_config.ini"

    if not config_path.exists():
        raise FileNotFoundError(
            f"配置文件不存在: {config_path}\n"
            "请先创建配置文件，可以参考以下内容:\n"
            """
[xiaohongshu]
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


def parse_multiline(text: str) -> str:
    """Parse multiline text, support \\n as line break"""
    if not text:
        return ""
    # 支持 \n 作为换行符
    return text.replace("\\n", "\n")


def upload_video_to_xiaohongshu():
    """Upload video to Xiaohongshu based on config file"""
    config = load_config()

    # 读取配置
    account_file = parse_path(config.get("xiaohongshu", "account_file", fallback="cookies/xiaohongshu_uploader/account.json"))
    video_file = parse_path(config.get("xiaohongshu", "video_file"))
    title = config.get("xiaohongshu", "title", fallback="").strip()
    desc = parse_multiline(config.get("xiaohongshu", "desc", fallback="").strip())
    tags = parse_tags(config.get("xiaohongshu", "tags", fallback=""))
    thumbnail = parse_path(config.get("xiaohongshu", "thumbnail", fallback=""))
    publish_strategy_str = config.get("xiaohongshu", "publish_strategy", fallback="immediate").strip().lower()
    publish_time_str = config.get("xiaohongshu", "publish_time", fallback="").strip()

    # 验证必要参数
    if not video_file:
        raise ValueError("配置文件中缺少 video_file 参数")
    if not video_file.exists():
        raise FileNotFoundError(f"视频文件不存在: {video_file}")
    if not title:
        raise ValueError("配置文件中缺少 title 参数")

    # 解析发布策略
    if publish_strategy_str == "scheduled":
        publish_strategy = XIAOHONGSHU_PUBLISH_STRATEGY_SCHEDULED
        if not publish_time_str:
            raise ValueError("定时发布需要设置 publish_time 参数")
        publish_date = datetime.strptime(publish_time_str, "%Y-%m-%d %H:%M")
    else:
        publish_strategy = XIAOHONGSHU_PUBLISH_STRATEGY_IMMEDIATE
        publish_date = 0

    print(f"准备上传视频到小红书:")
    print(f"  文件: {video_file}")
    print(f"  标题: {title}")
    print(f"  描述: {desc}")
    print(f"  标签: {tags}")
    print(f"  发布策略: {publish_strategy_str}")
    if publish_strategy_str == "scheduled":
        print(f"  发布时间: {publish_time_str}")

    # 执行上传
    app = XiaoHongShuVideo(
        title=title,
        file_path=str(video_file),
        desc=desc,
        tags=tags,
        publish_date=publish_date,
        account_file=str(account_file),
        publish_strategy=publish_strategy,
        thumbnail_path=str(thumbnail) if thumbnail else None,
    )
    result = asyncio.run(app.xiaohongshu_upload_video())
    print(f"\n上传结果: {result}")


def upload_note_to_xiaohongshu():
    """Upload note (images) to Xiaohongshu based on config file"""
    config = load_config()

    # 读取配置
    account_file = parse_path(config.get("xiaohongshu", "account_file", fallback="cookies/xiaohongshu_uploader/account.json"))
    note_images_str = config.get("xiaohongshu", "note_images", fallback="")
    note_title = config.get("xiaohongshu", "note_title", fallback="").strip()
    note_content = parse_multiline(config.get("xiaohongshu", "note_content", fallback="").strip())
    note_tags = parse_tags(config.get("xiaohongshu", "note_tags", fallback=""))
    publish_strategy_str = config.get("xiaohongshu", "publish_strategy", fallback="immediate").strip().lower()
    publish_time_str = config.get("xiaohongshu", "publish_time", fallback="").strip()

    # 解析图片路径
    image_paths = [parse_path(p) for p in note_images_str.split(",") if p.strip()]
    image_paths = [p for p in image_paths if p]  # 过滤 None

    # 验证必要参数
    if not image_paths:
        raise ValueError("配置文件中缺少 note_images 参数")
    for img_path in image_paths:
        if not img_path.exists():
            raise FileNotFoundError(f"图片文件不存在: {img_path}")
    if not note_title:
        raise ValueError("配置文件中缺少 note_title 参数")

    # 解析发布策略
    if publish_strategy_str == "scheduled":
        publish_strategy = XIAOHONGSHU_PUBLISH_STRATEGY_SCHEDULED
        if not publish_time_str:
            raise ValueError("定时发布需要设置 publish_time 参数")
        publish_date = datetime.strptime(publish_time_str, "%Y-%m-%d %H:%M")
    else:
        publish_strategy = XIAOHONGSHU_PUBLISH_STRATEGY_IMMEDIATE
        publish_date = 0

    print(f"准备上传图文到小红书:")
    print(f"  图片数量: {len(image_paths)}")
    print(f"  标题: {note_title}")
    print(f"  内容: {note_content}")
    print(f"  标签: {note_tags}")

    # 执行上传
    app = XiaoHongShuNote(
        image_paths=[str(p) for p in image_paths],
        note=note_content,
        tags=note_tags,
        publish_date=publish_date,
        account_file=str(account_file),
        publish_strategy=publish_strategy,
        title=note_title,
    )
    result = asyncio.run(app.xiaohongshu_upload_note())
    print(f"\n上传结果: {result}")


if __name__ == "__main__":
    config = load_config()

    # 根据配置决定上传视频还是图文
    upload_note = parse_bool(config.get("xiaohongshu", "upload_note", fallback="false"))

    if upload_note:
        upload_note_to_xiaohongshu()
    else:
        upload_video_to_xiaohongshu()
