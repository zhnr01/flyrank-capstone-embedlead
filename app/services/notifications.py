import logging

from app.core.outbox import OutboxMessage

logger = logging.getLogger(__name__)


class LoggingNotificationTransport:
    name = "logging"

    def send(self, message: OutboxMessage) -> None:
        logger.info(
            "notification delivered topic=%s key=%s payload_keys=%s",
            message.topic,
            message.idempotency_key,
            sorted(message.payload),
        )
