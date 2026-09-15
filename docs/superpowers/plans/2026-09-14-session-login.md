# 发布会话内登录合并（每素材单浏览器）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 同一平台对同一素材的发布只启动一次浏览器：登录判定、扫码、上传、结果确认全部并入 `_browser_session`，素材发布结束统一关闭。

**Architecture:** 登录状态机做进 `BaseBrowserUploader._browser_session` 的 `yield page` 之前（新方法 `_ensure_session_login`）；各平台 `upload()` except 链最前放行 `LoginCheckError` / `LoginTimeoutError`；`dispatch.publish_to_platform` 集中把两类异常转结果；orchestrator 对浏览器平台跳过登录预检（仅 bilibili 保留）、中途失效重试改为直接重调一次发布；5 平台 `validate_login_and_strategy` 移除 `cookie_auth` 调用。

**Tech Stack:** Python 3.9+（patchright async_playwright、unittest/pytest）。

**Spec:** `docs/superpowers/specs/2026-09-14-session-login-design.md`

## 执行前审视修正（优先于下方原始代码草案）

- 采用现有七项任务的职责划分；具体代码草案需按以下边界调整，不逐字照搬。
- 6 个浏览器平台的本地验证必须允许缺少账号文件；首次登录由会话创建父目录并写入账号状态。
- 有效登录快路径必须保留平台既有正向 DOM / URL 判定及必要就绪等待。扫码完成后在当前页返回发布入口，重新确认登录，才保存状态和允许上传。
- context / page 初始化也纳入资源清理范围；一个关闭动作失败不能阻止其余资源关闭，也不能覆盖原始发布结果。登录失败不得在退出时保存不完整状态。
- Task 5 原始步骤“删除登录异常分支、保留通用捕获”会吞掉异常；应在通用捕获前显式放行登录异常，再统一转换。测试必须覆盖真实 wrapper。
- 登录交互中断采用固定、无敏感数据的消息。网络、未知页面和保存文件失败仍保留对应分类；不得把原始异常字符串放入对外消息。
- 保留小红书/快手切换扫码面板、已有二维码本地输出和刷新能力，兼容无头配置。视频号发布页内 qrconnect iframe 也需触发登录。驱动管理器进入/退出失败与取消操作均补充回归。
- 仅浏览器平台移除独立登录预检和强制登录恢复。B站保留原流程。每素材正常一次会话；明确提交前失效最多重开一次恢复会话，超时和提交结果未知不得自动重复发布。
- 不执行真实投稿；完成回归和独立审查后按 AGENTS.md 提交、推送，远端 CI 通过后发布 0.8.6 并验证安装。

## Global Constraints

- 不确定失败不触发扫码、不自动重试：NET-001 / PAGE-001 / ENV-006 语义与 `safe_to_retry=False` 保持。
- `LoginTimeoutError` → AUTH-001、`safe_to_retry=True`。
- 重复提交保护不变：`_submission_attempted` / RUN-004 语义原样；登录异常发生在任何提交动作之前。
- 扫码 stderr 提醒文案逐字保留（Agent ≥360s 超时契约）。
- tencent 上传会话退出保存保持禁用（`save_state=False`）；扫码成功后的保存在状态机内完成。
- bilibili（CLI）流程不变，发布前预检保留。
- Python 3.9 兼容：禁用 `match`、`X | Y` 类型注解等 3.10+ 语法。
- 单测命令 `.venv/bin/python -m pytest <file> -q`；全量 `.venv/bin/python -m pytest tests license_server/tests -q`。
- 不执行真实登录或发布；文档中文优先。

---

### Task 1: auth.py — `LoginTimeoutError` 与扫码提醒 helper

**Files:**
- Modify: `publish/auth.py`
- Test: `tests/test_session_login.py`（新建）

**Interfaces:**
- Produces: `LoginTimeoutError(RuntimeError)`，构造签名 `__init__(self, message: str = "扫码登录超时")`，方法 `to_result() -> dict`；模块函数 `warn_qr_login_pending(platform_label: str) -> None`；`login_check` 装饰器同时放行两类异常。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_session_login.py`：

```python
from __future__ import annotations

import asyncio
import contextlib
import io
import unittest

from publish.auth import (
    LoginCheckError,
    LoginTimeoutError,
    login_check,
    warn_qr_login_pending,
)


