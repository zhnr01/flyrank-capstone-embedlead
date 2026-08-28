from fastapi.testclient import TestClient

from app.api.lifecycle import close_resources
from app.main import app


def test_the_app_declares_a_lifespan_so_shutdown_is_hooked() -> None:
    assert app.router.lifespan_context is not None


def test_startup_and_shutdown_run_without_error() -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/system/health/live").status_code == 200


def test_close_resources_is_idempotent() -> None:
    close_resources()
    close_resources()


def test_close_resources_replaces_the_connection_pool() -> None:
    from app.core.db import engine

    before = id(engine.pool)
    close_resources()

    assert id(engine.pool) != before


def test_a_request_still_works_after_resources_are_closed() -> None:
    close_resources()
    client = TestClient(app)

    assert client.get("/api/v1/system/health/live").status_code == 200
