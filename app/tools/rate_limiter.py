from __future__ import annotations

import functools
import logging
import random
import time
from collections import deque
from collections.abc import Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

logger = logging.getLogger(__name__)


class RateLimitExceeded(RuntimeError):
    pass


class RateLimiter:
    """Synchronous requests-per-minute limiter with retry and exponential backoff."""

    def __init__(self, requests_per_minute: int = 30, max_retries: int = 3) -> None:
        self.requests_per_minute = max(1, requests_per_minute)
        self.max_retries = max(0, max_retries)
        self._timestamps: deque[float] = deque()

    def acquire(self) -> None:
        now = time.monotonic()
        while self._timestamps and now - self._timestamps[0] >= 60:
            self._timestamps.popleft()
        if len(self._timestamps) >= self.requests_per_minute:
            raise RateLimitExceeded(
                f"Rate limit exceeded: {self.requests_per_minute} requests/minute"
            )
        self._timestamps.append(now)

    def run(self, func: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                self.acquire()
                return func(*args, **kwargs)
            except RateLimitExceeded as exc:
                last_error = exc
                sleep_for = min(2**attempt + random.uniform(0, 0.25), 10)
                logger.warning("Rate limit hit, retrying in %.2fs", sleep_for)
                time.sleep(sleep_for)
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                sleep_for = min(2**attempt + random.uniform(0, 0.25), 10)
                logger.warning("Provider call failed, retrying in %.2fs: %s", sleep_for, exc)
                time.sleep(sleep_for)
        assert last_error is not None
        raise last_error

    def decorate(self, func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            return self.run(func, *args, **kwargs)

        return wrapper
