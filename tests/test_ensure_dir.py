# -*- coding: utf-8 -*-
"""ensure_dir:防御式目录创建 + 全仓禁止裸 mkdir(exist_ok)。

背景:WorkBuddy 等 Agent 沙箱的文件系统 shim 代理 Path.mkdir 时,对
"目录已存在"错误处理不当,标准 exist_ok=True 语义被破坏——opub 在
`import uploader` 阶段就会崩。统一走 ensure_dir(先查存在再建,容忍
FileExistsError 竞态),并用 AST 扫描锁定源码不再出现裸 mkdir 调用。
"""
import ast
from pathlib import Path

from utils.fs import ensure_dir

SOURCE_DIRS = ("uploader", "publish", "utils")
SOURCE_FILES = ("conf.py", "login_tencent.py", "publish_all.py")


def test_ensure_dir_creates_missing_directory_with_parents(tmp_path):
    target = tmp_path / "a" / "b"
    ensure_dir(target)
    assert target.is_dir()


def test_ensure_dir_existing_directory_is_silent_noop(tmp_path, monkeypatch):
    """沙箱 shim 场景:目录已存在时调用 mkdir 会抛,ensure_dir 根本不调 mkdir。"""
    target = tmp_path / "existing"
    target.mkdir()

    def boom(*args, **kwargs):
        raise AssertionError("mkdir called on an existing directory")

    monkeypatch.setattr(type(target), "mkdir", boom)
    ensure_dir(target)


def test_ensure_dir_tolerates_creation_race():
    """exists() 与 mkdir() 之间目录被并发创建时,FileExistsError 被容忍。"""

    class RacyDir:
        def exists(self):
            return False

        def mkdir(self, parents=False):
            raise FileExistsError

    ensure_dir(RacyDir())


def _iter_source_files():
    for source_dir in SOURCE_DIRS:
        yield from Path(source_dir).rglob("*.py")
    for name in SOURCE_FILES:
        path = Path(name)
        if path.exists():
            yield path


def test_no_bare_mkdir_calls_outside_helper():
    offenders = []
    for path in _iter_source_files():
        if path == Path("utils/fs.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "mkdir"
            ):
                offenders.append(f"{path}:{node.lineno}")
    assert offenders == [], f"direct mkdir() calls must go through ensure_dir: {offenders}"
