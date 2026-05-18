# -*- coding: utf-8 -*-
"""
视频内容分析模块
分析视频画面内容，自动生成标题和描述
"""
from __future__ import annotations

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
    import numpy as np

    # 使用项目内的临时目录，便于管理和读取
    from conf import BASE_DIR
    frames_base_dir = os.path.join(str(BASE_DIR), 'temp_frames')
    os.makedirs(frames_base_dir, exist_ok=True)

    # 为每个视频创建唯一的子目录（使用 hash 避免中文路径问题）
    import hashlib
    video_hash = hashlib.md5(video_file.encode('utf-8')).hexdigest()[:8]
    video_name = os.path.basename(video_file).rsplit('.', 1)[0]
    # 使用纯 hash 作为目录名，完全避免中文和特殊字符路径问题
    temp_dir = os.path.join(frames_base_dir, video_hash)
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
                frame_path = os.path.join(temp_dir, f"frame_{idx}.jpg")
                # 使用 JPEG 格式压缩，减少 API 调用时的数据量
                cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tofile(frame_path)

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
        if file.startswith("frame_") and (file.endswith(".jpg") or file.endswith(".png")):
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


def encode_image_to_base64(image_path: str) -> str:
    """
    将图片编码为 base64 字符串

    Args:
        image_path: 图片文件路径

    Returns:
        base64 编码的字符串
    """
    import base64
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def analyze_frames_with_glm4v(frame_paths: list[str], video_name: str) -> tuple[str, str]:
    """
    使用智谱 GLM-4V 视觉模型分析视频帧，生成标题和描述

    Args:
        frame_paths: 帧图像路径列表
        video_name: 视频文件名

    Returns:
        (title, desc) 元组

    Raises:
        RuntimeError: API 调用失败时抛出
    """
    try:
        from conf import ZHIPU_API_KEY, ZHIPU_VISION_MODEL
    except ImportError:
        raise RuntimeError("未找到配置文件 conf.py，请确保配置文件存在")

    if not ZHIPU_API_KEY:
        raise RuntimeError("未配置 ZHIPU_API_KEY，请在 conf.py 中设置智谱 AI API Key")

    # 构建消息内容
    content = []

    # 添加文字提示 - 自然口语化，避免模板和虚假营销
    prompt = f"""你是一位高级的电视营销运营专家，请看图写文案，用于社交媒体发布。

视频文件名：{video_name}

【输出格式】
返回JSON：{{"title": "标题", "desc": "描述"}}

【标题要求】
- 15字以内，突出画面亮点
- 可以是感叹句、陈述句、问句，风格多变，形象生动

【描述要求】
- 30-60字，口语化表达
- 描述画面内容或产品特点
- 句式要多样，不要每条都一样的开头
- 示例只是给几个符合的样例，不要照搬，要有创作力

【绝对禁止】
❌ 时间词：最近、今天、刚、终于
❌ 购买词：入手、买了、购入、下单
❌ 营销词：强烈推荐、赶紧收藏、值得一看
❌ 官方腔：本视频展示了、这款产品
❌ 固定开头：这台电视、这个电视、这电视

【多样化开头示例】
- "画质真的绝了..."
- "大屏看球赛太爽了"
- "语音控制挺方便的"
- "色彩很鲜艳，看着舒服"
- "游戏模式延迟很低"
- "边框很窄，颜值在线"

每次换一种表达方式，不要照搬示例！不要重复！"""

    content.append({"type": "text", "text": prompt})

    # 添加帧图像（最多 3 张）
    for frame_path in frame_paths[:3]:
        if os.path.exists(frame_path):
            image_base64 = encode_image_to_base64(frame_path)
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{image_base64}"
                }
            })

    # 调用智谱 AI API
    try:
        from zhipuai import ZhipuAI
    except ImportError:
        raise RuntimeError("未安装 zhipuai 库，请运行: pip install zhipuai")

    client = ZhipuAI(api_key=ZHIPU_API_KEY)

    try:
        response = client.chat.completions.create(
            model=ZHIPU_VISION_MODEL,
            messages=[{"role": "user", "content": content}],
            temperature=0.7,
            max_tokens=400,  # 增加到 400 以适应中文内容
        )

        result_text = response.choices[0].message.content.strip()

        # 解析 JSON 结果 - 多种方式尝试
        import re
        result = None

        # 方式1: 尝试提取 JSON 块（处理 markdown 代码块）
        json_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', result_text, re.DOTALL)
        if json_block_match:
            try:
                result = json.loads(json_block_match.group(1))
            except json.JSONDecodeError:
                pass

        # 方式2: 尝试提取裸 JSON 对象
        if not result:
            json_match = re.search(r'\{[^{}]*"title"[^{}]*"desc"[^{}]*\}', result_text, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass

        # 方式3: 直接解析整个响应
        if not result:
            try:
                result = json.loads(result_text)
            except json.JSONDecodeError:
                pass

        if not result:
            raise RuntimeError(f"无法解析 API 返回的 JSON: {result_text}")

        title = result.get("title", "")
        desc = result.get("desc", "")

        # 验证结果
        if not title or not desc:
            raise ValueError("API 返回结果缺少 title 或 desc 字段")

        return title, desc

    except json.JSONDecodeError as e:
        raise RuntimeError(f"解析 API 返回结果失败: {e}\n原始响应: {result_text}")
    except Exception as e:
        raise RuntimeError(f"调用智谱 AI API 失败: {e}")