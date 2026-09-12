import contextlib
import io
import json
from unittest.mock import AsyncMock, patch

import pytest

from publish import orchestrator


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr('publish.history.BASE_DIR', tmp_path)
    with patch('publish.orchestrator.runtime_preflight', AsyncMock(return_value=True)), patch(
        'publish.orchestrator.require_valid_license', return_value=(True, None)
    ), patch('publish.orchestrator.ensure_account_login', AsyncMock(return_value=True)) as login, patch(
        'publish.orchestrator.publish_to_platform', AsyncMock(return_value={'success': True, 'message': 'ok'})
    ) as publish:
        yield login, publish


def run(args):
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
        code = orchestrator.main(['--output', 'json', *args])
    report = json.loads(stdout.getvalue())
    assert report['exit_code'] == code
    return report


def inputs(tmp_path):
    video = tmp_path / 'video.mp4'
    video.write_bytes(b'original video')
    return ['--platforms', 'douyin,weibo', '--video', str(video), '--title', 'test']


def test_resume_reuses_success_and_retries_only_safe_failure(tmp_path, isolated):
    login, publish = isolated
    publish.side_effect = [
        {'success': True, 'message': 'done', 'result_url': 'https://example.com/1'},
        {'success': False, 'message': 'not submitted', 'safe_to_retry': True},
    ]
    first = run(inputs(tmp_path))
    assert first['exit_code'] == 1
    publish.reset_mock(side_effect=True)
    login.reset_mock()
    second = run(['--resume', first['run_id']])
    assert second['exit_code'] == 0
    assert second['mode'] == 'resume'
    assert publish.await_count == 1
    assert login.await_count == 1
    assert publish.await_args.args[0] == 'weibo'
    assert second['results'][0]['reused'] is True
    assert second['results'][0]['result_url'] == 'https://example.com/1'


@pytest.mark.parametrize('outcome', [
    {'success': False, 'message': 'unknown outcome'}, RuntimeError('connection lost after click'),
])
def test_uncertain_submission_is_never_retried(tmp_path, isolated, outcome):
    login, publish = isolated
    publish.side_effect = [{'success': True, 'message': 'ok'}, outcome]
    first = run(inputs(tmp_path))
    publish.reset_mock(side_effect=True)
    login.reset_mock()
    report = run(['--resume', first['run_id']])
    publish.assert_not_awaited()
    login.assert_not_awaited()
    assert report['results'][1]['error_code'] == 'RUN-004'
    assert report['results'][1]['safe_to_retry'] is False


def test_failed_login_can_be_resumed_without_prior_submission(tmp_path, isolated):
    login, publish = isolated
    login.return_value = False
    first = run(inputs(tmp_path))
    publish.assert_not_awaited()
    login.return_value = True
    assert run(['--resume', first['run_id']])['exit_code'] == 0
    assert publish.await_count == 2


def test_changed_media_rejected_before_login(tmp_path, isolated):
    login, publish = isolated
    first = run(inputs(tmp_path))
    (tmp_path / 'video.mp4').write_bytes(b'different')
    login.reset_mock()
    publish.reset_mock()
    report = run(['--resume', first['run_id']])
    assert report['errors'][0]['error_code'] == 'RUN-003'
    login.assert_not_awaited()
    publish.assert_not_awaited()


def test_explicit_new_command_starts_new_run(tmp_path, isolated):
    args = inputs(tmp_path)
    first, second = run(args), run(args)
    assert first['run_id'] != second['run_id']
    assert isolated[1].await_count == 4


def test_dry_run_has_plan_and_no_history_or_login(tmp_path, isolated):
    login, publish = isolated
    report = run([*inputs(tmp_path), '--dry-run'])
    assert report['exit_code'] == 0
    assert report['mode'] == 'dry_run'
    assert report['run_id'] is None
    assert report['results'] == []
    assert len(report['planned']) == 1
    assert not (tmp_path / 'publish-history.sqlite3').exists()
    login.assert_not_awaited()
    publish.assert_not_awaited()


def test_dry_run_does_not_require_license_or_generate_content(tmp_path, isolated):
    args = inputs(tmp_path)
    args[-1] = ''
    with patch('publish.orchestrator.require_valid_license') as license_check, patch(
        'publish.orchestrator.get_video_content', return_value=('', '')
    ) as content:
        report = run([*args, '--dry-run'])
    assert report['exit_code'] == 10
    license_check.assert_not_called()
    assert content.call_args.kwargs['auto_generate'] is False
    assert content.call_args.kwargs['force'] is False
    isolated[0].assert_not_awaited()


