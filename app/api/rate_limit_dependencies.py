import logging

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.rate_limit import RateLimiter

logger = logging.getLogger(__name__)

_ip_limiter = RateLimiter(
    limit=settings.submission_rate_limit_per_ip,
    window_seconds=settings.submission_rate_limit_window_seconds,
    max_keys=settings.rate_limit_max_tracked_keys,
)
_widget_limiter = RateLimiter(
    limit=settings.submission_rate_limit_per_widget,
    window_seconds=settings.submission_rate_limit_window_seconds,
    max_keys=settings.rate_limit_max_tracked_keys,
)


def reset_rate_limiters() -> None:
    global _ip_limiter, _widget_limiter
    _ip_limiter = RateLimiter(
        limit=settings.submission_rate_limit_per_ip,
        window_seconds=settings.submission_rate_limit_window_seconds,
        max_keys=settings.rate_limit_max_tracked_keys,
    )
    _widget_limiter = RateLimiter(
        limit=settings.submission_rate_limit_per_widget,
        window_seconds=settings.submission_rate_limit_window_seconds,
        max_keys=settings.rate_limit_max_tracked_keys,
    )


def client_address(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host


def enforce_submission_rate_limits(request: Request, widget_id: int) -> None:
    address = client_address(request)
    for limiter, key in (
        (_ip_limiter, f"ip:{address}"),
        (_widget_limiter, f"widget:{widget_id}"),
    ):
        decision = limiter.check(key)
        if not decision.allowed:
            scope = key.split(":")[0]
            logger.warning("submission rate limit exceeded for scope %s", scope)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many submissions, retry later",
                headers={"Retry-After": str(decision.retry_after_seconds)},
            )
