# publish_all.py 清洁架构重构 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 1225 行的 `publish_all.py` 拆成 `publish/` 包(7 模块 + 薄壳),合并 `hgsau_cli.py` 的 argparse 到 `orchestrator.main()`,合并 `ensure_login` 分发表,`publish_to_platform` 用 dict 查表,抽 `reporter.print_summary`。

**Architecture:** 务实分层 -- config / runtime / content / dispatch / reporter / orchestrator 各自独立,`publish_all.py` 缩成薄壳 re-export。向后兼容靠薄壳 + `pyproject.toml` 控制台脚本指向 `publish_all:main`。

**Tech Stack:** Python 3.9+ / argparse / asyncio / unittest.mock / pytest / patchright / playwright

## Global Constraints

- **禁止截屏定位 UI**:不从 `page.screenshot` 截图发给模型 API 定位 UI;用 DOM/页面源码(`page.content()` / `page.evaluate` / selector)
- **禁止非文本文件调用大模型 API**:LLM API 输入只限纯文本
- **`python publish_all.py` 入口必须保留**:用户主力发布路径,不破坏
- **`publish_config.ini` 格式不变**:`[common]` + `[platforms]` 字段保持
- **`PublishOverrides` dataclass 字段不变**:shape 锁定
- **`hgsau` 控制台脚本保留**(指向 `publish_all:main`),去掉 `publish` 子命令
- **Python 3.9 兼容**:TypedDict 用继承模式(不用 `Required[]`/`NotRequired[]`)

## Spec 修正(重要)

Spec §测试策略 说"现有测试零修改"。**这不准确。** `tests/test_publish_engine.py` 通过 `patch("publish_all.X", ...)` mock 函数。Python `mock.patch` 拦截的是**特定模块命名空间的名字查找**。重构后,调用方(如 `publish_one_item` 在 `publish.orchestrator`)和函数定义(如 `publish_to_platform` 在 `publish.dispatch`)分属不同模块,`patch("publish_all.X")` 只替换 `publish_all.__dict__` 的引用,不拦截 `publish.orchestrator` 内部的词法调用。

**需要更新的 patch target**(Task 1 处理,机械替换):

| 旧 target | 新 target | 出现行 |
|---|---|---|
| `publish_all.run_publish_with_params` | `publish.orchestrator.run_publish_with_params` | 127, 148 |
| `publish_all.runtime_preflight` | `publish.orchestrator.runtime_preflight` | 176, 208, 417 |
| `publish_all.get_video_files` | `publish.orchestrator.get_video_files` | 177 |
| `publish_all.get_video_content` | `publish.orchestrator.get_video_content` | 178, 418 |
| `publish_all.publish_one_item` | `publish.orchestrator.publish_one_item` | 179, 419 |
| `publish_all.ensure_account_login` | `publish.orchestrator.ensure_account_login` | 315, 337, 359, 390 |
| `publish_all.publish_to_platform` | `publish.orchestrator.publish_to_platform` | 316, 338, 391 |
| `publish_all.patchright_available` | `publish.runtime.patchright_available` | 251, 260, 268 |
| `publish_all.patchright_chromium_installed` | `publish.runtime.patchright_chromium_installed` | 252, 261, 269 |
| `publish_all.install_patchright_chromium` | `publish.runtime.install_patchright_chromium` | 253, 262 |

**保留不变的**(`publish_all.os`/`Path`/`subprocess`/`datetime`/`run_async_for_test` 通过薄壳 re-export 仍可访问):
- `patch.dict("publish_all.os.environ", ...)` -- `os` 是共享模块,re-export 后仍指向同一 `os`
- `patch("publish_all.Path.home", ...)` -- `Path` 是 `pathlib.Path` 类,re-export 后 patch 类方法
- `patch("publish_all.subprocess.run", ...)` -- 同理
- `publish_all.datetime.strptime(...)` -- re-export `datetime` 类
- `publish_all.run_async_for_test(...)` -- re-export 函数
- `patch("uploader.douyin_uploader.main.DouYinVideo")` -- 不经 publish_all,不受影响

---

## File Structure

| 文件 | 职责 | 状态 |
|---|---|---|
| `publish/__init__.py` | re-export `run_publish` / `run_publish_sync` / `PublishOverrides` / `main` | 新建 |
| `publish/constants.py` | `PLATFORM_NAMES` / `TITLE_LIMITS` / `PUBLISH_TASK_FIELD_DEFAULTS` | 新建 |
| `publish/config.py` | INI 解析、overrides、reset:`read_config` / `parse_config` / `apply_overrides` / `reset_publish_task_fields` / `default_params_from_overrides` / `_split_csv` / `_discover_account_files` + `PublishOverrides` dataclass | 新建 |
| `publish/runtime.py` | patchright/chromium preflight:`runtime_preflight` / `patchright_available` / `playwright_browser_cache_dirs` / `patchright_chromium_installed` / `install_patchright_chromium` / `run_async_for_test` | 新建 |
| `publish/content.py` | 内容解析:`get_video_content` / `fill_empty_content` / `load_content_templates` / `get_video_files` / `truncate_title` / `resolve_path` + `CONTENT_TEMPLATES_FILE` | 新建 |
| `publish/dispatch.py` | 8 个 `publish_to_*` + `publish_to_platform` + `ensure_login` / `ensure_account_login` / `platform_requires_account_login` + `PlatformResult` TypedDict + `_PLATFORM_LOGIN` / `_PUBLISH_DISPATCH` 注册表 | 新建 |
| `publish/reporter.py` | `print_header` / `print_results` / `print_summary` | 新建 |
| `publish/orchestrator.py` | `run_publish` / `run_publish_with_params` / `publish_one_item` / `main`(含 argparse) + `build_parser` / `_build_overrides` / `_schedule_value` | 新建 |
| `publish_all.py` | 薄壳:re-export 所有外部依赖的名字 | 改写 |
| `hgsau_cli.py` | - | **删除** |
| `pyproject.toml` | `hgsau = "publish_all:main"`,`py-modules` 移除 `hgsau_cli` | 修改 |
| `tests/test_publish_engine.py` | patch target 更新(见上表) | 修改 |
| `tests/test_hgsau_cli.py` | 删除,改名 `tests/test_publish_cli.py` 改写 | 重写 |
| `tests/test_publish_dispatch.py` | `_PLATFORM_LOGIN` / `_PUBLISH_DISPATCH` / `ensure_login` 注册表测试 | 新建 |
| `tests/test_publish_reporter.py` | `print_summary` 测试 | 新建 |

