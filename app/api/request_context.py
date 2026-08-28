import time
import uuid
from collections.abc import Iterable
from typing import Any

from starlette import status
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging_config import request_id_var
from app.core.metrics import observe_request

REQUEST_ID_HEADER = "x-request-id"
MAX_REQUEST_ID_LENGTH = 64
REQUEST_ID_ALLOWED_PUNCTUATION = "-_."
UNMATCHED_ROUTE = "unmatched"


def safe_request_id(raw: str | None) -> str:
    if raw is None:
        return str(uuid.uuid4())
    candidate = raw.strip()
    if not candidate or len(candidate) > MAX_REQUEST_ID_LENGTH:
        return str(uuid.uuid4())
    allowed = REQUEST_ID_ALLOWED_PUNCTUATION
    if not all(character.isalnum() or character in allowed for character in candidate):
        return str(uuid.uuid4())
    return candidate


def incoming_request_id(scope: Scope) -> str | None:
    wanted = REQUEST_ID_HEADER.encode()
    headers: Iterable[tuple[bytes, bytes]] = scope.get("headers", ())
    for name, value in headers:
        if name.lower() == wanted:
            return value.decode("latin-1")
    return None


def route_template(scope: Scope) -> str:
    route: Any = scope.get("route")
    path_format = getattr(route, "path_format", None)
    if not isinstance(path_format, str) or not path_format:
        return UNMATCHED_ROUTE

    path_params = scope.get("path_params") or {}
    concrete_suffix = path_format
    for name, value in path_params.items():
        concrete_suffix = concrete_suffix.replace("{" + name + "}", str(value))

    full_path = str(scope.get("path", ""))
    if concrete_suffix and full_path.endswith(concrete_suffix):
        mount_prefix = full_path[: -len(concrete_suffix)]
        return f"{mount_prefix}{path_format}"
    return path_format


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = safe_request_id(incoming_request_id(scope))
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER.encode(), request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            observe_request(
                method=str(scope["method"]),
                route=route_template(scope),
                status_code=status_code,
                duration_seconds=time.perf_counter() - started,
            )
            request_id_var.reset(token)
