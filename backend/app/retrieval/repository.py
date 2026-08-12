from __future__ import annotations

import re

from sqlalchemy import ColumnElement, Float, and_, case, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Card, CardAlias, Passage, SourceVersion
from app.generation.openai_adapter import RetrievedPassage
from app.retrieval.analysis import QuestionAnalysis
from app.retrieval.service import RetrievalCandidate


def _to_passage(passage: Passage) -> RetrievedPassage:
    return RetrievedPassage(
        passage_id=str(passage.id),
        document_type=passage.document_type,
        citation_label=str(
            passage.passage_metadata.get("citation_label", passage.canonical_key)
        ),
        canonical_url=str(passage.passage_metadata.get("canonical_url", "")),
        text=passage.text,
    )


def _whole_phrase_present(question: str, phrase: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", question) is not None


def _authority_bonus() -> ColumnElement[float]:
    return cast(
        case(
            (
                and_(
                    Passage.document_type == "ruling",
                    Passage.passage_metadata["source"].astext == "wotc",
                ),
                0.05,
            ),
            else_=0.0,
        ),
        Float,
    )


class PostgresRetrievalRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def exact(
        self, analysis: QuestionAnalysis, *, limit: int
    ) -> list[RetrievalCandidate]:
        if limit < 1:
            return []
        canonical_keys = set(analysis.rule_references)
        async with self._session_factory() as session:
            alias_rows = (
                await session.execute(
                    select(CardAlias.normalized_alias, Card.oracle_id)
                    .join(Card, Card.id == CardAlias.card_id)
                    .join(SourceVersion, SourceVersion.id == Card.source_version_id)
                    .where(
                        SourceVersion.is_active.is_(True),
                        func.strpos(literal(analysis.normalized), CardAlias.normalized_alias) > 0,
                    )
                    .order_by(func.length(CardAlias.normalized_alias).desc())
                    .limit(limit * 3)
                )
            ).all()
            for alias, oracle_id in alias_rows:
                if _whole_phrase_present(analysis.normalized, alias):
                    canonical_keys.add(str(oracle_id))

            if not canonical_keys:
                return []
            passages = (
                await session.execute(
                    select(Passage)
                    .where(
                        Passage.is_active.is_(True),
                        Passage.canonical_key.in_(canonical_keys),
                    )
                    .order_by(Passage.canonical_key, Passage.id)
                    .limit(limit)
                )
            ).scalars().all()
        return [
            RetrievalCandidate(
                passage=_to_passage(passage),
                rank=rank,
                source="exact",
                exact=True,
            )
            for rank, passage in enumerate(passages, start=1)
        ]

    async def lexical(self, question: str, *, limit: int) -> list[RetrievalCandidate]:
        if limit < 1:
            return []
        query = func.websearch_to_tsquery("english", question)
        relevance = func.ts_rank_cd(Passage.search_vector, query) + _authority_bonus()
        async with self._session_factory() as session:
            passages = (
                await session.execute(
                    select(Passage, relevance.label("relevance"))
                    .where(
                        Passage.is_active.is_(True),
                        Passage.search_vector.op("@@")(query),
                    )
                    .order_by(relevance.desc(), Passage.canonical_key, Passage.id)
                    .limit(limit)
                )
            ).all()
        return [
            RetrievalCandidate(
                passage=_to_passage(passage),
                rank=rank,
                source="lexical",
            )
            for rank, (passage, _) in enumerate(passages, start=1)
        ]

    async def vector(
        self, embedding: list[float], *, limit: int
    ) -> list[RetrievalCandidate]:
        if limit < 1:
            return []
        distance = Passage.embedding.cosine_distance(embedding)
        relevance = (1.0 - distance) + _authority_bonus()
        async with self._session_factory() as session:
            passages = (
                await session.execute(
                    select(Passage, relevance.label("relevance"))
                    .where(Passage.is_active.is_(True))
                    .order_by(relevance.desc(), Passage.canonical_key, Passage.id)
                    .limit(limit)
                )
            ).all()
        return [
            RetrievalCandidate(
                passage=_to_passage(passage),
                rank=rank,
                source="vector",
            )
            for rank, (passage, _) in enumerate(passages, start=1)
        ]