---

## Task 1: 创建 publish/ 包 + 机械迁移 + 薄壳 + 测试 patch 更新

**Files:**
- Create: `publish/__init__.py`, `publish/constants.py`, `publish/config.py`, `publish/runtime.py`, `publish/content.py`, `publish/dispatch.py`, `publish/reporter.py`, `publish/orchestrator.py`
- Modify: `publish_all.py`(改写为薄壳)
- Modify: `tests/test_publish_engine.py`(patch target 更新)
- Test: `tests/test_publish_engine.py`(回归安全网)

**Interfaces:**
- Produces: `publish.*` 各模块的公共函数(签名不变,只搬位置);`publish_all.py` re-export 所有外部依赖的名字

**迁移映射(函数 -> 目标模块,带 publish_all.py 行号):**

- [ ] **Step 1: 创建 `publish/constants.py`**

```python
"""发布流程共享常量"""

PLATFORM_NAMES = {
    "douyin": "抖音",
    "xiaohongshu": "小红书",
    "kuaishou": "快手",
    "bilibili": "B站",
    "tencent": "微信视频号",
    "baijiahao": "百家号",
    "tk": "TikTok",
    "weibo": "微博",
}

TITLE_LIMITS = {
    "douyin": 30,
    "xiaohongshu": 20,
    "kuaishou": 30,
    "bilibili": 80,
    "tencent": 30,
    "baijiahao": 30,
    "tk": 150,
    "weibo": 2000,
}

PUBLISH_TASK_FIELD_DEFAULTS = {
    "common": {
        "content_type": "video",
        "convert_to_video": "false",
        "video_duration": "5",
        "title": "",
        "desc": "",
        "tags": "",
        "video_file": "",
        "images": "",
        "publish_strategy": "immediate",
        "publish_time": "",
        "start_from": "",
    },
    "platforms": {
        "enabled": "",
    },
}
```

- [ ] **Step 2: 创建 `publish/config.py`**

从 `publish_all.py` 迁入(保持函数体不动,只搬位置 + 修 import):
- `PublishOverrides` dataclass(行 73-82)
- `read_config`(行 199-215)
- `reset_publish_task_fields`(行 217-249)
- `_split_csv`(行 251-255)
- `_discover_account_files`(行 257-289)
- `default_params_from_overrides`(行 290-306)
- `apply_overrides`(行 308-332)
- `parse_config`(行 429-487)

import 依赖:
```python
import configparser
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from conf import BASE_DIR
from publish.constants import PUBLISH_TASK_FIELD_DEFAULTS, TITLE_LIMITS
from publish.content import resolve_path, truncate_title
```

注意:`parse_config` 内部如果用到 `resolve_path`/`truncate_title`,从 `publish.content` import。读源码确认具体调用点。

- [ ] **Step 3: 创建 `publish/runtime.py`**

从 `publish_all.py` 迁入:
- `run_async_for_test`(行 334-335)
- `patchright_available`(行 338-343)
- `playwright_browser_cache_dirs`(行 346-359)
- `patchright_chromium_installed`(行 361-392)
- `install_patchright_chromium`(行 394-403)
- `runtime_preflight`(行 405-427)

import 依赖:
```python
import asyncio
import os
import subprocess
from importlib import import_module
from pathlib import Path
```

- [ ] **Step 4: 创建 `publish/content.py`**

从 `publish_all.py` 迁入:
- `CONTENT_TEMPLATES_FILE` 常量(行 26)
- `load_content_templates`(行 84-90)
- `fill_empty_content`(行 93-108)
- `get_video_content`(行 111-197)
- `get_video_files`(行 488-512)
- `truncate_title`(行 514-520)
- `resolve_path`(行 522-530)

import 依赖:
```python
import json
import os
import random
from pathlib import Path

from conf import BASE_DIR
from publish.constants import TITLE_LIMITS
```

注意:`get_video_content` 如果调 GLM-4V(`utils/video_analyzer.py`),保持现有 import 不动。

- [ ] **Step 5: 创建 `publish/dispatch.py`**

从 `publish_all.py` 迁入(保持函数体不动):
- `ensure_login`(行 532-584)-- **暂保留两份分发表**(Task 3 再合并)
- `ensure_account_login`(行 587-589)
- `platform_requires_account_login`(行 592-593)
- `publish_to_douyin`(行 596-654)
- `publish_to_xiaohongshu`(行 657-718)
- `publish_to_kuaishou`(行 720-780)
- `publish_to_tencent`(行 782-816)
- `publish_to_baijiahao`(行 818-864)
- `publish_to_bilibili`(行 867-895)
- `publish_to_weibo`(行 897-964)
- `publish_to_platform`(行 966-985)-- **暂保留 if/elif**(Task 4 再改 dict)

import 依赖:
```python
import os
from typing import TypedDict

from publish.constants import PLATFORM_NAMES, TITLE_LIMITS
from publish.content import resolve_path, truncate_title
```

新增 `PlatformResult` TypedDict(放文件顶部):
```python
class PlatformResult(TypedDict):
    success: bool
    message: str

class PlatformResultExtras(PlatformResult, total=False):
    share_link: str
    video_link: str
    account_issue: bool
    issue_type: str
```

- [ ] **Step 6: 创建 `publish/reporter.py`**

从 `publish_all.py` 迁入:
- `print_header`(行 988-999)
- `print_results`(行 1002-1008)

