from __future__ import annotations

import asyncio
import logging
from uuid import UUID

import httpx
import pytest

from app.api.app import create_app
from app.api.auth import AuthenticatedUser
from app.api.schemas import AskResponse
from app.api.services import AppServices
from app.cache.context import CorpusUnavailableError
from app.config import Settings
from app.generation.openai_adapter import ModelOutputError


class Auth:
    async def verify(self, token: str) -> AuthenticatedUser:
        return AuthenticatedUser(firebase_uid="firebase-user", email=None)


class Ask:
    def __init__(self, *, delay: float = 0, error: Exception | None = None) -> None:
        self.delay = delay
        self.error = error
        self.calls = 0

    async def ask(self, **kwargs: object) -> AskResponse:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return AskResponse(
            conversation_id=UUID("00000000-0000-0000-0000-000000000001"),
            message_id=UUID("00000000-0000-0000-0000-000000000002"),
            answer="A grounded answer.",
            citations=[],
            assumptions=[],
            confidence="high",
            needs_clarification=False,
            quota_remaining=19,
            cache_status="miss",
        )


class UnusedService:
    async def list(self, **kwargs: object) -> list[object]:
        return []

    async def get(self, **kwargs: object) -> None:
        return None

    async def delete(self, **kwargs: object) -> None:
        return None

    async def submit(self, **kwargs: object) -> None:
        return None


def _app(ask: Ask, **overrides: object):  # type: ignore[no-untyped-def]
    settings = Settings(
        database_url="postgresql+asyncpg://mtg:mtg@localhost:5432/mtg",
        frontend_origin="https://rules.example.com",
        **overrides,
    )
    unused = UnusedService()
    return create_app(
        settings=settings,
        services=AppServices(
            auth=Auth(),
            ask=ask,
            conversations=unused,
            feedback=unused,
            accounts=unused,
        ),
    )


def test_prod_alias_disables_api_schema_routes() -> None:
    app = _app(
        Ask(),
        environment="prod",
        openai_api_key="test-placeholder",
        gcp_project_id="mtg-production",
        gcs_snapshot_bucket="mtg-production-snapshots",
    )

    assert app.docs_url is None
    assert app.openapi_url is None


@pytest.mark.asyncio
async def test_request_metrics_use_bounded_correlation_id_without_logging_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_content = "private-question-content-must-not-appear"
    app = _app(Ask())
    caplog.set_level(logging.INFO, logger="app.api.middleware")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://api.example.com",
    ) as client:
        response = await client.post(
            "/v1/ask",
            headers={
                "Authorization": "Bearer token",
                "X-Request-ID": "web-123",
            },
            json={"question": private_content},
        )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "web-123"
    record = next(item for item in caplog.records if item.message == "http_request_completed")
    assert record.request_id == "web-123"  # type: ignore[attr-defined]
    assert record.method == "POST"  # type: ignore[attr-defined]
    assert record.path == "/v1/ask"  # type: ignore[attr-defined]
    assert record.status_code == 200  # type: ignore[attr-defined]
    assert record.response_bytes > 0  # type: ignore[attr-defined]
    assert private_content not in caplog.text


@pytest.mark.asyncio
async def test_invalid_correlation_id_is_replaced() -> None:
    app = _app(Ask())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://api.example.com",
    ) as client:
        response = await client.get("/healthz", headers={"X-Request-ID": "x" * 100})

    assert response.status_code == 200
    assert response.headers["x-request-id"] != "x" * 100
    assert len(response.headers["x-request-id"]) == 36


@pytest.mark.asyncio
async def test_request_body_limit_rejects_before_endpoint_execution() -> None:
    ask = Ask()
    app = _app(ask, max_request_body_bytes=64)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://api.example.com",
    ) as client:
        response = await client.post(
            "/v1/ask",
            headers={"Authorization": "Bearer token"},
            json={"question": "x" * 100},
        )

    assert response.status_code == 413
    assert response.json() == {"detail": "request body too large"}
    assert ask.calls == 0


@pytest.mark.asyncio
async def test_response_body_limit_replaces_oversized_payload() -> None:
    app = _app(Ask(), max_response_body_bytes=128)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://api.example.com",
    ) as client:
        response = await client.post(
            "/v1/ask",
            headers={"Authorization": "Bearer token"},
            json={"question": "What is flying?"},
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "response body exceeds configured limit"}


@pytest.mark.asyncio
async def test_request_timeout_returns_bounded_gateway_error() -> None:
    app = _app(Ask(delay=0.05), request_timeout_seconds=0.001)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://api.example.com",
    ) as client:
        response = await client.post(
            "/v1/ask",
            headers={"Authorization": "Bearer token"},
            json={"question": "What is flying?"},
        )

    assert response.status_code == 504
    assert response.json() == {"detail": "request timed out"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    [
        (CorpusUnavailableError("missing corpus"), 503, "rules corpus is unavailable"),
        (ModelOutputError("bad model output"), 502, "model response was invalid"),
        (RuntimeError("private database failure"), 500, "internal server error"),
    ],
)
async def test_known_upstream_failures_return_content_free_error_categories(
    error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    app = _app(Ask(error=error))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="https://api.example.com",
    ) as client:
        response = await client.post(
            "/v1/ask",
            headers={"Authorization": "Bearer token"},
            json={"question": "private question"},
        )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert str(error) not in response.text
