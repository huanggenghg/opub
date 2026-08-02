import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import publish_all


class PublishEngineTests(unittest.TestCase):
    def test_reset_publish_task_fields_clears_one_time_fields_and_keeps_accounts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "publish_config.ini"
            config_path.write_text(
                "# config comments should stay\n"
                "[common]\n"
                "content_type = note\n"
                "convert_to_video = true\n"
                "video_duration = 9\n"
                "title = old title\n"
                "desc = old desc\n"
                "tags = old,tags\n"
                "video_file = videos/old.mp4\n"
                "images = images/old.png\n"
                "publish_strategy = scheduled\n"
                "publish_time = 2026-05-01 12:00\n"
                "start_from = 3\n"
                "\n"
                "[platforms]\n"
                "enabled = weibo,douyin\n"
                "weibo_account = cookies/weibo.json\n",
                encoding="utf-8",
            )

            publish_all.reset_publish_task_fields(config_path)

            text = config_path.read_text(encoding="utf-8")

        self.assertIn("# config comments should stay", text)
        self.assertIn("content_type = video", text)
        self.assertIn("convert_to_video = false", text)
        self.assertIn("video_duration = 5", text)
        self.assertIn("title =", text)
        self.assertIn("desc =", text)
        self.assertIn("tags =", text)
        self.assertIn("video_file =", text)
        self.assertIn("images =", text)
        self.assertIn("publish_strategy = immediate", text)
        self.assertIn("publish_time =", text)
        self.assertIn("start_from =", text)
        self.assertIn("enabled =", text)
        self.assertIn("weibo_account = cookies/weibo.json", text)

    def test_apply_overrides_merges_publish_fields(self):
        publish_time = publish_all.datetime.strptime("2026-05-30 21:30", "%Y-%m-%d %H:%M")
        params = {
            "content_type": "video",
            "title": "old title",
            "desc": "old desc",
            "tags": ["old"],
            "video_file": "old.mp4",
            "images": [],
            "publish_strategy": "immediate",
            "publish_time": None,
            "enabled_platforms": ["douyin"],
            "platforms": {},
            "convert_to_video": False,
            "video_duration": 5,
            "start_from": 1,
        }
        overrides = publish_all.PublishOverrides(
            platforms="douyin,weibo",
            video="videos/demo.mp4",
            title="标题",
            desc="描述",
            tags="标签1,标签2",
            schedule=publish_time,
            start_from=3,
            force=True,
        )

        merged = publish_all.apply_overrides(params, overrides)

        self.assertEqual(merged["enabled_platforms"], ["douyin", "weibo"])
        self.assertEqual(merged["video_file"], "videos/demo.mp4")
        self.assertEqual(merged["title"], "标题")
        self.assertEqual(merged["desc"], "描述")
        self.assertEqual(merged["tags"], ["标签1", "标签2"])
        self.assertEqual(merged["publish_strategy"], "scheduled")
        self.assertEqual(merged["publish_time"], publish_time)
        self.assertEqual(merged["start_from"], 3)
        self.assertTrue(merged["force"])

    def test_run_publish_sync_returns_1_when_config_has_no_enabled_platforms(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "publish_config.ini"
            config_path.write_text(
                "[common]\n"
                "video_file = videos/demo.mp4\n"
                "title = 标题\n"
                "\n"
                "[platforms]\n"
                "enabled = \n",
                encoding="utf-8",
            )

            code = publish_all.run_publish_sync(str(config_path))

        self.assertEqual(code, 1)

    def test_run_publish_sync_resets_task_fields_after_config_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "publish_config.ini"
            config_path.write_text(
                "[common]\n"
                "content_type = video\n"
                "video_file = videos/demo.mp4\n"
                "title = old title\n"
                "tags = old\n"
                "\n"
                "[platforms]\n"
                "enabled = weibo\n"
                "weibo_account = cookies/weibo.json\n",
                encoding="utf-8",
            )

            with patch("publish.orchestrator.run_publish_with_params", new=AsyncMock(return_value=0)):
                code = publish_all.run_publish_sync(str(config_path))

            text = config_path.read_text(encoding="utf-8")

        self.assertEqual(code, 0)
        self.assertIn("video_file =", text)
        self.assertIn("title =", text)
        self.assertIn("tags =", text)
        self.assertIn("enabled =", text)
        self.assertIn("weibo_account = cookies/weibo.json", text)

    def test_run_publish_sync_uses_cli_overrides_without_config_file(self):
        overrides = publish_all.PublishOverrides(
            platforms="weibo",
            video="videos/demo.mp4",
            title="标题",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            missing_config = Path(tmpdir) / "missing.ini"
            with patch("publish.orchestrator.run_publish_with_params", new=AsyncMock(return_value=0)) as run_params:
                code = publish_all.run_publish_sync(str(missing_config), overrides)

        self.assertEqual(code, 0)
        call = run_params.await_args
        params = call.args[0]
        self.assertEqual(params["enabled_platforms"], ["weibo"])
        self.assertEqual(params["video_file"], "videos/demo.mp4")
        self.assertEqual(params["title"], "标题")

    def test_run_publish_with_params_passes_force_to_content_generation(self):
        params = {
            "content_type": "video",
            "title": "标题",
            "desc": "描述",
            "tags": [],
            "video_file": "videos/demo.mp4",
            "images": [],
            "publish_strategy": "immediate",
            "publish_time": None,
            "enabled_platforms": ["weibo"],
            "platforms": {},
            "convert_to_video": False,
            "video_duration": 5,
            "start_from": 1,
            "force": True,
        }

        with patch("publish.orchestrator.runtime_preflight", new=AsyncMock(return_value=True)):
            with patch("publish.orchestrator.get_video_files", return_value=["videos/demo.mp4"]):
                with patch("publish.orchestrator.get_video_content", return_value=("标题", "描述")) as get_video_content:
                    with patch("publish.orchestrator.publish_one_item", new=AsyncMock(return_value={})) as publish_one_item:
                        code = asyncio.run(publish_all.run_publish_with_params(params))

        self.assertEqual(code, 0)
        get_video_content.assert_called_once_with(
            "videos/demo.mp4",
            "标题",
            "描述",
            force=True,
        )
        publish_one_item.assert_awaited_once()

    def test_run_publish_with_params_skips_preflight_when_video_missing(self):
        params = {
            "content_type": "video",
            "title": "标题",
            "desc": "描述",
            "tags": [],
            "video_file": "videos/missing.mp4",
            "images": [],
            "publish_strategy": "immediate",
            "publish_time": None,
            "enabled_platforms": ["weibo"],
            "platforms": {},
            "convert_to_video": False,
            "video_duration": 5,
            "start_from": 1,
        }

        with patch("publish.orchestrator.runtime_preflight", new=AsyncMock(return_value=True)) as preflight:
            code = asyncio.run(publish_all.run_publish_with_params(params))

        self.assertEqual(code, 1)
        preflight.assert_not_awaited()

    def test_publish_to_douyin_marks_restriction_as_account_issue(self):
        params = {
            "account_file": "cookies/douyin_uploader/account.json",
            "title": "标题",
            "tags": [],
            "publish_strategy": "immediate",
            "publish_time": None,
            "content_type": "video",
            "video_file": "videos/demo.mp4",
            "desc": "",
        }

        restriction_result = {
            "success": False,
            "message": "账号被限制发布: 作品发布失败，健康分不足投稿功能受限",
            "account_issue": True,
            "issue_type": "publish_restricted",
        }

        with patch("uploader.douyin_uploader.main.DouYinVideo") as MockDouYinVideo:
            MockDouYinVideo.validate_base_args.return_value = None
            MockDouYinVideo.return_value.upload = AsyncMock(return_value=restriction_result)
            result = publish_all.run_async_for_test(publish_all.publish_to_douyin(params))

        self.assertFalse(result["success"])
        self.assertTrue(result["account_issue"])
        self.assertEqual(result["issue_type"], "publish_restricted")
        self.assertIn("健康分不足", result["message"])


class RuntimePreflightTests(unittest.TestCase):
    def test_playwright_browser_cache_dirs_include_windows_default(self):
        fake_home = Path("/Users/example")
        with patch.dict("publish_all.os.environ", {}, clear=True), \
             patch("publish_all.Path.home", return_value=fake_home):
            cache_dirs = publish_all.playwright_browser_cache_dirs()

        self.assertIn(fake_home / "AppData" / "Local" / "ms-playwright", cache_dirs)

    def test_runtime_preflight_installs_missing_chromium(self):
        with patch("publish.runtime.patchright_available", return_value=True), \
             patch("publish.runtime.patchright_chromium_installed", return_value=False), \
             patch("publish.runtime.install_patchright_chromium", return_value=True) as install:
            ok = publish_all.run_async_for_test(publish_all.runtime_preflight())

        self.assertTrue(ok)
        install.assert_called_once()

    def test_runtime_preflight_fails_when_chromium_install_fails(self):
        with patch("publish.runtime.patchright_available", return_value=True), \
             patch("publish.runtime.patchright_chromium_installed", return_value=False), \
             patch("publish.runtime.install_patchright_chromium", return_value=False):
            ok = publish_all.run_async_for_test(publish_all.runtime_preflight())

        self.assertFalse(ok)

    def test_runtime_preflight_fails_without_patchright_and_does_not_install(self):
        with patch("publish.runtime.patchright_available", return_value=False), \
             patch("publish.runtime.install_patchright_chromium", return_value=True) as install:
            ok = publish_all.run_async_for_test(publish_all.runtime_preflight())

        self.assertFalse(ok)
        install.assert_not_called()

    def test_install_patchright_chromium_defaults_to_playwright_cdn_for_chromium(self):
        with patch.dict("publish_all.os.environ", {}, clear=True):
            with patch("publish_all.subprocess.run") as run:
                run.return_value.returncode = 0

                ok = publish_all.install_patchright_chromium()

        self.assertTrue(ok)
        env = run.call_args.kwargs["env"]
        self.assertEqual(env["PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST"], "https://cdn.playwright.dev")
        self.assertNotIn("PLAYWRIGHT_DOWNLOAD_HOST", env)

    def test_install_patchright_chromium_preserves_user_download_host(self):
        with patch.dict("publish_all.os.environ", {"PLAYWRIGHT_DOWNLOAD_HOST": "https://mirror.example/playwright"}, clear=True):
            with patch("publish_all.subprocess.run") as run:
                run.return_value.returncode = 0

                ok = publish_all.install_patchright_chromium()

        self.assertTrue(ok)
        env = run.call_args.kwargs["env"]
        self.assertEqual(env["PLAYWRIGHT_DOWNLOAD_HOST"], "https://mirror.example/playwright")
        self.assertNotIn("PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST", env)


class AccountLoginFlowTests(unittest.TestCase):
    def test_publish_one_item_triggers_login_before_publish(self):
        params = {
            "enabled_platforms": ["douyin"],
            "platforms": {"douyin_account": "cookies/douyin.json"},
            "content_type": "video",
            "video_file": "videos/demo.mp4",
            "title": "标题",
            "desc": "描述",
            "tags": [],
            "publish_strategy": "immediate",
            "publish_time": None,
            "convert_to_video": False,
        }

        with patch("publish.orchestrator.ensure_account_login", new=AsyncMock(return_value=True)) as ensure_login, \
             patch("publish.orchestrator.publish_to_platform", new=AsyncMock(return_value={"success": True, "message": "发布成功"})) as publish:
            results = publish_all.run_async_for_test(publish_all.publish_one_item(params))

        ensure_login.assert_awaited_once_with("douyin", "cookies/douyin.json")
        publish.assert_awaited_once()
        self.assertTrue(results["douyin"]["success"])

    def test_publish_one_item_skips_publish_when_login_fails(self):
        params = {
            "enabled_platforms": ["douyin"],
            "platforms": {"douyin_account": "cookies/douyin.json"},
            "content_type": "video",
            "video_file": "videos/demo.mp4",
            "title": "标题",
            "desc": "描述",
            "tags": [],
            "publish_strategy": "immediate",
            "publish_time": None,
            "convert_to_video": False,
        }

        with patch("publish.orchestrator.ensure_account_login", new=AsyncMock(return_value=False)), \
             patch("publish.orchestrator.publish_to_platform", new=AsyncMock(return_value={"success": True, "message": "发布成功"})) as publish:
            results = publish_all.run_async_for_test(publish_all.publish_one_item(params))

        publish.assert_not_awaited()
        self.assertFalse(results["douyin"]["success"])
        self.assertIn("登录失败", results["douyin"]["message"])

    def test_publish_one_item_skips_login_for_unsupported_platforms(self):
        params = {
            "enabled_platforms": ["bilibili"],
            "platforms": {"bilibili_account": "cookies/bili.json"},
            "content_type": "video",
            "video_file": "videos/demo.mp4",
            "title": "标题",
            "desc": "描述",
            "tags": [],
            "publish_strategy": "immediate",
            "publish_time": None,
            "convert_to_video": False,
        }

        with patch("publish.orchestrator.ensure_account_login", new=AsyncMock()) as ensure_login:
            results = publish_all.run_async_for_test(publish_all.publish_one_item(params))

        ensure_login.assert_not_awaited()
        self.assertFalse(results["bilibili"]["success"])
        self.assertIn("暂未实现", results["bilibili"]["message"])


class PublishFailurePolicyTests(unittest.TestCase):
    def test_publish_one_item_continues_after_platform_failure(self):
        params = {
            "enabled_platforms": ["douyin", "weibo"],
            "platforms": {
                "douyin_account": "cookies/douyin.json",
                "weibo_account": "cookies/weibo.json",
            },
            "content_type": "video",
            "video_file": "videos/demo.mp4",
            "title": "标题",
            "desc": "描述",
            "tags": [],
            "publish_strategy": "immediate",
            "publish_time": None,
            "convert_to_video": False,
        }

        async def fake_publish(platform, publish_params):
            if platform == "douyin":
                return {"success": False, "message": "发布失败"}
            return {"success": True, "message": "发布成功"}

        with patch("publish.orchestrator.ensure_account_login", new=AsyncMock(return_value=True)), \
             patch("publish.orchestrator.publish_to_platform", new=AsyncMock(side_effect=fake_publish)):
            results = publish_all.run_async_for_test(publish_all.publish_one_item(params))

        self.assertFalse(results["douyin"]["success"])
        self.assertTrue(results["weibo"]["success"])

    def test_run_publish_with_params_returns_one_when_any_publish_fails(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "demo.mp4"
            video_path.write_bytes(b"video")
            params = {
                "enabled_platforms": ["douyin"],
                "platforms": {"douyin_account": "cookies/douyin.json"},
                "content_type": "video",
                "video_file": str(video_path),
                "images": [],
                "title": "标题",
                "desc": "描述",
                "tags": [],
                "publish_strategy": "immediate",
                "publish_time": None,
                "convert_to_video": False,
                "video_duration": 5,
                "start_from": 1,
            }

            with patch("publish.orchestrator.runtime_preflight", new=AsyncMock(return_value=True)), \
                 patch("publish.orchestrator.get_video_content", return_value=("标题", "描述")), \
                 patch("publish.orchestrator.publish_one_item", new=AsyncMock(return_value={"douyin": {"success": False, "message": "发布失败"}})) as publish_one_item:
                code = publish_all.run_async_for_test(publish_all.run_publish_with_params(params))

        publish_one_item.assert_awaited_once()
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
