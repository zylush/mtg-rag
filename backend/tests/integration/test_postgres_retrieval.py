from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import delete, func, or_
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.db.models import Card, CardAlias, Passage, SourceVersion
from app.retrieval.analysis import analyze_question
from app.retrieval.repository import PostgresRetrievalRepository


@pytest.fixture
async def session_factory():  # type: ignore[no-untyped-def]
    engine = create_async_engine(Settings().database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _embedding(first: float) -> list[float]:
    return [first, 1.0 - first, *([0.0] * 1534)]


def _version(source_name: str, *, active: bool) -> SourceVersion:
    suffix = uuid.uuid4().hex
    return SourceVersion(
        source_name=source_name,
        source_type="fixture",
        source_url=f"https://media.wizards.com/{suffix}.txt",
        effective_date=date(2026, 8, 1),
        fetched_at=datetime.now(UTC),
        sha256=suffix.ljust(64, "0"),
        parser_version="1",
        schema_version="1",
        raw_gcs_uri=f"gs://snapshots/{suffix}",
        status="active" if active else "inactive",
        is_active=active,
        activated_at=datetime.now(UTC) if active else None,
    )


def _passage(
    *,
    source_version_id: uuid.UUID,
    document_type: str,
    canonical_key: str,
    body: str,
    first_dimension: float,
    source: str | None = None,
    active: bool = True,
) -> Passage:
    metadata = {
        "citation_label": canonical_key,
        "canonical_url": f"https://example.test/{canonical_key}",
    }
    if source is not None:
        metadata["source"] = source
    return Passage(
        source_version_id=source_version_id,
        document_type=document_type,
        canonical_key=canonical_key,
        text=body,
        passage_metadata=metadata,
        search_vector=func.to_tsvector("english", body),
        embedding=_embedding(first_dimension),
        is_active=active,
    )


@pytest.fixture
async def retrieval_fixture(session_factory):  # type: ignore[no-untyped-def]
    active_version = _version(f"retrieval-{uuid.uuid4().hex}", active=True)
    inactive_version = _version(f"inactive-{uuid.uuid4().hex}", active=False)
    oracle_id = uuid.uuid4()
    printing_id = uuid.uuid4()
    card = Card(
        oracle_id=oracle_id,
        source_version_id=active_version.id,
        representative_printing_id=printing_id,
        name="Lightning Bolt",
        normalized_name="lightning bolt",
        layout="normal",
        document_text="Lightning Bolt deals 3 damage to any target.",
    )
    async with session_factory.begin() as session:
        await session.execute(
            delete(SourceVersion).where(
                or_(
                    SourceVersion.source_name.like("retrieval-%"),
                    SourceVersion.source_name.like("inactive-%"),
                )
            )
        )
        session.add_all([active_version, inactive_version])
        await session.flush()
        card.source_version_id = active_version.id
        session.add(card)
        await session.flush()
        session.add(CardAlias(card_id=card.id, alias="Lightning Bolt", normalized_alias="lightning bolt"))
        passages = [
            _passage(
                source_version_id=active_version.id,
                document_type="rule",
                canonical_key="608.2h",
                body="The spell resolves using the last known information.",
                first_dimension=0.2,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="card",
                canonical_key=str(oracle_id),
                body=card.document_text,
                first_dimension=0.4,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="ruling",
                canonical_key="ruling-wotc",
                body="A target spell is countered when all its targets are illegal.",
                first_dimension=0.5,
                source="wotc",
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="ruling",
                canonical_key="ruling-scryfall",
                body="A target spell is countered when all its targets are illegal.",
                first_dimension=0.5,
                source="scryfall",
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="glossary",
                canonical_key="flying",
                body="Flying is an evasion ability.",
                first_dimension=1.0,
            ),
            _passage(
                source_version_id=inactive_version.id,
                document_type="glossary",
                canonical_key="inactive-best",
                body="Inactive passage must never be returned.",
                first_dimension=1.0,
                active=False,
            ),
        ]
        session.add_all(passages)
    return PostgresRetrievalRepository(session_factory), passages


@pytest.mark.asyncio
@pytest.mark.integration
async def test_exact_lookup_finds_rule_and_unquoted_active_card_alias(retrieval_fixture) -> None:  # type: ignore[no-untyped-def]
    repository, passages = retrieval_fixture

    result = await repository.exact(
        analyze_question("How do Lightning Bolt and rule 608.2h interact?"), limit=20
    )

    assert {candidate.passage.passage_id for candidate in result} == {
        str(passages[0].id),
        str(passages[1].id),
    }
    assert all(candidate.exact for candidate in result)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_lexical_search_ranks_wotc_ruling_above_editorial_tie(retrieval_fixture) -> None:  # type: ignore[no-untyped-def]
    repository, passages = retrieval_fixture

    result = await repository.lexical("target spell countered", limit=20)

    ruling_ids = [
        candidate.passage.passage_id
        for candidate in result
        if candidate.passage.document_type == "ruling"
    ]
    assert ruling_ids[:2] == [str(passages[2].id), str(passages[3].id)]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_vector_search_uses_cosine_distance_and_excludes_inactive_passages(
    retrieval_fixture,  # type: ignore[no-untyped-def]
) -> None:
    repository, passages = retrieval_fixture

    result = await repository.vector(_embedding(1.0), limit=20)

    assert result[0].passage.passage_id == str(passages[4].id)
    assert str(passages[5].id) not in {candidate.passage.passage_id for candidate in result}
    assert len(result) <= 20
