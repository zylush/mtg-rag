from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.auth import AuthenticatedUser
from app.api.services import ResourceNotFoundError
from app.config import Settings
from app.db.models import ApplicationUser, Conversation, SourceVersion
from app.history.repository import SqlConversationService
from app.ingestion.activation import ActivationCandidate, ValidationMetrics
from app.ingestion.repository import PostgresVersionRepository
from app.usage.repository import PostgresUsageRepository


@pytest.fixture
async def session_factory():  # type: ignore[no-untyped-def]
    settings = Settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_required_extensions_are_installed(session_factory) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as session:
        extensions = set(
            (
                await session.execute(
                    text("SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pg_trgm')")
                )
            ).scalars()
        )

    assert extensions == {"vector", "pg_trgm"}


def _source(source_name: str, *, active: bool, status: str) -> SourceVersion:
    suffix = uuid.uuid4().hex
    return SourceVersion(
        source_name=source_name,
        source_type="rules",
        source_url=f"https://media.wizards.com/{suffix}.txt",
        effective_date=date(2026, 8, 1),
        fetched_at=datetime.now(UTC),
        sha256=suffix.ljust(64, "0"),
        parser_version="1",
        schema_version="1",
        raw_gcs_uri=f"gs://snapshots/{suffix}",
        status=status,
        is_active=active,
        activated_at=datetime.now(UTC) if active else None,
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_source_activation_and_rollback_switch_exactly_one_active_version(
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    source_name = f"rules-{uuid.uuid4().hex}"
    old = _source(source_name, active=True, status="active")
    candidate = _source(source_name, active=False, status="staged")
    async with session_factory.begin() as session:
        session.add_all([old, candidate])

    repository = PostgresVersionRepository(session_factory)
    await repository.activate_atomically(
        ActivationCandidate(
            source_name=source_name,
            version_id=str(candidate.id),
            metrics=ValidationMetrics(100, 90, 0, 0, 0),
        )
    )

    async with session_factory() as session:
        active = (
            await session.execute(
                select(SourceVersion).where(
                    SourceVersion.source_name == source_name, SourceVersion.is_active.is_(True)
                )
            )
        ).scalars().all()
    assert [version.id for version in active] == [candidate.id]

    rolled_back = await repository.rollback_atomically(source_name)
    assert rolled_back == str(old.id)
    async with session_factory() as session:
        active_after_rollback = (
            await session.execute(
                select(SourceVersion).where(
                    SourceVersion.source_name == source_name, SourceVersion.is_active.is_(True)
                )
            )
        ).scalar_one()
    assert active_after_rollback.id == old.id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_concurrent_successes_never_exceed_daily_limit(session_factory) -> None:  # type: ignore[no-untyped-def]
    user = ApplicationUser(firebase_uid=f"quota-{uuid.uuid4().hex}")
    async with session_factory.begin() as session:
        session.add(user)

    repository = PostgresUsageRepository(session_factory)
    results = await asyncio.gather(
        *(repository.consume_success(user.id, date(2026, 8, 12), limit=20) for _ in range(30))
    )

    assert sum(result is not None for result in results) == 20
    assert max(result for result in results if result is not None) == 20


@pytest.mark.asyncio
@pytest.mark.integration
async def test_concurrent_burst_attempts_admit_only_five_per_minute(session_factory) -> None:  # type: ignore[no-untyped-def]
    user = ApplicationUser(firebase_uid=f"burst-{uuid.uuid4().hex}")
    async with session_factory.begin() as session:
        session.add(user)

    repository = PostgresUsageRepository(session_factory)
    now = datetime.now(UTC)
    admitted = await asyncio.gather(
        *(repository.register_ask_attempt(user.id, now=now, limit=5) for _ in range(6))
    )

    assert admitted.count(True) == 5
    assert admitted.count(False) == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_conversation_queries_and_deletes_enforce_firebase_ownership(session_factory) -> None:  # type: ignore[no-untyped-def]
    owner_uid = f"owner-{uuid.uuid4().hex}"
    other_uid = f"other-{uuid.uuid4().hex}"
    owner = ApplicationUser(firebase_uid=owner_uid)
    other = ApplicationUser(firebase_uid=other_uid)
    conversation = Conversation(user=owner, title="Owned history")
    async with session_factory.begin() as session:
        session.add_all([owner, other, conversation])

    service = SqlConversationService(session_factory)
    detail = await service.get(
        user=AuthenticatedUser(firebase_uid=owner_uid, email=None),
        conversation_id=conversation.id,
    )
    assert detail.id == conversation.id

    with pytest.raises(ResourceNotFoundError):
        await service.get(
            user=AuthenticatedUser(firebase_uid=other_uid, email=None),
            conversation_id=conversation.id,
        )
    with pytest.raises(ResourceNotFoundError):
        await service.delete(
            user=AuthenticatedUser(firebase_uid=other_uid, email=None),
            conversation_id=conversation.id,
        )

    await service.delete(
        user=AuthenticatedUser(firebase_uid=owner_uid, email=None),
        conversation_id=conversation.id,
    )
