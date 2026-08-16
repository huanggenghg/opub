# Agent Bootstrap Prompt

这份文档是写给 `OpenClaw`、`Codex`、`Claude Code / cc` 这类 agent 客户端用户的。

目标不是让 agent 先通读整个仓库，而是先把 `social-auto-upload` 安装到可运行、可验证、可继续执行任务的状态。

当前主线已接入的平台：

- `douyin`（抖音）
- `xiaohongshu`（小红书）
- `kuaishou`（快手）
- `bilibili`（B站）
- `tencent`（微信视频号）
- `baijiahao`（百家号）
- `weibo`（微博，支持多账号）

以上平台均已通过真实发布端到端验证。TikTok 等国际化平台暂不在主线范围内。

## 这份文档解决什么问题

现在仓库里已经有：

- 安装说明
- CLI 文档
- 统一 CLI skill

但这些内容更偏向“agent 进入仓库之后怎么执行”。

这份文档补的是“用户第一次把仓库交给 agent 客户端时，应该怎么说”。

## 推荐使用方式

1. 把整个仓库给你的 agent 客户端。
2. 把下面这段启动提示词完整发给它。
3. 等 agent 完成安装和统一发布入口验证后，再继续给它下达登录、上传、定时发布等任务。

## 通用启动提示词

复制下面整段，发给你的 agent：

```text
你现在在一个名为 `social-auto-upload` 的仓库中工作。

这是一个多平台社交媒体自动发布项目。当前主线已经接入：

- `douyin`（抖音）
- `xiaohongshu`（小红书）
- `kuaishou`（快手）
- `bilibili`（B站）
- `tencent`（微信视频号）
- `baijiahao`（百家号）
- `weibo`（微博，支持多账号）

你的第一目标不是通读全部源码，也不是优先运行历史 examples，而是先把项目安装到“可运行、可验证、可继续执行任务”的状态。

请遵守以下规则：

1. 默认把仓库根目录视为当前工作目录。
2. 优先使用 `uv` 管理 Python 环境，不要默认回退到旧的 `requirements.txt`。
3. 优先使用当前主线 CLI：`hgsau`。
4. 优先参考这些文档：
   - `docs/install.md`
   - `docs/CLI.md`
   - `docs/update.md`
5. `publish_config.ini` 是主要控制文件。账号文件可以长期保留；内容、素材路径、启用平台、标题、简介、标签和定时发布是一次性任务字段，每次发布前都必须重新设置。
6. 如果需要 agent skill，优先参考 `skills/hgsau-cli/`。
7. 不要默认走历史 `examples/` 和旧 Web 路径，除非当前 CLI 主线不可用。
8. 如果登录流程生成二维码图片，不要只返回图片路径；请直接展示图片，或者明确告诉我该打开哪个本地图片文件扫码。
9. 如果是 Bilibili 登录，不要在非交互环境里强行代跑；应改为指导我在本地真实终端完成扫码。
10. 首次环境准备时，先预热安装 Patchright Chromium：
   `PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST="https://cdn.playwright.dev" patchright install chromium`
11. 安装完成后，请优先验证 `hgsau --help`。
12. 需要执行发布时，请先确认本次发布的平台、素材路径、标题、简介和标签都已经重新设置，然后运行：
   `hgsau`
13. `hgsau` 会自动完成运行环境预检、账号登录校验、发布和结果汇总，并在结束后清空一次性任务字段，避免下次沿用旧配置。
14. 完成后，请明确输出：
   - 你实际执行了哪些命令
   - 哪些验证通过了
   - 当前项目是否已经进入“可继续登录/上传”的状态
   - 推荐我下一步执行什么

如果过程中遇到错误，不要跳过，请先说明错误，再给出你准备采取的下一步动作。
```

## 安装完成后，你可以继续怎么说

下面这些是你可以继续发给 agent 的任务示例。

### 更新发布配置

```text
请帮我检查 `publish_config.ini`，把发布平台改成小红书，账号名用 `creator`，素材使用 `videos/demo.mp4`。
```

```text
请帮我把 `publish_config.ini` 改成定时发布，不要立即发布。
```

### 做一次 CLI 可用性检查

```text
请检查统一发布入口是否可用，并告诉我缺什么依赖。
```

### 做一次真实上传

```text
请按 `publish_config.ini` 帮我发布一次，发布前先说明将启用哪些平台和素材。
```

```text
请临时覆盖配置，只发布到抖音和微博，视频用 `videos/demo.mp4`，标题用 `标题`。
```

## OpenClaw / Codex / Claude Code 使用建议

### OpenClaw

- 适合直接粘贴上面的完整启动提示词
- 如果支持把仓库作为工作目录挂载进去，优先先挂载仓库，再发提示词
- 如果支持本地文件展示，登录二维码应让 agent 直接展示图片

### Codex

- 建议先让它完成 bootstrap，再继续发平台任务
- 让它优先使用 `docs/install.md`、`docs/CLI.md` 和 `skills/hgsau-cli/`
- 不要让它一开始自由探索整个仓库，否则容易走到历史路径

### Claude Code / cc

- 建议先让仓库成为当前 workspace
- 再发完整启动提示词
- 后续按“安装 -> 验证 -> 登录 -> 上传”顺序继续给任务

## 为什么不按平台拆多套提示词

因为这个项目现在已经有统一的 CLI 主线。

用户第一次把仓库交给 agent 时，更需要的是：

- agent 知道主入口是什么
- agent 知道应该优先走哪条路径
- agent 知道哪些是历史路径
- agent 安装完成后先给出明确验收结果

等进入执行阶段，再让 agent 根据你的实际目标去选择：

- `douyin`
- `xiaohongshu`
- `kuaishou`
- `bilibili`
- `tencent`
- `baijiahao`
- `weibo`

这样比给用户准备多套平台 prompt 更稳，也更容易维护。

## 快速开始

1. 编辑 `publish_config.ini`，配置内容、素材路径、启用平台和账号文件。
2. 执行统一发布入口：

```bash
hgsau
```

如需临时覆盖配置：

```bash
hgsau --platforms douyin,weibo --video videos/demo.mp4 --title "标题"
```

`hgsau` 会自动完成运行环境预检、账号登录校验、发布和结果汇总。

本项目不维护国际化文档，当前文档以中文优先。
