from __future__ import annotations

import threading

from license_server.limiter import RateLimiter


def test_expired_keys_are_removed_during_later_requests(monkeypatch) -> None:
    now = 100.0
    monkeypatch.setattr("license_server.limiter.time.monotonic", lambda: now)
    limiter = RateLimiter(limit=2, window_seconds=10)

    for key in ("old-1", "old-2", "old-3"):
        assert limiter.allow(key)
    assert len(limiter.events) == 3

    now = 111.0
    assert limiter.allow("current")

    assert set(limiter.events) == {"current"}


def test_concurrent_calls_keep_each_key_ordered_by_timestamp(monkeypatch) -> None:
    older_clock_read = threading.Event()
    newer_finished = threading.Event()

    class InterleavingLock:
        def __init__(self) -> None:
            self._lock = threading.Lock()

        def __enter__(self):
            if (
                threading.current_thread().name == "older-request"
                and older_clock_read.is_set()
            ):
                assert newer_finished.wait(timeout=1)
            self._lock.acquire()
            return self

        def __exit__(self, exc_type, exc_value, traceback) -> None:
            self._lock.release()

    def monotonic() -> float:
        if threading.current_thread().name == "older-request":
            older_clock_read.set()
            return 100.0
        if threading.current_thread().name == "newer-request":
            return 101.0
        return 110.5

    monkeypatch.setattr("license_server.limiter.time.monotonic", monotonic)
    limiter = RateLimiter(limit=2, window_seconds=10)
    limiter.lock = InterleavingLock()  # type: ignore[assignment]
    admitted: list[bool] = []

    def allow_request() -> None:
        admitted.append(limiter.allow("shared"))
        if threading.current_thread().name == "newer-request":
            newer_finished.set()

    older = threading.Thread(target=allow_request, name="older-request")
    older.start()
    assert older_clock_read.wait(timeout=1)
    newer = threading.Thread(target=allow_request, name="newer-request")
    newer.start()
    older.join(timeout=1)
    newer.join(timeout=1)

    assert not older.is_alive()
    assert not newer.is_alive()
    assert admitted == [True, True]
    assert limiter.allow("shared")
