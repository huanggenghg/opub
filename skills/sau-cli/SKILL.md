---
name: sau-cli
description: Use when operating the social-auto-upload CLI tool — checking environment, logging in, uploading videos, publishing to platforms, or analyzing video content. Also use when a user asks to publish/upload to Douyin, Xiaohongshu, Kuaishou, Weibo, Bilibili, Tencent, Baijiahao, or TikTok via command line. IMPORTANT: Before ANY sau command, you MUST run `pip install --upgrade hgeng-sau` and `sau status` first — do not skip these steps.
---

# sau CLI 使用指南

## 强制前置步骤（不可跳过）

每次使用 sau 前必须执行，确保包是最新版且环境就绪：

```bash
pip install --upgrade hgeng-sau
sau status
```

- `pip install --upgrade hgeng-sau`：确保安装最新版本（旧版本有已知 bug，必须升级）
- `sau status`：自动检测并安装缺失的 patchright 库和 chromium 浏览器驱动

**这两步不能省略、不能假设已执行过。** 即使之前执行过，也要重新运行以确保版本最新。

## CLI 命令总览

```
sau <子命令> [选项]
```

| 子命令 | 说明 | 是否需要登录 |
|---------|------|-------------|
| `status` | 检查环境与登录状态 | 否 |
| `login` | 登录指定平台（扫码） | 否（登录本身） |
| `generate` | 分析视频帧，自动生成标题描述 | 否（需智谱 API key） |
| `publish` | 一键多平台发布（读配置文件） | 自动检查，未登录则触发登录 |
| `douyin` | 抖音：login / check / upload-video / upload-note | 是 |
| `kuaishou` | 快手：login / check / upload-video / upload-note | 是 |
| `xiaohongshu` | 小红书：login / check / upload-video / upload-note | 是 |
| `bilibili` | B站：login / check / upload-video | 是 |

**其他平台**（weibo、tencent、baijiahao、tk）通过 `sau login --platform <平台>` 和 `sau publish` 支持，暂无独立子命令。

## 常用命令

### 环境检查

```bash
sau status                    # 检查 Python、浏览器、配置、各平台登录状态
```

### 登录

```bash
sau login --platform weibo --account <账号名>       # 微博登录
sau login --platform douyin --account <账号名>       # 抖音登录
sau login --platform kuaishou --account <账号名>     # 快手登录
sau login --platform xiaohongshu --account <账号名>  # 小红书登录
sau login --platform bilibili --account <账号名>     # B站登录
sau login --platform tencent --account <账号名>      # 微信视频号登录
sau login --platform baijiahao --account <账号名>    # 百家号登录
sau login --platform tk --account <账号名>           # TikTok 登录
sau login --platform <平台> --account <账号> --headless  # 无头模式登录
```

登录后 cookie 保存在 `~/.social-auto-upload/cookies/` 目录。

**注意**：Bilibili 登录必须由用户在本地真实终端执行，agent 不应在非交互环境里运行 `sau login --platform bilibili`。

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

**自动登录**：发布时自动检查各平台 cookie 有效性，无效则自动触发登录流程（扫码），无需手动分步操作。

### 单平台上传

```bash
sau douyin upload-video --account <账号> --file <视频> --title <标题> [--tags 标签1,标签2] [--schedule 2026-05-20 12:00]
sau kuaishou upload-video --account <账号> --file <视频> --title <标题>
sau xiaohongshu upload-video --account <账号> --file <视频> --title <标题>
sau bilibili upload-video --account <账号> --file <视频> --title <标题> --desc <描述> --tid <分区ID>
```

### 视频内容分析（可选功能）

```bash
pip install --upgrade "hgeng-sau[analyze]"     # 安装视频分析依赖
sau generate --dir videos/                     # 分析目录下所有视频
sau generate --dir videos/ --force             # 强制重新分析
```

## 配置（可选）

默认无需配置。如需自定义，在 `~/.social-auto-upload/config.json` 中设置：

```json
{
  "chrome_headless": true,
  "chrome_path": "",
  "debug": false,
  "zhipu_api_key": "",
  "zhipu_vision_model": "glm-4v-plus",
  "xhs_server": ""
}
```

环境变量 `SAU_HOME` 可覆盖数据目录（默认 `~/.social-auto-upload/`）。

## Agent 交互流程

```
Agent 收到发布请求
  → pip install --upgrade hgeng-sau（强制，不可跳过）
  → sau status（检查环境，自动安装浏览器驱动）
  → sau publish --platforms weibo --video xxx --title xxx
    → 内部自动 check cookie
    → cookie 无效 → 自动触发 login（扫码）
    → 登录成功 → 继续发布
  → 返回结果
```

Agent 只需知道 `sau status` 和 `sau publish` 两个命令。

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| Browser: patchright not found | 未安装浏览器驱动 | `sau status`（自动安装） |
| cookie missing or expired | 未登录或 cookie 过期 | `sau login --platform <平台> --account <账号>` |
| 未找到视频文件 | video_file 路径错误 | 路径相对于数据目录，或用 `--video` 覆盖 |
| 标题为空 | 未配置标题 | `sau generate` 自动生成（需安装 analyze 依赖），或 `--title` 手动指定 |
| 浏览器启动失败 | 未安装浏览器驱动 | `sau status`（自动安装） |
| 智谱 API 报错 | 未配置 API key | 在 config.json 中填入 zhipu_api_key |
