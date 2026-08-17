---
name: hgsau-cli
description: Use when 用户要用 hgsau 发布/上传视频或图文、配置多平台发布、发布到抖音/小红书/快手/微博/B站/视频号/百家号，或排查 hgsau、publish_config.ini、账号登录校验、浏览器驱动环境问题
version: "0.4.7"
---

# hgsau CLI 使用指南

## 这是什么

`hgsau` 是一个 pip 包，把视频/图文一键发布到 7 个国内平台。本文件是它对 Agent 的完整接口契约：安装、配置、调用、读取结果所需的信息全部在此或 `hgsau` 运行时输出中。

## 安装

```bash
pip install hgsau
```

系统依赖：

```bash
# 浏览器驱动（首次发布时会自动检查并尝试自动安装，失败时按 ENV-004 提示手动执行）
PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST="https://cdn.playwright.dev" patchright install chromium

# ffmpeg（仅"图文转视频"功能需要）
# macOS: brew install ffmpeg
# Ubuntu/Debian: sudo apt-get install ffmpeg
```

首次运行会自动在 `~/.social-auto-upload/` 创建数据目录（cookies 等），无需手动初始化。可用环境变量 `SAU_HOME` 指定其他数据目录。

## 已验证平台（7个）

| 平台标识 | 名称 | 视频 | 图文 | 说明 |
| --- | --- | --- | --- | --- |
| `douyin` | 抖音 | ✅ | ✅ | |
| `xiaohongshu` | 小红书 | ✅ | ✅ | 浏览器自动化 |
| `kuaishou` | 快手 | ✅ | ✅ | 浏览器自动化 |
| `bilibili` | B站 | ✅ | ❌ | 自动准备 biliup，自动抓取BV号 |
| `tencent` | 视频号 | ✅ | ❌ | |
| `baijiahao` | 百家号 | ✅ | ❌ | 浏览器自动化 |
| `weibo` | 微博 | ✅ | ❌ | 支持逗号分隔多账号，每个账号各发一遍 |

## 触发场景

当用户表达下面任一意图时使用本 skill：

- 发布视频、上传视频、一键发布、多平台发布、图文发布
- 发布到抖音、小红书、快手、微博、B站、视频号、百家号
- 配置发布平台、账号、cookie、登录校验、扫码登录
- 排查 `hgsau`、`publish_config.ini`、Chromium 或浏览器驱动问题

## 配置

### 配置文件位置

默认配置文件是数据目录下的 `publish_config.ini`（pip 模式即 `~/.social-auto-upload/publish_config.ini`，随 `SAU_HOME` 变化）；不存在时需用 `--config` 指定路径，或直接用 `--platforms` + `--video` 命令行运行。配置文件需手动创建，不会自动生成。

### publish_config.ini 关键字段

```ini
[common]
content_type = video          # video=视频, note=图文
title =                       # 标题（所有平台共用）
desc =                        # 描述，支持\n换行
tags =                        # 话题标签，英文逗号分隔
video_file =                  # 视频路径
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
- 发布流程结束后，`hgsau` 自动清空一次性任务字段，避免下次沿用旧配置

## 调用

```bash
hgsau                                  # 读取 publish_config.ini 执行完整发布
hgsau --platforms douyin,weibo --video videos/demo.mp4 --title "标题"
hgsau --config my_publish_config.ini
hgsau --start-from 5
hgsau --force
hgsau --version                        # 查看已安装版本
hgsau --help                           # 全部参数说明（每个参数标注对应的 ini 字段）
```

命令行参数只作为本次运行的临时覆盖；也可以不写 ini，直接 `hgsau --platforms ... --video ...` 运行。使用 `--schedule` 时本次运行自动切换为定时发布，无需在 ini 中设置 `publish_strategy = scheduled`。

## 读取结果

### 退出码

| 退出码 | 含义 | Agent 下一步 |
| --- | --- | --- |
| 0 | 全部平台发布成功 | 从汇总中提取结果链接汇报给用户 |
| 1 | 部分平台成功、部分失败 | 读"发布结果"汇总，向用户汇报成败明细 |
| 2 | 全部平台发布失败 | 读各平台 [PUB-xxx] 错误码，按建议动作处理 |
| 10 | 配置错误 | 按 stderr 的 CFG-xxx 建议修配置或改用 CLI 覆盖参数 |
| 11 | 环境错误 | 按 stderr 的 ENV-xxx 建议执行安装命令后重试 |
| 12 | 账号未登录且扫码未完成 | 引导用户完成扫码登录后重试 |

### 错误输出格式

所有流程级错误输出到 stderr，格式固定：

```
[hgsau] <错误码>: <描述>。建议: <可执行的动作>
```

错误码体系：`CFG-xxx` 配置、`ENV-xxx` 环境、`AUTH-xxx` 登录、`PUB-<platform>` 平台发布失败（出现在"发布结果"汇总行中）、`RUN-xxx` 运行时异常（意外错误，退出码 2）。

### 结果汇总格式

发布结束打印稳定格式的汇总（stdout）：

```
========== 发布结果 ==========
抖音: ✅ 成功
微博: ❌ 失败 [PUB-weibo]: 上传超时

========== 总体发布汇总 ==========
成功: 1 次
失败: 1 次
```

成功平台的分享链接写入 Excel 结果文件并显示在输出中。

## Agent 注意事项

- 不要先单独校验登录后再要求用户二次确认发布。
- 当登录流程生成本地二维码图片时，应直接展示图片或明确告诉用户打开哪个本地图片扫码，不要只回传路径。
- Bilibili 等需要真实交互的登录场景，不要在非交互环境里强行代跑；应指导用户在本地真实终端完成扫码后再继续发布。
- 微博多账号发布时，同一视频会为每个账号各发一遍。
- 本项目文档中文优先，不维护国际化文案。
