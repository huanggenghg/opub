import asyncio
import contextlib
import io
import unittest
from unittest.mock import AsyncMock, patch

from publish import orchestrator
from publish.config import PublishOverrides, default_params_from_overrides


class EnvironmentCommandTests(unittest.TestCase):
    def test_repair_does_not_require_license_or_publish(self):
        with patch('publish.runtime.repair_environment', return_value=True) as repair, patch(
            'publish.orchestrator.require_valid_license'
        ) as license_check, patch('publish.orchestrator.run_publish', AsyncMock()) as publish:
            code = orchestrator.main(['--repair-env', '--with-video'])
        self.assertEqual(code, 0)
        repair.assert_called_once_with(with_video=True)
        license_check.assert_not_called()
        publish.assert_not_called()

    def test_repair_failure_exits_environment_error(self):
        with patch('publish.runtime.repair_environment', return_value=False):
            self.assertEqual(orchestrator.main(['--repair-env']), 11)

    def test_repair_rejects_publish_and_license_options(self):
        for args in [
            ['--repair-env', '--video', 'a.mp4'],
            ['--repair-env', '--activate'],
            ['--with-video'],
        ]:
            with self.subTest(args=args), self.assertRaises(SystemExit), patch(
                'publish.runtime.repair_environment'
            ) as repair:
                orchestrator.main(args)
            repair.assert_not_called()


class LoginClassificationIntegrationTests(unittest.TestCase):
    def test_weibo_upload_validation_preserves_check_error(self):
        from publish.auth import LoginCheckError
        from uploader.weibo_uploader.main import WeiboVideo, WeiboNote

        uploaders = [
            WeiboVideo(title='test', file_path='/fake.mp4', tags=[], publish_date=0, account_file='/fake.json'),
            WeiboNote(image_paths=['/fake.jpg'], note='test', account_file='/fake.json'),
        ]
        for uploader in uploaders:
            with self.subTest(uploader=type(uploader).__name__), patch.object(
                uploader, 'validate_upload_args', AsyncMock(side_effect=LoginCheckError('network'))
            ):
                result = asyncio.run(uploader.upload())
            self.assertEqual(result.get('error_code'), 'NET-001')
            self.assertFalse(result.get('account_issue', False))

    def test_uploader_check_error_keeps_its_classification_in_dispatch(self):
        from publish.auth import LoginCheckError
        from publish.dispatch import publish_to_platform
        from uploader.weibo_uploader.main import WeiboVideo

        params = {**self.params(), 'account_file': '/fake.json'}
        with patch.object(WeiboVideo, 'validate_base_args', return_value=None), patch.object(
            WeiboVideo, 'upload', AsyncMock(side_effect=LoginCheckError('page'))
        ):
            result = asyncio.run(publish_to_platform('weibo', params))
        self.assertEqual(result['error_code'], 'PAGE-001')
        self.assertFalse(result['safe_to_retry'])

    def params(self):
        return default_params_from_overrides(PublishOverrides(
            platforms='weibo', video='/fake.mp4', title='test'
        ))

    def test_network_error_does_not_report_account_failure(self):
        with patch('publish.orchestrator.ensure_account_login', AsyncMock(side_effect=TimeoutError('private url'))), patch(
            'publish.orchestrator.publish_to_platform', AsyncMock()
        ) as publish, contextlib.redirect_stderr(io.StringIO()):
            results = asyncio.run(orchestrator.publish_one_item(self.params()))
        result = results['weibo']
        self.assertEqual(result['error_code'], 'NET-001')
        self.assertFalse(result.get('account_issue', False))
        self.assertNotIn('private url', result['message'])
        self.assertEqual(orchestrator.exit_code_from_results({'video': results}), 2)
        publish.assert_not_called()

    def test_broken_greenlet_is_environment_failure(self):
        with patch('publish.orchestrator.ensure_account_login', AsyncMock(side_effect=AttributeError(
            "module 'greenlet' has no attribute 'greenlet'"
        ))), contextlib.redirect_stderr(io.StringIO()):
            result = asyncio.run(orchestrator.publish_one_item(self.params()))['weibo']
        self.assertEqual(result['error_code'], 'ENV-006')
        self.assertFalse(result['account_issue'])

    def test_recovery_error_preserves_environment_classification(self):
        expired = {'success': False, 'account_issue': True, 'issue_type': 'login_expired', 'safe_to_retry': True}
        with patch('publish.orchestrator.ensure_account_login', AsyncMock(side_effect=[True, ImportError('greenlet')])), patch(
            'publish.orchestrator.publish_to_platform', AsyncMock(return_value=expired)
        ) as publish, contextlib.redirect_stderr(io.StringIO()):
            results = asyncio.run(orchestrator.publish_one_item(self.params()))
        self.assertEqual(results['weibo']['error_code'], 'ENV-006')
        self.assertFalse(results['weibo']['account_issue'])
        self.assertEqual(publish.await_count, 1)