**暂不抽 `print_summary`**(Task 5 再抽)。

import 依赖:
```python
from publish.constants import PLATFORM_NAMES
```

- [ ] **Step 7: 创建 `publish/orchestrator.py`**

从 `publish_all.py` 迁入(保持函数体不动):
- `publish_one_item`(行 1011-1073)
- `run_publish_with_params`(行 1076-1181)-- **暂保留内联的 summary 打印**(Task 5 再抽)
- `run_publish`(行 1184-1209)
- `run_publish_sync`(行 1212-1216)
- `main`(行 1219-1221)-- **暂保留 async 无参版本**(Task 2 再加 argparse)

import 依赖:
```python
import asyncio
import os
from pathlib import Path
from typing import Any, Dict, Optional

from conf import BASE_DIR
from publish.config import (
    PublishOverrides,
    apply_overrides,
    default_params_from_overrides,
    parse_config,
    read_config,
    reset_publish_task_fields,
)
from publish.content import get_video_content, get_video_files
from publish.dispatch import ensure_account_login, publish_to_platform
from publish.reporter import print_header, print_results
from publish.runtime import runtime_preflight
```

注意:`publish_one_item` 和 `run_publish_with_params` 内部调用 `ensure_account_login` / `publish_to_platform` / `print_header` / `print_results` / `runtime_preflight` / `get_video_files` / `get_video_content` -- 这些必须 import 进 `orchestrator.py` 的命名空间(因为测试要 patch `publish.orchestrator.X`)。

- [ ] **Step 8: 创建 `publish/__init__.py`**

```python
"""publish 包:多平台统一发布编排"""
from publish.config import PublishOverrides
from publish.orchestrator import main, run_publish, run_publish_sync

__all__ = ["PublishOverrides", "main", "run_publish", "run_publish_sync"]
```

- [ ] **Step 9: 改写 `publish_all.py` 为薄壳**

```python
"""publish_all.py -- 向后兼容薄壳

实际代码在 publish/ 包内。此文件保留用于:
- python publish_all.py 入口
- hgsau 控制台脚本(publish_all:main)
- 测试 import 兼容(publish_all.X)
"""
import os
import subprocess
from datetime import datetime
from pathlib import Path

from publish.config import (
    PublishOverrides,
    apply_overrides,
    default_params_from_overrides,
    parse_config,
    read_config,
    reset_publish_task_fields,
)
from publish.content import (
    fill_empty_content,
    get_video_content,
    get_video_files,
    load_content_templates,
    resolve_path,
    truncate_title,
)
from publish.constants import (
    PLATFORM_NAMES,
    PUBLISH_TASK_FIELD_DEFAULTS,
    TITLE_LIMITS,
)
from publish.dispatch import (
    ensure_account_login,
    ensure_login,
    platform_requires_account_login,
    publish_to_baijiahao,
    publish_to_bilibili,
    publish_to_douyin,
    publish_to_kuaishou,
    publish_to_platform,
    publish_to_tencent,
    publish_to_weibo,
    publish_to_xiaohongshu,
)
from publish.orchestrator import (
    main,
    publish_one_item,
    run_publish,
    run_publish_sync,
    run_publish_with_params,
)
from publish.reporter import print_header, print_results
from publish.runtime import (
    install_patchright_chromium,
    patchright_available,
    patchright_chromium_installed,
    playwright_browser_cache_dirs,
    run_async_for_test,
    runtime_preflight,
)

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 10: 更新 `tests/test_publish_engine.py` 的 patch target**

按"Spec 修正"表格机械替换 patch target 字符串。**不改测试逻辑,只改 patch target 字符串。**

具体替换(用编辑器的查找替换或 sed):
- `"publish_all.run_publish_with_params"` -> `"publish.orchestrator.run_publish_with_params"`
- `"publish_all.runtime_preflight"` -> `"publish.orchestrator.runtime_preflight"`
- `"publish_all.get_video_files"` -> `"publish.orchestrator.get_video_files"`
- `"publish_all.get_video_content"` -> `"publish.orchestrator.get_video_content"`
- `"publish_all.publish_one_item"` -> `"publish.orchestrator.publish_one_item"`
- `"publish_all.ensure_account_login"` -> `"publish.orchestrator.ensure_account_login"`
- `"publish_all.publish_to_platform"` -> `"publish.orchestrator.publish_to_platform"`
- `"publish_all.patchright_available"` -> `"publish.runtime.patchright_available"`
- `"publish_all.patchright_chromium_installed"` -> `"publish.runtime.patchright_chromium_installed"`
- `"publish_all.install_patchright_chromium"` -> `"publish.runtime.install_patchright_chromium"`

**保留不变**:`publish_all.os` / `publish_all.Path` / `publish_all.subprocess` / `publish_all.datetime` / `publish_all.run_async_for_test` / `publish_all.reset_publish_task_fields` / `publish_all.apply_overrides` / `publish_all.publish_to_douyin`(这些通过薄壳 re-export 仍可访问,且不是跨模块调用)。

- [ ] **Step 11: 运行测试验证**

Run: `python -m pytest tests/test_publish_engine.py -v`
Expected: 16 个测试全 PASS

如果有 FAIL:
- `AttributeError: module 'publish_all' has no attribute 'X'` -> 薄壳漏 re-export `X`,加上
- `AssertError: mock not called` -> patch target 还没更新,检查 Step 10 替换是否完整
- `ImportError` -> 模块间循环 import,检查 import 顺序

- [ ] **Step 12: 运行 `python publish_all.py --help` 确认入口不破**

Run: `python publish_all.py --help`
Expected: 打印用法(此时还是无 argparse 的旧 main,应该直接跑 `run_publish()` 报缺 config,或正常跑)

注意:此时 `main` 还是 `async def main(): return await run_publish()`,无 argparse。`--help` 不会生效。这是预期的 -- Task 2 才加 argparse。

- [ ] **Step 13: 提交**

```bash
git add publish/ publish_all.py tests/test_publish_engine.py
git commit -m "refactor(publish): split publish_all.py into publish/ package

