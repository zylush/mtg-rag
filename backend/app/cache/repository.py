from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cache.policy import CacheContext, cache_fingerprint
from app.db.models import Passage, SemanticCacheEntry
from app.retrieval.query import normalize_question


@dataclass(frozen=True)
class CachedAnswer:
    entry_id: uuid.UUID
    response: dict[str, Any]
    citation_ids: tuple[uuid.UUID, ...]
    similarity: float


def _context_matches(entry: SemanticCacheEntry, context: CacheContext) -> bool:
    return (
        entry.corpus_versions == context.corpus_versions
        and entry.embedding_model == context.embedding_model
        and entry.embedding_dimensions == context.embedding_dimensions
        and entry.generation_model == context.generation_model
        and entry.prompt_version == context.prompt_version
        and entry.retrieval_version == context.retrieval_version
        and entry.language == context.language
        and tuple(entry.filters) == context.filters
    )


class PostgresCacheRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @staticmethod
    async def _citations_are_active(
        session: AsyncSession, citation_ids: tuple[uuid.UUID, ...]
    ) -> bool:
        if not citation_ids:
            return False
        count = await session.scalar(
            select(func.count(Passage.id)).where(
                Passage.id.in_(citation_ids), Passage.is_active.is_(True)
            )
        )
        return int(count or 0) == len(set(citation_ids))

    async def get_exact(
        self, *, key: str, context: CacheContext, now: datetime
    ) -> CachedAnswer | None:
        async with self._session_factory() as session:
            entry = await session.scalar(
                select(SemanticCacheEntry).where(
                    SemanticCacheEntry.exact_key == key,
                    SemanticCacheEntry.expires_at > now,
                )
            )
            if entry is None or not _context_matches(entry, context):
                return None
            citation_ids = tuple(entry.citation_ids)
            if not await self._citations_are_active(session, citation_ids):
                return None
            return CachedAnswer(
                entry_id=entry.id,
                response=entry.response,
                citation_ids=citation_ids,
                similarity=1.0,
            )

    async def get_semantic(
        self,
        *,
        question_embedding: list[float],
        context: CacheContext,
        threshold: float,
        now: datetime,
    ) -> CachedAnswer | None:
        if len(question_embedding) != context.embedding_dimensions:
            raise ValueError("question embedding dimension does not match cache context")
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("semantic cache threshold must be between 0 and 1")

        distance = SemanticCacheEntry.question_embedding.cosine_distance(question_embedding)
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(SemanticCacheEntry, distance.label("distance"))
                    .where(
                        SemanticCacheEntry.expires_at > now,
                        SemanticCacheEntry.corpus_versions == context.corpus_versions,
                        SemanticCacheEntry.embedding_model == context.embedding_model,
                        SemanticCacheEntry.embedding_dimensions == context.embedding_dimensions,
                        SemanticCacheEntry.generation_model == context.generation_model,
                        SemanticCacheEntry.prompt_version == context.prompt_version,
                        SemanticCacheEntry.retrieval_version == context.retrieval_version,
                        SemanticCacheEntry.language == context.language,
                        SemanticCacheEntry.filters == list(context.filters),
                        distance <= 1.0 - threshold,
                    )
                    .order_by(distance.asc(), SemanticCacheEntry.id)
                    .limit(5)
                )
            ).all()
            for entry, raw_distance in rows:
                citation_ids = tuple(entry.citation_ids)
                if await self._citations_are_active(session, citation_ids):
                    return CachedAnswer(
                        entry_id=entry.id,
                        response=entry.response,
                        citation_ids=citation_ids,
                        similarity=1.0 - float(raw_distance),
                    )
        return None

    async def put(
        self,
        *,
        question: str,
        question_embedding: list[float],
        response: dict[str, Any],
        citation_ids: tuple[uuid.UUID, ...],
        context: CacheContext,
        created_at: datetime,
        expires_at: datetime,
    ) -> str:
        ttl = expires_at - created_at
        if ttl <= timedelta(0) or ttl > timedelta(days=7):
            raise ValueError("semantic cache TTL must be positive and no longer than seven days")
        if len(question_embedding) != context.embedding_dimensions:
            raise ValueError("question embedding dimension does not match cache context")
        key = cache_fingerprint(question, context)
        values = {
            "id": uuid.uuid4(),
            "exact_key": key,
            "normalized_question": normalize_question(question),
            "question_embedding": question_embedding,
            "response": response,
            "citation_ids": list(citation_ids),
            "corpus_versions": context.corpus_versions,
            "embedding_model": context.embedding_model,
            "embedding_dimensions": context.embedding_dimensions,
            "generation_model": context.generation_model,
            "prompt_version": context.prompt_version,
            "retrieval_version": context.retrieval_version,
            "language": context.language,
            "filters": list(context.filters),
            "created_at": created_at,
            "updated_at": created_at,
            "expires_at": expires_at,
        }
        async with self._session_factory.begin() as session:
            if not await self._citations_are_active(session, citation_ids):
                raise ValueError("cache citations must all be active")
            statement = insert(SemanticCacheEntry).values(**values)
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[SemanticCacheEntry.exact_key],
                    set_={
                        **{key: value for key, value in values.items() if key != "id"},
                        "updated_at": created_at,
                    },
                )
            )
        return key

