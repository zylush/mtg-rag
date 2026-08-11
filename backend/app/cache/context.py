from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cache.policy import CacheContext
from app.db.models import SourceVersion


class CorpusUnavailableError(RuntimeError):
    pass


class PostgresCacheContextProvider:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        embedding_model: str,
        embedding_dimensions: int,
        generation_model: str,
        prompt_version: str,
        retrieval_version: str,
        required_sources: tuple[str, ...] = ("rules", "cards", "rulings"),
    ) -> None:
        self._session_factory = session_factory
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions
        self._generation_model = generation_model
        self._prompt_version = prompt_version
        self._retrieval_version = retrieval_version
        self._required_sources = required_sources

    async def current(self) -> CacheContext:
        async with self._session_factory() as session:
            versions = (
                await session.execute(
                    select(SourceVersion.source_name, SourceVersion.id).where(
                        SourceVersion.source_name.in_(self._required_sources),
                        SourceVersion.is_active.is_(True),
                    )
                )
            ).all()
        corpus_versions = {name: str(version_id) for name, version_id in versions}
        missing = sorted(set(self._required_sources) - set(corpus_versions))
        if missing:
            raise CorpusUnavailableError(
                f"required active corpus unavailable: {', '.join(missing)}"
            )
        return CacheContext(
            corpus_versions=corpus_versions,
            embedding_model=self._embedding_model,
            embedding_dimensions=self._embedding_dimensions,
            generation_model=self._generation_model,
            prompt_version=self._prompt_version,
            retrieval_version=self._retrieval_version,
            language="en",
            filters=("paper",),
        )

