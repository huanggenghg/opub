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


if __name__ == "__main__":
    unittest.main()
