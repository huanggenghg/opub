import asyncio
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from uploader.bilibili_uploader import runtime


def test_async_command_captures_output_and_return_code():
    with patch.object(runtime, 'require_biliup_binary', return_value=Path(sys.executable)):
        result = asyncio.run(runtime.run_biliup_command_async([
            '-c', 'import sys; sys.stdout.buffer.write(b"ok\\xff"); sys.stderr.write("error"); sys.exit(3)',
        ]))
    assert result.returncode == 3
    assert result.stdout == 'ok\ufffd'
    assert result.stderr == 'error'


@pytest.mark.parametrize('interactive', [False, True])
def test_async_timeout_kills_and_reaps_real_process(interactive):
    children = []
    real_popen = subprocess.Popen

    def track_process(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        children.append(child)
        return child

    with patch.object(runtime, 'require_biliup_binary', return_value=Path(sys.executable)), \
         patch.object(runtime, '_needs_detached_login_console', return_value=False), \
         patch('subprocess.Popen', side_effect=track_process):
        with pytest.raises(subprocess.TimeoutExpired):
            asyncio.run(runtime.run_biliup_command_async(
                ['-c', 'import time; time.sleep(30)'], interactive=interactive, timeout=0.1,
            ))
    assert len(children) == 1
    assert children[0].poll() is not None


@pytest.mark.parametrize('command, interactive, detached, seconds', [
    ('list', False, False, 60),
    ('renew', False, False, 60),
    ('login', True, False, 360),
    ('login', True, True, 360),
    ('upload', False, False, 3600),
])
def test_async_defaults_and_console_modes(command, interactive, detached, seconds):
    process = SimpleNamespace(returncode=0, communicate=AsyncMock(return_value=(None, None)))
    with patch.object(runtime, 'require_biliup_binary', return_value=Path('/mock/biliup')), \
         patch.object(runtime, '_needs_detached_login_console', return_value=detached), \
         patch.object(runtime.asyncio, 'create_subprocess_exec', return_value=process) as spawn, \
         patch.object(runtime.asyncio, 'wait', wraps=asyncio.wait) as wait:
        asyncio.run(runtime.run_biliup_command_async([command], interactive=interactive))
    assert wait.call_args.kwargs['timeout'] == seconds
    options = spawn.call_args.kwargs
    if interactive:
        assert 'stdout' not in options and 'stderr' not in options
    else:
        assert options['stdout'] == asyncio.subprocess.PIPE
        assert options['stderr'] == asyncio.subprocess.PIPE
    assert options.get('creationflags') == (runtime._CREATE_NEW_CONSOLE if detached else None)


@pytest.mark.parametrize('initial_timeout', [False, True])
def test_cancel_during_cleanup_remains_cancelled_and_waits_for_reaping(initial_timeout):
    async def scenario():
        killed, reaped = asyncio.Event(), asyncio.Event()

        async def communicate():
            await reaped.wait()
            process.returncode = -9
            return b'', b''

        process = SimpleNamespace(returncode=None, communicate=communicate, kill=Mock(side_effect=killed.set), wait=AsyncMock(return_value=-9))
        with patch.object(runtime, 'require_biliup_binary', return_value=Path('/mock/biliup')), \
             patch.object(runtime.asyncio, 'create_subprocess_exec', return_value=process):
            task = asyncio.create_task(runtime.run_biliup_command_async(['list'], timeout=0.01 if initial_timeout else 60))
            if not initial_timeout:
                await asyncio.sleep(0)
                task.cancel()
            await asyncio.wait_for(killed.wait(), 2)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done(), 'cancellation returned before child was reaped'
            reaped.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        process.kill.assert_called_once()
        assert process.returncode is not None

    asyncio.run(scenario())


def test_cancel_at_command_completion_is_not_swallowed():
    async def scenario():
        async def communicate():
            asyncio.get_running_loop().call_soon(task.cancel)
            return b'', b''

        process = SimpleNamespace(returncode=0, communicate=communicate, wait=AsyncMock(return_value=0))
        with patch.object(runtime, 'require_biliup_binary', return_value=Path('/mock/biliup')), \
             patch.object(runtime.asyncio, 'create_subprocess_exec', return_value=process):
            task = asyncio.create_task(runtime.run_biliup_command_async(['list']))
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(scenario())


def test_pipe_error_still_waits_for_child_exit():
    async def scenario():
        process = SimpleNamespace(
            returncode=None, communicate=AsyncMock(side_effect=OSError('pipe read failed')),
            kill=Mock(), wait=AsyncMock(return_value=-9),
        )
        with patch.object(runtime, 'require_biliup_binary', return_value=Path('/mock/biliup')), \
             patch.object(runtime.asyncio, 'create_subprocess_exec', return_value=process):
            with pytest.raises(OSError, match='pipe read failed'):
                await runtime.run_biliup_command_async(['list'])
        process.kill.assert_called_once()
        process.wait.assert_awaited_once()

    asyncio.run(scenario())