def test_dry_run_conversion_checks_without_creating_video(tmp_path, isolated):
    image = tmp_path / 'a.png'
    image.write_bytes(b'image')
    with patch('utils.image_to_video.check_moviepy_installed', return_value=True), patch(
        'publish.orchestrator.shutil.which', return_value='/fake/ffmpeg'
    ), patch('utils.image_to_video.convert_images_to_video_for_publish') as convert:
        report = run(['--note', '--images', str(image), '--title', 'test', '--platforms', 'tencent', '--convert-to-video', '--dry-run'])
    assert report['exit_code'] == 0
    assert report['planned'][0]['convert_to_video'] is True
    convert.assert_not_called()
    isolated[0].assert_not_awaited()


def test_resume_rejects_new_publish_inputs(tmp_path, isolated):
    first = run(inputs(tmp_path))
    isolated[1].reset_mock()
    report = run(['--resume', first['run_id'], '--title', 'different'])
    assert report['exit_code'] == 2
    isolated[1].assert_not_awaited()


def test_completed_resume_does_not_require_browser_environment(tmp_path, isolated):
    first = run(inputs(tmp_path))
    with patch('publish.orchestrator.runtime_preflight', AsyncMock(return_value=False)) as preflight:
        report = run(['--resume', first['run_id']])
    assert report['exit_code'] == 0
    assert all(result['reused'] for result in report['results'])
    preflight.assert_not_awaited()


def test_completed_resume_does_not_revalidate_elapsed_schedule(tmp_path, isolated):
    from datetime import datetime, timedelta
    from publish.config import PublishOverrides, default_params_from_overrides
    from publish.history import HistoryStore

    args = inputs(tmp_path)
    item = default_params_from_overrides(PublishOverrides(platforms='weibo', video=args[3], title='test'))
    item['publish_time'] = datetime.now() - timedelta(days=1)
    store = HistoryStore()
    run_id = store.create([item])
    store.claim(run_id, 0, 'weibo')
    store.finish(run_id, 0, 'weibo', {'success': True, 'message': 'done'}, False)
    report = run(['--resume', run_id])
    assert report['exit_code'] == 0
    isolated[1].assert_not_awaited()


def test_persistence_failure_stops_next_platform_and_keeps_completed_result(tmp_path, isolated):
    from publish.history import HistoryError

    with patch('publish.history.HistoryStore.finish', side_effect=HistoryError('RUN-005', 'disk full', 'check disk')):
        first = run(inputs(tmp_path))
    assert first['exit_code'] == 2
    assert first['results'][0]['success'] is True
    assert first['errors'][0]['error_code'] == 'RUN-005'
    assert isolated[1].await_count == 1
    isolated[1].reset_mock()
    second = run(['--resume', first['run_id']])
    assert second['results'][0]['error_code'] == 'RUN-004'
    assert isolated[1].await_count == 1
    assert isolated[1].await_args.args[0] == 'weibo'


def test_resume_does_not_claim_work_that_became_retryable_after_preflight(tmp_path, isolated):
    from publish.history import HistoryStore

    isolated[1].side_effect = RuntimeError('submission interrupted')
    first = run(inputs(tmp_path))
    isolated[1].reset_mock(side_effect=True)
    original = HistoryStore.runnable_entries

    def finish_in_other_process(store, run_id):
        entries = original(store, run_id)
        store.finish(run_id, 0, 'douyin', {'success': False, 'message': 'not submitted'}, True)
        return entries

    with patch.object(HistoryStore, 'runnable_entries', finish_in_other_process):
        second = run(['--resume', first['run_id']])
    assert second['results'][0]['error_code'] == 'RUN-004'
    assert isolated[1].await_count == 1
    assert isolated[1].await_args.args[0] == 'weibo'


@pytest.mark.parametrize('args', [[], ['--platforms', 'weibo', '--video', '/missing-video.mp4']])
def test_failed_dry_run_retains_mode(args, isolated):
    report = run([*args, '--dry-run'])
    assert report['exit_code'] == 10
    assert report['mode'] == 'dry_run'
    assert report['run_id'] is None
    assert report['results'] == []
    isolated[0].assert_not_awaited()
    isolated[1].assert_not_awaited()
