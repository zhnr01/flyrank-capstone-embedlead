import hashlib
import hmac
import logging

import httpx

from app.core.config import settings
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


class WebhookNotificationTransport:
    name = "webhook"

    def __init__(self, url: str, *, timeout_seconds: float, secret: str = "") -> None:
        if not url:
            raise ValueError("webhook url is required")
        self._url = url
        self._timeout = timeout_seconds
        self._secret = secret

    def send(self, message: OutboxMessage) -> None:
        headers = {
            "Content-Type": "application/json",
            "X-Embedlead-Topic": message.topic,
            "X-Embedlead-Idempotency-Key": message.idempotency_key,
        }
        if self._secret:
            headers["X-Embedlead-Signature"] = sign_payload(
                self._secret,
                message.idempotency_key,
            )
        response = httpx.post(
            self._url,
            json={
                "topic": message.topic,
                "idempotency_key": message.idempotency_key,
                "payload": message.payload,
            },
            headers=headers,
            timeout=self._timeout,
        )
        response.raise_for_status()
        logger.info(
            "webhook delivered topic=%s key=%s status=%s",
            message.topic,
            message.idempotency_key,
            response.status_code,
        )


def sign_payload(secret: str, body: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def build_transport() -> LoggingNotificationTransport | WebhookNotificationTransport:
    if settings.notification_webhook_url:
        return WebhookNotificationTransport(
            settings.notification_webhook_url,
            timeout_seconds=settings.notification_webhook_timeout_seconds,
            secret=settings.notification_webhook_secret,
        )
    return LoggingNotificationTransport()
