# 运行前提

这个 skill 默认假设当前环境已经具备：

- 已安装 `hgeng-sau`
- 可以调用 `sau` 命令
- 已为 `patchright` 安装 Chromium

## 安装

```bash
pip install hgeng-sau
```

## 安装 patchright 浏览器

```bash
patchright install chromium
```

国内镜像加速：

```bash
PLAYWRIGHT_DOWNLOAD_HOST="https://npmmirror.com/mirrors/playwright" patchright install chromium
```

## 环境检查

```bash
sau status
```

## 常见调用方式

### `sau` 已在 PATH 中

```bash
sau xiaohongshu --help
```

### 开发模式（仓库内）

```bash
uv pip install -e .
sau xiaohongshu --help
```

## 无头和有头模式

- 使用 `--headless` 表示无头模式
- 使用 `--headed` 表示有头模式
- 如果用户明确要求无头登录，也要预期 CLI 会通过控制台输出或临时图片路径提供二维码相关提示
- 如果登录过程中已经生成了本地二维码图片，agent 应优先直接把图片展示/发送给用户扫码，不要只告诉用户图片路径
