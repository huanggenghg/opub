"""SQLite publish journal: an interrupted submission requires human reconciliation."""
import hashlib
import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from conf import BASE_DIR


class HistoryError(Exception):
    """An actionable failure that must stop publishing before another submission."""

    def __init__(self, code, message, action):
        super().__init__(message)
        self.code = code
        self.message = message
        self.action = action


_PARAMS = {
    'content_type', 'title', 'desc', 'tags', 'video_file', 'images',
    'publish_strategy', 'publish_time', 'enabled_platforms', 'platforms',
    'convert_to_video', 'video_duration', 'start_from', 'force',
}
_RESULTS = {
    'success', 'message', 'error_code', 'result_url', 'result_id',
    'safe_to_retry', 'action',
}
_VERSION = 1


def _invalid(message='发布记录不存在或已损坏'):
    return HistoryError('RUN-003', message, '检查 run_id 与发布记录；必要时核对平台作品后创建新任务')


def _fingerprint(path):
    try:
        digest = hashlib.sha256()
        with open(path, 'rb') as media:
            for block in iter(lambda: media.read(1024 * 1024), b''):
                digest.update(block)
        return digest.hexdigest()
    except OSError as exc:
        raise HistoryError('RUN-003', '发布素材缺失或无法读取', '恢复原始素材后再恢复任务') from exc


