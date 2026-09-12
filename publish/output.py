"""Collect machine-readable outcomes without parsing human-readable logs."""
import contextlib
import json
import os
import sys
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class JsonReport:
    results: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    mode: str = 'publish'
    run_id: Optional[str] = None
    planned: list = field(default_factory=list)

    def document(self, exit_code: int) -> dict:
        return {
            'schema_version': 1,
            'mode': self.mode,
            'run_id': self.run_id,
            'planned': self.planned,
            'exit_code': exit_code,
            'summary': {
                'success': sum(r['success'] for r in self.results),
                'failed': sum(not r['success'] for r in self.results),
            },
            'results': self.results,
            'errors': self.errors,
        }


_report: ContextVar[Optional[JsonReport]] = ContextVar('publish_json_report', default=None)


def record_plan(items: list) -> None:
    report = _report.get()
    if report is not None:
        report.mode = 'dry_run'
        report.planned = [{
            'material': item.get('video_file') if item['content_type'] == 'video' else item['images'],
            'content_type': item['content_type'], 'title': item['title'],
            'platforms': item['enabled_platforms'],
            'publish_time': item['publish_time'].isoformat() if item.get('publish_time') else None,
            'convert_to_video': item.get('convert_to_video', False),
        } for item in items]


def record_run(run_id: str, mode: str) -> None:
    report = _report.get()
    if report is not None:
        report.run_id, report.mode = run_id, mode


def record_error(code: str, message: str, action: str) -> None:
    report = _report.get()
    if report is not None:
        report.errors.append({'error_code': code, 'message': message, 'action': action})


def record_result(params: dict, platform: str, result: dict) -> None:
    report = _report.get()
    if report is None:
        return
    success = result.get('success') is True
    report.results.append({
        'material': params.get('video_file') if params.get('content_type') == 'video' else list(params.get('images', [])),
        'content_type': params.get('content_type'),
        'platform': platform,
        'success': success,
        'message': result.get('message', ''),
        'error_code': None if success else result.get('error_code') or f'PUB-{platform}',
        'result_url': result.get('result_url'),
        'result_id': result.get('result_id'),
        'safe_to_retry': not success and result.get('safe_to_retry') is True,
        'reused': result.get('reused') is True,
        'action': result.get('action'),
    })


@contextlib.contextmanager
def _diagnostics_to_stderr():
    """Redirect Python output and inherited child stdout, restoring both on exit."""
    original = sys.stdout
    saved_fd = None
    stdout_fd = None
    try:
        try:
            stdout_fd, stderr_fd = original.fileno(), sys.stderr.fileno()
            original.flush()
            saved_fd = os.dup(stdout_fd)
            os.dup2(stderr_fd, stdout_fd)
        except (AttributeError, OSError, ValueError):
            # StringIO/test streams have no OS descriptor.
            if saved_fd is not None:
                os.close(saved_fd)
                saved_fd = None
        with contextlib.redirect_stdout(sys.stderr):
            yield
    finally:
        if saved_fd is not None:
            try:
                sys.stderr.flush()
                original.flush()
            finally:
                os.dup2(saved_fd, stdout_fd)
                os.close(saved_fd)


def run_with_json(command: Callable[[], int]) -> int:
    report = JsonReport()
    token = _report.set(report)
    try:
        with _diagnostics_to_stderr():
            try:
                code = command()
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 2
                if code:
                    record_error('CFG-001', '命令行参数无效', '运行 opub --help 检查参数')
            except KeyboardInterrupt:
                code = 130
                record_error('RUN-002', '发布已中断，部分平台结果可能尚未确认', '检查平台作品状态后再决定是否重试')
            except Exception:
                code = 2
                record_error('RUN-001', '运行时异常', '检查配置与环境后重试')
        print(json.dumps(report.document(code), ensure_ascii=False))
        return code
    finally:
        _report.reset(token)
