"""issue-2026-09-19 修复的回归测试:
- tencent 二维码不可见时的下载兜底
- kuaishou 登录检查轮询等待上传按钮(页面改版后按钮延迟渲染)
- bilibili renew 查询超时重试一次
- 浏览器启动失败重试一次(批跑偶发 ENV-006)
"""
from __future__ import annotations

import asyncio
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from publish.auth import LoginCheckError
from uploader.base_video import BaseBrowserUploader
from uploader.bilibili_uploader.main import BilibiliUploader
from uploader.ks_uploader.main import KSBaseUploader
from uploader.tencent_uploader.main import (
    _download_tencent_qrcode_fallback,
    _save_tencent_qrcode,
)

_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQAB"
    "h6FO1AAAAABJRU5ErkJggg=="
)


class _FakeFrame:
    def __init__(self, url: str, evaluate_result=None):
        self.url = url
        self._evaluate_result = evaluate_result
        self.evaluate_calls = 0

    async def evaluate(self, *args, **kwargs):
        self.evaluate_calls += 1
        if callable(self._evaluate_result):
            return self._evaluate_result(*args, **kwargs)
        return self._evaluate_result


class _FakePage:
    def __init__(self, url: str = "", frames=()):
        self.url = url
        self.frames = list(frames)

    def locator(self, selector):
        return _FakeLocator()

    async def wait_for_timeout(self, timeout_ms):
        return None


class _FakeLocator:
    def __init__(self):
        self.first = self


class TencentQrFallbackTests(unittest.TestCase):
    def test_download_fallback_writes_qrcode_from_hidden_frame(self):
        frame = _FakeFrame("https://open.weixin.qq.com/connect/qrconnect?appid=x",
                           evaluate_result=_PNG_DATA_URL)
        page = _FakePage(frames=[frame])
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "qrcode.png"
            ok = asyncio.run(_download_tencent_qrcode_fallback(page, target))
            self.assertTrue(ok)
            self.assertTrue(target.exists())
            self.assertTrue(target.read_bytes().startswith(b"\x89PNG"))

    def test_download_fallback_returns_false_without_qrconnect_frame(self):
        page = _FakePage(frames=[_FakeFrame("https://channels.weixin.qq.com/login.html")])
        with tempfile.TemporaryDirectory() as tmp:
            ok = asyncio.run(_download_tencent_qrcode_fallback(page, Path(tmp) / "q.png"))
        self.assertFalse(ok)

    def test_save_qrcode_uses_fallback_when_element_never_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "qrcode.png"
            with patch("uploader.tencent_uploader.main._find_tencent_qrcode_element",
                       AsyncMock(side_effect=RuntimeError("未获取到视频号登录二维码地址"))), \
                 patch("uploader.tencent_uploader.main._download_tencent_qrcode_fallback",
                       AsyncMock(side_effect=lambda page, path: path.write_bytes(b"png") or True)), \
                 patch("uploader.tencent_uploader.main._get_qrcode_utils", return_value={
                     "build_login_qrcode_path": lambda account_file, suffix: target,
                     "decode_qrcode_from_path": lambda path: "",
                     "print_terminal_qrcode": lambda *a, **k: None,
                     "remove_qrcode_file": lambda path: False,
                 }):
                info = asyncio.run(_save_tencent_qrcode(_FakePage(), "account.json"))
            self.assertTrue(target.exists())
            self.assertEqual(info["image_path"], str(target))


class KuaishouPollingCheckTests(unittest.TestCase):
    def test_check_upload_page_polls_until_button_appears(self):
        """改版后按钮延迟渲染:单次判定失败不再立刻报 PAGE-001,轮询到就绪为止。"""
        page = _FakePage(url="https://cp.kuaishou.com/article/publish/video")
        with patch("uploader.ks_uploader.main._is_ks_locator_visible",
                   AsyncMock(return_value=False)), \
             patch("uploader.ks_uploader.main._dismiss_ks_confirm_dialog", AsyncMock()) as dismiss, \
             patch("uploader.ks_uploader.main._is_ks_auth_page_valid",
                   AsyncMock(side_effect=[False, False, True])):
            result = asyncio.run(KSBaseUploader.check_upload_page(page, timeout=10))
        self.assertTrue(result)
        self.assertGreaterEqual(dismiss.await_count, 1)

    def test_check_upload_page_returns_false_on_passport_redirect(self):
        page = _FakePage(url="https://passport.kuaishou.com/pc/account/login")
        result = asyncio.run(KSBaseUploader.check_upload_page(page))
        self.assertFalse(result)

    def test_check_upload_page_raises_page_error_when_never_ready(self):
        page = _FakePage(url="https://cp.kuaishou.com/article/publish/video")
        with patch("uploader.ks_uploader.main._is_ks_locator_visible",
                   AsyncMock(return_value=False)), \
             patch("uploader.ks_uploader.main._dismiss_ks_confirm_dialog", AsyncMock()), \
             patch("uploader.ks_uploader.main._is_ks_auth_page_valid",
                   AsyncMock(return_value=False)):
            with self.assertRaises(LoginCheckError):
                asyncio.run(KSBaseUploader.check_upload_page(page, timeout=0.3))


class BilibiliQueryRetryTests(unittest.TestCase):
    def test_cookie_auth_retries_once_on_query_timeout(self):
        timeout_exc = subprocess.TimeoutExpired(cmd="biliup", timeout=60)
        completed = subprocess.CompletedProcess(["biliup"], 0, stdout="", stderr="")
        with patch("os.path.exists", return_value=True), \
             patch("uploader.bilibili_uploader.main.run_biliup_command_async",
                   AsyncMock(side_effect=[timeout_exc, completed])) as run_mock:
            result = asyncio.run(BilibiliUploader.cookie_auth("account.json"))
        self.assertTrue(result)
        self.assertEqual(run_mock.await_count, 2)


class BrowserLaunchRetryTests(unittest.TestCase):
    def test_launch_browser_retries_once_after_failure(self):
        calls = {"count": 0}

        class _FakeChromium:
            async def launch(self, **kwargs):
                calls["count"] += 1
                if calls["count"] == 1:
                    raise RuntimeError("transient launch failure")
                return object()

        class _FakePlaywright:
            chromium = _FakeChromium()

        with patch("uploader.base_video.asyncio.sleep", AsyncMock()):
            browser = asyncio.run(BaseBrowserUploader._launch_browser(_FakePlaywright(), True))
        self.assertIsNotNone(browser)
        self.assertEqual(calls["count"], 2)


if __name__ == "__main__":
    unittest.main()
