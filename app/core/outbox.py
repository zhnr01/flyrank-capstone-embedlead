from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol


class OutboxStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


OutboxTopic = Literal["submission.created"]
SUBMISSION_CREATED_TOPIC: OutboxTopic = "submission.created"


def status_from_stored(value: str) -> OutboxStatus:
    try:
        return OutboxStatus(value)
    except ValueError:
        raise ValueError(f"unknown outbox status: {value!r}") from None


@dataclass(frozen=True)
class OutboxMessage:
    id: int
    topic: str
    idempotency_key: str
    payload: dict[str, object]
    status: OutboxStatus
    attempts: int
    last_error: str | None = None
    created_at: datetime | None = None


class NotificationTransport(Protocol):
    name: str

    def send(self, message: OutboxMessage) -> None: ...


def submission_created_key(submission_id: int) -> str:
    return f"submission:{submission_id}:created"
