"""Durable publish decisions must survive crashes without duplicate submission."""
import concurrent.futures
import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from publish.history import HistoryError, HistoryStore


class HistoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.media = self.root / 'video.mp4'
        self.media.write_bytes(b'original video')
        self.path = self.root / 'history.sqlite3'
        self.store = HistoryStore(self.path)
        self.params = {
            'content_type': 'video', 'video_file': str(self.media),
            'images': [], 'title': 'A title', 'desc': 'Description', 'tags': ['tag'],
            'enabled_platforms': ['douyin', 'bilibili'],
            'platforms': {'douyin_account': 'cookies/douyin/account.json',
                          'bilibili_account': str(self.root / 'account.json')},
            'publish_time': datetime(2030, 1, 2, 3, 4, tzinfo=timezone.utc),
            'publish_strategy': 'scheduled', 'force': True,
        }

    def test_snapshot_restores_datetime_paths_and_never_copies_cookies(self):
        self.params['cookies'] = [{'secret': 'COOKIE_SECRET'}]
        self.params['platforms']['cookies'] = 'COOKIE_SECRET'
        (self.root / 'account.json').write_text('COOKIE_SECRET')
        with patch('publish.history.BASE_DIR', self.root):
            run_id = self.store.create([self.params])
        self.params['title'] = 'edited after create'
        restored = HistoryStore(self.path).load(run_id)[0]
        self.assertEqual(restored['title'], 'A title')
        self.assertEqual(restored['publish_time'], self.params['publish_time'])
        self.assertEqual(restored['platforms']['douyin_account'], str((self.root / 'cookies/douyin/account.json').resolve()))
        self.assertNotIn('cookies', restored)
        self.assertNotIn('cookies', restored['platforms'])
        self.assertNotIn(b'COOKIE_SECRET', self.path.read_bytes())

    def test_success_survives_reopen_and_cannot_be_overwritten(self):
        run = self.store.create([self.params])
        self.assertEqual(self.store.claim(run, 0, 'douyin')['state'], 'claimed')
        result = {'success': True, 'result_url': 'https://example.com/123', 'result_id': '123'}
        self.store.finish(run, 0, 'douyin', result, retryable=False)
        self.assertEqual(HistoryStore(self.path).claim(run, 0, 'douyin'), {'state': 'success', 'result': result})
        with self.assertRaises(HistoryError):
            self.store.finish(run, 0, 'douyin', {'success': False}, retryable=True)
        self.assertEqual(self.store.claim(run, 0, 'douyin')['result'], result)
        self.assertEqual(self.store.claim(run, 0, 'bilibili')['state'], 'claimed')

    def test_interrupted_claim_stays_running_and_does_not_change_owner_result(self):
        run = self.store.create([self.params])
        self.store.claim(run, 0, 'douyin')
        blocked = HistoryStore(self.path).claim(run, 0, 'douyin')
        self.assertEqual(blocked['state'], 'blocked')
        self.assertFalse(blocked['result']['safe_to_retry'])
        self.store.finish(run, 0, 'douyin', {'success': True}, retryable=False)
        self.assertEqual(self.store.claim(run, 0, 'douyin')['state'], 'success')

    def test_retryable_failure_can_be_claimed_but_uncertain_failure_cannot(self):
        run = self.store.create([self.params])
        for platform, retryable in [('douyin', True), ('bilibili', False)]:
            self.store.claim(run, 0, platform)
            self.store.finish(run, 0, platform, {'success': False, 'message': 'failed'}, retryable)
        self.assertEqual(HistoryStore(self.path).claim(run, 0, 'douyin')['state'], 'claimed')
        self.assertEqual(HistoryStore(self.path).claim(run, 0, 'bilibili')['state'], 'blocked')

    def test_simultaneous_connections_only_one_claims(self):
        run = self.store.create([self.params])
        stores = [HistoryStore(self.path), HistoryStore(self.path)]
        barrier = threading.Barrier(2)
        def claim(store):
            barrier.wait()
            return store.claim(run, 0, 'douyin')['state']
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(pool.map(claim, stores), ['claimed', 'blocked'])

    def test_modified_or_missing_media_blocks_resume(self):
        for change in ('modify', 'delete'):
            with self.subTest(change=change):
                self.media.write_bytes(b'original video')
                run = self.store.create([self.params])
                if change == 'modify':
                    self.media.write_bytes(b'changed content')
                else:
                    self.media.unlink()
                with self.assertRaises(HistoryError) as raised:
                    self.store.load(run)
                self.assertEqual(raised.exception.code, 'RUN-003')
                self.assertTrue(raised.exception.action)

    def test_all_note_images_are_fingerprinted(self):
        second = self.root / 'second.jpg'
        second.write_bytes(b'image')
        params = dict(self.params, content_type='note', video_file='', images=[str(self.media), str(second)])
        run = self.store.create([params])
        second.write_bytes(b'changed')
        with self.assertRaises(HistoryError):
            self.store.load(run)

    def test_invalid_unknown_run_and_unknown_entry_are_rejected(self):
        for run in ('../../account.json', '00000000-0000-0000-0000-000000000000'):
            with self.assertRaises(HistoryError):
                self.store.load(run)
        run = self.store.create([self.params])
        with self.assertRaises(HistoryError):
            self.store.claim(run, 3, 'douyin')
        with self.assertRaises(HistoryError):
            self.store.claim(run, 0, 'unknown')
        with self.assertRaises(HistoryError):
            self.store.finish(run, 0, 'douyin', {'success': True}, False)

    def test_missing_media_does_not_persist_partial_run(self):
        missing = dict(self.params, video_file=str(self.root / 'missing.mp4'))
        with self.assertRaises(HistoryError):
            self.store.create([self.params, missing])
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM runs').fetchone()[0], 0)

    def test_unknown_version_is_rejected(self):
        run = self.store.create([self.params])
        with sqlite3.connect(self.path) as connection:
            connection.execute('UPDATE runs SET version = 999 WHERE run_id = ?', (run,))
        with self.assertRaises(HistoryError):
            self.store.load(run)
        with self.assertRaises(HistoryError):
            self.store.claim(run, 0, 'douyin')

    def test_sqlite_failure_rolls_back_whole_run(self):
        with sqlite3.connect(self.path) as connection:
            connection.execute("""CREATE TRIGGER reject_second_platform
                BEFORE INSERT ON entries WHEN NEW.platform = 'bilibili'
                BEGIN SELECT RAISE(ABORT, 'disk write rejected'); END""")
        with self.assertRaises(HistoryError):
            self.store.create([self.params])
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM runs').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT count(*) FROM entries').fetchone()[0], 0)

    def test_result_serialization_failure_leaves_claim_blocked(self):
        run = self.store.create([self.params])
        self.store.claim(run, 0, 'douyin')
        with self.assertRaises(HistoryError):
            self.store.finish(run, 0, 'douyin', {'success': True, 'result_id': object()}, False)
        self.assertEqual(HistoryStore(self.path).claim(run, 0, 'douyin')['state'], 'blocked')

    def test_corrupt_database_errors_are_actionable(self):
        self.path.write_text('not a database')
        with self.assertRaises(HistoryError) as raised:
            HistoryStore(self.path)
        self.assertTrue(raised.exception.action)


if __name__ == '__main__':
    unittest.main()
