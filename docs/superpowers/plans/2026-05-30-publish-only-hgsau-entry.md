# Publish-Only Hgsau Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old multi-command `sau` CLI with one config-driven `hgsau publish` workflow that performs runtime preflight, account login checks, publishing, and summary output.

**Architecture:** `hgsau_cli.py` becomes a thin parser and dispatcher. `publish_all.py` becomes the single publishing engine and owns config loading, override merging, runtime preflight, account login checks, platform dispatch, and exit-code decisions. The project does not provide compatibility for the old `sau` command or old platform-specific CLI commands.

**Tech Stack:** Python 3.9+, argparse, configparser, asyncio, setuptools console scripts, unittest/pytest, patchright.

---

## File Structure

- Rename: `sau_cli.py` -> `hgsau_cli.py`
  - Responsibility: parse `hgsau publish` arguments and call `publish_all.run_publish`.
- Modify: `publish_all.py`
  - Responsibility: own the unified publish engine, runtime preflight, config overrides, account login checks, platform dispatch, and final exit code.
- Modify: `pyproject.toml`
  - Responsibility: rename distribution package to `hgsau`, expose only `hgsau = "hgsau_cli:main"`, and include `hgsau_cli` in `py-modules`.
- Replace tests:
  - Remove/replace platform-specific CLI expectations in `tests/test_sau_browser_cli.py` and `tests/test_sau_bilibili_cli.py`.
  - Create `tests/test_hgsau_cli.py` for CLI parser/dispatcher/package naming.
  - Create `tests/test_publish_engine.py` for config overrides, preflight, account login, failure continuation, and exit code.
- Modify docs:
  - `AGENT.md`
  - `README.md`
  - `docs/install.md`
  - `docs/CLI.md`
  - `docs/agent-bootstrap.md`

---

### Task 1: Rename Package And CLI Module

**Files:**
- Rename: `sau_cli.py` -> `hgsau_cli.py`
- Modify: `pyproject.toml`
- Create: `tests/test_hgsau_cli.py`
- Remove in this task: `tests/test_sau_browser_cli.py`, `tests/test_sau_bilibili_cli.py`

- [ ] **Step 1: Write failing package/rename tests**

Create `tests/test_hgsau_cli.py` with:

```python
import unittest
from pathlib import Path
import tomllib

import hgsau_cli


class HgsauPackagingTests(unittest.TestCase):
    def test_pyproject_exposes_only_hgsau_console_script(self):
        data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(data["project"]["name"], "hgsau")
        self.assertEqual(data["project"]["scripts"]["hgsau"], "hgsau_cli:main")
        self.assertNotIn("sau", data["project"]["scripts"])

    def test_hgsau_cli_module_exists(self):
        self.assertTrue(hasattr(hgsau_cli, "build_parser"))
        self.assertTrue(hasattr(hgsau_cli, "main"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the failing rename test**

Run:

```bash
.venv/bin/python -m pytest tests/test_hgsau_cli.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'hgsau_cli'` or package-name/script assertions failing.

- [ ] **Step 3: Rename the CLI module**

Run:

```bash
mv sau_cli.py hgsau_cli.py
```

- [ ] **Step 4: Update `pyproject.toml` package metadata**

Change these entries:

```toml
[project]
name = "hgsau"

[project.scripts]
hgsau = "hgsau_cli:main"

[tool.setuptools]
py-modules = ["conf", "hgsau_cli", "publish_all"]
```

Remove the old `sau = "sau_cli:main"` script entry and remove `sau_cli` from `py-modules`.

- [ ] **Step 5: Remove old CLI tests that encode removed behavior**

Run:

```bash
rm tests/test_sau_browser_cli.py tests/test_sau_bilibili_cli.py
```

These tests assert the old platform-specific CLI and must not remain as expected behavior.

- [ ] **Step 6: Run the rename test again**

Run:

```bash
.venv/bin/python -m pytest tests/test_hgsau_cli.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml hgsau_cli.py tests/test_hgsau_cli.py
git rm sau_cli.py tests/test_sau_browser_cli.py tests/test_sau_bilibili_cli.py
git commit -m "refactor: rename cli entry to hgsau"
```

---

### Task 2: Reduce CLI Parser To `hgsau publish`

**Files:**
- Modify: `hgsau_cli.py`
- Modify: `tests/test_hgsau_cli.py`

- [ ] **Step 1: Add failing parser tests**

Append to `tests/test_hgsau_cli.py`:

```python
from unittest.mock import AsyncMock, patch


