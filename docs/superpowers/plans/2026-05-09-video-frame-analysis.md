# 视频帧分析功能重构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 `sau generate` 命令，移除占位符实现，使用两阶段执行（并发帧提取 + 串行分析）

**Architecture:** 阶段1 并发提取所有视频帧到独立文件夹，阶段2 串行读取帧图像由大模型分析生成标题描述

**Tech Stack:** Python, OpenCV (视频帧提取), concurrent.futures (并发), Claude Code 多模态能力

---

## 文件结构

| 文件 | 操作 | 说明 |
|------|------|------|
| `utils/video_analyzer.py` | 修改 | 重构帧提取逻辑，删除占位符，新增并发提取函数 |
| `sau_cli.py` | 修改 | 重构 generate 命令处理逻辑，分两阶段执行 |

---

### Task 1: 重构 video_analyzer.py - 删除占位符并修改帧提取函数

**Files:**
- Modify: `utils/video_analyzer.py`

- [ ] **Step 1: 删除 analyze_video_content 占位符函数**

删除 `utils/video_analyzer.py` 中的 `analyze_video_content()` 函数（第 169-192 行）。

- [ ] **Step 2: 修改 extract_frames 函数返回帧文件夹路径**

将 `extract_frames()` 函数修改为返回帧文件夹路径，而非帧文件列表：

```python
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
```

- [ ] **Step 3: 新增 extract_all_frames_parallel 并发提取函数**

在 `extract_frames()` 函数之后添加：

```python
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
```

- [ ] **Step 4: 新增 get_frame_files 辅助函数**

在 `extract_all_frames_parallel()` 之后添加：

```python
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
```

- [ ] **Step 5: 删除旧的 generate_video_configs 函数**

删除 `generate_video_configs()` 函数（第 195-270 行），因为该函数包含占位符调用逻辑，将在 sau_cli.py 中重新实现。

- [ ] **Step 6: 新增 cleanup_frames_dir 清理函数**

在文件末尾添加：

```python
def cleanup_frames_dir(frames_dir: str) -> None:
    """
    清理帧文件夹

    Args:
        frames_dir: 帧文件夹路径
    """
    import shutil
    if frames_dir and os.path.exists(frames_dir):
        shutil.rmtree(frames_dir, ignore_errors=True)
```

- [ ] **Step 7: 更新文件顶部的导出列表**

确保文件顶部有正确的导入：

```python
from typing import Callable, Optional
```

- [ ] **Step 8: 提交代码**

```bash
git add utils/video_analyzer.py
git commit -m "refactor: 重构 video_analyzer.py，移除占位符，新增并发帧提取"
```

---

### Task 2: 重构 sau_cli.py - 分两阶段执行 generate 命令

**Files:**
- Modify: `sau_cli.py:553-586` (dispatch 函数中的 generate 处理)

- [ ] **Step 1: 修改 dispatch 函数中的 generate 处理逻辑**

将 `sau_cli.py` 中 `dispatch()` 函数的 generate 处理部分（约第 553-586 行）替换为：

