# Uploader 公共基类抽取 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从 8 个平台 uploader 抽取三层公共基类(`BasePlatformUploader` / `BaseBrowserUploader` / `BaseCliUploader`),消除 ~400 行重复的 launch/context/cookie_auth/cookie_gen/setup 代码,统一返回契约为 `PlatformResultExtras`,迁移 tk 到 chromium+patchright 并接入 dispatch。

**Architecture:** 务实分层 -- 抽象基类拥有 shared utilities 和 template method;浏览器子类提供 `_browser_session` context manager 和 QR 登录模板;平台子类只实现 hook(`UPLOAD_URL` / `LOGIN_MARKERS` / `extract_qrcode_src` / `is_login_completed`)和 `upload()`。模块级 `cookie_auth` / `<platform>_setup` 保留为薄 wrapper 委托 classmethod,dispatch.py 注册表不动。向后兼容靠 `BaseVideoUploader = BasePlatformUploader` 别名(Task 9 删)和 `main()` 别名(Task 9 删)。

**Tech Stack:** Python 3.9+ / asyncio / patchright / playwright / unittest.mock / pytest / contextlib.asynccontextmanager

## Global Constraints

- **禁止截屏定位 UI**:不从 `page.screenshot` 截图发给模型 API 定位 UI;用 DOM/页面源码(`page.content()` / `page.evaluate` / selector)
- **禁止非文本文件调用大模型 API**:LLM API 输入只限纯文本
- **Python 3.9 兼容**:TypedDict 用继承模式(`class X(TypedDict)` + `class XExtras(X, total=False)`),不用 `Required[]`/`NotRequired[]`(3.11+ 才有);`X | None` 用 `Optional[X]` 或 `from __future__ import annotations`
- **patchright**:所有浏览器导入用 `from patchright.async_api import async_playwright`(不是 `playwright`)。tk 迁移必须从 `playwright` 切到 `patchright`
- **`LOCAL_CHROME_HEADLESS` / `LOCAL_CHROME_PATH`**:从 `conf` 导入,所有浏览器启动用这两个配置
- **`set_init_script`**:`utils.base_social_media.set_init_script`,每个 `browser.new_context()` 后必调(防爬)
- **`resolve_path`**:`publish.content.resolve_path`,dispatch 层用此函数解析路径(不用 `myUtils` 的 `get_absolute_path` 或平台内的 `_resolve_account_file`)
- **`truncate_title`**:`publish.content.truncate_title`,dispatch 调用前先截断
- **`write_video_link`**:`utils.excel_writer.write_video_link`,baijiahao / weibo 发布成功后调,参数为 `result["result_url"]`
- **5 参数 setup 签名**:`(account_file, handle, return_detail, qrcode_callback, headless)`,所有平台统一
- **`PublishStrategy` enum**:`str` 子类,字符串字面量 `"immediate"`/`"scheduled"` 仍可比,向后兼容
- **`BaseVideoUploader` 别名**:Task 1-8 保留 `BaseVideoUploader = BasePlatformUploader`,Task 9 删除
- **`main()` / `douyin_upload_note()` 别名**:各平台旧入口方法名改为 `upload()` 的别名 wrapper,Task 9 删
- **`validate_base_args` 命名分离**:Task 1 在 `BasePlatformUploader` 加 staticmethod `validate_base_args(params) -> Optional[PlatformResultExtras]`(dispatch 调,检查文件存在);Tasks 2-6 把各 `*BaseUploader` 上的实例方法 `validate_base_args(self)` 重命名为 `validate_login_and_strategy(self)`(检查 cookie + publish_strategy),避免子类实例方法遮蔽基类 staticmethod。同时更新 `*Video.validate_upload_args()` / `*Note.validate_upload_args()` 内部调用从 `self.validate_base_args()` 改为 `self.validate_login_and_strategy()`
- **`test_publish_engine.py` 回归网**:每个 task 结束必须全绿(16 用例)
- **myUtils/ 不碰**:sub-project C 范围,本 plan 不动 `myUtils/`

---

## File Structure

| 文件 | 职责 | 状态 |
|---|---|---|
| `uploader/base_video.py` | 三层基类 + `PublishStrategy` enum + `PlatformResultExtras` TypedDict + `AccountRestrictedError` + `BaseVideoUploader` 别名 | 升级 |
| `uploader/weibo_uploader/main.py` | `WeiboBaseUploader` 缩成 hook 层,`WeiboVideo`/`WeiboNote` 改 `upload()` | 修改 |
| `uploader/xiaohongshu_uploader/main.py` | `XiaoHongShuBaseUploader` 缩,`XiaoHongShuVideo`/`XiaoHongShuNote` 改 `upload()` | 修改 |
| `uploader/ks_uploader/main.py` | `KSBaseUploader` 缩,`KSVideo`/`KSNote` 改 `upload()` | 修改 |
| `uploader/tencent_uploader/main.py` | `TencentBaseUploader` 缩,`TencentVideo` 改 `upload()` | 修改 |
| `uploader/douyin_uploader/main.py` | `DouYinBaseUploader` 缩,`DouYinVideo`/`DouYinNote` 改 `upload()` | 修改 |
| `uploader/baijiahao_uploader/main.py` | `BaiJiaHaoVideo` 改基类,保留 `@async_retry` + `ai2video` | 修改 |
| `uploader/bilibili_uploader/main.py` | 包成 `BilibiliUploader(BaseCliUploader)` | 修改 |
| `uploader/tk_uploader/main.py` | firefox->chromium+patchright,改基类,override `cookie_gen` | 改写 |
| `publish/dispatch.py` | 8 个 `publish_to_*` 简化 + 加 `publish_to_tk` + 删 "tk 暂未实现" 分支 | 修改 |
| `publish/constants.py` | 加 `"tk": 2200` 到 `TITLE_LIMITS` | 修改 |
| `tests/test_base_uploader.py` | `BasePlatformUploader` 纯逻辑测试 | 新建 |
| `tests/test_base_uploader_login.py` | `BaseBrowserUploader` 模板方法测试(用 `FakeUploader`) | 新建 |
| `tests/test_base_uploader_session.py` | `_browser_session` context manager 测试 | 新建 |
| `tests/test_tk_migration.py` | tk 迁移验证 | 新建 |
| `tests/test_publish_dispatch.py` | 加 tk 到 dispatch 表覆盖断言 | 修改 |

---

## Task 1: 升级 `uploader/base_video.py` 基类基金会

**Files:**
- Modify: `uploader/base_video.py`(升级,保留现有 `validate_video_file`/`validate_image_file`/`validate_publish_date` 不动)
- Create: `tests/test_base_uploader.py`
- Create: `tests/test_base_uploader_login.py`
- Create: `tests/test_base_uploader_session.py`

**Interfaces:**
- Consumes: `conf.LOCAL_CHROME_HEADLESS` / `conf.LOCAL_CHROME_PATH`, `utils.base_social_media.set_init_script`, `utils.log` 各平台 logger, `patchright.async_api.async_playwright` / `Page` / `Playwright`
- Produces: 
  - `BasePlatformUploader`(abstract base,validation + enum + TypedDict + exception)
  - `BaseBrowserUploader(BasePlatformUploader)`(template login flow + `_browser_session`)
  - `BaseCliUploader(BasePlatformUploader)`(abstract CLI base)
  - `PublishStrategy(str, Enum)` with `IMMEDIATE = "immediate"` / `SCHEDULED = "scheduled"`
  - `PlatformResult(TypedDict)` with `success: bool` / `message: str`
  - `PlatformResultExtras(PlatformResult, total=False)` with `result_url: str` / `result_id: str` / `account_issue: bool` / `issue_type: str`
  - `AccountRestrictedError(Exception)`
  - `BaseVideoUploader = BasePlatformUploader`(别名,Task 9 删)
- Hook contract (subclasses must define): `PLATFORM_NAME: str`, `UPLOAD_URL: str`, `LOGIN_URL: str`, `LOGIN_MARKERS: list[str]`, `PUBLISH_MARKERS: list[str]`, `extract_qrcode_src(page) -> str | None`, `is_login_completed(page) -> bool`

- [ ] **Step 1: Write failing test for `PublishStrategy` enum and `PlatformResultExtras` TypedDict**

Create `tests/test_base_uploader.py`:

```python
from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from uploader.base_video import (
    AccountRestrictedError,
    BaseBrowserUploader,
    BaseCliUploader,
    BasePlatformUploader,
    BaseVideoUploader,
    PlatformResult,
    PlatformResultExtras,
    PublishStrategy,
)


class PublishStrategyTests(unittest.TestCase):
    def test_immediate_value(self):
        self.assertEqual(PublishStrategy.IMMEDIATE.value, "immediate")

    def test_scheduled_value(self):
        self.assertEqual(PublishStrategy.SCHEDULED.value, "scheduled")

    def test_str_subclass_for_backward_compat(self):
        self.assertEqual(PublishStrategy.IMMEDIATE, "immediate")
        self.assertEqual(PublishStrategy.SCHEDULED, "scheduled")


class PlatformResultTypedDictTests(unittest.TestCase):
    def test_minimal_result(self):
        r: PlatformResult = {"success": True, "message": "ok"}
        self.assertTrue(r["success"])

    def test_extras_with_all_fields(self):
        r: PlatformResultExtras = {
            "success": False,
            "message": "limited",
            "result_url": "https://example.com/v/1",
            "result_id": "abc123",
            "account_issue": True,
            "issue_type": "publish_restricted",
        }
        self.assertEqual(r["result_url"], "https://example.com/v/1")
        self.assertEqual(r["issue_type"], "publish_restricted")


class AccountRestrictedErrorTests(unittest.TestCase):
    def test_is_exception_subclass(self):
        self.assertTrue(issubclass(AccountRestrictedError, Exception))

    def test_carries_message(self):
        exc = AccountRestrictedError("风控限制")
        self.assertEqual(str(exc), "风控限制")


class BaseVideoUploaderAliasTests(unittest.TestCase):
    def test_alias_points_to_base_platform_uploader(self):
        self.assertIs(BaseVideoUploader, BasePlatformUploader)


class ValidateBaseArgsTests(unittest.TestCase):
    def test_video_file_missing_returns_error(self):
        params = {"content_type": "video", "video_file": "/nonexistent/x.mp4"}
        result = BasePlatformUploader.validate_base_args(params)
        self.assertIsNotNone(result)
        self.assertFalse(result["success"])
        self.assertIn("视频文件不存在", result["message"])

    def test_video_file_none_returns_error(self):
        params = {"content_type": "video", "video_file": ""}
        result = BasePlatformUploader.validate_base_args(params)
        self.assertIsNotNone(result)
        self.assertIn("视频文件不存在", result["message"])

    def test_note_without_images_returns_error(self):
        params = {"content_type": "note", "images": []}
        result = BasePlatformUploader.validate_base_args(params)
        self.assertIsNotNone(result)
        self.assertIn("图文模式需要提供图片", result["message"])

    def test_note_with_missing_image_file_returns_error(self):
        params = {"content_type": "note", "images": ["/nonexistent/a.jpg"]}
        result = BasePlatformUploader.validate_base_args(params)
        self.assertIsNotNone(result)
        self.assertIn("图片文件不存在", result["message"])

    def test_valid_video_params_returns_none(self):
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"fake")
            path = f.name
        try:
            params = {"content_type": "video", "video_file": path}
            self.assertIsNone(BasePlatformUploader.validate_base_args(params))
        finally:
            os.unlink(path)

    def test_valid_note_params_returns_none(self):
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"fake")
            path = f.name
        try:
            params = {"content_type": "note", "images": [path]}
            self.assertIsNone(BasePlatformUploader.validate_base_args(params))
        finally:
            os.unlink(path)


class ValidateVideoFileTests(unittest.TestCase):
    def test_existing_validation_preserved(self):
        # inherited from old BaseVideoUploader, must still work via BasePlatformUploader
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"fake")
            path = f.name
        try:
            resolved = BasePlatformUploader.validate_video_file(path)
            self.assertEqual(resolved.suffix, ".mp4")
        finally:
            os.unlink(path)

    def test_unsupported_extension_raises(self):
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"fake")
            path = f.name
        try:
            with self.assertRaises(ValueError):
                BasePlatformUploader.validate_video_file(path)
        finally:
            os.unlink(path)


class ValidatePublishDateTests(unittest.TestCase):
    def test_zero_returns_zero(self):
        self.assertEqual(BasePlatformUploader.validate_publish_date(0), 0)

    def test_none_returns_zero(self):
        self.assertEqual(BasePlatformUploader.validate_publish_date(None), 0)

    def test_past_datetime_raises(self):
        past = datetime(2020, 1, 1)
        with self.assertRaises(ValueError):
            BasePlatformUploader.validate_publish_date(past)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_base_uploader.py -v`
Expected: FAIL with `ImportError: cannot import name 'AccountRestrictedError' ...` (classes not yet defined)

- [ ] **Step 3: Write minimal implementation in `uploader/base_video.py`**

Replace the entire contents of `uploader/base_video.py` with:

