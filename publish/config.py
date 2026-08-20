# -*- coding: utf-8 -*-
"""配置读取与解析:publish_config.ini、PublishOverrides、字段重置"""
import configparser
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from conf import BASE_DIR
from publish.constants import PUBLISH_TASK_FIELD_DEFAULTS, TITLE_LIMITS
from publish.content import resolve_path, truncate_title


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


def reset_publish_task_fields(config_file: str | Path) -> None:
    """清空一次性发布任务字段，保留账号文件和注释。"""
    config_path = Path(config_file)
    if not config_path.exists():
        return

    section_pattern = re.compile(r"^\s*\[([^\]]+)\]\s*$")
    field_pattern = re.compile(r"^(\s*([^#;=\s]+)\s*=\s*).*$")
    current_section = ""
    output_lines = []

    for line in config_path.read_text(encoding="utf-8").splitlines(keepends=True):
        newline = "\n" if line.endswith("\n") else ""
        raw_line = line[:-1] if newline else line

        section_match = section_pattern.match(raw_line)
        if section_match:
            current_section = section_match.group(1).strip().lower()
            output_lines.append(line)
            continue

        field_match = field_pattern.match(raw_line)
        if field_match:
            key = field_match.group(2).strip().lower()
            section_defaults = PUBLISH_TASK_FIELD_DEFAULTS.get(current_section, {})
            if key in section_defaults:
                output_lines.append(f"{field_match.group(1)}{section_defaults[key]}{newline}")
                continue

        output_lines.append(line)

    config_path.write_text("".join(output_lines), encoding="utf-8")


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
