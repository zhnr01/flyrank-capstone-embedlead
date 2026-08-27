import pytest

from app.core.outbox import OutboxMessage, submission_created_key
from app.repositories.outbox import InMemoryOutboxRepository
from app.services.outbox_worker import OutboxWorker


class CountingTransport:
    name = "counting"

    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, message: OutboxMessage) -> None:
        self.sent.append(message.idempotency_key)


class FailingTransport:
    name = "failing"

    def __init__(self) -> None:
        self.attempts = 0

    def send(self, message: OutboxMessage) -> None:
        self.attempts += 1
        raise ConnectionError("transport unavailable")


def test_idempotency_key_is_derived_and_stable() -> None:
    assert submission_created_key(42) == "submission:42:created"
    assert submission_created_key(42) == submission_created_key(42)


def test_enqueue_creates_one_pending_message() -> None:
    repository = InMemoryOutboxRepository()

    repository.enqueue(
        topic="submission.created",
        idempotency_key=submission_created_key(1),
        payload={"submission_id": 1},
    )

    pending = repository.claim_pending(limit=10)
    assert len(pending) == 1
    assert pending[0].status == "pending"
    assert pending[0].attempts == 0
    assert pending[0].payload == {"submission_id": 1}


def test_duplicate_enqueue_is_ignored() -> None:
    repository = InMemoryOutboxRepository()
    key = submission_created_key(1)

    first = repository.enqueue(
        topic="submission.created", idempotency_key=key, payload={}
    )
    second = repository.enqueue(
        topic="submission.created", idempotency_key=key, payload={}
    )

    assert first is not None
    assert second is None
    assert len(repository.all_messages()) == 1


def test_worker_delivers_and_marks_sent() -> None:
    repository = InMemoryOutboxRepository()
    repository.enqueue(
        topic="submission.created",
        idempotency_key=submission_created_key(5),
        payload={"submission_id": 5},
    )
    transport = CountingTransport()
    worker = OutboxWorker(repository, transport, max_attempts=3)

    processed = worker.run_once()

    assert processed == 1
    assert transport.sent == ["submission:5:created"]
    message = repository.all_messages()[0]
    assert message.status == "sent"
    assert message.attempts == 1


def test_already_sent_message_is_not_delivered_again() -> None:
    repository = InMemoryOutboxRepository()
    repository.enqueue(
        topic="submission.created",
        idempotency_key=submission_created_key(5),
        payload={},
    )
    transport = CountingTransport()
    worker = OutboxWorker(repository, transport, max_attempts=3)

    worker.run_once()
    worker.run_once()

    assert len(transport.sent) == 1


def test_failing_transport_keeps_message_pending_and_counts_attempts() -> None:
    repository = InMemoryOutboxRepository()
    repository.enqueue(
        topic="submission.created",
        idempotency_key=submission_created_key(7),
        payload={},
    )
    transport = FailingTransport()
    worker = OutboxWorker(repository, transport, max_attempts=3)

    worker.run_once()

    message = repository.all_messages()[0]
    assert message.status == "pending"
    assert message.attempts == 1
    assert message.last_error is not None
    assert "ConnectionError" in message.last_error


def test_exhausted_attempts_move_message_to_dead_letter() -> None:
    repository = InMemoryOutboxRepository()
    repository.enqueue(
        topic="submission.created",
        idempotency_key=submission_created_key(9),
        payload={},
    )
    transport = FailingTransport()
    worker = OutboxWorker(repository, transport, max_attempts=2)

    worker.run_once()
    worker.run_once()
    worker.run_once()

    message = repository.all_messages()[0]
    assert message.status == "failed"
    assert message.attempts == 2
    assert transport.attempts == 2


@pytest.mark.parametrize("limit", [1, 5])
def test_claim_respects_limit(limit: int) -> None:
    repository = InMemoryOutboxRepository()
    for index in range(5):
        repository.enqueue(
            topic="submission.created",
            idempotency_key=submission_created_key(index),
            payload={},
        )

    claimed = repository.claim_pending(limit=limit)

    assert len(claimed) == limit
