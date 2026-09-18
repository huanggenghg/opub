# -*- coding: utf-8 -*-
"""防御式目录创建:供 Agent 沙箱环境使用的文件系统工具。"""
from __future__ import annotations

from pathlib import Path


def ensure_dir(path: Path, parents: bool = True) -> None:
    """创建目录,已存在时静默跳过。

    不直接用 mkdir(exist_ok=True):部分 Agent 沙箱(如 WorkBuddy)的
    文件系统 shim 代理 Path.mkdir 时对"目录已存在"错误处理不当,标准
    exist_ok 语义被破坏,opub 在模块导入阶段即崩。先检查存在性再创建;
    FileExistsError 竞态一并容忍(单进程使用,无并发正确性顾虑)。
    """
    if path.exists():
        return
    try:
        path.mkdir(parents=parents)
    except FileExistsError:
        pass
