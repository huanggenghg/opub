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


class WeiboNoteUploadTests(unittest.TestCase):
    def test_upload_returns_platform_result_extras(self):
        import asyncio
        uploader = WeiboNote(
            image_paths=["/fake.jpg"], note="test note", tags=[],
            publish_date=0, account_file="/fake.json",
        )
        with patch.object(uploader, "_browser_session") as mock_session, \
             patch.object(uploader, "validate_upload_args", AsyncMock()), \
             patch.object(WeiboNote, "upload_note_content", AsyncMock()):
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def fake_session():
                class FakePage:
                    url = "https://weibo.com/upload/channel"
                yield FakePage()

            mock_session.return_value = fake_session()
            result = asyncio.run(uploader.upload())
        self.assertTrue(result["success"])
        self.assertEqual(result["message"], "发布成功")


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
