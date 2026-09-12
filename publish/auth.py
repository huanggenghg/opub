"""Lightweight, sanitized failures for login checks (no browser dependencies)."""
from __future__ import annotations

import json
import subprocess
from functools import wraps


_ERROR_DETAILS = {
    'network': ('NET-001', '登录检查时网络连接失败或超时，尚未确认登录失效', '检查网络连接后重新运行'),
    'page': ('PAGE-001', '登录检查页面未能识别，尚未确认登录失效', '检查平台页面是否可访问；若仍失败，请更新 opub 或联系支持'),
    'environment': ('ENV-006', '登录检查所需的本机环境或账号文件不可用', '检查浏览器、平台工具与账号文件；修复环境后重新运行'),
}


class LoginCheckError(RuntimeError):
    """An uncertain check must not trigger automatic QR login or publishing retry."""

    def __init__(self, kind: str):
        self.kind = kind
        self.error_code, message, self.action = _ERROR_DETAILS[kind]
        super().__init__(message)

    def to_result(self) -> dict:
        return {
            'success': False,
            'message': str(self),
            'account_issue': False,
            'issue_type': self.kind + '_error',
            'error_code': self.error_code,
            'action': self.action,
            'safe_to_retry': False,
        }


def classify_login_exception(exc: Exception) -> LoginCheckError:
    """Inspect diagnostics only to classify; never expose raw exception details."""
    if isinstance(exc, LoginCheckError):
        return exc
    detail = str(exc).lower()
    if isinstance(exc, (FileNotFoundError, PermissionError, ImportError, json.JSONDecodeError)) or any(
        marker in detail for marker in (
            'browsertype.launch', 'executable doesn\'t exist', 'missing executable',
            'target page, context or browser has been closed', 'browser closed',
            'error reading storage state', 'failed to launch',
            "module 'greenlet'", "module 'patchright'",
        )
    ):
        return LoginCheckError('environment')
    # Locator waits indicate an unrecognized/slow page, not a network diagnosis.
    if any(marker in detail for marker in ('locator.', 'wait_for_selector', 'wait_for_url')):
        return LoginCheckError('page')
    if isinstance(exc, (ConnectionError, TimeoutError, subprocess.TimeoutExpired)) or any(
        marker in detail for marker in (
            'net::err_', 'network', 'connection reset', 'connection refused',
            'connection error', 'dns', 'timed out', 'timeout', 'error sending request',
        )
    ):
        return LoginCheckError('network')
    return LoginCheckError('page')


def login_check(check):
    """Classify failures including browser startup/teardown and CLI invocation."""
    @wraps(check)
    async def checked(*args, **kwargs):
        try:
            return await check(*args, **kwargs)
        except LoginCheckError:
            raise
        except Exception as exc:
            raise classify_login_exception(exc) from None
    return checked
