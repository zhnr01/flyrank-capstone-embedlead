import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

GUARDED_PATH_SUFFIX = "/submissions"
CONTENT_LENGTH_HEADER = b"content-length"
TOO_LARGE_STATUS = 413
BAD_REQUEST_STATUS = 400
TOO_LARGE_DETAIL = "Submission payload too large"
BAD_LENGTH_DETAIL = "Invalid Content-Length header"


def declared_content_length(scope: Scope) -> bytes | None:
    for name, value in scope.get("headers", ()):
        if name.lower() == CONTENT_LENGTH_HEADER:
            return bytes(value)
    return None


def is_guarded(scope: Scope) -> bool:
    return str(scope.get("method", "")) == "POST" and str(scope["path"]).endswith(
        GUARDED_PATH_SUFFIX
    )


def error_payload(detail: str) -> bytes:
    return json.dumps({"detail": detail}).encode()


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be at least 1")
        self.app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_guarded(scope):
            await self.app(scope, receive, send)
            return

        declared = declared_content_length(scope)
        if declared is not None:
            try:
                length = int(declared)
            except ValueError:
                await self._respond(send, BAD_REQUEST_STATUS, BAD_LENGTH_DETAIL)
                return
            if length > self._max_bytes:
                await self._respond(send, TOO_LARGE_STATUS, TOO_LARGE_DETAIL)
                return

        received = 0
        exceeded = False
        responded = False

        async def guarded_receive() -> Message:
            nonlocal received, exceeded
            if exceeded:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] != "http.request":
                return message
            received += len(message.get("body", b""))
            if received > self._max_bytes:
                exceeded = True
                return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal responded
            if exceeded:
                if not responded:
                    responded = True
                    await self._respond(send, TOO_LARGE_STATUS, TOO_LARGE_DETAIL)
                return
            await send(message)

        await self.app(scope, guarded_receive, guarded_send)

        if exceeded and not responded:
            await self._respond(send, TOO_LARGE_STATUS, TOO_LARGE_DETAIL)

    async def _respond(self, send: Send, status_code: int, detail: str) -> None:
        body = error_payload(detail)
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
