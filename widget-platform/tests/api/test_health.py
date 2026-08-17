import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import QueuePool

from app.core.db import database_connect_args, engine
from app.main import app
from app.services.health import DependencyHealth, database_health

client = TestClient(app)


def test_liveness_returns_healthy_without_dependency_checks() -> None:
    response = client.get("/api/v1/system/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_liveness_openapi_allows_only_healthy_status() -> None:
    schema = client.get("/api/v1/openapi.json").json()
    status_schema = schema["components"]["schemas"]["LivenessResponse"]["properties"][
        "status"
    ]

    assert status_schema["const"] == "healthy"


def test_readiness_returns_healthy_when_database_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def healthy_database() -> DependencyHealth:
        return DependencyHealth(status="healthy", response_time_ms=1.25)

    monkeypatch.setattr("app.services.health.database_health", healthy_database)

    response = client.get("/api/v1/system/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "checks": {
            "database": {
                "status": "healthy",
                "response_time_ms": 1.25,
                "error": None,
            }
        },
    }


def test_readiness_returns_safe_503_when_database_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable_database() -> DependencyHealth:
        return DependencyHealth(
            status="unhealthy",
            response_time_ms=4.5,
            error="OperationalError",
        )

    monkeypatch.setattr("app.services.health.database_health", unavailable_database)

    response = client.get("/api/v1/system/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unhealthy",
        "checks": {
            "database": {
                "status": "unhealthy",
                "response_time_ms": 4.5,
                "error": "OperationalError",
            }
        },
    }


def test_database_engine_has_bounded_waits() -> None:
    assert isinstance(engine.pool, QueuePool)
    assert engine.pool.timeout() == 2
    assert database_connect_args == {
        "connect_timeout": 2,
        "options": "-c statement_timeout=2000",
    }


def test_database_health_converts_probe_failure_to_safe_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failed_probe() -> None:
        raise RuntimeError("secret database details")

    monkeypatch.setattr("app.services.health.check_database_sync", failed_probe)

    report = asyncio.run(database_health())

    assert report.status == "unhealthy"
    assert report.error == "RuntimeError"
    assert "secret database details" not in report.model_dump_json()
