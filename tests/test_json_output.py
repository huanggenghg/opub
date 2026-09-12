import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from publish import orchestrator


class JsonOutputTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.images = [str(Path(workspace.name) / name) for name in ('a.jpg', 'b.jpg')]
        for image in self.images:
            Path(image).write_bytes(b'image')

    def run_cli(self, args, licensed=True):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), patch(
            'publish.orchestrator.require_valid_license', return_value=(licensed, 'LIC-001')
        ):
            code = orchestrator.main(['--output', 'json', *args])
        return code, json.loads(stdout.getvalue()), stderr.getvalue()

    def test_configuration_failure_is_json(self):
        code, report, stderr = self.run_cli([])
        self.assertEqual(code, 10)
        self.assertEqual(report['schema_version'], 1)
        self.assertEqual(report['exit_code'], code)
        self.assertEqual(report['errors'][0]['error_code'], 'CFG-002')
        self.assertEqual(report['results'], [])

    def test_license_failure_is_json(self):
        code, report, _ = self.run_cli([], licensed=False)
        self.assertEqual(code, 13)
        self.assertEqual(report['errors'][0]['error_code'], 'LIC-001')

    def test_mixed_results_preserve_material_and_retry_permission(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / '测试.mp4'
            video.touch()
            with patch('publish.orchestrator.runtime_preflight', AsyncMock(return_value=True)), patch(
                'publish.orchestrator.ensure_account_login', AsyncMock(return_value=True)
            ), patch('publish.orchestrator.publish_to_platform', AsyncMock(side_effect=[
                {'success': True, 'message': 'ok', 'result_url': 'https://example.com/v/1', 'result_id': '1'},
                {'success': False, 'message': 'unknown outcome'},
            ])):
                code, report, stderr = self.run_cli([
                    '--platforms', 'douyin,weibo', '--video', str(video), '--title', '测试'
                ])
        self.assertEqual(code, 1)
        self.assertEqual(report['summary'], {'success': 1, 'failed': 1})
        self.assertEqual(len(report['results']), 2)
        success, failure = report['results']
        self.assertEqual(success['material'], str(video))
        self.assertEqual(success['platform'], 'douyin')
        self.assertEqual(success['result_id'], '1')
        self.assertEqual(failure['error_code'], 'PUB-weibo')
        self.assertFalse(failure['safe_to_retry'])
        self.assertIn('多平台发布', stderr)

    def test_exception_keeps_previously_completed_platforms(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / 'test.mp4'
            video.touch()
            with patch('publish.orchestrator.runtime_preflight', AsyncMock(return_value=True)), patch(
                'publish.orchestrator.ensure_account_login', AsyncMock(return_value=True)
            ), patch('publish.orchestrator.publish_to_platform', AsyncMock(side_effect=[
                {'success': True, 'message': 'ok'}, RuntimeError('unexpected'),
            ])):
                code, report, _ = self.run_cli([
                    '--platforms', 'douyin,weibo', '--video', str(video), '--title', 'test'
                ])
        self.assertEqual(code, 2)
        self.assertEqual(report['results'][0]['platform'], 'douyin')
        self.assertEqual(report['errors'][0]['error_code'], 'RUN-001')

    def test_repeated_calls_do_not_share_results(self):
        _, first, _ = self.run_cli([])
        _, second, _ = self.run_cli([], licensed=False)
        self.assertEqual(len(first['errors']), 1)
        self.assertEqual(len(second['errors']), 1)

    def test_parser_failure_has_json_document(self):
        code, report, _ = self.run_cli(['--video-duration', 'bad'])
        self.assertEqual(code, 2)
        self.assertEqual(report['errors'][0]['error_code'], 'CFG-001')

    def test_missing_duplicate_output_value_still_returns_json(self):
        code, report, _ = self.run_cli(['--output'])
        self.assertEqual(code, 2)
        self.assertEqual(report['errors'][0]['error_code'], 'CFG-001')

    def test_repair_starts_without_cryptography(self):
        script = '''
import importlib.abc, sys
class BlockCrypto(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'cryptography' or fullname.startswith('cryptography.'):
            raise ImportError('simulated missing cryptography')
sys.meta_path.insert(0, BlockCrypto())
import publish.runtime
publish.runtime.repair_environment = lambda with_video=False: True
from publish_all import main
raise SystemExit(main(['--output', 'json', '--repair-env']))
'''
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['exit_code'], 0)

    def test_note_materials_and_confirmed_retry_permission(self):
        with patch('publish.orchestrator.runtime_preflight', AsyncMock(return_value=True)), patch(
            'publish.orchestrator.ensure_account_login', AsyncMock(return_value=True)
        ), patch('publish.orchestrator.publish_to_platform', AsyncMock(return_value={
            'success': False, 'message': 'retry allowed', 'safe_to_retry': True,
        })):
            code, report, _ = self.run_cli([
                '--platforms', 'xiaohongshu', '--note', '--images', ','.join(self.images), '--title', 'test'
            ])
        self.assertEqual(code, 2)
        self.assertEqual(report['results'][0]['material'], self.images)
        self.assertTrue(report['results'][0]['safe_to_retry'])

    def test_interruption_has_explicit_error(self):
        with patch('publish.orchestrator.run_publish', AsyncMock(side_effect=KeyboardInterrupt)):
            code, report, _ = self.run_cli([])
        self.assertEqual(code, 130)
        self.assertEqual(report['errors'][0]['error_code'], 'RUN-002')

    def test_missing_moviepy_provides_video_repair_guidance(self):
        with patch('utils.image_to_video.check_moviepy_installed', return_value=False), patch('publish.orchestrator.runtime_preflight', AsyncMock(return_value=True)):
            code, report, _ = self.run_cli([
                '--platforms', 'tencent', '--note', '--images', self.images[0], '--title', 'test', '--convert-to-video'
            ])
        self.assertEqual(code, 11)
        self.assertEqual(report['errors'][0]['error_code'], 'ENV-005')
        self.assertIn('--with-video', report['errors'][0]['action'])

    def test_native_child_and_prebound_logger_do_not_pollute_stdout(self):
        script = '''
import subprocess, sys
from utils.log import weibo_logger
from publish.output import run_with_json
def work():
    print('progress')
    weibo_logger.info('logger-progress')
    subprocess.run([sys.executable, '-c', "print('child-progress')"], check=True)
    return 0
run_with_json(work)
'''
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['exit_code'], 0)
        self.assertIn('child-progress', result.stderr)
        self.assertIn('logger-progress', result.stderr)


if __name__ == '__main__':
    unittest.main()
