# tests/test_conf_pip_mode.py
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ConfPipModeTests(unittest.TestCase):
    def test_all_agents_use_user_opub_even_when_sau_home_is_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            env = os.environ.copy()
            env["HOME"] = str(home)
            env["USERPROFILE"] = str(home)
            env["SAU_HOME"] = str(Path(tmp) / "stale-snapshot")
            result = subprocess.run(
                [sys.executable, "-c", "import conf; print(conf.BASE_DIR)"],
                env=env, capture_output=True, text=True, check=True,
            )
            self.assertEqual(result.stdout.strip(), str((home / ".opub").resolve()))
            self.assertFalse((Path(tmp) / "stale-snapshot" / "cookies").exists())

    def test_source_checkout_does_not_become_data_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            env = os.environ.copy()
            env["HOME"] = str(home)
            env["USERPROFILE"] = str(home)
            env.pop("SAU_HOME", None)
            result = subprocess.run(
                [sys.executable, "-c", "import conf; print(conf.BASE_DIR)"],
                env=env, capture_output=True, text=True, check=True,
            )
            self.assertEqual(result.stdout.strip(), str((home / ".opub").resolve()))


if __name__ == "__main__":
    unittest.main()
