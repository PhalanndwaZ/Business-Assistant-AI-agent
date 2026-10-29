"""Apply a bounded in-memory sliding-window rate limit per identity."""

from __future__ import annotations

import math
import time
from collections import deque
from threading import Lock


class RateLimiter:
    """Track request timestamps and enforce a small per-identity window."""

    def __init__(
        self,
        max_requests: int = 20,
        window_seconds: float = 60.0,
    ) -> None:
        """Create a limiter with a request cap and a rolling time window."""
        if max_requests < 1 or window_seconds <= 0:
            raise ValueError("Rate-limit settings must be positive.")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = {}
        self._lock = Lock()

    def retry_after(self, identity: str) -> int | None:
        """Record one request, returning seconds to wait when the cap is reached."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            for existing_identity in list(self._requests):
                timestamps = self._requests[existing_identity]
                while timestamps and timestamps[0] <= cutoff:
                    timestamps.popleft()
                if not timestamps:
                    del self._requests[existing_identity]

            timestamps = self._requests.get(identity)
            if timestamps is None:
                if len(self._requests) >= 10_000:
                    return math.ceil(self.window_seconds)
                timestamps = deque()
                self._requests[identity] = timestamps
            if len(timestamps) >= self.max_requests:
                return max(
                    1,
                    math.ceil(self.window_seconds - (now - timestamps[0])),
                )
            timestamps.append(now)
        return None
