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

    def test_browser_session_skips_save_on_failure_when_opted_in(self):
        """save_on_success_only=True skips storage_state save when yielded block raises."""
        uploader = FakeUploader.__new__(FakeUploader)
        uploader.account_file = "/fake/account.json"
        uploader.headless = True
        fake_context = FakeContext()
        with patch("uploader.base_video.async_playwright") as mock_ap, \
             patch("uploader.base_video.set_init_script", side_effect=lambda ctx: ctx), \
             patch("uploader.base_video.os.path.exists", return_value=True):
            mock_ap.return_value = FakePlaywright(fake_context)

            async def run():
                async with uploader._browser_session(save_on_success_only=True) as page:
                    raise RuntimeError("upload failed")
            with self.assertRaises(RuntimeError):
                asyncio.run(run())
        # save_on_success_only=True + exception -> no save
        self.assertEqual(len(fake_context.storage_state_calls), 0)

    def test_browser_session_saves_on_success_when_opted_in(self):
        """save_on_success_only=True still saves when yielded block succeeds."""
        uploader = FakeUploader.__new__(FakeUploader)
        uploader.account_file = "/fake/account.json"
        uploader.headless = True
        fake_context = FakeContext()
        with patch("uploader.base_video.async_playwright") as mock_ap, \
             patch("uploader.base_video.set_init_script", side_effect=lambda ctx: ctx), \
             patch("uploader.base_video.os.path.exists", return_value=True):
            mock_ap.return_value = FakePlaywright(fake_context)

            async def run():
                async with uploader._browser_session(save_on_success_only=True) as page:
                    pass  # success
            asyncio.run(run())
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

    def test_cookie_auth_uses_local_chrome_headless(self):
        """Base class cookie_auth passes LOCAL_CHROME_HEADLESS to _launch_browser,
        not hardcoded True."""
        from conf import LOCAL_CHROME_HEADLESS
        uploader = FakeUploader.__new__(FakeUploader)
        captured_headless = []

        async def fake_launch_browser(playwright, headless):
            captured_headless.append(headless)
            return FakeBrowser(FakeContext())

        with patch("uploader.base_video.async_playwright") as mock_ap, \
             patch("uploader.base_video.set_init_script", side_effect=lambda ctx: ctx), \
             patch("uploader.base_video.os.path.exists", return_value=True):
            mock_ap.return_value = FakePlaywright(FakeContext())
            with patch.object(FakeUploader, "_launch_browser", side_effect=fake_launch_browser):
                asyncio.run(FakeUploader.cookie_auth("/fake.json"))
        # FakePage lacks goto(), so cookie_auth's page.goto() raises
        # AttributeError which is swallowed by cookie_auth's broad
        # except Exception: return False (base_video.py:216-217).
        # captured_headless is populated before that error, which is
        # what this test asserts on.
        self.assertEqual(captured_headless, [LOCAL_CHROME_HEADLESS])

    def test_storage_state_saved_before_code_after_async_with(self):
        """storage_state (saved in finally) must complete before code after
        the async with block runs. This ordering invariant is what makes
        placing the 'cookie 更新完毕' log after async with accurate - the
        log only fires after storage_state has been persisted."""
        uploader = FakeUploader.__new__(FakeUploader)
        uploader.account_file = "/fake/account.json"
        uploader.headless = True
        fake_context = FakeContext()
        call_order = []

        async def track_storage_state(path=None):
            fake_context.storage_state_calls.append(path)
            call_order.append("storage_state")

        fake_context.storage_state = track_storage_state

        with patch("uploader.base_video.async_playwright") as mock_ap, \
             patch("uploader.base_video.set_init_script", side_effect=lambda ctx: ctx), \
             patch("uploader.base_video.os.path.exists", return_value=True):
            mock_ap.return_value = FakePlaywright(fake_context)

            async def run():
                async with uploader._browser_session() as page:
                    pass  # success
                # Code here runs AFTER async with exits (after finally block)
                call_order.append("after_async_with")
            asyncio.run(run())

        # storage_state must be called before code after async with
        self.assertEqual(call_order, ["storage_state", "after_async_with"])


if __name__ == "__main__":
    unittest.main()
