# -*- coding: utf-8 -*-
"""内容处理:模板加载、标题/描述填充、视频内容解析、路径解析"""
import json
import os
import random
from pathlib import Path

from conf import BASE_DIR
from publish.constants import TITLE_LIMITS

# 内容模板文件路径(原 publish_all.py 位于仓库根,现 publish/content.py
# 深一层,用 parent.parent 回到仓库根以保持解析路径不变)
CONTENT_TEMPLATES_FILE = Path(__file__).resolve().parent.parent / "templates" / "content_templates.json"


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
    0. publish_config.ini 显式指定的 title/desc（最高优先，不调 GLM-4V API）
    1. 视频同名的 JSON 配置文件
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

    # 0. 最高优先：publish_config.ini 显式指定的 title/desc
    # 用户在配置文件里填了就用用户的，避免触发 GLM-4V API 调用
    if (default_title and default_title.strip()) or (default_desc and default_desc.strip()):
        print(f"[AUTO] 使用 publish_config.ini 配置: {default_title}")
        return default_title, default_desc

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
