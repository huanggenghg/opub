# CLI 使用说明

项目现在提供一个统一的 CLI 入口：

```bash
hgsau publish
```

`publish_config.ini` 是主要控制文件，用于描述内容、素材路径、启用平台、账号文件、定时发布和平台元数据。命令行参数只用于临时覆盖本次运行的配置。

当前主线已接入：

- `douyin`
- `kuaishou`
- `xiaohongshu`
- `bilibili`
- `weibo`

实现说明：

- CLI 包装层很薄，只负责解析 `hgsau publish` 参数。
- `publish_all.py` 是统一发布引擎，负责读取配置、合并临时覆盖、运行环境预检、账号登录校验、发布和结果汇总。
- 如果需要给 OpenClaw、Codex 等 agent 使用，可参考仓库内 skill：`skills/hgsau-cli/`

## 安装 CLI 入口

在项目根目录安装一次：

```bash
uv pip install -e .
```

安装后就可以使用：

```bash
hgsau publish --help
```

## 快速开始

1. 编辑 `publish_config.ini`，配置内容、素材路径、启用平台和账号文件。
2. 执行统一发布入口：

```bash
hgsau publish
```

如需临时覆盖配置：

```bash
hgsau publish --platforms douyin,weibo --video videos/demo.mp4 --title "标题"
```

`hgsau publish` 会自动完成运行环境预检、账号登录校验、发布和结果汇总。

## 常用覆盖参数

常规使用建议写入 `publish_config.ini`。下面这些参数适合临时覆盖一次发布任务：

```bash
--config publish_config.ini
--platforms douyin,weibo
--video videos/demo.mp4
--title "示例标题"
--desc "示例简介"
--tags 运动,训练
--schedule "2026-03-24 21:30"
--start-from 5
--force
```

## 配置优先级

1. 默认读取 `publish_config.ini`。
2. `--config` 可以指定其他配置文件。
3. 其他命令行参数只覆盖本次运行，不会写回配置文件。

## 登录二维码说明

- 抖音、快手、小红书等平台登录过程中，CLI / uploader 可能会生成临时二维码图片。
- 对普通用户来说，可以直接打开该图片扫码。
- 对可操作本地文件的 agent 来说，不要只把图片路径告诉用户。
- 这类二维码图片本身就是给用户扫码的，agent 应优先直接展示/发送本地图片给用户。
- 如果 Bilibili 登录需要用户扫码，而当前环境不适合交互，请让用户在本地真实终端处理扫码。

## 运行时行为

`hgsau publish` 执行完整发布场景：

1. 读取 `publish_config.ini`。
2. 合并命令行临时覆盖参数。
3. 执行运行环境预检，包括必要的浏览器或平台依赖检查。
4. 校验启用平台对应账号是否已登录。
5. 按配置发布视频或图文内容。
6. 输出结果汇总，并用退出码表达整体结果。

## 文档语言

本项目不维护国际化文档，当前文档以中文优先。

后续维护 CLI 时，优先看统一 CLI 包装层、`publish_all.py`、`uploader/` 和 `skills/hgsau-cli/`。
