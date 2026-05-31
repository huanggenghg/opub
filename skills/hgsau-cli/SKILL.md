---
name: hgsau-cli
description: Use when 用户要用 hgsau 发布/上传视频、配置多平台发布、发布到抖音/小红书/快手/微博/B站/视频号/百家号/TikTok，或排查 hgsau publish、publish_config.ini、账号登录校验、浏览器驱动环境问题
---

# hgsau CLI 使用指南

## 当前主入口

项目当前只提供一个公开 CLI 入口：

```bash
hgsau publish
```

不要引导用户执行独立的登录、校验或单平台上传命令。发布平台、账号文件、视频路径、标题、描述、标签和定时发布时间都应优先写入 `publish_config.ini`，命令行参数只作为本次运行的临时覆盖。

## 触发场景

当用户表达下面任一意图时使用本 skill：

- 发布视频、上传视频、一键发布、多平台发布
- 发布到抖音、小红书、快手、微博、B站、视频号、百家号或 TikTok
- 配置发布平台、账号、cookie、登录校验、扫码登录
- 排查 `hgsau publish`、`publish_config.ini`、patchright、Chromium 或浏览器驱动问题

## 推荐流程

```bash
uv pip install -e .
hgsau publish --help
hgsau publish
```

如需临时覆盖配置：

```bash
hgsau publish --platforms douyin,weibo --video videos/demo.mp4 --title "标题"
hgsau publish --config my_publish_config.ini
hgsau publish --start-from 5
hgsau publish --force
```

## 配置原则

- 用 `publish_config.ini` 声明启用平台和账号文件。
- 用配置文件声明内容元数据；临时调试时再使用 `--video`、`--title`、`--desc`、`--tags`、`--schedule`。
- 运行环境预检属于发布流程的一部分，会检查 patchright 和 Chromium。
- 用户登录校验也在发布流程里完成，未登录或 cookie 失效时再触发对应平台登录。

## Agent 注意事项

- 不要先单独校验登录后再要求用户二次确认发布。
- 当登录流程生成本地二维码图片时，应直接展示图片或明确告诉用户打开哪个本地图片扫码。
- Bilibili 等需要真实交互的登录场景，不要在非交互环境里强行代跑；应指导用户在本地真实终端完成扫码后再继续发布。
- 本项目文档中文优先，不维护国际化文案。
