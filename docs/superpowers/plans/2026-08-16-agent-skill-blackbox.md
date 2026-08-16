# Agent 技能黑盒化（hgsau）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Agent 只通过 SKILL.md 和 `hgsau` 运行时输出即可完成发布，底层代码仓完全黑盒（pip 包为唯一入口）。

**Architecture:** 三层契约：① 分发层 pip 包 `hgsau`；② 契约层重写后的 SKILL.md（零仓库引用）；③ 运行时自描述层（`--help`/`--version`、语义化退出码、`[hgsau] CODE: desc。建议: action` 格式错误输出）。CLI 保持无子命令单入口。

**Tech Stack:** Python 3.9+，argparse，unittest（现有测试风格，无 pytest）。

**Spec:** `docs/superpowers/specs/2026-08-16-agent-skill-blackbox-design.md`

## Global Constraints

- 不新增 CLI 子命令，保持 `hgsau` 单入口（spec：组件 2 第 3 项）。
- 不加 `--json` 输出（spec：不做的事）。
- 退出码语义固定：0=全部成功，1=部分成功部分失败，2=全部平台失败，10=配置错误，11=环境错误，12=账号未登录且扫码未完成。
- 错误输出统一格式：`[hgsau] <错误码>: <描述>。建议: <可执行动作>`，输出到 stderr。
- SKILL.md 零仓库引用：不得出现 `pip install -e .`、`conf.example.py`、`pyproject.toml`、`requirements.txt`、目录结构等实现层信息。
- 文档中文优先，不维护国际化文案（CLAUDE.md）。
- 禁止通过截图/多模态 API 定位 UI；测试与验证只用文本和 DOM（CLAUDE.md 硬约束）。
- 测试用 unittest（现有 `tests/` 风格），运行命令 `python -m unittest tests.<模块名> -v`。

---

### Task 1: 错误码/退出码模块 `publish/errors.py`

**Files:**
- Create: `publish/errors.py`
- Test: `tests/test_publish_errors.py`

**Interfaces:**
- Consumes: 无
- Produces: 退出码常量 `EXIT_OK=0, EXIT_PARTIAL_FAIL=1, EXIT_ALL_FAIL=2, EXIT_CONFIG_ERROR=10, EXIT_ENV_ERROR=11, EXIT_AUTH_ERROR=12`；函数 `print_error(code: str, message: str, action: str) -> None`（打印到 stderr，格式 `[hgsau] {code}: {message}。建议: {action}`）。后续 Task 3/4/5 均从此模块导入。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_publish_errors.py
import contextlib
import io
import unittest

from publish.errors import (
    EXIT_ALL_FAIL,
    EXIT_AUTH_ERROR,
    EXIT_CONFIG_ERROR,
    EXIT_ENV_ERROR,
    EXIT_OK,
    EXIT_PARTIAL_FAIL,
    print_error,
)


class ExitCodeConstantsTests(unittest.TestCase):
    def test_exit_code_values(self):
        self.assertEqual(EXIT_OK, 0)
        self.assertEqual(EXIT_PARTIAL_FAIL, 1)
        self.assertEqual(EXIT_ALL_FAIL, 2)
        self.assertEqual(EXIT_CONFIG_ERROR, 10)
        self.assertEqual(EXIT_ENV_ERROR, 11)
        self.assertEqual(EXIT_AUTH_ERROR, 12)


