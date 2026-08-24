from dataclasses import dataclass

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.accounts.service import AccountDeletionService
from app.api.auth import AuthenticatedUser
from app.api.services import AppServices
from app.ask.context import PostgresConversationContextLoader
from app.ask.service import AskApplicationService
from app.config import Settings
from app.feedback.service import SqlFeedbackService
from app.history.repository import SqlConversationService
from app.runtime import build_services


@dataclass
class FakeAuth:
    async def verify(self, token: str) -> AuthenticatedUser:
        return AuthenticatedUser(firebase_uid="uid", email=None)


class FakeOpenAI:
    pass


def test_runtime_wires_all_public_use_cases_without_creating_extra_api_capabilities() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://mtg:mtg@localhost:5432/mtg",
        frontend_origin="http://localhost:5173",
    )
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    services = build_services(
        settings=settings,
        session_factory=factory,
        openai_client=FakeOpenAI(),  # type: ignore[arg-type]
        auth=FakeAuth(),
        delete_firebase_user=lambda uid: None,
    )

    assert isinstance(services, AppServices)
    assert isinstance(services.ask, AskApplicationService)
    assert services.ask._conversation_contexts is None
    assert isinstance(services.conversations, SqlConversationService)
    assert isinstance(services.feedback, SqlFeedbackService)
    assert isinstance(services.accounts, AccountDeletionService)


def test_runtime_wires_context_loader_only_when_rollout_flag_is_enabled() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://mtg:mtg@localhost:5432/mtg",
        frontend_origin="http://localhost:5173",
        conversation_context_enabled=True,
    )
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    services = build_services(
        settings=settings,
        session_factory=factory,
        openai_client=FakeOpenAI(),  # type: ignore[arg-type]
        auth=FakeAuth(),
        delete_firebase_user=lambda uid: None,
    )

    assert isinstance(
        services.ask._conversation_contexts,
        PostgresConversationContextLoader,
    )
