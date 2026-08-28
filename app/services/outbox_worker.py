import logging
from typing import Protocol

from app.core.metrics import increment
from app.core.outbox import NotificationTransport
from app.repositories.outbox import OutboxRepository

logger = logging.getLogger(__name__)


class FailureAlerter(Protocol):
    def dead_letter(
        self,
        *,
        idempotency_key: str,
        topic: str,
        attempts: int,
        error: str,
    ) -> None: ...


class LoggingFailureAlerter:
    def dead_letter(
        self,
        *,
        idempotency_key: str,
        topic: str,
        attempts: int,
        error: str,
    ) -> None:
        logger.error(
            "ALERT_outbox_dead_letter",
            extra={
                "fields": {
                    "topic": topic,
                    "idempotency_key": idempotency_key,
                    "attempts": attempts,
                    "error": error,
                }
            },
        )


class OutboxWorker:
    def __init__(
        self,
        repository: OutboxRepository,
        transport: NotificationTransport,
        *,
        max_attempts: int = 3,
        batch_size: int = 20,
        alerter: FailureAlerter | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._repository = repository
        self._transport = transport
        self._max_attempts = max_attempts
        self._batch_size = batch_size
        self._alerter = alerter or LoggingFailureAlerter()

    def run_once(self) -> int:
        messages = self._repository.claim_pending(limit=self._batch_size)
        processed = 0
        for message in messages:
            if message.attempts >= self._max_attempts:
                self._repository.mark_failed(
                    message.id,
                    attempts=message.attempts,
                    error=message.last_error or "attempts exhausted",
                    exhausted=True,
                )
                continue
            attempts = message.attempts + 1
            try:
                self._transport.send(message)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                exhausted = attempts >= self._max_attempts
                logger.warning(
                    "outbox_delivery_failed",
                    extra={
                        "fields": {
                            "idempotency_key": message.idempotency_key,
                            "attempts": attempts,
                            "exhausted": exhausted,
                        }
                    },
                )
                increment("outbox_delivery", "exhausted" if exhausted else "retry")
                self._repository.mark_failed(
                    message.id,
                    attempts=attempts,
                    error=error,
                    exhausted=exhausted,
                )
                if exhausted:
                    self._alerter.dead_letter(
                        idempotency_key=message.idempotency_key,
                        topic=message.topic,
                        attempts=attempts,
                        error=error,
                    )
                continue
            self._repository.mark_sent(message.id, attempts=attempts)
            increment("outbox_delivery", "sent")
            processed += 1
        return processed
