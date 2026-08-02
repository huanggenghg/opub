import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


class PackageBuildTest(unittest.TestCase):
    def test_wheel_contains_hgsau_entry_modules(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    "--no-deps",
                    "--wheel-dir",
                    tmpdir,
                    str(repo_root),
                ],
                cwd=repo_root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            wheel = next(Path(tmpdir).glob("hgsau-*.whl"))
            with zipfile.ZipFile(wheel) as archive:
                names = set(archive.namelist())

        self.assertIn("conf.py", names)
        self.assertNotIn("hgsau_cli.py", names)
        self.assertIn("publish_all.py", names)
        self.assertNotIn("sau_cli.py", names)

