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


class TkWaitTimeoutTests(unittest.TestCase):
    """detect_upload_status / click_publish 的 while 循环必须有超时兜底,
    否则发布按钮永远不激活/发布永远不成功时进程会无限截图+重试挂死。"""

    def _make_uploader(self):
        return TiktokVideo(
            title="t", file_path="/fake.mp4", tags=[], publish_date=0,
            account_file="/fake.json", publish_strategy=PublishStrategy.IMMEDIATE,
        )

    def test_detect_upload_status_raises_on_timeout(self):
        import asyncio
        from uploader.tk_uploader import main as tk_main

        uploader = self._make_uploader()
        with patch.object(tk_main, "TK_UPLOAD_WAIT_TIMEOUT", 0):
            with self.assertRaises(TimeoutError):
                asyncio.run(uploader.detect_upload_status(page=None))

    def test_click_publish_raises_on_timeout(self):
        import asyncio
        from uploader.tk_uploader import main as tk_main

        uploader = self._make_uploader()
        with patch.object(tk_main, "TK_PUBLISH_WAIT_TIMEOUT", 0):
            with self.assertRaises(TimeoutError):
                asyncio.run(uploader.click_publish(page=None))


class ModuleWrapperTests(unittest.TestCase):
    def test_setup_signature_is_5_params(self):
        import inspect
        sig = inspect.signature(tiktok_setup)
        params = list(sig.parameters.keys())
        self.assertEqual(params, ["account_file", "handle", "return_detail", "qrcode_callback", "headless"])


if __name__ == "__main__":
    unittest.main()
