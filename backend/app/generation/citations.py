from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AnswerBehavior = Literal["answer", "clarify", "abstain"]


class ModelCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passage_id: str = Field(min_length=1)
    claim: str = Field(min_length=1, max_length=320)


class GroundedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    citations: list[ModelCitation]
    assumptions: list[str]
    confidence: Literal["high", "medium", "low"]
    needs_clarification: bool
    behavior: AnswerBehavior


class ResolvedCitation(ModelCitation):
    label: str
    url: str


class ResolvedAnswer(BaseModel):
    answer: str
    citations: list[ResolvedCitation]
    assumptions: list[str]
    confidence: Literal["high", "medium", "low"]
    needs_clarification: bool
    behavior: AnswerBehavior


class CitationValidationError(ValueError):
    def __init__(self, unknown_ids: tuple[str, ...]) -> None:
        super().__init__(f"unknown citation IDs: {', '.join(unknown_ids)}")
        self.unknown_ids = unknown_ids


class CitationSupportError(ValueError):
    def __init__(self, unsupported_ids: tuple[str, ...]) -> None:
        super().__init__(
            "citation claims are not normalized exact source excerpts for IDs: "
            f"{', '.join(unsupported_ids)}"
        )
        self.unsupported_ids = unsupported_ids


def normalize_citation_excerpt(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


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

    claims_by_passage: dict[str, list[str]] = {}
    for citation in answer.citations:
        normalized_claim = normalize_citation_excerpt(citation.claim)
        claims = claims_by_passage.setdefault(citation.passage_id, [])
        if normalized_claim not in claims:
            claims.append(normalized_claim)

    excerpts_by_passage = {
        passage_id: " ".join(claims)
        for passage_id, claims in claims_by_passage.items()
    }
    unsupported_ids = tuple(
        passage_id
        for passage_id, excerpt in excerpts_by_passage.items()
        if not excerpt
        or len(excerpt) > 320
        or excerpt
        not in normalize_citation_excerpt(
            canonical_citations[passage_id].get("text", "")
        )
    )
    if unsupported_ids:
        raise CitationSupportError(unsupported_ids)

    resolved = [
        ResolvedCitation(
            passage_id=passage_id,
            claim=excerpt,
            label=canonical_citations[passage_id]["label"],
            url=canonical_citations[passage_id]["url"],
        )
        for passage_id, excerpt in excerpts_by_passage.items()
    ]
    return ResolvedAnswer(
        answer=answer.answer,
        citations=resolved,
        assumptions=answer.assumptions,
        confidence=answer.confidence,
        needs_clarification=answer.needs_clarification,
        behavior=answer.behavior,
    )
