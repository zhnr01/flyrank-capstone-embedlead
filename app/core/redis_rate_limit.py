import logging
import math
import time
from functools import lru_cache
from typing import Protocol

from limits import RateLimitItemPerSecond
from limits.storage import RedisStorage
from limits.strategies import MovingWindowRateLimiter
from redis import Redis
from redis import exceptions as redis_exceptions
from redis.backoff import NoBackoff
from redis.retry import Retry

from app.core.config import settings
from app.core.rate_limit import RateLimitDecision

logger = logging.getLogger(__name__)

KEY_PREFIX = "ratelimit"
REDIS_FAILURES = (
    redis_exceptions.RedisError,
    redis_exceptions.ConnectionError,
    redis_exceptions.TimeoutError,
    OSError,
)


class RateLimiterProtocol(Protocol):
    def check(self, key: str) -> RateLimitDecision: ...

    def reset(self) -> None: ...

    def close(self) -> None: ...


def build_redis_client(url: str) -> Redis:
    return Redis.from_url(
        url,
        decode_responses=True,
        socket_timeout=settings.redis_socket_timeout_seconds,
        socket_connect_timeout=settings.redis_connect_timeout_seconds,
        health_check_interval=settings.redis_health_check_interval_seconds,
        retry_on_timeout=False,
        retry=Retry(NoBackoff(), 0),
    )


@lru_cache(maxsize=4)
def shared_redis_client(url: str) -> Redis:
    return build_redis_client(url)


class RedisRateLimiter:
    def __init__(
        self,
        *,
        redis_client: Redis,
        limit: int,
        window_seconds: int,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if window_seconds < 1:
            raise ValueError("window_seconds must be at least 1")
        self._client = redis_client
        self._item = RateLimitItemPerSecond(limit, window_seconds)
        storage = RedisStorage(
            "redis://invalid",
            connection_pool=redis_client.connection_pool,
            key_prefix=KEY_PREFIX,
        )
        self._strategy = MovingWindowRateLimiter(storage)

    def check(self, key: str) -> RateLimitDecision:
        if self._strategy.hit(self._item, key):
            return RateLimitDecision(allowed=True, retry_after_seconds=0)
        stats = self._strategy.get_window_stats(self._item, key)
        remaining = stats.reset_time - time.time()
        return RateLimitDecision(
            allowed=False,
            retry_after_seconds=max(1, math.ceil(remaining)),
        )

    def reset(self) -> None:
        for found in self._client.scan_iter(f"{KEY_PREFIX}*"):
            self._client.delete(found)

    def close(self) -> None:
        shared_redis_client.cache_clear()
        self._client.close()


class ResilientRateLimiter:
    def __init__(
        self,
        *,
        primary: RateLimiterProtocol,
        fallback: RateLimiterProtocol,
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    def check(self, key: str) -> RateLimitDecision:
        try:
            return self._primary.check(key)
        except REDIS_FAILURES:
            logger.warning(
                "rate_limit_store_unavailable",
                extra={"fields": {"fallback": "in_process"}},
            )
            return self._fallback.check(key)

    def reset(self) -> None:
        try:
            self._primary.reset()
        except REDIS_FAILURES:
            logger.warning(
                "rate_limit_store_unavailable",
                extra={"fields": {"operation": "reset"}},
            )
        self._fallback.reset()

    def close(self) -> None:
        try:
            self._primary.close()
        except REDIS_FAILURES:
            logger.warning("rate_limit_store_close_failed")
        self._fallback.close()