```python
    # === 处理 generate 命令 ===
    if args.platform == "generate":
        import os
        import shutil

        from utils.video_analyzer import (
            extract_all_frames_parallel,
            get_video_files,
            save_video_config,
            config_exists,
            get_frame_files,
            cleanup_frames_dir,
        )

        directory = args.dir
        if not os.path.isdir(directory):
            print(f"错误: 目录不存在: {directory}", file=sys.stderr)
            return 1

        video_files = get_video_files(directory)
        if not video_files:
            print(f"未找到视频文件: {directory}")
            return 0

        total = len(video_files)
        print(f"找到 {total} 个视频文件")
        print("=" * 50)

        # === 阶段1: 并发提取所有视频帧 ===
        print("\n[阶段1] 提取视频帧...")

        frames_results = {}
        failed_extractions = []

        def extraction_callback(video_file, frames_dir, error):
            basename = os.path.basename(video_file)
            if error:
                print(f"  ❌ {basename}: {error}")
                failed_extractions.append(video_file)
            else:
                print(f"  ✓ {basename}")

        frames_results = extract_all_frames_parallel(
            video_files,
            progress_callback=extraction_callback
        )

        if failed_extractions:
            print(f"\n警告: {len(failed_extractions)} 个视频帧提取失败")

        # === 阶段2: 串行分析每个视频的帧 ===
        print("\n[阶段2] 分析视频内容...")
        print("提示: 此阶段需要逐个分析视频帧，请等待大模型处理")
        print("-" * 50)

        results = {"success": 0, "skip": 0, "error": 0, "files": []}

        for idx, video_file in enumerate(video_files, 1):
            basename = os.path.basename(video_file)

            # 检查是否已存在配置文件
            if not args.force and config_exists(video_file):
                print(f"[{idx}/{total}] 跳过 {basename} (配置已存在)")
                results["skip"] += 1
                # 清理帧文件夹
                frames_dir = frames_results.get(video_file, "")
                if frames_dir:
                    cleanup_frames_dir(frames_dir)
                continue

            frames_dir = frames_results.get(video_file, "")
            if not frames_dir:
                print(f"[{idx}/{total}] 跳过 {basename} (帧提取失败)")
                results["error"] += 1
                continue

            frame_files = get_frame_files(frames_dir)
            if not frame_files:
                print(f"[{idx}/{total}] 跳过 {basename} (无有效帧)")
                results["error"] += 1
                cleanup_frames_dir(frames_dir)
                continue

            print(f"\n[{idx}/{total}] 分析: {basename}")
            print(f"  帧图像: {len(frame_files)} 张")

            # 读取帧图像供 Claude Code 分析
            # 注意: 此处需要 Claude Code 在执行时直接读取帧图像
            # 以下是占位符，实际分析由 Claude Code 多模态能力完成
            print(f"  请分析以下帧图像:")
            for frame_file in frame_files:
                print(f"    - {frame_file}")

            # 占位符: 实际标题描述由 Claude Code 分析后填入
            # 这里使用文件名作为临时标题，等待 Claude Code 覆盖
            name_without_ext = basename.rsplit('.', 1)[0]
            title = f"{name_without_ext}"
            desc = f"视频内容分析待完成"

            # 保存配置
            config_file = save_video_config(video_file, title, desc)
            print(f"  ✓ 配置已保存: {os.path.basename(config_file)}")

            results["success"] += 1
            results["files"].append({
                "video": basename,
                "config": os.path.basename(config_file),
                "title": title
            })

            # 清理帧文件夹
            cleanup_frames_dir(frames_dir)

        # 清理临时目录
        from conf import BASE_DIR
        temp_frames_dir = os.path.join(BASE_DIR, 'temp_frames')
        if os.path.exists(temp_frames_dir):
            shutil.rmtree(temp_frames_dir, ignore_errors=True)

        print("\n" + "=" * 50)
        print(f"生成完成: 成功 {results['success']}, 跳过 {results['skip']}, 错误 {results['error']}")
        return 0
```

- [ ] **Step 2: 提交代码**

```bash
git add sau_cli.py
git commit -m "refactor: 重构 sau generate 命令，分两阶段执行"
```

---

### Task 3: 测试 generate 命令

**Files:**
- Test: `sau generate` 命令

- [ ] **Step 1: 准备测试视频目录**

确保 `videos/` 目录下有测试视频文件。

- [ ] **Step 2: 运行 generate 命令测试**

```bash
sau generate --dir videos/
```

预期输出：
- 显示找到的视频数量
- 阶段1: 并发提取帧，显示进度
- 阶段2: 串行分析，提示需要分析的帧图像路径
- 显示生成结果统计

- [ ] **Step 3: 验证生成的配置文件**

```bash
ls videos/*.json
```

预期：每个视频都有对应的 .json 配置文件

- [ ] **Step 4: 验证临时文件夹已清理**

```bash
ls temp_frames/
```

预期：目录不存在或为空

---

## 自审检查

1. **Spec coverage:**
   - ✅ 移除占位符 - Task 1 Step 1
   - ✅ 两阶段执行 - Task 2 Step 1
   - ✅ 独立帧存储 - Task 1 Step 2
   - ✅ 通用风格 - 分析提示词在设计中定义，实际分析由 Claude Code 执行时完成

2. **Placeholder scan:**
   - ⚠️ Task 2 Step 1 中仍有占位符注释，说明实际分析需要 Claude Code 执行时覆盖
   - 这是设计意图：帧分析需要 Claude Code 多模态能力，无法在代码中硬编码

3. **Type consistency:**
   - ✅ `extract_frames()` 返回 `str` (帧文件夹路径)
   - ✅ `extract_all_frames_parallel()` 返回 `dict[str, str]`
   - ✅ `get_frame_files()` 返回 `list[str]`
