---
name: sau-cli
description: Use when operating the social-auto-upload CLI tool — logging in, uploading videos, publishing to platforms, or analyzing video content. Also use when a user asks to publish/upload to Douyin, Xiaohongshu, Kuaishou, Weibo, Bilibili, Tencent, Baijiahao, or TikTok via command line.
---

# sau CLI 使用指南

## 前置依赖

使用前必须确保：

1. **安装包**：`pip install hgeng-sau`
2. **浏览器驱动**：`playwright install chromium`
3. **配置文件**：复制 `conf.example.py` 为 `conf.py`，填入智谱 API key（GLM-4V 视觉模型）
4. **登录账号**：各平台需先登录获取 cookie，否则上传会失败

## CLI 命令总览

```
sau <子命令> [选项]
```

| 子命令 | 说明 | 是否需要登录 |
|---------|------|-------------|
| `generate` | 分析视频帧，自动生成标题描述 | 否（需智谱 API key） |
| `publish` | 一键多平台发布（读配置文件） | 是 |
| `douyin` | 抖音：login / check / upload-video / upload-note | 是 |
| `kuaishou` | 快手：login / check / upload-video / upload-note | 是 |
| `xiaohongshu` | 小红书：login / check / upload-video / upload-note | 是 |
| `bilibili` | B站：login / check / upload-video | 是 |

**注意**：微博、微信视频号、百家号、TikTok 没有独立 CLI 子命令，只能通过 `sau publish` 批量发布。

## 常用命令

### 登录

```bash
sau douyin login --account <账号名>          # 抖音登录（扫码）
sau kuaishou login --account <账号名>        # 快手登录
sau xiaohongshu login --account <账号名>     # 小红书登录
sau bilibili login --account <账号名>        # B站登录（终端二维码）
```

登录后 cookie 保存在 `cookies/<平台>_<账号名>.json`。

### 检查登录状态

```bash
sau douyin check --account <账号名>
sau kuaishou check --account <账号名>
sau xiaohongshu check --account <账号名>
sau bilibili check --account <账号名>
```

### 单平台上传

```bash
sau douyin upload-video --account <账号> --file <视频> --title <标题> [--tags 标签1,标签2] [--schedule 2026-05-20 12:00]
sau kuaishou upload-video --account <账号> --file <视频> --title <标题>
sau xiaohongshu upload-video --account <账号> --file <视频> --title <标题>
sau bilibili upload-video --account <账号> --file <视频> --title <标题> --desc <描述> --tid <分区ID>
```

### 一键多平台发布

```bash
sau publish                                    # 按 publish_config.ini 配置发布
sau publish --platforms weibo,xiaohongshu      # 覆盖启用平台
sau publish --title "我的标题" --video videos/  # 覆盖标题和视频路径
sau publish --start-from 5                     # 从第5个视频开始（断点续传）
sau publish --schedule "2026-05-20 12:00"      # 定时发布
sau publish --force                            # 强制重新生成视频配置
sau publish --config my_config.ini             # 指定配置文件
```

### 视频内容分析

```bash
sau generate --dir videos/                     # 分析目录下所有视频
sau generate --dir videos/ --force             # 强制重新分析（覆盖已有配置）
```

分析结果保存为视频同名的 `.json` 文件，`sau publish` 时自动读取。

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| cookie missing or expired | 未登录或 cookie 过期 | 先 `sau <平台> login --account <账号>` |
| 未找到视频文件 | video_file 路径错误 | 路径相对于项目根目录，或用 `--video` 覆盖 |
| 标题为空 | 未配置标题 | `sau generate` 自动生成，或 `--title` 手动指定 |
| B站/TikTok 发布失败 | publish_all 中标注暂未实现 | B站用 `sau bilibili upload-video`，TikTok 用脚本 |
| 浏览器启动失败 | 未安装浏览器驱动 | `playwright install chromium` |
| 智谱 API 报错 | 未配置 API key | 在 `conf.py` 中填入 ZHIPU_API_KEY |