```python
from __future__ import annotations

import inspect
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional, TypedDict

from patchright.async_api import Page, Playwright, async_playwright

from conf import BASE_DIR, LOCAL_CHROME_HEADLESS, LOCAL_CHROME_PATH
from utils.base_social_media import set_init_script


class PublishStrategy(str, Enum):
    IMMEDIATE = "immediate"
    SCHEDULED = "scheduled"


class PlatformResult(TypedDict):
    success: bool
    message: str


class PlatformResultExtras(PlatformResult, total=False):
    result_url: str
    result_id: str
    account_issue: bool
    issue_type: str


class AccountRestrictedError(Exception):
    """平台限制发布(风控/限流/封禁)。upload() 捕获后映射为 account_issue=True。"""


class BasePlatformUploader:
    SUPPORTED_VIDEO_EXTENSIONS = {
        ".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm", ".flv", ".wmv",
    }
    SUPPORTED_IMAGE_EXTENSIONS = {
        ".jpg", ".jpeg", ".png", ".webp", ".bmp",
    }
    MIN_SCHEDULE_LEAD_TIME = timedelta(hours=2)

    @classmethod
    def validate_video_file(cls, file_path: str | Path) -> Path:
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"视频文件不存在: {path}")
        if not path.is_file():
            raise ValueError(f"视频路径不是文件: {path}")
        if path.suffix.lower() not in cls.SUPPORTED_VIDEO_EXTENSIONS:
            raise ValueError(
                f"不支持的视频格式: {path.suffix}，当前支持: {', '.join(sorted(cls.SUPPORTED_VIDEO_EXTENSIONS))}"
            )
        return path

    @classmethod
    def validate_image_file(cls, file_path: str | Path) -> Path:
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"图片文件不存在: {path}")
        if not path.is_file():
            raise ValueError(f"图片路径不是文件: {path}")
        if path.suffix.lower() not in cls.SUPPORTED_IMAGE_EXTENSIONS:
            raise ValueError(
                f"不支持的图片格式: {path.suffix}，当前支持: {', '.join(sorted(cls.SUPPORTED_IMAGE_EXTENSIONS))}"
            )
        return path

    @classmethod
    def validate_publish_date(cls, publish_date: datetime | int | None) -> datetime | int:
        if publish_date in (None, 0):
            return 0
        if not isinstance(publish_date, datetime):
            raise TypeError("publish_date 必须是 datetime 类型或 0")
        now = datetime.now(tz=publish_date.tzinfo) if publish_date.tzinfo else datetime.now()
        if publish_date <= now:
            raise ValueError("定时发布时间必须晚于当前时间")
        min_publish_time = now + cls.MIN_SCHEDULE_LEAD_TIME
        if publish_date <= min_publish_time:
            raise ValueError("定时发布时间必须大于当前时间 2 小时")
        return publish_date

    @staticmethod
    def validate_base_args(params: dict) -> Optional[PlatformResultExtras]:
        """Returns error dict if invalid, None if OK.
        Expects paths already resolved by dispatch (resolve_path applied).
        Called by dispatch before construction."""
        if params.get("content_type") == "video":
            video_file = params.get("video_file")
            if not video_file or not os.path.exists(video_file):
                return {"success": False, "message": f"视频文件不存在: {video_file}"}
        elif params.get("content_type") == "note":
            images = params.get("images") or []
            if not images:
                return {"success": False, "message": "图文模式需要提供图片"}
            for img_path in images:
                if not os.path.exists(img_path):
                    return {"success": False, "message": f"图片文件不存在: {img_path}"}
        return None


# Backward-compat alias (Task 9 deletes this)
BaseVideoUploader = BasePlatformUploader


def _msg(emoji: str, text: str) -> str:
    return f"{emoji} {text}"


def _build_launch_kwargs(headless: bool) -> dict:
    launch_kwargs: dict = {"headless": headless}
    if LOCAL_CHROME_PATH:
        launch_kwargs["executable_path"] = LOCAL_CHROME_PATH
    else:
        launch_kwargs["channel"] = "chrome"
    return launch_kwargs


async def _emit_qrcode_callback(qrcode_callback, payload: dict) -> None:
    if not qrcode_callback:
        return
    callback_result = qrcode_callback(payload)
    if inspect.isawaitable(callback_result):
        await callback_result


def _build_login_result(
    success: bool,
    status: str,
    message: str,
    account_file: str,
    qrcode: dict | None = None,
    current_url: str = "",
) -> dict:
    return {
        "success": success,
        "status": status,
        "message": message,
        "account_file": str(account_file),
        "qrcode": qrcode,
        "current_url": current_url,
    }


def _get_qrcode_utils() -> dict:
    from utils.login_qrcode import (
        build_login_qrcode_path,
        decode_qrcode_from_path,
        print_terminal_qrcode,
        remove_qrcode_file,
        save_data_url_image,
    )
    return {
        "build_login_qrcode_path": build_login_qrcode_path,
        "decode_qrcode_from_path": decode_qrcode_from_path,
        "print_terminal_qrcode": print_terminal_qrcode,
        "remove_qrcode_file": remove_qrcode_file,
        "save_data_url_image": save_data_url_image,
    }


class BaseBrowserUploader(BasePlatformUploader):
    """浏览器平台基类:提供 cookie_auth/setup/cookie_gen 模板方法和 _browser_session context manager。
    子类必须定义:PLATFORM_NAME / UPLOAD_URL / LOGIN_URL / LOGIN_MARKERS / PUBLISH_MARKERS
    子类可 override:extract_qrcode_src / is_login_completed / cookie_gen / _launch_browser"""

    PLATFORM_NAME: str = ""
    UPLOAD_URL: str = ""
    LOGIN_URL: str = ""
    LOGIN_MARKERS: list = []
    PUBLISH_MARKERS: list = []

    @classmethod
    async def _launch_browser(cls, playwright: Playwright, headless: bool):
        return await playwright.chromium.launch(**_build_launch_kwargs(headless))

    @classmethod
    async def _init_context(cls, browser, account_file: Optional[str]):
        if account_file and os.path.exists(account_file):
            context = await browser.new_context(storage_state=account_file)
        else:
            context = await browser.new_context()
        return await set_init_script(context)

    @classmethod
    async def is_login_completed(cls, page: Page) -> bool:
        """Override hook:轮询登录是否完成。默认检查 URL 不在 LOGIN_MARKERS。"""
        current_url = (page.url or "").lower()
        if any(marker.lower() in current_url for marker in cls.LOGIN_MARKERS):
            return False
        return True

    @classmethod
    async def extract_qrcode_src(cls, page: Page) -> Optional[str]:
        """Override hook:从登录页提取 QR 图片 src。默认返回 None(子类实现)。"""
        return None

    @classmethod
    async def cookie_auth(cls, account_file: str) -> bool:
        """Navigate to upload page, check if still logged in."""
        if not os.path.exists(account_file):
            return False
        async with async_playwright() as playwright:
            browser = await cls._launch_browser(playwright, headless=True)
            try:
                context = await cls._init_context(browser, account_file)
                page = await context.new_page()
                await page.goto(cls.UPLOAD_URL)
                await page.wait_for_timeout(3000)
                current_url = (page.url or "").lower()
                if any(marker.lower() in current_url for marker in cls.LOGIN_MARKERS):
                    return False
                if await cls.is_login_completed(page):
                    return True
                return False
            except Exception:
                return False
            finally:
                await browser.close()

    @classmethod
    async def setup(
        cls,
        account_file: str,
        handle: bool = False,
        return_detail: bool = False,
        qrcode_callback=None,
        headless: bool = LOCAL_CHROME_HEADLESS,
    ):
        """Resolve path -> cookie_auth -> if invalid and handle: cookie_gen."""
        if not os.path.exists(account_file) or not await cls.cookie_auth(account_file):
            if not handle:
                result = _build_login_result(False, "cookie_invalid", "cookie文件不存在或已失效", account_file)
                return result if return_detail else False
            result = await cls.cookie_gen(account_file, qrcode_callback=qrcode_callback, headless=headless)
            return result if return_detail else (result["success"] if isinstance(result, dict) else result)
        result = _build_login_result(True, "cookie_valid", "cookie有效", account_file)
        return result if return_detail else True

    @classmethod
    async def cookie_gen(
        cls,
        account_file: str,
        qrcode_callback=None,
        headless: bool = LOCAL_CHROME_HEADLESS,
        return_detail: bool = False,
    ):
        """QR login: goto login URL -> extract QR -> poll until complete -> save state."""
        Path(account_file).parent.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as playwright:
            browser = await cls._launch_browser(playwright, headless)
            context = await cls._init_context(browser, None)
            result = _build_login_result(False, "failed", f"{cls.PLATFORM_NAME}登录失败", account_file)
            page = None
            try:
                page = await context.new_page()
                await page.goto(cls.LOGIN_URL)
                await page.wait_for_timeout(3000)
                qrcode_src = await cls.extract_qrcode_src(page)
                if qrcode_src:
                    await _emit_qrcode_callback(qrcode_callback, {"qrcode": qrcode_src, "account_file": account_file})
                for _ in range(100):
                    if await cls.is_login_completed(page):
                        await page.wait_for_timeout(2000)
                        await context.storage_state(path=account_file)
                        if await cls.cookie_auth(account_file):
                            result = _build_login_result(True, "success", f"{cls.PLATFORM_NAME}扫码登录成功", account_file, None, page.url)
                        else:
                            result = _build_login_result(False, "cookie_invalid", f"{cls.PLATFORM_NAME}扫码完成但 cookie 校验失败", account_file, None, page.url)
                        break
                    await page.wait_for_timeout(3000)
                else:
                    result = _build_login_result(False, "timeout", f"{cls.PLATFORM_NAME}扫码登录超时", account_file, None, page.url if page else "")
            except Exception as exc:
                result = _build_login_result(False, "failed", str(exc), account_file, current_url=page.url if page else "")
            finally:
                await context.close()
                await browser.close()
            return result

    @asynccontextmanager
    async def _browser_session(self, headless: Optional[bool] = None):
        """Launch browser + context with stored cookies, yield page.
        Saves storage_state on exit (finally). Ensures cleanup."""
        async with async_playwright() as playwright:
            browser = await self._launch_browser(playwright, headless if headless is not None else self.headless)
            context = await self._init_context(browser, self.account_file)
            page = await context.new_page()
            try:
                yield page
            finally:
                try:
                    await context.storage_state(path=self.account_file)
                except Exception:
                    pass
                await context.close()
                await browser.close()


class BaseCliUploader(BasePlatformUploader):
    """CLI 平台基类(如 bilibili 走 biliup subprocess)。子类实现 cookie_auth/setup/upload。"""

    @classmethod
    async def cookie_auth(cls, account_file: str) -> bool:
        raise NotImplementedError

    @classmethod
    async def setup(cls, account_file, handle=False, return_detail=False, qrcode_callback=None, headless=LOCAL_CHROME_HEADLESS):
        raise NotImplementedError

    async def upload(self) -> PlatformResultExtras:
        raise NotImplementedError

    @staticmethod
    def run_subprocess(cmd: list):
        import subprocess
        return subprocess.run(cmd, capture_output=True, text=True)

    @staticmethod
    def parse_cli_output(output: str) -> dict:
        return {"raw": output}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_base_uploader.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Write failing test for `BaseBrowserUploader` login template**

Create `tests/test_base_uploader_login.py`:

```python
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from uploader.base_video import BaseBrowserUploader, _build_login_result


class FakeUploader(BaseBrowserUploader):
    PLATFORM_NAME = "fake"
    UPLOAD_URL = "https://example.com/upload"
    LOGIN_URL = "https://example.com/login"
    LOGIN_MARKERS = ["/login", "/signin"]
    PUBLISH_MARKERS = []

    @classmethod
    async def extract_qrcode_src(cls, page):
        return "data:image/png;base64,FAKE_QR_DATA"

    @classmethod
    async def is_login_completed(cls, page):
        # logged in if URL is the upload page (no /login marker)
        return "/login" not in (page.url or "")


class FakePage:
    def __init__(self, url):
        self.url = url

    async def goto(self, url):
        self.url = url

    async def wait_for_timeout(self, ms):
        pass


class FakeContext:
    def __init__(self, login_url, upload_url):
        self._login_url = login_url
        self._upload_url = upload_url
        self._goto_count = 0
        self.storage_state_saved = False

    async def new_page(self):
        # first goto (login) returns login URL, subsequent gotos return upload URL
        self._goto_count += 1
        return FakePage(self._login_url if self._goto_count == 1 else self._upload_url)

    async def storage_state(self, path=None):
        self.storage_state_saved = True

    async def close(self):
        pass


class FakeBrowser:
    def __init__(self, context):
        self._context = context

    async def new_context(self, **kwargs):
        return self._context

    async def close(self):
        pass


class FakePlaywright:
    def __init__(self, context):
        self._context = context
        self.chromium = MagicMock()

    async def __aenter__(self):
        self.chromium.launch = AsyncMock(return_value=FakeBrowser(self._context))
        return self

    async def __aexit__(self, *args):
        return False


