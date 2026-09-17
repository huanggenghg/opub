"""Single-page authentication and browser ownership regression tests."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from publish.auth import LoginCheckError, LoginTimeoutError, login_check, warn_qr_login_pending
from uploader.base_video import BaseBrowserUploader


def test_timeout_contract_and_shared_warning(capsys):
    result = LoginTimeoutError().to_result()
    assert result['error_code'] == 'AUTH-001'
    assert result['issue_type'] == 'login_timeout'
    assert result['safe_to_retry'] is True
    warn_qr_login_pending('微博')
    assert '不低于 360 秒' in capsys.readouterr().err


def test_decorator_preserves_interactive_failure():
    @login_check
    async def check():
        raise LoginTimeoutError()
    with pytest.raises(LoginTimeoutError):
        asyncio.run(check())


class SessionUploader(BaseBrowserUploader):
    PLATFORM_NAME = 'fake'
    UPLOAD_URL = 'https://example.test/upload'
    LOGIN_URL = 'https://example.test/login'
    LOGIN_MARKERS = ['/login']

    def __init__(self, account_file):
        self.account_file = str(account_file)
        self.headless = True


class SessionPage:
    def __init__(self, login=False, completed=True, returned_url=None):
        self.url = 'about:blank'
        self.login = login
        self.completed = completed
        self.returned_url = returned_url
        self.visits = []
        self.context = SimpleNamespace(storage_state=AsyncMock())

    async def goto(self, url, **kwargs):
        self.visits.append(url)
        self.url = SessionUploader.LOGIN_URL if self.login else url
        if url == SessionUploader.LOGIN_URL:
            self.url = url
        elif len(self.visits) > 1 and self.returned_url:
            self.url = self.returned_url

    async def wait_for_timeout(self, *args, **kwargs):
        if self.url == SessionUploader.LOGIN_URL and self.completed and len(self.visits) > 1:
            self.login = False
            self.url = 'https://example.test/home'


@pytest.mark.parametrize('login', [False, True])
def test_session_uses_same_page_and_saves_only_valid_new_login(tmp_path, capsys, login):
    uploader = SessionUploader(tmp_path / 'new' / 'cookie.json')
    page = SessionPage(login=login)
    asyncio.run(uploader._ensure_session_login(page))
    assert page.url == uploader.UPLOAD_URL
    assert page.visits == ([uploader.UPLOAD_URL, uploader.LOGIN_URL, uploader.UPLOAD_URL] if login else [uploader.UPLOAD_URL])
    assert page.context.storage_state.await_count == int(login)
    assert ('360 秒' in capsys.readouterr().err) is login
    if login:
        assert (tmp_path / 'new').is_dir()


@pytest.mark.parametrize('returned_url', [SessionUploader.LOGIN_URL, 'https://example.test/unknown'])
def test_post_login_page_must_validate_before_state_save(tmp_path, returned_url):
    uploader = SessionUploader(tmp_path / 'cookie.json')
    page = SessionPage(login=True, returned_url=returned_url)
    with pytest.raises((LoginCheckError, LoginTimeoutError)):
        asyncio.run(uploader._ensure_session_login(page))
    page.context.storage_state.assert_not_awaited()


def test_login_url_immediate_authenticated_redirect_skips_qr_extraction(tmp_path):
    uploader = SessionUploader(tmp_path / 'cookie.json')
    page = SessionPage(login=True)

    async def goto(url, **kwargs):
        page.visits.append(url)
        if url == uploader.UPLOAD_URL and len(page.visits) == 1:
            page.url = uploader.LOGIN_URL
        else:
            page.login = False
            page.url = uploader.UPLOAD_URL

    page.goto = goto
    interaction = AsyncMock(side_effect=AssertionError('QR extraction is not needed'))
    with patch.object(uploader, '_session_login_interaction', interaction):
        asyncio.run(uploader._ensure_session_login(page))

    interaction.assert_not_called()
    page.context.storage_state.assert_awaited_once_with(path=uploader.account_file)


def test_login_timeout_and_interruption_are_sanitized(tmp_path):
    uploader = SessionUploader(tmp_path / 'cookie.json')
    page = SessionPage(login=True, completed=False)
    with pytest.raises(LoginTimeoutError) as caught:
        asyncio.run(uploader._ensure_session_login(page))
    assert 'fake' in str(caught.value)
    page.context.storage_state.assert_not_awaited()
    original_goto = page.goto
    async def goto(url, **kwargs):
        if url == uploader.LOGIN_URL:
            raise RuntimeError('browser closed https://secret?cookie=private')
        await original_goto(url, **kwargs)
    page.goto = goto
    with pytest.raises(LoginTimeoutError) as caught:
        asyncio.run(uploader._ensure_session_login(page))
    assert 'secret' not in str(caught.value)


def test_qr_file_failure_keeps_environment_classification(tmp_path):
    uploader = SessionUploader(tmp_path / 'cookie.json')
    page = SessionPage(login=True, completed=False)

    @asynccontextmanager
    async def interaction(_page):
        raise PermissionError('private account path')
        yield

    with patch.object(uploader, '_session_login_interaction', interaction):
        with pytest.raises(LoginCheckError) as caught:
            asyncio.run(uploader._ensure_session_login(page))

    assert caught.value.kind == 'environment'
    assert 'private account path' not in str(caught.value)


def test_qr_disk_full_keeps_environment_classification(tmp_path):
    uploader = SessionUploader(tmp_path / 'cookie.json')
    page = SessionPage(login=True, completed=False)

    @asynccontextmanager
    async def interaction(_page):
        raise OSError(28, 'No space left on device', 'private path')
        yield

    with patch.object(uploader, '_session_login_interaction', interaction):
        with pytest.raises(LoginCheckError) as caught:
            asyncio.run(uploader._ensure_session_login(page))

    assert caught.value.kind == 'environment'
    assert 'private path' not in str(caught.value)


@pytest.mark.parametrize('failure,kind', [
    (TimeoutError('private login URL timed out'), 'network'),
    (RuntimeError('Locator.wait_for private selector'), 'page'),
])
def test_qr_network_and_unknown_page_keep_non_auth_classification(tmp_path, failure, kind):
    uploader = SessionUploader(tmp_path / 'cookie.json')
    page = SessionPage(login=True, completed=False)

    @asynccontextmanager
    async def interaction(_page):
        raise failure
        yield

    with patch.object(uploader, '_session_login_interaction', interaction):
        with pytest.raises(LoginCheckError) as caught:
            asyncio.run(uploader._ensure_session_login(page))

    assert caught.value.kind == kind
    assert 'private' not in str(caught.value)


@pytest.mark.parametrize('failure,kind', [(TimeoutError('secret'), 'network'), (RuntimeError('bad DOM'), 'page')])
def test_uncertain_navigation_never_prompts_login(tmp_path, capsys, failure, kind):
    uploader = SessionUploader(tmp_path / 'cookie.json')
    page = SessionPage()
    page.goto = AsyncMock(side_effect=failure)
    with pytest.raises(LoginCheckError) as caught:
        asyncio.run(uploader._ensure_session_login(page))
    assert caught.value.kind == kind
    assert page.goto.await_count == 1
    assert not capsys.readouterr().err


def test_unknown_page_and_missing_positive_evidence_do_not_prompt_login(tmp_path, capsys):
    uploader = SessionUploader(tmp_path / 'cookie.json')
    page = SessionPage()
    async def goto(*args, **kwargs):
        page.url = 'https://example.test/unknown'
    page.goto = goto
    with pytest.raises(LoginCheckError):
        asyncio.run(uploader._ensure_session_login(page))
    page.goto = AsyncMock()
    page.url = uploader.UPLOAD_URL
    with patch.object(SessionUploader, 'is_login_completed', AsyncMock(return_value=False)):
        with pytest.raises(LoginCheckError):
            asyncio.run(uploader._ensure_session_login(page))
    assert not capsys.readouterr().err


@pytest.mark.parametrize('failure_stage', ['context', 'page', 'login', 'context_close', 'browser_close', 'publish'])
def test_session_cleanup_never_leaks_browser_or_masks_outcome(tmp_path, failure_stage):
    uploader = SessionUploader(tmp_path / 'cookie.json')
    page = SessionPage()
    context = SimpleNamespace(new_page=AsyncMock(return_value=page), close=AsyncMock(), storage_state=AsyncMock())
    browser = SimpleNamespace(close=AsyncMock())
    if failure_stage == 'page':
        context.new_page.side_effect = RuntimeError('page failed')
    if failure_stage == 'context_close' or failure_stage == 'publish':
        context.close.side_effect = RuntimeError('cleanup failed')
    if failure_stage == 'browser_close':
        browser.close.side_effect = RuntimeError('cleanup failed')
    @asynccontextmanager
    async def playwright():
        yield object()
    init = AsyncMock(return_value=context, side_effect=RuntimeError('setup failed') if failure_stage == 'context' else None)
    login = AsyncMock(side_effect=LoginTimeoutError() if failure_stage == 'login' else None)
    async def run():
        async with uploader._browser_session():
            if failure_stage == 'publish':
                raise ValueError('publish failed')
    with patch('uploader.base_video.async_playwright', playwright), patch.object(uploader, '_launch_browser', AsyncMock(return_value=browser)), patch.object(uploader, '_init_context', init), patch.object(uploader, '_ensure_session_login', login):
        if failure_stage in {'context', 'page'}:
            with pytest.raises(LoginCheckError):
                asyncio.run(run())
        elif failure_stage == 'login':
            with pytest.raises(LoginTimeoutError):
                asyncio.run(run())
        elif failure_stage == 'publish':
            with pytest.raises(ValueError, match='publish failed'):
                asyncio.run(run())
        else:
            asyncio.run(run())
    browser.close.assert_awaited_once()
    if failure_stage != 'context':
        context.close.assert_awaited_once()
    if failure_stage in {'context', 'page', 'login'}:
        context.storage_state.assert_not_awaited()


def test_successful_login_state_survives_upload_failure_with_exit_save_disabled(tmp_path):
    uploader = SessionUploader(tmp_path / 'new' / 'cookie.json')
    page = SessionPage(login=True)
    context = page.context
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()
    browser = SimpleNamespace(close=AsyncMock())
    @asynccontextmanager
    async def playwright():
        yield object()
    async def run():
        async with uploader._browser_session(save_state=False):
            assert context.storage_state.await_count == 1
            raise ValueError('upload failed')
    with patch('uploader.base_video.async_playwright', playwright), patch.object(uploader, '_launch_browser', AsyncMock(return_value=browser)) as launch, patch.object(uploader, '_init_context', AsyncMock(return_value=context)):
        with pytest.raises(ValueError, match='upload failed'):
            asyncio.run(run())
    launch.assert_awaited_once()
    context.storage_state.assert_awaited_once_with(path=uploader.account_file)
    browser.close.assert_awaited_once()


PLATFORMS = [
    ('douyin', 'douyin', 'DouYinVideo', 'DouYinNote'),
    ('xiaohongshu', 'xiaohongshu', 'XiaoHongShuVideo', 'XiaoHongShuNote'),
    ('kuaishou', 'ks', 'KSVideo', 'KSNote'),
    ('tencent', 'tencent', 'TencentVideo', 'TencentNote'),
    ('baijiahao', 'baijiahao', 'BaiJiaHaoVideo', None),
    ('weibo', 'weibo', 'WeiboVideo', 'WeiboNote'),
]


def make_uploader(module_name, class_name, tmp_path):
    import importlib
    cls = getattr(importlib.import_module('uploader.' + module_name + '_uploader.main'), class_name)
    kwargs = dict(title='t', tags=[], publish_date=0, account_file=str(tmp_path / 'missing.json'), publish_strategy='immediate')
    if class_name.endswith('Note'):
        kwargs.update(image_paths=[str(tmp_path / 'image.jpg')], note='note')
    else:
        kwargs.update(file_path=str(tmp_path / 'video.mp4'))
    return cls(**kwargs)


@pytest.mark.parametrize('platform,module,video,note', PLATFORMS)
def test_local_validation_allows_missing_account_without_cookie_check(tmp_path, platform, module, video, note):
    uploader = make_uploader(module, video, tmp_path)
    with patch('uploader.' + module + '_uploader.main.cookie_auth', AsyncMock(side_effect=AssertionError('nested auth'))) as check:
        asyncio.run(uploader.validate_login_and_strategy())
        assert uploader.publish_date == 0
        uploader.publish_strategy = 'invalid'
        with pytest.raises(ValueError):
            asyncio.run(uploader.validate_login_and_strategy())
        check.assert_not_awaited()


@pytest.mark.parametrize('platform,module,video,note', PLATFORMS)
@pytest.mark.parametrize('error', [LoginCheckError('network'), LoginTimeoutError()])
def test_platform_uploads_preserve_typed_auth_failures(tmp_path, platform, module, video, note, error):
    for name in filter(None, (video, note)):
        uploader = make_uploader(module, name, tmp_path)
        @asynccontextmanager
        async def failing_session(**kwargs):
            raise error
            yield
        with patch.object(uploader, 'validate_upload_args', AsyncMock()), patch.object(uploader, '_browser_session', failing_session):
            with pytest.raises(type(error)):
                asyncio.run(uploader.upload())


@pytest.mark.parametrize('platform,module,video,note', PLATFORMS)
@pytest.mark.parametrize('error', [LoginCheckError('network'), LoginTimeoutError()])
def test_real_dispatch_wrapper_preserves_auth_result(tmp_path, platform, module, video, note, error):
    from publish.dispatch import publish_to_platform
    uploader = make_uploader(module, video, tmp_path)
    path = tmp_path / 'video.mp4'
    path.write_bytes(b'video')
    params = dict(title='test', tags=[], desc='', content_type='video', video_file=str(path), publish_time=None, publish_strategy='immediate', account_file=str(tmp_path / 'missing.json'))
    with patch.object(type(uploader), 'upload', AsyncMock(side_effect=error)):
        result = asyncio.run(publish_to_platform(platform, params))
    assert result == error.to_result()


@pytest.mark.parametrize('module,cls_name,helper', [
    ('douyin', 'DouYinBaseUploader', '_is_douyin_auth_page_valid'),
    ('baijiahao', 'BaiJiaHaoVideo', '_is_baijiahao_auth_page_valid'),
    ('weibo', 'WeiboBaseUploader', '_wait_for_weibo_upload_button'),
])
def test_platform_auth_evidence_is_required_on_same_page(module, cls_name, helper):
    import importlib
    mod = importlib.import_module('uploader.' + module + '_uploader.main')
    cls = getattr(mod, cls_name)
    page = SimpleNamespace(url=cls.UPLOAD_URL, wait_for_timeout=AsyncMock())
    helper_mock = AsyncMock(side_effect=RuntimeError('missing upload entry')) if module == 'weibo' else AsyncMock(return_value=False)
    with patch.object(cls, 'is_login_required', AsyncMock(return_value=False)), patch.object(cls, 'is_login_completed', AsyncMock(return_value=True)), patch.object(mod, helper, helper_mock), patch.object(mod, '_wait_for_douyin_publish_marker', AsyncMock(), create=True):
        with pytest.raises((LoginCheckError, RuntimeError)):
            asyncio.run(cls.check_upload_page(page))
        assert helper_mock.await_count > 0
        assert all(call.args[0] is page for call in helper_mock.await_args_list)


def test_tencent_login_iframe_at_upload_url_is_explicit_expiry():
    from uploader.tencent_uploader.main import TencentBaseUploader
    marker = SimpleNamespace(count=AsyncMock(return_value=1), is_visible=AsyncMock(return_value=True))
    empty = SimpleNamespace(count=AsyncMock(return_value=0), is_visible=AsyncMock(return_value=False))
    marker.first = marker
    empty.first = empty
    page = SimpleNamespace(url=TencentBaseUploader.UPLOAD_URL, locator=lambda selector: marker if 'qrconnect' in selector else empty)
    assert asyncio.run(TencentBaseUploader.is_login_required(page)) is True


class _FlippingLocator:
    """count() flips to 1 after `after` polls of wait_for_timeout."""

    def __init__(self, after=None):
        self.after = after
        self.polls = 0
        self.first = self

    async def count(self):
        if self.after is not None and self.polls >= self.after:
            return 1
        return 0

    async def is_visible(self):
        return bool(await self.count())


class TencentLateEvidencePage:
    """视频号发布页:登录证据/上传控件在若干次轮询后才出现。"""

    def __init__(self, input_after=None, qr_after=None, url=None):
        self.url = url or 'https://channels.weixin.qq.com/platform/post/create'
        self.input_locator = _FlippingLocator(input_after)
        self.qr_locator = _FlippingLocator(qr_after)
        self._generic = _FlippingLocator()

    def locator(self, selector):
        if 'input[type="file"]' in selector:
            return self.input_locator
        if 'qrconnect' in selector:
            return self.qr_locator
        return self._generic

    async def wait_for_timeout(self, *args, **kwargs):
        for loc in (self.input_locator, self.qr_locator, self._generic):
            loc.polls += 1


@pytest.mark.parametrize('qr_after', [1, 3])
def test_tencent_check_waits_for_late_login_evidence(qr_after):
    from uploader.tencent_uploader.main import TencentBaseUploader
    page = TencentLateEvidencePage(qr_after=qr_after)
    assert asyncio.run(TencentBaseUploader.check_upload_page(page)) is False


@pytest.mark.parametrize('input_after', [0, 3])
def test_tencent_check_waits_for_late_upload_input(input_after):
    from uploader.tencent_uploader.main import TencentBaseUploader
    page = TencentLateEvidencePage(input_after=input_after)
    assert asyncio.run(TencentBaseUploader.check_upload_page(page)) is True


def test_tencent_check_times_out_without_evidence():
    from uploader.tencent_uploader.main import TencentBaseUploader
    page = TencentLateEvidencePage()
    with pytest.raises(LoginCheckError):
        asyncio.run(TencentBaseUploader.check_upload_page(page, timeout=0.2))


def test_tencent_check_survives_navigation_race_during_redirect():
    """跳转瞬间 count() 抛 execution context destroyed 不应直接判 PAGE-001。"""
    from uploader.tencent_uploader.main import TencentBaseUploader
    page = TencentLateEvidencePage(qr_after=3)

    real_count = page.qr_locator.count

    async def flaky_count():
        if page.qr_locator.polls < 2:
            raise RuntimeError("Locator.count: Execution context was destroyed, most likely because of a navigation.")
        return await real_count()

    page.qr_locator.count = flaky_count
    assert asyncio.run(TencentBaseUploader.check_upload_page(page, timeout=5)) is False


def test_tencent_check_preserves_non_navigation_errors():
    from uploader.tencent_uploader.main import TencentBaseUploader
    page = TencentLateEvidencePage()
    page.qr_locator.count = AsyncMock(side_effect=ConnectionError("connection reset"))
    with pytest.raises(ConnectionError):
        asyncio.run(TencentBaseUploader.check_upload_page(page, timeout=0))


def test_tencent_check_bounds_persistent_navigation_races():
    from uploader.tencent_uploader.main import TencentBaseUploader
    page = TencentLateEvidencePage()
    page.qr_locator.count = AsyncMock(side_effect=RuntimeError("Execution context was destroyed"))
    with pytest.raises(LoginCheckError) as error:
        asyncio.run(TencentBaseUploader.check_upload_page(page, timeout=0))
    assert error.value.kind == 'page'


@pytest.mark.parametrize('start_url, expected_actions', [
    ('https://channels.weixin.qq.com/platform', ['内容管理', '视频', '发表视频']),
    ('https://channels.weixin.qq.com/platform/post/list', ['发表视频']),
])
def test_tencent_check_navigates_dashboard_to_ready_upload_page(start_url, expected_actions):
    from uploader.tencent_uploader.main import TencentBaseUploader
    page = TencentLateEvidencePage(url=start_url)
    actions = []

    def navigation(name):
        async def click(**kwargs):
            actions.append(name)
            if name == '视频':
                page.url = 'https://channels.weixin.qq.com/platform/post/list'
            elif name == '发表视频':
                page.url = TencentBaseUploader.UPLOAD_URL
                page.input_locator.after = 0
        async def is_visible():
            return name != '视频' or '内容管理' in actions
        locator = SimpleNamespace(is_visible=is_visible, click=click)
        locator.first = locator
        return locator

    page.get_by_role = lambda role, name, exact: navigation(name)
    page.get_by_text = lambda text, exact: navigation(text)
    assert asyncio.run(TencentBaseUploader.check_upload_page(page, timeout=0.1)) is True
    assert actions == expected_actions


def test_tencent_upload_reuses_ready_page_without_reload():
    from uploader.tencent_uploader.main import TencentVideo
    page = TencentLateEvidencePage(input_after=0)
    page.goto = AsyncMock()
    uploader = TencentVideo(title='test', file_path='test.mp4', tags=[], publish_date=0, account_file='test.json')
    assert asyncio.run(uploader.open_upload_page(page)) is page.input_locator
    page.goto.assert_not_awaited()


def test_tencent_dashboard_navigation_is_bounded_when_click_does_not_navigate():
    from uploader.tencent_uploader import main as tencent
    page = TencentLateEvidencePage(url='https://channels.weixin.qq.com/platform')
    link = SimpleNamespace(is_visible=AsyncMock(return_value=True), click=AsyncMock())
    link.first = link
    page.get_by_role = lambda *args, **kwargs: link
    clock = {'now': 0.0}

    async def wait(milliseconds):
        clock['now'] += milliseconds / 1000

    page.wait_for_timeout = wait
    with patch.object(tencent, 'time', SimpleNamespace(monotonic=lambda: clock['now'])):
        with pytest.raises(LoginCheckError) as error:
            asyncio.run(tencent.TencentBaseUploader.check_upload_page(page, timeout=1))
    assert error.value.kind == 'page'
    link.click.assert_awaited_once()


def test_tencent_login_url_is_actual_login_page():
    """LOGIN_URL 必须是 login.html,不能是站点首页。

    Why: 首页(channels.weixin.qq.com)是否跳 login.html 由站点异步决定、不可控
    (2026-09-17 实测:有失效 cookie 时 8s 不跳、goto 甚至被跳转打断 ERR_ABORTED),
    二维码 iframe 只在 login.html 上;等首页自跳会 30s 超时判 PAGE-001。
    """
    from uploader.tencent_uploader.main import TencentBaseUploader
    assert 'login.html' in TencentBaseUploader.LOGIN_URL
    assert TencentBaseUploader.LOGIN_URL != 'https://channels.weixin.qq.com'


@pytest.mark.parametrize('stage', ['enter', 'exit'])
def test_driver_lifecycle_is_classified_without_masking_publish(tmp_path, stage):
    uploader = SessionUploader(tmp_path / 'cookie.json')
    driver = MagicMock(__aenter__=AsyncMock(return_value=object()), __aexit__=AsyncMock())
    if stage == 'enter':
        driver.__aenter__.side_effect = FileNotFoundError('private path')
    else:
        driver.__aexit__.side_effect = RuntimeError('driver cleanup failed')
    context = SimpleNamespace(new_page=AsyncMock(), storage_state=AsyncMock(), close=AsyncMock())
    browser = SimpleNamespace(close=AsyncMock())
    async def run():
        async with uploader._browser_session():
            pass
    with patch('uploader.base_video.async_playwright', return_value=driver), patch.object(uploader, '_launch_browser', AsyncMock(return_value=browser)), patch.object(uploader, '_init_context', AsyncMock(return_value=context)), patch.object(uploader, '_ensure_session_login', AsyncMock()):
        if stage == 'enter':
            with pytest.raises(LoginCheckError) as caught:
                asyncio.run(run())
            assert caught.value.kind == 'environment'
        else:
            asyncio.run(run())
            browser.close.assert_awaited_once()


@pytest.mark.parametrize('stage', ['login', 'upload'])
def test_external_cancellation_closes_resources_and_propagates(tmp_path, stage):
    uploader = SessionUploader(tmp_path / 'cookie.json')
    context = SimpleNamespace(new_page=AsyncMock(), storage_state=AsyncMock(), close=AsyncMock())
    browser = SimpleNamespace(close=AsyncMock())
    @asynccontextmanager
    async def driver():
        yield object()
    async def scenario():
        reached = asyncio.Event()
        async def pause():
            reached.set()
            await asyncio.Event().wait()
        async def login(page):
            if stage == 'login':
                await pause()
        async def run():
            async with uploader._browser_session():
                await pause()
        with patch('uploader.base_video.async_playwright', driver), patch.object(uploader, '_launch_browser', AsyncMock(return_value=browser)), patch.object(uploader, '_init_context', AsyncMock(return_value=context)), patch.object(uploader, '_ensure_session_login', login):
            task = asyncio.create_task(run())
            await reached.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    asyncio.run(scenario())
    context.close.assert_awaited_once()
    browser.close.assert_awaited_once()
