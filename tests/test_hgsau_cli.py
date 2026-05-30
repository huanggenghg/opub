import unittest
from pathlib import Path

import hgsau_cli


class HgsauPackagingTests(unittest.TestCase):
    def test_pyproject_exposes_only_hgsau_console_script(self):
        pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
        py_modules_line = next(
            line for line in pyproject.splitlines() if line.startswith("py-modules = ")
        )

        self.assertIn('name = "hgsau"', pyproject)
        self.assertIn('hgsau = "hgsau_cli:main"', pyproject)
        self.assertNotIn('sau = "sau_cli:main"', pyproject)
        self.assertEqual(py_modules_line, 'py-modules = ["conf", "hgsau_cli", "publish_all"]')
        self.assertNotIn('"sau_cli"', py_modules_line)

    def test_hgsau_cli_module_exists(self):
        self.assertTrue(hasattr(hgsau_cli, "build_parser"))
        self.assertTrue(hasattr(hgsau_cli, "main"))

    def test_parser_prog_is_hgsau(self):
        parser = hgsau_cli.build_parser()

        self.assertEqual(parser.prog, "hgsau")


if __name__ == "__main__":
    unittest.main()
