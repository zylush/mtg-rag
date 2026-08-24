from __future__ import annotations

import asyncio
from typing import Protocol

from app.ask.service import RetrievalBundle
from app.generation.openai_adapter import RetrievedPassage
from app.retrieval.query import normalize_question
from app.retrieval.service import PreparedRetrieval


class EmbeddingProvider(Protocol):
    async def embed(self, text: str) -> list[float]: ...


class HybridProvider(Protocol):
    async def prepare_retrieval(self, question: str) -> PreparedRetrieval: ...

    async def retrieve_with_embedding(
        self,
        question: str,
        embedding: list[float],
        *,
        prepared: PreparedRetrieval | asyncio.Task[PreparedRetrieval] | None = None,
    ) -> list[RetrievedPassage]: ...


class AskRetrievalAdapter:
    def __init__(self, *, embedding: EmbeddingProvider, hybrid: HybridProvider) -> None:
        self._embedding = embedding
        self._hybrid = hybrid

    async def embed_question(self, question: str) -> list[float]:
        return await self._embedding.embed(normalize_question(question))

    async def prepare_retrieval(self, question: str) -> PreparedRetrieval:
        return await self._hybrid.prepare_retrieval(question)

    async def retrieve_with_embedding(
        self,
        question: str,
        embedding: list[float],
        *,
        prepared: PreparedRetrieval | asyncio.Task[PreparedRetrieval] | None = None,
    ) -> RetrievalBundle:
        passages = await self._hybrid.retrieve_with_embedding(
            question,
            embedding,
            prepared=prepared,
        )
        return RetrievalBundle(embedding=embedding, passages=passages)
