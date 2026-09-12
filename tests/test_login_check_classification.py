"""Login checks must distinguish explicit expiry from uncertain failures."""
import asyncio
import json
import subprocess
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from uploader.base_video import BaseBrowserUploader
from uploader.douyin_uploader.main import DouYinBaseUploader
from uploader.baijiahao_uploader.main import BaiJiaHaoVideo
from uploader.weibo_uploader.main import WeiboBaseUploader
from uploader.bilibili_uploader.main import BilibiliUploader


class AuthProbe(BaseBrowserUploader):
    UPLOAD_URL = 'https://example.com/upload'
    LOGIN_MARKERS = ['/login']


BROWSER_CHECKS = (
    (AuthProbe, 'uploader.base_video'),
    (DouYinBaseUploader, 'uploader.douyin_uploader.main'),
    (BaiJiaHaoVideo, 'uploader.baijiahao_uploader.main'),
    (WeiboBaseUploader, 'uploader.weibo_uploader.main'),
)


def browser_check(cls, module, *, url=None, navigation_error=None, launch_error=None,
                  visible_selector=None, completed=False):
    stack = ExitStack()
    page = MagicMock()
    page.url = url or cls.UPLOAD_URL
    page.goto = AsyncMock(side_effect=navigation_error)
    page.wait_for_timeout = AsyncMock()
    page.wait_for_url = AsyncMock()

    def locator(selector, **kwargs):
        selector = selector.replace('"', '')
        loc = MagicMock()
        loc.first = loc
        loc.count = AsyncMock(return_value=int(selector == visible_selector))
        loc.is_visible = AsyncMock(return_value=selector == visible_selector)
        return loc

    page.locator.side_effect = locator
    page.get_by_text.side_effect = lambda text, **kw: locator('text=' + text)
    page.get_by_role.side_effect = lambda role, **kw: locator('role=' + role)
    browser = SimpleNamespace(close=AsyncMock())
    pw = MagicMock()
    pw.__aenter__ = AsyncMock(return_value=pw)
    pw.__aexit__ = AsyncMock(return_value=False)
    stack.enter_context(patch(module + '.os.path.exists', return_value=True))
    stack.enter_context(patch(module + '.async_playwright', return_value=pw))
    stack.enter_context(patch.object(cls, '_launch_browser', AsyncMock(return_value=browser, side_effect=launch_error)))
    stack.enter_context(patch.object(cls, '_init_context', AsyncMock(return_value=SimpleNamespace(new_page=AsyncMock(return_value=page)))))
    if cls is AuthProbe:
        stack.enter_context(patch.object(cls, 'is_login_completed', AsyncMock(return_value=completed)))
    elif cls is DouYinBaseUploader:
        stack.enter_context(patch(module + '._wait_for_douyin_publish_marker', AsyncMock()))
    elif cls is WeiboBaseUploader and not navigation_error and not launch_error:
        from uploader.base_video import LoginExpiredError
        error = LoginExpiredError() if '/login' in page.url else RuntimeError('未找到视频上传入口')
        stack.enter_context(patch(module + '._wait_for_weibo_upload_button', AsyncMock(side_effect=error)))
    return stack, page, browser


class BrowserClassificationTests(unittest.TestCase):
    def assert_check_error(self, cls, kind):
        with self.assertRaises(RuntimeError) as raised:
            asyncio.run(cls.cookie_auth('/fake/account.json'))
        self.assertEqual(getattr(raised.exception, 'kind', None), kind)
        self.assertFalse(raised.exception.to_result()['safe_to_retry'])

    def test_navigation_network_failure_never_means_expired(self):
        for cls, module in BROWSER_CHECKS:
            with self.subTest(platform=module):
                stack, _, browser = browser_check(cls, module, navigation_error=RuntimeError('net::ERR_CONNECTION_RESET token=secret'))
                with stack:
                    self.assert_check_error(cls, 'network')
                browser.close.assert_awaited_once()

    def test_unknown_page_never_means_expired(self):
        for cls, module in BROWSER_CHECKS:
            with self.subTest(platform=module):
                stack, _, _ = browser_check(cls, module)
                with stack:
                    self.assert_check_error(cls, 'page')

    def test_browser_launch_failure_is_environment(self):
        for cls, module in BROWSER_CHECKS:
            with self.subTest(platform=module):
                stack, _, _ = browser_check(cls, module, launch_error=RuntimeError("BrowserType.launch: Executable doesn't exist at /private/path"))
                with stack:
                    self.assert_check_error(cls, 'environment')

    def test_explicit_login_redirect_is_expired(self):
        for cls, module in BROWSER_CHECKS:
            with self.subTest(platform=module):
                stack, _, _ = browser_check(cls, module, url='https://example.com/login')
                with stack:
                    self.assertFalse(asyncio.run(cls.cookie_auth('/fake/account.json')))

    def test_visible_douyin_login_form_is_expired(self):
        stack, _, _ = browser_check(DouYinBaseUploader, BROWSER_CHECKS[1][1], visible_selector='text=扫码登录')
        with stack:
            self.assertFalse(asyncio.run(DouYinBaseUploader.cookie_auth('/fake/account.json')))

    def test_visible_baijiahao_login_form_is_expired(self):
        stack, _, _ = browser_check(BaiJiaHaoVideo, BROWSER_CHECKS[2][1], visible_selector='text=扫码登录')
        with stack:
            self.assertFalse(asyncio.run(BaiJiaHaoVideo.cookie_auth('/fake/account.json')))

    def test_setup_does_not_start_qr_login_for_uncertain_page(self):
        stack, _, _ = browser_check(AuthProbe, 'uploader.base_video')
        with stack, patch.object(AuthProbe, 'cookie_gen', AsyncMock()) as login:
            from publish.auth import LoginCheckError
            with self.assertRaises(LoginCheckError):
                asyncio.run(AuthProbe.setup('/fake/account.json', handle=True))
        login.assert_not_awaited()


