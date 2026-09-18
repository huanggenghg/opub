# -*- coding: utf-8 -*-
"""B站登录的 pty 驱动与旧登录态上传失败的自愈。

背景(2026-09-18 定因):①biliup renew 通过 ≠ 上传 token 有效,旧登录态
上传必败("Request failed after N retries"),应自动重登后重试,而不是
报含糊的 Unknown Error 让人怀疑线路;②biliup login 要求 TTY 且默认菜单
停在"短信登录",Agent 无终端环境直接 "not a terminal" 失败——POSIX 下
用 pty 驱动自动选"扫码登录"并转发二维码输出。
"""
import asyncio
import subprocess
from unittest.mock import AsyncMock, patch

import pytest

from uploader.bilibili_uploader.main import BilibiliUploader

REAL_MENU = (
    "\x1b[?25l\x1b[33m?\x1b[0m \x1b[1m选择一种登录方式\x1b[0m \x1b[38;5;8m›\x1b[0m\r\n"
    "  账号密码\r\n"
    "\x1b[32m❯\x1b[0m \x1b[36m短信登录\x1b[0m\r\n"
    "  扫码登录\r\n"
    "  浏览器登录\r\n"
    "  网页Cookie登录1\r\n"
    "  网页Cookie登录2\r\n"
)


class TestCountMenuDownPresses:
    def test_real_menu_with_ansi_needs_one_down(self):
        from uploader.bilibili_uploader.login_pty import count_menu_down_presses

        assert count_menu_down_presses(REAL_MENU) == 1

    def test_cursor_on_first_item_needs_two_downs(self):
        from uploader.bilibili_uploader.login_pty import count_menu_down_presses

        menu = (
            "? 选择一种登录方式 ›\r\n"
            "❯ 账号密码\r\n"
            "  短信登录\r\n"
            "  扫码登录\r\n"
            "  浏览器登录\r\n"
        )
        assert count_menu_down_presses(menu) == 2

    def test_cursor_already_on_qrcode_needs_zero_downs(self):
        from uploader.bilibili_uploader.login_pty import count_menu_down_presses

        menu = (
            "? 选择一种登录方式 ›\r\n"
            "  账号密码\r\n"
            "  短信登录\r\n"
            "❯ 扫码登录\r\n"
            "  浏览器登录\r\n"
        )
        assert count_menu_down_presses(menu) == 0

    def test_menu_absent_returns_none(self):
        from uploader.bilibili_uploader.login_pty import count_menu_down_presses

        assert count_menu_down_presses("随便的输出,没有菜单") is None

    def test_menu_without_qrcode_option_returns_none(self):
        from uploader.bilibili_uploader.login_pty import count_menu_down_presses

        menu = "? 选择一种登录方式 ›\r\n❯ 账号密码\r\n  短信登录\r\n"
        assert count_menu_down_presses(menu) is None


class TestCookieGenRouting:
    def test_posix_uses_pty_driver_with_resolved_paths(self, tmp_path):
        account = tmp_path / "sub" / "account.json"
        completed = subprocess.CompletedProcess([], 0)
        with patch("os.path.exists", return_value=True), patch(
            "uploader.bilibili_uploader.main.run_biliup_login_pty_async",
            new=AsyncMock(return_value=completed),
        ) as pty_login, patch(
            "uploader.bilibili_uploader.main.run_biliup_command_async",
            new=AsyncMock(side_effect=AssertionError("interactive path must not run on posix")),
        ):
            result = asyncio.run(BilibiliUploader.cookie_gen(str(account)))
        assert result is True
        args = pty_login.await_args.args
        assert args[0] == ["-u", str(account.resolve()), "login"]
        assert args[1] == str(account.resolve().parent)

    def test_windows_keeps_interactive_console_login(self, tmp_path):
        account = tmp_path / "sub" / "account.json"
        completed = subprocess.CompletedProcess([], 0)
        with patch("uploader.bilibili_uploader.main._IS_WINDOWS", True), patch(
            "os.path.exists", return_value=True
        ), patch(
            "uploader.bilibili_uploader.main.run_biliup_command_async",
            new=AsyncMock(return_value=completed),
        ) as command, patch(
            "uploader.bilibili_uploader.main.run_biliup_login_pty_async",
            new=AsyncMock(side_effect=AssertionError("pty driver must not run on windows")),
        ):
            result = asyncio.run(BilibiliUploader.cookie_gen(str(account)))
        assert result is True
        command.assert_awaited_once_with(
            ["-u", str(account.resolve()), "login"], interactive=True
        )


def _make_uploader(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"v")
    return BilibiliUploader(
        title="t", file_path=str(video), tags=[],
        account_file=str(tmp_path / "account.json"),
    )


def _run_upload(uploader):
    return asyncio.run(uploader.upload())


