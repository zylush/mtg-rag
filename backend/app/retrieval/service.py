from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Protocol

from app.generation.openai_adapter import RetrievedPassage
from app.retrieval.analysis import QuestionAnalysis, analyze_question
from app.retrieval.fusion import RankedPassage, reciprocal_rank_fusion

_CURRENT_QUESTION = re.compile(
    r"^current question:\s*(.*?)(?:\n\s*\nprior user:|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_DEFINITION_REQUEST = re.compile(
    r"\b(?:rules?\s+definition|definition\s+of|define)\b"
    r"|\bwhat\s+(?:does|do)\b.{0,120}\bmean\b"
    r"|^what\s+is\s+(?:a\s+|an\s+|the\s+)?[a-z][a-z' -]{1,80}[?.!]*$",
    re.IGNORECASE | re.DOTALL,
)
_CONTEXTUAL_ABILITY_REFERENCE = re.compile(
    r"\b(?:that|this|its|the)\s+abilit(?:y|ies)\b",
    re.IGNORECASE,
)
_PRE_PRIORITY_PROCEDURE = re.compile(
    r"\b(?:before|prior\s+to)\b.*\bpriority\b",
    re.IGNORECASE | re.DOTALL,
)


def _current_question(question: str) -> str:
    current_match = _CURRENT_QUESTION.match(question.strip())
    return current_match.group(1) if current_match else question


def _asks_for_rules_definition(question: str) -> bool:
    normalized = " ".join(_current_question(question).casefold().split())
    return _DEFINITION_REQUEST.search(normalized) is not None


def _asks_about_contextual_ability(question: str) -> bool:
    return _CONTEXTUAL_ABILITY_REFERENCE.search(_current_question(question)) is not None


def _protected_rule_limit(question: str) -> int:
    return 2 if _PRE_PRIORITY_PROCEDURE.search(_current_question(question)) else 1


@dataclass(frozen=True)
class RetrievalCandidate:
    passage: RetrievedPassage
    rank: int
    source: str
    exact: bool = False
    protected: bool = False


@dataclass(frozen=True)
class PreparedRetrieval:
    question: str
    exact: tuple[RetrievalCandidate, ...]
    lexical: tuple[RetrievalCandidate, ...]


class EmbeddingProvider(Protocol):
    async def embed(self, text: str) -> list[float]: ...


class RetrievalRepository(Protocol):
    async def exact(
        self,
        analysis: QuestionAnalysis,
        *,
        limit: int,
    ) -> Sequence[RetrievalCandidate]: ...

    async def lexical(self, question: str, *, limit: int) -> Sequence[RetrievalCandidate]: ...

    async def vector(
        self, embedding: list[float], *, limit: int
    ) -> Sequence[RetrievalCandidate]: ...


