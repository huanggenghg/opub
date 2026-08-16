---
name: hgsau-cli
description: Use when 用户要用 hgsau 发布/上传视频或图文、配置多平台发布、发布到抖音/小红书/快手/微博/B站/视频号/百家号，或排查 hgsau、publish_config.ini、账号登录校验、浏览器驱动环境问题
version: "0.4.6"
---

# hgsau CLI 使用指南

## 当前主入口

项目当前只提供一个公开 CLI 入口：

```bash
hgsau
```

不要引导用户执行独立的登录、校验或单平台上传命令。发布平台、视频路径、标题、描述、标签和定时发布时间都是一次性任务字段，每次发布前都必须明确设置；账号文件可以长期保存在 `publish_config.ini` 中。命令行参数只作为本次运行的临时覆盖。

## 已验证平台（7个）

| 平台标识 | 名称 | 视频 | 图文 | 说明 |
| --- | --- | --- | --- | --- |
| `douyin` | 抖音 | ✅ | ✅ | 主线重构最完整 |
| `xiaohongshu` | 小红书 | ✅ | ✅ | 浏览器自动化 |
| `kuaishou` | 快手 | ✅ | ✅ | 浏览器自动化 |
| `bilibili` | B站 | ✅ | ❌ | 运行时自动准备 biliup，自动抓取BV号 |
| `tencent` | 视频号 | ✅ | ❌ | 对应 tencent_uploader |
| `baijiahao` | 百家号 | ✅ | ❌ | 浏览器自动化 |
| `weibo` | 微博 | ✅ | ❌ | 支持逗号分隔多账号，每个账号各发一遍 |

TikTok 等国际化平台暂不在主线范围内。

## 触发场景

当用户表达下面任一意图时使用本 skill：

- 发布视频、上传视频、一键发布、多平台发布、图文发布
- 发布到抖音、小红书、快手、微博、B站、视频号、百家号
- 配置发布平台、账号、cookie、登录校验、扫码登录
- 排查 `hgsau`、`publish_config.ini`、patchright、Chromium 或浏览器驱动问题

## 推荐流程

```bash
uv pip install -e .
hgsau --help
hgsau
```

如需临时覆盖配置：

```bash
hgsau --platforms douyin,weibo --video videos/demo.mp4 --title "标题"
hgsau --config my_publish_config.ini
hgsau --start-from 5
hgsau --force
```

## 环境准备

### Python 依赖

```bash
uv venv && source .venv/bin/activate
uv pip install -e .
```

当前主线依赖在 `pyproject.toml`（v0.4.6），关键依赖：
- `patchright==1.58.2`（浏览器驱动）
- `loguru`, `opencv-python`, `qrcode`, `segno`, `requests`

`requirements.txt` 仅作历史兼容，不是主安装入口。

### 浏览器驱动

```bash
PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST="https://cdn.playwright.dev" patchright install chromium
```

### conf.py

```bash
cp conf.example.py conf.py
```

常用配置项：`LOCAL_CHROME_PATH`、`LOCAL_CHROME_HEADLESS`、`DEBUG_MODE`。

### Bilibili biliup

首次运行 B站 发布时自动下载 `biliup`，后续自动检查 release 更新。用户无需手动安装。国内网络访问 GitHub Release 较慢时可使用 `https://gh-proxy.com/` 或 `https://gh-proxy.org/` 辅助。

## 配置原则

### publish_config.ini 关键字段

```ini
[common]
content_type = video          # video=视频, note=图文
title =                       # 标题（所有平台共用）
desc =                        # 描述，支持\n换行
tags =                        # 话题标签，英文逗号分隔
video_file =                  # 视频路径（相对项目根目录）
images =                      # 图文图片路径，英文逗号分隔
publish_strategy = immediate  # immediate=立即, scheduled=定时
publish_time =                # 定时发布时间 YYYY-MM-DD HH:MM
start_from =                  # 断点续传起始序号
convert_to_video = false      # 图文转视频（仅 note 模式）

[platforms]
enabled =                     # 启用平台，英文逗号分隔
# 各平台账号文件路径（长期保留）
douyin_account = cookies/douyin_uploader/account.json
weibo_account = cookies/weibo_uploader/account1.json  # 微博支持逗号分隔多账号
```

### 一次性字段 vs 长期字段

- **长期保留**：各平台账号文件路径（`*_account`）
- **每次发布前必须重新设置**：`enabled`、`title`、`desc`、`tags`、`video_file`/`images`、`publish_strategy`、`publish_time`、`start_from`
- 发布流程结束后，`hgsau` 会自动清空一次性任务字段，避免下次沿用旧配置

### 命令行临时覆盖

```bash
--config publish_config.ini    # 指定配置文件
--platforms douyin,weibo       # 覆盖启用平台
--video videos/demo.mp4        # 覆盖视频路径
--title "标题"                  # 覆盖标题
--desc "简介"                   # 覆盖描述
--tags 运动,训练               # 覆盖标签
--schedule "2026-03-24 21:30"  # 覆盖定时发布
--start-from 5                 # 断点续传
--force                        # 强制重新生成视频配置
```

## 运行时行为

`hgsau` 执行完整发布场景：

1. 读取 `publish_config.ini`，合并命令行临时覆盖
2. 运行环境预检（patchright、Chromium）
3. 校验启用平台账号登录状态
4. 按配置发布视频或图文内容
5. 输出结果汇总（退出码表达整体结果）
6. 清空一次性任务字段，保留账号文件配置

## Agent 注意事项

- 不要先单独校验登录后再要求用户二次确认发布。
- 当登录流程生成本地二维码图片时，应直接展示图片或明确告诉用户打开哪个本地图片扫码，不要只回传路径。
- Bilibili 等需要真实交互的登录场景，不要在非交互环境里强行代跑；应指导用户在本地真实终端完成扫码后再继续发布。
- 微博多账号发布时，同一视频会为每个账号各发一遍。
- 优先相信 `pyproject.toml`，不要把 `requirements.txt` 视为主线真相。
- 本项目文档中文优先，不维护国际化文案。
