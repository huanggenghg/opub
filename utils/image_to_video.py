# -*- coding: utf-8 -*-
"""
图片转视频工具
将图片序列转换为视频文件
"""
from __future__ import annotations

import os
from pathlib import Path

from conf import BASE_DIR


def check_moviepy_installed() -> bool:
    """检查 moviepy 是否已安装"""
    try:
        from moviepy import ImageSequenceClip
        return True
    except ImportError:
        return False


def images_to_video(
    image_paths: list[str],
    output_path: str,
    duration: float = 5.0,
    fps: int = 24,
) -> str:
    """
    将图片序列转换为视频

    Args:
        image_paths: 图片路径列表
        output_path: 输出视频路径
        duration: 每张图片显示时长（秒）
        fps: 视频帧率

    Returns:
        生成的视频路径
    """
    if not check_moviepy_installed():
        raise RuntimeError(
            "moviepy 未安装，请运行: pip install moviepy\n"
            "同时需要安装 ffmpeg: https://ffmpeg.org/download.html"
        )

    from moviepy import ImageClip, concatenate_videoclips
    from PIL import Image
    import tempfile
    import shutil

    # 验证图片文件存在
    valid_images = []
    for img_path in image_paths:
        path = Path(img_path)
        if path.exists():
            valid_images.append(str(path.absolute()))
        else:
            print(f"[WARN] 图片不存在，跳过: {img_path}")

    if not valid_images:
        raise ValueError("没有有效的图片文件")

    # 确保输出目录存在
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 统一图片尺寸 - 使用第一张图片的尺寸
    first_img = Image.open(valid_images[0])
    target_size = first_img.size
    first_img.close()

    # 创建临时目录存放调整后的图片
    temp_dir = Path(tempfile.mkdtemp())
    resized_images = []

    try:
        for i, img_path in enumerate(valid_images):
            img = Image.open(img_path)
            if img.size != target_size:
                # 调整图片尺寸，保持比例并居中
                new_img = Image.new('RGB', target_size, (0, 0, 0))
                img.thumbnail(target_size, Image.Resampling.LANCZOS)
                offset = ((target_size[0] - img.size[0]) // 2, (target_size[1] - img.size[1]) // 2)
                new_img.paste(img, offset)
                resized_path = temp_dir / f"resized_{i:04d}.jpg"
                new_img.save(resized_path, 'JPEG')
                resized_images.append(str(resized_path))
            else:
                resized_images.append(img_path)
            img.close()

        # 创建每个图片的 clip
        clips = []
        for img_path in resized_images:
            clip = ImageClip(img_path, duration=duration)
            clips.append(clip)

        # 合并所有 clip
        final_clip = concatenate_videoclips(clips, method="compose")

        # 写入视频文件
        final_clip.write_videofile(
            str(output_path),
            fps=fps,
            codec="libx264",
            audio=False,
            logger=None,
        )

        final_clip.close()

        print(f"[OK] 视频已生成: {output_path}")
        return str(output_path)

    finally:
        # 清理临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)


def convert_images_to_video_for_publish(
    image_paths: list[str],
    title: str = "converted",
    duration: float = 5.0,
) -> str:
    """
    为发布功能转换图片为视频

    Args:
        image_paths: 图片路径列表（相对或绝对路径）
        title: 用于生成视频文件名的标题
        duration: 每张图片显示时长（秒）

    Returns:
        生成的视频绝对路径
    """
    # 解析图片路径
    resolved_paths = []
    for img_path in image_paths:
        path = Path(img_path)
        if not path.is_absolute():
            path = Path(BASE_DIR) / img_path
        resolved_paths.append(str(path))

    # 生成输出路径
    output_dir = Path(BASE_DIR) / "videos" / "converted"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 使用标题作为文件名（去除特殊字符）
    safe_title = "".join(c for c in title if c.isalnum() or c in " _-")[:50]
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"{safe_title}_{timestamp}.mp4"

    return images_to_video(
        image_paths=resolved_paths,
        output_path=str(output_path),
        duration=duration,
    )
