import logging

from app.core.outbox import NotificationTransport
from app.repositories.outbox import OutboxRepository

logger = logging.getLogger(__name__)


class OutboxWorker:
    def __init__(
        self,
        repository: OutboxRepository,
        transport: NotificationTransport,
        *,
        max_attempts: int = 3,
        batch_size: int = 20,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._repository = repository
        self._transport = transport
        self._max_attempts = max_attempts
        self._batch_size = batch_size

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
                    "outbox delivery failed key=%s attempts=%s exhausted=%s",
                    message.idempotency_key,
                    attempts,
                    exhausted,
                )
                self._repository.mark_failed(
                    message.id,
                    attempts=attempts,
                    error=error,
                    exhausted=exhausted,
                )
                continue
            self._repository.mark_sent(message.id, attempts=attempts)
            processed += 1
        return processed
