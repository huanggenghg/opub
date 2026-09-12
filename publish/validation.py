"""Validate the complete request without opening a browser or modifying media."""
import math
from datetime import datetime, timedelta
from pathlib import Path

from publish.constants import IMAGE_EXTENSIONS, NOTE_PLATFORMS, PLATFORM_NAMES, VIDEO_EXTENSIONS
from publish.content import resolve_path


class ValidationError(ValueError):
    def __init__(self, code, message, action):
        super().__init__(message)
        self.code, self.action = code, action


def validate_file(value, extensions, code):
    path = Path(resolve_path(str(value)))
    if not path.is_file():
        raise ValidationError(code, f'素材不是可用文件: {path}', '检查素材路径，确保文件存在')
    if path.suffix.lower() not in extensions:
        raise ValidationError(code, f'不支持的素材格式: {path.suffix}', f'使用以下格式: {", ".join(sorted(extensions))}')
    try:
        with path.open('rb') as stream:
            stream.read(1)
    except OSError as exc:
        raise ValidationError(code, f'无法读取素材: {path}', '检查文件权限后重试') from exc
    return str(path.resolve())


def validate_schedule(params):
    when = params.get('publish_time')
    if when is None or when == 0:
        if params.get('publish_strategy') == 'scheduled':
            raise ValidationError('CFG-006', '缺少定时时间', '提供 --schedule')
        return
    if not isinstance(when, datetime):
        raise ValidationError('CFG-006', '定时时间格式无效', '使用 YYYY-MM-DD HH:MM 格式')
    if 'bilibili' in params.get('enabled_platforms', []):
        raise ValidationError('CFG-006', '当前 B站上传接口未传递定时时间', '移除 B站或使用立即发布，避免定时任务被立即发出')
    if when <= datetime.now(tz=when.tzinfo) + timedelta(hours=2):
        raise ValidationError('CFG-006', '定时发布时间必须晚于当前时间两小时', '调整 --schedule 后重试')


def validate_inputs(params, video_files):
    platforms = params.get('enabled_platforms', [])
    if not platforms or any(p not in PLATFORM_NAMES for p in platforms):
        raise ValidationError('CFG-002', '启用平台为空或包含未知平台', '运行 opub --help 检查 --platforms')
    kind = params.get('content_type')
    if kind not in {'video', 'note'}:
        raise ValidationError('CFG-001', '内容类型无效', '选择视频或图文发布')
    if kind == 'note' and not params.get('convert_to_video'):
        unsupported = set(platforms) - NOTE_PLATFORMS
        if unsupported:
            raise ValidationError('CFG-005', f'以下平台不支持直接图文发布: {", ".join(sorted(unsupported))}', '使用 --convert-to-video 或调整平台')
    validate_schedule(params)
    start = params.get('start_from', 1)
    if not isinstance(start, int) or isinstance(start, bool) or start < 1:
        raise ValidationError('CFG-007', '起始序号必须是正整数', '调整 --start-from，序号从 1 开始')
    if kind == 'note':
        if start != 1:
            raise ValidationError('CFG-007', '图文任务不支持跳过视频序号', '移除 --start-from')
        if not params.get('images'):
            raise ValidationError('CFG-004', '图文模式需要图片', '提供 --images')
        for image in params['images']:
            validate_file(image, IMAGE_EXTENSIONS, 'CFG-004')
    else:
        if params.get('convert_to_video') or params.get('images'):
            raise ValidationError('CFG-001', '图文参数不能用于视频模式', '图文使用 --note；视频使用 --video')
        if not video_files:
            raise ValidationError('CFG-003', '未找到视频文件', '检查 --video 路径')
        if start > len(video_files):
            raise ValidationError('CFG-007', '起始序号超出视频数量', '调整 --start-from')
        for video in video_files:
            validate_file(video, VIDEO_EXTENSIONS, 'CFG-003')
    duration = params.get('video_duration', 5)
    if params.get('convert_to_video') and (not isinstance(duration, (float, int)) or not math.isfinite(duration) or duration <= 0):
        raise ValidationError('CFG-008', '图片展示时长必须是有限正数', '调整 --video-duration')
