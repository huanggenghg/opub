# -*- coding: utf-8 -*-
"""登录(setup/cookie_gen)必须默认有头:扫码要看得见浏览器窗口,
不跟随 config.json 的 chrome_headless(该键已废弃,不再影响登录)。"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


_CHECK_CODE = """
import inspect
import sys

from uploader.base_video import BaseBrowserUploader
from uploader.baijiahao_uploader.main import baijiahao_setup
from uploader.douyin_uploader.main import douyin_setup
from uploader.ks_uploader.main import ks_setup
from uploader.tencent_uploader.main import tencent_setup
from uploader.tk_uploader.main import tiktok_setup
from uploader.weibo_uploader.main import weibo_setup
from uploader.xiaohongshu_uploader.main import xiaohongshu_setup

targets = [
    ("BaseBrowserUploader.setup", BaseBrowserUploader.setup),
    ("BaseBrowserUploader.cookie_gen", BaseBrowserUploader.cookie_gen),
    ("douyin_setup", douyin_setup),
    ("xiaohongshu_setup", xiaohongshu_setup),
    ("ks_setup", ks_setup),
    ("tencent_setup", tencent_setup),
    ("baijiahao_setup", baijiahao_setup),
    ("weibo_setup", weibo_setup),
    ("tiktok_setup", tiktok_setup),
]
bad = [
    name for name, fn in targets
    if inspect.signature(fn).parameters["headless"].default is not False
]
print(",".join(bad))
sys.exit(1 if bad else 0)
"""


class LoginHeadedDefaultTests(unittest.TestCase):
    def test_login_entry_points_stay_headed_even_with_chrome_headless_config(self):
        """chrome_headless=true 时登录入口仍必须有头(扫码需要可见窗口)。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            home = Path(tmp_dir) / "home"
            data_dir = home / ".opub"
            data_dir.mkdir(parents=True)
            (data_dir / "config.json").write_text('{"chrome_headless": true}', encoding="utf-8")
            env = os.environ.copy()
            env["HOME"] = str(home)
            env["USERPROFILE"] = str(home)
            result = subprocess.run(
                [sys.executable, "-c", _CHECK_CODE],
                env=env, capture_output=True, text=True,
            )

        self.assertEqual(
            result.returncode, 0,
            f"以下登录入口默认了无头: {result.stdout.strip() or '(见 stderr)'}\n{result.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
