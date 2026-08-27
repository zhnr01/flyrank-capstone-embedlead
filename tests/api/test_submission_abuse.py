from collections.abc import Generator
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.membership_dependencies import get_membership_repository
from app.api.outbox_dependencies import get_outbox_repository, get_unit_of_work
from app.api.rate_limit_dependencies import reset_rate_limiters
from app.api.submission_dependencies import get_submission_repository
from app.api.widget_dependencies import get_widget_repository
from app.core.auth import create_access_token
from app.core.config import settings
from app.main import app
from app.repositories.memberships import InMemoryMembershipRepository
from app.repositories.outbox import InMemoryOutboxRepository
from app.repositories.submissions import InMemorySubmissionRepository
from app.repositories.widgets import InMemoryWidgetRepository

client = TestClient(app)
ORIGIN = "http://localhost:5500"

Repositories = tuple[InMemoryWidgetRepository, InMemorySubmissionRepository]


class NoopUnitOfWork:
    def commit(self) -> None:
        return None


@pytest.fixture(autouse=True)
def repositories() -> Generator[Repositories]:
    widgets = InMemoryWidgetRepository()
    submissions = InMemorySubmissionRepository()
    memberships = InMemoryMembershipRepository({7: 10, 8: 20})
    app.dependency_overrides[get_widget_repository] = lambda: widgets
    app.dependency_overrides[get_submission_repository] = lambda: submissions
    app.dependency_overrides[get_membership_repository] = lambda: memberships
    app.dependency_overrides[get_outbox_repository] = lambda: InMemoryOutboxRepository()
    app.dependency_overrides[get_unit_of_work] = lambda: NoopUnitOfWork()
    reset_rate_limiters()
    yield widgets, submissions
    app.dependency_overrides.clear()
    reset_rate_limiters()


def make_widget(user_id: int = 7) -> int:
    token = create_access_token(f"user-{user_id}", timedelta(minutes=5))
    response = client.post(
        "/api/v1/widgets",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Abuse target", "kind": "contact"},
    )
    return int(response.json()["id"])


def submit(widget_id: int, **kwargs: str) -> httpx.Response:
    payload: dict[str, str] = {"email": "visitor@example.com", "name": "Visitor"}
    payload.update(kwargs)
    response: httpx.Response = client.post(
        f"/api/v1/public/widgets/{widget_id}/submissions",
        headers={"Origin": ORIGIN},
        json=payload,
    )
    return response


def test_burst_returns_429_with_retry_after() -> None:
    widget_id = make_widget()
    statuses = []
    for _ in range(settings.submission_rate_limit_per_ip + 3):
        statuses.append(submit(widget_id).status_code)

    assert 202 in statuses
    assert 429 in statuses
    blocked = submit(widget_id)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.json() == {"detail": "Too many submissions, retry later"}


def test_blocked_ip_does_not_block_a_different_ip(
    repositories: Repositories,
) -> None:
    _, submissions = repositories
    widget_id = make_widget()
    for _ in range(settings.submission_rate_limit_per_ip + 2):
        submit(widget_id)
    assert submit(widget_id).status_code == 429

    other = TestClient(app, client=("203.0.113.9", 5000))
    response = other.post(
        f"/api/v1/public/widgets/{widget_id}/submissions",
        headers={"Origin": ORIGIN},
        json={"email": "other@example.com", "name": "Other"},
    )

    assert response.status_code == 202
    assert any(s.email == "other@example.com" for s in submissions.all_for_tenant(10))


def test_forwarded_header_cannot_bypass_the_ip_limit() -> None:
    widget_id = make_widget()
    for _ in range(settings.submission_rate_limit_per_ip + 2):
        submit(widget_id)

    spoofed = client.post(
        f"/api/v1/public/widgets/{widget_id}/submissions",
        headers={"Origin": ORIGIN, "X-Forwarded-For": "198.51.100.77"},
        json={"email": "spoof@example.com", "name": "Spoof"},
    )

    assert spoofed.status_code == 429


def test_populated_honeypot_is_silently_dropped(
    repositories: Repositories,
) -> None:
    _, submissions = repositories
    widget_id = make_widget()

    response = submit(widget_id, website="http://spam.example")

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert submissions.all_for_tenant(10) == []


def test_empty_honeypot_is_accepted_normally(
    repositories: Repositories,
) -> None:
    _, submissions = repositories
    widget_id = make_widget()

    response = submit(widget_id, website="")

    assert response.status_code == 202
    assert len(submissions.all_for_tenant(10)) == 1
