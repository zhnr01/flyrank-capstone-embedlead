import logging

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.metrics import increment
from app.core.rate_limit import RateLimiter
from app.core.redis_rate_limit import (
    RateLimiterProtocol,
    RedisRateLimiter,
    ResilientRateLimiter,
    shared_redis_client,
)

logger = logging.getLogger(__name__)

IP_SCOPE = "ip"
WIDGET_SCOPE = "widget"
LOGIN_SCOPE = "login"
UNKNOWN_ADDRESS = "unknown"


def _in_process(limit: int, window_seconds: int) -> RateLimiter:
    return RateLimiter(
        limit=limit,
        window_seconds=window_seconds,
        max_keys=settings.rate_limit_max_tracked_keys,
    )


def build_limiter(limit: int, window_seconds: int | None = None) -> RateLimiterProtocol:
    window = window_seconds or settings.submission_rate_limit_window_seconds
    fallback = _in_process(limit, window)
    if not settings.redis_url:
        return fallback
    try:
        shared = RedisRateLimiter(
            redis_client=shared_redis_client(settings.redis_url),
            limit=limit,
            window_seconds=window,
        )
    except Exception:
        logger.warning(
            "rate_limit_store_unavailable",
            extra={"fields": {"stage": "construction", "fallback": "in_process"}},
        )
        return fallback
    return ResilientRateLimiter(primary=shared, fallback=fallback)


_ip_limiter: RateLimiterProtocol = build_limiter(settings.submission_rate_limit_per_ip)
_widget_limiter: RateLimiterProtocol = build_limiter(
    settings.submission_rate_limit_per_widget
)
_login_limiter: RateLimiterProtocol = build_limiter(
    settings.login_rate_limit_per_ip, settings.login_rate_limit_window_seconds
)


def reset_rate_limiters() -> None:
    global _ip_limiter, _widget_limiter, _login_limiter
    _ip_limiter.reset()
    _widget_limiter.reset()
    _login_limiter.reset()
    _ip_limiter = build_limiter(settings.submission_rate_limit_per_ip)
    _widget_limiter = build_limiter(settings.submission_rate_limit_per_widget)
    _login_limiter = build_limiter(
        settings.login_rate_limit_per_ip, settings.login_rate_limit_window_seconds
    )


def close_rate_limiters() -> None:
    global _ip_limiter, _widget_limiter, _login_limiter
    _ip_limiter.close()
    _widget_limiter.close()
    _login_limiter.close()


def client_address(request: Request) -> str:
    if request.client is None:
        return UNKNOWN_ADDRESS
    return request.client.host


def enforce_submission_rate_limits(request: Request, widget_id: int) -> None:
    address = client_address(request)
    for limiter, scope, key in (
        (_ip_limiter, IP_SCOPE, f"{IP_SCOPE}:{address}"),
        (_widget_limiter, WIDGET_SCOPE, f"{WIDGET_SCOPE}:{widget_id}"),
    ):
        decision = limiter.check(key)
        if not decision.allowed:
            increment("submission_rate_limited", scope)
            logger.warning(
                "submission_rate_limited",
                extra={
                    "fields": {
                        "scope": scope,
                        "retry_after": decision.retry_after_seconds,
                    }
                },
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many submissions, retry later",
                headers={"Retry-After": str(decision.retry_after_seconds)},
            )


def enforce_login_rate_limit(request: Request) -> None:
    address = client_address(request)
    decision = _login_limiter.check(f"{LOGIN_SCOPE}:{address}")
    if decision.allowed:
        return
    increment("login_rate_limited", LOGIN_SCOPE)
    logger.warning(
        "login_rate_limited",
        extra={
            "fields": {
                "scope": LOGIN_SCOPE,
                "retry_after": decision.retry_after_seconds,
            }
        },
    )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many login attempts, retry later",
        headers={"Retry-After": str(decision.retry_after_seconds)},
    )
