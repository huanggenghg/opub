# -*- coding: utf-8 -*-
"""
视频内容分析脚本
使用 Claude Code 多模态能力分析视频帧，生成标题和描述
"""
import os
import sys
import json
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from utils.video_analyzer import (
    get_video_files,
    extract_frames,
    save_video_config,
    config_exists,
    load_video_config,
    get_frame_files,
    cleanup_frames_dir,
)


def analyze_frames_with_claude(frame_paths: list[str], video_name: str) -> tuple[str, str]:
    """
    分析帧图像生成标题和描述
    使用智谱 AI GLM-4V 视觉模型分析视频帧
    """
    from utils.video_analyzer import analyze_frames_with_glm4v
    return analyze_frames_with_glm4v(frame_paths, video_name)


def main():
    """主函数 - 分析视频并生成配置"""
    import argparse

    parser = argparse.ArgumentParser(description="分析视频内容生成标题描述")
    parser.add_argument("--dir", required=True, help="视频目录路径")
    parser.add_argument("--force", action="store_true", help="强制覆盖已存在的配置文件")
    args = parser.parse_args()

    if not os.path.isdir(args.dir):
        print(f"错误: 目录不存在: {args.dir}")
        return 1

    video_files = get_video_files(args.dir)
    if not video_files:
        print(f"未找到视频文件: {args.dir}")
        return 0

    print(f"找到 {len(video_files)} 个视频文件")
    print("=" * 50)

    for idx, video_file in enumerate(video_files, 1):
        basename = os.path.basename(video_file)

        # 检查是否已存在配置文件
        if not args.force and config_exists(video_file):
            print(f"[{idx}/{len(video_files)}] 跳过 {basename} (配置已存在)")
            continue

        print(f"\n[{idx}/{len(video_files)}] 分析: {basename}")

        try:
            # 提取关键帧（返回帧文件夹目录）
            frames_dir = extract_frames(video_file, num_frames=3)
            # 获取帧文件路径列表
            frame_paths = get_frame_files(frames_dir)
            print(f"  提取了 {len(frame_paths)} 帧")

            # 分析内容
            title, desc = analyze_frames_with_claude(frame_paths, basename)

            # 保存配置
            config_file = save_video_config(video_file, title, desc)
            print(f"  标题: {title}")
            print(f"  描述: {desc[:50]}...")
            print(f"  保存: {os.path.basename(config_file)}")

            # 清理临时文件
            cleanup_frames_dir(frames_dir)

        except Exception as e:
            print(f"  错误: {e}")

    print("\n" + "=" * 50)
    print("分析完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
