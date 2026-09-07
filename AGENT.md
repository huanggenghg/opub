# AGENT.md

This file is the project bootstrap guide for AI coding agents working in this
repository.

## Project

`opub` is a multi-platform social media publishing automation
project. The current mainline workflow is the unified Python CLI entrypoint
`opub`.

Mainline platforms:

- `douyin`
- `kuaishou`
- `xiaohongshu`
- `bilibili`

## First Principles

- Treat the repository root as the working directory.
- Prefer `uv` for Python environment and dependency management.
- Prefer `opub` CLI over legacy example scripts
  or platform-specific command flows.
- Do not default to historical `examples/` or old Web flows unless the CLI path
  is unavailable for the task.
- Keep user changes intact. Do not revert unrelated local changes.
- If a login flow creates a QR code image, show the image to the user or clearly
  identify the exact local file to open.
- For Bilibili login, prefer telling the user to run it in a real local terminal
  if the current environment is not interactive enough for QR login.

## Recommended Setup

Create and activate the virtual environment:

```bash
uv venv
source .venv/bin/activate
```

Install the project in editable mode:

```bash
uv pip install -e .
```

Install Patchright Chromium for browser automation:

```bash
PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST="https://cdn.playwright.dev" patchright install chromium
```

If `conf.py` does not exist, copy the example:

```bash
cp conf.example.py conf.py
```

## Required Smoke Checks

After setup, verify the unified CLI entrypoint:

```bash
opub --help
```

Report:

- Commands actually executed
- Which checks passed or failed
- Whether the repo is ready for login/upload work
- The recommended next command for the user's goal

## Core CLI Usage

`opub` is stateless: every publish run passes all settings (enabled platforms,
content, asset paths, tags, scheduling) as command-line arguments. Account
files are auto-discovered from the `cookies/` directory under the data
directory.

每个平台只自动发现一个规范账号文件；未发现账号时，发布流程会引导扫码并写入对应上传器目录的 `account.json`。

## 快速开始

执行统一发布入口（全部发布信息通过命令行参数传入）：

```bash
opub --platforms douyin,weibo --video videos/demo.mp4 --title "标题"
```

`opub` 会自动完成运行环境预检、账号登录校验、发布和结果汇总。

## 付费许可契约

`opub 0.x 创始版`售价 ¥9.90，在爱发电商品页购买：<https://afdian.com/item/69bf71f0a9f511f1bc065254001e7c00>。爱发电发放的激活码首次兑换后绑定一个设备，不需账号；许可不迁移、不解绑、不提供换机重置，新电脑重新购买。该许可覆盖 `0.x`，已安装的 `0.x` 版本可永久离线使用；未来大版本需要单独购买。支付方式由用户在爱发电页面选择。公开 Python 包是诚实用户门禁，属于非强 DRM。

```bash
opub --license-status
opub --activate
opub --activate --code OPUB0-ABCDE-FGHJK-MNPQR-STVWX-YZ234-56789
```

发布前静默执行 `opub --license-status`。若退出码为 13，保留已经确认的发布输入，运行 `opub --activate` 打开购买页；用户取得激活码后运行带 `--code` 的命令。激活成功后自动继续同一个发布任务，不重复问参数。不得在用户可见消息、异常或 internal log 中展示完整激活码或设备 hash。详见 [docs/CLI.md](docs/CLI.md)。

许可错误映射：

| 错误码 | 含义 | 建议 |
| --- | --- | --- |
| `LIC-001` | 尚未激活 | 执行激活命令 |
| `LIC-002` | 损坏签名 | 联系支持并提供错误码 |
| `LIC-003` | 许可属于其他设备 | 新电脑重新购买 |
| `LIC-004` | 稳定设备标识不可用 | 联系支持并提供错误码 |
| `LIC-011` | 服务不可用 | 稍后重试 |
| `LIC-013` | 激活码无效 | 检查激活码后重新激活 |
| `LIC-014` | 激活码已绑定其他设备 | 当前电脑重新购买 |
| `LIC-015` | 当前客户端版本不适用 | 升级或切换到 opub 0.x 后重试 |

## Runtime Notes

- The project does not maintain internationalized docs. Current documentation is
  Chinese-first, with agent bootstrap notes kept concise where useful.

## Useful References

- `docs/install.md`
- `docs/CLI.md`
- `docs/update.md`
- `docs/agent-bootstrap.md`
- `skills/opub-cli/`

## Notes For Maintenance

- The CLI wrapper is intentionally thin around `opub`.
- The `publish/` package owns runtime preflight, account login checks,
  publishing, and summary output. `publish_all.py` is a thin backward-compat
  shell re-exporting it.
- Browser automation lives under `uploader/` and related utility modules.
- For TestPyPI uploads, first look for the local token file
  `.secrets/testpypi.token` and use it as the Twine API token
  (`TWINE_USERNAME=__token__`). Never print or commit the token; `.secrets/` is
  intentionally gitignored.
- `requirements.txt` is kept mostly for legacy compatibility; do not prefer it
  for normal setup.
- Existing Web code is retained but is not the current mainline path.
