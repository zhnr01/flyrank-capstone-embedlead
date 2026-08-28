import asyncio
import threading

import pytest

from app.core.config import settings
from app.services import health
from app.services.health import HealthStatus, redis_health


def test_a_hanging_redis_is_bounded_by_the_health_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = threading.Event()
    release = threading.Event()

    def hang() -> None:
        started.set()
        release.wait(timeout=10)

    monkeypatch.setattr(health, "check_redis_sync", hang)
    monkeypatch.setattr(settings, "redis_health_timeout_seconds", 0.2)

    async def run() -> health.DependencyHealth:
        try:
            return await redis_health()
        finally:
            release.set()

    result = asyncio.run(asyncio.wait_for(run(), timeout=5))

    assert started.is_set()
    assert result.status is HealthStatus.DEGRADED
    assert result.error == "TimeoutError"
    assert result.response_time_ms < 2_000


async def test_a_refused_redis_is_degraded_not_unhealthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse() -> None:
        raise ConnectionError("connection refused")

    monkeypatch.setattr(health, "check_redis_sync", refuse)

    result = await redis_health()

    assert result.status is HealthStatus.DEGRADED


async def test_a_reachable_redis_is_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health, "check_redis_sync", lambda: None)

    result = await redis_health()

    assert result.status is HealthStatus.HEALTHY
    assert result.error is None


async def test_redis_degradation_never_makes_the_report_unhealthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse() -> None:
        raise ConnectionError("connection refused")

    monkeypatch.setattr(health, "check_redis_sync", refuse)
    monkeypatch.setattr(settings, "redis_url", "redis://localhost:6379/0")

    report = await health.readiness_report()

    assert report.checks["redis"].status is HealthStatus.DEGRADED
    assert report.status is report.checks["database"].status


async def test_redis_is_absent_from_the_report_when_no_url_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "redis_url", "")

    report = await health.readiness_report()

    assert "redis" not in report.checks
