import ast
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE_TEST_SOURCES = (
    REPO_ROOT / "tests/test_license_e2e.py",
    REPO_ROOT / "tests/test_package_build.py",
)


def _public_client_sources():
    return (
        REPO_ROOT / "publish_all.py",
        REPO_ROOT / "publish/orchestrator.py",
        REPO_ROOT / "publish/errors.py",
        *sorted((REPO_ROOT / "publish/licensing").glob("*.py")),
    )


def _annotations(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            yield node.annotation
        elif isinstance(node, ast.arg) and node.annotation is not None:
            yield node.annotation
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns is not None:
                yield node.returns


class SupportedPythonSyntaxTests(unittest.TestCase):
    def test_xiaohongshu_module_compiles(self):
        source_path = (
            Path(__file__).parents[1]
            / "uploader"
            / "xiaohongshu_uploader"
            / "main.py"
        )
        source = source_path.read_text(encoding="utf-8")

        try:
            compile(source, str(source_path), "exec")
        except SyntaxError as exc:
            self.fail(f"xiaohongshu module must compile on supported Python: {exc}")

    def test_release_public_client_sources_parse_with_python_39_grammar(self):
        for source_path in _public_client_sources():
            with self.subTest(source=source_path.relative_to(REPO_ROOT)):
                source = source_path.read_text(encoding="utf-8")
                try:
                    ast.parse(
                        source,
                        filename=str(source_path),
                        mode="exec",
                        feature_version=(3, 9),
                    )
                except SyntaxError as exc:
                    self.fail(
                        f"{source_path.relative_to(REPO_ROOT)} must parse with "
                        f"Python 3.9 grammar: {exc}"
                    )

    def test_release_tests_avoid_python_310_union_annotation_syntax(self):
        violations = []
        for source_path in RELEASE_TEST_SOURCES:
            tree = ast.parse(
                source_path.read_text(encoding="utf-8"), filename=str(source_path)
            )
            for annotation in _annotations(tree):
                for node in ast.walk(annotation):
                    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
                        violations.append(
                            f"{source_path.relative_to(REPO_ROOT)}:{node.lineno}"
                        )

        self.assertEqual(
            [],
            violations,
            "Python >=3.9 release tests must use Optional/Union rather than PEP 604: "
            + ", ".join(violations),
        )


if __name__ == "__main__":
    unittest.main()
