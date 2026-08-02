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


class ModuleWrapperTests(unittest.TestCase):
    def test_setup_signature_is_5_params(self):
        import inspect
        sig = inspect.signature(xiaohongshu_setup)
        params = list(sig.parameters.keys())
        self.assertEqual(params, ["account_file", "handle", "return_detail", "qrcode_callback", "headless"])


if __name__ == "__main__":
    unittest.main()
