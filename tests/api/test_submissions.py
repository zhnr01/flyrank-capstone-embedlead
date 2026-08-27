from collections.abc import Generator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.membership_dependencies import get_membership_repository
from app.api.submission_dependencies import get_submission_repository
from app.api.widget_dependencies import get_widget_repository
from app.core.auth import create_access_token
from app.core.config import settings
from app.main import app
from app.repositories.memberships import InMemoryMembershipRepository
from app.repositories.submissions import InMemorySubmissionRepository
from app.repositories.widgets import InMemoryWidgetRepository

client = TestClient(app)
ALLOWED_ORIGIN = "http://localhost:5500"
DISALLOWED_ORIGIN = "http://evil.example"


Repositories = tuple[InMemoryWidgetRepository, InMemorySubmissionRepository]


@pytest.fixture(autouse=True)
def repositories() -> Generator[Repositories]:
    widgets = InMemoryWidgetRepository()
    submissions = InMemorySubmissionRepository()
    memberships = InMemoryMembershipRepository({7: 10, 8: 20})
    app.dependency_overrides[get_widget_repository] = lambda: widgets
    app.dependency_overrides[get_submission_repository] = lambda: submissions
    app.dependency_overrides[get_membership_repository] = lambda: memberships
    yield widgets, submissions
    app.dependency_overrides.clear()


def create_widget(user_id: int = 7) -> int:
    token = create_access_token(f"user-{user_id}", timedelta(minutes=5))
    response = client.post(
        "/api/v1/widgets",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Contact form", "kind": "contact"},
    )
    return int(response.json()["id"])


def test_valid_cross_origin_submission_is_accepted(
    repositories: Repositories,
) -> None:
    _, submissions = repositories
    widget_id = create_widget()

    response = client.post(
        f"/api/v1/public/widgets/{widget_id}/submissions",
        headers={"Origin": ALLOWED_ORIGIN},
        json={"email": "visitor@example.com", "name": "Visitor"},
    )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    stored = submissions.all_for_tenant(10)
    assert len(stored) == 1
    assert stored[0].email == "visitor@example.com"
    assert stored[0].widget_id == widget_id


def test_submission_response_does_not_leak_internal_identifiers() -> None:
    widget_id = create_widget()

    response = client.post(
        f"/api/v1/public/widgets/{widget_id}/submissions",
        json={"email": "visitor@example.com", "name": "Visitor"},
    )

    assert set(response.json()) == {"status"}


def test_submission_cannot_choose_its_own_tenant(
    repositories: Repositories,
) -> None:
    _, submissions = repositories
    widget_id = create_widget(user_id=7)

    response = client.post(
        f"/api/v1/public/widgets/{widget_id}/submissions",
        json={
            "email": "visitor@example.com",
            "name": "Visitor",
            "tenant_id": 20,
        },
    )

    assert response.status_code == 422
    assert submissions.all_for_tenant(20) == []


def test_malformed_payload_returns_clean_422() -> None:
    widget_id = create_widget()

    response = client.post(
        f"/api/v1/public/widgets/{widget_id}/submissions",
        json={"email": "not-an-email", "name": ""},
    )

    assert response.status_code == 422
    assert "detail" in response.json()


def test_oversized_payload_returns_413() -> None:
    widget_id = create_widget()
    oversized = "x" * (settings.max_submission_bytes + 1)

    response = client.post(
        f"/api/v1/public/widgets/{widget_id}/submissions",
        headers={"Content-Type": "application/json"},
        content=f'{{"email":"visitor@example.com","name":"{oversized}"}}'.encode(),
    )

    assert response.status_code == 413
    assert "detail" in response.json()


def test_submission_to_unknown_widget_returns_404(
    repositories: Repositories,
) -> None:
    _, submissions = repositories

    response = client.post(
        "/api/v1/public/widgets/999999/submissions",
        json={"email": "visitor@example.com", "name": "Visitor"},
    )

    assert response.status_code == 404
    assert submissions.all_for_tenant(10) == []


def test_cors_preflight_from_allowed_origin_is_answered() -> None:
    widget_id = create_widget()

    response = client.options(
        f"/api/v1/public/widgets/{widget_id}/submissions",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "POST" in response.headers["access-control-allow-methods"]


def test_disallowed_origin_is_not_granted_browser_access() -> None:
    widget_id = create_widget()

    response = client.options(
        f"/api/v1/public/widgets/{widget_id}/submissions",
        headers={
            "Origin": DISALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.headers.get("access-control-allow-origin") != DISALLOWED_ORIGIN
