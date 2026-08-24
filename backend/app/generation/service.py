from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.ask.context import ConversationContextMessage
from app.generation.citations import (
    CitationSupportError,
    CitationValidationError,
    GroundedAnswer,
    ModelCitation,
    ResolvedAnswer,
    normalize_citation_excerpt,
    validate_citations,
)
from app.generation.openai_adapter import ModelResult, RetrievedPassage
from app.retrieval.query import normalize_question

_UNRESOLVED_COMPARISON = re.compile(
    r"(?:\b(?:the|that|this)\s+(?:trigger|ability|effect|spell|object|one)\b.*"
    r"\b(?:first|before|after|next)\b|^which\s+(?:one\s+)?"
    r"(?:happens|resolves|triggers|applies)\s+first\b)"
)
_LOCAL_EVENT_LOOKUP = re.compile(r"\b(?:which|what|where|find|is there|are there)\b")
_LOCAL_EVENT_SUBJECT = re.compile(r"\b(?:store|shop|qualifier|tournament|event)\b")
_LOCAL_EVENT_TIME_OR_PLACE = re.compile(
    r"\b(?:near me|nearby|my area|tonight|today|this weekend|currently)\b"
)


class GenerationAdapter(Protocol):
    async def generate(
        self,
        *,
        question: str,
        passages: Sequence[RetrievedPassage],
        safety_identifier: str,
        conversation: tuple[ConversationContextMessage, ...] = (),
        repair_unknown_ids: tuple[str, ...] | None = None,
        repair_missing_ids: tuple[str, ...] | None = None,
        repair_unsupported_ids: tuple[str, ...] | None = None,
        repair_missing_citations: bool = False,
        repair_candidate: GroundedAnswer | None = None,
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
    initial_latency_ms: int | None = None
    initial_input_tokens: int | None = None
    initial_output_tokens: int | None = None
    repair_latency_ms: int | None = None
    repair_input_tokens: int | None = None
    repair_output_tokens: int | None = None


class RequiredCitationError(ValueError):
    def __init__(self, missing_ids: tuple[str, ...]) -> None:
        super().__init__(f"missing required citation IDs: {', '.join(missing_ids)}")
        self.missing_ids = missing_ids


class MissingCitationError(ValueError):
    def __init__(self) -> None:
        super().__init__("a substantive answer must include at least one citation")


def _bounded_exact_excerpt(text: str) -> str:
    normalized = normalize_citation_excerpt(text)
    if len(normalized) <= 320:
        return normalized
    boundary = normalized.rfind(" ", 0, 321)
    return normalized[: boundary if boundary > 0 else 320]


def _complete_missing_required_citations(
    answer: GroundedAnswer,
    canonical_citations: Mapping[str, Mapping[str, str]],
    missing_ids: tuple[str, ...],
) -> GroundedAnswer:
    completed = list(answer.citations)
    completed.extend(
        ModelCitation(
            passage_id=passage_id,
            claim=_bounded_exact_excerpt(
                canonical_citations[passage_id].get("text", "")
            ),
        )
        for passage_id in missing_ids
    )
    return answer.model_copy(update={"citations": completed})


def _supported_citation_subset(
    answer: GroundedAnswer,
    canonical_citations: Mapping[str, Mapping[str, str]],
) -> list[ModelCitation]:
    supported: list[ModelCitation] = []
    seen_ids: set[str] = set()
    for citation in answer.citations:
        canonical = canonical_citations.get(citation.passage_id)
        if canonical is None or citation.passage_id in seen_ids:
            continue
        claim = normalize_citation_excerpt(citation.claim)
        source_text = normalize_citation_excerpt(canonical.get("text", ""))
        if not claim or len(claim) > 320 or claim not in source_text:
            continue
        supported.append(
            ModelCitation(passage_id=citation.passage_id, claim=claim)
        )
        seen_ids.add(citation.passage_id)
    return supported


def _rebuild_first_candidate_citations(
    answer: GroundedAnswer,
    canonical_citations: Mapping[str, Mapping[str, str]],
    required_ids: tuple[str, ...],
) -> GroundedAnswer | None:
    if not answer.answer.strip():
        return None
    supported = _supported_citation_subset(answer, canonical_citations)
    if answer.behavior == "clarify":
        return answer.model_copy(update={"citations": supported})
    if answer.behavior != "answer" or not answer.citations or not required_ids:
        return None
    rebuilt = answer.model_copy(update={"citations": supported})
    return _complete_missing_required_citations(
        rebuilt,
        canonical_citations,
        _missing_required_citations(rebuilt, required_ids),
    )


def _deterministic_policy_answer(
    question: str,
    conversation: tuple[ConversationContextMessage, ...],
) -> ResolvedAnswer | None:
    normalized = normalize_question(question)
    if not conversation and _UNRESOLVED_COMPARISON.search(normalized):
        return ResolvedAnswer(
            answer=(
                "Which trigger or effect, and which other event or object, should I "
                "compare it with?"
            ),
            citations=[],
            assumptions=[],
            confidence="low",
            needs_clarification=True,
            behavior="clarify",
        )
    if (
        _LOCAL_EVENT_LOOKUP.search(normalized)
        and _LOCAL_EVENT_SUBJECT.search(normalized)
        and _LOCAL_EVENT_TIME_OR_PLACE.search(normalized)
    ):
        return ResolvedAnswer(
            answer=(
                "I can answer Magic rules questions, but the supplied rules corpus "
                "cannot determine current local store or tournament availability."
            ),
            citations=[],
            assumptions=[],
            confidence="low",
            needs_clarification=False,
            behavior="abstain",
        )
    return None


def _missing_required_citations(
    answer: GroundedAnswer,
    required_ids: tuple[str, ...],
) -> tuple[str, ...]:
    if answer.behavior != "answer":
        return ()
    cited_ids = {citation.passage_id for citation in answer.citations}
    return tuple(passage_id for passage_id in required_ids if passage_id not in cited_ids)


def _validate_model_answer(
    answer: GroundedAnswer,
    canonical_citations: Mapping[str, Mapping[str, str]],
    required_ids: tuple[str, ...],
) -> ResolvedAnswer:
    if not answer.answer.strip():
        return ResolvedAnswer(
            answer=(
                "I couldn't find enough supported rules evidence to answer this question."
            ),
            citations=[],
            assumptions=[],
            confidence="low",
            needs_clarification=False,
            behavior="abstain",
        )
    resolved = validate_citations(answer, canonical_citations)
    if answer.behavior == "answer" and not answer.citations:
        raise MissingCitationError
    missing_ids = _missing_required_citations(answer, required_ids)
    if missing_ids:
        raise RequiredCitationError(missing_ids)
    return resolved


def _outcome(
    answer: ResolvedAnswer,
    result: ModelResult,
    *,
    citation_repaired: bool,
    prior_result: ModelResult | None = None,
) -> GenerationOutcome:
    initial_result = prior_result or result
    repair_result = result if prior_result is not None else None
    prior_latency = prior_result.latency_ms if prior_result is not None else 0
    prior_input = prior_result.input_tokens if prior_result is not None else 0
    prior_output = prior_result.output_tokens if prior_result is not None else 0
    return GenerationOutcome(
        answer=answer,
        request_id=result.request_id,
        latency_ms=prior_latency + result.latency_ms,
        input_tokens=prior_input + result.input_tokens,
        output_tokens=prior_output + result.output_tokens,
        model=result.model,
        citation_repaired=citation_repaired,
        initial_latency_ms=initial_result.latency_ms,
        initial_input_tokens=initial_result.input_tokens,
        initial_output_tokens=initial_result.output_tokens,
        repair_latency_ms=repair_result.latency_ms if repair_result is not None else None,
        repair_input_tokens=(
            repair_result.input_tokens if repair_result is not None else None
        ),
        repair_output_tokens=(
            repair_result.output_tokens if repair_result is not None else None
        ),
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
        conversation: tuple[ConversationContextMessage, ...] = (),
    ) -> GenerationOutcome:
        canonical = {
            passage.passage_id: {
                "label": passage.citation_label,
                "url": passage.canonical_url,
                "text": passage.text,
            }
            for passage in passages
        }
        required_ids = tuple(
            passage.passage_id for passage in passages if passage.citation_required
        )
        first = await self._adapter.generate(
            question=question,
            passages=passages,
            safety_identifier=safety_identifier,
            conversation=conversation,
        )
        policy_answer = _deterministic_policy_answer(question, conversation)
        if policy_answer is not None:
            return _outcome(
                policy_answer,
                first,
                citation_repaired=False,
            )
        try:
            return _outcome(
                _validate_model_answer(first.answer, canonical, required_ids),
                first,
                citation_repaired=False,
            )
        except (
            CitationSupportError,
            CitationValidationError,
            MissingCitationError,
            RequiredCitationError,
        ) as first_error:
            unknown_ids = (
                first_error.unknown_ids
                if isinstance(first_error, CitationValidationError)
                else ()
            )
            unsupported_ids = (
                first_error.unsupported_ids
                if isinstance(first_error, CitationSupportError)
                else ()
            )
            missing_ids = _missing_required_citations(first.answer, required_ids)
            missing_citations = (
                first.answer.behavior == "answer" and not first.answer.citations
            )
            repaired = await self._adapter.generate(
                question=question,
                passages=passages,
                safety_identifier=safety_identifier,
                conversation=conversation,
                repair_unknown_ids=unknown_ids or None,
                repair_missing_ids=missing_ids or None,
                repair_unsupported_ids=unsupported_ids or None,
                repair_missing_citations=missing_citations,
                repair_candidate=first.answer,
            )
            try:
                return _outcome(
                    _validate_model_answer(repaired.answer, canonical, required_ids),
                    repaired,
                    citation_repaired=True,
                    prior_result=first,
                )
            except (
                CitationSupportError,
                CitationValidationError,
                MissingCitationError,
                RequiredCitationError,
            ):
                rebuilt = _rebuild_first_candidate_citations(
                    first.answer,
                    canonical,
                    required_ids,
                )
                if rebuilt is not None:
                    try:
                        resolved = _validate_model_answer(
                            rebuilt,
                            canonical,
                            required_ids,
                        )
                    except (
                        CitationSupportError,
                        CitationValidationError,
                        MissingCitationError,
                        RequiredCitationError,
                    ):
                        pass
                    else:
                        return _outcome(
                            resolved,
                            repaired,
                            citation_repaired=True,
                            prior_result=first,
                        )
                abstention = ResolvedAnswer(
                    answer=(
                        "I couldn't verify the generated citations against the "
                        "active rules corpus, "
                        "so I can't provide a supported answer."
                    ),
                    citations=[],
                    assumptions=[],
                    confidence="low",
                    needs_clarification=False,
                    behavior="abstain",
                )
                return _outcome(
                    abstention,
                    repaired,
                    citation_repaired=True,
                    prior_result=first,
                )
