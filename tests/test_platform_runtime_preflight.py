import asyncio
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import publish_all
from publish import orchestrator, runtime
from publish.errors import EXIT_ENV_ERROR


def _video_params(platforms, accounts):
    return {
        "content_type": "video",
        "title": "标题",
        "desc": "描述",
        "tags": [],
        "video_file": "videos/demo.mp4",
        "images": [],
        "publish_strategy": "immediate",
        "publish_time": None,
        "enabled_platforms": platforms,
        "platforms": accounts,
        "convert_to_video": False,
        "video_duration": 5,
        "start_from": 1,
    }


class _FakeStore:
    def __init__(self, items, runnable):
        self._items = items
        self._runnable = runnable

    def load(self, run_id):
        return self._items

    def runnable_entries(self, run_id):
        return self._runnable


class PlatformRuntimePreflightTests(unittest.TestCase):
    def test_bilibili_missing_binary_fails_with_repair_hint(self):
        stderr = io.StringIO()
        with patch(
            "uploader.bilibili_uploader.runtime.require_biliup_binary",
            side_effect=FileNotFoundError("未找到 biliup，请运行 opub --repair-env --with-bilibili 安装"),
        ), contextlib.redirect_stderr(stderr):
            ok = runtime.platform_runtime_preflight(["bilibili"])
        self.assertFalse(ok)
        self.assertIn("ENV-007", stderr.getvalue())
        self.assertIn("opub --repair-env --with-bilibili", stderr.getvalue())

    def test_preflight_is_read_only_and_never_installs(self):
        with patch(
            "uploader.bilibili_uploader.runtime.require_biliup_binary",
            side_effect=FileNotFoundError("缺失"),
        ), patch("uploader.bilibili_uploader.runtime.ensure_biliup_binary") as ensure:
            runtime.platform_runtime_preflight(["bilibili"])
        ensure.assert_not_called()

    def test_present_binary_passes(self):
        with patch(
            "uploader.bilibili_uploader.runtime.require_biliup_binary",
            return_value=Path("/mock/biliup"),
        ) as require:
            self.assertTrue(runtime.platform_runtime_preflight(["bilibili"]))
        require.assert_called_once()

    def test_other_platforms_skip_bilibili_check(self):
        with patch("uploader.bilibili_uploader.runtime.require_biliup_binary") as require:
            self.assertTrue(runtime.platform_runtime_preflight(["douyin", "baijiahao"]))
        require.assert_not_called()


class RepairWithBilibiliTests(unittest.TestCase):
    def setUp(self):
        dependencies = patch("publish.runtime.sync_python_dependencies", return_value=True)
        browser = patch("publish.runtime.install_patchright_chromium", return_value=True)
        dependencies.start()
        browser.start()
        self.addCleanup(dependencies.stop)
        self.addCleanup(browser.stop)

    def test_with_bilibili_installs_biliup(self):
        with patch(
            "uploader.bilibili_uploader.runtime.ensure_biliup_binary",
            return_value=Path("/mock/biliup"),
        ) as ensure:
            self.assertTrue(runtime.repair_environment(with_bilibili=True))
        ensure.assert_called_once()

    def test_normal_repair_does_not_install_biliup(self):
        with patch("uploader.bilibili_uploader.runtime.ensure_biliup_binary") as ensure:
            self.assertTrue(runtime.repair_environment())
        ensure.assert_not_called()

    def test_biliup_install_failure_reports_error_and_stops(self):
        stderr = io.StringIO()
        with patch(
            "uploader.bilibili_uploader.runtime.ensure_biliup_binary",
            side_effect=OSError("network down"),
        ), contextlib.redirect_stderr(stderr):
            self.assertFalse(runtime.repair_environment(with_bilibili=True))
        self.assertIn("ENV-007", stderr.getvalue())


class PublishGateIntegrationTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.test_video = Path(workspace.name) / "demo.mp4"
        self.test_video.write_bytes(b"video")

    def test_publish_with_bilibili_stops_before_accounts_when_binary_missing(self):
        params = _video_params(["bilibili"], {"bilibili_account": "cookies/bili_1.json"})
        with patch("publish.orchestrator.runtime_preflight", new=AsyncMock(return_value=True)), \
             patch("publish.orchestrator.platform_runtime_preflight", return_value=False) as platform_check, \
             patch("publish.orchestrator.get_video_files", return_value=[str(self.test_video)]), \
             patch("publish.orchestrator.get_video_content", return_value=("标题", "描述")), \
             patch("publish.orchestrator.publish_one_item", new=AsyncMock()) as publish_item, \
             patch("publish.orchestrator.execute_prepared", new=AsyncMock(return_value=0)) as prepared:
            code = asyncio.run(publish_all.run_publish_with_params(params))
        self.assertEqual(code, EXIT_ENV_ERROR)
        platform_check.assert_called_once_with(["bilibili"])
        publish_item.assert_not_awaited()
        prepared.assert_not_awaited()

    def test_dry_run_with_bilibili_checks_read_only_program_before_plan(self):
        params = {**_video_params(["bilibili"], {"bilibili_account": "cookies/bili_1.json"}), "dry_run": True}
        with patch("publish.orchestrator.runtime_preflight", new=AsyncMock(return_value=True)), \
             patch("publish.orchestrator.platform_runtime_preflight", return_value=False), \
             patch("publish.orchestrator.get_video_files", return_value=[str(self.test_video)]), \
             patch("publish.orchestrator.get_video_content", return_value=("标题", "描述")), \
             patch("publish.orchestrator.record_plan") as record_plan:
            code = asyncio.run(publish_all.run_publish_with_params(params))
        self.assertEqual(code, EXIT_ENV_ERROR)
        record_plan.assert_not_called()

    def test_publish_without_bilibili_skips_platform_check(self):
        params = _video_params(["douyin"], {"douyin_account": "cookies/douyin_1.json"})
        with patch("publish.orchestrator.runtime_preflight", new=AsyncMock(return_value=True)), \
             patch("publish.orchestrator.platform_runtime_preflight", return_value=True) as platform_check, \
             patch("publish.orchestrator.get_video_files", return_value=[str(self.test_video)]), \
             patch("publish.orchestrator.get_video_content", return_value=("标题", "描述")), \
             patch("publish.orchestrator.execute_prepared", new=AsyncMock(return_value=0)):
            code = asyncio.run(publish_all.run_publish_with_params(params))
        self.assertEqual(code, 0)
        platform_check.assert_called_once_with(["douyin"])

    def test_resume_checks_only_still_runnable_platforms(self):
        items = [_video_params(["douyin", "bilibili"], {})]
        store = _FakeStore(items, [(0, "douyin")])
        with patch("publish.orchestrator.HistoryStore", return_value=store), \
             patch("publish.orchestrator.runtime_preflight", new=AsyncMock(return_value=True)), \
             patch("publish.orchestrator.platform_runtime_preflight", return_value=True) as platform_check, \
             patch("publish.orchestrator.validate_schedule"), \
             patch("publish.orchestrator.execute_prepared", new=AsyncMock(return_value=0)) as prepared:
            code = asyncio.run(orchestrator.resume_publish("run-1"))
        self.assertEqual(code, 0)
        platform_check.assert_called_once_with({"douyin"})
        prepared.assert_awaited_once()

    def test_resume_fails_when_runnable_bilibili_binary_missing(self):
        items = [_video_params(["douyin", "bilibili"], {})]
        store = _FakeStore(items, [(0, "douyin"), (0, "bilibili")])
        with patch("publish.orchestrator.HistoryStore", return_value=store), \
             patch("publish.orchestrator.runtime_preflight", new=AsyncMock(return_value=True)), \
             patch("publish.orchestrator.platform_runtime_preflight", return_value=False), \
             patch("publish.orchestrator.validate_schedule"), \
             patch("publish.orchestrator.execute_prepared", new=AsyncMock(return_value=0)) as prepared:
            code = asyncio.run(orchestrator.resume_publish("run-1"))
        self.assertEqual(code, EXIT_ENV_ERROR)
        prepared.assert_not_awaited()

    def test_resume_with_no_runnable_work_skips_platform_check(self):
        items = [_video_params(["bilibili"], {})]
        store = _FakeStore(items, [])
        with patch("publish.orchestrator.HistoryStore", return_value=store), \
             patch("publish.orchestrator.runtime_preflight", new=AsyncMock(return_value=True)), \
             patch("publish.orchestrator.platform_runtime_preflight", return_value=True) as platform_check, \
             patch("publish.orchestrator.execute_prepared", new=AsyncMock(return_value=0)) as prepared:
            code = asyncio.run(orchestrator.resume_publish("run-1"))
        self.assertEqual(code, 0)
        platform_check.assert_not_called()
        prepared.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
