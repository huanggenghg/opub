"""无头发布会话的扫码登录必须弹可见窗口(方案 C)。

回归背景:统一登录进发布会话后,无头会话里的扫码在看不见的浏览器里
等 300 秒;Agent 调用时用户既看不到窗口也看不到实时终端输出,只能
在最终汇总里被告知要登录(AUTH-001 超时)。契约:
- 无头会话需要登录 → 单独弹一个有头浏览器完成扫码 → 立刻带新 cookie
  重启无头会话继续上传(tencent 登录 session 数秒内衰减,重启紧跟扫码);
- cookie 有效的无头快路径与有头发布(--no-headless)行为不变。
"""
import asyncio
import time
from contextlib import ExitStack, asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from publish.auth import LoginCheckError, LoginTimeoutError
from uploader.base_video import BaseBrowserUploader


class HandoffUploader(BaseBrowserUploader):
    PLATFORM_NAME = "fake"
    UPLOAD_URL = "https://example.test/upload"
    LOGIN_URL = "https://example.test/login"
    LOGIN_MARKERS = ["/login"]

    def __init__(self, account_file, headless=True):
        self.account_file = str(account_file)
        self.headless = headless


class FakePage:
    """URL 假页:login=True 时上传页跳登录页;显式到登录页后的等待模拟扫码完成。"""

    def __init__(self, login=False, completed=True):
        self.url = "about:blank"
        self.login = login
        self.completed = completed
        self.visits = []
        self._on_login_page = False
        self.context = SimpleNamespace(storage_state=AsyncMock())

    async def goto(self, url, **kwargs):
        self.visits.append(url)
        self._on_login_page = url == HandoffUploader.LOGIN_URL
        self.url = HandoffUploader.LOGIN_URL if self.login else url
        if url == HandoffUploader.LOGIN_URL:
            self.url = url

    async def wait_for_timeout(self, *args, **kwargs):
        if self.login and self.completed and self._on_login_page:
            self.login = False
            self.url = "https://example.test/home"
            self._on_login_page = False


class SessionStack:
    """按会话顺序供给 page 的 fake 浏览器栈,记录 launch 的 headless 标志。"""

    def __init__(self, pages):
        self.pages = list(pages)
        self.launches = []
        self.browsers = []
        self.contexts = []

    def patches(self, uploader):
        @asynccontextmanager
        async def driver():
            yield object()

        async def launch(playwright, headless):
            self.launches.append(headless)
            browser = SimpleNamespace(close=AsyncMock())
            self.browsers.append(browser)
            return browser

        def init_context(browser, account_file=None):
            page = self.pages[len(self.contexts)]
            context = SimpleNamespace(
                new_page=AsyncMock(return_value=page),
                close=AsyncMock(),
                storage_state=AsyncMock(),
            )
            self.contexts.append(context)
            return context

        return (
            patch("uploader.base_video.async_playwright", driver),
            patch.object(uploader, "_launch_browser", AsyncMock(side_effect=launch)),
            patch.object(uploader, "_init_context", AsyncMock(side_effect=init_context)),
        )


def run_session(uploader, stack, handed_off=None):
    async def run():
        with ExitStack() as stack_ctx:
            for patcher in stack.patches(uploader):
                stack_ctx.enter_context(patcher)
            if handed_off is not None:
                stack_ctx.enter_context(
                    patch.object(uploader, "_headed_qr_login", handed_off, create=True)
                )
            async with uploader._browser_session() as page:
                return page

    return asyncio.run(run())


def test_headless_expired_login_hands_off_to_headed_window_then_relaunches(tmp_path):
    uploader = HandoffUploader(tmp_path / "cookie.json", headless=True)
    stack = SessionStack([FakePage(login=True), FakePage(login=False)])
    handed_off = AsyncMock()

    page = run_session(uploader, stack, handed_off)

    handed_off.assert_awaited_once()
    assert stack.launches == [True, True]  # 发布始终无头,登录窗另算
    assert page is stack.pages[1]  # 上传发生在带新 cookie 的重启会话
    assert all(browser.close.await_count == 1 for browser in stack.browsers)
    assert all(context.close.await_count == 1 for context in stack.contexts)
    stack.contexts[0].storage_state.assert_not_awaited()  # 失效会话不落盘
    stack.contexts[1].storage_state.assert_awaited_once_with(path=uploader.account_file)


