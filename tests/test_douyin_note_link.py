"""图文发布、取链和结果输出的回归验证。"""
import asyncio
import io
from contextlib import asynccontextmanager, redirect_stdout
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from uploader.douyin_uploader.main import DouYinNote
from publish.dispatch import publish_to_douyin
from publish.reporter import print_results

NOTE_ID = '7680000000000000001'
NOTE_URL = f'https://www.douyin.com/note/{NOTE_ID}'
TITLE = '图文链接回归测试'
NOW = 1790069121


def note_uploader():
    return DouYinNote(image_paths=['/fake.jpg'], note='描述', tags=[],
                     publish_date=0, account_file='/fake.json', title=TITLE)


@pytest.mark.parametrize('link', [NOTE_URL, None])
def test_note_upload_propagates_result_link_and_preserves_success(link):
    app = note_uploader()
    @asynccontextmanager
    async def session(**kwargs):
        yield SimpleNamespace(goto=AsyncMock(), wait_for_url=AsyncMock())
    with patch.object(app, 'validate_upload_args', AsyncMock()), \
         patch.object(app, '_browser_session', session), \
         patch.object(app, 'upload_note_content', AsyncMock(return_value=link)):
        result = asyncio.run(app.upload())
    assert result['success'] is True
    assert result.get('result_url') == link


@pytest.mark.parametrize('lookup_success', [True, False])
def test_note_flow_captures_baseline_then_publishes_once_and_reports_link(lookup_success):
    app = note_uploader()
    events = []
    publish = SimpleNamespace(count=AsyncMock(return_value=1),
                              click=AsyncMock(side_effect=lambda: events.append('publish')))
    page = SimpleNamespace(
        goto=AsyncMock(side_effect=lambda *a, **kw: events.append('upload-page')),
        wait_for_url=AsyncMock(), wait_for_timeout=AsyncMock(),
        get_by_text=Mock(return_value=SimpleNamespace(click=AsyncMock())),
        get_by_role=Mock(return_value=publish),
        locator=Mock(return_value=SimpleNamespace(set_input_files=AsyncMock(
            side_effect=lambda *a: events.append('images')))),
    )
    post = {'aweme_id': NOTE_ID, 'item_title': TITLE, 'create_time': NOW,
            'images': [{'uri': 'fixture'}], 'aweme_type': 68,
            'desc': f'{TITLE} 描述'}
    async def read_posts(_page):
        events.append('read')
        if events.count('read') == 1:
            return []
        return [post] if lookup_success else None
    @asynccontextmanager
    async def session(**kwargs):
        yield page
    params = dict(account_file='/fake.json', title=TITLE, content_type='note',
                  images=['/fake.jpg'], desc='描述', tags=[], publish_time=None,
                  publish_strategy='immediate')
    with patch.object(app, 'validate_upload_args', AsyncMock()), \
         patch.object(app, '_browser_session', session), \
         patch.object(app, 'fill_title_and_description', AsyncMock()), \
         patch('uploader.douyin_uploader.main.DouYinVideo.validate_base_args', return_value=None), \
         patch('uploader.douyin_uploader.main.DouYinNote', return_value=app), \
         patch('uploader.douyin_uploader.main._read_douyin_work_list', read_posts), \
         patch('uploader.douyin_uploader.main._check_douyin_publish_restriction', AsyncMock(return_value=None)), \
         patch('uploader.douyin_uploader.main.time.time', return_value=NOW), \
         patch('uploader.douyin_uploader.main.asyncio.sleep', AsyncMock()):
        result = asyncio.run(publish_to_douyin(params))
    assert result['success'] is True
    assert events.index('read') < events.index('images') < events.index('publish')
    assert events[events.index('publish') + 1] == 'read'
    publish.click.assert_awaited_once()
    assert result.get('result_url') == (NOTE_URL if lookup_success else None)
    out = io.StringIO()
    with redirect_stdout(out):
        print_results({'douyin': result})
    assert ('https://www.douyin.com/note/' in out.getvalue()) is lookup_success


def test_note_matches_observed_empty_title_and_twenty_character_desc():
    app = note_uploader()
    app.title = '这是一条用于验证图文标题截断与正文合并行为的测试标题'
    app.note = ''
    post = {'aweme_id': NOTE_ID, 'item_title': '', 'create_time': NOW,
            'is_pic_word': True, 'aweme_type': 2, 'images': [{}],
            'desc': app.title[:20] + '。#测试  #图文'}
    with patch('uploader.douyin_uploader.main._read_douyin_work_list', AsyncMock(return_value=[post])), \
         patch('uploader.douyin_uploader.main.time.time', return_value=NOW), \
         patch('uploader.douyin_uploader.main.asyncio.sleep', AsyncMock()):
        assert asyncio.run(app._get_content_link(object(), published_after=NOW-5, previous_ids=set())) == NOTE_URL


def test_note_with_same_title_but_different_body_is_rejected():
    post = {'aweme_id': NOTE_ID, 'item_title': TITLE, 'create_time': NOW,
            'is_pic_word': True, 'images': [{}], 'desc': f'{TITLE} 另一段正文'}
    with patch('uploader.douyin_uploader.main._read_douyin_work_list', AsyncMock(return_value=[post])), \
         patch('uploader.douyin_uploader.main.time.time', return_value=NOW), \
         patch('uploader.douyin_uploader.main.asyncio.sleep', AsyncMock()):
        assert asyncio.run(note_uploader()._get_content_link(
            object(), published_after=NOW-5, previous_ids=set())) is None


@pytest.mark.parametrize('overrides', [
    {'desc': '另一条作品'}, {'create_time': NOW-60},
    {'is_pic_word': False, 'images': None, 'aweme_type': 4},
    {'desc': TITLE + '追加标题文字'},
])
def test_note_rejects_unrelated_old_and_video_candidates(overrides):
    post = {'aweme_id': NOTE_ID, 'item_title': '', 'create_time': NOW,
            'is_pic_word': True, 'images': [{}], 'desc': TITLE+'。#测试'}
    post.update(overrides)
    with patch('uploader.douyin_uploader.main._read_douyin_work_list', AsyncMock(return_value=[post])), \
         patch('uploader.douyin_uploader.main.time.time', return_value=NOW), \
         patch('uploader.douyin_uploader.main.asyncio.sleep', AsyncMock()):
        assert asyncio.run(note_uploader()._get_content_link(object(), published_after=NOW-5, previous_ids=set())) is None
