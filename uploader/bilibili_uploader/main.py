# -*- coding: utf-8 -*-
"""B站上传器 - 基于 biliup CLI (wrapped in BilibiliUploader class)

与其他平台的 playwright+cookie 方案不同, B站使用社区维护的 biliup CLI
(https://github.com/biliup/biliup), 通过 B站内部上传 API 完成, 更稳定。
登录/上传/校验均通过 subprocess 调用 biliup 二进制完成。
"""
from __future__ import annotations

import asyncio
import os
import platform
import re
import subprocess
from pathlib import Path

from publish.auth import classify_login_exception, login_check
from uploader.base_video import BaseCliUploader, PlatformResultExtras, PublishStrategy
from uploader.bilibili_uploader.login_pty import run_biliup_login_pty_async
from uploader.bilibili_uploader.runtime import run_biliup_command_async
from utils.log import bilibili_logger
from utils.fs import ensure_dir

# 默认投稿分区: 171=个人动态
DEFAULT_TID = 171

_IS_WINDOWS = platform.system().lower() == "windows"

# cookie renew 通过但上传 token 已失效的特征(2026-09-18 定因):
# 旧登录态下 biliup 上传对 upos 全部重试失败,报 Request failed after N retries
_STALE_LOGIN_UPLOAD_FAILURE = re.compile(r"request failed after \d+ retries", re.IGNORECASE)


class _BiliupListCommandError(RuntimeError):
    """biliup list 命令失败(rc != 0)。仅供 _list_bvs_with_status 感知 list 成败。"""


