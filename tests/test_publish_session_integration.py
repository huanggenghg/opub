"""Exercise real orchestration/dispatch/session boundaries without remote publishing."""
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from publish.orchestrator import publish_one_item
from uploader.weibo_uploader import main as weibo


class Locator:
    def __init__(self, visible):
        self.visible = visible

    @property
    def first(self):
        return self

    async def count(self):
        return int(self.visible)

    async def is_visible(self):
        return self.visible


class Page:
    def __init__(self, context):
        self.context = context
        self.url = 'about:blank'
        self.visited = []

    async def goto(self, url, **kwargs):
        self.visited.append(url)
        if url == weibo.WEIBO_LOGIN_URL:
            # Simulated user completes login in this page, retaining its context.
            self.context.authenticated = True
            self.url = weibo.WEIBO_MAIN_URL
        elif not self.context.authenticated:
            self.url = weibo.WEIBO_LOGIN_URL
        else:
            self.url = url

    async def wait_for_timeout(self, *args, **kwargs):
        pass

    def locator(self, selector):
        return Locator(self.context.authenticated and selector == weibo.WEIBO_UPLOAD_BUTTON_SELECTOR)


class Context:
    def __init__(self, state):
        self.authenticated = bool(state)
        self.loaded_state = state
        self.saved_paths = []
        self.pages = []
        self.closed = False

    async def new_page(self):
        page = Page(self)
        self.pages.append(page)
        return page

    async def storage_state(self, path):
        self.saved_paths.append(str(path))
        Path(path).write_text(json.dumps({'cookies': [], 'origins': []}))

    async def close(self):
        self.closed = True


class Browser:
    def __init__(self):
        self.contexts = []
        self.closed = False

    async def new_context(self, **kwargs):
        context = Context(kwargs.get('storage_state'))
        self.contexts.append(context)
        return context

    async def close(self):
        self.closed = True


@pytest.fixture
def transport(monkeypatch):
    browsers = []
    launch_flags = []
    uploaded_pages = []

    @asynccontextmanager
    async def driver():
        yield object()

    async def launch(cls, playwright, headless):
        browser = Browser()
        browsers.append(browser)
        launch_flags.append(headless)
        return browser

    async def upload(self, page):
        assert page.context.authenticated
        assert page.url == weibo.WEIBO_UPLOAD_CHANNEL_URL
        uploaded_pages.append(page)
        return 'https://weibo.com/tv/show/test-result'

    monkeypatch.setattr('uploader.base_video.async_playwright', driver)
    monkeypatch.setattr('uploader.base_video.set_init_script', AsyncMock(side_effect=lambda context: context))
    monkeypatch.setattr(weibo.WeiboBaseUploader, '_launch_browser', classmethod(launch))
    monkeypatch.setattr(weibo.WeiboVideo, 'upload_video_content', upload)
    # Any legacy precheck would both violate the contract and touch a real site.
    monkeypatch.setattr('publish.orchestrator.ensure_account_login', AsyncMock(side_effect=AssertionError('unexpected separate login')))
    monkeypatch.setattr(weibo, 'cookie_auth', AsyncMock(side_effect=AssertionError('unexpected separate auth browser')))
    return browsers, launch_flags, uploaded_pages


def params(tmp_path, account):
    video = tmp_path / 'video.mp4'
    video.touch()
    return {
        'enabled_platforms': ['weibo'], 'platforms': {'weibo_account': str(account)},
        'content_type': 'video', 'video_file': str(video), 'title': '测试标题',
        'desc': '测试描述', 'tags': [], 'publish_strategy': 'immediate',
        'publish_time': None, 'convert_to_video': False,
    }


@pytest.mark.parametrize('existing_account', [True, False])
def test_publish_uses_one_browser_context_and_working_page(tmp_path, transport, existing_account):
    account = tmp_path / 'new-account' / 'account.json'
    if existing_account:
        account.parent.mkdir()
        account.write_text('{"cookies": [], "origins": []}')
    browsers, launch_flags, uploaded_pages = transport
    result = asyncio.run(publish_one_item(params(tmp_path, account)))
    assert result['weibo']['success'] is True
    if existing_account:
        assert len(browsers) == 1
        assert launch_flags == [True]
        context, = browsers[0].contexts
        page, = context.pages
        assert uploaded_pages == [page]
        assert weibo.WEIBO_LOGIN_URL not in page.visited
        assert context.saved_paths and set(context.saved_paths) == {str(account)}
        assert context.closed and browsers[0].closed
        return
    # 无头发布遇到未登录:无头探测会话不落盘,弹有头窗口扫码,带新 cookie 重启无头会话上传
    assert len(browsers) == 3
    assert launch_flags == [True, False, True]
    probe_context, = browsers[0].contexts
    assert not probe_context.saved_paths
    login_context, = browsers[1].contexts
    login_page, = login_context.pages
    assert weibo.WEIBO_LOGIN_URL in login_page.visited
    publish_context, = browsers[2].contexts
    assert publish_context.loaded_state == str(account)
    assert uploaded_pages == publish_context.pages
    assert login_context.saved_paths == [str(account)]
    assert publish_context.saved_paths == [str(account)]
    assert account.exists()
    assert all(browser.closed for browser in browsers)
    assert probe_context.closed and login_context.closed and publish_context.closed


def test_distinct_accounts_and_materials_do_not_reuse_context(tmp_path, transport):
    accounts = [tmp_path / name / 'account.json' for name in ('one', 'two')]
    for account in accounts:
        account.parent.mkdir()
        account.write_text('{"cookies": [], "origins": []}')
    browsers, launch_flags, uploaded_pages = transport
    for account in [accounts[0], accounts[1], accounts[0]]:
        result = asyncio.run(publish_one_item(params(tmp_path, account)))
        assert result['weibo']['success'] is True
    assert len(browsers) == len(uploaded_pages) == 3
    assert len({id(page.context) for page in uploaded_pages}) == 3
    assert [browser.contexts[0].loaded_state for browser in browsers] == [str(accounts[0]), str(accounts[1]), str(accounts[0])]
    for browser, account in zip(browsers, [accounts[0], accounts[1], accounts[0]]):
        assert set(browser.contexts[0].saved_paths) == {str(account)}
        assert browser.closed and browser.contexts[0].closed
