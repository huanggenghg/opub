from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from uploader.bilibili_uploader.main import BilibiliUploader


def _make_completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _make_uploader() -> BilibiliUploader:
    return BilibiliUploader(
        title="测试标题",
        file_path="/fake.mp4",
        tags=["测试"],
        account_file="/fake/account.json",
        desc="描述",
    )


class ListBvsTests(unittest.TestCase):
    def test_parses_bv_lines_into_set(self):
        stdout = "BV15r3q6FEYZ\t无小丑\t开放浏览\nBV1QQgy6rEaA\t西南\t开放浏览\nBV1PmMg68ERX\tWHO\t开放浏览\n"
        uploader = _make_uploader()
        with patch("uploader.bilibili_uploader.main.run_biliup_command", return_value=_make_completed(0, stdout=stdout)):
            bvs = uploader._list_bvs()
        self.assertEqual(bvs, {"BV15r3q6FEYZ", "BV1QQgy6rEaA", "BV1PmMg68ERX"})

    def test_returns_empty_set_for_empty_stdout(self):
        uploader = _make_uploader()
        with patch("uploader.bilibili_uploader.main.run_biliup_command", return_value=_make_completed(0, stdout="")):
            bvs = uploader._list_bvs()
        self.assertEqual(bvs, set())

    def test_returns_empty_set_when_command_fails(self):
        uploader = _make_uploader()
        with patch("uploader.bilibili_uploader.main.run_biliup_command", return_value=_make_completed(1, stderr="cookie 失效")):
            bvs = uploader._list_bvs()
        self.assertEqual(bvs, set())

    def test_skips_lines_without_bv_prefix(self):
        stdout = "2026-08-09 22:47:20  INFO biliup_cli::uploader: user: 你的收音机头\nBV15r3q6FEYZ\t无小丑\t开放浏览\n\n"
        uploader = _make_uploader()
        with patch("uploader.bilibili_uploader.main.run_biliup_command", return_value=_make_completed(0, stdout=stdout)):
            bvs = uploader._list_bvs()
        self.assertEqual(bvs, {"BV15r3q6FEYZ"})


class MatchBvByTitleTests(unittest.TestCase):
    def test_returns_bv_when_title_matches(self):
        stdout = "BV15r3q6FEYZ\t无小丑\t开放浏览\nBV1QQgy6rEaA\t测试标题\t开放浏览\n"
        uploader = _make_uploader()
        with patch("uploader.bilibili_uploader.main.run_biliup_command", return_value=_make_completed(0, stdout=stdout)):
            bv = uploader._match_bv_by_title()
        self.assertEqual(bv, "BV1QQgy6rEaA")

    def test_returns_none_when_no_match(self):
        stdout = "BV15r3q6FEYZ\t无小丑\t开放浏览\n"
        uploader = _make_uploader()
        with patch("uploader.bilibili_uploader.main.run_biliup_command", return_value=_make_completed(0, stdout=stdout)):
            bv = uploader._match_bv_by_title()
        self.assertIsNone(bv)

    def test_returns_first_bv_when_multiple_matches(self):
        stdout = "BV1111111111\t测试标题\t开放浏览\nBV2222222222\t测试标题\t开放浏览\n"
        uploader = _make_uploader()
        with patch("uploader.bilibili_uploader.main.run_biliup_command", return_value=_make_completed(0, stdout=stdout)):
            bv = uploader._match_bv_by_title()
        self.assertEqual(bv, "BV1111111111")

    def test_returns_none_when_command_fails(self):
        uploader = _make_uploader()
        with patch("uploader.bilibili_uploader.main.run_biliup_command", return_value=_make_completed(1, stderr="cookie 失效")):
            bv = uploader._match_bv_by_title()
        self.assertIsNone(bv)


