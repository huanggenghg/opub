import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from uploader.baijiahao_uploader.main import BaiJiaHaoVideo


def uploader(title='原始标题'):
    return BaiJiaHaoVideo(title, '/fake.mp4', [], 0, '/fake.json')


def page_fixture():
    empty = SimpleNamespace(count=AsyncMock(return_value=0))
    button = SimpleNamespace(count=AsyncMock(return_value=1), get_attribute=AsyncMock(return_value=None), click=AsyncMock())
    page = SimpleNamespace(url='https://example.test/editor', locator=Mock(return_value=empty),
                           get_by_test_id=Mock(return_value=button), screenshot=AsyncMock())
    return page, button


def test_error_after_submit_never_clicks_publish_again():
    obj = uploader()
    page, button = page_fixture()
    error = SimpleNamespace(count=AsyncMock(side_effect=RuntimeError('lost page after click')))
    page.locator.side_effect = lambda selector: error if 'cheetah-message-error' in selector else SimpleNamespace(count=AsyncMock(return_value=0))
    with patch('utils.network.time.time', side_effect=[0, 1, 301]), patch('asyncio.sleep', AsyncMock()):
        with pytest.raises(Exception):
            asyncio.run(obj.publish_video(page, 0))
    assert button.click.await_count == 1


def test_scheduled_submission_error_is_not_retried():
    obj = uploader()
    with patch.object(obj, 'set_schedule_publish', AsyncMock(side_effect=RuntimeError('confirmation uncertain'))) as schedule, patch(
        'utils.network.time.time', side_effect=[0, 1, 301]
    ), patch('asyncio.sleep', AsyncMock()):
        with pytest.raises(Exception):
            asyncio.run(obj.publish_video(object(), object()))
    assert schedule.await_count == 1


def test_optional_screenshot_failure_does_not_fail_submission():
    obj = uploader()
    page, button = page_fixture()
    page.screenshot.side_effect = OSError('disk full')
    with patch('asyncio.sleep', AsyncMock()):
        asyncio.run(obj.direct_publish(page))
    button.click.assert_awaited_once()


def test_missing_publish_button_is_an_error():
    page, button = page_fixture()
    button.count.return_value = 0
    with pytest.raises(RuntimeError, match='发布按钮'):
        asyncio.run(uploader().direct_publish(page))
    button.click.assert_not_awaited()


@pytest.mark.parametrize('title', ['短标题', '12345678', '123456789'])
def test_title_is_written_without_added_words(title):
    obj = uploader(title)
    editor = SimpleNamespace(click=AsyncMock())
    page = SimpleNamespace(locator=Mock(return_value=SimpleNamespace(first=editor)),
                           keyboard=SimpleNamespace(press=AsyncMock(), type=AsyncMock()))
    asyncio.run(obj.add_title_tags(page))
    assert obj.title == title
    page.keyboard.type.assert_awaited_once_with(title)


def test_uncertain_submission_result_explicitly_disallows_retry():
    obj = uploader()

    @asynccontextmanager
    async def session(**kwargs):
        yield object()

    async def lost_after_submit(page):
        obj._submission_attempted = True
        raise RuntimeError('lost page')

    with patch.object(obj, 'validate_upload_args', AsyncMock()), patch.object(obj, '_browser_session', session), patch.object(
        obj, 'upload_video_content', lost_after_submit
    ):
        result = asyncio.run(obj.upload())
    assert result['success'] is False
    assert result.get('safe_to_retry') is False
    assert result.get('error_code') == 'PUB-baijiahao'
    assert '未确认' in result['message']
