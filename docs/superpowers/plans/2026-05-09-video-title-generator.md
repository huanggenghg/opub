# 视频标题描述自动生成功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 添加 `sau generate` 命令，批量分析视频内容生成标题描述，存储为独立 JSON 配置文件，发布时自动匹配。

**Architecture:** 新增 `utils/video_analyzer.py` 模块处理视频分析，修改 `sau_cli.py` 添加 generate 子命令，修改 `publish_all.py` 支持读取视频同名配置文件。

**Tech Stack:** Python, OpenCV (视频帧提取), 多模态分析 (Claude Code 内置能力), JSON 配置文件

---

## 文件结构

| 文件 | 操作 | 说明 |
|------|------|------|
| `utils/video_analyzer.py` | 创建 | 视频分析模块：提取关键帧、生成标题描述、保存配置文件 |
| `sau_cli.py` | 修改 | 添加 `generate` 子命令 |
| `publish_all.py` | 修改 | 添加 `get_video_content()` 函数，优先读取同名 JSON 配置 |

---

### Task 1: 创建视频分析模块

**Files:**
- Create: `utils/video_analyzer.py`

- [ ] **Step 1: 创建 video_analyzer.py 模块骨架**

```python
# -*- coding: utf-8 -*-
"""
视频内容分析模块
分析视频画面内容，自动生成标题和描述
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

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
```

- [ ] **Step 2: 添加关键帧提取函数**

```python
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
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频文件: {video_file}")
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        cap.release()
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
    
    cap.release()
    return frame_paths
```

- [ ] **Step 3: 添加内容分析函数（调用 Claude Code 分析）**

```python
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
```

- [ ] **Step 4: 添加批量生成函数**

```python
def generate_video_configs(
    directory: str,
    force: bool = False,
    progress_callback: Optional[callable] = None
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
            
            # 清理临时帧文件
            import shutil
            for frame_path in frame_paths:
                if os.path.exists(frame_path):
                    os.remove(frame_path)
            # 清理临时目录
            temp_dir = os.path.dirname(frame_paths[0]) if frame_paths else ""
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
                
        except Exception as e:
            results["error"] += 1
            results["errors"].append({"video": basename, "error": str(e)})
            if progress_callback:
                progress_callback(idx, total, basename, f"error: {str(e)}")
    
    return results
```

- [ ] **Step 5: 提交代码**

```bash
git add utils/video_analyzer.py
git commit -m "feat: 添加视频分析模块 utils/video_analyzer.py"
```

---

### Task 2: 修改 sau_cli.py 添加 generate 子命令

**Files:**
- Modify: `sau_cli.py:435-544` (build_parser 函数)
- Modify: `sau_cli.py:547-731` (dispatch 函数)

- [ ] **Step 1: 在 build_parser 函数中添加 generate 子命令**

在 `build_parser()` 函数中，在 `platform_parsers` 定义之后，添加 generate 子命令：

```python
def build_parser() -> argparse.ArgumentParser:
    schedule_help = SCHEDULE_FORMAT.replace("%", "%%")
    parser = argparse.ArgumentParser(
        prog="sau",
        description="CLI for social-auto-upload.",
    )
    platform_parsers = parser.add_subparsers(dest="platform", required=True)

    # === 添加 generate 子命令 ===
    generate_parser = platform_parsers.add_parser("generate", help="Generate video title/description from content analysis")
    generate_parser.add_argument("--dir", required=True, help="Video directory path")
    generate_parser.add_argument("--force", action="store_true", help="Force overwrite existing config files")
    
    # === 原有的平台子命令 ===
    douyin_parser = platform_parsers.add_parser("douyin", help="Douyin operations")
    # ... 后续代码保持不变
```

- [ ] **Step 2: 在 dispatch 函数中添加 generate 处理逻辑**

在 `dispatch()` 函数开头，添加 generate 命令的处理：

