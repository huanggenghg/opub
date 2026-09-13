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

    def test_cookie_gen_awaits_interactive_command(self):
        import asyncio
        with patch("pathlib.Path.mkdir"), patch("os.path.exists", return_value=True), \
             patch("uploader.bilibili_uploader.main.run_biliup_command_async", new=AsyncMock()) as command:
            command.return_value.returncode = 0
            result = asyncio.run(BilibiliUploader.cookie_gen("/fake/account.json"))
        self.assertTrue(result)
        command.assert_awaited_once_with(["-u", "/fake/account.json", "login"], interactive=True)


if __name__ == "__main__":
    unittest.main()
