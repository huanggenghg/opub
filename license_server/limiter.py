from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    """Bounded in-memory sliding-window limiter for the documented single worker.

    ``allow`` records one timestamp per admitted request and forgets entries
    older than ``window_seconds``, so each key holds at most ``limit``
    timestamps. The limiter is process-local: it must not be shared between
    multiple workers.
    """

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.events: defaultdict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            events = self.events[key]
            while events and events[0] <= now - self.window_seconds:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True
