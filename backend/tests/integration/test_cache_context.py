from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.cache.context import CorpusUnavailableError, PostgresCacheContextProvider
from app.config import Settings
from app.db.models import SourceVersion


@pytest.fixture
async def session_factory():  # type: ignore[no-untyped-def]
    engine = create_async_engine(Settings().database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        await session.execute(
            delete(SourceVersion).where(SourceVersion.source_name.in_(["rules", "cards", "rulings"]))
        )
    yield factory
    await engine.dispose()


def _version(name: str) -> SourceVersion:
    suffix = uuid.uuid4().hex
    return SourceVersion(
        source_name=name,
        source_type=name,
        source_url=f"https://example.test/{suffix}",
        fetched_at=datetime.now(UTC),
        sha256=suffix.ljust(64, "0"),
        parser_version="1",
        schema_version="1",
        raw_gcs_uri=f"gs://snapshots/{suffix}",
        status="active",
        is_active=True,
        activated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_context_contains_all_active_corpus_and_configuration_versions(
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    versions = [_version(name) for name in ("rules", "cards", "rulings")]
    async with session_factory.begin() as session:
        session.add_all(versions)
    provider = PostgresCacheContextProvider(
        session_factory,
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
        generation_model="gpt-5.6-terra",
        prompt_version="p1",
        retrieval_version="rrf1",
    )

    context = await provider.current()

    assert context.corpus_versions == {version.source_name: str(version.id) for version in versions}
    assert context.filters == ("paper",)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_context_refuses_queries_until_every_required_corpus_is_active(
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    async with session_factory.begin() as session:
        session.add_all([_version("rules"), _version("cards")])
    provider = PostgresCacheContextProvider(
        session_factory,
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
        generation_model="gpt-5.6-terra",
        prompt_version="p1",
        retrieval_version="rrf1",
    )

    with pytest.raises(CorpusUnavailableError, match="rulings"):
        await provider.current()

