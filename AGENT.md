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
- Prefer `publish_config.ini` plus `opub` over legacy example scripts
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

`publish_config.ini` is the primary control file. Account file mappings can
persist there, but enabled platforms, content, asset paths, tags, scheduling,
and other publish-task fields are one-time task state. Set them explicitly for
each publish run; `opub` resets those task fields after it runs.

## 快速开始

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

## Runtime Notes

- Command-line options are temporary overrides for values in
  `publish_config.ini`.
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
- `publish_all.py` owns config loading, runtime preflight, account login checks,
  publishing, and summary output.
- Browser automation lives under `uploader/` and related utility modules.
- For TestPyPI uploads, first look for the local token file
  `.secrets/testpypi.token` and use it as the Twine API token
  (`TWINE_USERNAME=__token__`). Never print or commit the token; `.secrets/` is
  intentionally gitignored.
- `requirements.txt` is kept mostly for legacy compatibility; do not prefer it
  for normal setup.
- Existing Web code is retained but is not the current mainline path.
