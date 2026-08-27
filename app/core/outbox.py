from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

OutboxStatus = Literal["pending", "sent", "failed"]


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