class PrintErrorTests(unittest.TestCase):
    def test_output_format_goes_to_stderr(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            print_error("CFG-001", "配置文件不存在: /tmp/x.ini", "提供 --config 或同时指定 --platforms 和 --video")
        self.assertEqual(
            stderr.getvalue(),
            "[hgsau] CFG-001: 配置文件不存在: /tmp/x.ini。建议: 提供 --config 或同时指定 --platforms 和 --video\n",
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_publish_errors -v`
Expected: FAIL/ERROR，`ModuleNotFoundError: No module named 'publish.errors'`

- [ ] **Step 3: 写最小实现**

```python
# -*- coding: utf-8 -*-
"""Agent 可消费的错误输出:语义化退出码 + 错误码格式化"""
import sys

EXIT_OK = 0
EXIT_PARTIAL_FAIL = 1
EXIT_ALL_FAIL = 2
EXIT_CONFIG_ERROR = 10
EXIT_ENV_ERROR = 11
EXIT_AUTH_ERROR = 12


def print_error(code: str, message: str, action: str) -> None:
    print(f"[hgsau] {code}: {message}。建议: {action}", file=sys.stderr)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_publish_errors -v`
Expected: PASS（2 tests OK）

- [ ] **Step 5: Commit**

```bash
git add publish/errors.py tests/test_publish_errors.py
git commit -m "feat: add exit code constants and agent-facing error output format"
```

---

### Task 2: `hgsau --version` 参数

**Files:**
- Modify: `publish/orchestrator.py:251-266`（`build_parser`）
- Test: `tests/test_publish_cli.py`（追加测试类）

**Interfaces:**
- Consumes: 无
- Produces: `hgsau --version` 打印包版本号并退出 0。版本号来自 `importlib.metadata.version("hgsau")`，取不到时（开发环境未安装）回退 `0.0.0.dev0`。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_publish_cli.py` 末尾：

```python
class PublishCliVersionTests(unittest.TestCase):
    def test_version_flag_prints_version_and_exits_zero(self):
        parser = publish_all.build_parser()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as ctx:
                parser.parse_args(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertRegex(stdout.getvalue(), r"^hgsau \d+\.\d+\.\d+")
```

（`io`、`contextlib` 该文件顶部已 import。）

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_publish_cli.PublishCliVersionTests -v`
Expected: FAIL，`SystemExit not raised`（argparse 不认识 `--version`）

- [ ] **Step 3: 写最小实现**

`publish/orchestrator.py` 顶部 import 区追加：

```python
from importlib.metadata import PackageNotFoundError, version as pkg_version
```

`build_parser()` 内 `parser.add_argument("--config", ...)` 之前加：

```python
    try:
        _version = pkg_version("hgsau")
    except PackageNotFoundError:
        _version = "0.0.0.dev0"
    parser.add_argument("--version", action="version", version=f"hgsau {_version}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_publish_cli -v`
Expected: 全部 PASS（含原有 8 个测试）

- [ ] **Step 5: Commit**

```bash
git add publish/orchestrator.py tests/test_publish_cli.py
git commit -m "feat: add hgsau --version flag reporting installed package version"
```

---

### Task 3: 配置错误改用退出码 10 + CFG-xxx 错误码

**Files:**
- Modify: `publish/orchestrator.py:96-125`（`run_publish_with_params` 开头分支）、`publish/orchestrator.py:204-229`（`run_publish` 配置文件缺失分支）、`publish/orchestrator.py:151-155`（视频文件缺失）
- Test: `tests/test_publish_cli.py`（追加测试类）

**Interfaces:**
- Consumes: Task 1 的 `EXIT_CONFIG_ERROR`、`print_error`
- Produces: 所有配置类失败统一 `return EXIT_CONFIG_ERROR`（10），stderr 带 CFG-xxx 错误码。错误码分配：CFG-001 配置文件不存在；CFG-002 未配置启用平台；CFG-003 未找到视频文件；CFG-004 图文/图文转视频缺图片。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_publish_cli.py`：

```python
from publish.errors import EXIT_CONFIG_ERROR  # 文件顶部 import 区追加


class PublishCliConfigErrorTests(unittest.TestCase):
    def _run(self, params):
        coro = publish_all.run_publish_with_params(params)
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with contextlib.redirect_stderr(stderr):
                code = asyncio.run(coro)
        return code, stderr.getvalue()

    def test_no_enabled_platforms_returns_config_error(self):
        params = publish_all.default_params_from_overrides()
        code, stderr = self._run(params)
        self.assertEqual(code, EXIT_CONFIG_ERROR)
        self.assertIn("CFG-002", stderr)

    def test_note_mode_without_images_returns_config_error(self):
        params = publish_all.default_params_from_overrides()
        params.update(content_type="note", enabled_platforms=["douyin"], images=[])
        code, stderr = self._run(params)
        self.assertEqual(code, EXIT_CONFIG_ERROR)
        self.assertIn("CFG-004", stderr)

    def test_video_mode_missing_video_returns_config_error(self):
        params = publish_all.default_params_from_overrides()
        params.update(content_type="video", enabled_platforms=["douyin"], video_file="no_such_video.mp4")
        code, stderr = self._run(params)
        self.assertEqual(code, EXIT_CONFIG_ERROR)
        self.assertIn("CFG-003", stderr)

    def test_convert_to_video_without_images_returns_config_error(self):
        params = publish_all.default_params_from_overrides()
        params.update(content_type="note", convert_to_video=True, enabled_platforms=["douyin"], images=[])
        code, stderr = self._run(params)
        self.assertEqual(code, EXIT_CONFIG_ERROR)
        self.assertIn("CFG-004", stderr)
```

（顶部还需 `import asyncio`，若尚未导入。）

注意：`video_mode_missing_video` 与 `convert_to_video` 测试会走到 `runtime_preflight` 之前的分支（CFG-003 在 preflight 之前触发，见 Step 3 的顺序调整），不会真正启动浏览器。

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_publish_cli.PublishCliConfigErrorTests -v`
Expected: 4 个测试 FAIL（当前返回 1 而非 10，stderr 无错误码）

- [ ] **Step 3: 写最小实现**

`publish/orchestrator.py` 顶部追加 import：

```python
from publish.errors import EXIT_CONFIG_ERROR, print_error
```

修改 `run_publish_with_params`：

```python
async def run_publish_with_params(params: Dict[str, Any]) -> int:
    if not params["enabled_platforms"]:
        print_error("CFG-002", "未配置启用平台", "在 publish_config.ini [platforms] enabled= 设置，或使用 --platforms 覆盖")
        return EXIT_CONFIG_ERROR

    # 处理图文转视频
    if params["content_type"] == "note" and params["convert_to_video"]:
        if not params["images"]:
            print_error("CFG-004", "图文转视频需要提供图片", "在 publish_config.ini [common] images= 设置图片路径（英文逗号分隔）")
            return EXIT_CONFIG_ERROR
        # ...（转换逻辑保持不变，except 分支见下）

    if params["content_type"] == "note":
        if not params["images"]:
            print_error("CFG-004", "图文模式需要提供图片", "在 publish_config.ini [common] images= 设置图片路径（英文逗号分隔）")
            return EXIT_CONFIG_ERROR
```

图片转视频 `except` 分支（原 line 123-125）改为：

```python
        except Exception as e:
            print_error("ENV-005", f"图片转视频失败: {e}", "安装 ffmpeg 后重试（macOS: brew install ffmpeg; Ubuntu: sudo apt-get install ffmpeg）")
            return 11  # ENV 错误，Task 4 会替换为 EXIT_ENV_ERROR 常量
```

注意顺序调整：把"未找到视频文件"检查（原 line 152-155）移到 `runtime_preflight()` 之前：

```python
    video_files = get_video_files(params["video_file"])
    if not video_files:
        print_error("CFG-003", f"未找到视频文件: {params['video_file']}", "检查 [common] video_file= 路径或使用 --video 覆盖")
        return EXIT_CONFIG_ERROR

    if not await runtime_preflight():
        print_error("ENV-004", "运行环境检查失败", "按上方 ENV 错误码中的建议命令安装后重试")
        return 11  # Task 4 替换为 EXIT_ENV_ERROR
```

`run_publish` 配置文件缺失分支（原 line 217-220）改为：

```python
        if overrides is None or overrides.platforms is None or overrides.video is None:
            print_error("CFG-001", f"配置文件不存在: {config_path}", "提供 --config 指定配置文件，或同时指定 --platforms 和 --video")
            return EXIT_CONFIG_ERROR
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_publish_cli -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add publish/orchestrator.py tests/test_publish_cli.py
git commit -m "feat: return exit code 10 with CFG-xxx error codes for config failures"
```

---

### Task 4: 环境预检改用 ENV-xxx 错误码 + 退出码 11

**Files:**
- Modify: `publish/runtime.py:96-122`（`runtime_preflight`）、`publish/orchestrator.py`（preflight 失败分支，Task 3 已预埋 `return 11`）
- Test: `tests/test_bilibili_runtime.py` 同级新建 `tests/test_runtime_preflight_errors.py`

**Interfaces:**
- Consumes: Task 1 的 `print_error`、`EXIT_ENV_ERROR`
- Produces: `runtime_preflight() -> bool` 签名不变，失败路径 stderr 输出 ENV-xxx。错误码分配：ENV-001 Python 版本过低；ENV-002 patchright 未安装；ENV-003 依赖同步失败；ENV-004 Chromium 安装失败。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_runtime_preflight_errors.py
import asyncio
import contextlib
import io
import unittest
from unittest.mock import patch

from publish import runtime


def _run_preflight():
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout):
        with contextlib.redirect_stderr(stderr):
            ok = asyncio.run(runtime.runtime_preflight())
    return ok, stderr.getvalue()


class RuntimePreflightErrorTests(unittest.TestCase):
    def test_patchright_missing_reports_env_002(self):
        with patch.object(runtime, "patchright_available", return_value=False):
            ok, stderr = _run_preflight()
        self.assertFalse(ok)
        self.assertIn("[hgsau] ENV-002", stderr)
        self.assertIn("pip install hgsau", stderr)

    def test_chromium_install_failure_reports_env_004(self):
        with patch.object(runtime, "patchright_available", return_value=True), \
             patch.object(runtime, "sync_python_dependencies", return_value=True), \
             patch.object(runtime, "patchright_chromium_installed", return_value=False), \
             patch.object(runtime, "install_patchright_chromium", return_value=False):
            ok, stderr = _run_preflight()
        self.assertFalse(ok)
        self.assertIn("[hgsau] ENV-004", stderr)
        self.assertIn("patchright install chromium", stderr)

    def test_python_version_reports_env_001(self):
        with patch.object(runtime.sys, "version_info", (3, 8, 0)):
            ok, stderr = _run_preflight()
        self.assertFalse(ok)
        self.assertIn("[hgsau] ENV-001", stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_runtime_preflight_errors -v`
Expected: FAIL（stderr 无 `[hgsau] ENV-xxx` 格式）

- [ ] **Step 3: 写最小实现**

`publish/runtime.py` 顶部追加：

```python
from publish.errors import print_error
```

`runtime_preflight` 各失败分支改为：

```python
async def runtime_preflight() -> bool:
    print("运行环境预检")

    if sys.version_info < (3, 9):
        print_error("ENV-001", "需要 Python 3.9 或更高版本", f"当前为 {'.'.join(map(str, sys.version_info[:3]))}，请安装 Python 3.9+ 后重试")
        return False

    if not patchright_available():
        print_error("ENV-002", "未安装 patchright", "运行 pip install --upgrade hgsau 重新安装")
        return False

    if not sync_python_dependencies():
        print_error("ENV-003", "Python 依赖同步失败", "运行 pip install -r requirements.txt 后重试")
        return False
    print("Python 依赖已同步")

    if patchright_chromium_installed():
        print("Patchright Chromium 已安装")
        return True

    print("Patchright Chromium 未安装，正在安装...")
    if install_patchright_chromium():
        print("Patchright Chromium 安装成功")
        return True

    print_error(
        "ENV-004",
        "Patchright Chromium 安装失败",
        '运行 PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST="https://cdn.playwright.dev" patchright install chromium',
    )
    return False
```

`publish/orchestrator.py`：把 Task 3 预埋的两处 `return 11` 替换为 `return EXIT_ENV_ERROR`（import 行同步加 `EXIT_ENV_ERROR`；图片转视频失败处的 ENV-005 输出保持 Task 3 写法）。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_runtime_preflight_errors tests.test_publish_cli -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add publish/runtime.py publish/orchestrator.py tests/test_runtime_preflight_errors.py
git commit -m "feat: report ENV-xxx error codes with fix actions and exit code 11 on preflight failures"
```

---

### Task 5: 发布结果退出码 0/1/2/12 + AUTH/PUB 错误码

**Files:**
- Modify: `publish/orchestrator.py:31-93`（`publish_one_item`）、`publish/orchestrator.py:96-201`（两处汇总返回）、`publish/reporter.py:20-27`（`print_results`）
- Test: `tests/test_publish_reporter.py`（追加）、`tests/test_publish_cli.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 `EXIT_OK, EXIT_PARTIAL_FAIL, EXIT_ALL_FAIL, EXIT_AUTH_ERROR, print_error`
- Produces: 模块级函数 `exit_code_from_results(all_results: Dict[str, Dict[str, Any]]) -> int`；结果 dict 新增可选键 `error_code: str`（登录失败=AUTH-001，账号未配置=AUTH-002，平台发布失败由 reporter 按 `PUB-{platform}` 计算）。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_publish_cli.py`：

```python
from publish.orchestrator import exit_code_from_results  # 顶部追加
from publish.errors import EXIT_OK, EXIT_PARTIAL_FAIL, EXIT_ALL_FAIL, EXIT_AUTH_ERROR  # 顶部追加


class ExitCodeFromResultsTests(unittest.TestCase):
    def test_all_success(self):
        results = {"v.mp4": {"douyin": {"success": True}}}
        self.assertEqual(exit_code_from_results(results), EXIT_OK)

    def test_partial_fail(self):
        results = {"v.mp4": {"douyin": {"success": True}, "weibo": {"success": False, "message": "x"}}}
        self.assertEqual(exit_code_from_results(results), EXIT_PARTIAL_FAIL)

    def test_all_fail_platform_error(self):
        results = {"v.mp4": {"weibo": {"success": False, "message": "x"}}}
        self.assertEqual(exit_code_from_results(results), EXIT_ALL_FAIL)

    def test_all_fail_account_issues_is_auth_error(self):
        results = {"v.mp4": {"weibo": {"success": False, "message": "登录失败", "account_issue": True}}}
        self.assertEqual(exit_code_from_results(results), EXIT_AUTH_ERROR)
```

追加到 `tests/test_publish_reporter.py`：

```python
class PrintResultsErrorCodeTests(unittest.TestCase):
    def test_platform_failure_line_contains_pub_code(self):
        stderr_or_out = io.StringIO()
        with contextlib.redirect_stdout(stderr_or_out):
            print_results({"weibo": {"success": False, "message": "上传超时"}})
        self.assertIn("[PUB-weibo]", stderr_or_out.getvalue())

    def test_login_failure_line_contains_auth_code(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            print_results({"douyin": {"success": False, "message": "登录失败: 抖音", "error_code": "AUTH-001"}})
        self.assertIn("[AUTH-001]", out.getvalue())
```

（按该文件已有的 import 方式引入 `print_results`、`io`、`contextlib`，若缺则补。）

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_publish_cli.ExitCodeFromResultsTests tests.test_publish_reporter.PrintResultsErrorCodeTests -v`
Expected: FAIL（`exit_code_from_results` 不存在；结果行无错误码）

- [ ] **Step 3: 写最小实现**

`publish/orchestrator.py`：

顶部 import 更新：

```python
from publish.errors import (
    EXIT_ALL_FAIL,
    EXIT_AUTH_ERROR,
    EXIT_CONFIG_ERROR,
    EXIT_ENV_ERROR,
    EXIT_OK,
    EXIT_PARTIAL_FAIL,
    print_error,
)
```

新增模块级函数（放在 `publish_one_item` 前）：

```python
def exit_code_from_results(all_results: Dict[str, Dict[str, Any]]) -> int:
    results = [r for item_results in all_results.values() for r in item_results.values()]
    if not results:
        return EXIT_ALL_FAIL
    failures = [r for r in results if not r["success"]]
    if not failures:
        return EXIT_OK
    if len(failures) == len(results):
        if all(r.get("account_issue") for r in failures):
            return EXIT_AUTH_ERROR
        return EXIT_ALL_FAIL
    return EXIT_PARTIAL_FAIL
```

`publish_one_item` 中两处改动：

未配置账号分支（原 line 45-49）：

```python
        if not account_files:
            print(f"[{i}/{total}] 发布到 {platform_name}...")
            results[platform] = {
                "success": False,
                "message": f"未配置 {platform} 账号",
                "account_issue": True,
                "error_code": "AUTH-002",
            }
            print("  ❌ 失败: 未配置账号")
            continue
```

登录失败分支（原 line 71-82）：

```python
                if not login_ok:
                    msg = f"登录失败: {platform_name}"
                    if login_error:
                        msg += f" - {login_error}"
                    results[result_key] = {
                        "success": False,
                        "message": msg,
                        "account_issue": True,
                        "error_code": "AUTH-001",
                    }
                    print_error("AUTH-001", msg, f"引导用户在弹出的浏览器中完成 {platform_name} 扫码登录后重试")
                    continue
```

两处汇总返回（note 路径原 line 148-149、视频路径原 line 200-201）统一改为：

```python
    print_summary(all_results)
    return exit_code_from_results(all_results)
```

`publish/reporter.py` 的 `print_results`：

```python
def print_results(results: dict):
    """打印发布结果汇总"""
    print("\n========== 发布结果 ==========")
    for platform, result in results.items():
        platform_name = PLATFORM_NAMES.get(platform, platform)
        if result["success"]:
            status = "✅ 成功"
        else:
            error_code = result.get("error_code") or f"PUB-{platform.split('_')[0]}"
            status = f"❌ 失败 [{error_code}]: {result['message']}"
        print(f"{platform_name}: {status}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_publish_cli tests.test_publish_reporter -v`
Expected: 全部 PASS（含原有测试——若有原有测试断言旧的失败行格式，按新格式更新断言）

- [ ] **Step 5: Commit**

```bash
git add publish/orchestrator.py publish/reporter.py tests/test_publish_cli.py tests/test_publish_reporter.py
git commit -m "feat: semantic exit codes 0/1/2/12 with AUTH/PUB error codes in publish results"
```

---

### Task 6: `--help` 文案完善（参数与 ini 字段对应）

**Files:**
- Modify: `publish/orchestrator.py:251-266`（`build_parser` 各参数 help）
- Test: `tests/test_publish_cli.py`（追加测试类）

**Interfaces:**
- Consumes: 无
- Produces: `--help` 输出为 SKILL.md 之外的第二份权威文档，每个参数 help 含对应 ini 字段名。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_publish_cli.py`：

```python
class PublishCliHelpTextTests(unittest.TestCase):
    def test_help_documents_ini_field_mapping(self):
        help_text = publish_all.build_parser().format_help()
        for fragment in [
            "[common] video_file",
            "[common] title",
            "[common] desc",
            "[common] tags",
            "[platforms] enabled",
            "[common] publish_time",
            "[common] start_from",
        ]:
            self.assertIn(fragment, help_text)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_publish_cli.PublishCliHelpTextTests -v`
Expected: FAIL（help 中无 ini 字段名）

- [ ] **Step 3: 写最小实现**

`build_parser()` 中各参数 help 替换为：

```python
    parser = argparse.ArgumentParser(
        prog="hgsau",
        description="把视频/图文一键发布到抖音/小红书/快手/微博/B站/视频号/百家号。无参数时读取 publish_config.ini 执行完整发布。",
    )
    parser.add_argument("--config", default="publish_config.ini", help="配置文件路径 (默认: publish_config.ini)")
    parser.add_argument("--platforms", default=None, help="临时覆盖启用平台，逗号分隔 (对应 [platforms] enabled)")
    parser.add_argument("--video", default=None, help="临时覆盖视频文件/目录路径 (对应 [common] video_file)")
    parser.add_argument("--title", default=None, help="临时覆盖标题 (对应 [common] title)")
    parser.add_argument("--desc", default=None, help="临时覆盖描述 (对应 [common] desc)")
    parser.add_argument("--tags", default=None, help="临时覆盖话题标签，逗号分隔 (对应 [common] tags)")
    parser.add_argument("--schedule", type=_schedule_value, default=None, help=f"临时覆盖定时发布时间，格式 {schedule_help} (对应 [common] publish_strategy/publish_time)")
    parser.add_argument("--start-from", type=int, default=None, help="断点续传起始序号，1 起 (对应 [common] start_from)")
    parser.add_argument("--force", action="store_true", help="强制重新生成视频配置 (对应 [common] 一次性 force)")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_publish_cli -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add publish/orchestrator.py tests/test_publish_cli.py
git commit -m "docs: map every hgsau CLI override to its publish_config.ini field in --help"
```

---

### Task 7: SAU_HOME 优先于 .git 检测 + pip 模式初始化验证

**Files:**
- Modify: `conf.py:10-22`（`_detect_mode`）
- Test: `tests/test_conf_pip_mode.py`（新建）

**Interfaces:**
- Consumes: 无
- Produces: `SAU_HOME` 环境变量在开发模式与 pip 模式下均生效（可测试的数据目录覆盖）；pip 模式自动创建数据目录的行为保持不变。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_conf_pip_mode.py
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ConfPipModeTests(unittest.TestCase):
    def test_sau_home_overrides_base_dir_even_in_dev_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["SAU_HOME"] = tmp
            result = subprocess.run(
                [sys.executable, "-c", "import conf; print(conf.BASE_DIR)"],
                env=env, capture_output=True, text=True, check=True,
            )
            self.assertEqual(result.stdout.strip(), str(Path(tmp).resolve()))

    def test_sau_home_dir_auto_created_with_cookies(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "data"
            env = os.environ.copy()
            env["SAU_HOME"] = str(target)
            subprocess.run(
                [sys.executable, "-c", "import conf"],
                env=env, capture_output=True, text=True, check=True,
            )
            self.assertTrue((target / "cookies").is_dir())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_conf_pip_mode -v`
Expected: 第一个测试 FAIL（当前开发模式下 `.git` 检测优先于 SAU_HOME，BASE_DIR 是仓库根）；第二个可能 PASS（tmp 下无 .git，但需确认）

- [ ] **Step 3: 写最小实现**

`conf.py` 的 `_detect_mode` 把 SAU_HOME 检查移到 `.git` 检查之前：

```python
def _detect_mode() -> Path:
    """SAU_HOME 环境变量始终优先。
    开发模式：项目根有 .git 目录 -> BASE_DIR = 项目根
    pip 模式：-> BASE_DIR = ~/.social-auto-upload/"""
    sau_home = os.environ.get("SAU_HOME", "").strip()
    if sau_home:
        return Path(sau_home)
    if (_PROJECT_ROOT / ".git").is_dir():
        return _PROJECT_ROOT
    home_dir = Path.home() / ".social-auto-upload"
    return home_dir
```

（目录自动创建逻辑保持在 `BASE_DIR = _detect_mode()` 之后的现有代码中执行。）

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_conf_pip_mode -v`
Expected: PASS。再跑 `python -m unittest tests.test_publish_cli -v` 确认无回归。

- [ ] **Step 5: Commit**

```bash
git add conf.py tests/test_conf_pip_mode.py
git commit -m "feat: make SAU_HOME override BASE_DIR in all modes for testable pip-mode init"
```

---

### Task 8: 重写 SKILL.md（零仓库引用）

**Files:**
- Modify: `skills/hgsau-cli/SKILL.md`（全文重写）
- Test: `tests/test_publish_cli.py`（追加 SKILL.md 一致性测试）

**Interfaces:**
- Consumes: Task 1-7 产出的 CLI 行为（退出码表、错误格式、`--version`、ini 字段映射）
- Produces: 黑盒契约文档。SKILL.md version 字段与 pyproject 版本一致（当前 0.4.6）。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_publish_cli.py`：

```python
class SkillDocBlackboxTests(unittest.TestCase):
    SKILL_PATH = Path("skills/hgsau-cli/SKILL.md")

    def test_no_repo_references(self):
        text = self.SKILL_PATH.read_text(encoding="utf-8")
        for forbidden in ["-e .", "conf.example.py", "pyproject.toml", "requirements.txt", "publish_all", "uv pip"]:
            self.assertNotIn(forbidden, text, f"SKILL.md 不应包含仓库实现细节: {forbidden}")

    def test_documents_exit_codes_and_install(self):
        text = self.SKILL_PATH.read_text(encoding="utf-8")
        self.assertIn("pip install hgsau", text)
        for code_doc in ["10", "11", "12", "CFG-", "ENV-", "AUTH-", "PUB-"]:
            self.assertIn(code_doc, text)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_publish_cli.SkillDocBlackboxTests -v`
Expected: FAIL（现有 SKILL.md 含 `uv pip install -e .`、`pyproject.toml` 等）

- [ ] **Step 3: 全文重写 SKILL.md**

```markdown
---
name: hgsau-cli
description: Use when 用户要用 hgsau 发布/上传视频或图文、配置多平台发布、发布到抖音/小红书/快手/微博/B站/视频号/百家号，或排查 hgsau、publish_config.ini、账号登录校验、浏览器驱动环境问题
version: "0.4.6"
---

# hgsau CLI 使用指南

## 这是什么

`hgsau` 是一个 pip 包，把视频/图文一键发布到 7 个国内平台。本文件是它对 Agent 的完整接口契约：安装、配置、调用、读取结果所需的信息全部在此或 `hgsau` 运行时输出中。

## 安装

```bash
pip install hgsau
```

系统依赖：

```bash
# 浏览器驱动（首次发布时会自动检查并尝试自动安装，失败时按 ENV-004 提示手动执行）
PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST="https://cdn.playwright.dev" patchright install chromium

# ffmpeg（仅"图文转视频"功能需要）
# macOS: brew install ffmpeg
# Ubuntu/Debian: sudo apt-get install ffmpeg
```

首次运行会自动在 `~/.social-auto-upload/` 创建数据目录（cookies、配置），无需手动初始化。可用环境变量 `SAU_HOME` 指定其他数据目录。

## 已验证平台（7个）

| 平台标识 | 名称 | 视频 | 图文 | 说明 |
| --- | --- | --- | --- | --- |
| `douyin` | 抖音 | ✅ | ✅ | |
| `xiaohongshu` | 小红书 | ✅ | ✅ | 浏览器自动化 |
| `kuaishou` | 快手 | ✅ | ✅ | 浏览器自动化 |
| `bilibili` | B站 | ✅ | ❌ | 自动准备 biliup，自动抓取BV号 |
| `tencent` | 视频号 | ✅ | ❌ | |
| `baijiahao` | 百家号 | ✅ | ❌ | 浏览器自动化 |
| `weibo` | 微博 | ✅ | ❌ | 支持逗号分隔多账号，每个账号各发一遍 |

## 触发场景

当用户表达下面任一意图时使用本 skill：

- 发布视频、上传视频、一键发布、多平台发布、图文发布
- 发布到抖音、小红书、快手、微博、B站、视频号、百家号
- 配置发布平台、账号、cookie、登录校验、扫码登录
- 排查 `hgsau`、`publish_config.ini`、Chromium 或浏览器驱动问题

## 配置

### publish_config.ini 关键字段

```ini
[common]
content_type = video          # video=视频, note=图文
title =                       # 标题（所有平台共用）
desc =                        # 描述，支持\n换行
tags =                        # 话题标签，英文逗号分隔
video_file =                  # 视频路径
images =                      # 图文图片路径，英文逗号分隔
publish_strategy = immediate  # immediate=立即, scheduled=定时
publish_time =                # 定时发布时间 YYYY-MM-DD HH:MM
start_from =                  # 断点续传起始序号
convert_to_video = false      # 图文转视频（仅 note 模式）

[platforms]
enabled =                     # 启用平台，英文逗号分隔
# 各平台账号文件路径（长期保留）
douyin_account = cookies/douyin_uploader/account.json
weibo_account = cookies/weibo_uploader/account1.json  # 微博支持逗号分隔多账号
```

### 一次性字段 vs 长期字段

- **长期保留**：各平台账号文件路径（`*_account`）
- **每次发布前必须重新设置**：`enabled`、`title`、`desc`、`tags`、`video_file`/`images`、`publish_strategy`、`publish_time`、`start_from`
- 发布流程结束后，`hgsau` 自动清空一次性任务字段，避免下次沿用旧配置

## 调用

```bash
hgsau                                  # 读取 publish_config.ini 执行完整发布
hgsau --platforms douyin,weibo --video videos/demo.mp4 --title "标题"
hgsau --config my_publish_config.ini
hgsau --start-from 5
hgsau --force
hgsau --version                        # 查看已安装版本
hgsau --help                           # 全部参数说明（每个参数标注对应的 ini 字段）
```

命令行参数只作为本次运行的临时覆盖；也可以不写 ini，直接 `hgsau --platforms ... --video ...` 运行。

## 读取结果

### 退出码

| 退出码 | 含义 | Agent 下一步 |
| --- | --- | --- |
| 0 | 全部平台发布成功 | 从汇总中提取结果链接汇报给用户 |
| 1 | 部分平台成功、部分失败 | 读"发布结果"汇总，向用户汇报成败明细 |
| 2 | 全部平台发布失败 | 读各平台 [PUB-xxx] 错误码，按建议动作处理 |
| 10 | 配置错误 | 按 stderr 的 CFG-xxx 建议修配置或改用 CLI 覆盖参数 |
| 11 | 环境错误 | 按 stderr 的 ENV-xxx 建议执行安装命令后重试 |
| 12 | 账号未登录且扫码未完成 | 引导用户完成扫码登录后重试 |

### 错误输出格式

所有流程级错误输出到 stderr，格式固定：

```
[hgsau] <错误码>: <描述>。建议: <可执行的动作>
```

错误码体系：`CFG-xxx` 配置、`ENV-xxx` 环境、`AUTH-xxx` 登录、`PUB-<platform>` 平台发布失败（出现在"发布结果"汇总行中）。

### 结果汇总格式

发布结束打印稳定格式的汇总（stdout）：

```
========== 发布结果 ==========
抖音: ✅ 成功
微博: ❌ 失败 [PUB-weibo]: 上传超时

========== 总体发布汇总 ==========
成功: 1 次
失败: 1 次
```

成功平台的分享链接写入 Excel 结果文件并显示在输出中。

## Agent 注意事项

- 不要先单独校验登录后再要求用户二次确认发布。
- 当登录流程生成本地二维码图片时，应直接展示图片或明确告诉用户打开哪个本地图片扫码，不要只回传路径。
- Bilibili 等需要真实交互的登录场景，不要在非交互环境里强行代跑；应指导用户在本地真实终端完成扫码后再继续发布。
- 微博多账号发布时，同一视频会为每个账号各发一遍。
- 本项目文档中文优先，不维护国际化文案。
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_publish_cli -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add skills/hgsau-cli/SKILL.md tests/test_publish_cli.py
git commit -m "docs: rewrite SKILL.md as blackbox contract with exit codes and zero repo references"
```

---

### Task 9: 全量回归 + 手工黑盒验证

**Files:**
- 无代码改动；验证任务

**Interfaces:**
- Consumes: Task 1-8 全部产出
- Produces: 验证结论（黑盒不变式成立：Agent 所需信息全部在 SKILL.md 或 CLI 输出中）

- [ ] **Step 1: 全量单测**

Run: `python -m unittest discover tests -v 2>&1 | tail -20`
Expected: 全部 PASS（如有环境依赖型测试在本地跑不动，记录并跳过，不算失败）

- [ ] **Step 2: 手工验证退出码**

```bash
hgsau --platforms douyin --video no_such.mp4; echo "exit=$?"    # 期望 exit=10, stderr 含 CFG-003
hgsau --version; echo "exit=$?"                                  # 期望打印版本, exit=0
```

Expected: 与 SKILL.md 退出码表一致

- [ ] **Step 3: pip 模式安装验证（黑盒终极检验）**

```bash
python -m venv /tmp/hgsau-blackbox-test && source /tmp/hgsau-blackbox-test/bin/activate
pip install dist/hgsau-*.whl   # 或 pip install --index-url https://test.pypi.org/simple hgsau
cd /tmp && hgsau --help && hgsau --version
SAU_HOME=/tmp/hgsau-data hgsau --platforms douyin --video no_such.mp4; echo "exit=$?"
deactivate
```

Expected: 不存在本仓库副本的环境下，`--help`/`--version` 正常；数据目录在 SAU_HOME 下自动创建；退出码与错误码符合预期

- [ ] **Step 4: 汇报验证结论**

向用户汇报各项验证结果；如有失败项，修复后重跑本任务。

- [ ] **Step 5: Commit（仅当验证中发现问题并修复时）**

```bash
git add -u && git commit -m "fix: address issues found in blackbox verification"
```