class CookieAuthTests(unittest.TestCase):
    def test_returns_false_when_account_file_missing(self):
        result = asyncio.run(FakeUploader.cookie_auth("/nonexistent.json"))
        self.assertFalse(result)

    def test_returns_true_when_upload_url_no_login_marker(self):
        with patch("uploader.base_video.async_playwright") as mock_ap, \
             patch("uploader.base_video.os.path.exists", return_value=True), \
             patch("uploader.base_video.set_init_script", side_effect=lambda ctx: ctx):
            fake_pw = FakePlaywright(FakeContext("https://example.com/login", "https://example.com/upload"))
            mock_ap.return_value = fake_pw
            # simulate cookie_auth navigating to upload URL with no login marker
            fake_pw._context._goto_count = 1  # so new_page returns upload_url
            result = asyncio.run(FakeUploader.cookie_auth("/fake/exists.json"))
        self.assertTrue(result)


class SetupTests(unittest.TestCase):
    def test_returns_false_when_cookie_invalid_and_no_handle(self):
        with patch.object(FakeUploader, "cookie_auth", AsyncMock(return_value=False)), \
             patch("uploader.base_video.os.path.exists", return_value=True):
            result = asyncio.run(FakeUploader.setup("/fake.json", handle=False))
        self.assertFalse(result)

    def test_returns_true_when_cookie_valid(self):
        with patch.object(FakeUploader, "cookie_auth", AsyncMock(return_value=True)), \
             patch("uploader.base_video.os.path.exists", return_value=True):
            result = asyncio.run(FakeUploader.setup("/fake.json", handle=False))
        self.assertTrue(result)

    def test_triggers_cookie_gen_when_handle_true_and_invalid(self):
        with patch.object(FakeUploader, "cookie_auth", AsyncMock(return_value=False)), \
             patch.object(FakeUploader, "cookie_gen", AsyncMock(return_value={"success": True, "status": "success", "message": "ok", "account_file": "/fake.json", "qrcode": None, "current_url": ""})), \
             patch("uploader.base_video.os.path.exists", return_value=True):
            result = asyncio.run(FakeUploader.setup("/fake.json", handle=True))
        self.assertTrue(result)


class CookieGenTests(unittest.TestCase):
    def test_returns_success_when_login_completed_immediately(self):
        with patch("uploader.base_video.async_playwright") as mock_ap, \
             patch("uploader.base_video.set_init_script", side_effect=lambda ctx: ctx):
            # context returns a page whose URL is NOT the login page -> is_login_completed returns True
            fake_context = FakeContext("https://example.com/upload", "https://example.com/upload")
            fake_pw = FakePlaywright(fake_context)
            mock_ap.return_value = fake_pw
            with patch.object(FakeUploader, "cookie_auth", AsyncMock(return_value=True)):
                result = asyncio.run(FakeUploader.cookie_gen("/fake.json"))
        self.assertTrue(result["success"])
        self.assertTrue(fake_context.storage_state_saved)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 6: Run test to verify it fails or passes**

Run: `python -m pytest tests/test_base_uploader_login.py -v`
Expected: PASS (implementation already in Step 3 covers this; if failures, fix the implementation)

- [ ] **Step 7: Write failing test for `_browser_session` context manager**

Create `tests/test_base_uploader_session.py`:

```python
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from uploader.base_video import BaseBrowserUploader


class FakeUploader(BaseBrowserUploader):
    PLATFORM_NAME = "fake"
    UPLOAD_URL = "https://example.com/upload"
    LOGIN_URL = "https://example.com/login"
    LOGIN_MARKERS = ["/login"]
    PUBLISH_MARKERS = []


class FakePage:
    def __init__(self):
        self.url = "https://example.com/upload"


class FakeContext:
    def __init__(self):
        self.storage_state_calls = []
        self.closed = False

    async def new_page(self):
        return FakePage()

    async def storage_state(self, path=None):
        self.storage_state_calls.append(path)

    async def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self, context):
        self._context = context
        self.closed = False

    async def new_context(self, **kwargs):
        return self._context

    async def close(self):
        self.closed = True


class FakePlaywright:
    def __init__(self, context):
        self._context = context
        self.chromium = MagicMock()

    async def __aenter__(self):
        self.chromium.launch = AsyncMock(return_value=FakeBrowser(self._context))
        return self

    async def __aexit__(self, *args):
        return False


class BrowserSessionTests(unittest.TestCase):
    def test_storage_state_saved_on_normal_exit(self):
        uploader = FakeUploader.__new__(FakeUploader)
        uploader.account_file = "/fake/account.json"
        uploader.headless = True
        fake_context = FakeContext()
        with patch("uploader.base_video.async_playwright") as mock_ap, \
             patch("uploader.base_video.set_init_script", side_effect=lambda ctx: ctx), \
             patch("uploader.base_video.os.path.exists", return_value=True):
            mock_ap.return_value = FakePlaywright(fake_context)

            async def run():
                async with uploader._browser_session() as page:
                    pass  # no-op
            asyncio.run(run())
        self.assertEqual(len(fake_context.storage_state_calls), 1)
        self.assertEqual(fake_context.storage_state_calls[0], "/fake/account.json")

    def test_storage_state_saved_on_exception(self):
        uploader = FakeUploader.__new__(FakeUploader)
        uploader.account_file = "/fake/account.json"
        uploader.headless = True
        fake_context = FakeContext()
        with patch("uploader.base_video.async_playwright") as mock_ap, \
             patch("uploader.base_video.set_init_script", side_effect=lambda ctx: ctx), \
             patch("uploader.base_video.os.path.exists", return_value=True):
            mock_ap.return_value = FakePlaywright(fake_context)

            async def run():
                async with uploader._browser_session() as page:
                    raise RuntimeError("upload failed")
            with self.assertRaises(RuntimeError):
                asyncio.run(run())
        # finally block must still save storage_state
        self.assertEqual(len(fake_context.storage_state_calls), 1)

    def test_context_and_browser_closed_on_exit(self):
        uploader = FakeUploader.__new__(FakeUploader)
        uploader.account_file = "/fake/account.json"
        uploader.headless = True
        fake_context = FakeContext()
        fake_browser = None
        with patch("uploader.base_video.async_playwright") as mock_ap, \
             patch("uploader.base_video.set_init_script", side_effect=lambda ctx: ctx), \
             patch("uploader.base_video.os.path.exists", return_value=True):
            fake_pw = FakePlaywright(fake_context)
            mock_ap.return_value = fake_pw

            async def run():
                async with uploader._browser_session() as page:
                    nonlocal fake_browser
                    pass
            asyncio.run(run())
        self.assertTrue(fake_context.closed)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 8: Run test to verify it passes**

Run: `python -m pytest tests/test_base_uploader_session.py -v`
Expected: PASS

- [ ] **Step 9: Run regression suite to verify nothing broke**

Run: `python -m pytest tests/test_publish_engine.py tests/test_publish_dispatch.py tests/test_publish_reporter.py tests/test_publish_cli.py -v`
Expected: PASS (all existing tests still green; `BaseVideoUploader` alias keeps 5 `*BaseUploader` imports working)

- [ ] **Step 10: Commit**

```bash
git add uploader/base_video.py tests/test_base_uploader.py tests/test_base_uploader_login.py tests/test_base_uploader_session.py
git commit -m "feat(uploader): add BasePlatformUploader/BaseBrowserUploader/BaseCliUploader three-layer base classes"
```

---

## Task 2: 迁移 weibo(首个浏览器平台,验证模式)

**Files:**
- Modify: `uploader/weibo_uploader/main.py`(`WeiboBaseUploader` 缩成 hook 层,`WeiboVideo`/`WeiboNote` 改 `upload()`,模块级 wrapper 改薄委托)
- Modify: `publish/dispatch.py:362-428`(`publish_to_weibo` 简化,删 `result.get("video_link", "")` 提取)
- Test: `tests/test_publish_engine.py`(回归网,零修改)
- Test: `tests/test_weibo_uploader.py`(现有,零修改)

**Interfaces:**
- Consumes: Task 1 的 `BaseBrowserUploader` / `PublishStrategy` / `PlatformResultExtras` / `_msg` / `_build_launch_kwargs` / `_build_login_result` / `_emit_qrcode_callback` / `_get_qrcode_utils`(均从 `uploader.base_video` 导入)
- Produces: 
  - `WeiboBaseUploader(BaseBrowserUploader)` with `PLATFORM_NAME="weibo"` / `UPLOAD_URL=WEIBO_UPLOAD_CHANNEL_URL` / `LOGIN_URL=WEIBO_LOGIN_URL` / `LOGIN_MARKERS=WEIBO_LOGIN_URL_MARKERS` / `is_login_completed` / `extract_qrcode_src`(如微博 QR 有)
  - `WeiboVideo.upload(self) -> PlatformResultExtras` returning `{"result_url": video_link}`
  - `WeiboNote.upload(self) -> PlatformResultExtras` returning `{"result_url": ...}` or empty
  - `WeiboVideo.main()` / `WeiboNote.main()` 别名 wrapper(Task 9 删)
  - 模块级 `cookie_auth(account_file)` / `weibo_setup(account_file, handle, return_detail, qrcode_callback, headless)` 薄 wrapper 委托 `WeiboBaseUploader.cookie_auth` / `.setup`

- [ ] **Step 1: Write failing test for weibo uploader structure**

Create `tests/test_weibo_uploader_base.py`:

```python
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from uploader.base_video import BaseBrowserUploader, PublishStrategy
from uploader.weibo_uploader.main import WeiboBaseUploader, WeiboVideo, WeiboNote, cookie_auth, weibo_setup


class WeiboBaseUploaderInheritanceTests(unittest.TestCase):
    def test_inherits_base_browser_uploader(self):
        self.assertTrue(issubclass(WeiboBaseUploader, BaseBrowserUploader))

    def test_platform_name(self):
        self.assertEqual(WeiboBaseUploader.PLATFORM_NAME, "weibo")

    def test_upload_url(self):
        self.assertTrue(WeiboBaseUploader.UPLOAD_URL.startswith("https://"))

    def test_login_url(self):
        self.assertTrue(WeiboBaseUploader.LOGIN_URL.startswith("https://"))

    def test_login_markers_nonempty(self):
        self.assertGreater(len(WeiboBaseUploader.LOGIN_MARKERS), 0)


class WeiboVideoUploadTests(unittest.TestCase):
    def test_upload_returns_platform_result_extras(self):
        import asyncio
        uploader = WeiboVideo(
            title="t", file_path="/fake.mp4", tags=[], publish_date=0,
            account_file="/fake.json", desc="", publish_strategy=PublishStrategy.IMMEDIATE,
        )
        with patch.object(uploader, "_browser_session") as mock_session, \
             patch.object(uploader, "validate_upload_args", AsyncMock()), \
             patch.object(WeiboVideo, "upload_video_content", AsyncMock(return_value="https://weibo.com/v/123")):
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def fake_session():
                class FakePage:
                    url = "https://weibo.com/upload/channel"
                yield FakePage()

            mock_session.return_value = fake_session()
            result = asyncio.run(uploader.upload())
        self.assertTrue(result["success"])
        self.assertEqual(result["result_url"], "https://weibo.com/v/123")

    def test_main_is_alias_of_upload(self):
        uploader = WeiboVideo(
            title="t", file_path="/fake.mp4", tags=[], publish_date=0,
            account_file="/fake.json", desc="", publish_strategy=PublishStrategy.IMMEDIATE,
        )
        with patch.object(uploader, "upload", AsyncMock(return_value={"success": True, "message": "ok"})):
            import asyncio
            result = asyncio.run(uploader.main())
        self.assertEqual(result["success"], True)


