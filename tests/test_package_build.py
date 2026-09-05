import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path


def _build_wheel(repo_root: Path, outdir: Path) -> set[str]:
    """Build the public wheel exactly the way a real pip install would."""
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(outdir),
            str(repo_root),
        ],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    wheel = next(outdir.glob("opub-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        return set(archive.namelist())


def _build_sdist(repo_root: Path, outdir: Path) -> set[str]:
    """Build the public sdist exactly the way a release upload would."""
    outdir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--sdist",
            "--outdir",
            str(outdir),
            str(repo_root),
        ],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    sdist = next(outdir.glob("opub-*.tar.gz"))
    with tarfile.open(sdist) as archive:
        return set(archive.getnames())


class PackageBuildTest(unittest.TestCase):
    def test_wheel_contains_opub_entry_modules(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmpdir:
            names = _build_wheel(repo_root, Path(tmpdir))

        self.assertIn("conf.py", names)
        self.assertNotIn("opub_cli.py", names)
        self.assertIn("publish_all.py", names)
        self.assertNotIn("sau_cli.py", names)
        # The client-facing publish packages must keep shipping in the wheel.
        self.assertIn("publish/orchestrator.py", names)
        self.assertIn("uploader/weibo_uploader/main.py", names)
        self.assertIn("utils/stealth.min.js", names)

    def test_distributions_exclude_private_license_service(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir)
            wheel_names = _build_wheel(repo_root, outdir / "wheel")
            sdist_names = _build_sdist(repo_root, outdir / "sdist")

        for names in (wheel_names, sdist_names):
            self.assertFalse(any("license_server/" in name for name in names))
            self.assertFalse(any(".secrets/" in name for name in names))
            self.assertFalse(any(name.endswith(".sqlite3") for name in names))
            # The *.sqlite3* wildcard also covers -shm and -wal sidecar files.
            self.assertFalse(any(".sqlite3" in name for name in names))
