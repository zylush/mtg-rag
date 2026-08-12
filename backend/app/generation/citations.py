from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passage_id: str = Field(min_length=1)
    claim: str = Field(min_length=1)


class GroundedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    citations: list[ModelCitation]
    assumptions: list[str]
    confidence: Literal["high", "medium", "low"]
    needs_clarification: bool


class ResolvedCitation(ModelCitation):
    label: str
    url: str


class ResolvedAnswer(BaseModel):
    answer: str
    citations: list[ResolvedCitation]
    assumptions: list[str]
    confidence: Literal["high", "medium", "low"]
    needs_clarification: bool


class CitationValidationError(ValueError):
    def __init__(self, unknown_ids: tuple[str, ...]) -> None:
        super().__init__(f"unknown citation IDs: {', '.join(unknown_ids)}")
        self.unknown_ids = unknown_ids


def validate_citations(
    answer: GroundedAnswer, canonical_citations: Mapping[str, Mapping[str, str]]
) -> ResolvedAnswer:
    unknown_ids = tuple(
        dict.fromkeys(
            citation.passage_id
            for citation in answer.citations
            if citation.passage_id not in canonical_citations
        )
    )
    if unknown_ids:
        raise CitationValidationError(unknown_ids)

    resolved = [
        ResolvedCitation(
            passage_id=citation.passage_id,
            claim=citation.claim,
            label=canonical_citations[citation.passage_id]["label"],
            url=canonical_citations[citation.passage_id]["url"],
        )
        for citation in answer.citations
    ]
    return ResolvedAnswer(
        answer=answer.answer,
        citations=resolved,
        assumptions=answer.assumptions,
        confidence=answer.confidence,
        needs_clarification=answer.needs_clarification,
    )

