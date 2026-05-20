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
sau login --platform weibo --account <name>
sau publish --platforms weibo
```

### 开发模式（仓库内）

```bash
uv pip install -e .
sau login --platform weibo --account <name>
```

## 无头和有头模式

- `sau login --platform weibo --account <name> --headless` 无头模式
- 默认有头模式（微博登录通常需要扫码）
- 如果登录过程中生成了本地二维码图片，agent 应优先直接把图片展示/发送给用户扫码