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
    import numpy as np

    # 使用项目内的临时目录，便于管理和读取
    from conf import BASE_DIR
    frames_base_dir = os.path.join(str(BASE_DIR), 'temp_frames')
    os.makedirs(frames_base_dir, exist_ok=True)

    # 为每个视频创建唯一的子目录（使用 hash 避免中文路径问题）
    import hashlib
    video_hash = hashlib.md5(video_file.encode('utf-8')).hexdigest()[:8]
    video_name = os.path.basename(video_file).rsplit('.', 1)[0]
    # 使用 hash 作为目录名，避免中文路径问题
    temp_dir = os.path.join(frames_base_dir, f"{video_hash}_{video_name[:20] if len(video_name) > 20 else video_name}")
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
                # 使用 imencode 处理中文路径
                cv2.imencode('.png', frame)[1].tofile(frame_path)

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
    import base64

    try:
        from conf import ZHIPU_API_KEY, ZHIPU_VISION_MODEL
    except ImportError:
        raise RuntimeError("未找到配置文件 conf.py，请确保配置文件存在")

    if not ZHIPU_API_KEY:
        raise RuntimeError("未配置 ZHIPU_API_KEY，请在 conf.py 中设置智谱 AI API Key")

    # 构建消息内容
    content = []

    # 添加文字提示 - 以创作者视角生成生动文案
    prompt = f"""你是一位资深短视频创作者，擅长在抖音、小红书等平台创作爆款内容。
现在请分析视频画面，以创作者的视角为这个视频写标题和描述。

视频文件名：{video_name}

【创作原则】
1. 标题要抓眼球但不做标题党，用真实内容打动人
2. 描述要有代入感，像朋友在聊天分享，不是官方介绍
3. 用口语化表达，避免书面语和官方腔调
4. 可以适当用emoji增加亲和力，但不要滥用
5. 突出视频最吸引人的点：是搞笑？是干货？是情感共鸣？

【风格参考】
好的标题示例：
- "这招绝了！一分钟学会..."（干货类）
- "笑死，我家猫竟然..."（搞笑类）
- "终于搞懂了，原来这么简单"（教程类）
- "这个真的好用，强烈推荐"（产品类）

好的描述示例：
- "试了好几次才成功，分享给你们～"
- "第一次发现这个功能，太方便了！"
- "看完记得点赞收藏，下次用得上"

【禁止事项】
- 不要用"本视频"、"该视频"等官方表达
- 不要用"展示了"、"呈现了"等书面语
- 不要用"精彩内容"、"值得观看"等空洞描述
- 不要过度夸张或虚假宣传

请根据画面内容，判断视频类型，然后创作标题和描述。
按以下 JSON 格式返回，不要包含其他内容：
{{"title": "标题内容", "desc": "描述内容"}}"""

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
            max_tokens=200,
        )

        result_text = response.choices[0].message.content.strip()

        # 解析 JSON 结果
        import re
        # 尝试提取 JSON 内容
        json_match = re.search(r'\{[^{}]*"title"[^{}]*"desc"[^{}]*\}', result_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            title = result.get("title", "")
            desc = result.get("desc", "")
        else:
            # 尝试直接解析
            result = json.loads(result_text)
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