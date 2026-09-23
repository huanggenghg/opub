"""发布后从创作者后台匹配本次作品，不能拿个人主页第一条冒充结果。"""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from uploader.douyin_uploader.main import DouYinVideo

TITLE = '秋日 city walk｜银杏道的尽头，是热拿铁和一扇起雾的玻璃窗'
VIDEO_ID = '7688267130843811106'
NOW = 1790064191
WORK_LIST = 'https://creator.douyin.com/janus/douyin/creator/pc/work_list?count=12'
MANAGE = 'https://creator.douyin.com/creator-micro/content/manage'


def post(video_id=VIDEO_ID, title=TITLE[:30], created=NOW):
    # 后台 aweme_id 是精确字符串；数值 item_id 可能已被 JS 舍入，不能使用。
    return {'aweme_id': video_id, 'item_id': 7688267130843811000,
            'item_title': title, 'create_time': created,
            'status': {'is_delete': False}}


def uploader():
    return DouYinVideo(title=TITLE, file_path='/fake.mp4', tags=[],
                      publish_date=0, account_file='/fake.json')


class Page:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.goto = AsyncMock()
        self.wait_for_load_state = AsyncMock()
        self.locator = Mock(return_value=SimpleNamespace(first=SimpleNamespace(count=AsyncMock(return_value=0))))
        self.url = MANAGE

    @asynccontextmanager
    async def expect_response(self, predicate, **kwargs):
        response = SimpleNamespace(url=WORK_LIST, status=200,
                                   json=AsyncMock(return_value=next(self.payloads)))
        assert predicate(response)
        assert not predicate(SimpleNamespace(url='https://example.org/janus/douyin/creator/pc/work_list', status=200))
        assert not predicate(SimpleNamespace(url=WORK_LIST, status=500))
        future = asyncio.get_running_loop().create_future()
        future.set_result(response)
        yield SimpleNamespace(value=future)


def resolve(payloads):
    page = Page(payloads)
    app = uploader()
    with patch('uploader.douyin_uploader.main.asyncio.sleep', AsyncMock()), \
         patch('uploader.douyin_uploader.main.time.time', return_value=NOW + 4):
        result = asyncio.run(app._get_content_link(page, published_after=NOW - 1, previous_ids=set()))
    return result, page


def test_returns_exact_id_from_creator_when_public_profile_has_no_video():
    result, page = resolve([{'status_code': 0, 'aweme_list': [post(created=NOW-600), post()]}])
    assert result == f'https://www.douyin.com/video/{VIDEO_ID}'
    assert all(call.args[0] == MANAGE for call in page.goto.call_args_list)
    page.locator.assert_not_called()


def test_waits_for_delayed_work_list():
    result, page = resolve([{'status_code': 0, 'aweme_list': []},
                            {'status_code': 0, 'aweme_list': [post()]}])
    assert result == f'https://www.douyin.com/video/{VIDEO_ID}'
    assert page.goto.await_count == 2


@pytest.mark.parametrize('posts', [
    [post(created=NOW-600)], [post(title='另一条作品')],
    [post(), post(video_id='7688267130843811107')],
    [post(video_id=7688267130843811000.0)], [post(video_id='invalid')],
    [post(created=NOW+3600)], [{'aweme_id': VIDEO_ID}], [None],
    [dict(post(), status={'is_delete': True})],
])
def test_never_returns_old_unrelated_ambiguous_or_malformed_content(posts):
    result, _ = resolve([{'status_code': 0, 'aweme_list': posts}] * 12)
    assert result is None


@pytest.mark.parametrize('payload', [None, [], {'status_code': 1, 'aweme_list': [post()]},
                                     {'status_code': 0, 'aweme_list': None}])
def test_invalid_or_unsuccessful_response_is_nonfatal(payload):
    result, _ = resolve([payload] * 12)
    assert result is None


def test_network_failure_returns_no_link_without_public_profile_navigation():
    page = Page([])
    page.expect_response = Mock(side_effect=TimeoutError('offline'))
    with patch('uploader.douyin_uploader.main.asyncio.sleep', AsyncMock()):
        result = asyncio.run(uploader()._get_content_link(page, published_after=NOW, previous_ids=set()))
    assert result is None
    page.locator.assert_not_called()


def test_result_lookup_has_total_timeout():
    page = Page([])
    async def never_ready(*args, **kwargs):
        await asyncio.Event().wait()
    page.goto = never_ready
    page.payloads = iter([{'status_code': 0, 'aweme_list': []}])
    with patch('uploader.douyin_uploader.main.DOUYIN_RESULT_WAIT_TIMEOUT', 0.01):
        result = asyncio.run(uploader()._get_content_link(page, published_after=NOW, previous_ids=set()))
    assert result is None


