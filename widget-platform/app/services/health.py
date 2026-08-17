import asyncio
import time
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text

from app.core.db import engine


class DependencyHealth(BaseModel):
    status: Literal["healthy", "unhealthy"]
    response_time_ms: float
    error: str | None = None


class HealthReport(BaseModel):
    status: Literal["healthy", "unhealthy"]
    checks: dict[str, DependencyHealth]


def check_database_sync() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


async def database_health() -> DependencyHealth:
    started = time.perf_counter()
    try:
        await asyncio.to_thread(check_database_sync)
    except Exception as exc:
        return DependencyHealth(
            status="unhealthy",
            response_time_ms=round((time.perf_counter() - started) * 1000, 2),
            error=type(exc).__name__,
        )
    return DependencyHealth(
        status="healthy",
        response_time_ms=round((time.perf_counter() - started) * 1000, 2),
    )


async def readiness_report() -> HealthReport:
    database = await database_health()
    status: Literal["healthy", "unhealthy"] = database.status
    return HealthReport(status=status, checks={"database": database})
