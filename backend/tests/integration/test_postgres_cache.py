from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import delete, func, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.cache.policy import CacheContext
from app.cache.repository import PostgresCacheRepository
from app.config import Settings
from app.db.models import Passage, SemanticCacheEntry, SourceVersion


@pytest.fixture
async def session_factory():  # type: ignore[no-untyped-def]
    engine = create_async_engine(Settings().database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        await session.execute(delete(SemanticCacheEntry))
        await session.execute(
            delete(SourceVersion).where(SourceVersion.source_name.like("cache-test-%"))
        )
    yield factory
    await engine.dispose()


def _context(*, prompt_version: str = "p1") -> CacheContext:
    return CacheContext(
        corpus_versions={"rules": "r1", "cards": "c1", "rulings": "u1"},
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
        generation_model="gpt-5.6-terra",
        prompt_version=prompt_version,
        retrieval_version="rrf1",
        language="en",
        filters=("paper",),
    )


def _embedding(first: float = 1.0) -> list[float]:
    return [first, 1.0 - first, *([0.0] * 1534)]


@pytest.fixture
async def cache_fixture(session_factory):  # type: ignore[no-untyped-def]
    suffix = uuid.uuid4().hex
    source = SourceVersion(
        source_name=f"cache-test-{suffix}",
        source_type="rules",
        source_url=f"https://media.wizards.com/{suffix}.txt",
        effective_date=date(2026, 8, 1),
        fetched_at=datetime.now(UTC),
        sha256=suffix.ljust(64, "0"),
        parser_version="1",
        schema_version="1",
        raw_gcs_uri=f"gs://snapshots/{suffix}",
        status="active",
        is_active=True,
        activated_at=datetime.now(UTC),
    )
    async with session_factory.begin() as session:
        session.add(source)
        await session.flush()
        passage = Passage(
            source_version_id=source.id,
            document_type="rule",
            canonical_key="702.9",
            text="Flying is an evasion ability.",
            passage_metadata={
                "citation_label": "Comprehensive Rules 702.9",
                "canonical_url": "https://magic.wizards.com/rules#702.9",
            },
            search_vector=func.to_tsvector("english", "Flying is an evasion ability."),
            embedding=_embedding(),
            is_active=True,
        )
        session.add(passage)
        await session.flush()
    return PostgresCacheRepository(session_factory), passage


@pytest.mark.asyncio
@pytest.mark.integration
async def test_exact_and_semantic_cache_require_matching_context_and_active_citations(
    cache_fixture, session_factory  # type: ignore[no-untyped-def]
) -> None:
    repository, passage = cache_fixture
    now = datetime.now(UTC)
    response = {"answer": "Flying restricts which creatures can block.", "citations": []}
    key = await repository.put(
        question="What is flying?",
        question_embedding=_embedding(),
        response=response,
        citation_ids=(passage.id,),
        context=_context(),
        created_at=now,
        expires_at=now + timedelta(days=7),
    )

    exact = await repository.get_exact(key=key, context=_context(), now=now)
    semantic = await repository.get_semantic(
        question_embedding=_embedding(),
        context=_context(),
        threshold=0.98,
        now=now,
    )
    mismatched = await repository.get_exact(
        key=key, context=_context(prompt_version="p2"), now=now
    )

    assert exact is not None and exact.response == response
    assert semantic is not None and semantic.response == response
    assert mismatched is None

    async with session_factory.begin() as session:
        await session.execute(
            update(Passage).where(Passage.id == passage.id).values(is_active=False)
        )
    assert await repository.get_exact(key=key, context=_context(), now=now) is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_semantic_cache_rejects_below_threshold_similarity(cache_fixture) -> None:  # type: ignore[no-untyped-def]
    repository, passage = cache_fixture
    now = datetime.now(UTC)
    await repository.put(
        question="What is flying?",
        question_embedding=_embedding(1.0),
        response={"answer": "Flying definition"},
        citation_ids=(passage.id,),
        context=_context(),
        created_at=now,
        expires_at=now + timedelta(days=1),
    )

    result = await repository.get_semantic(
        question_embedding=_embedding(0.0),
        context=_context(),
        threshold=0.98,
        now=now,
    )

    assert result is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cache_refuses_ttl_longer_than_seven_days(cache_fixture) -> None:  # type: ignore[no-untyped-def]
    repository, passage = cache_fixture
    now = datetime.now(UTC)

    with pytest.raises(ValueError, match="seven days"):
        await repository.put(
            question="What is flying?",
            question_embedding=_embedding(),
            response={"answer": "Flying definition"},
            citation_ids=(passage.id,),
            context=_context(),
            created_at=now,
            expires_at=now + timedelta(days=8),
        )