class HgsauParserTests(unittest.TestCase):
    def test_parser_accepts_publish_defaults(self):
        parser = hgsau_cli.build_parser()
        args = parser.parse_args(["publish"])

        self.assertEqual(args.command, "publish")
        self.assertEqual(args.config, "publish_config.ini")
        self.assertIsNone(args.platforms)
        self.assertIsNone(args.video)

    def test_parser_accepts_publish_overrides(self):
        parser = hgsau_cli.build_parser()
        args = parser.parse_args(
            [
                "publish",
                "--config",
                "my.ini",
                "--platforms",
                "douyin,weibo",
                "--video",
                "videos/demo.mp4",
                "--title",
                "标题",
                "--desc",
                "描述",
                "--tags",
                "标签1,标签2",
                "--schedule",
                "2026-05-30 21:30",
                "--start-from",
                "3",
                "--force",
            ]
        )

        self.assertEqual(args.config, "my.ini")
        self.assertEqual(args.platforms, "douyin,weibo")
        self.assertEqual(args.video, "videos/demo.mp4")
        self.assertEqual(args.title, "标题")
        self.assertEqual(args.desc, "描述")
        self.assertEqual(args.tags, "标签1,标签2")
        self.assertEqual(args.schedule.strftime("%Y-%m-%d %H:%M"), "2026-05-30 21:30")
        self.assertEqual(args.start_from, 3)
        self.assertTrue(args.force)

    def test_parser_rejects_removed_platform_command(self):
        parser = hgsau_cli.build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args(["douyin", "upload-video"])

    def test_dispatch_calls_publish_engine(self):
        parser = hgsau_cli.build_parser()
        args = parser.parse_args(["publish", "--platforms", "weibo", "--title", "标题"])

        with patch("publish_all.run_publish", new=AsyncMock(return_value=0)) as run_publish:
            code = hgsau_cli.run_async(args)

        self.assertEqual(code, 0)
        call = run_publish.await_args
        self.assertEqual(call.args[0], "publish_config.ini")
        self.assertEqual(call.args[1].platforms, "weibo")
        self.assertEqual(call.args[1].title, "标题")
```

- [ ] **Step 2: Run parser tests and confirm failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_hgsau_cli.py -q
```

Expected: fail because `hgsau_cli.py` still exposes old parser branches or lacks `run_async`.

- [ ] **Step 3: Replace `hgsau_cli.py` with thin CLI wrapper**

Replace `hgsau_cli.py` content with:

```python
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from typing import Sequence

from publish_all import PublishOverrides
import publish_all

SCHEDULE_FORMAT = "%Y-%m-%d %H:%M"


def schedule_value(raw: str) -> datetime:
    try:
        return datetime.strptime(raw, SCHEDULE_FORMAT)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"时间格式必须为 YYYY-MM-DD HH:MM: {raw}") from exc


def build_parser() -> argparse.ArgumentParser:
    schedule_help = SCHEDULE_FORMAT.replace("%", "%%")
    parser = argparse.ArgumentParser(
        prog="hgsau",
        description="hgsau 统一发布工具。",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    publish_parser = subparsers.add_parser("publish", help="按 publish_config.ini 执行统一发布")
    publish_parser.add_argument("--config", default="publish_config.ini", help="配置文件路径，默认 publish_config.ini")
    publish_parser.add_argument("--platforms", default=None, help="覆盖启用平台，多个平台用英文逗号分隔")
    publish_parser.add_argument("--video", default=None, help="覆盖视频文件或目录路径")
    publish_parser.add_argument("--title", default=None, help="覆盖标题")
    publish_parser.add_argument("--desc", default=None, help="覆盖描述")
    publish_parser.add_argument("--tags", default=None, help="覆盖标签，多个标签用英文逗号分隔")
    publish_parser.add_argument("--schedule", type=schedule_value, default=None, help=f"覆盖定时发布时间，格式 {schedule_help}")
    publish_parser.add_argument("--start-from", type=int, default=None, help="从第几个视频开始发布，1 表示从第一个开始")
    publish_parser.add_argument("--force", action="store_true", help="强制重新生成视频配置")
    return parser


async def dispatch(args: argparse.Namespace) -> int:
    if args.command != "publish":
        raise ValueError(f"不支持的命令: {args.command}")

    overrides = PublishOverrides(
        platforms=args.platforms,
        video=args.video,
        title=args.title,
        desc=args.desc,
        tags=args.tags,
        schedule=args.schedule,
        start_from=args.start_from,
        force=args.force,
    )
    return await publish_all.run_publish(args.config, overrides)


def run_async(args: argparse.Namespace) -> int:
    return asyncio.run(dispatch(args))


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_async(args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run parser tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_hgsau_cli.py -q
```

