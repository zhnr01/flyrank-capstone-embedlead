import asyncio
import time
from enum import StrEnum

from pydantic import BaseModel
from sqlalchemy import text

from app.core.db import engine

MILLISECONDS_PER_SECOND = 1000
RESPONSE_TIME_PRECISION = 2


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


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


async def readiness_report() -> HealthReport:
    database = await database_health()
    return HealthReport(status=database.status, checks={"database": database})
