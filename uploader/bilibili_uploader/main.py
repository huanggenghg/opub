# -*- coding: utf-8 -*-
"""B站上传器 - 基于 biliup CLI

与其他平台的 playwright+cookie 方案不同, B站使用社区维护的 biliup CLI
(https://github.com/biliup/biliup), 通过 B站内部上传 API 完成, 更稳定。
登录/上传/校验均通过 subprocess 调用 biliup 二进制完成。
"""
import os
from pathlib import Path

from uploader.bilibili_uploader.runtime import run_biliup_command
from utils.log import bilibili_logger

# 默认投稿分区: 171=个人动态
DEFAULT_TID = 171


async def bilibili_cookie_gen(account_file) -> bool:
    """交互式扫码登录 B站, 保存 biliup 格式 cookie。"""
    bilibili_logger.info(f"启动 biliup 登录, cookie 将保存到: {account_file}")
    Path(account_file).parent.mkdir(parents=True, exist_ok=True)
    result = run_biliup_command(["-u", account_file, "login"], interactive=True)
    if result.returncode == 0 and os.path.exists(account_file):
        bilibili_logger.success("biliup 登录成功, cookie 已保存")
        return True
    bilibili_logger.error(f"biliup 登录失败, returncode={result.returncode}")
    return False


async def cookie_auth(account_file) -> bool:
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


async def bilibili_setup(account_file, handle=False) -> bool:
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            return False
        bilibili_logger.error("cookie 不存在或已失效, 即将启动 biliup 登录, 请扫码")
        return await bilibili_cookie_gen(account_file)
    return True


async def upload(account_file, video_file, title, desc="", tags=None, tid=DEFAULT_TID) -> dict:
    """用 biliup 上传视频到 B站。

    Args:
        account_file: biliup 格式 cookie 文件路径
        video_file: 视频文件绝对路径
        title: 视频标题
        desc: 视频简介
        tags: 标签列表 (或逗号分隔字符串)
        tid: 投稿分区, 默认 171=个人动态

    Returns:
        {"success": bool, "message": str, ...}
    """
    if tags is None:
        tags = []
    tag_str = ",".join(tags) if isinstance(tags, list) else str(tags)
    if not os.path.exists(video_file):
        return {"success": False, "message": f"视频文件不存在: {video_file}"}

    args = [
        "-u", account_file,
        "upload",
        video_file,
        "--title", title,
        "--desc", desc or "",
        "--tag", tag_str,
        "--tid", str(tid),
    ]
    bilibili_logger.info(f"biliup 上传: {video_file}, title={title}, tid={tid}")
    result = run_biliup_command(args)
    stdout = result.stdout or ""
    stderr = result.stderr or ""

    if result.returncode == 0:
        bilibili_logger.success(f"biliup 上传成功: {stdout.strip()[:300]}")
        return {"success": True, "message": "发布成功", "raw_output": stdout}
    bilibili_logger.error(f"biliup 上传失败: {stderr.strip()[:300]}")
    return {"success": False, "message": f"biliup 上传失败: {stderr.strip()[:200]}"}