class TestStaleLoginUploadRecovery:
    def test_stale_upload_failure_relogins_and_retries_once(self, tmp_path):
        uploader = _make_uploader(tmp_path)
        list_outputs = iter(["", "", "BV1\tt"])
        upload_outputs = iter([
            subprocess.CompletedProcess([], 1, stderr="Error: Request failed after 5 retries"),
            subprocess.CompletedProcess([], 0, stdout="上传成功"),
        ])

        async def fake_run(arguments, **kwargs):
            if "list" in arguments:
                return subprocess.CompletedProcess(arguments, 0, stdout=next(list_outputs))
            return next(upload_outputs)

        with patch(
            "uploader.bilibili_uploader.main.run_biliup_command_async",
            new=AsyncMock(side_effect=fake_run),
        ) as command, patch.object(
            BilibiliUploader, "cookie_gen", new=AsyncMock(return_value=True)
        ) as relogin:
            result = _run_upload(uploader)

        assert result["success"] is True
        assert result["result_url"] == "https://www.bilibili.com/video/BV1"
        relogin.assert_awaited_once_with(str(tmp_path / "account.json"))
        upload_calls = [c for c in command.await_args_list if "upload" in c.args[0]]
        assert len(upload_calls) == 2  # 失败一次 + 重登后重试一次

    def test_failed_relogin_maps_to_login_expired_auth_result(self, tmp_path):
        uploader = _make_uploader(tmp_path)

        async def fake_run(arguments, **kwargs):
            if "list" in arguments:
                return subprocess.CompletedProcess(arguments, 0, stdout="")
            return subprocess.CompletedProcess(arguments, 1, stderr="Request failed after 5 retries")

        with patch(
            "uploader.bilibili_uploader.main.run_biliup_command_async",
            new=AsyncMock(side_effect=fake_run),
        ), patch.object(
            BilibiliUploader, "cookie_gen", new=AsyncMock(return_value=False)
        ) as relogin:
            result = _run_upload(uploader)

        assert result["success"] is False
        assert result["account_issue"] is True
        assert result["issue_type"] == "login_expired"
        assert result["safe_to_retry"] is True
        assert "重新扫码登录未完成" in result["message"]
        relogin.assert_awaited_once()

    def test_relogin_timeout_maps_to_auth_result(self, tmp_path):
        uploader = _make_uploader(tmp_path)

        async def fake_run(arguments, **kwargs):
            if "list" in arguments:
                return subprocess.CompletedProcess(arguments, 0, stdout="")
            return subprocess.CompletedProcess(arguments, 1, stderr="Request failed after 5 retries")

        with patch(
            "uploader.bilibili_uploader.main.run_biliup_command_async",
            new=AsyncMock(side_effect=fake_run),
        ), patch.object(
            BilibiliUploader,
            "cookie_gen",
            new=AsyncMock(side_effect=subprocess.TimeoutExpired(["biliup"], 360)),
        ):
            result = _run_upload(uploader)

        assert result["success"] is False
        assert result["account_issue"] is True
        assert result["issue_type"] == "login_expired"

    def test_second_stale_failure_does_not_relogin_again(self, tmp_path):
        uploader = _make_uploader(tmp_path)

        async def fake_run(arguments, **kwargs):
            if "list" in arguments:
                return subprocess.CompletedProcess(arguments, 0, stdout="")
            return subprocess.CompletedProcess(arguments, 1, stderr="Request failed after 5 retries")

        with patch(
            "uploader.bilibili_uploader.main.run_biliup_command_async",
            new=AsyncMock(side_effect=fake_run),
        ), patch.object(
            BilibiliUploader, "cookie_gen", new=AsyncMock(return_value=True)
        ) as relogin:
            result = _run_upload(uploader)

        assert result["success"] is False
        assert "重新登录后上传仍失败" in result["message"]
        relogin.assert_awaited_once()  # 只恢复一次,不循环

    def test_non_stale_upload_failure_keeps_generic_error(self, tmp_path):
        uploader = _make_uploader(tmp_path)

        async def fake_run(arguments, **kwargs):
            if "list" in arguments:
                return subprocess.CompletedProcess(arguments, 0, stdout="")
            return subprocess.CompletedProcess(arguments, 1, stderr="some other error")

        with patch(
            "uploader.bilibili_uploader.main.run_biliup_command_async",
            new=AsyncMock(side_effect=fake_run),
        ), patch.object(
            BilibiliUploader, "cookie_gen", new=AsyncMock(side_effect=AssertionError("no relogin"))
        ) as relogin:
            result = _run_upload(uploader)

        assert result["success"] is False
        assert "biliup 上传失败" in result["message"]
        assert "account_issue" not in result
        relogin.assert_not_awaited()