Expected: fail because `publish_all.PublishOverrides` and `publish_all.run_publish` are not implemented yet, or pass if Task 3 has already been implemented in the same execution batch.

- [ ] **Step 5: Commit after Task 3 provides engine symbols**

Do not commit Task 2 alone if tests fail due to missing `PublishOverrides` or `run_publish`. Commit Task 2 and Task 3 together after Task 3 is green.

---

### Task 3: Add Unified Publish Engine API

**Files:**
- Modify: `publish_all.py`
- Create: `tests/test_publish_engine.py`
- Modify: `tests/test_hgsau_cli.py`

- [ ] **Step 1: Write failing tests for overrides and engine call shape**

Create `tests/test_publish_engine.py`:

```python
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import publish_all
from publish_all import PublishOverrides


class PublishOverridesTests(unittest.TestCase):
    def test_apply_overrides_merges_cli_values(self):
        params = {
            "content_type": "video",
            "title": "",
            "desc": "",
            "tags": [],
            "video_file": "",
            "images": [],
            "publish_strategy": "immediate",
            "publish_time": None,
            "enabled_platforms": [],
            "platforms": {},
            "convert_to_video": False,
            "video_duration": 5,
            "start_from": 1,
        }
        schedule = datetime(2026, 5, 30, 21, 30)
        overrides = PublishOverrides(
            platforms="douyin,weibo",
            video="videos/demo.mp4",
            title="标题",
            desc="描述",
            tags="标签1,标签2",
            schedule=schedule,
            start_from=3,
            force=True,
        )

        merged = publish_all.apply_overrides(params, overrides)

        self.assertEqual(merged["enabled_platforms"], ["douyin", "weibo"])
        self.assertEqual(merged["video_file"], "videos/demo.mp4")
        self.assertEqual(merged["title"], "标题")
        self.assertEqual(merged["desc"], "描述")
        self.assertEqual(merged["tags"], ["标签1", "标签2"])
        self.assertEqual(merged["publish_strategy"], "scheduled")
        self.assertEqual(merged["publish_time"], schedule)
        self.assertEqual(merged["start_from"], 3)
        self.assertTrue(merged["force"])

    def test_run_publish_returns_one_when_no_platforms_enabled(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "publish_config.ini"
            config_path.write_text(
                "[common]\n"
                "content_type = video\n"
                "title = 标题\n"
                "desc = 描述\n"
                "tags =\n"
                "video_file = videos/demo.mp4\n"
                "images =\n"
                "publish_strategy = immediate\n"
                "publish_time =\n"
                "convert_to_video = false\n"
                "video_duration = 5\n"
                "start_from = 1\n"
                "\n"
                "[platforms]\n"
                "enabled =\n",
                encoding="utf-8",
            )

            with patch("publish_all.runtime_preflight", new=AsyncMock(return_value=True)):
                code = publish_all.run_publish_sync(str(config_path), PublishOverrides())

        self.assertEqual(code, 1)

    def test_run_publish_can_start_from_cli_overrides_without_config_file(self):
        overrides = PublishOverrides(
            platforms="douyin",
            video="videos/demo.mp4",
            title="标题",
        )

        with patch("publish_all.runtime_preflight", new=AsyncMock(return_value=True)), \
             patch("publish_all.run_publish_with_params", new=AsyncMock(return_value=0)) as run_with_params:
            code = publish_all.run_publish_sync("missing.ini", overrides)

        self.assertEqual(code, 0)
        params = run_with_params.await_args.args[0]
        self.assertEqual(params["enabled_platforms"], ["douyin"])
        self.assertEqual(params["video_file"], "videos/demo.mp4")
        self.assertEqual(params["title"], "标题")
```

- [ ] **Step 2: Run publish engine tests and confirm failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_publish_engine.py -q
```

Expected: fail because `PublishOverrides`, `apply_overrides`, `default_params_from_overrides`, and `run_publish_sync` are missing.

- [ ] **Step 3: Add `PublishOverrides`, path-aware config loading, override merging, and sync wrapper**

Add near the top of `publish_all.py`, after imports:

```python
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class PublishOverrides:
    platforms: Optional[str] = None
    video: Optional[str] = None
    title: Optional[str] = None
    desc: Optional[str] = None
    tags: Optional[str] = None
    schedule: Optional[datetime] = None
    start_from: Optional[int] = None
    force: bool = False
