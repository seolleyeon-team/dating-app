from __future__ import annotations

from collections import deque
import threading
import time
from typing import Callable, Deque, Optional


class AzureRequestRateLimiter:
    """Enforce a paced rolling request-start quota for one worker process.

    Cloud Run is configured with one worker instance and one request at a time,
    so a process-local paced schedule is the safety boundary for the currently
    discovered Azure quota. Starts are separated by ``window / maximum`` so a
    2 RPM quota cannot burst two requests at time zero. A slot is reserved
    immediately before each provider attempt, including retries, because every
    attempt consumes quota.
    """

    def __init__(
        self,
        maximum_requests: int,
        *,
        window_seconds: float = 60.0,
        clock_fn: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        maximum = int(maximum_requests)
        window = float(window_seconds)
        if maximum < 1:
            raise ValueError("maximum_requests must be at least 1")
        if window <= 0.0:
            raise ValueError("window_seconds must be greater than zero")
        self._maximum_requests = maximum
        self._window_seconds = window
        self._minimum_start_interval = window / maximum
        self._clock = clock_fn
        self._sleep = sleep_fn
        self._lock = threading.Lock()
        self._request_starts: Deque[float] = deque()
        self._next_start_at: Optional[float] = None

    def acquire(self, timeout: Optional[float] = None) -> bool:
        deadline = None
        if timeout is not None:
            deadline = self._clock() + max(0.0, float(timeout))

        with self._lock:
            now = self._clock()
            self._discard_expired(now)
            scheduled_start = max(now, self._next_start_at or now)
            if deadline is not None and scheduled_start >= deadline:
                return False
            self._next_start_at = scheduled_start + self._minimum_start_interval
            self._request_starts.append(scheduled_start)
            wait_seconds = scheduled_start - now

        # Reserve the slot before sleeping so concurrent callers receive
        # distinct starts. If sleep is interrupted, the reserved slot is
        # conservatively lost rather than allowing a quota burst.
        if wait_seconds > 0.0:
            self._sleep(wait_seconds)
        return True

    def _discard_expired(self, now: float) -> None:
        cutoff = now - self._window_seconds
        while self._request_starts and self._request_starts[0] <= cutoff:
            self._request_starts.popleft()


__all__ = ["AzureRequestRateLimiter"]
