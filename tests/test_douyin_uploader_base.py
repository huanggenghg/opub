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
