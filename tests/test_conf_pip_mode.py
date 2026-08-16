# tests/test_conf_pip_mode.py
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ConfPipModeTests(unittest.TestCase):
    def test_sau_home_overrides_base_dir_even_in_dev_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["SAU_HOME"] = tmp
            result = subprocess.run(
                [sys.executable, "-c", "import conf; print(conf.BASE_DIR)"],
                env=env, capture_output=True, text=True, check=True,
            )
            self.assertEqual(result.stdout.strip(), str(Path(tmp).resolve()))

    def test_sau_home_dir_auto_created_with_cookies(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "data"
            env = os.environ.copy()
            env["SAU_HOME"] = str(target)
            subprocess.run(
                [sys.executable, "-c", "import conf"],
                env=env, capture_output=True, text=True, check=True,
            )
            self.assertTrue((target / "cookies").is_dir())


if __name__ == "__main__":
    unittest.main()
