import asyncio
import json

from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from app.api.body_limit import BodySizeLimitMiddleware
from app.core.config import settings
from app.main import app

client = TestClient(app)
SUBMISSION_PATH = "/api/v1/public/widgets/1/submissions"


class SpyApp:
    def __init__(self) -> None:
        self.body_bytes_seen = 0
        self.was_called = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.was_called = True
        if scope["type"] != "http":
            return
        while True:
            message = await receive()
            self.body_bytes_seen += len(message.get("body", b""))
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 202, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})


def http_scope(
    path: str = SUBMISSION_PATH,
    *,
    content_length: bytes | None = None,
) -> Scope:
    headers = [(b"host", b"testserver"), (b"content-type", b"application/json")]
    if content_length is None:
        headers.append((b"transfer-encoding", b"chunked"))
    else:
        headers.append((b"content-length", content_length))
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "scheme": "http",
        "headers": headers,
        "client": ("203.0.113.9", 5000),
        "server": ("testserver", 80),
    }


def run_middleware(
    middleware: BodySizeLimitMiddleware,
    scope: Scope,
    chunks: list[bytes],
) -> list[Message]:
    sent: list[Message] = []
    queue = list(chunks)

    async def receive() -> Message:
        if queue:
            body = queue.pop(0)
            return {"type": "http.request", "body": body, "more_body": bool(queue)}
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    asyncio.run(middleware(scope, receive, send))
    return sent


def status_of(sent: list[Message]) -> int:
    for message in sent:
        if message["type"] == "http.response.start":
            return int(message["status"])
    raise AssertionError("no http.response.start was sent")


def body_of(sent: list[Message]) -> bytes:
    chunks = [
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    ]
    return b"".join(bytes(chunk) for chunk in chunks)


def test_chunked_oversized_body_is_rejected_without_content_length() -> None:
    spy = SpyApp()
    sent = run_middleware(
        BodySizeLimitMiddleware(spy, max_bytes=1_000),
        http_scope(),
        [b"X" * 5_000],
    )

    assert status_of(sent) == 413
    assert b"too large" in body_of(sent).lower()


def test_streamed_body_is_cut_off_near_the_limit_not_after_the_whole_payload() -> None:
    spy = SpyApp()
    run_middleware(
        BodySizeLimitMiddleware(spy, max_bytes=1_000),
        http_scope(),
        [b"X" * 600] * 20,
    )

    assert spy.body_bytes_seen <= 1_600


def test_body_within_the_limit_passes_through_untouched() -> None:
    spy = SpyApp()
    payload = b"X" * 400
    sent = run_middleware(
        BodySizeLimitMiddleware(spy, max_bytes=1_000),
        http_scope(),
        [payload],
    )

    assert status_of(sent) == 202
    assert spy.body_bytes_seen == len(payload)


def test_declared_content_length_over_the_limit_never_reaches_the_app() -> None:
    spy = SpyApp()
    sent = run_middleware(
        BodySizeLimitMiddleware(spy, max_bytes=1_000),
        http_scope(content_length=b"999999"),
        [b"X" * 10],
    )

    assert status_of(sent) == 413
    assert spy.was_called is False


def test_unparsable_content_length_is_a_client_error() -> None:
    spy = SpyApp()
    sent = run_middleware(
        BodySizeLimitMiddleware(spy, max_bytes=1_000),
        http_scope(content_length=b"not-a-number"),
        [b"{}"],
    )

    assert status_of(sent) == 400
    assert spy.was_called is False


def test_limit_applies_only_to_the_guarded_path() -> None:
    spy = SpyApp()
    sent = run_middleware(
        BodySizeLimitMiddleware(spy, max_bytes=10),
        http_scope("/api/v1/widgets"),
        [b"X" * 500],
    )

    assert status_of(sent) == 202
    assert spy.body_bytes_seen == 500


def test_non_http_scope_is_passed_through() -> None:
    spy = SpyApp()
    run_middleware(
        BodySizeLimitMiddleware(spy, max_bytes=10),
        {"type": "lifespan"},
        [b""],
    )

    assert spy.was_called is True


def test_oversized_submission_is_rejected_by_the_running_app() -> None:
    oversized = json.dumps(
        {
            "email": "big@example.com",
            "name": "Big",
            "message": "X" * (settings.max_submission_bytes + 5_000),
        }
    )

    response = client.post(
        SUBMISSION_PATH,
        headers={
            "Origin": "http://localhost:5500",
            "Content-Type": "application/json",
        },
        content=oversized,
    )

    assert response.status_code == 413


def test_whitespace_padded_body_cannot_slip_past_field_validation() -> None:
    padded = (
        '{"name":"Padded","email":"padded@example.com","message":"ok"'
        + " " * (settings.max_submission_bytes * 3)
        + "}"
    )

    response = client.post(
        SUBMISSION_PATH,
        headers={
            "Origin": "http://localhost:5500",
            "Content-Type": "application/json",
        },
        content=padded,
    )

    assert response.status_code == 413
