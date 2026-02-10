"""Unit tests for the in-memory rate limiter."""

import time

from caselens.rate_limiter import RateLimiter


def test_allows_under_limit():
    """Requests under the limit are allowed."""
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    assert limiter.is_allowed("key1") is True
    assert limiter.is_allowed("key1") is True
    assert limiter.is_allowed("key1") is True


def test_blocks_over_limit():
    """Request exceeding the limit is denied."""
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    assert limiter.is_allowed("key1") is True
    assert limiter.is_allowed("key1") is True
    assert limiter.is_allowed("key1") is False


def test_separate_keys_independent():
    """Different keys have independent limits."""
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    assert limiter.is_allowed("key1") is True
    assert limiter.is_allowed("key2") is True
    # key1 is now at limit
    assert limiter.is_allowed("key1") is False
    # key2 is also at limit
    assert limiter.is_allowed("key2") is False


def test_window_expiry():
    """Requests are allowed again after the window expires."""
    limiter = RateLimiter(max_requests=1, window_seconds=0.1)
    assert limiter.is_allowed("key1") is True
    assert limiter.is_allowed("key1") is False
    time.sleep(0.15)
    assert limiter.is_allowed("key1") is True


def test_remaining_count():
    """remaining() returns correct count."""
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    assert limiter.remaining("key1") == 3
    limiter.is_allowed("key1")
    assert limiter.remaining("key1") == 2
    limiter.is_allowed("key1")
    assert limiter.remaining("key1") == 1
    limiter.is_allowed("key1")
    assert limiter.remaining("key1") == 0


def test_retry_after_when_limited():
    """retry_after() returns seconds when rate-limited."""
    limiter = RateLimiter(max_requests=1, window_seconds=3600)
    limiter.is_allowed("key1")
    retry = limiter.retry_after("key1")
    assert retry is not None
    assert 3599 <= retry <= 3601


def test_retry_after_when_not_limited():
    """retry_after() returns None when not rate-limited."""
    limiter = RateLimiter(max_requests=5, window_seconds=60)
    assert limiter.retry_after("key1") is None
    limiter.is_allowed("key1")
    assert limiter.retry_after("key1") is None
