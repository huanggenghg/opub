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


class KSNoteUploadTests(unittest.TestCase):
    def test_upload_returns_unified_dict(self):
        import asyncio
        uploader = KSNote(
            image_paths=["/fake.jpg"], note="test note", tags=[],
            publish_date=0, account_file="/fake.json",
        )
        with patch.object(KSNote, "upload_note_content", AsyncMock(return_value={"share_link": "https://kuaishou.com/n/abc", "video_id": "nid123"})), \
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
        self.assertEqual(result["result_url"], "https://kuaishou.com/n/abc")
        self.assertEqual(result["result_id"], "nid123")


class ModuleWrapperTests(unittest.TestCase):
    def test_setup_signature_is_5_params(self):
        import inspect
        sig = inspect.signature(ks_setup)
        params = list(sig.parameters.keys())
        self.assertEqual(params, ["account_file", "handle", "return_detail", "qrcode_callback", "headless"])


if __name__ == "__main__":
    unittest.main()