class HistoryStore:
    """Persist snapshots and atomic per-item, per-platform submission decisions."""

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else BASE_DIR / 'publish-history.sqlite3'
        with self._connection() as connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY, version INTEGER NOT NULL,
                snapshot TEXT NOT NULL, fingerprints TEXT NOT NULL
            )''')
            connection.execute('''CREATE TABLE IF NOT EXISTS entries (
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                item_index INTEGER NOT NULL, platform TEXT NOT NULL,
                state TEXT NOT NULL, result TEXT, retryable INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (run_id, item_index, platform)
            )''')

    @contextmanager
    def _connection(self):
        connection = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(str(self.path), timeout=5)
            connection.row_factory = sqlite3.Row
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
            connection.execute('PRAGMA foreign_keys = ON')
            with connection:
                yield connection
        except (sqlite3.Error, OSError) as exc:
            raise HistoryError('RUN-005', '无法读取或保存发布记录', '检查数据目录权限及磁盘空间；若有其他发布进程，请等待其结束') from exc
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _run(connection, run_id):
        if not isinstance(run_id, str) or not re.fullmatch(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', run_id
        ):
            raise _invalid('run_id 格式无效')
        run = connection.execute('SELECT * FROM runs WHERE run_id = ?', (run_id,)).fetchone()
        if run is None:
            raise _invalid('未找到发布记录')
        if run['version'] != _VERSION:
            raise _invalid('发布记录版本不受支持')
        return run

    def create(self, items: list[dict]) -> str:
        snapshots = []
        fingerprints = {}
        try:
            if not items:
                raise _invalid('发布任务不能为空')
            for item in items:
                snapshot = {key: value for key, value in item.items() if key in _PARAMS}
                platforms = list(dict.fromkeys(snapshot['enabled_platforms']))
                snapshot['enabled_platforms'] = platforms
                accounts = {}
                for platform in platforms:
                    key = f'{platform}_account'
                    value = snapshot.get('platforms', {}).get(key)
                    if value:
                        path = Path(value).expanduser()
                        accounts[key] = str((path if path.is_absolute() else BASE_DIR / path).resolve())
                snapshot['platforms'] = accounts
                if snapshot.get('publish_time') is not None:
                    snapshot['publish_time'] = snapshot['publish_time'].isoformat()
                paths = []
                if snapshot.get('video_file'):
                    snapshot['video_file'] = str(Path(snapshot['video_file']).expanduser().resolve())
                    paths.append(snapshot['video_file'])
                snapshot['images'] = [str(Path(path).expanduser().resolve()) for path in snapshot.get('images', [])]
                paths.extend(snapshot['images'])
                if not paths or not platforms:
                    raise _invalid('发布任务缺少素材或平台')
                for path in paths:
                    if path not in fingerprints:
                        fingerprints[path] = _fingerprint(path)
                snapshots.append(snapshot)
            encoded = json.dumps(snapshots, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            raise _invalid('发布参数无法保存') from exc
        run_id = str(uuid.uuid4())
        with self._connection() as connection:
            connection.execute('INSERT INTO runs VALUES (?, ?, ?, ?)', (
                run_id, _VERSION, encoded, json.dumps(fingerprints),
            ))
            connection.executemany(
                'INSERT INTO entries (run_id, item_index, platform, state) VALUES (?, ?, ?, ?)',
                [(run_id, index, platform, 'pending') for index, item in enumerate(snapshots)
                 for platform in item['enabled_platforms']],
            )
        return run_id

    def load(self, run_id: str) -> list[dict]:
        with self._connection() as connection:
            run = self._run(connection, run_id)
        try:
            snapshots = json.loads(run['snapshot'])
            fingerprints = json.loads(run['fingerprints'])
            if not isinstance(snapshots, list) or not snapshots or not fingerprints:
                raise _invalid()
            for path, expected in fingerprints.items():
                if _fingerprint(path) != expected:
                    raise HistoryError('RUN-003', '发布素材内容已改变', '恢复原始素材后再恢复任务；新素材请创建新任务')
            for snapshot in snapshots:
                if snapshot.get('publish_time') is not None:
                    snapshot['publish_time'] = datetime.fromisoformat(snapshot['publish_time'])
            return snapshots
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            raise _invalid() from exc

    def _entry(self, connection, run_id, item_index, platform):
        self._run(connection, run_id)
        if type(item_index) is not int or item_index < 0 or not isinstance(platform, str):
            raise _invalid('发布记录条目无效')
        entry = connection.execute(
            'SELECT * FROM entries WHERE run_id = ? AND item_index = ? AND platform = ?',
            (run_id, item_index, platform),
        ).fetchone()
        if entry is None:
            raise _invalid('发布记录中没有此素材或平台')
        return entry

    def runnable_entries(self, run_id: str) -> set:
        """Read a preflight hint; claim() still makes the atomic submission decision."""
        with self._connection() as connection:
            self._run(connection, run_id)
            rows = connection.execute(
                "SELECT item_index, platform FROM entries WHERE run_id = ? "
                "AND (state = 'pending' OR (state = 'failed' AND retryable = 1))",
                (run_id,),
            ).fetchall()
        return {(row['item_index'], row['platform']) for row in rows}

    def claim(self, run_id: str, item_index: int, platform: str, allow_submit: bool = True) -> dict:
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            entry = self._entry(connection, run_id, item_index, platform)
            if entry['state'] == 'success':
                try:
                    result = json.loads(entry['result'])
                    if not isinstance(result, dict) or result.get('success') is not True:
                        raise _invalid()
                except (ValueError, TypeError) as exc:
                    raise _invalid() from exc
                return {'state': 'success', 'result': result}
            if allow_submit and (entry['state'] == 'pending' or (entry['state'] == 'failed' and entry['retryable'])):
                connection.execute(
                    "UPDATE entries SET state = 'running', result = NULL, retryable = 0 "
                    'WHERE run_id = ? AND item_index = ? AND platform = ?',
                    (run_id, item_index, platform),
                )
                return {'state': 'claimed'}
            if entry['state'] not in ('pending', 'running', 'failed'):
                raise _invalid()
            return {'state': 'blocked', 'result': {
                'success': False, 'error_code': 'RUN-004', 'safe_to_retry': False,
                'message': '上次发布结果未确认，已阻止重复提交',
                'action': '先到平台核对作品状态；确认需要再次发布后创建新任务',
            }}

    def finish(self, run_id: str, item_index: int, platform: str, result: dict, retryable: bool) -> None:
        try:
            if type(result.get('success')) is not bool or type(retryable) is not bool:
                raise _invalid('发布结果格式无效')
            saved = {key: value for key, value in result.items() if key in _RESULTS}
            encoded = json.dumps(saved, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError, AttributeError) as exc:
            raise _invalid('发布结果无法保存') from exc
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            entry = self._entry(connection, run_id, item_index, platform)
            if entry['state'] != 'running':
                raise _invalid('发布记录状态不允许写入结果')
            success = saved['success']
            connection.execute(
                'UPDATE entries SET state = ?, result = ?, retryable = ? '
                'WHERE run_id = ? AND item_index = ? AND platform = ?',
                ('success' if success else 'failed', encoded, int(retryable and not success),
                 run_id, item_index, platform),
            )
