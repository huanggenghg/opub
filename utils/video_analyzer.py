# -*- coding: utf-8 -*-
"""
视频内容分析模块
分析视频画面内容，自动生成标题和描述
"""
import json
import os
import shutil
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


def extract_frames(video_file: str, num_frames: int = 3) -> str:
    """
    从视频中提取关键帧，保存到独立文件夹

    Args:
        video_file: 视频文件路径
        num_frames: 提取帧数（默认提取开头、中间、结尾三帧）

    Returns:
        帧文件夹路径（包含提取的帧图像）
    """
    import cv2

    # 使用项目内的临时目录，便于管理和读取
    from conf import BASE_DIR
    frames_base_dir = os.path.join(BASE_DIR, 'temp_frames')
    os.makedirs(frames_base_dir, exist_ok=True)

    # 为每个视频创建唯一的子目录
    video_name = os.path.basename(video_file).rsplit('.', 1)[0]
    temp_dir = os.path.join(frames_base_dir, video_name)
    os.makedirs(temp_dir, exist_ok=True)

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

        for idx, pos in enumerate(positions[:num_frames]):
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            ret, frame = cap.read()
            if ret:
                frame_path = os.path.join(temp_dir, f"frame_{idx}.png")
                cv2.imwrite(frame_path, frame)

        return temp_dir
    finally:
        cap.release()


def extract_all_frames_parallel(
    video_files: list[str],
    progress_callback: Optional[Callable] = None
) -> dict[str, str]:
    """
    并发提取所有视频的帧

    Args:
        video_files: 视频文件路径列表
        progress_callback: 进度回调函数 (video_file, frames_dir, error)

    Returns:
        字典 {video_file: frames_dir}，失败的视频值为空字符串
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = {}

    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_video = {
            executor.submit(extract_frames, video_file): video_file
            for video_file in video_files
        }

        for future in as_completed(future_to_video):
            video_file = future_to_video[future]
            try:
                frames_dir = future.result()
                results[video_file] = frames_dir
                if progress_callback:
                    progress_callback(video_file, frames_dir, None)
            except Exception as e:
                results[video_file] = ""
                if progress_callback:
                    progress_callback(video_file, "", str(e))

    return results


def get_frame_files(frames_dir: str) -> list[str]:
    """
    获取帧文件夹中的所有帧图像路径

    Args:
        frames_dir: 帧文件夹路径

    Returns:
        帧图像路径列表，按文件名排序
    """
    if not os.path.isdir(frames_dir):
        return []

    frame_files = []
    for file in os.listdir(frames_dir):
        if file.startswith("frame_") and file.endswith(".png"):
            frame_files.append(os.path.join(frames_dir, file))

    frame_files.sort()
    return frame_files


def cleanup_frames_dir(frames_dir: str) -> None:
    """
    清理帧文件夹

    Args:
        frames_dir: 帧文件夹路径
    """
    if frames_dir and os.path.exists(frames_dir):
        shutil.rmtree(frames_dir, ignore_errors=True)