```

Update `read_config` so absolute config paths work:

```python
def read_config(config_file: str = "publish_config.ini") -> dict:
    """读取配置文件"""
    config_path = Path(config_file)
    if not config_path.is_absolute():
        config_path = BASE_DIR / config_file
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    parser = configparser.ConfigParser()
    parser.read(config_path, encoding="utf-8")

    return {
        "common": dict(parser["common"]),
        "platforms": dict(parser["platforms"]),
    }
```

Add after `parse_config`:

```python
def default_params_from_overrides() -> dict[str, Any]:
    return {
        "content_type": "video",
        "title": "",
        "desc": "",
        "tags": [],
        "video_file": "",
        "images": [],
        "publish_strategy": "immediate",
        "publish_time": None,
        "enabled_platforms": [],
        "platforms": {},
        "convert_to_video": False,
        "video_duration": 5,
        "start_from": 1,
    }


def apply_overrides(params: dict[str, Any], overrides: PublishOverrides) -> dict[str, Any]:
    merged = dict(params)
    if overrides.platforms is not None:
        merged["enabled_platforms"] = [p.strip() for p in overrides.platforms.split(",") if p.strip()]
    if overrides.video is not None:
        merged["video_file"] = overrides.video
    if overrides.title is not None:
        merged["title"] = overrides.title
    if overrides.desc is not None:
        merged["desc"] = overrides.desc
    if overrides.tags is not None:
        merged["tags"] = [t.strip() for t in overrides.tags.split(",") if t.strip()]
    if overrides.schedule is not None:
        merged["publish_strategy"] = "scheduled"
        merged["publish_time"] = overrides.schedule
    if overrides.start_from is not None:
        merged["start_from"] = overrides.start_from
    if overrides.force:
        merged["force"] = True
    return merged
```

Add temporary runtime preflight and run wrappers near the bottom, before `main`:

```python
async def runtime_preflight() -> bool:
    return True


async def run_publish(config_file: str = "publish_config.ini", overrides: Optional[PublishOverrides] = None) -> int:
    overrides = overrides or PublishOverrides()
    if not await runtime_preflight():
        return 1

    try:
        config = read_config(config_file)
        params = parse_config(config)
    except FileNotFoundError as exc:
        if overrides.platforms is None or overrides.video is None:
            print(f"错误: {exc}", file=sys.stderr)
            print("请提供配置文件，或同时提供 --platforms 和 --video", file=sys.stderr)
            return 1
        params = default_params_from_overrides()

    params = apply_overrides(params, overrides)
    if not params["enabled_platforms"]:
        print("错误: 未配置启用平台", file=sys.stderr)
        return 1

    return await run_publish_with_params(params)


def run_publish_sync(config_file: str = "publish_config.ini", overrides: Optional[PublishOverrides] = None) -> int:
    return asyncio.run(run_publish(config_file, overrides))
```

Move the body of current `main()` into a new function:

```python
async def run_publish_with_params(params: dict[str, Any]) -> int:
    if params["content_type"] == "note" and params["convert_to_video"]:
        if not params["images"]:
            print("错误: 图文转视频需要提供图片", file=sys.stderr)
            return 1
        print("正在将图片转换为视频")
        try:
            from utils.image_to_video import convert_images_to_video_for_publish

            video_path = convert_images_to_video_for_publish(
                image_paths=params["images"],
                title=params["title"],
                duration=params["video_duration"],
            )
            params["content_type"] = "video"
            params["video_file"] = video_path
            print(f"[OK] 视频已生成: {video_path}\n")
        except Exception as exc:
            print(f"[ERROR] 图片转视频失败: {exc}", file=sys.stderr)
            return 1

    video_files = get_video_files(params["video_file"])
    if not video_files:
        print("错误: 未找到视频文件", file=sys.stderr)
        return 1

    print(f"找到 {len(video_files)} 个视频文件:")
    for video_file in video_files:
        print(f"  - {os.path.basename(video_file)}")
    print()

    all_results = {}
    start_from = params.get("start_from", 1)
    if start_from > 1:
        print(f"\n[SKIP] 从第 {start_from} 个视频开始发布（跳过前 {start_from - 1} 个）\n")

    for video_idx, video_file in enumerate(video_files, 1):
        if video_idx < start_from:
            continue

        print(f"\n========== 视频 [{video_idx}/{len(video_files)}] ==========")
        print(f"文件: {os.path.basename(video_file)}")

        title, desc = get_video_content(video_file, params["title"], params["desc"])
        video_params = {**params, "video_file": video_file, "title": title, "desc": desc}
        print_header(video_params)

        results = await publish_one_item(video_params)
        print_results(results)
        all_results[video_file] = results

    print("\n========== 总体发布汇总 ==========")
    success_count = sum(1 for results in all_results.values() for result in results.values() if result["success"])
    fail_count = sum(1 for results in all_results.values() for result in results.values() if not result["success"])
    print(f"成功: {success_count} 次")
    print(f"失败: {fail_count} 次")
    return 0 if fail_count == 0 else 1