class LoginTimeoutErrorTests(unittest.TestCase):
    def test_to_result_is_auth_failure_with_safe_retry(self):
        result = LoginTimeoutError("微博扫码登录超时").to_result()
        self.assertFalse(result["success"])
        self.assertEqual("AUTH-001", result["error_code"])
        self.assertTrue(result["account_issue"])
        self.assertEqual("login_timeout", result["issue_type"])
        self.assertTrue(result["safe_to_retry"])
        self.assertIn("扫码", result["action"])
        self.assertIn("微博扫码登录超时", result["message"])

    def test_login_check_passes_through_login_timeout_error(self):
        @login_check
        async def check():
            raise LoginTimeoutError("interrupted")

        with self.assertRaises(LoginTimeoutError):
            asyncio.run(check())

    def test_login_check_still_classifies_other_errors(self):
        @login_check
        async def check():
            raise TimeoutError("timed out")

        with self.assertRaises(LoginCheckError):
            asyncio.run(check())

    def test_warn_qr_login_pending_writes_agent_timeout_contract(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            warn_qr_login_pending("微博")
        text = stderr.getvalue()
        self.assertIn("[opub] 微博 未登录", text)
        self.assertIn("最长约 5 分钟", text)
        self.assertIn("不低于 360 秒", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_session_login.py -q`
Expected: FAIL — `ImportError: cannot import name 'LoginTimeoutError'`

- [ ] **Step 3: 实现**

`publish/auth.py`：顶部加 `import sys`。在 `LoginCheckError` 类之后新增：

```python
class LoginTimeoutError(RuntimeError):
    """扫码登录未在时限内完成或交互中断:定论性登录失败,可安全重试。"""

    def __init__(self, message: str = "扫码登录超时"):
        super().__init__(message)

    def to_result(self) -> dict:
        return {
            'success': False,
            'message': str(self),
            'account_issue': True,
            'issue_type': 'login_timeout',
            'error_code': 'AUTH-001',
            'action': '引导用户在弹出的浏览器中完成扫码登录后重试',
            'safe_to_retry': True,
        }


def warn_qr_login_pending(platform_label: str) -> None:
    print(
        f"[opub] {platform_label} 未登录,即将打开浏览器等待扫码登录(最长约 5 分钟)。"
        f"若由 Agent 调用,请确保工具超时不低于 360 秒",
        file=sys.stderr,
    )
```

`login_check` 装饰器的放行分支改为同时放行两类：

```python
        try:
            return await check(*args, **kwargs)
        except (LoginCheckError, LoginTimeoutError):
            raise
        except Exception as exc:
            raise classify_login_exception(exc) from None
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_session_login.py tests/test_login_check_classification.py -q`
Expected: PASS（auth.py 原有分类测试不受影响）

- [ ] **Step 5: Commit**

```bash
git add publish/auth.py tests/test_session_login.py
git commit -m "feat: add LoginTimeoutError and shared QR warning helper"
```

---

### Task 2: base_video.py — `_browser_session` 内嵌登录状态机

**Files:**
- Modify: `uploader/base_video.py`（`_browser_session` 现位于约 330-353 行）
- Modify: `tests/test_base_uploader_session.py`（`FakePage` 增补方法）
- Test: `tests/test_session_login.py`

**Interfaces:**
- Consumes: Task 1 的 `LoginCheckError` / `LoginTimeoutError` / `classify_login_exception` / `warn_qr_login_pending`。
- Produces: `BaseBrowserUploader._ensure_session_login(self, page) -> None`（正常返回 = 已登录且在上传页；异常 = `LoginCheckError` 或 `LoginTimeoutError`）；`_browser_session` 在 `new_page()` 后、`yield` 前调用它。

- [ ] **Step 1: 写失败测试**

在 `tests/test_session_login.py` 追加（`from unittest.mock import AsyncMock, patch` 与 `from uploader.base_video import BaseBrowserUploader` 移到文件顶部 import 区，与 Task 1 的导入合并；以下为新增的类与用例）：

```python


class FakeSessionUploader(BaseBrowserUploader):
    PLATFORM_NAME = "假平台"
    UPLOAD_URL = "https://example.com/upload"
    LOGIN_URL = "https://example.com/login"
    LOGIN_MARKERS = ["/login"]
    PUBLISH_MARKERS = []


class RecordingContext:
    def __init__(self):
        self.storage_state_calls = []

    async def storage_state(self, path=None):
        self.storage_state_calls.append(path)


class FakeSessionPage:
    """状态机测试用假 page:goto 记录并跳转;可配置落地 URL 或抛错。"""

    def __init__(self, url="https://example.com/upload", land=None, goto_error=None):
        self.url = url
        self.land = land or {}
        self.goto_error = goto_error
        self.goto_calls = []
        self.context = RecordingContext()

    async def goto(self, url, timeout=None, wait_until=None):
        self.goto_calls.append(url)
        if self.goto_error is not None:
            raise self.goto_error
        self.url = self.land.get(url, url)

    async def wait_for_timeout(self, ms):
        pass


def _make_uploader(account_file="/fake/account.json"):
    uploader = FakeSessionUploader.__new__(FakeSessionUploader)
    uploader.account_file = account_file
    return uploader


class SessionLoginMachineTests(unittest.TestCase):
    def test_fast_path_skips_login_flow(self):
        uploader = _make_uploader()
        page = FakeSessionPage()
        with patch.object(FakeSessionUploader, "is_login_required", AsyncMock(return_value=False)):
            asyncio.run(uploader._ensure_session_login(page))
        self.assertEqual(["https://example.com/upload"], page.goto_calls)

    def test_qr_flow_warns_saves_state_and_returns_to_upload_page(self):
        uploader = _make_uploader("/fake/acc.json")
        page = FakeSessionPage(url="https://example.com/login?x=1")
        stderr = io.StringIO()
        with patch.object(FakeSessionUploader, "is_login_required", AsyncMock(return_value=True)), \
             patch.object(FakeSessionUploader, "is_login_completed", AsyncMock(return_value=True)), \
             contextlib.redirect_stderr(stderr):
            asyncio.run(uploader._ensure_session_login(page))
        self.assertEqual(
            ["https://example.com/upload", "https://example.com/login", "https://example.com/upload"],
            page.goto_calls,
        )
        self.assertEqual(["/fake/acc.json"], page.context.storage_state_calls)
        self.assertIn("不低于 360 秒", stderr.getvalue())

    def test_qr_timeout_raises_login_timeout(self):
        uploader = _make_uploader()
        page = FakeSessionPage(url="https://example.com/login")
        with patch.object(FakeSessionUploader, "is_login_required", AsyncMock(return_value=True)), \
             patch.object(FakeSessionUploader, "is_login_completed", AsyncMock(return_value=False)):
            with self.assertRaises(LoginTimeoutError):
                asyncio.run(uploader._ensure_session_login(page))

    def test_navigation_network_error_is_classified_and_never_enters_qr(self):
        uploader = _make_uploader()
        page = FakeSessionPage(goto_error=TimeoutError("net::err_timed_out"))
        with patch.object(FakeSessionUploader, "is_login_required", AsyncMock(side_effect=AssertionError("must not check"))):
            with self.assertRaises(LoginCheckError) as ctx:
                asyncio.run(uploader._ensure_session_login(page))
        self.assertEqual("NET-001", ctx.exception.error_code)
        self.assertEqual(["https://example.com/upload"], page.goto_calls)

    def test_non_login_redirect_raises_page_error(self):
        uploader = _make_uploader()
        page = FakeSessionPage(land={"https://example.com/upload": "https://example.com/interstitial"})
        with patch.object(FakeSessionUploader, "is_login_required", AsyncMock(return_value=False)):
            with self.assertRaises(LoginCheckError) as ctx:
                asyncio.run(uploader._ensure_session_login(page))
        self.assertEqual("PAGE-001", ctx.exception.error_code)

    def test_tencent_style_redirect_detected_by_login_markers(self):
        uploader = _make_uploader()
        page = FakeSessionPage(land={"https://example.com/upload": "https://example.com/login.html"})
        with patch.object(FakeSessionUploader, "is_login_completed", AsyncMock(return_value=True)):
            asyncio.run(uploader._ensure_session_login(page))
        self.assertEqual(["/fake/account.json"], page.context.storage_state_calls)


class BrowserSessionIntegrationTests(unittest.TestCase):
    """_browser_session 集成:状态机并入 yield 前,退出保存规则不变。

    FakeContext / FakeBrowser / FakePlaywright 从 tests/test_base_uploader_session.py
    顶部复制定义(19-61 行),追加 RecordingSessionContext。
    """

    def test_browser_session_runs_login_state_machine_and_closes_on_failure(self):
        uploader = _make_uploader()
        uploader.headless = True
        fake_context = FakeContext()
        with patch.object(FakeSessionUploader, "_ensure_session_login", AsyncMock(side_effect=LoginTimeoutError("超时"))), \
             patch("uploader.base_video.async_playwright") as mock_ap, \
             patch("uploader.base_video.set_init_script", side_effect=lambda ctx: ctx), \
             patch("uploader.base_video.os.path.exists", return_value=True):
            mock_ap.return_value = FakePlaywright(fake_context)

            async def run():
                async with uploader._browser_session(save_on_success_only=True):
                    pass  # 状态机在 yield 前抛出,块体不可达
            with self.assertRaises(LoginTimeoutError):
                asyncio.run(run())
        self.assertTrue(fake_context.closed)
        self.assertEqual([], fake_context.storage_state_calls)

    def test_qr_save_survives_upload_failure(self):
        # 状态机内已保存 1 次;save_on_success_only=True + 上传失败 → 退出不覆盖保存
        uploader = _make_uploader("/fake/account.json")
        uploader.headless = True
        page = FakeSessionPage(url="https://example.com/login")
        fake_context = RecordingSessionContext(page)
        with patch.object(FakeSessionUploader, "is_login_required", AsyncMock(return_value=True)), \
             patch.object(FakeSessionUploader, "is_login_completed", AsyncMock(return_value=True)), \
             patch("uploader.base_video.async_playwright") as mock_ap, \
             patch("uploader.base_video.set_init_script", side_effect=lambda ctx: ctx), \
             patch("uploader.base_video.os.path.exists", return_value=True):
            mock_ap.return_value = FakePlaywright(fake_context)

            async def run():
                async with uploader._browser_session(save_on_success_only=True) as _:
                    raise RuntimeError("上传失败")
            with self.assertRaises(RuntimeError):
                asyncio.run(run())
        self.assertEqual(["/fake/account.json"], fake_context.storage_state_calls)
```

`RecordingSessionContext` 放在 `FakePlaywright` 定义之后（`new_page` 返回注入的 `FakeSessionPage`，其 `.context` 回指该 context，使状态机的 `page.context.storage_state` 落到同一对象）：

```python
class RecordingSessionContext(FakeContext):
    """FakeContext 变体:new_page 返回接好 context 的 FakeSessionPage。"""

    def __init__(self, page):
        super().__init__()
        page.context = self
        self._page = page

    async def new_page(self):
        return self._page
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_session_login.py -q`
Expected: FAIL — `AttributeError: 'FakeSessionUploader' object has no attribute '_ensure_session_login'`

- [ ] **Step 3: 实现状态机**

`uploader/base_video.py`：导入行改为

```python
from publish.auth import LoginCheckError, classify_login_exception, login_check, warn_qr_login_pending
```

`BaseBrowserUploader` 内新增两个方法（放在 `cookie_gen` 之后、`_browser_session` 之前）：

```python
    async def _ensure_session_login(self, page: Page) -> None:
        """导航到上传页并确认登录态;需要扫码时在同一 page 完成,不另起浏览器。

        导航/判定阶段的不确定异常转 LoginCheckError(不触发扫码);
        扫码阶段超时或中断转 LoginTimeoutError(定论性登录失败,可重试)。
        """
        try:
            await page.goto(self.UPLOAD_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            login_required = await self.is_login_required(page)
        except (LoginCheckError, LoginTimeoutError):
            raise
        except Exception as exc:
            raise classify_login_exception(exc) from None
        if login_required:
            await self._run_session_qr_login(page)
            return
        expected_url = self.UPLOAD_URL.split("?", 1)[0].rstrip("/")
        current_url = (page.url or "").split("?", 1)[0].rstrip("/")
        if current_url != expected_url:
            raise LoginCheckError('page')

    async def _run_session_qr_login(self, page: Page) -> None:
        warn_qr_login_pending(self.PLATFORM_NAME)
        try:
            await page.goto(self.LOGIN_URL, timeout=60000, wait_until="domcontentloaded")
        except Exception as exc:
            raise LoginTimeoutError(f"前往登录页失败: {exc}") from None
        try:
            for _ in range(100):
                if await self.is_login_completed(page):
                    await page.context.storage_state(path=self.account_file)
                    await page.goto(self.UPLOAD_URL, timeout=60000, wait_until="domcontentloaded")
                    return
                await page.wait_for_timeout(3000)
        except Exception as exc:
            raise LoginTimeoutError(f"扫码登录中断: {exc}") from None
        raise LoginTimeoutError(f"{self.PLATFORM_NAME}扫码登录超时(300秒)")
```

`_browser_session` 的 `page = await context.new_page()` 之后改为：

```python
        page = await context.new_page()
        success = False
        try:
            await self._ensure_session_login(page)
            yield page
            success = True
        finally:
            if save_state and (not save_on_success_only or success):
                try:
                    await context.storage_state(path=self.account_file)
                except Exception:
                    pass
            await context.close()
            await browser.close()
```

（原 `try: yield page / success = True` 结构不变，只是 `yield` 前多一行状态机调用；登录异常在 try 内抛出，`finally` 保证浏览器关闭。）

- [ ] **Step 4: 更新既有会话测试的 FakePage**

`tests/test_base_uploader_session.py` 的 `FakePage`（19-22 行）增补两个方法，使既有 7 个会话测试走快路径：

```python
class FakePage:
    def __init__(self):
        self.url = "https://example.com/upload"

    async def goto(self, url, timeout=None, wait_until=None):
        self.url = url

    async def wait_for_timeout(self, ms):
        pass
```

- [ ] **Step 5: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_session_login.py tests/test_base_uploader_session.py tests/test_base_uploader_login.py -q`
Expected: PASS（新增用例全绿；既有会话/登录测试不回归）

- [ ] **Step 6: Commit**

```bash
git add uploader/base_video.py tests/test_session_login.py tests/test_base_uploader_session.py
git commit -m "feat: embed login state machine in browser session"
```

---

### Task 3: `validate_login_and_strategy` 移除 cookie_auth（5 平台）

**Files:**
- Modify: `uploader/douyin_uploader/main.py`（约 365-376 行）
- Modify: `uploader/xiaohongshu_uploader/main.py`（约 469-475 行）
- Modify: `uploader/ks_uploader/main.py`（约 420-426 行）
- Modify: `uploader/baijiahao_uploader/main.py`（约 232-243 行）
- Modify: `uploader/weibo_uploader/main.py`（约 288-305 行）
- Test: `tests/test_session_login.py`、`tests/test_weibo_uploader_base.py`、`tests/test_xiaohongshu_uploader.py`

**Interfaces:**
- Consumes: 无新接口。
- Produces: `validate_login_and_strategy` 只做本地校验（文件存在 + 策略 + 日期），不再开浏览器；运行时有效性由 Task 2 状态机负责。

- [ ] **Step 1: 写失败测试**

`tests/test_session_login.py` 追加：

```python
class ValidateStaysLocalTests(unittest.TestCase):
    """validate_login_and_strategy 不得调用 cookie_auth(那会另开一个浏览器)。"""

    CASES = [
        ("uploader.douyin_uploader.main", "DouYinVideo",
         dict(title="t", file_path="/fake.mp4", tags=[], publish_date=0,
              desc="", publish_strategy="immediate")),
        ("uploader.xiaohongshu_uploader.main", "XiaoHongShuVideo",
         dict(title="t", file_path="/fake.mp4", tags=[], publish_date=0,
              desc="", publish_strategy="immediate")),
        ("uploader.ks_uploader.main", "KSVideo",
         dict(title="t", file_path="/fake.mp4", tags=[], publish_date=0,
              desc="", publish_strategy="immediate")),
        ("uploader.baijiahao_uploader.main", "BaiJiaHaoVideo",
         dict(title="t", file_path="/fake.mp4", tags=[], publish_date=0,
              publish_strategy="immediate")),
        ("uploader.weibo_uploader.main", "WeiboVideo",
         dict(title="t", file_path="/fake.mp4", tags=[], publish_date=0,
              desc="", publish_strategy="immediate")),
    ]

    def test_validate_does_not_call_cookie_auth(self):
        import importlib
        import tempfile
        from pathlib import Path
        for module_path, cls_name, kwargs in self.CASES:
            with self.subTest(platform=module_path):
                module = importlib.import_module(module_path)
                with tempfile.TemporaryDirectory() as tmp:
                    cookie = Path(tmp) / "account.json"
                    cookie.write_text("{}", encoding="utf-8")
                    uploader = getattr(module, cls_name)(account_file=str(cookie), **kwargs)
                    with patch(
                        f"{module_path}.cookie_auth",
                        AsyncMock(side_effect=AssertionError("validate must not open browser")),
                    ):
                        asyncio.run(uploader.validate_login_and_strategy())
```

注意：各平台 `publish_strategy` 常量均为 `"immediate"` / `"scheduled"` 字符串（`PublishStrategy.IMMEDIATE` 等），传 `"immediate"` 可通过校验；若某平台常量值不同，以该平台 main.py 顶部常量为准改为逐字引用。

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_session_login.py -q`
Expected: FAIL — `AssertionError: validate must not open browser`（5 个 subTest 全红）

- [ ] **Step 3: 实现**

五个平台各删除 `validate_login_and_strategy` 中这两行（保留文件存在检查与其后策略/日期校验）：

douyin / xiaohongshu / ks / baijiahao（形如）：

```python
        if not await cookie_auth(self.account_file):
            raise RuntimeError(f"cookie文件已失效，请先完成XX登录: {self.account_file}")
```

weibo：

```python
        if not await cookie_auth(self.account_file):
            raise LoginExpiredError("cookie 已失效，请重新扫码登录")
```

同时把各方法 docstring 中的 "Checks cookie existence/validity" 更新为 "Checks cookie existence + publish_strategy + publish_date（本地校验，登录有效性由上传会话状态机负责）"。weibo 若 `LoginExpiredError` 在该文件再无其他使用处，保留导入（`upload_video_content` 中途失效仍用）。

- [ ] **Step 4: 改写受影响的既有测试**

1. `tests/test_weibo_uploader_base.py`：`WeiboVideoUploadTests.test_upload_maps_validation_cookie_auth_failure_to_safe_retry_result`（约 38-53 行）与 `WeiboNoteUploadTests` 同名测试（约 413-428 行）——场景已不存在，改写为「校验不再开浏览器、上传正常走会话」：

```python
    def test_upload_proceeds_with_existing_cookie_without_browser_precheck(self):
        import asyncio
        from contextlib import asynccontextmanager

        uploader = WeiboVideo(
            title="t", file_path="/fake.mp4", tags=[], publish_date=0,
            account_file="/fake.json", desc="", publish_strategy=PublishStrategy.IMMEDIATE,
        )

        @asynccontextmanager
        async def fake_session(**kwargs):
            yield object()

        with patch("uploader.weibo_uploader.main.os.path.exists", return_value=True), \
             patch("uploader.weibo_uploader.main.cookie_auth", AsyncMock(side_effect=AssertionError("must not open browser"))), \
             patch.object(uploader, "_browser_session", fake_session), \
             patch.object(WeiboVideo, "upload_video_content", AsyncMock(return_value="https://weibo.com/v/1")):
            result = asyncio.run(uploader.upload())

        self.assertTrue(result["success"])
        self.assertEqual("https://weibo.com/v/1", result["result_url"])
```

（WeiboNote 同构：`upload_note_content` 打桩、无 `result_url` 断言。）

2. `tests/test_xiaohongshu_uploader.py` `test_video_validate_upload_args_normalizes_video_and_thumbnail`（约 241-267 行）：将 `patch("uploader.xiaohongshu_uploader.main.cookie_auth", new=AsyncMock(return_value=True))` 改为 `AsyncMock(side_effect=AssertionError("must not open browser"))`，断言不变。

- [ ] **Step 5: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_session_login.py tests/test_weibo_uploader_base.py tests/test_xiaohongshu_uploader.py tests/test_weibo_uploader.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add uploader/douyin_uploader/main.py uploader/xiaohongshu_uploader/main.py uploader/ks_uploader/main.py uploader/baijiahao_uploader/main.py uploader/weibo_uploader/main.py tests/test_session_login.py tests/test_weibo_uploader_base.py tests/test_xiaohongshu_uploader.py
git commit -m "refactor: keep platform login validation local without browser"
```

---

### Task 4: 平台 `upload()` 放行登录异常（6 平台 11 处）

**Files:**
- Modify: `uploader/douyin_uploader/main.py`（video 约 717、note 约 879 的 except 链）
- Modify: `uploader/xiaohongshu_uploader/main.py`（约 786、942）
- Modify: `uploader/ks_uploader/main.py`（约 672、854）
- Modify: `uploader/baijiahao_uploader/main.py`（约 490）
- Modify: `uploader/weibo_uploader/main.py`（约 654、780）
- Modify: `uploader/tencent_uploader/main.py`（约 880、977）
- Test: `tests/test_session_login.py`

**Interfaces:**
- Consumes: Task 1 的 `LoginCheckError` / `LoginTimeoutError`。
- Produces: 各平台 `upload()` 对登录阶段异常向上传播（不再吞成 `PUB-xxx` / 平台失败结果）。

- [ ] **Step 1: 写失败测试**

`tests/test_session_login.py` 追加：

```python
class UploadReRaisesLoginErrorsTests(unittest.TestCase):
    """_browser_session 在 yield 前抛出的登录异常必须穿出 upload()，交给 dispatch 统一转换。"""

    CASES = [
        ("uploader.douyin_uploader.main", "DouYinVideo",
         dict(title="t", file_path="/fake.mp4", tags=[], publish_date=0,
              account_file="/fake.json", desc="", publish_strategy="immediate")),
        ("uploader.douyin_uploader.main", "DouYinNote",
         dict(image_paths=["/fake.jpg"], note="n", tags=[], publish_date=0,
              account_file="/fake.json", title="t", publish_strategy="immediate")),
        ("uploader.xiaohongshu_uploader.main", "XiaoHongShuVideo",
         dict(title="t", file_path="/fake.mp4", tags=[], publish_date=0,
              account_file="/fake.json", desc="", publish_strategy="immediate")),
        ("uploader.xiaohongshu_uploader.main", "XiaoHongShuNote",
         dict(image_paths=["/fake.jpg"], note="n", tags=[], publish_date=0,
              account_file="/fake.json", title="t", desc="", publish_strategy="immediate")),
        ("uploader.ks_uploader.main", "KSVideo",
         dict(title="t", file_path="/fake.mp4", tags=[], publish_date=0,
              account_file="/fake.json", desc="", publish_strategy="immediate")),
        ("uploader.ks_uploader.main", "KSNote",
         dict(image_paths=["/fake.jpg"], note="n", tags=[], publish_date=0,
              account_file="/fake.json", title="t", publish_strategy="immediate")),
        ("uploader.baijiahao_uploader.main", "BaiJiaHaoVideo",
         dict(title="t", file_path="/fake.mp4", tags=[], publish_date=0,
              account_file="/fake.json", publish_strategy="immediate")),
        ("uploader.weibo_uploader.main", "WeiboVideo",
         dict(title="t", file_path="/fake.mp4", tags=[], publish_date=0,
              account_file="/fake.json", desc="", publish_strategy="immediate")),
        ("uploader.weibo_uploader.main", "WeiboNote",
         dict(image_paths=["/fake.jpg"], note="n", tags=[], publish_date=0,
              account_file="/fake.json", title="t", publish_strategy="immediate")),
        ("uploader.tencent_uploader.main", "TencentVideo",
         dict(title="t", file_path="/fake.mp4", tags=[], publish_date=0,
              account_file="/fake.json", desc="", publish_strategy="immediate")),
        ("uploader.tencent_uploader.main", "TencentNote",
         dict(image_paths=["/fake.jpg"], note="n", tags=[], publish_date=0,
              account_file="/fake.json", title="t", publish_strategy="immediate")),
    ]

    def test_login_errors_propagate_out_of_upload(self):
        import importlib
        from contextlib import asynccontextmanager

        for exc_type in (LoginCheckError('network'), LoginTimeoutError("超时")):
            for module_path, cls_name, kwargs in self.CASES:
                with self.subTest(exc=type(exc_type).__name__, platform=cls_name):
                    module = importlib.import_module(module_path)
                    uploader = getattr(module, cls_name)(**kwargs)

                    @asynccontextmanager
                    async def failing_session(**session_kwargs):
                        raise exc_type
                        yield  # pragma: no cover

                    with patch.object(uploader, "validate_upload_args", AsyncMock()), \
                         patch.object(uploader, "_browser_session", failing_session):
                        with self.assertRaises(type(exc_type)):
                            asyncio.run(uploader.upload())
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_session_login.py -q`
Expected: FAIL — 各平台把登录异常吞成结果 dict，`assertRaises` 不触发

- [ ] **Step 3: 实现**

各平台 `upload()` 的 except 链**最前面**插入一行放行（在 `except DouyinPublishRestrictedError` / `except XhsPublishRestrictedError` / `except _TencentPreMediaLoginExpired` / `except _WeiboPreMediaLoginExpired` / 通用 `except Exception` 之前）：

```python
        except (LoginCheckError, LoginTimeoutError):
            raise
```

weibo 特殊：现有 `except LoginCheckError as exc: result.update(exc.to_result())`（video 约 654 行、note 约 780 行）整段**替换**为上面的放行两行（转换职责上移到 dispatch，Task 5 落地）。

导入：
- douyin / baijiahao / weibo（已 `from publish.auth import LoginCheckError, login_check`）→ 改为 `from publish.auth import LoginCheckError, LoginTimeoutError, login_check`
- xiaohongshu / ks / tencent（无 auth 导入）→ 新增 `from publish.auth import LoginCheckError, LoginTimeoutError`

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_session_login.py tests/test_douyin_uploader_base.py tests/test_ks_uploader_base.py tests/test_baijiahao_uploader_base.py tests/test_weibo_uploader_base.py tests/test_tencent_uploader_base.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add uploader/douyin_uploader/main.py uploader/xiaohongshu_uploader/main.py uploader/ks_uploader/main.py uploader/baijiahao_uploader/main.py uploader/weibo_uploader/main.py uploader/tencent_uploader/main.py tests/test_session_login.py
git commit -m "feat: re-raise session login errors from platform uploads"
```

---

### Task 5: dispatch — 集中转换与共享提醒

**Files:**
- Modify: `publish/dispatch.py`（导入区、`ensure_login` 约 38-46、8 个 `publish_to_*` wrapper 的 except 链、`publish_to_platform` 约 334-339）
- Test: `tests/test_publish_dispatch.py`

**Interfaces:**
- Consumes: Task 1 的 `LoginTimeoutError` / `warn_qr_login_pending`、`LoginCheckError.to_result()`。
- Produces: `publish_to_platform(platform, params)` 对两类登录异常返回结果 dict（`LoginCheckError` → `to_result()`；`LoginTimeoutError` → AUTH-001 `safe_to_retry=True`）；`ensure_login` 使用共享提醒 helper。

- [ ] **Step 1: 写失败测试**

`tests/test_publish_dispatch.py` 追加（沿用该文件现有 import 风格）：

```python
class PublishToPlatformLoginConversionTests(unittest.TestCase):
    def test_converts_login_check_error(self):
        import asyncio
        from publish.auth import LoginCheckError

        async def handler(params):
            raise LoginCheckError('network')

        with patch.dict("publish.dispatch._PUBLISH_DISPATCH", {"fake": handler}):
            result = asyncio.run(publish_to_platform("fake", {}))
        self.assertFalse(result["success"])
        self.assertEqual("NET-001", result["error_code"])
        self.assertFalse(result["safe_to_retry"])

    def test_converts_login_timeout_error_to_auth_result(self):
        import asyncio
        from publish.auth import LoginTimeoutError

        async def handler(params):
            raise LoginTimeoutError("扫码登录超时")

        with patch.dict("publish.dispatch._PUBLISH_DISPATCH", {"fake": handler}):
            result = asyncio.run(publish_to_platform("fake", {}))
        self.assertFalse(result["success"])
        self.assertEqual("AUTH-001", result["error_code"])
        self.assertTrue(result["safe_to_retry"])

    def test_ensure_login_warns_via_shared_helper(self):
        import asyncio

        # dispatch 按名导入 helper,必须 patch dispatch 命名空间内的引用
        with patch("publish.dispatch.warn_qr_login_pending") as warn:
            with patch.dict(
                "publish.dispatch._PLATFORM_LOGIN",
                {"fake_plat": ("fake_mod", "cookie_auth", "fake_setup")},
            ):
                with patch("os.path.exists", return_value=False), \
                     patch("importlib.import_module") as import_module:
                    fake_setup = AsyncMock(return_value=True)
                    import_module.return_value.fake_setup = fake_setup
                    ok = asyncio.run(dispatch.ensure_login("fake_plat", "cookies/x.json"))
        self.assertTrue(ok)
        warn.assert_called_once_with("fake_plat")
```

（若该文件尚未 import `publish_to_platform` / `dispatch` / `AsyncMock` / `patch`，按现有头部补齐。）

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_publish_dispatch.py -q`
Expected: FAIL — `publish_to_platform` 不捕获登录异常（异常直接抛出）

- [ ] **Step 3: 实现**

`publish/dispatch.py`：

1. 导入改为：`from publish.auth import LoginCheckError, LoginTimeoutError, warn_qr_login_pending`
2. `ensure_login` 中原内联 print 块（约 38-44 行）替换为 `warn_qr_login_pending(platform)`（原注释两行保留）。
3. `publish_to_platform` 改为：

```python
async def publish_to_platform(platform: str, params: dict) -> dict:
    """发布到指定平台"""
    handler = _PUBLISH_DISPATCH.get(platform)
    if handler is not None:
        try:
            return await handler(params)
        except LoginCheckError as exc:
            return exc.to_result()
        except LoginTimeoutError as exc:
            return exc.to_result()
    return {"success": False, "message": f"未知平台: {platform}"}
```

4. 删除 8 个 `publish_to_*` wrapper 中各自的这两行（douyin / xiaohongshu / kuaishou / tencent / baijiahao / bilibili / weibo / tk 各一处，形如）：

```python
    except LoginCheckError as exc:
        return exc.to_result()
```

（wrapper 内通用 `except Exception` 分支保留不动。）

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_publish_dispatch.py tests/test_publish_engine.py -q`
Expected: PASS（`EnsureLoginWarningTests` 的"工具超时"文案断言仍通过）

- [ ] **Step 5: Commit**

```bash
git add publish/dispatch.py tests/test_publish_dispatch.py
git commit -m "refactor: centralize login error conversion in dispatch"
```

---

### Task 6: orchestrator — 预检收窄与重试简化

**Files:**
- Modify: `publish/dispatch.py`（`platform_requires_account_login` 约 54-55 行）
- Modify: `publish/orchestrator.py`（预检循环约 148-159、重试路径约 161-181）
- Test: `tests/test_publish_dispatch.py`、`tests/test_publish_engine.py`、`tests/test_publish_resume_cli.py`

**Interfaces:**
- Consumes: Task 5 的 `publish_to_platform` 转换。
- Produces: `platform_requires_account_login(platform) -> bool` 仅对 `"bilibili"` 为 True；浏览器平台发布直接进入 `publish_to_platform`；`_is_safe_login_expiry` 命中时重调一次 `publish_to_platform`，不再调 `ensure_account_login(force=True)`。

- [ ] **Step 1: 写失败测试**

1. `tests/test_publish_dispatch.py` 的 `test_platform_requires_account_login`（约 24-29 行）改写为：

```python
    def test_platform_requires_account_login(self):
        self.assertTrue(platform_requires_account_login("bilibili"))
        self.assertFalse(platform_requires_account_login("douyin"))
        self.assertFalse(platform_requires_account_login("weibo"))
        self.assertFalse(platform_requires_account_login("tk"))
        self.assertFalse(platform_requires_account_login("unknown_platform"))
```

2. `tests/test_publish_engine.py`：

   - `test_publish_one_item_triggers_login_before_publish`（约 515-534 行）改名 `test_publish_one_item_does_not_precheck_browser_platform_login`，断言反转：

```python
        ensure_login.assert_not_awaited()
        publish.assert_awaited_once_with("douyin", unittest.mock.ANY)
```

   - 新增 bilibili 预检保留测试：

```python
    def test_publish_one_item_prechecks_bilibili_login(self):
        params = {
            "enabled_platforms": ["bilibili"],
            "platforms": {"bilibili_account": "cookies/biliup.json"},
            "content_type": "video",
            "video_file": "videos/demo.mp4",
            "title": "标题",
            "desc": "描述",
            "tags": [],
            "publish_strategy": "immediate",
            "publish_time": None,
            "convert_to_video": False,
        }
        with patch("publish.orchestrator.ensure_account_login", new=AsyncMock(return_value=True)) as ensure_login, \
             patch("publish.orchestrator.publish_to_platform", new=AsyncMock(return_value={"success": True, "message": "ok"})) as publish:
            results = publish_all.run_async_for_test(publish_all.publish_one_item(params))
        ensure_login.assert_awaited_once_with("bilibili", "cookies/biliup.json")
        publish.assert_awaited_once()
```

   - `test_safe_login_expiry_forces_one_login_and_republishes_successfully`（约 424-445 行）改名 `test_safe_login_expiry_republishes_once_without_forced_login`，去掉 `ensure_login` 断言、保留双次发布：

```python
        with patch("publish.orchestrator.ensure_account_login", new=AsyncMock()) as ensure_login, \
             patch("publish.orchestrator.publish_to_platform", new=AsyncMock(side_effect=[first_result, final_result])) as publish:
            results = publish_all.run_async_for_test(publish_all.publish_one_item(params))
        ensure_login.assert_not_awaited()
        self.assertEqual(publish.await_count, 2)
        self.assertEqual(publish.await_args_list[0].args, publish.await_args_list[1].args)
        self.assertTrue(results["weibo"]["success"])
```

   - `test_forced_login_failure_replaces_expiry_result_with_auth_failure`（约 447-467 行）改名 `test_republish_failure_result_is_kept`：

```python
        with patch("publish.orchestrator.ensure_account_login", new=AsyncMock()) as ensure_login, \
             patch("publish.orchestrator.publish_to_platform", new=AsyncMock(side_effect=[expiry, {"success": False, "message": "重试后仍失败"}])) as publish, \
             contextlib.redirect_stdout(io.StringIO()):
            results = publish_all.run_async_for_test(publish_all.publish_one_item(params))
        ensure_login.assert_not_awaited()
        self.assertEqual(publish.await_count, 2)
        self.assertEqual("重试后仍失败", results["weibo"]["message"])
```

   - `test_second_safe_login_expiry_does_not_trigger_a_third_publish_or_login`（约 469-485 行）：删除 `ensure_login` 断言，改加 `ensure_login.assert_not_awaited()`，`publish.await_count == 2` 保留。
   - `test_non_retryable_login_expiry_does_not_force_login`（约 487-503 行）：`ensure_login.assert_awaited_once_with(...)` 改为 `ensure_login.assert_not_awaited()`，`publish.assert_awaited_once()` 保留。

3. `tests/test_publish_resume_cli.py`：

   - `test_resume_reuses_success_and_retries_only_safe_failure`（约 51 行）：`assert login.await_count == 1` 改为 `assert login.await_count == 0`。
   - `test_failed_login_can_be_resumed_without_prior_submission`（约 74-80 行）改写为发布侧登录失败：

```python
def test_failed_login_can_be_resumed_without_prior_submission(tmp_path, isolated):
    login, publish = isolated
    auth_failure = {'success': False, 'message': '登录超时', 'error_code': 'AUTH-001',
                    'account_issue': True, 'issue_type': 'login_timeout', 'safe_to_retry': True}
    publish.side_effect = [auth_failure, {'success': True, 'message': 'ok'}]
    first = run(inputs(tmp_path))
    assert first['exit_code'] == 1
    assert run(['--resume', first['run_id']])['exit_code'] == 0
    assert publish.await_count == 2
```

（`isolated` fixture 的 `login` mock 保留但不再被浏览器平台路径调用。）

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_publish_dispatch.py tests/test_publish_engine.py tests/test_publish_resume_cli.py -q`
Expected: FAIL（预检收窄与重试简化尚未实现）

- [ ] **Step 3: 实现**

1. `publish/dispatch.py` 的 `platform_requires_account_login`（约 54-55 行）替换为：

```python
# 仅 bilibili(CLI 平台,无浏览器)保留发布前独立登录预检;
# 浏览器平台的登录由上传会话内的状态机完成
_PRECHECK_LOGIN_PLATFORMS = {"bilibili"}


def platform_requires_account_login(platform: str) -> bool:
    return platform in _PRECHECK_LOGIN_PLATFORMS
```

2. `publish/orchestrator.py` 重试路径（约 161-181 行）替换为：

```python
        result = await publish_to_platform(platform, platform_params)
        retryable = result.get('safe_to_retry') is True
        if _is_safe_login_expiry(result):
            # 上传会话已并入登录:重试的新会话自行完成重新登录
            result = await publish_to_platform(platform, platform_params)
            retryable = result.get('safe_to_retry') is True

        save_result(platform, result, retryable=retryable)
        if result.get("success"):
            print("  ✅ 成功")
        else:
            print(f"  ❌ 失败: {result['message']}")
```

（删除 `auth_failure_reported` 变量及其 `continue` 分支；预检循环约 148-159 行结构不动——由收窄后的 `platform_requires_account_login` 自然只对 bilibili 生效，其中 `print_error` 失败分支的 `continue` 保留。）

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_publish_dispatch.py tests/test_publish_engine.py tests/test_publish_resume_cli.py tests/test_publish_validation.py tests/test_license_e2e.py -q`
Expected: PASS（`test_publish_validation.py` 的 autouse `ensure_account_login` mock 变为未使用但不报错）

- [ ] **Step 5: Commit**

```bash
git add publish/dispatch.py publish/orchestrator.py tests/test_publish_dispatch.py tests/test_publish_engine.py tests/test_publish_resume_cli.py
git commit -m "feat: skip browser precheck and republish through session login"
```

---

### Task 7: 文档、0.8.6 版本与全量回归

**Files:**
- Modify: `pyproject.toml`（version）
- Modify: `skills/opub-cli/SKILL.md`（frontmatter version + 措辞）
- Modify: `tests/test_package_build.py`（三处版本断言）
- Modify: `uv.lock`（`uv lock` 生成）
- Modify: `docs/KNOWN_ISSUES.md`（BROWSER-01 标记已实现）
- Modify: `docs/CLI.md`（如登录流程措辞涉及预检，grep 后调整）

**Interfaces:**
- Consumes: Task 1-6 全部落地。
- Produces: 0.8.6 版本一致性（4 处）；文档与实现一致。

- [ ] **Step 1: 版本 bump**

`pyproject.toml` `version = "0.8.6"`；`skills/opub-cli/SKILL.md` frontmatter `version: "0.8.6"`；`tests/test_package_build.py` 三处断言 `0.8.5` → `0.8.6`（`test_release_version_is_consistent` 内 pyproject/skill/lock 三行）。

- [ ] **Step 2: uv.lock 同步**

Run: `uv lock`
Expected: uv.lock 中 `name = "opub"` 的 `version = "0.8.6"`

- [ ] **Step 3: 文档更新**

1. `docs/KNOWN_ISSUES.md` 浏览器会话复用一节：BROWSER-01 状态改为「已实现（0.8.6）：登录判定/扫码/上传/结果确认并入同一会话，素材结束统一关闭；bilibili 保持 biliup 子进程与预检」。后续验证清单保留，供用户 e2e 核验。
2. `skills/opub-cli/SKILL.md`：无需改对外行为描述（"启用平台若无账号文件,发布时会自动弹出浏览器扫码登录,登录完成后继续发布"在新行为下仍准确）；仅确认无"登录预检"单独措辞。
3. `docs/CLI.md`：`grep -n "登录\|login" docs/CLI.md`，如有描述"发布前先校验登录"的段落，改为"登录判定在上传会话内完成"。

- [ ] **Step 4: 版本一致性测试**

Run: `.venv/bin/python -m pytest tests/test_package_build.py::PackageBuildTest::test_release_version_is_consistent -q`
Expected: PASS

- [ ] **Step 5: 全量回归**

Run: `.venv/bin/python -m pytest tests license_server/tests -q`
Expected: 全部通过（此前基线 759 通过 + 本计划新增用例）

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml skills/opub-cli/SKILL.md tests/test_package_build.py uv.lock docs/KNOWN_ISSUES.md docs/CLI.md
git commit -m "chore: release 0.8.6 with single-browser publish sessions"
```

---

## 验收核对（对 spec「验证」节）

- 快路径不进登录流程、不打印扫码提醒：`SessionLoginMachineTests.test_fast_path_skips_login_flow`
- 扫码路径完整（提醒 → 轮询 → 落盘 → 回导航）：`test_qr_flow_warns_saves_state_and_returns_to_upload_page`
- 扫码超时抛 `LoginTimeoutError`、dispatch 转 AUTH-001：`test_qr_timeout_raises_login_timeout` + `PublishToPlatformLoginConversionTests.test_converts_login_timeout_error_to_auth_result`
- goto 网络异常抛 `LoginCheckError` 且不 `goto(LOGIN_URL)`（契约锁定）：`test_navigation_network_error_is_classified_and_never_enters_qr`
- 非登录重定向报 PAGE-001 不扫码：`test_non_login_redirect_raises_page_error`
- 扫码成功后上传失败 cookie 仍保留：`BrowserSessionIntegrationTests.test_qr_save_survives_upload_failure`
- 退出保存规则不变：`tests/test_base_uploader_session.py` 既有 7 测（不改断言，仅 FakePage 增补）
- 浏览器平台不再调 `ensure_account_login`、bilibili 仍调：Task 6 Step 1 两组测试
- 重试路径重调 publish 而非 force 登录：`test_safe_login_expiry_republishes_once_without_forced_login`
- 平台层放行不被吞成 PUB-xxx：`UploadReRaisesLoginErrorsTests`（11 类 × 2 异常）
- 全量回归无真实账号或发布：Task 7 Step 5

真实平台 e2e（weibo 快路径 + 扫码路径，tencent 扫码后直传）由用户在合并后执行，对应 KNOWN_ISSUES「后续实现前验证」清单。
