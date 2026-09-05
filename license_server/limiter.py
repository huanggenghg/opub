from __future__ import annotations

import heapq
import threading
import time
from collections import deque


class RateLimiter:
    """Bounded in-memory sliding-window limiter for the documented single worker.

    ``allow`` records one timestamp per admitted request and forgets entries
    older than ``window_seconds``, so each key holds at most ``limit``
    timestamps. A min-heap also removes keys after their final event expires,
    so historical random keys do not remain in memory forever. The limiter is
    process-local: it must not be shared between multiple workers.
    """

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.events: dict[str, deque[float]] = {}
        self.expirations: list[tuple[float, str]] = []
        self.lock = threading.Lock()

    def _expire(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self.expirations and self.expirations[0][0] <= now:
            _, key = heapq.heappop(self.expirations)
            events = self.events.get(key)
            if events is None:
                continue
            while events and events[0] <= cutoff:
                events.popleft()
            if not events:
                del self.events[key]

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            self._expire(now)
            events = self.events.get(key)
            if events is None:
                events = deque()
                self.events[key] = events
            if len(events) >= self.limit:
                return False
            events.append(now)
            heapq.heappush(self.expirations, (now + self.window_seconds, key))
            return True
