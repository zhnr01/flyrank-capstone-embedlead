import math
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int


class RateLimiter:
    def __init__(
        self,
        *,
        limit: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if window_seconds < 1:
            raise ValueError("window_seconds must be at least 1")
        if max_keys < 1:
            raise ValueError("max_keys must be at least 1")
        self._limit = limit
        self._window = float(window_seconds)
        self._clock = clock
        self._max_keys = max_keys
        self._hits: OrderedDict[str, list[float]] = OrderedDict()

    @property
    def tracked_keys(self) -> int:
        return len(self._hits)

    def check(self, key: str) -> RateLimitDecision:
        now = self._clock()
        self._discard_expired(now)

        timestamps = self._hits.get(key)
        if timestamps is None:
            timestamps = []
            self._hits[key] = timestamps
        self._hits.move_to_end(key)

        if len(timestamps) >= self._limit:
            oldest = timestamps[0]
            remaining = self._window - (now - oldest)
            return RateLimitDecision(
                allowed=False,
                retry_after_seconds=max(1, math.ceil(remaining)),
            )

        timestamps.append(now)
        self._evict_over_cap()
        return RateLimitDecision(allowed=True, retry_after_seconds=0)

    def _discard_expired(self, now: float) -> None:
        cutoff = now - self._window
        for key in list(self._hits):
            timestamps = self._hits[key]
            fresh = [moment for moment in timestamps if moment > cutoff]
            if fresh:
                self._hits[key] = fresh
            else:
                del self._hits[key]

    def _evict_over_cap(self) -> None:
        while len(self._hits) > self._max_keys:
            self._hits.popitem(last=False)
