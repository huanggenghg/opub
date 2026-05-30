import contextlib
import io
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import hgsau_cli


class HgsauPackagingTests(unittest.TestCase):
    def test_pyproject_exposes_only_hgsau_console_script(self):
        pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
        py_modules_line = next(
            line for line in pyproject.splitlines() if line.startswith("py-modules = ")
        )

        self.assertIn('name = "hgsau"', pyproject)
        self.assertIn('hgsau = "hgsau_cli:main"', pyproject)
        self.assertNotIn('sau = "sau_cli:main"', pyproject)
        self.assertEqual(py_modules_line, 'py-modules = ["conf", "hgsau_cli", "publish_all"]')
        self.assertNotIn('"sau_cli"', py_modules_line)

    def test_hgsau_cli_module_exists(self):
        self.assertTrue(hasattr(hgsau_cli, "build_parser"))
        self.assertTrue(hasattr(hgsau_cli, "main"))

    def test_parser_prog_is_hgsau(self):
        parser = hgsau_cli.build_parser()

        self.assertEqual(parser.prog, "hgsau")


class HgsauParserTests(unittest.TestCase):
    def test_parser_accepts_publish_defaults(self):
        parser = hgsau_cli.build_parser()
        args = parser.parse_args(["publish"])

        self.assertEqual(args.command, "publish")
        self.assertEqual(args.config, "publish_config.ini")
        self.assertIsNone(args.platforms)
        self.assertIsNone(args.video)

    def test_parser_accepts_publish_overrides(self):
        parser = hgsau_cli.build_parser()
        args = parser.parse_args(
            [
                "publish",
                "--config",
                "my.ini",
                "--platforms",
                "douyin,weibo",
                "--video",
                "videos/demo.mp4",
                "--title",
                "标题",
                "--desc",
                "描述",
                "--tags",
                "标签1,标签2",
                "--schedule",
                "2026-05-30 21:30",
                "--start-from",
                "3",
                "--force",
            ]
        )

        self.assertEqual(args.config, "my.ini")
        self.assertEqual(args.platforms, "douyin,weibo")
        self.assertEqual(args.video, "videos/demo.mp4")
        self.assertEqual(args.title, "标题")
        self.assertEqual(args.desc, "描述")
        self.assertEqual(args.tags, "标签1,标签2")
        self.assertEqual(args.schedule.strftime("%Y-%m-%d %H:%M"), "2026-05-30 21:30")
        self.assertEqual(args.start_from, 3)
        self.assertTrue(args.force)

    def test_parser_rejects_removed_platform_command(self):
        parser = hgsau_cli.build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args(["douyin", "upload-video"])

    def test_dispatch_calls_publish_engine(self):
        parser = hgsau_cli.build_parser()
        args = parser.parse_args(["publish", "--platforms", "weibo", "--title", "标题"])

        with patch("publish_all.run_publish", new=AsyncMock(return_value=0)) as run_publish:
            code = hgsau_cli.run_async(args)

        self.assertEqual(code, 0)
        call = run_publish.await_args
        self.assertEqual(call.args[0], "publish_config.ini")
        self.assertEqual(call.args[1].platforms, "weibo")
        self.assertEqual(call.args[1].title, "标题")

    def test_main_returns_1_for_publish_engine_exception(self):
        stderr = io.StringIO()

        with patch("publish_all.run_publish", new=AsyncMock(side_effect=RuntimeError("boom"))):
            with contextlib.redirect_stderr(stderr):
                code = hgsau_cli.main(["publish"])

        self.assertEqual(code, 1)
        self.assertIn("boom", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
