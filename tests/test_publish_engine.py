import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import publish_all


class PublishEngineTests(unittest.TestCase):
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

    def test_run_publish_sync_uses_cli_overrides_without_config_file(self):
        overrides = publish_all.PublishOverrides(
            platforms="weibo",
            video="videos/demo.mp4",
            title="标题",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            missing_config = Path(tmpdir) / "missing.ini"
            with patch("publish_all.run_publish_with_params", new=AsyncMock(return_value=0)) as run_params:
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

        with patch("publish_all.get_video_files", return_value=["videos/demo.mp4"]):
            with patch("publish_all.get_video_content", return_value=("标题", "描述")) as get_video_content:
                with patch("publish_all.publish_one_item", new=AsyncMock(return_value={})) as publish_one_item:
                    code = asyncio.run(publish_all.run_publish_with_params(params))

        self.assertEqual(code, 0)
        get_video_content.assert_called_once_with(
            "videos/demo.mp4",
            "标题",
            "描述",
            force=True,
        )
        publish_one_item.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