def test_successful_submission_with_missing_link_clicks_publish_only_once():
    app = uploader()
    publish_button = SimpleNamespace(count=AsyncMock(return_value=1), click=AsyncMock())
    file_input = SimpleNamespace(set_input_files=AsyncMock())
    uploaded = SimpleNamespace(count=AsyncMock(return_value=1))
    absent = SimpleNamespace(count=AsyncMock(return_value=0))
    def locator(selector):
        if selector == "div[class^='container'] input":
            return file_input
        if selector == '[class^="long-card"] div:has-text("重新上传")':
            return uploaded
        return absent
    page = SimpleNamespace(goto=AsyncMock(), wait_for_url=AsyncMock(),
                           locator=locator, get_by_role=Mock(return_value=publish_button))
    with patch('uploader.douyin_uploader.main._check_douyin_publish_restriction', AsyncMock(return_value=None)), \
         patch('uploader.douyin_uploader.main.asyncio.sleep', AsyncMock()), \
         patch.object(app, '_get_existing_content_ids', AsyncMock(return_value=set())), \
         patch.object(app, 'fill_title_and_description', AsyncMock()), \
         patch.object(app, 'set_thumbnail', AsyncMock()), \
         patch.object(app, '_get_content_link', AsyncMock(return_value=None)) as lookup:
        assert asyncio.run(app.upload_video_content(page)) is None
    publish_button.click.assert_awaited_once()
    lookup.assert_awaited_once()
    assert isinstance(lookup.call_args.kwargs['published_after'], float)


@pytest.mark.parametrize('link', [None, f'https://www.douyin.com/video/{VIDEO_ID}'])
def test_upload_preserves_success_and_propagates_link(link):
    app = uploader()
    @asynccontextmanager
    async def session(**kwargs):
        yield object()
    with patch.object(app, 'validate_upload_args', AsyncMock()), \
         patch.object(app, '_browser_session', session), \
         patch.object(app, 'upload_video_content', AsyncMock(return_value=link)):
        result = asyncio.run(app.upload())
    assert result['success'] is True
    assert result.get('result_url') == link


def test_waits_beyond_three_empty_responses():
    result, page = resolve([{'status_code': 0, 'aweme_list': []}] * 4 +
                           [{'status_code': 0, 'aweme_list': [post()]}])
    assert result == f'https://www.douyin.com/video/{VIDEO_ID}'
    assert page.goto.await_count == 5


def test_excludes_recent_same_title_post_present_before_submission():
    old = post(video_id='7688267130843811105', created=NOW-1)
    page = Page([{'status_code': 0, 'aweme_list': [old]},
                 {'status_code': 0, 'aweme_list': [old, post()]}])
    with patch('uploader.douyin_uploader.main.asyncio.sleep', AsyncMock()), \
         patch('uploader.douyin_uploader.main.time.time', return_value=NOW+4):
        result = asyncio.run(uploader()._get_content_link(
            page, published_after=NOW-5, previous_ids={old['aweme_id']}))
    assert result == f'https://www.douyin.com/video/{VIDEO_ID}'


def test_missing_baseline_does_not_guess_content_identity():
    page = Page([{'status_code': 0, 'aweme_list': [post()]}])
    assert asyncio.run(uploader()._get_content_link(
        page, published_after=NOW-5, previous_ids=None)) is None
    page.goto.assert_not_awaited()


def test_reads_existing_ids_before_submission():
    page = Page([{'status_code': 0, 'aweme_list': [post()]}])
    assert asyncio.run(uploader()._get_existing_content_ids(page)) == {VIDEO_ID}


@pytest.mark.parametrize('payload', [None, {'status_code': 1},
    {'status_code': 0, 'aweme_list': None}, {'status_code': 0, 'aweme_list': [None]}])
def test_invalid_baseline_is_not_an_empty_account(payload):
    assert asyncio.run(uploader()._get_existing_content_ids(Page([payload]))) is None


def test_baseline_retries_transient_failure():
    page = Page([])
    with patch('uploader.douyin_uploader.main._read_douyin_work_list',
               AsyncMock(side_effect=[TimeoutError(), [post()]])), \
         patch('uploader.douyin_uploader.main.asyncio.sleep', AsyncMock()):
        assert asyncio.run(uploader()._get_existing_content_ids(page)) == {VIDEO_ID}
