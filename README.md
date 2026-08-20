# opub

`opub` 是一个 Python 工具包，把视频/图文一键发布到国内主流社交媒体平台，支持定时发布。

已支持 `抖音`、`小红书`、`快手`、Bilibili、`视频号`、`百家号`、`微博` 共 7 个平台。
项目以 AI Agent 技能（skill）为核心使用形态，也可以直接作为 CLI 使用。

## 功能特性

| 平台标识 | 名称 | 视频上传 | 图文上传 | 定时发布 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `douyin` | 抖音 | ✅ | ✅ | ✅ | |
| `xiaohongshu` | 小红书 | ✅ | ✅ | ✅ | 浏览器自动化 |
| `kuaishou` | 快手 | ✅ | ✅ | ✅ | 浏览器自动化 |
| `bilibili` | B站 | ✅ | ❌ | ✅ | 运行时自动准备 `biliup`，自动抓取BV号 |
| `tencent` | 视频号 | ✅ | ❌ | ✅ | 分享短链通过 API 自动抓取 |
| `baijiahao` | 百家号 | ✅ | ❌ | ✅ | 浏览器自动化 |
| `weibo` | 微博 | ✅ | ❌ | ✅ | 支持逗号分隔多账号，每个账号各发一遍 |

所有平台通过统一入口 `opub` 调用，自动完成运行环境预检、账号登录校验、发布和结果汇总。

## 安装

```bash
pip install opub
```

系统依赖：

```bash
# 浏览器驱动（首次发布时会自动检查并尝试自动安装，失败时按提示手动执行）
PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST="https://cdn.playwright.dev" patchright install chromium

# ffmpeg（仅"图文转视频"功能需要）
# macOS: brew install ffmpeg
# Ubuntu/Debian: sudo apt-get install ffmpeg
```

首次运行会自动在 `~/.opub/` 创建数据目录（cookies 等）。可用环境变量 `SAU_HOME` 指定其他数据目录。

## 快速开始

1. 编辑工作目录中的 `publish_config.ini`，配置内容、素材路径、启用平台和账号文件。
2. 执行统一发布入口：

```bash
opub
```

如需临时覆盖配置：

```bash
opub --platforms douyin,weibo --video videos/demo.mp4 --title "标题"
```

`publish_config.ini` 是主要控制文件，用于配置内容、素材路径、启用平台、账号文件、定时发布和平台元数据。命令行参数只用于临时覆盖本次运行的配置。发布结束后会自动清空一次性任务字段，账号文件配置保留。

## AI Agent 技能

Agent 的完整接口契约见 [skills/opub-cli/SKILL.md](./skills/opub-cli/SKILL.md)，安装、配置、调用、读取结果所需信息全部在其中。

技能与运行时分发相互独立：Agent 平台安装技能时即获得 SKILL.md，运行时依赖由 Agent 按 SKILL.md 指引自行动 `pip install opub` 安装。

从源码运行（开发）：

```bash
git clone https://github.com/huanggenghg/opub.git
cd opub
uv venv && source .venv/bin/activate
uv pip install -e .
```

## 贡献指南

1. Fork 本仓库。
2. 创建一个新的分支（`git checkout -b feature/YourFeature`）。
3. 提交您的更改（`git commit -m 'Add some feature'`）。
4. Push 到您的分支并创建 Pull Request。

## 致谢

- Bilibili 上传能力基于开源项目 [biliup](https://github.com/biliup/biliup) 接入与封装。
- 本项目基于 [dreammis/social-auto-upload](https://github.com/dreammis/social-auto-upload) 重构而来，感谢原作者及贡献者。

## 许可证

[MIT License](LICENSE)