def test_headless_valid_login_stays_single_headless_session(tmp_path):
    uploader = HandoffUploader(tmp_path / "cookie.json", headless=True)
    stack = SessionStack([FakePage(login=False)])
    handed_off = AsyncMock()

    page = run_session(uploader, stack, handed_off)

    handed_off.assert_not_awaited()
    assert stack.launches == [True]
    assert page is stack.pages[0]
    assert len(stack.browsers) == 1


def test_headed_publish_session_scans_in_same_window(tmp_path):
    uploader = HandoffUploader(tmp_path / "cookie.json", headless=False)
    stack = SessionStack([FakePage(login=True)])
    handed_off = AsyncMock()

    page = run_session(uploader, stack, handed_off)

    handed_off.assert_not_awaited()
    assert stack.launches == [False]
    assert page is stack.pages[0]
    assert page.visits == [uploader.UPLOAD_URL, uploader.LOGIN_URL, uploader.UPLOAD_URL]


def test_headless_relaunch_still_expired_fails_after_single_handoff(tmp_path):
    uploader = HandoffUploader(tmp_path / "cookie.json", headless=True)
    stack = SessionStack([FakePage(login=True), FakePage(login=True)])
    handed_off = AsyncMock()

    with pytest.raises(LoginTimeoutError) as caught:
        run_session(uploader, stack, handed_off)

    assert "仍需登录" in str(caught.value)
    assert handed_off.await_count == 1  # 不做第二次交接
    assert stack.launches == [True, True]
    assert all(browser.close.await_count == 1 for browser in stack.browsers)
    assert all(context.close.await_count == 1 for context in stack.contexts)


def test_headed_qr_login_opens_visible_window_and_saves_state(tmp_path):
    uploader = HandoffUploader(tmp_path / "new" / "cookie.json", headless=True)
    page = FakePage(login=True)
    context = SimpleNamespace(
        new_page=AsyncMock(return_value=page),
        close=AsyncMock(),
        storage_state=AsyncMock(),
    )
    page.context = context
    browser = SimpleNamespace(close=AsyncMock())
    launches = []

    async def launch(playwright, headless):
        launches.append(headless)
        return browser

    @asynccontextmanager
    async def driver():
        yield object()

    init = AsyncMock(return_value=context)
    with patch("uploader.base_video.async_playwright", driver), patch.object(
        uploader, "_launch_browser", AsyncMock(side_effect=launch)
    ), patch.object(uploader, "_init_context", init):
        asyncio.run(uploader._headed_qr_login())

    assert launches == [False]  # 可见窗口
    init.assert_awaited_once_with(browser, None)  # 全新 context,不带失效 cookie
    context.storage_state.assert_awaited_once_with(path=uploader.account_file)
    assert (tmp_path / "new").is_dir()
    context.close.assert_awaited_once()
    browser.close.assert_awaited_once()


def test_headed_login_timeout_fails_publish_and_closes_headless_session(tmp_path):
    uploader = HandoffUploader(tmp_path / "cookie.json", headless=True)
    stack = SessionStack([FakePage(login=True)])
    handed_off = AsyncMock(side_effect=LoginTimeoutError("fake扫码登录超时或中断"))

    with pytest.raises(LoginTimeoutError):
        run_session(uploader, stack, handed_off)

    stack.browsers[0].close.assert_awaited_once()
    stack.contexts[0].close.assert_awaited_once()
    stack.contexts[0].storage_state.assert_not_awaited()


