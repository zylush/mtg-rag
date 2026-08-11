from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.api.auth import AuthenticatedUser
from app.api.schemas import AskResponse, ConversationDetail, ConversationSummary


class ResourceNotFoundError(LookupError):
    pass


class QuotaExceededError(RuntimeError):
    pass


class BurstLimitExceededError(RuntimeError):
    pass


class TokenVerifier(Protocol):
    async def verify(self, token: str) -> AuthenticatedUser: ...


class AskUseCase(Protocol):
    async def ask(
        self, *, user: AuthenticatedUser, question: str, conversation_id: UUID | None
    ) -> AskResponse: ...


class ConversationUseCase(Protocol):
    async def list(self, *, user: AuthenticatedUser) -> list[ConversationSummary]: ...

    async def get(
        self, *, user: AuthenticatedUser, conversation_id: UUID
    ) -> ConversationDetail: ...

    async def delete(self, *, user: AuthenticatedUser, conversation_id: UUID) -> None: ...


class FeedbackUseCase(Protocol):
    async def submit(
        self,
        *,
        user: AuthenticatedUser,
        answer_message_id: UUID,
        rating: int,
        comment: str | None,
    ) -> None: ...


class AccountUseCase(Protocol):
    async def delete(self, *, user: AuthenticatedUser) -> None: ...


@dataclass(frozen=True)
class AppServices:
    auth: TokenVerifier
    ask: AskUseCase
    conversations: ConversationUseCase
    feedback: FeedbackUseCase
    accounts: AccountUseCase

