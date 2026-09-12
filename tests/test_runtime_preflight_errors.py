import asyncio
import contextlib
import io
import subprocess
import sys
import tempfile
from pathlib import Path
from importlib.metadata import PackageNotFoundError
import unittest
from unittest.mock import patch

from publish import runtime


def _run_preflight():
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout):
        with contextlib.redirect_stderr(stderr):
            ok = asyncio.run(runtime.runtime_preflight())
    return ok, stderr.getvalue()


class RuntimePreflightErrorTests(unittest.TestCase):
    def test_patchright_missing_reports_env_002(self):
        with patch.object(runtime, "patchright_available", return_value=False):
            ok, stderr = _run_preflight()
        self.assertFalse(ok)
        self.assertIn("[opub] ENV-002", stderr)
        self.assertIn("opub --repair-env", stderr)

    def test_chromium_missing_reports_env_004_without_installing(self):
        with patch.object(runtime, "patchright_available", return_value=True), \
             patch.object(runtime, "sync_python_dependencies", return_value=True), \
             patch.object(runtime, "patchright_chromium_installed", return_value=False), \
             patch.object(runtime, "install_patchright_chromium", return_value=False) as install:
            ok, stderr = _run_preflight()
        self.assertFalse(ok)
        self.assertIn("[opub] ENV-004", stderr)
        self.assertIn("opub --repair-env", stderr)
        install.assert_not_called()

    def test_python_version_reports_env_001(self):
        with patch.object(runtime.sys, "version_info", (3, 8, 0)):
            ok, stderr = _run_preflight()
        self.assertFalse(ok)
        self.assertIn("[opub] ENV-001", stderr)


class EnvironmentRepairTests(unittest.TestCase):
    def setUp(self):
        pip_patch = patch("importlib.util.find_spec", return_value=object())
        self.pip_spec = pip_patch.start()
        self.addCleanup(pip_patch.stop)

    def test_missing_pip_is_bootstrapped_before_project_and_browser_install(self):
        self.pip_spec.return_value = None
        with patch.object(runtime.subprocess, "run") as run:
            run.return_value.returncode = 0
            self.assertTrue(runtime.repair_environment(with_video=True))
        self.pip_spec.assert_called_once_with("pip")
        self.assertEqual(run.call_count, 3)
        bootstrap, project, browser = run.call_args_list
        self.assertEqual(bootstrap.args[0], [sys.executable, "-m", "ensurepip", "--upgrade"])
        self.assertGreater(bootstrap.kwargs["timeout"], 0)
        self.assertLessEqual(bootstrap.kwargs["timeout"], 600)
        self.assertEqual(project.args[0][:4], [sys.executable, "-m", "pip", "install"])
        self.assertTrue(project.args[0][-1].endswith("[video]"))
        self.assertEqual(browser.args[0][2:5], ["patchright", "install", "chromium"])

    def test_existing_pip_does_not_run_bootstrap(self):
        with patch.object(runtime.subprocess, "run") as run:
            run.return_value.returncode = 0
            self.assertTrue(runtime.repair_environment())
        self.pip_spec.assert_called_once_with("pip")
        self.assertEqual(run.call_count, 2)
        self.assertNotIn("ensurepip", run.call_args_list[0].args[0])

    def test_unavailable_ensurepip_reports_repair_guidance_without_installing(self):
        self.pip_spec.return_value = None
        stderr = io.StringIO()
        with patch.object(runtime.subprocess, "run") as run, contextlib.redirect_stderr(stderr):
            run.return_value.returncode = 1
            self.assertFalse(runtime.repair_environment())
        self.assertEqual(run.call_count, 1)
        self.assertIn("ENV-003", stderr.getvalue())
        self.assertIn("uv pip install --python", stderr.getvalue())
        self.assertIn(sys.executable, stderr.getvalue())

    def test_bootstrap_launch_failure_and_timeout_do_not_escape(self):
        self.pip_spec.return_value = None
        for error in (OSError("unavailable"), subprocess.TimeoutExpired("ensurepip", 600)):
            with self.subTest(error=type(error).__name__), \
                 patch.object(runtime.subprocess, "run", side_effect=error) as run:
                self.assertFalse(runtime.repair_environment())
                self.assertEqual(run.call_count, 1)

    def test_source_repair_installs_project_using_current_interpreter(self):
        with patch.object(runtime.subprocess, "run") as run:
            run.return_value.returncode = 0
            self.assertTrue(runtime.repair_environment())
        command = run.call_args_list[0].args[0]
        self.assertEqual(command[:4], [sys.executable, "-m", "pip", "install"])
        self.assertIn(str(Path(runtime.__file__).resolve().parent.parent), command)
        self.assertIn("--force-reinstall", command)
        self.assertNotIn("--upgrade", command)
        self.assertEqual(run.call_args_list[1].args[0], [sys.executable, "-m", "patchright", "install", "chromium"])
        for call in run.call_args_list:
            self.assertGreater(call.kwargs["timeout"], 0)
            self.assertLessEqual(call.kwargs["timeout"], 600)

    def test_source_video_repair_selects_video_extra(self):
        with patch.object(runtime.subprocess, "run") as run:
            run.return_value.returncode = 0
            self.assertTrue(runtime.repair_environment(with_video=True))
        root = Path(runtime.__file__).resolve().parent.parent
        self.assertIn(f"{root}[video]", run.call_args_list[0].args[0])

    def test_installed_repair_pins_installed_version_without_source_tree(self):
        for with_video, target in [(False, "opub==0.8.2"), (True, "opub[video]==0.8.2")]:
            with self.subTest(with_video=with_video), tempfile.TemporaryDirectory() as tmp:
                fake_file = str(Path(tmp) / "publish" / "runtime.py")
                with patch.object(runtime, "__file__", fake_file), \
                     patch("importlib.metadata.version", return_value="0.8.2"), \
                     patch.object(runtime.subprocess, "run") as run:
                    run.return_value.returncode = 0
                    self.assertTrue(runtime.repair_environment(with_video=with_video))
                self.assertIn(target, run.call_args_list[0].args[0])

    def test_unknown_installed_version_fails_without_unpinned_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(runtime, "__file__", str(Path(tmp) / "publish" / "runtime.py")), \
                 patch("importlib.metadata.version", side_effect=PackageNotFoundError), \
                 patch.object(runtime.subprocess, "run") as run:
                self.assertFalse(runtime.repair_environment())
            run.assert_not_called()

    def test_failed_dependency_repair_does_not_install_browser(self):
        with patch.object(runtime.subprocess, "run") as run:
            run.return_value.returncode = 1
            self.assertFalse(runtime.repair_environment())
        self.assertEqual(run.call_count, 1)

    def test_repair_handles_dependency_process_launch_failure_and_timeout(self):
        for error in (OSError("unavailable"), subprocess.TimeoutExpired("pip", 600)):
            with self.subTest(error=type(error).__name__), \
                 patch.object(runtime.subprocess, "run", side_effect=error) as run:
                self.assertFalse(runtime.repair_environment())
            self.assertEqual(run.call_count, 1)

    def test_repair_handles_browser_failure_and_timeout(self):
        for result in (subprocess.CompletedProcess([], 1), OSError("unavailable"), subprocess.TimeoutExpired("patchright", 600)):
            with self.subTest(result=type(result).__name__), \
                 patch.object(runtime.subprocess, "run", side_effect=[subprocess.CompletedProcess([], 0), result]):
                self.assertFalse(runtime.repair_environment())


if __name__ == "__main__":
    unittest.main()