Move 1225-line god module into 7 focused modules (constants/config/runtime/
content/dispatch/reporter/orchestrator) + thin re-export shim. Update test
patch targets from publish_all.X to publish.<module>.X for cross-module
calls. Behavior unchanged, all 16 tests pass."
```

---

## Task 2: 合并 CLI(argparse -> orchestrator.main,删 hgsau_cli.py)

**Files:**
- Modify: `publish/orchestrator.py`(加 argparse)
- Modify: `publish_all.py`(re-export `build_parser`)
- Delete: `hgsau_cli.py`
- Modify: `pyproject.toml`
- Delete: `tests/test_hgsau_cli.py`
- Create: `tests/test_publish_cli.py`
- Test: `tests/test_publish_cli.py`

**Interfaces:**
- Consumes: `run_publish(config_file, overrides)` from Task 1
- Produces: `publish.orchestrator.main(argv)` / `build_parser()` / `_build_overrides(args)` / `_schedule_value(value)`

- [ ] **Step 1: 写 `tests/test_publish_cli.py` 失败测试**

```python
import contextlib
import io
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import publish_all


class PublishCliPackagingTests(unittest.TestCase):
    def test_pyproject_exposes_hgsau_pointing_to_publish_all(self):
        pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
        py_modules_line = next(
            line for line in pyproject.splitlines() if line.startswith("py-modules = ")
        )

        self.assertIn('name = "hgsau"', pyproject)
        self.assertIn('hgsau = "publish_all:main"', pyproject)
        self.assertNotIn("hgsau_cli", pyproject)
        self.assertEqual(py_modules_line, 'py-modules = ["conf", "publish_all"]')

    def test_publish_all_exposes_build_parser_and_main(self):
        self.assertTrue(hasattr(publish_all, "build_parser"))
        self.assertTrue(hasattr(publish_all, "main"))

    def test_parser_prog_is_hgsau(self):
        parser = publish_all.build_parser()
        self.assertEqual(parser.prog, "hgsau")


