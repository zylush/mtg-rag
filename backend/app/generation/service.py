from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from app.generation.citations import (
    CitationValidationError,
    ResolvedAnswer,
    validate_citations,
)
from app.generation.openai_adapter import ModelResult, RetrievedPassage


class GenerationAdapter(Protocol):
    async def generate(
        self,
        *,
        question: str,
        passages: Sequence[RetrievedPassage],
        safety_identifier: str,
        repair_unknown_ids: tuple[str, ...] | None = None,
    ) -> ModelResult: ...


@dataclass(frozen=True)
class GenerationOutcome:
    answer: ResolvedAnswer
    request_id: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    model: str
    citation_repaired: bool


def _outcome(
    answer: ResolvedAnswer, result: ModelResult, *, citation_repaired: bool
) -> GenerationOutcome:
    return GenerationOutcome(
        answer=answer,
        request_id=result.request_id,
        latency_ms=result.latency_ms,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        model=result.model,
        citation_repaired=citation_repaired,
    )


class GroundedGenerationService:
    def __init__(self, adapter: GenerationAdapter) -> None:
        self._adapter = adapter

    async def answer(
        self,
        *,
        question: str,
        passages: list[RetrievedPassage],
        safety_identifier: str,
    ) -> GenerationOutcome:
        canonical = {
            passage.passage_id: {
                "label": passage.citation_label,
                "url": passage.canonical_url,
            }
            for passage in passages
        }
        first = await self._adapter.generate(
            question=question,
            passages=passages,
            safety_identifier=safety_identifier,
        )
        try:
            return _outcome(validate_citations(first.answer, canonical), first, citation_repaired=False)
        except CitationValidationError as first_error:
            repaired = await self._adapter.generate(
                question=question,
                passages=passages,
                safety_identifier=safety_identifier,
                repair_unknown_ids=first_error.unknown_ids,
            )
            try:
                return _outcome(
                    validate_citations(repaired.answer, canonical),
                    repaired,
                    citation_repaired=True,
                )
            except CitationValidationError:
                abstention = ResolvedAnswer(
                    answer=(
                        "I couldn't verify the generated citations against the active rules corpus, "
                        "so I can't provide a supported answer."
                    ),
                    citations=[],
                    assumptions=[],
                    confidence="low",
                    needs_clarification=False,
                )
                return _outcome(abstention, repaired, citation_repaired=True)

