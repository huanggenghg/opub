# -*- coding: utf-8 -*-
"""
视频内容分析模块
分析视频画面内容，自动生成标题和描述
"""
import json
import os
from datetime import datetime
from typing import Callable, Optional

# 视频文件扩展名
VIDEO_EXTENSIONS = ['.mp4', '.mov', '.mkv', '.avi', '.flv', '.mpeg', '.ogg', '.vob', '.webm', '.wmv', '.rmvb']


def get_video_files(directory: str) -> list[str]:
    """
    获取目录下所有视频文件

    Args:
        directory: 视频目录路径

    Returns:
        视频文件路径列表（按文件名排序）
    """
    if not os.path.isdir(directory):
        return []

    video_files = []
    for file in os.listdir(directory):
        file_lower = file.lower()
        if any(file_lower.endswith(ext) for ext in VIDEO_EXTENSIONS):
            video_files.append(os.path.join(directory, file))

    video_files.sort()
    return video_files


def get_config_file_path(video_file: str) -> str:
    """
    获取视频对应的配置文件路径

    Args:
        video_file: 视频文件路径

    Returns:
        配置文件路径（同名 .json 文件）
    """
    return video_file.rsplit('.', 1)[0] + '.json'


def save_video_config(video_file: str, title: str, desc: str) -> str:
    """
    保存视频配置到 JSON 文件

    Args:
        video_file: 视频文件路径
        title: 生成的标题
        desc: 生成的描述

    Returns:
        配置文件路径
    """
    config_file = get_config_file_path(video_file)
    config_data = {
        "title": title,
        "desc": desc,
        "generated_at": datetime.now().isoformat(),
        "video_file": os.path.basename(video_file)
    }

    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)

    return config_file


def load_video_config(video_file: str) -> Optional[dict]:
    """
    加载视频配置文件

    Args:
        video_file: 视频文件路径

    Returns:
        配置数据字典，如果不存在则返回 None
    """
    config_file = get_config_file_path(video_file)
    if not os.path.exists(config_file):
        return None

    with open(config_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def config_exists(video_file: str) -> bool:
    """
    检查视频配置文件是否已存在

    Args:
        video_file: 视频文件路径

    Returns:
        是否存在配置文件
    """
    return os.path.exists(get_config_file_path(video_file))


def extract_frames(video_file: str, num_frames: int = 3) -> list[str]:
    """
    从视频中提取关键帧

    Args:
        video_file: 视频文件路径
        num_frames: 提取帧数（默认提取开头、中间、结尾三帧）

    Returns:
        帧图像文件路径列表（临时文件）
    """
    import cv2
    import tempfile

    # 创建临时目录存放帧图像
    temp_dir = tempfile.mkdtemp(prefix='video_frames_')

    cap = cv2.VideoCapture(video_file)
    try:
        if not cap.isOpened():
            raise RuntimeError(f"无法打开视频文件: {video_file}")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            raise RuntimeError(f"视频文件无有效帧: {video_file}")

        # 计算提取帧的位置
        if total_frames <= num_frames:
            positions = list(range(total_frames))
        else:
            # 提取开头、中间、结尾帧
            positions = [
                0,  # 开头
                total_frames // 2,  # 中间
                total_frames - 1  # 结尾
            ]
            # 如果需要更多帧，均匀分布
            if num_frames > 3:
                step = total_frames // num_frames
                positions = [i * step for i in range(num_frames)]

        frame_paths = []
        for idx, pos in enumerate(positions[:num_frames]):
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            ret, frame = cap.read()
            if ret:
                frame_path = os.path.join(temp_dir, f"frame_{idx}.png")
                cv2.imwrite(frame_path, frame)
                frame_paths.append(frame_path)

        return frame_paths
    finally:
        cap.release()


def analyze_video_content(video_file: str, frame_paths: list[str]) -> tuple[str, str]:
    """
    分析视频内容生成标题和描述

    注意：此函数需要由 Claude Code 在执行时直接分析帧图像
    因为 Claude Code 具有多模态能力，可以直接读取图像

    Args:
        video_file: 视频文件路径
        frame_paths: 提取的帧图像路径列表

    Returns:
        (title, desc) 元组
    """
    # 此函数在 Claude Code 执行环境中会被覆盖
    # Claude Code 会直接读取帧图像并分析
    # 这里提供一个默认实现，返回基于文件名的简单标题
    basename = os.path.basename(video_file)
    name_without_ext = basename.rsplit('.', 1)[0]

    title = f"{name_without_ext} - 精彩内容分享"
    desc = f"这是一个关于{name_without_ext}的视频内容，欢迎观看。"

    return title, desc


def generate_video_configs(
    directory: str,
    force: bool = False,
    progress_callback: Optional[Callable] = None
) -> dict:
    """
    批量生成视频配置文件

    Args:
        directory: 视频目录路径
        force: 是否强制覆盖已存在的配置文件
        progress_callback: 进度回调函数 (current, total, video_file, status)

    Returns:
        生成结果统计 {"success": int, "skip": int, "error": int, "files": list}
    """
    video_files = get_video_files(directory)
    if not video_files:
        return {"success": 0, "skip": 0, "error": 0, "files": [], "message": "未找到视频文件"}

    results = {
        "success": 0,
        "skip": 0,
        "error": 0,
        "files": [],
        "errors": []
    }

    total = len(video_files)
    for idx, video_file in enumerate(video_files, 1):
        basename = os.path.basename(video_file)

        # 检查是否已存在配置文件
        if not force and config_exists(video_file):
            results["skip"] += 1
            if progress_callback:
                progress_callback(idx, total, basename, "skip")
            continue

        frame_paths = []
        try:
            # 提取关键帧
            frame_paths = extract_frames(video_file, num_frames=3)

            # 分析内容（此步骤需要 Claude Code 多模态能力）
            title, desc = analyze_video_content(video_file, frame_paths)

            # 保存配置
            config_file = save_video_config(video_file, title, desc)
            results["success"] += 1
            results["files"].append({
                "video": basename,
                "config": os.path.basename(config_file),
                "title": title
            })

            if progress_callback:
                progress_callback(idx, total, basename, "success")

        except Exception as e:
            results["error"] += 1
            results["errors"].append({"video": basename, "error": str(e)})
            if progress_callback:
                progress_callback(idx, total, basename, f"error: {str(e)}")
        finally:
            # 清理临时帧文件和目录
            import shutil
            for frame_path in frame_paths:
                if os.path.exists(frame_path):
                    os.remove(frame_path)
            # 清理临时目录
            temp_dir = os.path.dirname(frame_paths[0]) if frame_paths else ""
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

    return results
