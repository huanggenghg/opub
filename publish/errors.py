# -*- coding: utf-8 -*-
"""Agent 可消费的错误输出:语义化退出码 + 错误码格式化"""
import sys
from publish.output import record_error

EXIT_OK = 0
EXIT_PARTIAL_FAIL = 1
EXIT_ALL_FAIL = 2
EXIT_CONFIG_ERROR = 10
EXIT_ENV_ERROR = 11
EXIT_AUTH_ERROR = 12
EXIT_LICENSE_ERROR = 13


def print_error(code: str, message: str, action: str) -> None:
    record_error(code, message, action)
    print(f"[opub] {code}: {message}。建议: {action}", file=sys.stderr)
