"""Keep platform QR preparation/output/refresh in the active browser page."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from utils.login_qrcode import session_qrcode


@pytest.mark.parametrize('cancelled', [False, True])
def test_qr_interaction_refreshes_same_page_and_cleans_latest_file(tmp_path, cancelled):
    page = object()
    first, second = tmp_path / 'first.png', tmp_path / 'second.png'
    calls = []

    async def save(given_page, account_file, previous_qrcode_path=None):
        assert given_page is page
        calls.append(previous_qrcode_path)
        path = second if previous_qrcode_path else first
        path.touch()
        if previous_qrcode_path:
            previous_qrcode_path.unlink()
        return {'image_path': str(path)}

    refresh = AsyncMock(return_value=True)

    async def run():
        async with session_qrcode(page, 'account.json', save, refresh) as poll:
            assert first.exists()
            await poll()
            assert second.exists() and not first.exists()
            if cancelled:
                raise asyncio.CancelledError()
    if cancelled:
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(run())
    else:
        asyncio.run(run())
    assert calls == [None, first]
    refresh.assert_awaited_once_with(page)
    assert not first.exists() and not second.exists()


def test_qr_interaction_does_not_regenerate_unexpired_code(tmp_path):
    path = tmp_path / 'qr.png'
    path.touch()
    save = AsyncMock(return_value={'image_path': str(path)})
    async def run():
        async with session_qrcode(object(), 'account.json', save, AsyncMock(return_value=False)) as poll:
            await poll()
    asyncio.run(run())
    save.assert_awaited_once()
    assert not path.exists()


def test_tencent_expiry_and_refresh_are_detected_inside_qrconnect_frame():
    from uploader.tencent_uploader import main as tencent

    class Locator:
        def __init__(self, visible=False):
            self.visible = visible
            self.clicked = False

        @property
        def first(self):
            return self

        async def count(self):
            return int(self.visible)

        async def is_visible(self):
            return self.visible

        async def click(self):
            self.clicked = True

        def locator(self, _selector):
            return self

    expired = Locator(visible=True)
    refresh = Locator(visible=True)

    class Scope:
        def locator(self, selector):
            if "refresh-tip" in selector:
                return expired
            if "refresh-wrap" in selector:
                return refresh
            return Locator()

    class Page:
        def frame_locator(self, selector):
            assert "qrconnect" in selector
            return Scope()

        def locator(self, _selector):
            return Locator()

    page = Page()
    assert asyncio.run(tencent._is_tencent_qrcode_expired(page)) is True
    asyncio.run(tencent._refresh_tencent_qrcode(page))
    assert refresh.clicked is True


@pytest.mark.parametrize('module_name,class_name,save_name', [
    ('douyin', 'DouYinBaseUploader', '_save_douyin_qrcode'),
    ('xiaohongshu', 'XiaoHongShuBaseUploader', '_save_xhs_qrcode'),
    ('ks', 'KSBaseUploader', '_save_ks_qrcode'),
    ('tencent', 'TencentBaseUploader', '_save_tencent_qrcode'),
])
def test_platform_session_preserves_qr_output_on_current_page(tmp_path, monkeypatch, module_name, class_name, save_name):
    import importlib
    module = importlib.import_module(f'uploader.{module_name}_uploader.main')
    uploader = getattr(module, class_name).__new__(getattr(module, class_name))
    uploader.account_file = str(tmp_path / 'account.json')
    uploader.headless = True
    page = object()
    path = tmp_path / 'qr.png'
    path.touch()
    save = AsyncMock(return_value={'image_path': str(path)})
    monkeypatch.setattr(module, save_name, save)
    async def run():
        async with uploader._session_login_interaction(page):
            save.assert_awaited_once_with(page, uploader.account_file, previous_qrcode_path=None)
    asyncio.run(run())
    assert not path.exists()