class InheritedPlatformLoginTests(unittest.TestCase):
    def test_explicit_login_form_returns_false_for_inherited_checks(self):
        from uploader.ks_uploader.main import KSBaseUploader
        from uploader.xiaohongshu_uploader.main import XiaoHongShuBaseUploader
        from uploader.tk_uploader.main import TiktokVideo
        cases = (
            (KSBaseUploader, 'main#login-form'),
            (XiaoHongShuBaseUploader, '.login-container'),
            (TiktokVideo, 'select[class*=SelectFormContainer]'),
        )
        for cls, selector in cases:
            with self.subTest(platform=cls.PLATFORM_NAME):
                stack, _, _ = browser_check(cls, 'uploader.base_video', visible_selector=selector)
                with stack:
                    self.assertFalse(asyncio.run(cls.cookie_auth('/fake/account.json')))

    def test_unknown_redirect_is_not_authenticated(self):
        stack, _, _ = browser_check(AuthProbe, 'uploader.base_video', url='https://example.com/unavailable', completed=True)
        with stack:
            from publish.auth import LoginCheckError
            with self.assertRaises(LoginCheckError):
                asyncio.run(AuthProbe.cookie_auth('/fake/account.json'))


class LoginErrorContractTests(unittest.TestCase):
    def test_classifier_returns_stable_sanitized_result(self):
        from publish.auth import classify_login_exception
        cases = [
            (RuntimeError('net::ERR_NAME_NOT_RESOLVED token=secret'), 'network', 'NET-001'),
            (ConnectionError('cookie=secret'), 'network', 'NET-001'),
            (TimeoutError('secret'), 'network', 'NET-001'),
            (RuntimeError('Page.goto: Timeout 60000ms exceeded secret'), 'network', 'NET-001'),
            (RuntimeError('Locator.wait_for: Timeout 5000ms exceeded secret'), 'page', 'PAGE-001'),
            (RuntimeError('BrowserType.launch: missing executable secret'), 'environment', 'ENV-006'),
            (FileNotFoundError('secret'), 'environment', 'ENV-006'),
            (json.JSONDecodeError('secret', '', 0), 'environment', 'ENV-006'),
            (RuntimeError('unknown secret'), 'page', 'PAGE-001'),
        ]
        for exc, kind, code in cases:
            with self.subTest(kind=kind, exc_type=type(exc).__name__):
                result = classify_login_exception(exc).to_result()
                self.assertEqual(result['error_code'], code)
                self.assertEqual(result['issue_type'], kind + '_error')
                self.assertFalse(result['safe_to_retry'])
                self.assertFalse(result['account_issue'])
                self.assertTrue(result['action'])
                self.assertNotIn('secret', json.dumps(result))

    def test_classification_preserves_existing_error(self):
        from publish.auth import LoginCheckError, classify_login_exception
        exc = LoginCheckError('page')
        self.assertIs(classify_login_exception(exc), exc)


class BilibiliLoginClassificationTests(unittest.TestCase):
    def test_renew_failures_only_expire_on_explicit_evidence(self):
        from publish.auth import LoginCheckError
        for stderr, expected in [
            ('cookie expired', False),
            ('账号未登录', False),
            ('request failed: connection reset token=secret', 'network'),
            ('unknown renew response token=secret', 'page'),
        ]:
            with self.subTest(stderr=stderr), patch('uploader.bilibili_uploader.main.os.path.exists', return_value=True), patch('uploader.bilibili_uploader.main.run_biliup_command', return_value=subprocess.CompletedProcess([], 1, '', stderr)):
                if expected is False:
                    self.assertFalse(asyncio.run(BilibiliUploader.cookie_auth('/fake/account.json')))
                else:
                    with self.assertRaises(LoginCheckError) as raised:
                        asyncio.run(BilibiliUploader.cookie_auth('/fake/account.json'))
                    self.assertEqual(raised.exception.kind, expected)
                    self.assertNotIn('secret', str(raised.exception))

    def test_missing_biliup_is_environment_failure(self):
        from publish.auth import LoginCheckError
        with patch('uploader.bilibili_uploader.main.os.path.exists', return_value=True), patch('uploader.bilibili_uploader.main.run_biliup_command', side_effect=FileNotFoundError('private path')):
            with self.assertRaises(LoginCheckError) as raised:
                asyncio.run(BilibiliUploader.cookie_auth('/fake/account.json'))
        self.assertEqual(raised.exception.kind, 'environment')
