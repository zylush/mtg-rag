from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.db.models import Passage, RuleSection, SourceVersion
from app.ingestion.corpus import parse_rules_corpus
from app.ingestion.pipeline import SourceDefinition
from app.ingestion.repository import PostgresIngestionRepository

RULES = """Magic: The Gathering Comprehensive Rules
These rules are effective as of July 25, 2026.

100. General
100.1. These rules apply to any Magic game.
100.2. Each player needs a deck.

Glossary
Owner
The player who started the game with a card in their deck.
"""


@pytest.fixture
async def session_factory():  # type: ignore[no-untyped-def]
    engine = create_async_engine(Settings().database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        await session.execute(
            delete(SourceVersion).where(SourceVersion.source_name.like("ingestion-test-%"))
        )
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_repository_stages_validates_and_atomically_activates_rules_corpus(
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    repository = PostgresIngestionRepository(session_factory)
    suffix = uuid.uuid4().hex
    source = SourceDefinition(
        name=f"ingestion-test-{suffix}",
        source_type="rules",
        url="https://media.wizards.com/rules.txt",
        parser_version="1",
        schema_version="1",
        minimum_record_count=3,
    )
    version_id = await repository.create_staged_version(
        source=source,
        source_url=source.url,
        fetched_at=datetime.now(UTC),
        sha256=suffix.ljust(64, "0"),
        raw_gcs_uri=f"gs://snapshots/{suffix}",
    )
    corpus = parse_rules_corpus(RULES.encode(), version_id)
    embeddings = {
        document.canonical_key: [0.1, *([0.0] * 1535)] for document in corpus.documents
    }

    await repository.stage_corpus(
        version_id=version_id,
        corpus=corpus,
        embeddings=embeddings,
    )
    metrics = await repository.validate_staged(version_id, minimum_record_count=3)
    await repository.activate(source.name, version_id)

    assert metrics.record_count == 3
    assert metrics.errors() == ()
    assert await repository.find_version_by_sha(source.name, suffix.ljust(64, "0")) == version_id
    async with session_factory() as session:
        version = await session.get(SourceVersion, uuid.UUID(version_id))
        rules = (
            await session.execute(
                select(RuleSection).where(
                    RuleSection.source_version_id == uuid.UUID(version_id)
                )
            )
        ).scalars().all()
        active_passages = await session.scalar(
            select(func.count(Passage.id)).where(
                Passage.source_version_id == uuid.UUID(version_id),
                Passage.is_active.is_(True),
            )
        )

    assert version is not None and version.is_active and version.status == "active"
    assert version.effective_date == date(2026, 7, 25)
    assert len(rules) == 2
    assert active_passages == 3


@pytest.mark.asyncio
@pytest.mark.integration
async def test_active_embedding_lookup_supports_copy_forward(session_factory) -> None:  # type: ignore[no-untyped-def]
    repository = PostgresIngestionRepository(session_factory)
    suffix = uuid.uuid4().hex
    source = SourceDefinition(
        name=f"ingestion-test-{suffix}",
        source_type="rules",
        url="https://media.wizards.com/rules.txt",
        parser_version="1",
        schema_version="1",
        minimum_record_count=3,
    )
    version_id = await repository.create_staged_version(
        source=source,
        source_url=source.url,
        fetched_at=datetime.now(UTC),
        sha256=suffix.ljust(64, "0"),
        raw_gcs_uri=f"gs://snapshots/{suffix}",
    )
    corpus = parse_rules_corpus(RULES.encode(), version_id)
    await repository.stage_corpus(
        version_id=version_id,
        corpus=corpus,
        embeddings={doc.canonical_key: [0.2, *([0.0] * 1535)] for doc in corpus.documents},
    )
    await repository.activate(source.name, version_id)

    cached = await repository.active_document_embeddings(source.name)

    assert cached["100.1"].content_hash == corpus.documents[0].content_hash
    assert cached["100.1"].embedding[0] == pytest.approx(0.2)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_repository_retries_a_failed_snapshot_without_duplicate_staged_records(
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    repository = PostgresIngestionRepository(session_factory)
    suffix = uuid.uuid4().hex
    sha256 = suffix.ljust(64, "0")
    source = SourceDefinition(
        name=f"ingestion-test-{suffix}",
        source_type="rules",
        url="https://media.wizards.com/rules.txt",
        parser_version="1",
        schema_version="1",
        minimum_record_count=3,
    )
    first_version_id = await repository.create_staged_version(
        source=source,
        source_url=source.url,
        fetched_at=datetime.now(UTC),
        sha256=sha256,
        raw_gcs_uri=f"gs://snapshots/{suffix}/first",
    )
    first_corpus = parse_rules_corpus(RULES.encode(), first_version_id)
    await repository.stage_corpus(
        version_id=first_version_id,
        corpus=first_corpus,
        embeddings={doc.canonical_key: [0.3, *([0.0] * 1535)] for doc in first_corpus.documents},
    )
    await repository.mark_failed(first_version_id, "validation")

    assert await repository.find_version_by_sha(source.name, sha256) is None

    retry_version_id = await repository.create_staged_version(
        source=source,
        source_url=source.url,
        fetched_at=datetime.now(UTC),
        sha256=sha256,
        raw_gcs_uri=f"gs://snapshots/{suffix}/retry",
    )
    retry_corpus = parse_rules_corpus(RULES.encode(), retry_version_id)
    await repository.stage_corpus(
        version_id=retry_version_id,
        corpus=retry_corpus,
        embeddings={doc.canonical_key: [0.4, *([0.0] * 1535)] for doc in retry_corpus.documents},
    )

    async with session_factory() as session:
        version_count = await session.scalar(
            select(func.count(SourceVersion.id)).where(SourceVersion.source_name == source.name)
        )
        retry_version = await session.get(SourceVersion, uuid.UUID(retry_version_id))
        passage_count = await session.scalar(
            select(func.count(Passage.id)).where(
                Passage.source_version_id == uuid.UUID(retry_version_id)
            )
        )

    assert retry_version_id == first_version_id
    assert version_count == 1
    assert retry_version is not None and retry_version.status == "staged"
    assert retry_version.raw_gcs_uri.endswith("/retry")
    assert passage_count == len(retry_corpus.documents)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_repository_restages_an_inactive_matching_snapshot(
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    repository = PostgresIngestionRepository(session_factory)
    suffix = uuid.uuid4().hex
    source = SourceDefinition(
        name=f"ingestion-test-{suffix}",
        source_type="rules",
        url="https://media.wizards.com/rules.txt",
        parser_version="1",
        schema_version="1",
        minimum_record_count=3,
    )
    first_sha = suffix.ljust(64, "0")
    second_sha = suffix.ljust(63, "1") + "2"

    first_version_id = await repository.create_staged_version(
        source=source,
        source_url=source.url,
        fetched_at=datetime.now(UTC),
        sha256=first_sha,
        raw_gcs_uri=f"gs://snapshots/{suffix}/first",
    )
    first_corpus = parse_rules_corpus(RULES.encode(), first_version_id)
    await repository.stage_corpus(
        version_id=first_version_id,
        corpus=first_corpus,
        embeddings={doc.canonical_key: [0.5, *([0.0] * 1535)] for doc in first_corpus.documents},
    )
    await repository.activate(source.name, first_version_id)

    second_version_id = await repository.create_staged_version(
        source=source,
        source_url=source.url,
        fetched_at=datetime.now(UTC),
        sha256=second_sha,
        raw_gcs_uri=f"gs://snapshots/{suffix}/second",
    )
    second_corpus = parse_rules_corpus(RULES.encode(), second_version_id)
    await repository.stage_corpus(
        version_id=second_version_id,
        corpus=second_corpus,
        embeddings={doc.canonical_key: [0.6, *([0.0] * 1535)] for doc in second_corpus.documents},
    )
    await repository.activate(source.name, second_version_id)

    assert await repository.find_version_by_sha(source.name, first_sha) is None

    retry_version_id = await repository.create_staged_version(
        source=source,
        source_url=source.url,
        fetched_at=datetime.now(UTC),
        sha256=first_sha,
        raw_gcs_uri=f"gs://snapshots/{suffix}/retry",
    )

    async with session_factory() as session:
        version_count = await session.scalar(
            select(func.count(SourceVersion.id)).where(SourceVersion.source_name == source.name)
        )
        retry_version = await session.get(SourceVersion, uuid.UUID(retry_version_id))
        passage_count = await session.scalar(
            select(func.count(Passage.id)).where(
                Passage.source_version_id == uuid.UUID(retry_version_id)
            )
        )

    assert retry_version_id == first_version_id
    assert version_count == 2
    assert retry_version is not None and retry_version.status == "staged"
    assert retry_version.raw_gcs_uri.endswith("/retry")
    assert passage_count == 0
