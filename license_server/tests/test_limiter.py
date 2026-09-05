from __future__ import annotations

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
