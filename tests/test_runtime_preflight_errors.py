import asyncio
import contextlib
import io
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
        self.assertIn("pip install opub", stderr)

    def test_chromium_install_failure_reports_env_004(self):
        with patch.object(runtime, "patchright_available", return_value=True), \
             patch.object(runtime, "sync_python_dependencies", return_value=True), \
             patch.object(runtime, "patchright_chromium_installed", return_value=False), \
             patch.object(runtime, "install_patchright_chromium", return_value=False):
            ok, stderr = _run_preflight()
        self.assertFalse(ok)
        self.assertIn("[opub] ENV-004", stderr)
        self.assertIn("patchright install chromium", stderr)

    def test_python_version_reports_env_001(self):
        with patch.object(runtime.sys, "version_info", (3, 8, 0)):
            ok, stderr = _run_preflight()
        self.assertFalse(ok)
        self.assertIn("[opub] ENV-001", stderr)


if __name__ == "__main__":
    unittest.main()