class ModuleWrapperTests(unittest.TestCase):
    def test_cookie_auth_delegates_to_classmethod(self):
        import asyncio
        with patch.object(WeiboBaseUploader, "cookie_auth", AsyncMock(return_value=True)):
            result = asyncio.run(cookie_auth("/fake.json"))
        self.assertTrue(result)

    def test_weibo_setup_signature_is_5_params(self):
        import inspect
        sig = inspect.signature(weibo_setup)
        params = list(sig.parameters.keys())
        self.assertEqual(params, ["account_file", "handle", "return_detail", "qrcode_callback", "headless"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_weibo_uploader_base.py -v`
Expected: FAIL (WeiboBaseUploader doesn't inherit BaseBrowserUploader yet; upload() signature wrong)

- [ ] **Step 3: Refactor `uploader/weibo_uploader/main.py`**

In `uploader/weibo_uploader/main.py`, make the following changes:

**3a. Update imports** - replace the module-level helper functions with imports from base_video. Change the top of the file so that `_msg`, `_build_launch_kwargs`, `_build_login_result`, `_emit_qrcode_callback`, `_get_qrcode_utils` come from `uploader.base_video`:

```python
from uploader.base_video import (
    BaseBrowserUploader,
    PlatformResultExtras,
    PublishStrategy,
    _build_launch_kwargs,
    _build_login_result,
    _emit_qrcode_callback,
    _get_qrcode_utils,
    _msg,
)
```

Remove the local definitions of `_msg`, `_build_launch_kwargs`, `_build_login_result`, `_emit_qrcode_callback`, `_get_qrcode_utils` (lines 28-92 in current file). Keep `_resolve_account_file` and the platform-specific constants (`WEIBO_MAIN_URL`, `WEIBO_LOGIN_URL`, etc.) and helper functions (`_is_visible`, `_is_weibo_auth_page_valid`, `_is_weibo_login_completed`).

**3b. Convert `WeiboBaseUploader` to inherit `BaseBrowserUploader`** - replace the class definition:

```python
class WeiboBaseUploader(BaseBrowserUploader):
    """微博上传器基类 - hook layer for BaseBrowserUploader."""

    PLATFORM_NAME = "weibo"
    UPLOAD_URL = WEIBO_UPLOAD_CHANNEL_URL
    LOGIN_URL = WEIBO_LOGIN_URL
    LOGIN_MARKERS = list(WEIBO_LOGIN_URL_MARKERS)
    PUBLISH_MARKERS = []

    def __init__(
        self,
        publish_date,
        account_file,
        publish_strategy=PublishStrategy.IMMEDIATE,
        debug=DEBUG_MODE,
        headless=LOCAL_CHROME_HEADLESS,
    ):
        self.publish_date = publish_date
        self.account_file = _resolve_account_file(account_file)
        self.publish_strategy = publish_strategy
        self.debug = debug
        self.date_format = "%Y年%m月%d日 %H:%M"
        self.headless = headless

    @classmethod
    async def is_login_completed(cls, page):
        return await _is_weibo_login_completed(page)

    async def validate_login_and_strategy(self):
        """Renamed from `validate_base_args(self)` to avoid collision with
        `BasePlatformUploader.validate_base_args(params)` staticmethod (called by dispatch).
        Checks cookie existence/validity + publish_strategy + publish_date."""
        if not os.path.exists(self.account_file):
            raise RuntimeError(f"cookie文件不存在，请先完成微博登录: {self.account_file}")
        if not await cookie_auth(self.account_file):
            raise RuntimeError(f"cookie文件已失效，请先完成微博登录: {self.account_file}")

        if self.publish_strategy not in {PublishStrategy.IMMEDIATE, PublishStrategy.SCHEDULED}:
            raise ValueError(f"不支持的发布策略: {self.publish_strategy}")

        if self.publish_strategy == PublishStrategy.SCHEDULED:
            self.publish_date = self.validate_publish_date(self.publish_date)
        else:
            self.publish_date = 0

    # fill_content / set_schedule_time: copy bodies verbatim from existing
    # WeiboBaseUploader (current lines 293-339). Do NOT change their internals.
    async def fill_content(self, page: Page, content: str, tags: list = None):
        ...  # copy existing body from uploader/weibo_uploader/main.py:293-310

    async def set_schedule_time(self, page: Page, publish_date: datetime):
        ...  # copy existing body from uploader/weibo_uploader/main.py:312-339
```

**3c. Convert module-level `cookie_auth`** to thin wrapper:

```python
async def cookie_auth(account_file):
    """验证 cookie 是否有效 - 委托 WeiboBaseUploader.cookie_auth"""
    account_file = _resolve_account_file(account_file)
    return await WeiboBaseUploader.cookie_auth(account_file)
```

**3d. Convert module-level `weibo_cookie_gen`** to thin wrapper:

```python
async def weibo_cookie_gen(account_file, qrcode_callback=None, poll_interval=3, max_checks=100, headless=LOCAL_CHROME_HEADLESS):
    """生成微博登录 cookie - 委托 WeiboBaseUploader.cookie_gen"""
    account_file = _resolve_account_file(account_file)
    return await WeiboBaseUploader.cookie_gen(account_file, qrcode_callback=qrcode_callback, headless=headless)
```

**3e. Convert module-level `weibo_setup`** to thin wrapper:

```python
async def weibo_setup(account_file, handle=False, return_detail=False, qrcode_callback=None, headless=LOCAL_CHROME_HEADLESS):
    """微博登录设置 - 委托 WeiboBaseUploader.setup"""
    account_file = _resolve_account_file(account_file)
    return await WeiboBaseUploader.setup(account_file, handle, return_detail, qrcode_callback, headless)
```

**3f. Convert `WeiboVideo.upload`** to use `_browser_session` and return `PlatformResultExtras`:

Replace the existing `upload` method (around lines 640-714) with:

```python
    async def upload(self) -> PlatformResultExtras:
        """主入口，返回 PlatformResultExtras"""
        weibo_logger.info(_msg("🧍", "检查 cookie 和视频文件..."))
        await self.validate_upload_args()
        weibo_logger.info(_msg("🥳", "上传前检查通过"))

        result: PlatformResultExtras = {"success": False, "message": ""}

        try:
            async with self._browser_session() as page:
                video_link = await self.upload_video_content(page)
                weibo_logger.success(_msg("🥳", "cookie 更新完毕"))
                result["success"] = True
                if video_link:
                    result["result_url"] = video_link
                    result["message"] = f"发布成功，视频链接: {video_link}"
                else:
                    result["message"] = "发布成功，但未获取到视频链接"
        except Exception as e:
            result["message"] = str(e)
            weibo_logger.error(_msg("❌", f"上传失败: {e}"))

        return result

    async def main(self) -> dict:
        """别名 wrapper - Task 9 删"""
        return await self.upload()
```

**3f-1. Update `WeiboVideo.validate_upload_args`** (around line 369): change the call `await self.validate_base_args()` to `await self.validate_login_and_strategy()` (renamed in 3b to avoid collision with the staticmethod on `BasePlatformUploader`).

**3g. Convert `WeiboNote.upload`** the same way - replace its `upload` method to use `_browser_session` and return `PlatformResultExtras`. Add `main()` alias. Also update `WeiboNote.validate_upload_args` (around line 749) to call `self.validate_login_and_strategy()` instead of `self.validate_base_args()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_weibo_uploader_base.py tests/test_weibo_uploader.py -v`
Expected: PASS

- [ ] **Step 5: Simplify `publish_to_weibo` in `publish/dispatch.py`**

Replace `publish/dispatch.py:362-428` (`publish_to_weibo` function) with:

```python
async def publish_to_weibo(params: dict) -> dict:
    """发布到微博"""
    from uploader.weibo_uploader.main import WeiboVideo, WeiboNote
    from utils.excel_writer import write_video_link

    account_file = resolve_path(params["account_file"])
    title = truncate_title(params["title"], "weibo")

    if params["content_type"] == "video":
        params = {**params, "video_file": resolve_path(params["video_file"])}
    elif params.get("images"):
        params = {**params, "images": [resolve_path(img) for img in params["images"]]}

    err = WeiboVideo.validate_base_args(params)
    if err:
        return err

    try:
        if params["content_type"] == "video":
            uploader = WeiboVideo(
                title=title, file_path=params["video_file"], tags=params["tags"],
                publish_date=params["publish_time"] or 0, account_file=account_file,
                desc=params["desc"], publish_strategy=params["publish_strategy"],
            )
        else:
            uploader = WeiboNote(
                image_paths=params["images"], note=params["desc"], tags=params["tags"],
                publish_date=params["publish_time"] or 0, account_file=account_file,
                title=title, publish_strategy=params["publish_strategy"],
            )
        result = await uploader.upload()
        if result["success"] and result.get("result_url"):
            try:
                write_result = write_video_link(result["result_url"])
                if write_result["success"]:
                    print(f"  📝 视频链接已写入 Excel: {result['result_url']}")
                else:
                    print(f"  ⚠️ 写入 Excel 失败: {write_result['message']}")
            except Exception as e:
                print(f"  ⚠️ 写入 Excel 异常: {e}")
        return result
    except Exception as e:
        return {"success": False, "message": str(e)}
```

- [ ] **Step 6: Run regression suite**

Run: `python -m pytest tests/test_publish_engine.py tests/test_publish_dispatch.py tests/test_weibo_uploader.py tests/test_weibo_uploader_base.py -v`
Expected: PASS (all green)

- [ ] **Step 7: Manual smoke test (optional but recommended)**

Configure a weibo account in `publish_config.ini`, run `python publish_all.py --platforms weibo --video <test.mp4> --title "test"`, verify publish succeeds.

- [ ] **Step 8: Commit**

```bash
git add uploader/weibo_uploader/main.py publish/dispatch.py tests/test_weibo_uploader_base.py
git commit -m "refactor(weibo): migrate WeiboBaseUploader to BaseBrowserUploader, unify return to PlatformResultExtras"
```

---

## Task 3: 迁移 xiaohongshu

**Files:**
- Modify: `uploader/xiaohongshu_uploader/main.py`
- Modify: `publish/dispatch.py:122-182` (`publish_to_xiaohongshu`)
- Test: `tests/test_xiaohongshu_uploader.py` (existing, zero modifications)

**Interfaces:**
- Consumes: Task 1 base classes + Task 2 pattern
- Produces: `XiaoHongShuBaseUploader(BaseBrowserUploader)`, `XiaoHongShuVideo.upload()` returning `{"result_url": share_link, "result_id": note_id}`, `XiaoHongShuNote.upload()` returning same, module-level wrappers, `main()` aliases

- [ ] **Step 1: Write failing test for xiaohongshu uploader structure**

Create `tests/test_xiaohongshu_uploader_base.py`:

```python
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from uploader.base_video import BaseBrowserUploader, PublishStrategy
from uploader.xiaohongshu_uploader.main import (
    XiaoHongShuBaseUploader, XiaoHongShuVideo, XiaoHongShuNote,
    cookie_auth, xiaohongshu_setup,
)


class XiaoHongShuBaseUploaderInheritanceTests(unittest.TestCase):
    def test_inherits_base_browser_uploader(self):
        self.assertTrue(issubclass(XiaoHongShuBaseUploader, BaseBrowserUploader))

    def test_platform_name(self):
        self.assertEqual(XiaoHongShuBaseUploader.PLATFORM_NAME, "xiaohongshu")

    def test_login_markers_nonempty(self):
        self.assertGreater(len(XiaoHongShuBaseUploader.LOGIN_MARKERS), 0)


class XiaoHongShuVideoUploadTests(unittest.TestCase):
    def test_upload_returns_unified_dict(self):
        import asyncio
        uploader = XiaoHongShuVideo(
            title="t", file_path="/fake.mp4", tags=[], publish_date=0,
            account_file="/fake.json", desc="", publish_strategy=PublishStrategy.IMMEDIATE,
        )
        with patch.object(XiaoHongShuVideo, "upload_video_content", AsyncMock(return_value={"share_link": "https://xhs.link/abc", "note_id": "xyz"})), \
             patch.object(uploader, "validate_upload_args", AsyncMock()):
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def fake_session():
                class FakePage:
                    url = "https://creator.xiaohongshu.com"
                yield FakePage()

            with patch.object(uploader, "_browser_session", return_value=fake_session()):
                result = asyncio.run(uploader.upload())
        self.assertTrue(result["success"])
        self.assertEqual(result["result_url"], "https://xhs.link/abc")
        self.assertEqual(result["result_id"], "xyz")

    def test_main_is_alias_of_upload(self):
        uploader = XiaoHongShuVideo(
            title="t", file_path="/fake.mp4", tags=[], publish_date=0,
            account_file="/fake.json", desc="", publish_strategy=PublishStrategy.IMMEDIATE,
        )
        with patch.object(uploader, "upload", AsyncMock(return_value={"success": True, "message": "ok"})):
            import asyncio
            result = asyncio.run(uploader.main())
        self.assertTrue(result["success"])


class ModuleWrapperTests(unittest.TestCase):
    def test_setup_signature_is_5_params(self):
        import inspect
        sig = inspect.signature(xiaohongshu_setup)
        params = list(sig.parameters.keys())
        self.assertEqual(params, ["account_file", "handle", "return_detail", "qrcode_callback", "headless"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_xiaohongshu_uploader_base.py -v`
Expected: FAIL

- [ ] **Step 3: Refactor `uploader/xiaohongshu_uploader/main.py`**

Apply the same pattern as Task 2:
- Import `_msg`, `_build_launch_kwargs`, `_build_login_result`, `_emit_qrcode_callback`, `_get_qrcode_utils` from `uploader.base_video`
- Remove their local definitions
- `XiaoHongShuBaseUploader` inherits `BaseBrowserUploader`, defines `PLATFORM_NAME = "xiaohongshu"`, `UPLOAD_URL = XHS_UPLOAD_URL` (existing constant), `LOGIN_URL = XHS_LOGIN_URL` (existing constant), `LOGIN_MARKERS = ["手机号登录", "扫码登录"]` (existing markers)
- **Rename instance method `validate_base_args(self)` to `validate_login_and_strategy(self)`** on `XiaoHongShuBaseUploader` (current line 467) - same collision fix as Task 2
- Update `XiaoHongShuVideo.validate_upload_args()` (line 620) and `XiaoHongShuNote.validate_upload_args()` (line 827) to call `self.validate_login_and_strategy()` instead of `self.validate_base_args()`
- Move `is_login_completed` logic to classmethod
- Module-level `cookie_auth(account_file)` -> `return await XiaoHongShuBaseUploader.cookie_auth(account_file)` (after resolving path with existing `_resolve_account_file` if present, or use the classmethod directly)
- Module-level `xiaohongshu_setup(account_file, handle, return_detail, qrcode_callback, headless)` -> thin wrapper with 5-param signature
- `XiaoHongShuVideo.upload(self) -> PlatformResultExtras` returns `{"success": True, "message": "发布成功", "result_url": share_link, "result_id": note_id}`
- `XiaoHongShuNote.upload(self) -> PlatformResultExtras` returns same shape
- Add `main()` alias wrapper on both Video and Note classes
- Use `async with self._browser_session() as page:` in upload methods, remove manual `context.storage_state(path=...)` + `context.close()` + `browser.close()` at end

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_xiaohongshu_uploader_base.py tests/test_xiaohongshu_uploader.py -v`
Expected: PASS

- [ ] **Step 5: Simplify `publish_to_xiaohongshu` in `publish/dispatch.py`**

Replace `publish/dispatch.py:122-182` with:

```python
async def publish_to_xiaohongshu(params: dict) -> dict:
    """发布到小红书"""
    from uploader.xiaohongshu_uploader.main import XiaoHongShuVideo, XiaoHongShuNote

    account_file = resolve_path(params["account_file"])
    title = truncate_title(params["title"], "xiaohongshu")

    if params["content_type"] == "video":
        params = {**params, "video_file": resolve_path(params["video_file"])}
    elif params.get("images"):
        params = {**params, "images": [resolve_path(img) for img in params["images"]]}

    err = XiaoHongShuVideo.validate_base_args(params)
    if err:
        return err

    try:
        if params["content_type"] == "video":
            uploader = XiaoHongShuVideo(
                title=title, file_path=params["video_file"], tags=params["tags"],
                publish_date=params["publish_time"] or 0, account_file=account_file,
                desc=params["desc"], publish_strategy=params["publish_strategy"],
            )
        else:
            uploader = XiaoHongShuNote(
                image_paths=params["images"], note=params["desc"], tags=params["tags"],
                publish_date=params["publish_time"] or 0, account_file=account_file,
                title=title, desc=params["desc"], publish_strategy=params["publish_strategy"],
            )
        return await uploader.upload()
    except Exception as e:
        return {"success": False, "message": str(e)}
```

- [ ] **Step 6: Run regression suite**

Run: `python -m pytest tests/test_publish_engine.py tests/test_publish_dispatch.py tests/test_xiaohongshu_uploader.py tests/test_xiaohongshu_uploader_base.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add uploader/xiaohongshu_uploader/main.py publish/dispatch.py tests/test_xiaohongshu_uploader_base.py
git commit -m "refactor(xiaohongshu): migrate to BaseBrowserUploader, unify return contract"
```

---

## Task 4: 迁移 kuaishou

**Files:**
- Modify: `uploader/ks_uploader/main.py`
- Modify: `publish/dispatch.py:185-244` (`publish_to_kuaishou`)
- Test: existing tests stay green

**Interfaces:**
- Consumes: Task 1 base classes + Task 2 pattern
- Produces: `KSBaseUploader(BaseBrowserUploader)`, `KSVideo.upload()` returning `{"result_url": share_link, "result_id": video_id}`, `KSNote.upload()`, module-level wrappers, `main()` aliases

- [ ] **Step 1: Write failing test for kuaishou uploader structure**

Create `tests/test_ks_uploader_base.py`:

```python
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from uploader.base_video import BaseBrowserUploader, PublishStrategy
from uploader.ks_uploader.main import KSBaseUploader, KSVideo, KSNote, cookie_auth, ks_setup


class KSBaseUploaderInheritanceTests(unittest.TestCase):
    def test_inherits_base_browser_uploader(self):
        self.assertTrue(issubclass(KSBaseUploader, BaseBrowserUploader))

    def test_platform_name(self):
        self.assertEqual(KSBaseUploader.PLATFORM_NAME, "kuaishou")


class KSVideUploadTests(unittest.TestCase):
    def test_upload_returns_unified_dict(self):
        import asyncio
        uploader = KSVideo(
            title="t", file_path="/fake.mp4", tags=[], publish_date=0,
            account_file="/fake.json", desc="", publish_strategy=PublishStrategy.IMMEDIATE,
        )
        with patch.object(KSVideo, "upload_video_content", AsyncMock(return_value={"share_link": "https://kuaishou.com/v/abc", "video_id": "vid123"})), \
             patch.object(uploader, "validate_upload_args", AsyncMock()):
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def fake_session():
                class FakePage:
                    url = "https://cp.kuaishou.com"
                yield FakePage()

            with patch.object(uploader, "_browser_session", return_value=fake_session()):
                result = asyncio.run(uploader.upload())
        self.assertTrue(result["success"])
        self.assertEqual(result["result_url"], "https://kuaishou.com/v/abc")
        self.assertEqual(result["result_id"], "vid123")


class ModuleWrapperTests(unittest.TestCase):
    def test_setup_signature_is_5_params(self):
        import inspect
        sig = inspect.signature(ks_setup)
        params = list(sig.parameters.keys())
        self.assertEqual(params, ["account_file", "handle", "return_detail", "qrcode_callback", "headless"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ks_uploader_base.py -v`
Expected: FAIL

- [ ] **Step 3: Refactor `uploader/ks_uploader/main.py`**

Apply same pattern as Task 2:
- Import shared helpers from `uploader.base_video`
- `KSBaseUploader` inherits `BaseBrowserUploader`, defines `PLATFORM_NAME = "kuaishou"`, `UPLOAD_URL = KS_UPLOAD_URL` (existing), `LOGIN_URL = KS_LOGIN_URL` (existing), `LOGIN_MARKERS` (existing markers)
- **Rename instance method `validate_base_args(self)` to `validate_login_and_strategy(self)`** on `KSBaseUploader` (current line 455) - same collision fix as Task 2
- Update `KSVideo.validate_upload_args()` (line 540) and `KSNote.validate_upload_args()` (line 755) to call `self.validate_login_and_strategy()` instead of `self.validate_base_args()`
- Module-level `cookie_auth` / `ks_setup` become thin wrappers with 5-param signature
- `KSVideo.upload(self)` returns `{"result_url": share_link, "result_id": video_id}`
- `KSNote.upload(self)` returns same
- Add `main()` aliases
- Use `_browser_session` context manager

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ks_uploader_base.py -v`
Expected: PASS

- [ ] **Step 5: Simplify `publish_to_kuaishou` in `publish/dispatch.py`**

Replace `publish/dispatch.py:185-244` with:

```python
async def publish_to_kuaishou(params: dict) -> dict:
    """发布到快手"""
    from uploader.ks_uploader.main import KSVideo, KSNote

    account_file = resolve_path(params["account_file"])
    title = truncate_title(params["title"], "kuaishou")

    if params["content_type"] == "video":
        params = {**params, "video_file": resolve_path(params["video_file"])}
    elif params.get("images"):
        params = {**params, "images": [resolve_path(img) for img in params["images"]]}

    err = KSVideo.validate_base_args(params)
    if err:
        return err

    try:
        if params["content_type"] == "video":
            uploader = KSVideo(
                title=title, file_path=params["video_file"], tags=params["tags"],
                publish_date=params["publish_time"] or 0, account_file=account_file,
                desc=params["desc"], publish_strategy=params["publish_strategy"],
            )
        else:
            uploader = KSNote(
                image_paths=params["images"], note=params["desc"], tags=params["tags"],
                publish_date=params["publish_time"] or 0, account_file=account_file,
                title=title, publish_strategy=params["publish_strategy"],
            )
        return await uploader.upload()
    except Exception as e:
        return {"success": False, "message": str(e)}
```

- [ ] **Step 6: Run regression suite**

Run: `python -m pytest tests/test_publish_engine.py tests/test_publish_dispatch.py tests/test_ks_uploader_base.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add uploader/ks_uploader/main.py publish/dispatch.py tests/test_ks_uploader_base.py
git commit -m "refactor(kuaishou): migrate to BaseBrowserUploader, unify return contract"
```

---

## Task 5: 迁移 tencent

**Files:**
- Modify: `uploader/tencent_uploader/main.py`
- Modify: `publish/dispatch.py:247-280` (`publish_to_tencent`)
- Test: existing tests stay green

**Interfaces:**
- Consumes: Task 1 base classes + Task 2 pattern
- Produces: `TencentBaseUploader(BaseBrowserUploader)`, `TencentVideo.upload()` returning `{"result_url": "", "result_id": ""}` (tencent doesn't expose URL), `TencentNote` stub preserved, module-level wrappers, `main()` aliases

- [ ] **Step 1: Write failing test for tencent uploader structure**

Create `tests/test_tencent_uploader_base.py`:

```python
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from uploader.base_video import BaseBrowserUploader, PublishStrategy
from uploader.tencent_uploader.main import TencentBaseUploader, TencentVideo, cookie_auth, tencent_setup


class TencentBaseUploaderInheritanceTests(unittest.TestCase):
    def test_inherits_base_browser_uploader(self):
        self.assertTrue(issubclass(TencentBaseUploader, BaseBrowserUploader))

    def test_platform_name(self):
        self.assertEqual(TencentBaseUploader.PLATFORM_NAME, "tencent")


class TencentVideoUploadTests(unittest.TestCase):
    def test_upload_returns_unified_dict_with_empty_url(self):
        import asyncio
        uploader = TencentVideo(
            title="t", file_path="/fake.mp4", tags=[], publish_date=0,
            account_file="/fake.json", desc="", publish_strategy=PublishStrategy.IMMEDIATE,
        )
        with patch.object(uploader, "validate_upload_args", AsyncMock()):
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def fake_session():
                class FakePage:
                    url = "https://channels.weixin.qq.com"
                yield FakePage()

            with patch.object(uploader, "_browser_session", return_value=fake_session()), \
                 patch.object(TencentVideo, "upload_video_content", AsyncMock()):
                result = asyncio.run(uploader.upload())
        self.assertTrue(result["success"])
        # tencent doesn't expose URL
        self.assertNotIn("result_url", result)


class ModuleWrapperTests(unittest.TestCase):
    def test_setup_signature_is_5_params(self):
        import inspect
        sig = inspect.signature(tencent_setup)
        params = list(sig.parameters.keys())
        self.assertEqual(params, ["account_file", "handle", "return_detail", "qrcode_callback", "headless"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tencent_uploader_base.py -v`
Expected: FAIL

- [ ] **Step 3: Refactor `uploader/tencent_uploader/main.py`**

Apply same pattern as Task 2:
- Import shared helpers from `uploader.base_video`
- `TencentBaseUploader` inherits `BaseBrowserUploader`, defines `PLATFORM_NAME = "tencent"`, `UPLOAD_URL = TENCENT_UPLOAD_URL` (existing), `LOGIN_URL = TENCENT_LOGIN_URL` (existing), `LOGIN_MARKERS` (existing)
- **Rename instance method `validate_base_args(self)` to `validate_login_and_strategy(self)`** on `TencentBaseUploader` (current line 462) - same collision fix as Task 2
- Update `TencentVideo.validate_upload_args()` (line 663) and `TencentNote.validate_upload_args()` (line 808) to call `self.validate_login_and_strategy()` instead of `self.validate_base_args()`
- **Preserve the cookie_auth headless bug fix** documented in memory `project_tencent_cookie_auth_headless_bug.md`: the `_launch_browser` call must use `LOCAL_CHROME_HEADLESS` (not hardcoded `True`), and the marker wait logic must be preserved. If the base class `cookie_auth` template doesn't accommodate this, override `cookie_auth` on `TencentBaseUploader` to add the marker wait, while still using `_launch_browser` + `_init_context` from base.
- Module-level `cookie_auth` / `tencent_setup` become thin wrappers with 5-param signature
- `TencentVideo.upload(self)` returns `{"success": True, "message": "发布成功"}` (no `result_url`/`result_id`)
- `TencentNote` stub preserved (don't touch its existing structure)
- Add `main()` alias on `TencentVideo`

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tencent_uploader_base.py -v`
Expected: PASS

- [ ] **Step 5: Simplify `publish_to_tencent` in `publish/dispatch.py`**

Replace `publish/dispatch.py:247-280` with:

```python
async def publish_to_tencent(params: dict) -> dict:
    """发布到微信视频号"""
    from uploader.tencent_uploader.main import TencentVideo

    account_file = resolve_path(params["account_file"])
    title = truncate_title(params["title"], "tencent")

    if params["content_type"] == "video":
        params = {**params, "video_file": resolve_path(params["video_file"])}
    else:
        return {"success": False, "message": "微信视频号不支持图文发布，请使用 convert_to_video=true 转为视频发布"}

    err = TencentVideo.validate_base_args(params)
    if err:
        return err

    try:
        uploader = TencentVideo(
            title=title, file_path=params["video_file"], tags=params["tags"],
            publish_date=params["publish_time"] or 0, account_file=account_file,
            desc=params["desc"], publish_strategy=params["publish_strategy"],
        )
        return await uploader.upload()
    except Exception as e:
        return {"success": False, "message": str(e)}
```

- [ ] **Step 6: Run regression suite**

Run: `python -m pytest tests/test_publish_engine.py tests/test_publish_dispatch.py tests/test_tencent_uploader_base.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add uploader/tencent_uploader/main.py publish/dispatch.py tests/test_tencent_uploader_base.py
git commit -m "refactor(tencent): migrate to BaseBrowserUploader, preserve headless bug fix"
```

---

## Task 6: 迁移 douyin(最复杂,有 DouyinPublishRestrictedError)

**Files:**
- Modify: `uploader/douyin_uploader/main.py`
- Modify: `publish/dispatch.py:61-119` (`publish_to_douyin`)
- Test: existing tests stay green

**Interfaces:**
- Consumes: Task 1 base classes + `AccountRestrictedError`
- Produces: `DouYinBaseUploader(BaseBrowserUploader)`, `DouYinVideo.upload()` returning `PlatformResultExtras` with `account_issue`/`issue_type` on restriction, `DouYinNote.upload()` with `douyin_upload_note()` alias, module-level wrappers, `main()` aliases

- [ ] **Step 1: Write failing test for douyin uploader structure**

Create `tests/test_douyin_uploader_base.py`:

```python
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from uploader.base_video import AccountRestrictedError, BaseBrowserUploader, PublishStrategy
from uploader.douyin_uploader.main import (
    DouYinBaseUploader, DouYinVideo, DouYinNote,
    cookie_auth, douyin_setup, DouyinPublishRestrictedError,
)


class DouYinBaseUploaderInheritanceTests(unittest.TestCase):
    def test_inherits_base_browser_uploader(self):
        self.assertTrue(issubclass(DouYinBaseUploader, BaseBrowserUploader))

    def test_platform_name(self):
        self.assertEqual(DouYinBaseUploader.PLATFORM_NAME, "douyin")


class DouYinVideoUploadTests(unittest.TestCase):
    def test_upload_returns_success_dict(self):
        import asyncio
        uploader = DouYinVideo(
            title="t", file_path="/fake.mp4", tags=[], publish_date=0,
            account_file="/fake.json", desc="", publish_strategy=PublishStrategy.IMMEDIATE,
        )
        with patch.object(uploader, "validate_upload_args", AsyncMock()):
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def fake_session():
                class FakePage:
                    url = "https://creator.douyin.com"
                yield FakePage()

            with patch.object(uploader, "_browser_session", return_value=fake_session()), \
                 patch.object(DouYinVideo, "upload_video_content", AsyncMock()):
                result = asyncio.run(uploader.upload())
        self.assertTrue(result["success"])

    def test_upload_maps_restriction_to_account_issue(self):
        import asyncio
        uploader = DouYinVideo(
            title="t", file_path="/fake.mp4", tags=[], publish_date=0,
            account_file="/fake.json", desc="", publish_strategy=PublishStrategy.IMMEDIATE,
        )
        with patch.object(uploader, "validate_upload_args", AsyncMock()):
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def fake_session():
                class FakePage:
                    url = "https://creator.douyin.com"
                yield FakePage()

            with patch.object(uploader, "_browser_session", return_value=fake_session()), \
                 patch.object(DouYinVideo, "upload_video_content", AsyncMock(side_effect=DouyinPublishRestrictedError("限制"))):
                result = asyncio.run(uploader.upload())
        self.assertFalse(result["success"])
        self.assertTrue(result["account_issue"])
        self.assertEqual(result["issue_type"], "publish_restricted")

    def test_douyin_upload_note_is_alias_of_upload(self):
        uploader = DouYinNote(
            image_paths=[], note="n", tags=[], publish_date=0,
            account_file="/fake.json", title="t", publish_strategy=PublishStrategy.IMMEDIATE,
        )
        with patch.object(uploader, "upload", AsyncMock(return_value={"success": True, "message": "ok"})):
            import asyncio
            result = asyncio.run(uploader.douyin_upload_note())
        self.assertTrue(result["success"])


class ModuleWrapperTests(unittest.TestCase):
    def test_setup_signature_is_5_params(self):
        import inspect
        sig = inspect.signature(douyin_setup)
        params = list(sig.parameters.keys())
        self.assertEqual(params, ["account_file", "handle", "return_detail", "qrcode_callback", "headless"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_douyin_uploader_base.py -v`
Expected: FAIL

- [ ] **Step 3: Refactor `uploader/douyin_uploader/main.py`**

Apply same pattern as Task 2, plus:
- `DouYinBaseUploader` inherits `BaseBrowserUploader`, defines `PLATFORM_NAME = "douyin"`, `UPLOAD_URL = DOUYIN_UPLOAD_URL` (existing), `LOGIN_URL = DOUYIN_LOGIN_URL` (existing), `LOGIN_MARKERS = ["扫码登录", "手机号登录"]` (existing)
- **Rename instance method `validate_base_args(self)` to `validate_login_and_strategy(self)`** on `DouYinBaseUploader` (current line 340) - same collision fix as Task 2
- Update `DouYinVideo.validate_upload_args()` (line 505) and `DouYinNote.validate_upload_args()` (line 759) to call `self.validate_login_and_strategy()` instead of `self.validate_base_args()`
- Module-level `cookie_auth` / `douyin_setup` become thin wrappers with 5-param signature
- `DouYinVideo.upload(self) -> PlatformResultExtras` wraps `upload_video_content` in try/except, catches `DouyinPublishRestrictedError` and returns `{"success": False, "message": f"账号被限制发布: {exc.toast_text}", "account_issue": True, "issue_type": "publish_restricted"}`
- `DouYinNote.upload(self) -> PlatformResultExtras` same pattern, also keeps `douyin_upload_note()` as alias wrapper (`async def douyin_upload_note(self): return await self.upload()`)
- Add `main()` alias on `DouYinVideo`
- Use `_browser_session` context manager

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_douyin_uploader_base.py -v`
Expected: PASS

- [ ] **Step 5: Simplify `publish_to_douyin` in `publish/dispatch.py`**

Replace `publish/dispatch.py:61-119` with:

```python
async def publish_to_douyin(params: dict) -> dict:
    """发布到抖音"""
    from uploader.douyin_uploader.main import DouYinVideo, DouYinNote

    account_file = resolve_path(params["account_file"])
    title = truncate_title(params["title"], "douyin")

    if params["content_type"] == "video":
        params = {**params, "video_file": resolve_path(params["video_file"])}
    elif params.get("images"):
        params = {**params, "images": [resolve_path(img) for img in params["images"]]}

    err = DouYinVideo.validate_base_args(params)
    if err:
        return err

    try:
        if params["content_type"] == "video":
            uploader = DouYinVideo(
                title=title, file_path=params["video_file"], tags=params["tags"],
                publish_date=params["publish_time"] or 0, account_file=account_file,
                desc=params["desc"], publish_strategy=params["publish_strategy"],
            )
        else:
            uploader = DouYinNote(
                image_paths=params["images"], note=params["desc"], tags=params["tags"],
                publish_date=params["publish_time"] or 0, account_file=account_file,
                title=title, publish_strategy=params["publish_strategy"],
            )
        return await uploader.upload()
    except Exception as e:
        return {"success": False, "message": str(e)}
```

- [ ] **Step 6: Run regression suite**

Run: `python -m pytest tests/test_publish_engine.py tests/test_publish_dispatch.py tests/test_douyin_uploader_base.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add uploader/douyin_uploader/main.py publish/dispatch.py tests/test_douyin_uploader_base.py
git commit -m "refactor(douyin): migrate to BaseBrowserUploader, map DouyinPublishRestrictedError to account_issue"
```

---

## Task 7: 迁移 baijiahao(1-tier + @async_retry)

**Files:**
- Modify: `uploader/baijiahao_uploader/main.py`
- Modify: `publish/dispatch.py:283-329` (`publish_to_baijiahao`)
- Test: existing `tests/test_baijiahao_uploader.py` stays green

**Interfaces:**
- Consumes: Task 1 base classes
- Produces: `BaiJiaHaoVideo(BaseBrowserUploader)` (1-tier, no intermediate base), `upload()` returning `{"result_url": video_link}`, `@async_retry` preserved on `upload()`, `ai2video` method preserved, module-level wrappers

- [ ] **Step 1: Write failing test for baijiahao uploader structure**

Create `tests/test_baijiahao_uploader_base.py`:

```python
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from uploader.base_video import BaseBrowserUploader, PublishStrategy
from uploader.baijiahao_uploader.main import BaiJiaHaoVideo, cookie_auth, baijiahao_setup


class BaiJiaHaoVideoInheritanceTests(unittest.TestCase):
    def test_inherits_base_browser_uploader(self):
        self.assertTrue(issubclass(BaiJiaHaoVideo, BaseBrowserUploader))

    def test_platform_name(self):
        self.assertEqual(BaiJiaHaoVideo.PLATFORM_NAME, "baijiahao")


class BaiJiaHaoVideoUploadTests(unittest.TestCase):
    def test_upload_returns_unified_dict_with_url(self):
        import asyncio
        uploader = BaiJiaHaoVideo(
            title="t", file_path="/fake.mp4", tags=[], publish_date=0,
            account_file="/fake.json",
        )
        with patch.object(uploader, "validate_upload_args", AsyncMock()):
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def fake_session():
                class FakePage:
                    url = "https://baijiahao.baidu.com"
                yield FakePage()

            with patch.object(uploader, "_browser_session", return_value=fake_session()), \
                 patch.object(BaiJiaHaoVideo, "upload_video_content", AsyncMock(return_value="https://baijiahao.baidu.com/s?id=123")):
                result = asyncio.run(uploader.upload())
        self.assertTrue(result["success"])
        self.assertEqual(result["result_url"], "https://baijiahao.baidu.com/s?id=123")


class ModuleWrapperTests(unittest.TestCase):
    def test_setup_signature_is_5_params(self):
        import inspect
        sig = inspect.signature(baijiahao_setup)
        params = list(sig.parameters.keys())
        self.assertEqual(params, ["account_file", "handle", "return_detail", "qrcode_callback", "headless"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_baijiahao_uploader_base.py -v`
Expected: FAIL

- [ ] **Step 3: Refactor `uploader/baijiahao_uploader/main.py`**

Apply pattern:
- Import shared helpers from `uploader.base_video`
- Change `class BaiJiaHaoVideo(object):` to `class BaiJiaHaoVideo(BaseBrowserUploader):`
- Define `PLATFORM_NAME = "baijiahao"`, `UPLOAD_URL = BJH_UPLOAD_URL` (existing), `LOGIN_URL = BJH_LOGIN_URL` (existing), `LOGIN_MARKERS` (existing)
- Keep `@async_retry` decorator on `upload()` method
- Keep `ai2video` method (do NOT delete - sub-project D's scope)
- `upload(self) -> PlatformResultExtras` returns `{"success": True, "message": "发布成功", "result_url": video_link}`
- Add `publish_strategy` parameter to `__init__` (default `PublishStrategy.IMMEDIATE`, baijiahao is IMMEDIATE-only this spec - sub-project E handles scheduled bug)
- Module-level `cookie_auth` / `baijiahao_setup` become thin wrappers with 5-param signature
- Add `main()` alias wrapper
- Use `_browser_session` context manager

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_baijiahao_uploader_base.py tests/test_baijiahao_uploader.py -v`
Expected: PASS

- [ ] **Step 5: Simplify `publish_to_baijiahao` in `publish/dispatch.py`**

Replace `publish/dispatch.py:283-329` with:

```python
async def publish_to_baijiahao(params: dict) -> dict:
    """发布到百家号"""
    from uploader.baijiahao_uploader.main import BaiJiaHaoVideo
    from utils.excel_writer import write_video_link

    account_file = resolve_path(params["account_file"])
    title = truncate_title(params["title"], "baijiahao")

    if params["content_type"] == "video":
        params = {**params, "video_file": resolve_path(params["video_file"])}
    else:
        return {"success": False, "message": "百家号不支持图文发布，请使用 convert_to_video=true 转为视频发布"}

    err = BaiJiaHaoVideo.validate_base_args(params)
    if err:
        return err

    try:
        uploader = BaiJiaHaoVideo(
            title=title, file_path=params["video_file"], tags=params["tags"],
            publish_date=params["publish_time"] or 0, account_file=account_file,
        )
        result = await uploader.upload()
        if result["success"] and result.get("result_url"):
            try:
                write_result = write_video_link(result["result_url"])
                if write_result["success"]:
                    print(f"  📝 视频链接已写入 Excel: {result['result_url']}")
                else:
                    print(f"  ⚠️ 写入 Excel 失败: {write_result['message']}")
            except Exception as e:
                print(f"  ⚠️ 写入 Excel 异常: {e}")
        return result
    except Exception as e:
        return {"success": False, "message": str(e)}
```

- [ ] **Step 6: Run regression suite**

Run: `python -m pytest tests/test_publish_engine.py tests/test_publish_dispatch.py tests/test_baijiahao_uploader.py tests/test_baijiahao_uploader_base.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add uploader/baijiahao_uploader/main.py publish/dispatch.py tests/test_baijiahao_uploader_base.py
git commit -m "refactor(baijiahao): migrate to BaseBrowserUploader, preserve @async_retry and ai2video"
```

---

## Task 8: 加 BaseCliUploader 用法 + 迁移 bilibili

**Files:**
- Modify: `uploader/bilibili_uploader/main.py`
- Modify: `publish/dispatch.py:332-359` (`publish_to_bilibili`)
- Test: existing `tests/test_bilibili_runtime.py` stays green

**Interfaces:**
- Consumes: Task 1 `BaseCliUploader`
- Produces: `BilibiliUploader(BaseCliUploader)` with `upload()` returning `PlatformResultExtras`, module-level `cookie_auth`/`bilibili_setup` as classmethod wrappers

- [ ] **Step 1: Write failing test for bilibili uploader structure**

Create `tests/test_bilibili_uploader_base.py`:

```python
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from uploader.base_video import BaseCliUploader
from uploader.bilibili_uploader.main import BilibiliUploader, cookie_auth, bilibili_setup


class BilibiliUploaderInheritanceTests(unittest.TestCase):
    def test_inherits_base_cli_uploader(self):
        self.assertTrue(issubclass(BilibiliUploader, BaseCliUploader))


class ModuleWrapperTests(unittest.TestCase):
    def test_setup_signature_is_5_params(self):
        import inspect
        sig = inspect.signature(bilibili_setup)
        params = list(sig.parameters.keys())
        self.assertEqual(params, ["account_file", "handle", "return_detail", "qrcode_callback", "headless"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_bilibili_uploader_base.py -v`
Expected: FAIL (`BilibiliUploader` class doesn't exist)

- [ ] **Step 3: Refactor `uploader/bilibili_uploader/main.py`**

Wrap the existing `upload()` function in a `BilibiliUploader(BaseCliUploader)` class. The existing module-level functions (`bilibili_cookie_gen`, `cookie_auth`, `bilibili_setup`, `upload`) have real logic (lines 18-90 of current file) - adapt them into classmethods. Keep `run_biliup_command` import from `uploader.bilibili_uploader.runtime`.

```python
# -*- coding: utf-8 -*-
"""B站上传器 - 基于 biliup CLI (wrapped in BilibiliUploader class)"""
import os
from pathlib import Path

from uploader.base_video import BaseCliUploader, PlatformResultExtras, PublishStrategy
from uploader.bilibili_uploader.runtime import run_biliup_command
from utils.log import bilibili_logger

DEFAULT_TID = 171


class BilibiliUploader(BaseCliUploader):
    """B 站上传器(走 biliup CLI subprocess)"""

    def __init__(
        self,
        title: str,
        file_path: str,
        tags: list,
        account_file: str,
        desc: str = "",
        publish_strategy: PublishStrategy = PublishStrategy.IMMEDIATE,
        tid: int = DEFAULT_TID,
    ):
        self.title = title
        self.file_path = file_path
        self.tags = tags if tags is not None else []
        self.account_file = account_file
        self.desc = desc
        self.publish_strategy = publish_strategy
        self.tid = tid

    @classmethod
    async def cookie_auth(cls, account_file: str) -> bool:
        """用 biliup renew 验证 cookie 是否有效。"""
        if not os.path.exists(account_file):
            return False
        result = run_biliup_command(["-u", account_file, "renew"])
        if result.returncode == 0:
            bilibili_logger.success("[+] cookie 有效")
            return True
        stderr = (result.stderr or "").strip()
        bilibili_logger.error(f"cookie 失效: {stderr[:200]}")
        return False

    @classmethod
    async def cookie_gen(cls, account_file: str) -> bool:
        """交互式扫码登录 B站, 保存 biliup 格式 cookie。"""
        bilibili_logger.info(f"启动 biliup 登录, cookie 将保存到: {account_file}")
        Path(account_file).parent.mkdir(parents=True, exist_ok=True)
        result = run_biliup_command(["-u", account_file, "login"], interactive=True)
        if result.returncode == 0 and os.path.exists(account_file):
            bilibili_logger.success("biliup 登录成功, cookie 已保存")
            return True
        bilibili_logger.error(f"biliup 登录失败, returncode={result.returncode}")
        return False

    @classmethod
    async def setup(
        cls,
        account_file: str,
        handle: bool = False,
        return_detail: bool = False,
        qrcode_callback=None,
        headless: bool = True,
    ):
        """5-param signature for dispatch compatibility. qrcode_callback/headless ignored (CLI)."""
        if not os.path.exists(account_file) or not await cls.cookie_auth(account_file):
            if not handle:
                return False
            bilibili_logger.error("cookie 不存在或已失效, 即将启动 biliup 登录, 请扫码")
            return await cls.cookie_gen(account_file)
        return True

    async def upload(self) -> PlatformResultExtras:
        """用 biliup 上传视频到 B站。"""
        tag_str = ",".join(self.tags) if isinstance(self.tags, list) else str(self.tags)
        if not os.path.exists(self.file_path):
            return {"success": False, "message": f"视频文件不存在: {self.file_path}"}

        args = [
            "-u", self.account_file,
            "upload",
            self.file_path,
            "--title", self.title,
            "--desc", self.desc or "",
            "--tag", tag_str,
            "--tid", str(self.tid),
        ]
        bilibili_logger.info(f"biliup 上传: {self.file_path}, title={self.title}, tid={self.tid}")
        result = run_biliup_command(args)
        stdout = result.stdout or ""
        stderr = result.stderr or ""

        if result.returncode == 0:
            bilibili_logger.success(f"biliup 上传成功: {stdout.strip()[:300]}")
            return {"success": True, "message": "发布成功"}
        bilibili_logger.error(f"biliup 上传失败: {stderr.strip()[:300]}")
        return {"success": False, "message": f"biliup 上传失败: {stderr.strip()[:200]}"}


# Module-level wrappers for dispatch.py compatibility
async def cookie_auth(account_file):
    return await BilibiliUploader.cookie_auth(account_file)

async def bilibili_setup(account_file, handle=False, return_detail=False, qrcode_callback=None, headless=True):
    return await BilibiliUploader.setup(account_file, handle, return_detail, qrcode_callback, headless)
```

Note: `headless` defaults to `True` for bilibili (CLI, no browser). The existing `bilibili_setup` had 2-param signature `(account_file, handle=False)` - the new wrapper accepts all 5 params but ignores `return_detail`/`qrcode_callback`/`headless`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_bilibili_uploader_base.py tests/test_bilibili_runtime.py -v`
Expected: PASS

- [ ] **Step 5: Simplify `publish_to_bilibili` in `publish/dispatch.py`**

Replace `publish/dispatch.py:332-359` with:

```python
async def publish_to_bilibili(params: dict) -> dict:
    """发布到 B站 (via biliup CLI)"""
    from uploader.bilibili_uploader.main import BilibiliUploader

    account_file = resolve_path(params["account_file"])
    title = truncate_title(params["title"], "bilibili")

    if params["content_type"] != "video":
        return {"success": False, "message": "B站暂只支持视频发布"}

    params = {**params, "video_file": resolve_path(params["video_file"])}

    err = BilibiliUploader.validate_base_args(params)
    if err:
        return err

    try:
        uploader = BilibiliUploader(
            title=title, file_path=params["video_file"], tags=params["tags"],
            account_file=account_file, desc=params["desc"],
            publish_strategy=params["publish_strategy"],
        )
        return await uploader.upload()
    except Exception as e:
        return {"success": False, "message": str(e)}
```

- [ ] **Step 6: Run regression suite**

Run: `python -m pytest tests/test_publish_engine.py tests/test_publish_dispatch.py tests/test_bilibili_uploader_base.py tests/test_bilibili_runtime.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add uploader/bilibili_uploader/main.py publish/dispatch.py tests/test_bilibili_uploader_base.py
git commit -m "refactor(bilibili): wrap upload function in BilibiliUploader(BaseCliUploader)"
```

---

## Task 9: 迁移 tk + 删 `BaseVideoUploader` 别名 + dispatch 最终清理

**Files:**
- Modify: `uploader/tk_uploader/main.py` (rewrite)
- Modify: `publish/dispatch.py` (add `publish_to_tk`, remove "tk 暂未实现" branch)
- Modify: `publish/constants.py` (add `"tk": 2200` to `TITLE_LIMITS`)
- Modify: `uploader/base_video.py` (delete `BaseVideoUploader = BasePlatformUploader` alias)
- Modify: 5 `*BaseUploader` imports (change `BaseVideoUploader` to `BasePlatformUploader`)
- Modify: 5 platform Video/Note classes (delete `main()` and `douyin_upload_note()` aliases)
- Modify: `tests/test_publish_dispatch.py` (add tk coverage)
- Create: `tests/test_tk_migration.py`

**Interfaces:**
- Consumes: Task 1-8 (all platforms migrated)
- Produces: `TiktokVideo(BaseBrowserUploader)` with `cookie_gen` override, tk in dispatch tables, no `BaseVideoUploader` alias, no `main()` aliases

- [ ] **Step 1: Write failing test for tk migration**

Create `tests/test_tk_migration.py`:

```python
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from uploader.base_video import BaseBrowserUploader, PublishStrategy
from uploader.tk_uploader.main import TiktokVideo, cookie_auth, tiktok_setup
from publish.dispatch import _PLATFORM_LOGIN, _PUBLISH_DISPATCH


class TiktokVideoInheritanceTests(unittest.TestCase):
    def test_inherits_base_browser_uploader(self):
        self.assertTrue(issubclass(TiktokVideo, BaseBrowserUploader))

    def test_platform_name(self):
        self.assertEqual(TiktokVideo.PLATFORM_NAME, "tk")

    def test_upload_url(self):
        self.assertTrue(TiktokVideo.UPLOAD_URL.startswith("https://"))

    def test_login_url(self):
        self.assertTrue(TiktokVideo.LOGIN_URL.startswith("https://"))

    def test_login_markers_nonempty(self):
        self.assertGreater(len(TiktokVideo.LOGIN_MARKERS), 0)


class TiktokCookieGenOverrideTests(unittest.TestCase):
    def test_cookie_gen_uses_page_pause(self):
        """tk overrides cookie_gen to use page.pause (manual login), not QR template."""
        # Verify cookie_gen is defined on TiktokVideo itself (not inherited)
        self.assertIn("cookie_gen", TiktokVideo.__dict__)


class DispatchRegistryTests(unittest.TestCase):
    def test_tk_in_platform_login(self):
        self.assertIn("tk", _PLATFORM_LOGIN)

    def test_tk_in_publish_dispatch(self):
        self.assertIn("tk", _PUBLISH_DISPATCH)

    def test_tk_login_entry_is_three_tuple(self):
        entry = _PLATFORM_LOGIN["tk"]
        self.assertEqual(len(entry), 3)
        module_path, check_name, setup_name = entry
        self.assertTrue(module_path.startswith("uploader."))
        self.assertEqual(check_name, "cookie_auth")
        self.assertEqual(setup_name, "tiktok_setup")


class TiktokVideoUploadTests(unittest.TestCase):
    def test_upload_returns_unified_dict(self):
        import asyncio
        uploader = TiktokVideo(
            title="t", file_path="/fake.mp4", tags=[], publish_date=0,
            account_file="/fake.json", publish_strategy=PublishStrategy.IMMEDIATE,
        )
        with patch.object(uploader, "validate_upload_args", AsyncMock()):
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def fake_session():
                class FakePage:
                    url = "https://www.tiktok.com/tiktokstudio/upload"
                yield FakePage()

            with patch.object(uploader, "_browser_session", return_value=fake_session()), \
                 patch.object(TiktokVideo, "upload_video_content", AsyncMock()):
                result = asyncio.run(uploader.upload())
        self.assertTrue(result["success"])


class ModuleWrapperTests(unittest.TestCase):
    def test_setup_signature_is_5_params(self):
        import inspect
        sig = inspect.signature(tiktok_setup)
        params = list(sig.parameters.keys())
        self.assertEqual(params, ["account_file", "handle", "return_detail", "qrcode_callback", "headless"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tk_migration.py -v`
Expected: FAIL (`TiktokVideo` doesn't inherit `BaseBrowserUploader` yet, tk not in dispatch tables)

- [ ] **Step 3: Rewrite `uploader/tk_uploader/main.py`**

Replace the entire file with:

```python
# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import os
from datetime import datetime

from patchright.async_api import Page, Playwright, async_playwright

from conf import LOCAL_CHROME_HEADLESS
from uploader.base_video import (
    BaseBrowserUploader,
    PlatformResultExtras,
    PublishStrategy,
    _build_launch_kwargs,
    _msg,
)
from uploader.tk_uploader.tk_config import Tk_Locator
from utils.base_social_media import set_init_script
from utils.log import tiktok_logger


class TiktokVideo(BaseBrowserUploader):
    """TikTok 视频上传器 - chromium + patchright"""

    PLATFORM_NAME = "tk"
    UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"
    LOGIN_URL = "https://www.tiktok.com/login?lang=en"
    LOGIN_MARKERS = ["/login", "/signup"]
    PUBLISH_MARKERS = []

    def __init__(
        self,
        title: str,
        file_path: str,
        tags: list,
        publish_date,
        account_file: str,
        publish_strategy: PublishStrategy = PublishStrategy.IMMEDIATE,
        desc: str = "",
        headless: bool = LOCAL_CHROME_HEADLESS,
    ):
        self.title = title
        self.file_path = file_path
        self.tags = tags or []
        self.publish_date = publish_date
        self.account_file = account_file
        self.publish_strategy = publish_strategy
        self.desc = desc
        self.headless = headless
        self.locator_base = None

    @classmethod
    async def is_login_completed(cls, page: Page) -> bool:
        return await _is_tiktok_auth_page_valid(page)

    @classmethod
    async def cookie_gen(
        cls,
        account_file: str,
        qrcode_callback=None,
        headless: bool = LOCAL_CHROME_HEADLESS,
        return_detail: bool = False,
    ):
        """tk 用 page.pause 手动登录,qrcode_callback 被忽略。"""
        from pathlib import Path
        Path(account_file).parent.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as playwright:
            browser = await cls._launch_browser(playwright, headless)
            context = await cls._init_context(browser, None)
            try:
                page = await context.new_page()
                await page.goto(cls.LOGIN_URL)
                tiktok_logger.info(_msg("🧭", "请在打开的浏览器中手动登录 TikTok,登录完成后在调试器中点继续"))
                await page.pause()
                await context.storage_state(path=account_file)
                return {"success": True, "status": "success", "message": "TikTok 手动登录完成", "account_file": account_file, "qrcode": None, "current_url": page.url}
            finally:
                await context.close()
                await browser.close()

    async def upload(self) -> PlatformResultExtras:
        """主入口"""
        async with self._browser_session() as page:
            await page.goto("https://www.tiktok.com/creator-center/upload")
            tiktok_logger.info(_msg("🏃", f"Uploading-------{self.title}.mp4"))

            try:
                await page.wait_for_url("https://www.tiktok.com/tiktokstudio/upload", timeout=10000)
            except Exception:
                pass

            try:
                await page.wait_for_selector('iframe[data-tt="Upload_index_iframe"], div.upload-container', timeout=10000)
            except Exception:
                tiktok_logger.error("Neither iframe nor div appeared within the timeout.")

            await self.choose_base_locator(page)

            upload_button = self.locator_base.locator('button:has-text("Select video"):visible')
            await upload_button.wait_for(state="visible")

            async with page.expect_file_chooser() as fc_info:
                await upload_button.click()
            file_chooser = await fc_info.value
            await file_chooser.set_files(self.file_path)

            await self.add_title_tags(page)
            await self.detect_upload_status(page)

            if self.publish_strategy == PublishStrategy.SCHEDULED and self.publish_date != 0:
                await self.set_schedule_time(page, self.publish_date)

            await self.click_publish(page)

            return {"success": True, "message": "发布成功"}

    async def main(self) -> dict:
        """别名 wrapper - Task 9 删"""
        return await self.upload()

    # Platform-specific helpers - copy exact bodies verbatim from original
    # uploader/tk_uploader/main.py (lines 110-289). Replace `playwright` import
    # with `patchright` if referenced, and use self._browser_session's page.
    # Do NOT leave these as stubs - copy the real implementation.
    async def set_schedule_time(self, page, publish_date):
        ...  # copy from original TiktokVideo.set_schedule_time

    async def handle_upload_error(self, page):
        ...  # copy from original TiktokVideo.handle_upload_error

    async def add_title_tags(self, page):
        ...  # copy from original TiktokVideo.add_title_tags

    async def click_publish(self, page):
        ...  # copy from original TiktokVideo.click_publish

    async def detect_upload_status(self, page):
        ...  # copy from original TiktokVideo.detect_upload_status

    async def choose_base_locator(self, page):
        ...  # copy from original TiktokVideo.choose_base_locator


async def _is_tiktok_auth_page_valid(page: Page) -> bool:
    """tk 登录页检测 - 保留原逻辑"""
    current_url = (page.url or "").lower()
    if any(marker in current_url for marker in TiktokVideo.LOGIN_MARKERS):
        return False

    login_markers = [
        page.locator('select[class*="SelectFormContainer"]').first,
        page.locator('a[href*="/login"]').first,
    ]
    for marker in login_markers:
        if await _is_tiktok_locator_visible(marker):
            return False

    upload_markers = [
        page.locator('button:has-text("Select video")').first,
        page.locator('button[aria-label="Select file"]').first,
        page.locator("div.upload-container").first,
    ]
    return any([await _is_tiktok_locator_visible(marker) for marker in upload_markers])


async def _is_tiktok_locator_visible(locator) -> bool:
    try:
        if not await locator.count():
            return False
        return await locator.is_visible()
    except Exception:
        return False


# Module-level wrappers for dispatch.py compatibility
async def cookie_auth(account_file):
    return await TiktokVideo.cookie_auth(account_file)

async def tiktok_setup(account_file, handle=False, return_detail=False, qrcode_callback=None, headless=LOCAL_CHROME_HEADLESS):
    return await TiktokVideo.setup(account_file, handle, return_detail, qrcode_callback, headless)
```

When copying the platform-specific helpers (`set_schedule_time`, `handle_upload_error`, `add_title_tags`, `click_publish`, `detect_upload_status`, `choose_base_locator`), copy the exact bodies from the original `uploader/tk_uploader/main.py` lines 110-289. The `_browser_session` context manager replaces the manual `browser.close()` / `context.close()` / `context.storage_state()` calls at the end of the original `upload` method.

- [ ] **Step 4: Add tk to dispatch tables**

In `publish/dispatch.py`, add to `_PLATFORM_LOGIN` (after the weibo entry):

```python
    "tk":          ("uploader.tk_uploader.main",          "cookie_auth", "tiktok_setup"),
```

Add `publish_to_tk` function (before `_PUBLISH_DISPATCH`):

```python
async def publish_to_tk(params: dict) -> dict:
    """发布到 TikTok"""
    from uploader.tk_uploader.main import TiktokVideo

    account_file = resolve_path(params["account_file"])
    title = truncate_title(params["title"], "tk")

    if params["content_type"] != "video":
        return {"success": False, "message": "TikTok 暂只支持视频发布"}

    params = {**params, "video_file": resolve_path(params["video_file"])}

    err = TiktokVideo.validate_base_args(params)
    if err:
        return err

    try:
        uploader = TiktokVideo(
            title=title, file_path=params["video_file"], tags=params["tags"],
            publish_date=params["publish_time"] or 0, account_file=account_file,
            desc=params.get("desc", ""), publish_strategy=params["publish_strategy"],
        )
        return await uploader.upload()
    except Exception as e:
        return {"success": False, "message": str(e)}
```

Add to `_PUBLISH_DISPATCH`:

```python
    "tk":         publish_to_tk,
```

Replace `publish_to_platform` (currently lines 442-449) with:

```python
async def publish_to_platform(platform: str, params: dict) -> dict:
    """发布到指定平台"""
    handler = _PUBLISH_DISPATCH.get(platform)
    if handler is not None:
        return await handler(params)
    return {"success": False, "message": f"未知平台: {platform}"}
```

(The `if platform == "tk"` branch is removed - tk now goes through the dispatch dict.)

- [ ] **Step 5: Add tk to `TITLE_LIMITS` in `publish/constants.py`**

Find the `TITLE_LIMITS` dict in `publish/constants.py` and add:

```python
    "tk": 2200,
```

Verify `PLATFORM_NAMES["tk"]` exists (it should already - if not, add `"tk": "TikTok"`).

- [ ] **Step 6: Delete `BaseVideoUploader` alias in `uploader/base_video.py`**

Remove the line:

```python
# Backward-compat alias (Task 9 deletes this)
BaseVideoUploader = BasePlatformUploader
```

- [ ] **Step 7: Update 5 `*BaseUploader` imports**

In each of these files, change `from uploader.base_video import BaseVideoUploader` to `from uploader.base_video import BasePlatformUploader`, and change the class declaration from `class XBaseUploader(BaseVideoUploader)` to `class XBaseUploader(BasePlatformUploader)`:

- `uploader/douyin_uploader/main.py`
- `uploader/xiaohongshu_uploader/main.py`
- `uploader/ks_uploader/main.py`
- `uploader/tencent_uploader/main.py`
- `uploader/weibo_uploader/main.py`

- [ ] **Step 8: Delete `main()` and `douyin_upload_note()` aliases**

In each of these files, delete the `main()` alias method (and `douyin_upload_note()` on `DouYinNote`):

- `uploader/douyin_uploader/main.py` - delete `async def main(self): return await self.upload()` on `DouYinVideo`, delete `async def douyin_upload_note(self): return await self.upload()` on `DouYinNote`
- `uploader/xiaohongshu_uploader/main.py` - delete `main()` on `XiaoHongShuVideo` and `XiaoHongShuNote`
- `uploader/ks_uploader/main.py` - delete `main()` on `KSVideo` and `KSNote`
- `uploader/tencent_uploader/main.py` - delete `main()` on `TencentVideo`
- `uploader/weibo_uploader/main.py` - delete `main()` on `WeiboVideo` and `WeiboNote`
- `uploader/baijiahao_uploader/main.py` - delete `main()` on `BaiJiaHaoVideo`
- `uploader/tk_uploader/main.py` - delete `main()` on `TiktokVideo`

- [ ] **Step 9: Update `tests/test_publish_dispatch.py` to include tk**

In `tests/test_publish_dispatch.py`, update the registry coverage test:

```python
class PlatformLoginRegistryTests(unittest.TestCase):
    def test_registry_covers_all_platforms(self):
        expected = {"douyin", "xiaohongshu", "kuaishou", "tencent", "baijiahao", "bilibili", "weibo", "tk"}
        self.assertEqual(set(_PLATFORM_LOGIN.keys()), expected)

    def test_platform_requires_account_login_includes_tk(self):
        self.assertTrue(platform_requires_account_login("tk"))
```

And add a test for `_PUBLISH_DISPATCH` covering tk:

```python
class PublishDispatchRegistryTests(unittest.TestCase):
    def test_dispatch_covers_all_platforms(self):
        from publish.dispatch import _PUBLISH_DISPATCH
        expected = {"douyin", "xiaohongshu", "kuaishou", "tencent", "baijiahao", "bilibili", "weibo", "tk"}
        self.assertEqual(set(_PUBLISH_DISPATCH.keys()), expected)
```

- [ ] **Step 10: Run tk migration test to verify it passes**

Run: `python -m pytest tests/test_tk_migration.py -v`
Expected: PASS

- [ ] **Step 11: Run full regression suite**

Run: `python -m pytest tests/ -v`
Expected: PASS (all tests green)

- [ ] **Step 12: Verify dispatch extraction cleanup**

Run: `grep -n "share_link\|video_link\|note_id\|video_id" publish/dispatch.py`
Expected: no output (all extraction moved to uploaders)

- [ ] **Step 13: Verify all platforms use patchright**

Run: `grep -rn "from playwright.async_api" uploader/`
Expected: no output (all platforms now use patchright)

- [ ] **Step 14: Verify BaseVideoUploader alias is gone**

Run: `grep -rn "BaseVideoUploader" uploader/`
Expected: no output (alias deleted, all references renamed to `BasePlatformUploader`)

- [ ] **Step 15: Verify CLI help works**

Run: `python publish_all.py --help`
Expected: displays argparse help without errors

- [ ] **Step 16: Manual smoke test (if tk network available)**

If TikTok network is accessible, configure tk account and run `python publish_all.py --platforms tk --video <test.mp4> --title "test"`. If network not available, document and skip.

- [ ] **Step 17: Commit**

```bash
git add uploader/tk_uploader/main.py uploader/base_video.py publish/dispatch.py publish/constants.py uploader/douyin_uploader/main.py uploader/xiaohongshu_uploader/main.py uploader/ks_uploader/main.py uploader/tencent_uploader/main.py uploader/weibo_uploader/main.py uploader/baijiahao_uploader/main.py tests/test_tk_migration.py tests/test_publish_dispatch.py
git commit -m "feat(tk): migrate to chromium+patchright and BaseBrowserUploader, wire into dispatch; delete BaseVideoUploader alias and main() aliases

BREAKING: myUtils/postVideo.py app.main() / app.douyin_upload_note() calls need sub-project C to sync migrate to upload()."
```

---

## 验证标准

每个 task 结束后:
- `pytest tests/` 全绿(`test_publish_engine.py` 16 用例是核心回归网)
- 该 task 涉及的平台 manual smoke test 一次真实发布(tk 视环境)
- diff 只动该 task 声明的文件,不溢出

最终(Task 9 完成后):
- `pytest tests/` 全绿
- `python publish_all.py --help` 正常显示
- `grep -rn "share_link\|video_link\|note_id\|video_id" publish/dispatch.py` 返回空
- `grep -rn "from playwright.async_api" uploader/` 返回空
- `grep -rn "BaseVideoUploader" uploader/` 返回空
- 8 个平台 manual smoke test 各一次(tk 视环境)