class CaptureBvAfterUploadTests(unittest.TestCase):
    def test_returns_new_bv_when_diff_has_exactly_one(self):
        uploader = _make_uploader()
        before = {"BV1111111111"}
        with patch.object(uploader, "_list_bvs", return_value={"BV1111111111", "BV2222222222"}), \
             patch.object(uploader, "_match_bv_by_title") as match_mock:
            bv = uploader._capture_bv_after_upload(before, max_retries=3, delay=0)
        self.assertEqual(bv, "BV2222222222")
        match_mock.assert_not_called()

    def test_falls_back_to_title_match_after_retries_exhausted(self):
        uploader = _make_uploader()
        before = {"BV1111111111"}
        with patch.object(uploader, "_list_bvs", return_value={"BV1111111111"}), \
             patch.object(uploader, "_match_bv_by_title", return_value="BV3333333333") as match_mock:
            bv = uploader._capture_bv_after_upload(before, max_retries=2, delay=0)
        self.assertEqual(bv, "BV3333333333")
        self.assertEqual(match_mock.call_count, 1)

    def test_falls_back_to_title_match_when_multiple_new_bvs(self):
        uploader = _make_uploader()
        before = {"BV1111111111"}
        after = {"BV1111111111", "BV2222222222", "BV3333333333"}
        with patch.object(uploader, "_list_bvs", return_value=after), \
             patch.object(uploader, "_match_bv_by_title", return_value="BV2222222222") as match_mock:
            bv = uploader._capture_bv_after_upload(before, max_retries=3, delay=0)
        self.assertEqual(bv, "BV2222222222")
        self.assertEqual(match_mock.call_count, 1)

    def test_returns_none_when_all_paths_fail(self):
        uploader = _make_uploader()
        before = {"BV1111111111"}
        with patch.object(uploader, "_list_bvs", return_value={"BV1111111111"}), \
             patch.object(uploader, "_match_bv_by_title", return_value=None):
            bv = uploader._capture_bv_after_upload(before, max_retries=2, delay=0)
        self.assertIsNone(bv)


class UploadWireTests(unittest.TestCase):
    def test_upload_success_with_bv_sets_result_url(self):
        import asyncio
        uploader = _make_uploader()
        upload_completed = _make_completed(0, stdout="Upload completed: demo.mp4")

        def fake_run_biliup_command(args):
            if "upload" in args:
                return upload_completed
            return _make_completed(0, stdout="")

        with patch("uploader.bilibili_uploader.main.run_biliup_command", side_effect=fake_run_biliup_command), \
             patch("os.path.exists", return_value=True), \
             patch.object(uploader, "_list_bvs", return_value=set()), \
             patch.object(uploader, "_capture_bv_after_upload", return_value="BV15r3q6FEYZ") as capture_mock:
            result = asyncio.run(uploader.upload())

        self.assertTrue(result["success"])
        self.assertEqual(result["result_url"], "https://www.bilibili.com/video/BV15r3q6FEYZ")
        capture_mock.assert_called_once_with(set())

    def test_upload_success_without_bv_leaves_result_url_absent(self):
        import asyncio
        uploader = _make_uploader()
        upload_completed = _make_completed(0, stdout="Upload completed: demo.mp4")

        with patch("uploader.bilibili_uploader.main.run_biliup_command", return_value=upload_completed), \
             patch("os.path.exists", return_value=True), \
             patch.object(uploader, "_list_bvs", return_value=set()), \
             patch.object(uploader, "_capture_bv_after_upload", return_value=None):
            result = asyncio.run(uploader.upload())

        self.assertTrue(result["success"])
        self.assertNotIn("result_url", result)

    def test_upload_failure_does_not_call_capture(self):
        import asyncio
        uploader = _make_uploader()
        upload_failed = _make_completed(1, stderr="cookie 失效")

        with patch("uploader.bilibili_uploader.main.run_biliup_command", return_value=upload_failed), \
             patch("os.path.exists", return_value=True), \
             patch.object(uploader, "_list_bvs", return_value=set()) as list_mock, \
             patch.object(uploader, "_capture_bv_after_upload") as capture_mock:
            result = asyncio.run(uploader.upload())

        self.assertFalse(result["success"])
        capture_mock.assert_not_called()
        list_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