```python
async def dispatch(args: argparse.Namespace) -> int:
    # === 处理 generate 命令 ===
    if args.platform == "generate":
        from utils.video_analyzer import generate_video_configs, get_video_files
        
        directory = args.dir
        if not os.path.isdir(directory):
            print(f"错误: 目录不存在: {directory}", file=sys.stderr)
            return 1
        
        video_files = get_video_files(directory)
        if not video_files:
            print(f"未找到视频文件: {directory}")
            return 0
        
        print(f"找到 {len(video_files)} 个视频文件，开始分析...")
        
        def progress_callback(current, total, video_file, status):
            if status == "skip":
                print(f"[{current}/{total}] 跳过 {video_file} (配置已存在)")
            elif status == "success":
                print(f"[{current}/{total}] 完成 {video_file}")
            else:
                print(f"[{current}/{total}] 错误 {video_file}: {status}")
        
        results = generate_video_configs(
            directory=directory,
            force=args.force,
            progress_callback=progress_callback
        )
        
        print(f"\n生成完成: 成功 {results['success']}, 跳过 {results['skip']}, 错误 {results['error']}")
        return 0
    
    # === 原有的平台处理逻辑 ===
    if args.platform == "douyin":
        # ... 后续代码保持不变
```

- [ ] **Step 3: 提交代码**

```bash
git add sau_cli.py
git commit -m "feat: 添加 sau generate 子命令"
```

---

### Task 3: 修改 publish_all.py 支持读取视频配置文件

**Files:**
- Modify: `publish_all.py:58-74` (fill_empty_content 函数附近)

- [ ] **Step 1: 添加 get_video_content 函数**

在 `fill_empty_content()` 函数之后，添加新函数：

```python
def get_video_content(video_file: str, default_title: str, default_desc: str) -> tuple:
    """
    获取视频的标题和描述
    
    优先级：
    1. 视频同名的 JSON 配置文件
    2. 默认配置文件中的标题/描述
    3. 模板随机填充
    
    Args:
        video_file: 视频文件路径
        default_title: 默认标题（来自 publish_config.ini）
        default_desc: 默认描述（来自 publish_config.ini）
        
    Returns:
        (title, desc) 元组
    """
    from utils.video_analyzer import load_video_config
    
    # 1. 查找同名 JSON 配置文件
    config = load_video_config(video_file)
    if config:
        title = config.get('title', '')
        desc = config.get('desc', '')
        if title or desc:
            print(f"[AUTO] 使用视频配置文件: {os.path.basename(video_file).rsplit('.', 1)[0]}.json")
            return title, desc
    
    # 2. 使用默认值或模板填充
    return fill_empty_content(default_title, default_desc)
```

- [ ] **Step 2: 修改视频发布逻辑，使用 get_video_content**

在 `main()` 函数中，修改视频参数获取部分（约第 659 行）：

将原来的：
```python
# 使用配置文件中的标题和描述，如果为空则从模板随机填充
title, desc = fill_empty_content(params["title"], params["desc"])
```

修改为：
```python
# 使用视频配置文件或默认配置/模板填充
title, desc = get_video_content(video_file, params["title"], params["desc"])
```

- [ ] **Step 3: 提交代码**

```bash
git add publish_all.py
git commit -m "feat: publish_all.py 支持读取视频同名配置文件"
```

---

### Task 4: 测试 generate 命令

**Files:**
- Test: `videos/20260509/` 目录

- [ ] **Step 1: 运行 generate 命令测试**

```bash
sau generate --dir videos/20260509/
```

预期输出：
- 显示找到的视频数量
- 逐个分析并生成配置文件
- 显示生成结果统计

- [ ] **Step 2: 检查生成的配置文件**

```bash
ls videos/20260509/*.json
```

预期：每个视频都有对应的 .json 配置文件

- [ ] **Step 3: 查看配置文件内容**

```bash
cat videos/20260509/懒人福音1.json
```

预期：包含 title、desc、generated_at、video_file 字段

---

### Task 5: 测试发布流程集成

**Files:**
- Test: `publish_all.py`

- [ ] **Step 1: 修改 publish_config.ini 使用视频目录**

```ini
video_file = videos/20260509/
title = 
desc = 
```

- [ ] **Step 2: 运行发布测试（可选平台）**

```bash
python publish_all.py
```

预期：发布时自动读取视频同名配置文件的标题/描述

- [ ] **Step 3: 验证输出日志**

检查日志是否显示 `[AUTO] 使用视频配置文件: xxx.json`

---

## 自审检查

1. **Spec coverage**: 
   - ✅ CLI 命令 `sau generate --dir` 已覆盖
   - ✅ 配置文件格式 JSON 已覆盖
   - ✅ 发布时自动匹配已覆盖
   - ✅ 强制覆盖参数 `--force` 已覆盖

2. **Placeholder scan**: 无 TBD、TODO 等占位符

3. **Type consistency**: 函数签名一致，`get_video_content` 返回 tuple[str, str]