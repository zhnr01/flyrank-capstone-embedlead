from collections.abc import Generator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.geo_dependencies import get_geo_chain
from app.api.membership_dependencies import get_membership_repository
from app.api.outbox_dependencies import get_outbox_repository, get_unit_of_work
from app.api.rate_limit_dependencies import reset_rate_limiters
from app.api.submission_dependencies import get_submission_repository
from app.api.widget_dependencies import get_widget_repository
from app.core.auth import create_access_token
from app.core.geo import GeoProviderChain
from app.core.outbox import SUBMISSION_CREATED_TOPIC, OutboxMessage, OutboxStatus
from app.main import app
from app.repositories.memberships import InMemoryMembershipRepository
from app.repositories.outbox import InMemoryOutboxRepository
from app.repositories.submissions import InMemorySubmissionRepository
from app.repositories.widgets import InMemoryWidgetRepository
from app.services.outbox_worker import OutboxWorker

ORIGIN = "http://localhost:5500"

Stores = tuple[InMemorySubmissionRepository, InMemoryOutboxRepository]


class NoopUnitOfWork:
    def commit(self) -> None:
        return None


class FailingTransport:
    name = "failing"

    def __init__(self) -> None:
        self.attempts = 0

    def send(self, message: OutboxMessage) -> None:
        self.attempts += 1
        raise ConnectionError("mail server unreachable")


class RecordingTransport:
    name = "recording"

    def __init__(self) -> None:
        self.delivered: list[str] = []

    def send(self, message: OutboxMessage) -> None:
        self.delivered.append(message.idempotency_key)


@pytest.fixture
def stores() -> Generator[Stores]:
    widgets = InMemoryWidgetRepository()
    submissions = InMemorySubmissionRepository()
    outbox = InMemoryOutboxRepository()
    memberships = InMemoryMembershipRepository({7: 10})
    app.dependency_overrides[get_widget_repository] = lambda: widgets
    app.dependency_overrides[get_submission_repository] = lambda: submissions
    app.dependency_overrides[get_outbox_repository] = lambda: outbox
    app.dependency_overrides[get_unit_of_work] = lambda: NoopUnitOfWork()
    app.dependency_overrides[get_membership_repository] = lambda: memberships
    app.dependency_overrides[get_geo_chain] = lambda: GeoProviderChain([])
    reset_rate_limiters()
    yield submissions, outbox
    app.dependency_overrides.clear()
    reset_rate_limiters()


client = TestClient(app)


def create_widget() -> int:
    token = create_access_token("user-7", timedelta(minutes=5))
    response = client.post(
        "/api/v1/widgets",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Outbox target", "kind": "contact"},
    )
    return int(response.json()["id"])


def submit(widget_id: int, email: str = "visitor@example.com") -> int:
    response = client.post(
        f"/api/v1/public/widgets/{widget_id}/submissions",
        headers={"Origin": ORIGIN},
        json={"email": email, "name": "Visitor"},
    )
    status_code: int = response.status_code
    return status_code


def test_submission_enqueues_exactly_one_message(stores: Stores) -> None:
    submissions, outbox = stores
    widget_id = create_widget()

    assert submit(widget_id) == 202

    messages = outbox.all_messages()
    assert len(messages) == 1
    assert messages[0].topic == SUBMISSION_CREATED_TOPIC
    assert messages[0].status == OutboxStatus.PENDING
    stored_id = submissions.all_for_tenant(10)[0].id
    assert messages[0].idempotency_key == f"submission:{stored_id}:created"
    assert messages[0].payload["submission_id"] == stored_id


def test_two_submissions_enqueue_distinct_messages(stores: Stores) -> None:
    _, outbox = stores
    widget_id = create_widget()

    assert submit(widget_id, "one@example.com") == 202
    assert submit(widget_id, "two@example.com") == 202

    keys = {message.idempotency_key for message in outbox.all_messages()}
    assert len(keys) == 2


def test_transport_failure_never_loses_the_submission(stores: Stores) -> None:
    submissions, outbox = stores
    widget_id = create_widget()
    assert submit(widget_id, "durable@example.com") == 202

    transport = FailingTransport()
    worker = OutboxWorker(outbox, transport, max_attempts=2)
    worker.run_once()
    worker.run_once()
    worker.run_once()

    stored = submissions.all_for_tenant(10)
    assert len(stored) == 1
    assert stored[0].email == "durable@example.com"

    message = outbox.all_messages()[0]
    assert message.status == OutboxStatus.FAILED
    assert message.last_error is not None
    assert "ConnectionError" in message.last_error


def test_worker_delivers_enqueued_submission_once(stores: Stores) -> None:
    _, outbox = stores
    widget_id = create_widget()
    assert submit(widget_id, "delivered@example.com") == 202

    transport = RecordingTransport()
    worker = OutboxWorker(outbox, transport, max_attempts=3)
    worker.run_once()
    worker.run_once()

    assert len(transport.delivered) == 1
    assert outbox.all_messages()[0].status == OutboxStatus.SENT


def test_honeypot_submission_enqueues_nothing(stores: Stores) -> None:
    submissions, outbox = stores
    widget_id = create_widget()

    response = client.post(
        f"/api/v1/public/widgets/{widget_id}/submissions",
        headers={"Origin": ORIGIN},
        json={
            "email": "bot@example.com",
            "name": "Bot",
            "website": "http://spam.example",
        },
    )

    assert response.status_code == 202
    assert submissions.all_for_tenant(10) == []
    assert outbox.all_messages() == []
