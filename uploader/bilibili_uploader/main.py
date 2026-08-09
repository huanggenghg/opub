# -*- coding: utf-8 -*-
"""B站上传器 - 基于 biliup CLI (wrapped in BilibiliUploader class)

与其他平台的 playwright+cookie 方案不同, B站使用社区维护的 biliup CLI
(https://github.com/biliup/biliup), 通过 B站内部上传 API 完成, 更稳定。
登录/上传/校验均通过 subprocess 调用 biliup 二进制完成。
"""
from __future__ import annotations

import os
from pathlib import Path

from uploader.base_video import BaseCliUploader, PlatformResultExtras, PublishStrategy
from uploader.bilibili_uploader.runtime import run_biliup_command
from utils.log import bilibili_logger

# 默认投稿分区: 171=个人动态
DEFAULT_TID = 171


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
    async def cookie_auth(cls, account_file: str) -> bool:
        """用 biliup renew 验证 cookie 是否有效。"""
        if not os.path.exists(account_file):
            return False
        result = run_biliup_command(["-u", account_file, "renew"])
        if result.returncode == 0:
            bilibili_logger.success("[+] cookie 有效")
            return True
        stderr = (result.stderr or "").strip()
        bilibili_logger.error(f"cookie 失效: {stderr[:200]}")
        return False

    @classmethod
    async def cookie_gen(cls, account_file: str) -> bool:
        """交互式扫码登录 B站, 保存 biliup 格式 cookie。"""
        bilibili_logger.info(f"启动 biliup 登录, cookie 将保存到: {account_file}")
        Path(account_file).parent.mkdir(parents=True, exist_ok=True)
        result = run_biliup_command(["-u", account_file, "login"], interactive=True)
        if result.returncode == 0 and os.path.exists(account_file):
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

    def _list_bvs(self) -> set[str]:
        """跑 biliup list,返回当前账号所有 BV 集合。命令失败返回空集,不抛异常。"""
        result = run_biliup_command(["-u", self.account_file, "list"])
        if result.returncode != 0:
            bilibili_logger.warning(f"biliup list 失败,返回空集: {(result.stderr or '').strip()[:200]}")
            return set()
        bvs: set[str] = set()
        for line in (result.stdout or "").splitlines():
            parts = line.split("\t", 2)
            if parts and parts[0].startswith("BV"):
                bvs.add(parts[0])
        return bvs

    async def upload(self) -> PlatformResultExtras:
        """用 biliup 上传视频到 B站。

        Returns PlatformResultExtras without raw_output (biliup stdout
        is logged but not returned - no consumer in the codebase).
        """
        tag_str = ",".join(self.tags) if isinstance(self.tags, list) else str(self.tags)
        if not os.path.exists(self.file_path):
            return {"success": False, "message": f"视频文件不存在: {self.file_path}"}

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
        result = run_biliup_command(args)
        stdout = result.stdout or ""
        stderr = result.stderr or ""

        if result.returncode == 0:
            bilibili_logger.success(f"biliup 上传成功: {stdout.strip()[:300]}")
            return {"success": True, "message": "发布成功"}
        bilibili_logger.error(f"biliup 上传失败: {stderr.strip()[:300]}")
        return {"success": False, "message": f"biliup 上传失败: {stderr.strip()[:200]}"}


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
