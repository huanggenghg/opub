import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from uploader.bilibili_uploader.runtime import (
    _CREATE_NEW_CONSOLE,
    build_biliup_runtime_path,
    ensure_biliup_binary,
    require_biliup_binary,
    run_biliup_command,
)


class BiliupRuntimeTests(unittest.TestCase):
    def test_build_biliup_runtime_path_returns_platform_path(self):
        path = build_biliup_runtime_path("Windows")
        self.assertTrue(str(path).endswith("biliup.exe"))

    @patch("uploader.bilibili_uploader.runtime.fetch_latest_release")
    def test_ensure_biliup_binary_downloads_when_missing(self, mock_release):
        mock_release.return_value = {
            "tag_name": "v1.0.0",
            "asset_url": "https://example.invalid/biliup.exe",
            "asset_name": "biliup.exe",
        }
        with patch("uploader.bilibili_uploader.runtime.read_local_biliup_version", return_value=None):
            with patch("pathlib.Path.exists", return_value=False):
                with patch("uploader.bilibili_uploader.runtime.download_biliup_asset") as mock_download:
                    with patch("uploader.bilibili_uploader.runtime.write_local_biliup_version") as mock_write_version:
                        ensure_biliup_binary(force_check=True)
        mock_download.assert_called_once()
        mock_write_version.assert_called_once_with("v1.0.0")

    @patch("uploader.bilibili_uploader.runtime.fetch_latest_release")
    def test_ensure_biliup_binary_reuses_local_when_up_to_date(self, mock_release):
        mock_release.return_value = {
            "tag_name": "v1.0.0",
            "asset_url": "https://example.invalid/biliup.exe",
            "asset_name": "biliup.exe",
        }
        with patch("uploader.bilibili_uploader.runtime.read_local_biliup_version", return_value="v1.0.0"):
            with patch("pathlib.Path.exists", return_value=True):
                with patch("uploader.bilibili_uploader.runtime.download_biliup_asset") as mock_download:
                    with patch("uploader.bilibili_uploader.runtime.write_local_biliup_version") as mock_write_version:
                        ensure_biliup_binary(force_check=True)
        mock_download.assert_not_called()
        mock_write_version.assert_not_called()

    def test_require_biliup_binary_rejects_missing_binary_without_downloading(self):
        with patch("uploader.bilibili_uploader.runtime.build_biliup_runtime_path", return_value=Path("/missing/biliup")), \
             patch("uploader.bilibili_uploader.runtime.fetch_latest_release") as fetch:
            with self.assertRaisesRegex(FileNotFoundError, "opub --repair-env --with-bilibili"):
                require_biliup_binary()
        fetch.assert_not_called()

    def test_require_biliup_binary_rejects_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
             patch("uploader.bilibili_uploader.runtime.build_biliup_runtime_path", return_value=Path(temp_dir)):
            with self.assertRaises(FileNotFoundError):
                require_biliup_binary()

    @unittest.skipIf(os.name == "nt", "POSIX executable bits do not apply on Windows")
    def test_require_biliup_binary_rejects_non_executable_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            binary = Path(temp_dir) / "biliup"
            binary.touch(mode=0o600)
            with patch("uploader.bilibili_uploader.runtime.build_biliup_runtime_path", return_value=binary):
                with self.assertRaises(FileNotFoundError):
                    require_biliup_binary()

    @patch("uploader.bilibili_uploader.runtime.subprocess.run")
    @patch("uploader.bilibili_uploader.runtime.require_biliup_binary")
    def test_run_biliup_command_returns_completed_process(self, mock_require_binary, mock_run):
        mock_require_binary.return_value = build_biliup_runtime_path("Windows")
        mock_run.return_value = Mock(returncode=0, stdout="ok", stderr="")
        result = run_biliup_command(["login"])
        self.assertEqual(result.returncode, 0)

    @patch("uploader.bilibili_uploader.runtime.subprocess.run")
    @patch("uploader.bilibili_uploader.runtime.require_biliup_binary", return_value=Path("/mock/biliup"))
    def test_run_biliup_command_uses_command_specific_timeouts(self, _, mock_run):
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        for arguments, expected in [(["list"], 60), (["renew"], 60), (["login"], 360), (["upload", "video.mp4"], 3600)]:
            with self.subTest(arguments=arguments):
                run_biliup_command(arguments, interactive="login" in arguments)
                self.assertEqual(mock_run.call_args.kwargs["timeout"], expected)

    @patch("uploader.bilibili_uploader.runtime.subprocess.run")
    @patch("uploader.bilibili_uploader.runtime.require_biliup_binary", return_value=Path("/mock/biliup"))
    def test_run_biliup_command_explicit_timeout_overrides_default(self, _, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(["biliup", "upload"], 0.01)
        with self.assertRaises(subprocess.TimeoutExpired):
            run_biliup_command(["upload", "video.mp4"], timeout=0.01)
        self.assertEqual(mock_run.call_args.kwargs["timeout"], 0.01)

    @patch("uploader.bilibili_uploader.runtime.subprocess.run")
    @patch("uploader.bilibili_uploader.runtime.require_biliup_binary")
    def test_run_biliup_command_login_uses_interactive_stdio(self, mock_ensure_binary, mock_run):
        mock_ensure_binary.return_value = Path("C:/mock/biliup.exe")
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        run_biliup_command(["login"], interactive=True)
        _, kwargs = mock_run.call_args
        self.assertNotIn("capture_output", kwargs)

    @patch("uploader.bilibili_uploader.runtime.subprocess.run")
    @patch("uploader.bilibili_uploader.runtime.require_biliup_binary")
    def test_interactive_login_opens_new_console_when_stdio_is_redirected(self, ensure, run):
        ensure.return_value = Path("C:/mock/biliup.exe")
        run.return_value = Mock(returncode=0)
        with patch("uploader.bilibili_uploader.runtime.platform.system", return_value="Windows"), \
             patch("sys.stdin.isatty", return_value=False), \
             patch("sys.stdout.isatty", return_value=False):
            run_biliup_command(["-u", "account.json", "login"], interactive=True)
        _, kwargs = run.call_args
        self.assertEqual(kwargs["creationflags"], _CREATE_NEW_CONSOLE)
        self.assertNotIn("capture_output", kwargs)

    @patch("uploader.bilibili_uploader.runtime.subprocess.run")
    @patch("uploader.bilibili_uploader.runtime.require_biliup_binary")
    def test_interactive_login_keeps_inherited_stdio_in_real_terminal(self, ensure, run):
        ensure.return_value = Path("C:/mock/biliup.exe")
        run.return_value = Mock(returncode=0)
        with patch("uploader.bilibili_uploader.runtime.platform.system", return_value="Windows"), \
             patch("sys.stdin.isatty", return_value=True), \
             patch("sys.stdout.isatty", return_value=True):
            run_biliup_command(["login"], interactive=True)
        _, kwargs = run.call_args
        self.assertNotIn("creationflags", kwargs)
        self.assertNotIn("capture_output", kwargs)
