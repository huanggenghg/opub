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
