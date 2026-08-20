## Hard Constraints (MUST follow every session)

*   **禁止截屏定位 UI**:不要通过 `page.screenshot` 截图、或任何把图片发给模型 API 的方式来定位 UI 控件或分析页面。需要页面信息时,从 DOM/页面源码定位(`page.content()`、`page.evaluate`、`page.locator` + selector,或保存 HTML 后用 grep/python 分析);信息不足以判断时,直接告知用户需要协助,不要靠猜,也不要截图。
*   **禁止非文本文件调用大模型 API**:调用大模型 API 时,输入只限纯文本。不要发送图片、PDF、音频、视频或任何二进制/多模态 payload —— 当前环境不具备多模态能力,这类调用无意义且浪费资源。
*   **例外**:`page.screenshot` 仅作为调试留证(保存到 `output/` 不发给模型)是可接受的,但不能用作定位手段,也不能作为模型 API 输入。

## Project Overview

This project, `opub`, is a powerful automation tool designed to help content creators and operators efficiently publish video content to multiple domestic and international mainstream social media platforms in one click. The project implements video upload, scheduled release and other functions for platforms such as `Douyin`, `Bilibili`, `Xiaohongshu`, `Kuaishou`, `WeChat Channel`, `Baijiahao` and `TikTok`.

The project consists of a Python CLI tool and uploader modules.

**Command-line Interface:**

The project provides one public command-line workflow for terminal users:

*   `opub`: Take all publish settings as command-line arguments, validate runtime dependencies, check account login per enabled platform, publish, and print a summary.

Platform, account, media, metadata, and schedule settings are passed as command-line arguments (`opub --platforms ... --video ...`); account files are auto-discovered from the `cookies/` directory. Standalone platform login/check/upload CLI commands are no longer part of the current mainline.

## Building and Running

### Setup

1.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Install Playwright browser drivers:**
    ```bash
    playwright install chromium
    ```

3.  **Install ffmpeg (required for image-to-video conversion):**
    The `convert_to_video` feature uses moviepy + ffmpeg to turn image notes into slideshow videos. moviepy is installed from `requirements.txt`, but ffmpeg must be installed separately as a system dependency:
    *   macOS: `brew install ffmpeg`
    *   Ubuntu/Debian: `sudo apt-get install ffmpeg`
    *   Windows: download from https://ffmpeg.org/download.html and add to PATH

### Command-line Interface

Install the editable package:

```bash
uv pip install -e .
```

All settings are provided as CLI arguments for each run:

```bash
opub --platforms douyin,weibo --video videos/demo.mp4 --title "标题"
```

## Development Conventions

*   The code is located in the root directory and the `uploader` directory.
*   The `conf.example.py` file should be copied to `conf.py` and configured with the appropriate settings.
*   The `requirements.txt` file lists the Python dependencies.