class BilibiliUploader(BaseCliUploader):
    """B 站上传器(走 biliup CLI subprocess)"""

    def __init__(
        self,
        title: str,
        file_path: str,
        tags: list,
        account_file: str,
        desc: str = "",
        publish_strategy: PublishStrategy = PublishStrategy.IMMEDIATE,
        tid: int = DEFAULT_TID,
    ):
        self.title = title
        self.file_path = file_path
        self.tags = tags if tags is not None else []
        self.account_file = account_file
        self.desc = desc
        self.tid = tid

    @classmethod
    @login_check
    async def cookie_auth(cls, account_file: str) -> bool:
        """用 biliup renew 验证 cookie 是否有效。

        renew 幂等且查询超时 60s 较短,偶发网络抖动(如代理瞬断)会导致 NET-001
        误报;查询命令超时后静默重试一次,仍超时才向上抛。
        """
        if not os.path.exists(account_file):
            return False
        try:
            result = await run_biliup_command_async(["-u", account_file, "renew"])
        except subprocess.TimeoutExpired:
            result = await run_biliup_command_async(["-u", account_file, "renew"])
        if result.returncode == 0:
            bilibili_logger.success("[+] cookie 有效")
            return True
        detail = ((result.stderr or "") + "\n" + (result.stdout or "")).lower()
        if any(marker in detail for marker in (
            "cookie expired", "cookies expired", "cookie 已失效", "cookie失效",
            "账号未登录", "账号未登陆", "未登录", "not logged in", "please login",
        )):
            return False
        raise classify_login_exception(RuntimeError(detail))

    @classmethod
    async def cookie_gen(cls, account_file: str) -> bool:
        """扫码登录 B站, 保存 biliup 格式 cookie。

        biliup login 要求 TTY 且先弹登录方式菜单(默认停在短信登录):
        POSIX 下用 pty 驱动自动选择"扫码登录"并转发二维码输出,Agent 等
        无终端环境也能完成;Windows 保持独立控制台原行为。
        """
        resolved = str(Path(account_file).resolve())
        bilibili_logger.info(f"启动 biliup 扫码登录, cookie 将保存到: {resolved}")
        ensure_dir(Path(resolved).parent)
        if _IS_WINDOWS:
            result = await run_biliup_command_async(["-u", resolved, "login"], interactive=True)
        else:
            result = await run_biliup_login_pty_async(
                ["-u", resolved, "login"], str(Path(resolved).parent)
            )
        if result.returncode == 0 and os.path.exists(resolved):
            bilibili_logger.success("biliup 登录成功, cookie 已保存")
            return True
        bilibili_logger.error(f"biliup 登录失败, returncode={result.returncode}")
        return False

    @classmethod
    async def setup(
        cls,
        account_file: str,
        handle: bool = False,
        return_detail: bool = False,
        qrcode_callback=None,
        headless: bool = True,
    ):
        """5-param signature for dispatch compatibility.

        return_detail/qrcode_callback/headless are ignored (CLI platform -
        biliup doesn't support QR callbacks or headless mode).
        """
        if not os.path.exists(account_file) or not await cls.cookie_auth(account_file):
            if not handle:
                return False
            bilibili_logger.error("cookie 不存在或已失效, 即将启动 biliup 登录, 请扫码")
            return await cls.cookie_gen(account_file)
        return True

    async def _list_bvs(self, *, strict: bool = False) -> set[str]:
        """跑 biliup list,返回当前账号所有 BV 集合。命令失败返回空集,不抛异常。

        strict=True 时命令失败改为抛 _BiliupListCommandError,
        供 _list_bvs_with_status 感知 list 成败。
        """
        result = await run_biliup_command_async(["-u", self.account_file, "list"])
        if result.returncode != 0:
            bilibili_logger.warning(f"biliup list 失败,返回空集: {(result.stderr or '').strip()[:200]}")
            if strict:
                raise _BiliupListCommandError((result.stderr or "").strip()[:200])
            return set()
        bvs: set[str] = set()
        for line in (result.stdout or "").splitlines():
            parts = line.split("\t", 2)
            if parts and parts[0].startswith("BV"):
                bvs.add(parts[0])
        return bvs

    async def _list_bvs_with_status(self) -> tuple[set[str], bool]:
        """跑 biliup list,返回 (BV 集合, list 是否成功)。命令失败或超时返回 (空集, False)。"""
        try:
            return await self._list_bvs(strict=True), True
        except (subprocess.TimeoutExpired, _BiliupListCommandError):
            return set(), False

    async def _match_bv_by_title(self) -> str | None:
        """fallback: 在 biliup list 里找 title 等于 self.title 的行,返回 BV。"""
        result = await run_biliup_command_async(["-u", self.account_file, "list"])
        if result.returncode != 0:
            return None
        matches: list[str] = []
        for line in (result.stdout or "").splitlines():
            parts = line.split("\t", 2)
            if len(parts) >= 2 and parts[0].startswith("BV") and parts[1] == self.title:
                matches.append(parts[0])
        if not matches:
            return None
        if len(matches) > 1:
            bilibili_logger.warning(f"title 匹配到多个 BV: {matches},取第一个")
        return matches[0]

    async def _capture_bv_after_upload(self, before_bvs: set[str], max_retries: int = 3, delay: float = 2.0) -> str | None:
        """上传后轮询 biliup list,找本次上传产生的新 BV。

        - 1 个新 BV: 返回它(主路径)
        - 0 个新 BV: sleep 后重试
        - >1 个新 BV: 立刻 fallback 到 title 匹配
        - 重试耗尽: fallback 到 title 匹配
        """
        for attempt in range(max_retries):
            after_bvs = await self._list_bvs()
            new_bvs = after_bvs - before_bvs
            if len(new_bvs) == 1:
                return next(iter(new_bvs))
            if len(new_bvs) > 1:
                bilibili_logger.warning(f"diff 出 {len(new_bvs)} 个新 BV,fallback 到 title 匹配: {new_bvs}")
                return await self._match_bv_by_title()
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
        bilibili_logger.warning(f"重试 {max_retries} 次仍未拿到新 BV,fallback 到 title 匹配")
        return await self._match_bv_by_title()

    @staticmethod
    def _is_stale_login_upload_failure(detail: str) -> bool:
        """cookie renew 通过但上传 token 已失效的特征(2026-09-18 定因)。"""
        return bool(_STALE_LOGIN_UPLOAD_FAILURE.search(detail))

    async def _recover_stale_login(self) -> PlatformResultExtras:
        """上传 token 失效:重新扫码登录后整体重试一次;只恢复一次。"""
        if getattr(self, "_stale_login_recovered", False):
            message = "重新登录后上传仍失败,可能是网络或 B站上传线路问题"
            bilibili_logger.error(message)
            return {"success": False, "message": message}
        self._stale_login_recovered = True
        bilibili_logger.warning("cookie 校验通过但上传 token 已失效,即将重新扫码登录后重试上传")
        try:
            login_ok = await self.cookie_gen(self.account_file)
        except subprocess.TimeoutExpired:
            login_ok = False
        if not login_ok:
            return {
                "success": False,
                "message": "cookie 校验通过但上传 token 已失效,重新扫码登录未完成",
                "account_issue": True,
                "issue_type": "login_expired",
                "error_code": "AUTH-001",
                "action": "引导用户在终端二维码中完成 B站 扫码登录后重试",
                "safe_to_retry": True,
            }
        return await self.upload()

    async def upload(self) -> PlatformResultExtras:
        """用 biliup 上传视频到 B站。

        逐步异步执行 biliup；取消时回收当前进程，不再启动后续投稿。
        上传成功后会尝试抓取本次发布视频的公开链接,写入 result_url。
        抓取失败不影响发布成功状态(发布已成功,只是缺链接)。
        """
        tag_str = ",".join(self.tags) if isinstance(self.tags, list) else str(self.tags)
        if not os.path.exists(self.file_path):
            return {"success": False, "message": f"视频文件不存在: {self.file_path}"}

        before_bvs, list_ok = await self._list_bvs_with_status()

        args = [
            "-u", self.account_file,
            "upload",
            self.file_path,
            "--title", self.title,
            "--desc", self.desc or "",
            "--tag", tag_str,
            "--tid", str(self.tid),
        ]
        bilibili_logger.info(f"biliup 上传: {self.file_path}, title={self.title}, tid={self.tid}")
        try:
            result = await run_biliup_command_async(args)
        except subprocess.TimeoutExpired as exc:
            # 上传可能已部分/全部完成,自动重发有重复投稿风险,必须人工确认
            message = (
                f"biliup 上传超时({exc.timeout} 秒),结果不明,"
                "请到 B站创作中心人工确认后再决定是否重发"
            )
            bilibili_logger.error(message)
            return {"success": False, "safe_to_retry": False, "message": message}
        stdout = result.stdout or ""
        stderr = result.stderr or ""

        if result.returncode != 0:
            if self._is_stale_login_upload_failure(f"{stderr or ''}\n{stdout or ''}"):
                return await self._recover_stale_login()
            bilibili_logger.error(f"biliup 上传失败: {stderr.strip()[:300]}")
            return {"success": False, "message": f"biliup 上传失败: {stderr.strip()[:200]}"}

        bilibili_logger.success(f"biliup 上传成功: {stdout.strip()[:300]}")
        result_dict: PlatformResultExtras = {"success": True, "message": "发布成功"}
        if not list_ok:
            # 上传前 list 失败,before 快照不可信,跳过链接抓取避免拿错 BV
            bilibili_logger.warning("上传前 biliup list 失败,跳过链接抓取,请到 B站创作中心查看")
            return result_dict
        try:
            bv = await self._capture_bv_after_upload(before_bvs)
        except Exception as exc:
            # 发布已成功,链接查询失败不能把结果改失败
            bilibili_logger.warning(f"抓取内容链接失败(不影响发布结果): {exc}")
            bv = None
        if bv:
            url = f"https://www.bilibili.com/video/{bv}"
            result_dict["result_url"] = url
            bilibili_logger.success(f"已抓取内容链接: {url}")
        else:
            bilibili_logger.warning("未能抓取 BV,请到 B站创作中心查看")
        return result_dict


# Module-level wrappers for dispatch.py compatibility
async def cookie_auth(account_file):
    return await BilibiliUploader.cookie_auth(account_file)


async def bilibili_cookie_gen(account_file) -> bool:
    """交互式扫码登录 B站 - 委托 BilibiliUploader.cookie_gen"""
    return await BilibiliUploader.cookie_gen(account_file)


async def bilibili_setup(account_file, handle=False, return_detail=False, qrcode_callback=None, headless=True):
    return await BilibiliUploader.setup(account_file, handle, return_detail, qrcode_callback, headless)


async def upload(account_file, video_file, title, desc="", tags=None, tid=DEFAULT_TID) -> dict:
    """用 biliup 上传视频到 B站 - 委托 BilibiliUploader.upload (向后兼容)"""
    uploader = BilibiliUploader(
        title=title, file_path=video_file, tags=tags if tags is not None else [],
        account_file=account_file, desc=desc, tid=tid,
    )
    return await uploader.upload()
