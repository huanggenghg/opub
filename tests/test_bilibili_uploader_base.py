from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from uploader.base_video import BaseCliUploader
from uploader.bilibili_uploader.main import BilibiliUploader, cookie_auth, bilibili_setup


class BilibiliUploaderInheritanceTests(unittest.TestCase):
    def test_inherits_base_cli_uploader(self):
        self.assertTrue(issubclass(BilibiliUploader, BaseCliUploader))


class ModuleWrapperTests(unittest.TestCase):
    def test_setup_signature_is_5_params(self):
        import inspect
        sig = inspect.signature(bilibili_setup)
        params = list(sig.parameters.keys())
        self.assertEqual(params, ["account_file", "handle", "return_detail", "qrcode_callback", "headless"])

    def test_cookie_gen_runs_cli_in_thread(self):
        import asyncio
        with patch("pathlib.Path.mkdir"), patch("os.path.exists", return_value=True), \
             patch("uploader.bilibili_uploader.main.asyncio.to_thread", new=AsyncMock()) as to_thread:
            to_thread.return_value.returncode = 0
            result = asyncio.run(BilibiliUploader.cookie_gen("/fake/account.json"))
        self.assertTrue(result)
        to_thread.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