```

Add `publish_one_item` extracted from the existing per-platform loop:

```python
async def publish_one_item(video_params: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results = {}
    total = len(video_params["enabled_platforms"])
    for index, platform in enumerate(video_params["enabled_platforms"], 1):
        platform_name = PLATFORM_NAMES.get(platform, platform)
        account_key = f"{platform}_account"
        account_file_str = video_params["platforms"].get(account_key, "")
        account_files = [account.strip() for account in account_file_str.split(",") if account.strip()]

        if not account_files:
            print(f"[{index}/{total}] 发布到 {platform_name}")
            results[platform] = {"success": False, "message": f"未配置 {platform} 账号"}
            print("  失败: 未配置账号")
            continue

        for account_index, account_file in enumerate(account_files):
            result_key = platform if len(account_files) == 1 else f"{platform}_{account_index + 1}"
            if len(account_files) > 1:
                print(f"[{index}/{total}] 发布到 {platform_name} (账号 {account_index + 1}/{len(account_files)})")
            else:
                print(f"[{index}/{total}] 发布到 {platform_name}")

            platform_params = {**video_params, "account_file": account_file}
            result = await publish_to_platform(platform, platform_params)
            results[result_key] = result
            if result["success"]:
                print("  成功")
            else:
                print(f"  失败: {result['message']}")
    return results
```

Update `main()`:

```python
async def main():
    return await run_publish()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Step 4: Run tests from Tasks 2 and 3**

Run:

```bash
.venv/bin/python -m pytest tests/test_hgsau_cli.py tests/test_publish_engine.py -q
```

Expected: pass for parser, packaging, override merge, and no-platform failure.

- [ ] **Step 5: Commit Tasks 2 and 3 together if Task 2 was waiting**

```bash
git add hgsau_cli.py publish_all.py tests/test_hgsau_cli.py tests/test_publish_engine.py
git commit -m "refactor: route hgsau publish through unified engine"
```

---

### Task 4: Implement Runtime Environment Preflight

**Files:**
- Modify: `publish_all.py`
- Modify: `tests/test_publish_engine.py`

- [ ] **Step 1: Add failing runtime preflight tests**

Append to `tests/test_publish_engine.py`:

```python
class RuntimePreflightTests(unittest.TestCase):
    def test_runtime_preflight_installs_missing_chromium(self):
        with patch("publish_all.patchright_chromium_installed", return_value=False), \
             patch("publish_all.install_patchright_chromium", return_value=True) as install:
            ok = publish_all.run_async_for_test(publish_all.runtime_preflight())

        self.assertTrue(ok)
        install.assert_called_once()

    def test_runtime_preflight_fails_when_chromium_install_fails(self):
        with patch("publish_all.patchright_chromium_installed", return_value=False), \
             patch("publish_all.install_patchright_chromium", return_value=False):
            ok = publish_all.run_async_for_test(publish_all.runtime_preflight())

        self.assertFalse(ok)
```

- [ ] **Step 2: Run runtime preflight tests and confirm failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_publish_engine.py::RuntimePreflightTests -q
```

Expected: fail because helper functions are missing.

- [ ] **Step 3: Add runtime preflight helpers**

Add to `publish_all.py`:

```python
import subprocess
from importlib import import_module


def run_async_for_test(coro):
    return asyncio.run(coro)


def patchright_chromium_installed() -> bool:
    try:
        patchright = import_module("patchright")
    except ImportError:
        return False

    package_root = Path(patchright.__file__).resolve().parent
    browsers_json = package_root / "driver" / "package" / "browsers.json"
    if not browsers_json.exists():
        return False

    try:
        data = json.loads(browsers_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False

    revisions = [
        browser["revision"]
        for browser in data.get("browsers", [])
        if browser.get("name") == "chromium" and browser.get("installByDefault", True)
    ]
    if not revisions:
        return False

    revision = revisions[0]
    candidates = [
        os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""),
        str(Path.home() / "Library" / "Caches" / "ms-playwright"),
        str(Path.home() / ".cache" / "ms-playwright"),
    ]
    return any(candidate and (Path(candidate) / f"chromium-{revision}").exists() for candidate in candidates)


def install_patchright_chromium() -> bool:
    env = dict(os.environ)
    env.setdefault("PLAYWRIGHT_DOWNLOAD_HOST", "https://npmmirror.com/mirrors/playwright")
    result = subprocess.run(
        [sys.executable, "-m", "patchright", "install", "chromium"],
        env=env,
        check=False,
    )
    return result.returncode == 0


async def runtime_preflight() -> bool:
    print("运行环境预检")
    if sys.version_info < (3, 9):
        print("错误: Python 版本必须 >= 3.9", file=sys.stderr)
        return False

    try:
        import_module("patchright")
    except ImportError:
        print("错误: 缺少 patchright 依赖，请先安装项目依赖", file=sys.stderr)
        return False

    if patchright_chromium_installed():
        print("浏览器驱动: Patchright Chromium 已安装")
        return True

    print("浏览器驱动: Patchright Chromium 未安装，正在自动安装")
    if install_patchright_chromium():
        print("浏览器驱动: Patchright Chromium 安装完成")
        return True

    print("错误: Patchright Chromium 自动安装失败", file=sys.stderr)
    return False
```

- [ ] **Step 4: Run runtime preflight tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_publish_engine.py::RuntimePreflightTests -q
```

Expected: pass.

- [ ] **Step 5: Run all engine and CLI tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_hgsau_cli.py tests/test_publish_engine.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add publish_all.py tests/test_publish_engine.py
git commit -m "feat: add publish runtime preflight"
```

---

### Task 5: Separate Account Login Checks From Runtime Preflight

**Files:**
- Modify: `publish_all.py`
- Modify: `tests/test_publish_engine.py`

- [ ] **Step 1: Add failing account-flow tests**

Append to `tests/test_publish_engine.py`:

```python
class AccountLoginFlowTests(unittest.TestCase):
    def test_publish_one_item_triggers_login_before_publish(self):
        params = {
            "enabled_platforms": ["douyin"],
            "platforms": {"douyin_account": "cookies/douyin.json"},
            "content_type": "video",
            "video_file": "videos/demo.mp4",
            "title": "标题",
            "desc": "描述",
            "tags": [],
            "publish_strategy": "immediate",
            "publish_time": None,
            "convert_to_video": False,
        }

        with patch("publish_all.ensure_account_login", new=AsyncMock(return_value=True)) as ensure_login, \
             patch("publish_all.publish_to_platform", new=AsyncMock(return_value={"success": True, "message": "发布成功"})) as publish:
            results = publish_all.run_async_for_test(publish_all.publish_one_item(params))

        ensure_login.assert_awaited_once_with("douyin", "cookies/douyin.json")
        publish.assert_awaited_once()
        self.assertTrue(results["douyin"]["success"])

    def test_publish_one_item_skips_publish_when_login_fails(self):
        params = {
            "enabled_platforms": ["douyin"],
            "platforms": {"douyin_account": "cookies/douyin.json"},
            "content_type": "video",
            "video_file": "videos/demo.mp4",
            "title": "标题",
            "desc": "描述",
            "tags": [],
            "publish_strategy": "immediate",
            "publish_time": None,
            "convert_to_video": False,
        }

        with patch("publish_all.ensure_account_login", new=AsyncMock(return_value=False)), \
             patch("publish_all.publish_to_platform", new=AsyncMock(return_value={"success": True, "message": "发布成功"})) as publish:
            results = publish_all.run_async_for_test(publish_all.publish_one_item(params))

        publish.assert_not_awaited()
        self.assertFalse(results["douyin"]["success"])
        self.assertIn("登录失败", results["douyin"]["message"])
```

- [ ] **Step 2: Run account-flow tests and confirm failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_publish_engine.py::AccountLoginFlowTests -q
```

Expected: fail because `publish_one_item` does not call `ensure_account_login`.

- [ ] **Step 3: Add `ensure_account_login` and wire it into `publish_one_item`**

Add to `publish_all.py`:

```python
async def ensure_account_login(platform: str, account_file: str) -> bool:
    resolved_account = resolve_path(account_file)
    return await ensure_login(platform, resolved_account)
```

Update the account loop inside `publish_one_item` before `publish_to_platform`:

```python
            if not await ensure_account_login(platform, account_file):
                results[result_key] = {"success": False, "message": f"登录失败: {platform}"}
                print("  失败: 登录失败")
                continue

            platform_params = {**video_params, "account_file": account_file}
            result = await publish_to_platform(platform, platform_params)
```

Remove direct login/check handling from `hgsau_cli.py`; after Task 2 it should not contain any login/check branch.

- [ ] **Step 4: Avoid duplicate login checks inside platform publish functions**

In `publish_all.py`, remove these blocks from `publish_to_douyin`, `publish_to_xiaohongshu`, `publish_to_kuaishou`, `publish_to_tencent`, `publish_to_baijiahao`, and `publish_to_weibo`:

```python
    if not await ensure_login("<platform>", account_file):
        return {"success": False, "message": "<平台>登录失败"}
```

The single login gate is now `publish_one_item -> ensure_account_login`.

- [ ] **Step 5: Run account-flow tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_publish_engine.py::AccountLoginFlowTests -q
```

Expected: pass.

- [ ] **Step 6: Run all engine and CLI tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_hgsau_cli.py tests/test_publish_engine.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add publish_all.py tests/test_publish_engine.py
git commit -m "refactor: separate account login from runtime preflight"
```

---

### Task 6: Validate Failure Continuation And Exit Codes

**Files:**
- Modify: `publish_all.py`
- Modify: `tests/test_publish_engine.py`

- [ ] **Step 1: Add failing continuation/exit-code tests**

Append to `tests/test_publish_engine.py`:

```python
class PublishFailurePolicyTests(unittest.TestCase):
    def test_publish_one_item_continues_after_platform_failure(self):
        params = {
            "enabled_platforms": ["douyin", "weibo"],
            "platforms": {
                "douyin_account": "cookies/douyin.json",
                "weibo_account": "cookies/weibo.json",
            },
            "content_type": "video",
            "video_file": "videos/demo.mp4",
            "title": "标题",
            "desc": "描述",
            "tags": [],
            "publish_strategy": "immediate",
            "publish_time": None,
            "convert_to_video": False,
        }

        async def fake_publish(platform, publish_params):
            if platform == "douyin":
                return {"success": False, "message": "发布失败"}
            return {"success": True, "message": "发布成功"}

        with patch("publish_all.ensure_account_login", new=AsyncMock(return_value=True)), \
             patch("publish_all.publish_to_platform", new=AsyncMock(side_effect=fake_publish)):
            results = publish_all.run_async_for_test(publish_all.publish_one_item(params))

        self.assertFalse(results["douyin"]["success"])
        self.assertTrue(results["weibo"]["success"])

    def test_run_publish_with_params_returns_one_when_any_publish_fails(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "demo.mp4"
            video_path.write_bytes(b"video")
            params = {
                "enabled_platforms": ["douyin"],
                "platforms": {"douyin_account": "cookies/douyin.json"},
                "content_type": "video",
                "video_file": str(video_path),
                "images": [],
                "title": "标题",
                "desc": "描述",
                "tags": [],
                "publish_strategy": "immediate",
                "publish_time": None,
                "convert_to_video": False,
                "video_duration": 5,
                "start_from": 1,
            }

            with patch("publish_all.get_video_content", return_value=("标题", "描述")), \
                 patch("publish_all.publish_one_item", new=AsyncMock(return_value={"douyin": {"success": False, "message": "发布失败"}})):
                code = publish_all.run_async_for_test(publish_all.run_publish_with_params(params))

        self.assertEqual(code, 1)
```

- [ ] **Step 2: Run failure-policy tests and confirm failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_publish_engine.py::PublishFailurePolicyTests -q
```

Expected: fail if current exit code returns `0` regardless of failed publishes.

- [ ] **Step 3: Ensure `run_publish_with_params` returns non-zero on any failed publish**

Verify this code exists at the end of `run_publish_with_params`:

```python
    success_count = sum(1 for results in all_results.values() for result in results.values() if result["success"])
    fail_count = sum(1 for results in all_results.values() for result in results.values() if not result["success"])
    print(f"成功: {success_count} 次")
    print(f"失败: {fail_count} 次")
    return 0 if fail_count == 0 else 1
```

If the code still returns `0` unconditionally, replace it with the block above.

- [ ] **Step 4: Run failure-policy tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_publish_engine.py::PublishFailurePolicyTests -q
```

Expected: pass.

- [ ] **Step 5: Run all targeted tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_hgsau_cli.py tests/test_publish_engine.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add publish_all.py tests/test_publish_engine.py
git commit -m "fix: return failed exit code for partial publish failures"
```

---

### Task 7: Update Documentation To `hgsau publish`

**Files:**
- Modify: `AGENT.md`
- Modify: `README.md`
- Modify: `docs/install.md`
- Modify: `docs/CLI.md`
- Modify: `docs/agent-bootstrap.md`

- [ ] **Step 1: Replace public command guidance**

In the docs listed above:

- Replace old `sau` command examples with `hgsau publish`.
- Remove platform-specific CLI examples from recommended quick-start sections.
- Describe `publish_config.ini` as the primary control file.
- State that `hgsau publish` performs runtime preflight, account login checks, publish, and summary.
- State that the project does not maintain internationalized docs; current docs are Chinese-first.

Use this canonical quick-start block wherever a concise example is needed:

~~~markdown
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
~~~

- [ ] **Step 2: Scan docs for old recommended commands**

Run:

```bash
rg -n "sau (douyin|kuaishou|xiaohongshu|bilibili|login|status|generate|publish)|sau --help|sau_cli" AGENT.md README.md docs/install.md docs/CLI.md docs/agent-bootstrap.md
```

Expected: no matches except explicit migration/history text saying old `sau` commands are removed.

- [ ] **Step 3: Commit docs**

```bash
git add AGENT.md README.md docs/install.md docs/CLI.md docs/agent-bootstrap.md
git commit -m "docs: document hgsau publish as only entry"
```

---

### Task 8: Final Verification And Cleanup

**Files:**
- Verify all changed files.

- [ ] **Step 1: Reinstall editable package**

Run:

```bash
$HOME/Library/Python/3.13/bin/uv pip install -e .
```

Expected: install succeeds and generates `.venv/bin/hgsau`.

- [ ] **Step 2: Verify `hgsau` command exists and old `sau` command is absent from the venv scripts after reinstall**

Run:

```bash
test -x .venv/bin/hgsau
test ! -x .venv/bin/sau
```

Expected: both commands exit `0`. If `.venv/bin/sau` remains from a previous editable install, remove it and rerun `uv pip install -e .`:

```bash
rm -f .venv/bin/sau
$HOME/Library/Python/3.13/bin/uv pip install -e .
test -x .venv/bin/hgsau
test ! -x .venv/bin/sau
```

- [ ] **Step 3: Run CLI help smoke checks**

Run:

```bash
.venv/bin/hgsau --help
.venv/bin/hgsau publish --help
```

Expected:

- Top-level help lists only `publish`.
- Publish help lists `--config`, `--platforms`, `--video`, `--title`, `--desc`, `--tags`, `--schedule`, `--start-from`, and `--force`.

- [ ] **Step 4: Run automated tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_hgsau_cli.py tests/test_publish_engine.py tests/test_bilibili_runtime.py tests/test_xiaohongshu_uploader.py -q
```

Expected: pass.

- [ ] **Step 5: Scan repository for old command recommendations**

Run:

```bash
rg -n "sau (douyin|kuaishou|xiaohongshu|bilibili|login|status|generate|publish)|sau --help|sau_cli|hgeng-sau" pyproject.toml README.md AGENT.md docs tests *.py
```

Expected: no matches except historical design/plan documents under `docs/superpowers/` and explicit migration notes.

- [ ] **Step 6: Inspect git diff**

Run:

```bash
git status --short --branch
git diff --stat
```

Expected: changed files are limited to the CLI rename, publish engine, tests, packaging, and docs requested by the spec. Existing unrelated local changes are not reverted.

- [ ] **Step 7: Commit final verification cleanup if any files changed**

If Step 1 updates package metadata files or Step 5 cleanup changes docs/tests:

```bash
git add pyproject.toml hgsau_cli.py publish_all.py tests README.md AGENT.md docs
git commit -m "chore: finalize hgsau publish entry cleanup"
```

If no files changed, do not create an empty commit.