def test_headed_login_close_timeout_does_not_block(tmp_path, monkeypatch):
    """有头 Chrome 登录后偶发数分钟不退出;关闭限时,超时放弃等待。

    残留进程由 playwright 驱动退出时的强杀兜底(实测 ~2.4s、无残留)。
    """
    from uploader import base_video

    monkeypatch.setattr(base_video, "_BROWSER_CLOSE_TIMEOUT", 0.05)
    uploader = HandoffUploader(tmp_path / "new" / "cookie.json", headless=True)
    page = FakePage(login=True)
    context = SimpleNamespace(
        new_page=AsyncMock(return_value=page),
        close=AsyncMock(),
        storage_state=AsyncMock(),
    )
    page.context = context
    launches = []

    async def launch(playwright, headless):
        launches.append(headless)

        async def hanging_close():
            await asyncio.Event().wait()

        return SimpleNamespace(close=hanging_close)

    @asynccontextmanager
    async def driver():
        yield object()

    async def run():
        with patch("uploader.base_video.async_playwright", driver), patch.object(
            uploader, "_launch_browser", AsyncMock(side_effect=launch)
        ), patch.object(uploader, "_init_context", AsyncMock(return_value=context)):
            await uploader._headed_qr_login()

    started = time.monotonic()
    asyncio.run(run())
    assert time.monotonic() - started < 5  # 未被挂起的 close 拖住
    context.storage_state.assert_awaited_once_with(path=uploader.account_file)
    context.close.assert_awaited_once()
    assert launches == [False]


def test_abandoned_close_late_exception_is_consumed(tmp_path, monkeypatch):
    """超时放弃的 close 迟到抛错(驱动强杀残留浏览器后),由回调消化,不外泄。"""
    from uploader import base_video

    monkeypatch.setattr(base_video, "_BROWSER_CLOSE_TIMEOUT", 0.05)
    uploader = HandoffUploader(tmp_path / "new" / "cookie.json", headless=True)
    page = FakePage(login=True)
    context = SimpleNamespace(
        new_page=AsyncMock(return_value=page),
        close=AsyncMock(),
        storage_state=AsyncMock(),
    )
    page.context = context

    async def late_raise_close():
        await asyncio.sleep(0.2)
        raise RuntimeError("Target page, context or browser has been closed")

    @asynccontextmanager
    async def driver():
        yield object()

    async def run():
        with patch("uploader.base_video.async_playwright", driver), patch.object(
            uploader, "_launch_browser", AsyncMock(return_value=SimpleNamespace(close=late_raise_close))
        ), patch.object(uploader, "_init_context", AsyncMock(return_value=context)):
            await uploader._headed_qr_login()

    started = time.monotonic()
    asyncio.run(run())
    assert time.monotonic() - started < 5
    context.storage_state.assert_awaited_once_with(path=uploader.account_file)


def test_headless_relaunch_not_blocked_by_hanging_headed_close(tmp_path, monkeypatch):
    """扫码落盘后无头重启不等有头浏览器退出;上传页在新会话就绪。"""
    from uploader import base_video

    monkeypatch.setattr(base_video, "_BROWSER_CLOSE_TIMEOUT", 0.05)
    uploader = HandoffUploader(tmp_path / "cookie.json", headless=True)
    # 顺序:无头探测(未登录) → 有头扫码页(完成登录) → 无头重启(已登录)
    pages = [FakePage(login=True), FakePage(login=True), FakePage(login=False)]
    launches = []
    browsers = []

    @asynccontextmanager
    async def driver():
        yield object()

    async def launch(playwright, headless):
        launches.append(headless)
        if not headless:

            async def hanging_close():
                await asyncio.Event().wait()

            browser = SimpleNamespace(close=hanging_close)
        else:
            browser = SimpleNamespace(close=AsyncMock())
        browsers.append(browser)
        return browser

    def init_context(browser, account_file=None):
        page = pages[len(browsers) - 1]
        context = SimpleNamespace(
            new_page=AsyncMock(return_value=page),
            close=AsyncMock(),
            storage_state=AsyncMock(),
        )
        return context

    async def run():
        with ExitStack() as stack_ctx:
            for patcher in (
                patch("uploader.base_video.async_playwright", driver),
                patch.object(uploader, "_launch_browser", AsyncMock(side_effect=launch)),
                patch.object(uploader, "_init_context", AsyncMock(side_effect=init_context)),
            ):
                stack_ctx.enter_context(patcher)
            async with uploader._browser_session() as page:
                return page

    started = time.monotonic()
    page = asyncio.run(run())
    assert time.monotonic() - started < 10
    assert page is pages[2]
    assert launches == [True, False, True]
