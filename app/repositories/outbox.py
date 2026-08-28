from itertools import count
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.outbox import (
    OutboxMessage,
    OutboxStatus,
    OutboxTopic,
    status_from_stored,
)
from app.models import OutboxMessageRecord


class OutboxRepository(Protocol):
    def enqueue(
        self,
        *,
        topic: OutboxTopic,
        idempotency_key: str,
        payload: dict[str, object],
    ) -> OutboxMessage | None: ...

    def claim_pending(self, *, limit: int) -> list[OutboxMessage]: ...

    def mark_sent(self, message_id: int, *, attempts: int) -> None: ...

    def mark_failed(
        self,
        message_id: int,
        *,
        attempts: int,
        error: str,
        exhausted: bool,
    ) -> None: ...


def to_message(record: OutboxMessageRecord) -> OutboxMessage:
    return OutboxMessage(
        id=record.id,
        topic=record.topic,
        idempotency_key=record.idempotency_key,
        payload=dict(record.payload),
        status=status_from_stored(record.status),
        attempts=record.attempts,
        last_error=record.last_error,
        created_at=record.created_at,
    )


class SqlAlchemyOutboxRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def enqueue(
        self,
        *,
        topic: OutboxTopic,
        idempotency_key: str,
        payload: dict[str, object],
    ) -> OutboxMessage | None:
        record = OutboxMessageRecord(
            topic=topic,
            idempotency_key=idempotency_key,
            payload=payload,
            status=OutboxStatus.PENDING,
            attempts=0,
        )
        savepoint = self._session.begin_nested()
        try:
            self._session.add(record)
            self._session.flush()
        except IntegrityError:
            savepoint.rollback()
            return None
        savepoint.commit()
        return to_message(record)

    def claim_pending(self, *, limit: int) -> list[OutboxMessage]:
        statement = (
            select(OutboxMessageRecord)
            .where(OutboxMessageRecord.status == OutboxStatus.PENDING)
            .order_by(OutboxMessageRecord.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        records = self._session.execute(statement).scalars().all()
        return [to_message(record) for record in records]

    def mark_sent(self, message_id: int, *, attempts: int) -> None:
        record = self._session.get(OutboxMessageRecord, message_id)
        if record is None:
            return
        record.status = OutboxStatus.SENT
        record.attempts = attempts
        record.last_error = None
        self._session.commit()

    def mark_failed(
        self,
        message_id: int,
        *,
        attempts: int,
        error: str,
        exhausted: bool,
    ) -> None:
        record = self._session.get(OutboxMessageRecord, message_id)
        if record is None:
            return
        record.status = (
            OutboxStatus.FAILED if exhausted else OutboxStatus.PENDING
        )
        record.attempts = attempts
        record.last_error = error
        self._session.commit()


class InMemoryOutboxRepository:
    def __init__(self) -> None:
        self._messages: dict[int, OutboxMessage] = {}
        self._keys: set[str] = set()
        self._ids = count(1)

    def enqueue(
        self,
        *,
        topic: OutboxTopic,
        idempotency_key: str,
        payload: dict[str, object],
    ) -> OutboxMessage | None:
        if idempotency_key in self._keys:
            return None
        self._keys.add(idempotency_key)
        message = OutboxMessage(
            id=next(self._ids),
            topic=topic,
            idempotency_key=idempotency_key,
            payload=payload,
            status=OutboxStatus.PENDING,
            attempts=0,
        )
        self._messages[message.id] = message
        return message

    def claim_pending(self, *, limit: int) -> list[OutboxMessage]:
        pending = [
            message
            for message in self._messages.values()
            if message.status == OutboxStatus.PENDING
        ]
        pending.sort(key=lambda message: message.id)
        return pending[:limit]

    def mark_sent(self, message_id: int, *, attempts: int) -> None:
        message = self._messages[message_id]
        self._messages[message_id] = OutboxMessage(
            id=message.id,
            topic=message.topic,
            idempotency_key=message.idempotency_key,
            payload=message.payload,
            status=OutboxStatus.SENT,
            attempts=attempts,
            last_error=None,
        )

    def mark_failed(
        self,
        message_id: int,
        *,
        attempts: int,
        error: str,
        exhausted: bool,
    ) -> None:
        message = self._messages[message_id]
        self._messages[message_id] = OutboxMessage(
            id=message.id,
            topic=message.topic,
            idempotency_key=message.idempotency_key,
            payload=message.payload,
            status=(
                OutboxStatus.FAILED if exhausted else OutboxStatus.PENDING
            ),
            attempts=attempts,
            last_error=error,
        )

    def all_messages(self) -> list[OutboxMessage]:
        return sorted(self._messages.values(), key=lambda m: m.id)
