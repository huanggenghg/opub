"""验证 examples/ 里的脚本不再调用已删除的别名方法。

sub-project B Task 9 删除了各平台 uploader 的 main() / <platform>_upload_video() /
<platform>_upload_note() 别名 wrapper。sub-project C Task 4 修复 examples/ 里的
调用方,改用 app.upload()。这个测试扫描 examples/ 确保没有残留的已删除别名调用。
"""
import re
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"

# 已删除的别名方法名(sub-project B Task 9 删除)
DEPRECATED_CALL_PATTERNS = [
    r"\.main\(\)",
    r"\.douyin_upload_video\(\)",
    r"\.douyin_upload_note\(\)",
    r"\.tencent_upload_video\(\)",
    r"\.tencent_upload_note\(\)",
    r"\.xiaohongshu_upload_video\(\)",
    r"\.xiaohongshu_upload_note\(\)",
]


def test_no_deprecated_alias_calls_in_examples():
    """扫描 examples/ 所有 .py 文件,确保没有调用已删除的别名方法。"""
    violations = []
    for py_file in EXAMPLES_DIR.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for pattern in DEPRECATED_CALL_PATTERNS:
            # 匹配 app.main() / app.douyin_upload_video() 等调用
            for match in re.finditer(pattern, content):
                line_num = content[:match.start()].count("\n") + 1
                violations.append(f"{py_file.name}:{line_num} -> {match.group()}")
    assert not violations, (
        f"examples/ 里有 {len(violations)} 处调用已删除的别名方法,改用 app.upload():\n"
        + "\n".join(violations)
    )


def test_examples_use_upload_method():
    """验证 examples/ 里的脚本调用了 app.upload()。"""
    py_files = list(EXAMPLES_DIR.rglob("*.py"))
    # 排除 __init__.py 等空文件
    upload_callers = []
    for py_file in py_files:
        content = py_file.read_text(encoding="utf-8")
        if "app.upload()" in content or "asyncio.run(app.upload()" in content:
            upload_callers.append(py_file.name)
    # 至少 6 个脚本应该调用 app.upload()
    assert len(upload_callers) >= 6, (
        f"期望至少 6 个 examples 脚本调用 app.upload(),实际 {len(upload_callers)} 个: "
        f"{upload_callers}"
    )
