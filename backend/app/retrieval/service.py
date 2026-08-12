from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.generation.openai_adapter import RetrievedPassage
from app.retrieval.analysis import QuestionAnalysis, analyze_question
from app.retrieval.fusion import RankedPassage, reciprocal_rank_fusion


@dataclass(frozen=True)
class RetrievalCandidate:
    passage: RetrievedPassage
    rank: int
    source: str
    exact: bool = False


class EmbeddingProvider(Protocol):
    async def embed(self, text: str) -> list[float]: ...


class RetrievalRepository(Protocol):
    async def exact(
        self, analysis: QuestionAnalysis, *, limit: int
    ) -> Sequence[RetrievalCandidate]: ...

    async def lexical(
        self, question: str, *, limit: int
    ) -> Sequence[RetrievalCandidate]: ...

    async def vector(
        self, embedding: list[float], *, limit: int
    ) -> Sequence[RetrievalCandidate]: ...


class HybridRetrievalService:
    def __init__(
        self, *, repository: RetrievalRepository, embedding: EmbeddingProvider
    ) -> None:
        self._repository = repository
        self._embedding = embedding

    async def retrieve(self, question: str) -> list[RetrievedPassage]:
        analysis = analyze_question(question)
        query_embedding = await self._embedding.embed(analysis.normalized)
        return await self.retrieve_with_embedding(question, query_embedding)

    async def retrieve_with_embedding(
        self, question: str, query_embedding: list[float]
    ) -> list[RetrievedPassage]:
        analysis = analyze_question(question)
        exact = list(await self._repository.exact(analysis, limit=20))
        lexical = list(await self._repository.lexical(analysis.normalized, limit=20))
        vector = list(await self._repository.vector(query_embedding, limit=20))

        fused = reciprocal_rank_fusion(
            [
                RankedPassage(
                    candidate.passage.passage_id,
                    rank=candidate.rank,
                    source=candidate.source,
                    exact=candidate.exact,
                )
                for candidate in lexical
            ],
            [
                RankedPassage(
                    candidate.passage.passage_id,
                    rank=candidate.rank,
                    source=candidate.source,
                    exact=candidate.exact,
                )
                for candidate in vector
            ],
            exact=[
                RankedPassage(
                    candidate.passage.passage_id,
                    rank=candidate.rank,
                    source="exact",
                    exact=True,
                )
                for candidate in exact
            ],
            limit=8,
            candidate_limit=20,
        )
        candidates = {
            candidate.passage.passage_id: candidate.passage
            for candidate in [*vector, *lexical, *exact]
        }
        return [candidates[item.passage_id] for item in fused]
