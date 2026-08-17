import contextlib
import io
import unittest

from publish.errors import (
    EXIT_ALL_FAIL,
    EXIT_AUTH_ERROR,
    EXIT_CONFIG_ERROR,
    EXIT_ENV_ERROR,
    EXIT_OK,
    EXIT_PARTIAL_FAIL,
    print_error,
)


class ExitCodeConstantsTests(unittest.TestCase):
    def test_exit_code_values(self):
        self.assertEqual(EXIT_OK, 0)
        self.assertEqual(EXIT_PARTIAL_FAIL, 1)
        self.assertEqual(EXIT_ALL_FAIL, 2)
        self.assertEqual(EXIT_CONFIG_ERROR, 10)
        self.assertEqual(EXIT_ENV_ERROR, 11)
        self.assertEqual(EXIT_AUTH_ERROR, 12)


class PrintErrorTests(unittest.TestCase):
    def test_output_format_goes_to_stderr(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            print_error("CFG-001", "配置文件不存在: /tmp/x.ini", "提供 --config 或同时指定 --platforms 和 --video")
        self.assertEqual(
            stderr.getvalue(),
            "[opub] CFG-001: 配置文件不存在: /tmp/x.ini。建议: 提供 --config 或同时指定 --platforms 和 --video\n",
        )


if __name__ == "__main__":
    unittest.main()
