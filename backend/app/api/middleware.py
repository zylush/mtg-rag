from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from collections import deque

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class _RequestTooLarge(RuntimeError):
    pass


def _request_id(scope: Scope) -> str:
    headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
    for name, value in headers:
        if name.lower() == b"x-request-id":
            candidate = value.decode("ascii", errors="ignore")
            if _REQUEST_ID.fullmatch(candidate):
                return candidate
            break
    return str(uuid.uuid4())


async def _read_request(receive: Receive, maximum_bytes: int) -> list[Message]:
    messages: list[Message] = []
    received_bytes = 0
    while True:
        message = await receive()
        messages.append(message)
        if message["type"] == "http.disconnect":
            return messages
        if message["type"] != "http.request":
            continue
        received_bytes += len(message.get("body", b""))
        if received_bytes > maximum_bytes:
            raise _RequestTooLarge
        if not message.get("more_body", False):
            return messages


def _replay(messages: list[Message]) -> Receive:
    pending = deque(messages)

    async def receive() -> Message:
        if pending:
            return pending.popleft()
        return {"type": "http.disconnect"}

    return receive


def _with_request_id(
    headers: list[tuple[bytes, bytes]],
    request_id: str,
) -> list[tuple[bytes, bytes]]:
    filtered = [(name, value) for name, value in headers if name.lower() != b"x-request-id"]
    filtered.append((b"x-request-id", request_id.encode("ascii")))
    return filtered


async def _send_json(send: Send, status_code: int, detail: str, request_id: str) -> int:
    body = json.dumps({"detail": detail}, separators=(",", ":")).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
                (b"x-request-id", request_id.encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
    return len(body)


class RequestBoundaryMiddleware:
    """Bound HTTP work and emit content-free request telemetry."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        timeout_seconds: float,
        max_request_bytes: int,
        max_response_bytes: int,
    ) -> None:
        self._app = app
        self._timeout_seconds = timeout_seconds
        self._max_request_bytes = max_request_bytes
        self._max_response_bytes = max_response_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        started = time.perf_counter()
        request_id = _request_id(scope)
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        status_code = 500
        response_bytes = 0
        error_category = "unhandled"

        try:
            async with asyncio.timeout(self._timeout_seconds):
                request_messages = await _read_request(receive, self._max_request_bytes)
                response_start: Message | None = None
                response_body = bytearray()
                response_too_large = False

                async def capture(message: Message) -> None:
                    nonlocal response_start, response_too_large
                    if message["type"] == "http.response.start":
                        response_start = message
                        return
                    if message["type"] == "http.response.body":
                        body = message.get("body", b"")
                        if len(response_body) + len(body) > self._max_response_bytes:
                            response_too_large = True
                        elif not response_too_large:
                            response_body.extend(body)

                await self._app(scope, _replay(request_messages), capture)
                if response_too_large:
                    status_code = 500
                    error_category = "response_too_large"
                    response_bytes = await _send_json(
                        send,
                        status_code,
                        "response body exceeds configured limit",
                        request_id,
                    )
                elif response_start is None:
                    status_code = 500
                    error_category = "missing_response"
                    response_bytes = await _send_json(
                        send,
                        status_code,
                        "response was not produced",
                        request_id,
                    )
                else:
                    status_code = int(response_start["status"])
                    headers = _with_request_id(
                        list(response_start.get("headers", [])),
                        request_id,
                    )
                    await send({**response_start, "headers": headers})
                    await send({"type": "http.response.body", "body": bytes(response_body)})
                    response_bytes = len(response_body)
                    if "error_category" in state:
                        error_category = str(state["error_category"])
                    elif status_code >= 500:
                        error_category = "server_error"
                    elif status_code >= 400:
                        error_category = "client_error"
                    else:
                        error_category = "none"
        except _RequestTooLarge:
            status_code = 413
            error_category = "request_too_large"
            response_bytes = await _send_json(
                send,
                status_code,
                "request body too large",
                request_id,
            )
        except TimeoutError:
            status_code = 504
            error_category = "request_timeout"
            response_bytes = await _send_json(send, status_code, "request timed out", request_id)
        except Exception:
            status_code = 500
            error_category = "unhandled"
            response_bytes = await _send_json(
                send,
                status_code,
                "internal server error",
                request_id,
            )
        finally:
            logger.info(
                "http_request_completed",
                extra={
                    "request_id": request_id,
                    "method": scope.get("method", ""),
                    "path": scope.get("path", ""),
                    "status_code": status_code,
                    "duration_ms": max(0, round((time.perf_counter() - started) * 1000)),
                    "response_bytes": response_bytes,
                    "error_category": error_category,
                },
            )
