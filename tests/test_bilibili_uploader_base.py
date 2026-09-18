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

    # cookie_gen 的 pty/Windows 路由由 tests/test_bilibili_login_pty.py 覆盖


if __name__ == "__main__":
    unittest.main()