class HybridRetrievalService:
    def __init__(self, *, repository: RetrievalRepository, embedding: EmbeddingProvider) -> None:
        self._repository = repository
        self._embedding = embedding

    async def retrieve(self, question: str) -> list[RetrievedPassage]:
        analysis = analyze_question(question)
        embedding_task = asyncio.create_task(self._embedding.embed(analysis.normalized))
        prepared_task = asyncio.create_task(self.prepare_retrieval(question))
        try:
            query_embedding = await embedding_task
        except BaseException:
            embedding_task.cancel()
            prepared_task.cancel()
            await asyncio.gather(
                embedding_task,
                prepared_task,
                return_exceptions=True,
            )
            raise
        return await self.retrieve_with_embedding(
            question,
            query_embedding,
            prepared=prepared_task,
        )

    async def prepare_retrieval(self, question: str) -> PreparedRetrieval:
        analysis = analyze_question(question)
        exact_task = asyncio.create_task(self._repository.exact(analysis, limit=20))
        lexical_task = asyncio.create_task(self._repository.lexical(question, limit=20))
        try:
            exact_result, lexical_result = await asyncio.gather(
                exact_task,
                lexical_task,
            )
        except BaseException:
            exact_task.cancel()
            lexical_task.cancel()
            await asyncio.gather(
                exact_task,
                lexical_task,
                return_exceptions=True,
            )
            raise
        return PreparedRetrieval(
            question=question,
            exact=tuple(exact_result),
            lexical=tuple(lexical_result),
        )

    async def retrieve_with_embedding(
        self,
        question: str,
        query_embedding: list[float],
        *,
        prepared: PreparedRetrieval | asyncio.Task[PreparedRetrieval] | None = None,
    ) -> list[RetrievedPassage]:
        if not isinstance(prepared, PreparedRetrieval):
            prepared_task = (
                prepared
                if prepared is not None
                else asyncio.create_task(self.prepare_retrieval(question))
            )
            vector_task = asyncio.create_task(
                self._repository.vector(query_embedding, limit=20)
            )
            try:
                resolved_prepared, vector_result = await asyncio.gather(
                    prepared_task,
                    vector_task,
                )
            except BaseException:
                prepared_task.cancel()
                vector_task.cancel()
                await asyncio.gather(
                    prepared_task,
                    vector_task,
                    return_exceptions=True,
                )
                raise
        else:
            if prepared.question != question:
                raise ValueError("prepared retrieval question does not match")
            resolved_prepared = prepared
            vector_result = await self._repository.vector(query_embedding, limit=20)
        if resolved_prepared.question != question:
            raise ValueError("prepared retrieval question does not match")
        exact = list(resolved_prepared.exact)
        lexical = list(resolved_prepared.lexical)
        vector = list(vector_result)

        fused = reciprocal_rank_fusion(
            [
                RankedPassage(
                    candidate.passage.passage_id,
                    rank=candidate.rank,
                    source=candidate.source,
                    exact=candidate.exact,
                    protected=candidate.protected,
                )
                for candidate in lexical
            ],
            [
                RankedPassage(
                    candidate.passage.passage_id,
                    rank=candidate.rank,
                    source=candidate.source,
                    exact=candidate.exact,
                    protected=candidate.protected,
                )
                for candidate in vector
            ],
            exact=[
                RankedPassage(
                    candidate.passage.passage_id,
                    rank=candidate.rank,
                    source=candidate.source,
                    exact=candidate.exact,
                    protected=candidate.protected,
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
        explicit_rule_ids = {
            item.passage_id
            for item in fused
            if candidates[item.passage_id].document_type == "rule" and "exact" in item.sources
        }
        primary_exact_card_id = next(
            (
                item.passage_id
                for item in fused
                if item.exact
                and candidates[item.passage_id].document_type == "card"
                and "exact" in item.sources
            ),
            None,
        )
        definition_glossary_id = (
            next(
                (
                    item.passage_id
                    for item in fused
                    if item.exact
                    and candidates[item.passage_id].document_type == "glossary"
                    and "glossary" in item.sources
                ),
                None,
            )
            if _asks_for_rules_definition(question)
            else None
        )
        required_ids = set(explicit_rule_ids)
        if primary_exact_card_id is not None:
            required_ids.add(primary_exact_card_id)
        if definition_glossary_id is not None:
            required_ids.add(definition_glossary_id)
        if primary_exact_card_id is not None and _asks_about_contextual_ability(question):
            linked_rule_id = next(
                (
                    item.passage_id
                    for item in fused
                    if item.exact
                    and candidates[item.passage_id].document_type == "rule"
                    and {"linked_rule", "linked_section"}.intersection(item.sources)
                ),
                None,
            )
            if linked_rule_id is not None:
                required_ids.add(linked_rule_id)
        if not required_ids:
            protected_rule_ids = [
                item.passage_id
                for item in fused
                if item.protected and candidates[item.passage_id].document_type == "rule"
            ][: _protected_rule_limit(question)]
            required_ids.update(protected_rule_ids)
        if not required_ids:
            corroborated_official_id = next(
                (
                    item.passage_id
                    for item in fused
                    if candidates[item.passage_id].document_type in {"rule", "glossary"}
                    and len(item.sources) >= 2
                ),
                None,
            )
            if corroborated_official_id is not None:
                required_ids.add(corroborated_official_id)
        return [
            replace(
                candidates[item.passage_id],
                citation_required=item.passage_id in required_ids,
            )
            for item in fused
        ]
