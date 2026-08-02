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
