"""Exercise cancellation against a local fake CLI, never a publishing service."""
import asyncio
import subprocess
import sys
from unittest.mock import patch

import pytest

from uploader.bilibili_uploader.main import BilibiliUploader


@pytest.mark.parametrize('stage', ['list', 'upload'])
def test_cancel_stops_active_process_and_no_later_upload(tmp_path, stage):
    account = tmp_path / 'fake_cli.py'
    account.write_text(
        'import pathlib, sys, time\n'
        'root = pathlib.Path(__file__).parent\n'
        'stage = sys.argv[1]\n'
        '(root / (stage + ".started")).touch()\n'
        f'if stage == {stage!r}:\n'
        '    while not (root / "release").exists():\n'
        '        time.sleep(0.01)\n',
        encoding='utf-8',
    )
    video = tmp_path / 'video.mp4'
    video.touch()
    uploader = BilibiliUploader('review', str(video), [], str(account))
    children = []
    real_popen = subprocess.Popen

    def track_process(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        children.append(child)
        return child

    async def scenario():
        task = asyncio.create_task(uploader.upload())
        try:
            async def wait_started():
                while not (tmp_path / (stage + '.started')).exists():
                    await asyncio.sleep(0.01)
            await asyncio.wait_for(wait_started(), 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 5)
            assert all(child.poll() is not None for child in children), 'cancel left a running child'
        finally:
            # Release the old threaded implementation too, so a regression cannot hang pytest.
            (tmp_path / 'release').touch()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    with patch('uploader.bilibili_uploader.runtime.require_biliup_binary', return_value=sys.executable), \
         patch('subprocess.Popen', side_effect=track_process):
        try:
            asyncio.run(scenario())
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                child.wait()
    if stage == 'list':
        assert not (tmp_path / 'upload.started').exists(), 'upload started after cancellation'
