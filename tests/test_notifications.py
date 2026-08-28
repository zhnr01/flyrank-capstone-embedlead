import httpx
import pytest

from app.core.outbox import OutboxMessage
from app.services.notifications import (
    LoggingNotificationTransport,
    WebhookNotificationTransport,
    sign_payload,
)

MESSAGE = OutboxMessage(
    id=1,
    topic="submission.created",
    idempotency_key="submission:1:created",
    payload={"submission_id": 1, "widget_id": 5},
    status="pending",
    attempts=0,
)


def test_logging_transport_never_raises() -> None:
    LoggingNotificationTransport().send(MESSAGE)


def test_webhook_requires_a_url() -> None:
    with pytest.raises(ValueError):
        WebhookNotificationTransport("", timeout_seconds=1.0)


def test_webhook_posts_topic_key_and_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        captured["url"] = url
        captured.update(kwargs)
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    transport = WebhookNotificationTransport(
        "https://hooks.example.com/lead",
        timeout_seconds=2.0,
    )

    transport.send(MESSAGE)

    assert captured["url"] == "https://hooks.example.com/lead"
    body = captured["json"]
    assert isinstance(body, dict)
    assert body["topic"] == "submission.created"
    assert body["idempotency_key"] == "submission:1:created"
    assert body["payload"] == {"submission_id": 1, "widget_id": 5}
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["X-Embedlead-Idempotency-Key"] == "submission:1:created"
    assert "X-Embedlead-Signature" not in headers


def test_webhook_signs_when_a_secret_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        captured.update(kwargs)
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    transport = WebhookNotificationTransport(
        "https://hooks.example.com/lead",
        timeout_seconds=2.0,
        secret="top-secret-value",
    )

    transport.send(MESSAGE)

    headers = captured["headers"]
    assert isinstance(headers, dict)
    signature = headers["X-Embedlead-Signature"]
    assert signature.startswith("sha256=")
    assert signature == sign_payload("top-secret-value", "submission:1:created")
    assert "top-secret-value" not in str(captured["json"])
    assert "top-secret-value" not in str(headers)


def test_webhook_raises_on_error_status_so_the_worker_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        return httpx.Response(500, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    transport = WebhookNotificationTransport(
        "https://hooks.example.com/lead",
        timeout_seconds=2.0,
    )

    with pytest.raises(httpx.HTTPStatusError):
        transport.send(MESSAGE)


def test_signature_is_stable_and_secret_dependent() -> None:
    first = sign_payload("secret-a", "submission:1:created")
    again = sign_payload("secret-a", "submission:1:created")
    other = sign_payload("secret-b", "submission:1:created")

    assert first == again
    assert first != other
