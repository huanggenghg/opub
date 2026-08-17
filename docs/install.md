# 安装说明

这个文档分成两部分：

- `For Humans`：给正常使用仓库的开发者、创作者、CLI 用户看
- `For AI Agents`：给 OpenClaw、Codex、Claude Code 一类 agent 看

如果你是“正在使用 agent 客户端的人”，想先给 agent 一段启动提示词，而不是直接阅读下面的执行细节，先看：

- [Agent Bootstrap Prompt](./agent-bootstrap.md)

## For Humans

### 1. 克隆项目

```bash
git clone https://github.com/dreammis/social-auto-upload.git
cd social-auto-upload
```

### 2. 创建虚拟环境

推荐使用 `uv`：

```bash
uv venv
source .venv/bin/activate
```

### 3. 安装主线依赖

当前主线依赖已经放到 `pyproject.toml`，推荐直接执行：

```bash
uv pip install -e .
```

安装完成后，会注册 `opub` 命令。

### 4. 安装 patchright Chromium

当前主线使用 `patchright` 驱动浏览器。

有代理环境时，推荐使用 Playwright 官方 CDN 安装 Chromium：

```bash
PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST="https://cdn.playwright.dev" patchright install chromium
```

如果你使用团队自建镜像，可以把 `PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST` 指向自己的制品仓库。
自建镜像需要保持 Playwright 的目录结构，例如包含 `builds/cft/...`。

### 5. 配置发布控制文件

`publish_config.ini` 是主要控制文件，用于配置内容、素材路径、启用平台、账号文件、定时发布和平台元数据。

### 6. 配置 conf.py

复制一份配置：

```bash
cp conf.example.py conf.py
```

Windows 也可以直接手动复制并重命名。

当前通常还会用到这些配置项：

- `LOCAL_CHROME_PATH`
- `LOCAL_CHROME_HEADLESS`
- `DEBUG_MODE`

### 7. 快速开始

1. 编辑 `publish_config.ini`，配置内容、素材路径、启用平台和账号文件。
2. 执行统一发布入口：

```bash
opub
```

如需临时覆盖配置：

```bash
opub --platforms douyin,weibo --video videos/demo.mp4 --title "标题"
```

`opub` 会自动完成运行环境预检、账号登录校验、发布和结果汇总。

如果命令找不到，优先确认：

- 当前虚拟环境是否已激活
- 是否执行过 `uv pip install -e .`

### 8. 补充说明

- `creator` 之类的名字只是示例值，真正传的是用户自定义的账号名
- 一个 `account_name` 对应一个账号文件，可以准备多个账号并发使用
- 浏览器平台统一元数据约定：
- 视频使用 `title + desc + tags`
- 图文使用 `title + note + tags`
- 用户不需要手动安装 `biliup`
- 首次运行相关发布任务时，程序会自动下载 `biliup`
- 后续运行会自动检查上游 release 并自动更新
- 如果国内网络访问 GitHub Release 较慢，可先用 `https://gh-proxy.com/` 或 `https://gh-proxy.org/` 辅助访问对应 release 地址排障
- 示例：
  - `https://gh-proxy.org/https://github.com/biliup/biliup/releases/download/v1.1.29/biliupR-v1.1.29-aarch64-linux.tar.xz`
- 本项目不维护国际化文档，当前文档以中文优先。

## For AI Agents

如果你是一个可执行命令的 agent，请优先按下面顺序处理：

1. 先假设仓库根目录就是当前工作目录
2. 优先使用 `uv` 管理环境，不要默认回退到旧的 `requirements.txt`
3. 安装命令优先使用：

```bash
uv pip install -e .
```

4. 如需浏览器驱动，优先使用：

```bash
PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST="https://cdn.playwright.dev" patchright install chromium
```

5. 安装完成后，优先检查 `opub --help`
6. 引导用户编辑 `publish_config.ini`，确认内容、素材路径、启用平台和账号文件
7. 如果用户的目标是登录、账号校验、视频上传、图文上传或定时发布，优先走统一发布入口：

```bash
opub
```

如需临时覆盖配置：

```bash
opub --platforms douyin,weibo --video videos/demo.mp4 --title "标题"
```

`opub` 会自动完成运行环境预检、账号登录校验、发布和结果汇总。

8. 如果用户明确在使用 skill 系统，再引导其阅读：

- `skills/opub-cli/SKILL.md`

### 对 agent 的额外说明

- 当登录流程生成本地二维码图片时，不要只把图片路径发给用户
- 这类二维码图片本身就是给用户扫码的，agent 应优先直接展示/发送本地图片给用户扫码
- 如果环境支持查看本地图片，优先用查看图片能力把二维码展示出来；路径只作为补充信息
- Bilibili 登录当前不建议 agent 在非交互环境里直接代跑
- 如果 Bilibili 登录需要用户扫码，而当前环境不适合交互，请让用户在本地真实终端处理扫码；如果二维码显示不完整，再提示用户打开 `qrcode.png`
- `requirements.txt` 目前是历史兼容文件，不是主安装入口
- `uploader/` 是核心实现目录
- 当前 CLI 主入口只保留统一发布包装层
- `publish_all.py` 是统一发布引擎
- `docs/legacy-web.md` 是历史 Web 版本说明，不保证当前可用
- Bilibili 首次运行时可能自动下载 `biliup`