class PublishCliParserTests(unittest.TestCase):
    def test_parser_accepts_defaults_no_subcommand(self):
        parser = publish_all.build_parser()
        args = parser.parse_args([])

        self.assertEqual(args.config, "publish_config.ini")
        self.assertIsNone(args.platforms)
        self.assertIsNone(args.video)

    def test_parser_accepts_overrides(self):
        parser = publish_all.build_parser()
        args = parser.parse_args(
            [
                "--config", "my.ini",
                "--platforms", "douyin,weibo",
                "--video", "videos/demo.mp4",
                "--title", "标题",
                "--desc", "描述",
                "--tags", "标签1,标签2",
                "--schedule", "2026-05-30 21:30",
                "--start-from", "3",
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

    def test_parser_rejects_unknown_subcommand(self):
        parser = publish_all.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["douyin", "upload-video"])

    def test_main_calls_run_publish_with_overrides(self):
        with patch("publish.orchestrator.run_publish", new=AsyncMock(return_value=0)) as run_publish:
            code = publish_all.main(["--platforms", "weibo", "--title", "标题"])

        self.assertEqual(code, 0)
        call = run_publish.await_args
        self.assertEqual(call.args[0], "publish_config.ini")
        self.assertEqual(call.args[1].platforms, "weibo")
        self.assertEqual(call.args[1].title, "标题")

    def test_main_returns_1_for_run_publish_exception(self):
        stderr = io.StringIO()
        with patch("publish.orchestrator.run_publish", new=AsyncMock(side_effect=RuntimeError("boom"))):
            with contextlib.redirect_stderr(stderr):
                code = publish_all.main([])

        self.assertEqual(code, 1)
        self.assertIn("boom", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_publish_cli.py -v`
Expected: FAIL(`publish_all.build_parser` 不存在)

- [ ] **Step 3: 在 `publish/orchestrator.py` 加 argparse**

在 `orchestrator.py` 顶部加 import:
```python
import argparse
import sys
from datetime import datetime
from typing import Sequence
```

替换 `main` 函数(原 `async def main(): return await run_publish()`)为:
```python
SCHEDULE_FORMAT = "%Y-%m-%d %H:%M"


def _schedule_value(value: str) -> datetime:
    try:
        return datetime.strptime(value, SCHEDULE_FORMAT)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid schedule '{value}'. Expected format: {SCHEDULE_FORMAT}"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    schedule_help = SCHEDULE_FORMAT.replace("%", "%%")
    parser = argparse.ArgumentParser(
        prog="hgsau",
        description="CLI for social-auto-upload.",
    )
    parser.add_argument("--config", default="publish_config.ini", help="Config file path (default: publish_config.ini)")
    parser.add_argument("--platforms", default=None, help="Override enabled platforms, comma-separated")
    parser.add_argument("--video", default=None, help="Override video file/directory path")
    parser.add_argument("--title", default=None, help="Override title")
    parser.add_argument("--desc", default=None, help="Override description")
    parser.add_argument("--tags", default=None, help="Override tags, comma-separated")
    parser.add_argument("--schedule", type=_schedule_value, default=None, help=f"Override schedule time in {schedule_help}")
    parser.add_argument("--start-from", type=int, default=None, help="Start from video index (1-based)")
    parser.add_argument("--force", action="store_true", help="Force regenerate video config")
    return parser


def _build_overrides(args: argparse.Namespace) -> PublishOverrides:
    return PublishOverrides(
        platforms=args.platforms,
        video=args.video,
        title=args.title,
        desc=args.desc,
        tags=args.tags,
        schedule=args.schedule,
        start_from=args.start_from,
        force=args.force,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return asyncio.run(run_publish(args.config, _build_overrides(args)))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
```

- [ ] **Step 4: 在 `publish_all.py` 薄壳加 `build_parser` re-export**

在 `publish/orchestrator.py` 的 import 块加 `build_parser`:
```python
from publish.orchestrator import (
    build_parser,
    main,
    publish_one_item,
    run_publish,
    run_publish_sync,
    run_publish_with_params,
)
```

- [ ] **Step 5: 删 `hgsau_cli.py`,更新 `pyproject.toml`**

删文件:
```bash
rm hgsau_cli.py
```

`pyproject.toml` 改两处:
- `[project.scripts]` 行 `hgsau = "hgsau_cli:main"` -> `hgsau = "publish_all:main"`
- `[tool.setuptools]` 行 `py-modules = ["conf", "hgsau_cli", "publish_all"]` -> `py-modules = ["conf", "publish_all"]`

- [ ] **Step 6: 删 `tests/test_hgsau_cli.py`**

```bash
rm tests/test_hgsau_cli.py
```

- [ ] **Step 7: 运行新测试验证通过**

Run: `python -m pytest tests/test_publish_cli.py -v`
Expected: 7 个测试全 PASS

- [ ] **Step 8: 运行全量测试确认没破其他**

Run: `python -m pytest tests/ -v`
Expected: 全绿(test_publish_engine.py 16 + test_publish_cli.py 7 + 其他现有测试)

- [ ] **Step 9: 验证 `python publish_all.py --help` 和 `hgsau --help`**

Run: `python publish_all.py --help`
Expected: 显示 argparse 用法(prog=hgsau,无子命令)

Run: `pip install -e . && hgsau --help`
Expected: 同上

- [ ] **Step 10: 提交**

```bash
git add publish/orchestrator.py publish_all.py pyproject.toml tests/test_publish_cli.py
git rm hgsau_cli.py tests/test_hgsau_cli.py
git commit -m "refactor(publish): merge hgsau_cli argparse into orchestrator.main

Delete hgsau_cli.py, move argparse into publish/orchestrator.py::main().
Drop redundant 'publish' subcommand. hgsau console script now points to
publish_all:main. Rewrite test_hgsau_cli.py as test_publish_cli.py."
```

---

## Task 3: 合并 ensure_login 两份分发表为 _PLATFORM_LOGIN 注册表(TDD)

**Files:**
- Modify: `publish/dispatch.py`(`ensure_login` / `platform_requires_account_login`)
- Test: `tests/test_publish_dispatch.py`(新建)

**Interfaces:**
- Consumes: 8 个平台的 `cookie_auth` / `*_setup` 函数(从 uploader 模块动态 import)
- Produces: `_PLATFORM_LOGIN` 注册表 / 重构后的 `ensure_login`

- [ ] **Step 1: 写 `tests/test_publish_dispatch.py` 失败测试**

```python
import unittest
from unittest.mock import AsyncMock, patch

from publish.dispatch import (
    _PLATFORM_LOGIN,
    ensure_login,
    platform_requires_account_login,
)


class PlatformLoginRegistryTests(unittest.TestCase):
    def test_registry_covers_all_platforms_except_tk(self):
        expected = {"douyin", "xiaohongshu", "kuaishou", "tencent", "baijiahao", "bilibili", "weibo"}
        self.assertEqual(set(_PLATFORM_LOGIN.keys()), expected)

    def test_registry_entries_are_three_tuples(self):
        for platform, entry in _PLATFORM_LOGIN.items():
            self.assertEqual(len(entry), 3, f"{platform} entry must be (module_path, check_name, setup_name)")
            module_path, check_name, setup_name = entry
            self.assertTrue(module_path.startswith("uploader."), f"{platform} module_path wrong: {module_path}")
            self.assertEqual(check_name, "cookie_auth", f"{platform} check_name should be cookie_auth")
            self.assertTrue(setup_name.endswith("_setup"), f"{platform} setup_name wrong: {setup_name}")

    def test_platform_requires_account_login(self):
        self.assertTrue(platform_requires_account_login("douyin"))
        self.assertTrue(platform_requires_account_login("weibo"))
        self.assertFalse(platform_requires_account_login("tk"))
        self.assertFalse(platform_requires_account_login("unknown_platform"))


class EnsureLoginTests(unittest.TestCase):
    def test_returns_false_for_unknown_platform(self):
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(ensure_login("unknown", "cookies/x.json"))
        self.assertFalse(result)

    def test_triggers_setup_when_account_file_missing(self):
        import asyncio
        with patch("os.path.exists", return_value=False), \
             patch("importlib.import_module") as mock_import:
            mock_module = mock_import.return_value
            mock_module.douyin_setup = AsyncMock(return_value=True)
            result = asyncio.get_event_loop().run_until_complete(
                ensure_login("douyin", "cookies/douyin_uploader/account.json")
            )
        self.assertTrue(result)
        mock_module.douyin_setup.assert_awaited_once()

    def test_checks_cookie_auth_when_file_exists(self):
        import asyncio
        with patch("os.path.exists", return_value=True), \
             patch("importlib.import_module") as mock_import:
            mock_module = mock_import.return_value
            mock_module.cookie_auth = AsyncMock(return_value=True)
            result = asyncio.get_event_loop().run_until_complete(
                ensure_login("douyin", "cookies/douyin_uploader/account.json")
            )
        self.assertTrue(result)
        mock_module.cookie_auth.assert_awaited_once()
        mock_module.douyin_setup.assert_not_awaited()

    def test_falls_through_to_setup_when_cookie_invalid(self):
        import asyncio
        with patch("os.path.exists", return_value=True), \
             patch("importlib.import_module") as mock_import:
            mock_module = mock_import.return_value
            mock_module.cookie_auth = AsyncMock(return_value=False)
            mock_module.douyin_setup = AsyncMock(return_value=True)
            result = asyncio.get_event_loop().run_until_complete(
                ensure_login("douyin", "cookies/douyin_uploader/account.json")
            )
        self.assertTrue(result)
        mock_module.cookie_auth.assert_awaited_once()
        mock_module.douyin_setup.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_publish_dispatch.py -v`
Expected: FAIL(`_PLATFORM_LOGIN` 不存在)

- [ ] **Step 3: 在 `publish/dispatch.py` 实现 `_PLATFORM_LOGIN` + 重构 `ensure_login`**

在 `dispatch.py` 顶部加 `import importlib`(如还没有)。

替换 `ensure_login` 函数(原行 532-584)和 `platform_requires_account_login`(原行 592-593)为:

```python
_PLATFORM_LOGIN = {
    "douyin":      ("uploader.douyin_uploader.main",      "cookie_auth", "douyin_setup"),
    "xiaohongshu": ("uploader.xiaohongshu_uploader.main", "cookie_auth", "xiaohongshu_setup"),
    "kuaishou":    ("uploader.ks_uploader.main",          "cookie_auth", "ks_setup"),
    "tencent":     ("uploader.tencent_uploader.main",     "cookie_auth", "tencent_setup"),
    "baijiahao":   ("uploader.baijiahao_uploader.main",   "cookie_auth", "baijiahao_setup"),
    "bilibili":    ("uploader.bilibili_uploader.main",    "cookie_auth", "bilibili_setup"),
    "weibo":       ("uploader.weibo_uploader.main",       "cookie_auth", "weibo_setup"),
}


async def ensure_login(platform: str, account_file: str) -> bool:
    """确保平台已登录,未登录则触发登录流程"""
    entry = _PLATFORM_LOGIN.get(platform)
    if entry is None:
        return False

    module_path, check_name, setup_name = entry
    module = importlib.import_module(module_path)

    if os.path.exists(account_file):
        check_func = getattr(module, check_name)
        if await check_func(account_file):
            return True

    setup_func = getattr(module, setup_name)
    return await setup_func(account_file, handle=True)


def platform_requires_account_login(platform: str) -> bool:
    return platform in _PLATFORM_LOGIN
```

- [ ] **Step 4: 运行新测试验证通过**

Run: `python -m pytest tests/test_publish_dispatch.py -v`
Expected: 7 个测试全 PASS

- [ ] **Step 5: 运行全量测试确认 `test_publish_engine.py` 的 login flow 测试仍通过**

Run: `python -m pytest tests/test_publish_engine.py -v`
Expected: 16 个全 PASS(尤其 `AccountLoginFlowTests` 3 个)

- [ ] **Step 6: 提交**

```bash
git add publish/dispatch.py tests/test_publish_dispatch.py
git commit -m "refactor(publish): consolidate ensure_login dispatch into _PLATFORM_LOGIN registry

Merge the duplicated check_map dict + if/elif setup chain into a single
_PLATFORM_LOGIN registry. ensure_login shrinks from ~50 to ~15 lines.
platform_requires_account_login becomes 'return platform in _PLATFORM_LOGIN'."
```

---

## Task 4: publish_to_platform if/elif -> _PUBLISH_DISPATCH dict(TDD)

**Files:**
- Modify: `publish/dispatch.py`(`publish_to_platform`)
- Test: `tests/test_publish_dispatch.py`(追加测试)

**Interfaces:**
- Consumes: 7 个 `publish_to_*` 函数(同模块)
- Produces: `_PUBLISH_DISPATCH` 注册表 / dict 查表版 `publish_to_platform`

- [ ] **Step 1: 追加失败测试到 `tests/test_publish_dispatch.py`**

在文件末尾(`if __name__` 之前)加:

```python
class PublishDispatchRegistryTests(unittest.TestCase):
    def test_registry_covers_all_enabled_platforms(self):
        from publish.dispatch import _PUBLISH_DISPATCH
        expected = {"douyin", "xiaohongshu", "kuaishou", "tencent", "baijiahao", "bilibili", "weibo"}
        self.assertEqual(set(_PUBLISH_DISPATCH.keys()), expected)

    def test_registry_values_are_callable(self):
        from publish.dispatch import _PUBLISH_DISPATCH
        for platform, handler in _PUBLISH_DISPATCH.items():
            self.assertTrue(callable(handler), f"{platform} handler not callable")

    def test_publish_to_platform_dispatches_to_handler(self):
        import asyncio
        from publish.dispatch import publish_to_platform
        with patch("publish.dispatch._PUBLISH_DISPATCH") as mock_reg:
            mock_handler = AsyncMock(return_value={"success": True, "message": "ok"})
            mock_reg.get.return_value = mock_handler
            result = asyncio.get_event_loop().run_until_complete(
                publish_to_platform("douyin", {"key": "val"})
            )
        self.assertEqual(result, {"success": True, "message": "ok"})
        mock_handler.assert_awaited_once_with({"key": "val"})

    def test_publish_to_platform_returns_stub_for_tk(self):
        import asyncio
        from publish.dispatch import publish_to_platform
        with patch("publish.dispatch._PUBLISH_DISPATCH") as mock_reg:
            mock_reg.get.return_value = None
            result = asyncio.get_event_loop().run_until_complete(
                publish_to_platform("tk", {})
            )
        self.assertFalse(result["success"])
        self.assertIn("TikTok", result["message"])

    def test_publish_to_platform_returns_error_for_unknown(self):
        import asyncio
        from publish.dispatch import publish_to_platform
        with patch("publish.dispatch._PUBLISH_DISPATCH") as mock_reg:
            mock_reg.get.return_value = None
            result = asyncio.get_event_loop().run_until_complete(
                publish_to_platform("unknown_plat", {})
            )
        self.assertFalse(result["success"])
        self.assertIn("未知平台", result["message"])
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_publish_dispatch.py::PublishDispatchRegistryTests -v`
Expected: FAIL(`_PUBLISH_DISPATCH` 不存在)

- [ ] **Step 3: 在 `publish/dispatch.py` 实现 `_PUBLISH_DISPATCH` + 重构 `publish_to_platform`**

替换 `publish_to_platform` 函数(原行 966-985)为:

```python
_PUBLISH_DISPATCH = {
    "douyin": publish_to_douyin,
    "xiaohongshu": publish_to_xiaohongshu,
    "kuaishou": publish_to_kuaishou,
    "tencent": publish_to_tencent,
    "baijiahao": publish_to_baijiahao,
    "bilibili": publish_to_bilibili,
    "weibo": publish_to_weibo,
}


async def publish_to_platform(platform: str, params: dict) -> dict:
    """发布到指定平台"""
    handler = _PUBLISH_DISPATCH.get(platform)
    if handler is not None:
        return await handler(params)
    if platform == "tk":
        return {"success": False, "message": "TikTok平台暂未实现"}
    return {"success": False, "message": f"未知平台: {platform}"}
```

注意:`_PUBLISH_DISPATCH` 必须在 7 个 `publish_to_*` 函数定义**之后**(它们互相引用)。

- [ ] **Step 4: 运行新测试验证通过**

Run: `python -m pytest tests/test_publish_dispatch.py -v`
Expected: 全 PASS(原 7 + 新 5 = 12)

- [ ] **Step 5: 运行全量测试**

Run: `python -m pytest tests/ -v`
Expected: 全绿

- [ ] **Step 6: 提交**

```bash
git add publish/dispatch.py tests/test_publish_dispatch.py
git commit -m "refactor(publish): replace publish_to_platform if/elif with _PUBLISH_DISPATCH dict

Adding a platform now = adding one line to the registry, no dispatcher
logic change. tk stub and unknown-platform error preserved."
```

---

## Task 5: 抽 reporter.print_summary(TDD)

**Files:**
- Modify: `publish/reporter.py`(加 `print_summary`)
- Modify: `publish/orchestrator.py`(`run_publish_with_params` 末尾改调用 `print_summary`)
- Test: `tests/test_publish_reporter.py`(新建)

**Interfaces:**
- Consumes: `PLATFORM_NAMES` from `publish.constants`
- Produces: `reporter.print_summary(all_results)`

- [ ] **Step 1: 写 `tests/test_publish_reporter.py` 失败测试**

```python
import io
import unittest
from contextlib import redirect_stdout

from publish.reporter import print_summary


class PrintSummaryTests(unittest.TestCase):
    def test_counts_success_and_failure(self):
        all_results = {
            "v1.mp4": {
                "douyin": {"success": True, "message": "ok"},
                "weibo": {"success": False, "message": "fail"},
            },
            "v2.mp4": {
                "douyin": {"success": True, "message": "ok"},
            },
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            print_summary(all_results)
        out = buf.getvalue()
        self.assertIn("成功: 2 次", out)
        self.assertIn("失败: 1 次", out)

    def test_aggregates_account_issues_deduped(self):
        all_results = {
            "v1.mp4": {
                "douyin": {"success": False, "message": "受限", "account_issue": True, "issue_type": "publish_restricted"},
            },
            "v2.mp4": {
                "douyin": {"success": False, "message": "受限", "account_issue": True, "issue_type": "publish_restricted"},
                "weibo": {"success": True, "message": "ok"},
            },
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            print_summary(all_results)
        out = buf.getvalue()
        self.assertIn("账号异常反馈", out)
        self.assertIn("抖音", out)
        # douyin 只出现一次(去重)
        self.assertEqual(out.count("[douyin]"), 1)

    def test_no_account_issues_section_when_all_success(self):
        all_results = {
            "v1.mp4": {"douyin": {"success": True, "message": "ok"}},
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            print_summary(all_results)
        out = buf.getvalue()
        self.assertNotIn("账号异常反馈", out)

    def test_empty_results(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            print_summary({})
        out = buf.getvalue()
        self.assertIn("成功: 0 次", out)
        self.assertIn("失败: 0 次", out)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_publish_reporter.py -v`
Expected: FAIL(`print_summary` 不存在)

- [ ] **Step 3: 在 `publish/reporter.py` 实现 `print_summary`**

在 `reporter.py` 末尾加:

```python
def print_summary(all_results: dict) -> None:
    """打印总体发布汇总 + 账号异常反馈"""
    print("\n========== 总体发布汇总 ==========")
    success_count = sum(1 for results in all_results.values() for result in results.values() if result["success"])
    fail_count = sum(1 for results in all_results.values() for result in results.values() if not result["success"])
    print(f"成功: {success_count} 次")
    print(f"失败: {fail_count} 次")

    seen_issues = set()
    account_issues = []
    for results in all_results.values():
        for result_key, result in results.items():
            if not result.get("account_issue"):
                continue
            if result_key in seen_issues:
                continue
            seen_issues.add(result_key)
            platform_name = PLATFORM_NAMES.get(result_key.split("_")[0], result_key)
            account_issues.append((result_key, platform_name, result.get("message", "")))

    if account_issues:
        print("\n========== ⚠️ 账号异常反馈 ==========")
        for result_key, platform_name, message in account_issues:
            print(f"  [{result_key}] {platform_name}: {message}")
        print("\n以上账号可能已失效、被限制或登录异常，请前往对应平台检查账号状态，")
        print("必要时重新扫码登录或联系平台客服。")
```

- [ ] **Step 4: 修改 `publish/orchestrator.py::run_publish_with_params` 调用 `print_summary`**

在 `orchestrator.py` 的 import 块,把 `from publish.reporter import print_header, print_results` 改为:
```python
from publish.reporter import print_header, print_results, print_summary
```

把 `run_publish_with_params` 末尾(原行 1154-1179 的总体汇总 + 账号异常反馈逻辑)替换为:
```python
    print_summary(all_results)
    return 0 if fail_count == 0 else 1
```

等等 -- `fail_count` 也要重新算。实际上 `print_summary` 内部已经算了 success/fail count,但 `run_publish_with_params` 需要返回 `0 if fail_count == 0 else 1`。所以要么:
(a) `run_publish_with_params` 自己也算一遍 fail_count(重复计算)
(b) `print_summary` 返回 `(success_count, fail_count)`

选 (a),保持 `print_summary` 返回 None(纯打印职责):

```python
    print_summary(all_results)
    fail_count = sum(1 for results in all_results.values() for result in results.values() if not result["success"])
    return 0 if fail_count == 0 else 1
```

- [ ] **Step 5: 运行新测试验证通过**

Run: `python -m pytest tests/test_publish_reporter.py -v`
Expected: 4 个测试全 PASS

- [ ] **Step 6: 运行全量测试**

Run: `python -m pytest tests/ -v`
Expected: 全绿

- [ ] **Step 7: 提交**

```bash
git add publish/reporter.py publish/orchestrator.py tests/test_publish_reporter.py
git commit -m "refactor(publish): extract print_summary from run_publish_with_params

Move the overall summary + account-issue aggregation logic (was inlined
at the end of run_publish_with_params) into reporter.print_summary.
Orchestrator now just calls print_summary + computes fail_count for exit code."
```

---

## Task 6: 最终验证

**Files:** 无新建/修改(纯验证)

- [ ] **Step 1: 运行全量测试**

Run: `python -m pytest tests/ -v`
Expected: 全绿

预期测试清单:
- `test_publish_engine.py`: 16 个(PublishEngineTests 7 + RuntimePreflightTests 6 + AccountLoginFlowTests 3 + PublishFailurePolicyTests 2... 实际数以源码为准)
- `test_publish_cli.py`: 7 个
- `test_publish_dispatch.py`: 12 个
- `test_publish_reporter.py`: 4 个
- 其他现有测试(`test_xiaohongshu_uploader.py` / `test_weibo_uploader.py` / `test_baijiahao_uploader.py` / `test_bilibili_runtime.py` / `test_cookie_auth_pages.py` / `test_package_build.py`)

- [ ] **Step 2: 验证 `python publish_all.py --help`**

Run: `python publish_all.py --help`
Expected: 显示 argparse 用法,`prog=hgsau`,无 `publish` 子命令,显示 `--config` / `--platforms` / `--video` / `--title` / `--desc` / `--tags` / `--schedule` / `--start-from` / `--force`

- [ ] **Step 3: 验证 `hgsau --help`(需 reinstall)**

Run: `pip install -e . && hgsau --help`
Expected: 同 Step 2

- [ ] **Step 4: 验证 `python publish_all.py` 无参跑发布流程**

Run: `python publish_all.py`(在项目根,有 `publish_config.ini`)
Expected: 读取 INI,走发布流程(实际发布与否取决于 INI 配置;至少不 crash,行为与重构前一致)

- [ ] **Step 5: 验证 `publish_all.py` 行数**

Run: `wc -l publish_all.py publish/*.py`
Expected:
- `publish_all.py` < 80 行(薄壳)
- 各 `publish/*.py` 模块在预估范围(见 spec §架构表格)

- [ ] **Step 6: 如有遗漏,补提交;否则无新提交**

如果 Step 1-4 全过,Task 6 不需要新 commit。如果有修补,提交:
```bash
git add <fixed files>
git commit -m "fix(publish): <what was fixed>"
```

---

## Self-Review

### Spec coverage

| Spec 章节 | 对应 Task |
|---|---|
| §架构(7 模块 + 薄壳) | Task 1 |
| §向后兼容(CLI 合并) | Task 2 |
| §Dispatch(PlatformResult TypedDict) | Task 1 Step 5(定义) |
| §Dispatch(_PLATFORM_LOGIN 注册表) | Task 3 |
| §Dispatch(_PUBLISH_DISPATCH dict) | Task 4 |
| §Dispatch(8 个 publish_to_* 保持独立) | Task 1(迁入,不合并) |
| §数据流 | Task 1(层间 import 体现) |
| §Reporter(print_summary 抽取) | Task 5 |
| §Reporter(错误处理边界) | 已在 Task 1 保持(函数体不动) |
| §测试策略(现有测试) | Task 1 Step 10(patch target 更新) |
| §测试策略(改写 test_hgsau_cli) | Task 2 Step 1(test_publish_cli.py) |
| §测试策略(新增 dispatch 测试) | Task 3 + Task 4 |
| §测试策略(新增 reporter 测试) | Task 5 |
| §死代码(删 hgsau_cli.py) | Task 2 Step 5 |
| §死代码(改 pyproject.toml) | Task 2 Step 5 |
| §迁移顺序 12 步 | Task 1-6 覆盖全部 |
| §验证标准 | Task 6 |

无遗漏。

### Placeholder scan

无 TBD/TODO/"实现略"。所有 code step 都有完整代码块。

### Type consistency

- `PlatformResult` / `PlatformResultExtras`:Task 1 定义,Task 3/4 不引用(注册表用 `dict` 返回类型,与现状一致)
- `_PLATFORM_LOGIN`:Task 3 定义为 `dict[str, tuple[str, str, str]]`,测试匹配
- `_PUBLISH_DISPATCH`:Task 4 定义为 `dict[str, Callable]`,测试匹配
- `print_summary(all_results: dict) -> None`:Task 5 定义,orchestrator 调用匹配
- `main(argv: Optional[Sequence[str]] = None) -> int`:Task 2 定义,`publish_all.py` re-export + `__main__` 调用匹配
- `build_parser() -> argparse.ArgumentParser`:Task 2 定义,测试匹配

类型一致。

### 关键风险点

1. **Task 1 是最大 task**:1225 行迁 7 模块 + 测试 patch 更新。如果循环 import 卡住,优先把常量/类型下沉到 `constants.py`,把工具函数下沉到 `content.py`。
2. **patch target 更新易漏**:Step 10 的 10 条替换必须全做,否则测试 mock 不生效(表现为 `assert_not_awaited` 失败或 `assert_called` 失败)。
3. **Task 2 删 `hgsau_cli.py` 后 `test_package_build.py` 可能受影响**:该测试检查包构建内容,可能引用 `hgsau_cli`。如果 FAIL,更新该测试的期望值。
4. **Task 5 的 `fail_count` 重复计算**:orchestrator 末尾自己算 `fail_count` 用于返回值,`print_summary` 内部也算。这是有意的(保持 `print_summary` 纯打印职责),不是 bug。
