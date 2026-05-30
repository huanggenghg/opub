---
name: hgsau-cli
description: Use when operating this repository's unified hgsau CLI publish flow. The only supported public command is `hgsau publish`; platforms, accounts, media, metadata, and schedule are configured through `publish_config.ini` or temporary publish overrides.
---

# hgsau CLI 使用指南

## 核心原则

当前主线只保留一个公开入口：

```bash
hgsau publish
```

不要再调用旧命令，也不要使用按平台拆分的登录、校验或上传子命令。登录校验属于发布场景的一部分，由 `hgsau publish` 在启用平台发布前统一触发。

## 安装与验证

在仓库根目录安装：

```bash
uv pip install -e .
```

验证入口：

```bash
hgsau publish --help
```

安装后应只有 `hgsau` 控制台入口；如果本地虚拟环境里还残留旧脚本，请重新安装或清理旧环境。

## 配置方式

`publish_config.ini` 是主要控制文件，用于声明：

- 发布平台
- 视频或图文素材
- 标题、简介、标签
- 账号文件
- 定时发布时间
- 平台特有元数据

命令行参数只用于临时覆盖一次运行，不写回配置文件。

常用覆盖示例：

```bash
hgsau publish --platforms douyin,weibo --video videos/demo.mp4 --title "标题"
hgsau publish --config my_config.ini
hgsau publish --start-from 5
hgsau publish --force
```

## 执行流程

`hgsau publish` 会完成一个完整发布场景：

1. 读取配置文件。
2. 合并命令行临时覆盖。
3. 校验素材和发布参数。
4. 执行运行环境预检，包括 patchright 与 Chromium 等浏览器依赖。
5. 对启用平台执行账号登录校验。
6. 未登录或登录失效时进入对应平台登录流程。
7. 登录通过后继续发布。
8. 输出发布结果汇总，并用退出码表达整体结果。

## 运行环境预检与账号登录

运行环境预检只处理“本机是否具备执行发布的基础能力”，例如浏览器驱动是否安装。

账号登录校验只处理“某个平台账号当前是否可用”。它不再作为独立 CLI 步骤暴露给用户，而是放在统一发布流程中执行。

## Agent 使用建议

收到发布任务时，优先按下面顺序处理：

```text
确认当前目录是仓库根目录
  → uv pip install -e .
  → hgsau publish --help
  → 检查 publish_config.ini
  → hgsau publish
  → 汇总执行命令、验证结果和发布结果
```

如果登录流程生成二维码图片，不要只把图片路径告诉用户。应优先展示图片，或明确告诉用户需要打开哪个本地图片文件扫码。

## 故障处理

| 问题 | 处理 |
|------|------|
| 找不到 `hgsau` | 确认虚拟环境已激活，并重新执行 `uv pip install -e .` |
| 浏览器依赖缺失 | 重新运行 `hgsau publish`，由运行环境预检处理；必要时手动执行 `patchright install chromium` |
| cookie 缺失或失效 | 继续走 `hgsau publish`，发布流程会触发登录 |
| 视频文件不存在 | 检查 `publish_config.ini` 或使用 `--video` 临时覆盖 |
| 标题为空 | 检查配置中的标题，或使用 `--title` 临时覆盖 |

## 文档语言

本项目不维护国际化文档，当前文档以中文优先。
