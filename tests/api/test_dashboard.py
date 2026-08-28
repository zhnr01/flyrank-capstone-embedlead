from collections.abc import Generator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.dashboard_dependencies import get_dashboard_repository
from app.api.membership_dependencies import get_membership_repository
from app.core.auth import create_access_token
from app.main import app
from app.repositories.dashboard import InMemoryDashboardRepository, SubmissionRow
from app.repositories.memberships import InMemoryMembershipRepository

client = TestClient(app)


@pytest.fixture(autouse=True)
def dashboard() -> Generator[InMemoryDashboardRepository]:
    repository = InMemoryDashboardRepository()
    memberships = InMemoryMembershipRepository({7: 10, 8: 20})
    app.dependency_overrides[get_dashboard_repository] = lambda: repository
    app.dependency_overrides[get_membership_repository] = lambda: memberships
    yield repository
    app.dependency_overrides.clear()


def token_for(user_id: int) -> str:
    return create_access_token(f"user-{user_id}", timedelta(minutes=5))


def auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(user_id)}"}


def seed_rows(repository: InMemoryDashboardRepository) -> None:
    repository.add(
        SubmissionRow(
            id=1,
            tenant_id=10,
            widget_id=1,
            email="a@example.com",
            name="Ann",
            message=None,
            geo_country="GB",
            geo_city="London",
        )
    )
    repository.add(
        SubmissionRow(
            id=2,
            tenant_id=10,
            widget_id=1,
            email="b@example.com",
            name="Bob",
            message="hello",
            geo_country="GB",
            geo_city="Leeds",
        )
    )
    repository.add(
        SubmissionRow(
            id=3,
            tenant_id=20,
            widget_id=2,
            email="c@example.com",
            name="Cara",
            message=None,
            geo_country="DE",
            geo_city="Berlin",
        )
    )


def test_dashboard_requires_authentication() -> None:
    assert client.get("/api/v1/dashboard/submissions").status_code == 401


def test_dashboard_lists_only_the_callers_tenant(
    dashboard: InMemoryDashboardRepository,
) -> None:
    seed_rows(dashboard)

    body = client.get("/api/v1/dashboard/submissions", headers=auth(7)).json()

    assert [row["id"] for row in body["data"]] == [2, 1]
    assert all(row["email"].endswith("example.com") for row in body["data"])
    assert "tenant_id" not in body["data"][0]


def test_dashboard_other_tenant_sees_only_its_own(
    dashboard: InMemoryDashboardRepository,
) -> None:
    seed_rows(dashboard)

    body = client.get("/api/v1/dashboard/submissions", headers=auth(8)).json()

    assert [row["id"] for row in body["data"]] == [3]


def test_dashboard_pagination_is_bounded(
    dashboard: InMemoryDashboardRepository,
) -> None:
    seed_rows(dashboard)

    first = client.get(
        "/api/v1/dashboard/submissions?limit=1",
        headers=auth(7),
    ).json()

    assert len(first["data"]) == 1
    assert first["next_after_id"] == 2

    second = client.get(
        f"/api/v1/dashboard/submissions?limit=1&after_id={first['next_after_id']}",
        headers=auth(7),
    ).json()

    assert [row["id"] for row in second["data"]] == [1]
    assert second["next_after_id"] is None


def test_dashboard_rejects_oversized_limit() -> None:
    response = client.get("/api/v1/dashboard/submissions?limit=500", headers=auth(7))

    assert response.status_code == 422


def test_dashboard_filters_by_widget(
    dashboard: InMemoryDashboardRepository,
) -> None:
    seed_rows(dashboard)

    body = client.get(
        "/api/v1/dashboard/submissions?widget_id=1",
        headers=auth(7),
    ).json()

    assert [row["id"] for row in body["data"]] == [2, 1]


def test_dashboard_stats_are_tenant_scoped(
    dashboard: InMemoryDashboardRepository,
) -> None:
    seed_rows(dashboard)

    body = client.get("/api/v1/dashboard/stats", headers=auth(7)).json()

    assert body["total_submissions"] == 2
    assert body["by_country"] == [{"country": "GB", "count": 2}]
    assert body["by_widget"] == [{"widget_id": 1, "count": 2}]


def test_dashboard_stats_for_empty_tenant() -> None:
    body = client.get("/api/v1/dashboard/stats", headers=auth(8)).json()

    assert body["total_submissions"] == 0
    assert body["by_country"] == []
    assert body["by_widget"] == []
