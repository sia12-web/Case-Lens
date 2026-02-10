"""In-memory sliding-window rate limiter."""

import time
from collections import defaultdict
from typing import Optional


class RateLimiter:
    """Track request timestamps per key and enforce a sliding-window limit."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 3600):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        """Check if *key* may make another request.

        Records the timestamp only when allowed.  Denied attempts
        do not consume a slot.
        """
        now = time.time()
        cutoff = now - self.window_seconds
        self._requests[key] = [ts for ts in self._requests[key] if ts > cutoff]

        if len(self._requests[key]) >= self.max_requests:
            return False

        self._requests[key].append(now)
        return True

    def remaining(self, key: str) -> int:
        """Requests remaining in the current window for *key*."""
        now = time.time()
        cutoff = now - self.window_seconds
        self._requests[key] = [ts for ts in self._requests[key] if ts > cutoff]
        return max(0, self.max_requests - len(self._requests[key]))

    def retry_after(self, key: str) -> Optional[int]:
        """Seconds until the oldest request in the window expires.

        Returns ``None`` if the key is not currently rate-limited.
        """
        now = time.time()
        cutoff = now - self.window_seconds
        active = [ts for ts in self._requests[key] if ts > cutoff]
        if len(active) < self.max_requests:
            return None
        oldest = min(active)
        return int(oldest + self.window_seconds - now) + 1
