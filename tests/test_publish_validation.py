import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from publish.config import PublishOverrides, default_params_from_overrides
from publish import orchestrator


@pytest.fixture(autouse=True)
def no_real_publish():
    with patch('publish.orchestrator.ensure_account_login', AsyncMock(return_value=False)), patch('publish.orchestrator.publish_to_platform', AsyncMock(return_value={'success': False, 'message': 'test'})):
        yield


def parameters(tmp_path, **overrides):
    video = tmp_path / 'test.mp4'
    video.write_bytes(b'video')
    return default_params_from_overrides(PublishOverrides(
        **{'platforms': 'douyin', 'video': str(video), 'title': 'test', **overrides}
    ))


@pytest.mark.parametrize('updates', [
    {'enabled_platforms': ['douyin', 'unknown']},
    {'start_from': 0}, {'start_from': -1}, {'start_from': 2},
    {'publish_time': datetime(2020, 1, 1), 'publish_strategy': 'scheduled'},
    {'publish_time': datetime.now() + timedelta(minutes=30), 'publish_strategy': 'scheduled'},
    {'enabled_platforms': ['bilibili'], 'publish_time': datetime.now() + timedelta(days=1), 'publish_strategy': 'scheduled'},
])
def test_invalid_parameters_fail_before_environment_or_login(tmp_path, updates):
    params = {**parameters(tmp_path), **updates}
    with patch('publish.orchestrator.runtime_preflight', AsyncMock(return_value=True)) as env, patch(
        'publish.orchestrator.publish_one_item', AsyncMock(return_value={})
    ) as publish:
        code = asyncio.run(orchestrator.run_publish_with_params(params))
    assert code == 10
    env.assert_not_awaited()
    publish.assert_not_awaited()


def test_missing_image_in_note_fails_before_login(tmp_path):
    params = parameters(tmp_path, video=None, note=True, images=str(tmp_path / 'missing.png'))
    with patch('publish.orchestrator.runtime_preflight', AsyncMock(return_value=True)) as env:
        assert asyncio.run(orchestrator.run_publish_with_params(params)) == 10
    env.assert_not_awaited()


def test_unsupported_note_platform_fails_before_conversion_or_login(tmp_path):
    image = tmp_path / 'a.jpg'
    image.write_bytes(b'image')
    params = parameters(tmp_path, platforms='douyin,tencent', video=None, note=True, images=str(image))
    with patch('publish.orchestrator.runtime_preflight', AsyncMock(return_value=True)) as env:
        assert asyncio.run(orchestrator.run_publish_with_params(params)) == 10
    env.assert_not_awaited()


def test_all_titles_are_checked_before_first_publish(tmp_path):
    params = parameters(tmp_path, video=str(tmp_path))
    (tmp_path / 'second.mp4').write_bytes(b'video2')
    with patch('publish.orchestrator.runtime_preflight', AsyncMock(return_value=True)), patch(
        'publish.orchestrator.get_video_content', side_effect=[('valid', ''), ('', '')]
    ), patch('publish.orchestrator.publish_one_item', AsyncMock(return_value={'douyin': {'success': True}})) as publish:
        assert asyncio.run(orchestrator.run_publish_with_params(params)) == 10
    publish.assert_not_awaited()


def test_directory_contains_fake_video_directory(tmp_path):
    params = parameters(tmp_path, video=str(tmp_path))
    (tmp_path / 'folder.mp4').mkdir()
    with patch('publish.orchestrator.runtime_preflight', AsyncMock(return_value=True)) as env:
        assert asyncio.run(orchestrator.run_publish_with_params(params)) == 10
    env.assert_not_awaited()


def test_unsupported_file_extension_is_configuration_error(tmp_path):
    bad = tmp_path / 'text.txt'
    bad.write_text('not a video')
    params = parameters(tmp_path, video=str(bad))
    with patch('publish.orchestrator.runtime_preflight', AsyncMock(return_value=True)) as env:
        assert asyncio.run(orchestrator.run_publish_with_params(params)) == 10
    env.assert_not_awaited()


def test_directory_discovery_includes_all_supported_video_extensions(tmp_path):
    from publish.content import get_video_files
    from uploader.base_video import BasePlatformUploader
    for extension in BasePlatformUploader.SUPPORTED_VIDEO_EXTENSIONS:
        (tmp_path / ('clip' + extension)).write_bytes(b'video')
    assert len(get_video_files(str(tmp_path))) == len(BasePlatformUploader.SUPPORTED_VIDEO_EXTENSIONS)


@pytest.mark.parametrize('duration', [0, -1, float('nan'), float('inf')])
def test_invalid_conversion_duration_fails_before_environment(tmp_path, duration):
    image = tmp_path / 'a.jpg'
    image.write_bytes(b'image')
    params = parameters(tmp_path, video=None, note=True, images=str(image), convert_to_video=True, video_duration=duration)
    with patch('publish.orchestrator.runtime_preflight', AsyncMock()) as env:
        assert asyncio.run(orchestrator.run_publish_with_params(params)) == 10
    env.assert_not_awaited()
