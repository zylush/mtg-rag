from __future__ import annotations

import hashlib
import time
from collections import defaultdict, deque
from typing import Annotated, cast
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import APIError

from app.api.auth import AuthenticatedUser, TokenVerificationError
from app.api.middleware import RequestBoundaryMiddleware
from app.api.schemas import (
    AskRequest,
    AskResponse,
    ConversationDetail,
    ConversationSummary,
    FeedbackRequest,
    PublicAskRequest,
)
from app.api.services import (
    AppServices,
    BurstLimitExceededError,
    ConversationChangedError,
    IdempotencyConflictError,
    QuotaExceededError,
    RequestInProgressError,
    ResourceNotFoundError,
)
from app.cache.context import CorpusUnavailableError
from app.config import Settings
from app.generation.openai_adapter import ModelOutputError


def _services(request: Request) -> AppServices:
    return cast(AppServices, request.app.state.services)


async def _current_user(
    services: Annotated[AppServices, Depends(_services)],
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return await services.auth.verify(token)
    except (TokenVerificationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


CurrentUser = Annotated[AuthenticatedUser, Depends(_current_user)]
Services = Annotated[AppServices, Depends(_services)]


class _PublicAskRateLimiter:
    """Small per-process guard for the free public endpoint.

    Production infrastructure must still provide a distributed edge limit. This guard
    keeps a single instance from being consumed by an unbounded burst and provides a
    safe default for development and staging.
    """

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self._limit = limit
        self._window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        events = self._events[key]
        cutoff = current - self._window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= self._limit:
            return False
        events.append(current)
        return True


def _public_client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    candidate = forwarded.split(",", 1)[0].strip() if forwarded else ""
    if not candidate and request.client is not None:
        candidate = request.client.host
    if not candidate:
        candidate = "unknown"
    return hashlib.sha256(f"mtg-public:{candidate}".encode()).hexdigest()


def create_app(*, settings: Settings, services: AppServices) -> FastAPI:
    app = FastAPI(
        title="MTG Rules Expert API",
        version="1.0.0",
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.state.services = services
    public_ask_limiter = _PublicAskRateLimiter(settings.burst_limit_per_minute)
    app.add_middleware(
        RequestBoundaryMiddleware,
        timeout_seconds=settings.request_timeout_seconds,
        max_request_bytes=settings.max_request_body_bytes,
        max_response_bytes=settings.max_response_body_bytes,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )

    @app.exception_handler(ResourceNotFoundError)
    async def not_found_handler(request: Request, exc: ResourceNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "resource not found"})

    @app.exception_handler(QuotaExceededError)
    async def quota_handler(request: Request, exc: QuotaExceededError) -> JSONResponse:
        return JSONResponse(status_code=429, content={"detail": "daily answer limit reached"})

    @app.exception_handler(BurstLimitExceededError)
    async def burst_handler(request: Request, exc: BurstLimitExceededError) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"detail": "ask rate limit reached"},
            headers={"Retry-After": "60"},
        )

    @app.exception_handler(ConversationChangedError)
    async def conversation_changed_handler(
        request: Request, exc: ConversationChangedError
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": "conversation changed"})

    @app.exception_handler(IdempotencyConflictError)
    async def idempotency_conflict_handler(
        request: Request, exc: IdempotencyConflictError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "detail": "request ID was already used for a different request",
                "code": "IDEMPOTENCY_CONFLICT",
            },
        )

    @app.exception_handler(RequestInProgressError)
    async def request_in_progress_handler(
        request: Request, exc: RequestInProgressError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "detail": "the matching request is still in progress",
                "code": "REQUEST_IN_PROGRESS",
            },
            headers={"Retry-After": "1"},
        )

    @app.exception_handler(CorpusUnavailableError)
    async def corpus_unavailable_handler(
        request: Request, exc: CorpusUnavailableError
    ) -> JSONResponse:
        request.state.error_category = "corpus_unavailable"
        return JSONResponse(status_code=503, content={"detail": "rules corpus is unavailable"})

    @app.exception_handler(ModelOutputError)
    async def invalid_model_output_handler(
        request: Request, exc: ModelOutputError
    ) -> JSONResponse:
        request.state.error_category = "model_output"
        return JSONResponse(status_code=502, content={"detail": "model response was invalid"})

    @app.exception_handler(APIError)
    async def model_api_handler(request: Request, exc: APIError) -> JSONResponse:
        request.state.error_category = "model_upstream"
        return JSONResponse(
            status_code=503,
            content={"detail": "model service is unavailable"},
            headers={"Retry-After": "5"},
        )

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/ask", response_model=AskResponse)
    async def ask(payload: AskRequest, user: CurrentUser, service: Services) -> AskResponse:
        return await service.ask.ask(
            user=user,
            question=payload.question,
            conversation_id=payload.conversation_id,
            request_id=payload.request_id,
        )

    @app.post("/v1/public/ask", response_model=AskResponse)
    async def public_ask(
        payload: PublicAskRequest, request: Request, service: Services
    ) -> AskResponse:
        client_key = _public_client_key(request)
        if not public_ask_limiter.allow(client_key):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="public question rate limit reached",
                headers={"Retry-After": "60"},
            )
        return await service.ask.ask_public(question=payload.question, client_key=client_key)

    @app.get("/v1/conversations", response_model=list[ConversationSummary])
    async def list_conversations(user: CurrentUser, service: Services) -> list[ConversationSummary]:
        return await service.conversations.list(user=user)

    @app.get("/v1/conversations/{conversation_id}", response_model=ConversationDetail)
    async def get_conversation(
        conversation_id: UUID, user: CurrentUser, service: Services
    ) -> ConversationDetail:
        return await service.conversations.get(user=user, conversation_id=conversation_id)

    @app.delete("/v1/conversations/{conversation_id}", status_code=204)
    async def delete_conversation(
        conversation_id: UUID, user: CurrentUser, service: Services
    ) -> Response:
        await service.conversations.delete(user=user, conversation_id=conversation_id)
        return Response(status_code=204)

    @app.post("/v1/feedback", status_code=204)
    async def feedback(payload: FeedbackRequest, user: CurrentUser, service: Services) -> Response:
        await service.feedback.submit(
            user=user,
            answer_message_id=payload.answer_message_id,
            rating=payload.rating,
            comment=payload.comment,
        )
        return Response(status_code=204)

    @app.delete("/v1/account", status_code=204)
    async def delete_account(user: CurrentUser, service: Services) -> Response:
        await service.accounts.delete(user=user)
        return Response(status_code=204)

    return app
