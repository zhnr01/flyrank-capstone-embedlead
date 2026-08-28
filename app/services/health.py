import asyncio
import time
from enum import StrEnum

from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import settings
from app.core.db import engine
from app.core.redis_rate_limit import REDIS_FAILURES, shared_redis_client

MILLISECONDS_PER_SECOND = 1000
RESPONSE_TIME_PRECISION = 2
DATABASE_CHECK = "database"
REDIS_CHECK = "redis"


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"


class DependencyHealth(BaseModel):
    status: HealthStatus
    response_time_ms: float
    error: str | None = None


class HealthReport(BaseModel):
    status: HealthStatus
    checks: dict[str, DependencyHealth]


def check_database_sync() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def check_redis_sync() -> None:
    shared_redis_client(settings.redis_url).ping()


def elapsed_ms(started: float) -> float:
    seconds = time.perf_counter() - started
    return round(seconds * MILLISECONDS_PER_SECOND, RESPONSE_TIME_PRECISION)


async def database_health() -> DependencyHealth:
    started = time.perf_counter()
    try:
        await asyncio.to_thread(check_database_sync)
    except Exception as exc:
        return DependencyHealth(
            status=HealthStatus.UNHEALTHY,
            response_time_ms=elapsed_ms(started),
            error=type(exc).__name__,
        )
    return DependencyHealth(
        status=HealthStatus.HEALTHY,
        response_time_ms=elapsed_ms(started),
    )


async def redis_health() -> DependencyHealth:
    started = time.perf_counter()
    try:
        await asyncio.wait_for(
            asyncio.to_thread(check_redis_sync),
            timeout=settings.redis_health_timeout_seconds,
        )
    except (TimeoutError, *REDIS_FAILURES) as exc:
        return DependencyHealth(
            status=HealthStatus.DEGRADED,
            response_time_ms=elapsed_ms(started),
            error=type(exc).__name__,
        )
    return DependencyHealth(
        status=HealthStatus.HEALTHY,
        response_time_ms=elapsed_ms(started),
    )


async def readiness_report() -> HealthReport:
    database = await database_health()
    checks = {DATABASE_CHECK: database}
    if settings.redis_url:
        checks[REDIS_CHECK] = await redis_health()
    return HealthReport(status=database.status, checks=checks)
