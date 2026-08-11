from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.auth import AuthenticatedUser, TokenVerificationError
from app.api.schemas import (
    AskRequest,
    AskResponse,
    ConversationDetail,
    ConversationSummary,
    FeedbackRequest,
)
from app.api.services import (
    AppServices,
    BurstLimitExceededError,
    QuotaExceededError,
    ResourceNotFoundError,
)
from app.config import Settings


def _services(request: Request) -> AppServices:
    return request.app.state.services


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


def create_app(*, settings: Settings, services: AppServices) -> FastAPI:
    app = FastAPI(
        title="MTG Rules Expert API",
        version="1.0.0",
        docs_url=None if settings.environment == "production" else "/docs",
        redoc_url=None,
        openapi_url=None if settings.environment == "production" else "/openapi.json",
    )
    app.state.services = services
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
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

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/ask", response_model=AskResponse)
    async def ask(payload: AskRequest, user: CurrentUser, service: Services) -> AskResponse:
        return await service.ask.ask(
            user=user,
            question=payload.question,
            conversation_id=payload.conversation_id,
        )

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

