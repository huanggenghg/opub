# -*- coding: utf-8 -*-
"""biliup 交互式登录的 pty 驱动(POSIX)。

biliup login 要求 TTY——无终端环境(Agent Bash、重定向输出)直接
`IO error: not a terminal` 失败;有终端时也先弹"选择登录方式"菜单,
默认停在"短信登录"。本模块用伪终端驱动登录:自动选择"扫码登录",
把二维码输出实时转发到进程 stderr(终端用户直接可见;Agent 环境进入
命令输出供转述),并把 biliup 落在 cwd 的 qrcode.png 在登录结束后清理。
Windows 不适用(pty 是 POSIX 模块),由 runtime 的独立控制台行为接管。
"""
from __future__ import annotations

import asyncio
import functools
import os
import re
import select
import subprocess
import sys
import threading
import time
from typing import Optional

from uploader.bilibili_uploader.runtime import _resolve_command_timeout, require_biliup_binary
from utils.log import bilibili_logger

MENU_TITLE = "选择一种登录方式"
QRCODE_OPTION = "扫码登录"
_QRCODE_IMAGE_NAME = "qrcode.png"
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def count_menu_down_presses(buffered: str) -> Optional[int]:
    """从(可能含 ANSI 重绘的)菜单文本计算到达"扫码登录"需要的 ↓ 次数。

    菜单会被 dialoguer 多次重绘,取最后一次出现的标题之后的选项区块;
    找不到标题、选项或"扫码登录"时返回 None,由调用方按已知布局兜底。
    """
    plain_lines = [_ANSI_ESCAPE.sub("", line) for line in buffered.splitlines()]
    title_indexes = [i for i, line in enumerate(plain_lines) if MENU_TITLE in line]
    if not title_indexes:
        return None
    items: list[str] = []
    cursor_index = None
    for line in plain_lines[title_indexes[-1] + 1:]:
        text = line.strip()
        if not text:
            if items:
                break
            continue
        if text.startswith("✔"):
            break  # 菜单已确认,后续不再是选项
        is_cursor = text.startswith("❯")
        label = text.lstrip("❯").strip()
        items.append(label)
        if is_cursor:
            cursor_index = len(items) - 1
    if not items or cursor_index is None:
        return None
    target_index = next((i for i, label in enumerate(items) if QRCODE_OPTION in label), None)
    if target_index is None:
        return None
    return (target_index - cursor_index) % len(items)


def _mirror_to_stderr(data: bytes) -> None:
    """实时转发 pty 输出(二维码/进度),json 模式下也不污染 stdout。"""
    try:
        sys.stderr.buffer.write(data)
        sys.stderr.buffer.flush()
    except (AttributeError, OSError, ValueError):
        pass


def _drain(master: int, captured: bytearray) -> None:
    while True:
        ready, _, _ = select.select([master], [], [], 0.2)
        if not ready:
            return
        try:
            data = os.read(master, 65536)
        except OSError:
            return
        if not data:
            return
        captured.extend(data)
        _mirror_to_stderr(data)


def run_biliup_login_pty(
    arguments: list[str],
    cwd: str,
    timeout: float,
    stop_event: Optional[threading.Event] = None,
) -> subprocess.CompletedProcess[str]:
    """在 pty 中驱动 biliup login,阻塞直至进程退出;超时抛 TimeoutExpired。

    qrcode.png 由 biliup 写在 cwd(cookie 目录),登录结束即作废并清理。
    """
    import pty  # POSIX 专属模块,延迟导入避免 Windows 导入失败

    command = [str(require_biliup_binary()), *arguments]
    qrcode_path = os.path.join(cwd, _QRCODE_IMAGE_NAME)
    master, slave = pty.openpty()
    proc = subprocess.Popen(
        command, stdin=slave, stdout=slave, stderr=slave, cwd=cwd, close_fds=True,
    )
    os.close(slave)
    captured = bytearray()
    menu_handled = False
    qrcode_hinted = False
    timed_out = False
    deadline = time.monotonic() + timeout
    try:
        while True:
            if proc.poll() is not None:
                _drain(master, captured)
                break
            if stop_event is not None and stop_event.is_set():
                proc.kill()
                _drain(master, captured)
                break
            if time.monotonic() > deadline:
                timed_out = True
                proc.kill()
                _drain(master, captured)
                break
            ready, _, _ = select.select([master], [], [], 0.5)
            if not qrcode_hinted and os.path.exists(qrcode_path):
                # 二维码渲染后 biliup 静默等待扫码,提示检查不能依赖后续数据
                bilibili_logger.info(
                    f"二维码图片已保存: {qrcode_path},终端二维码无法扫描时可打开该图片"
                )
                qrcode_hinted = True
            if not ready:
                continue
            try:
                data = os.read(master, 65536)
            except OSError:
                break
            if not data:
                continue
            captured.extend(data)
            _mirror_to_stderr(data)
            text = captured.decode("utf-8", "replace")
            if not menu_handled and MENU_TITLE in text and QRCODE_OPTION in text:
                # 等菜单渲染稳定后自动选择"扫码登录"
                time.sleep(0.8)
                downs = count_menu_down_presses(text)
                for _ in range(downs if downs is not None else 1):
                    os.write(master, b"\x1b[B")
                    time.sleep(0.15)
                time.sleep(0.3)
                os.write(master, b"\r")
                menu_handled = True
        exit_code = proc.wait()
    finally:
        try:
            os.close(master)
        except OSError:
            pass
        # 登录已结束,二维码作废
        try:
            os.remove(qrcode_path)
        except OSError:
            pass
    if timed_out:
        raise subprocess.TimeoutExpired(
            command, timeout, output=captured.decode("utf-8", "replace")
        )
    return subprocess.CompletedProcess(
        command, exit_code, stdout=captured.decode("utf-8", "replace"), stderr=None,
    )


async def run_biliup_login_pty_async(
    arguments: list[str],
    cwd: str,
    timeout: Optional[float] = None,
) -> subprocess.CompletedProcess[str]:
    """可取消的 pty 登录入口;取消时先终止 biliup 子进程再抛出。"""
    effective_timeout = _resolve_command_timeout(arguments, timeout)
    loop = asyncio.get_running_loop()
    stop_event = threading.Event()
    task = loop.run_in_executor(
        None,
        functools.partial(run_biliup_login_pty, arguments, cwd, effective_timeout, stop_event),
    )
    try:
        return await asyncio.shield(task)
    except BaseException:
        stop_event.set()
        cleanup = asyncio.gather(task, return_exceptions=True)
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                # 清理未完成前的新取消不中断排空
                continue
        raise
