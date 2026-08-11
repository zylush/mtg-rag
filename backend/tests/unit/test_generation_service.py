from dataclasses import dataclass, field

import pytest

from app.generation.citations import GroundedAnswer, ModelCitation
from app.generation.openai_adapter import ModelResult, RetrievedPassage
from app.generation.service import GroundedGenerationService


@dataclass
class FakeAdapter:
    answers: list[GroundedAnswer]
    repair_requests: list[tuple[str, ...] | None] = field(default_factory=list)

    async def generate(
        self,
        *,
        question: str,
        passages: list[RetrievedPassage],
        safety_identifier: str,
        repair_unknown_ids: tuple[str, ...] | None = None,
    ) -> ModelResult:
        self.repair_requests.append(repair_unknown_ids)
        return ModelResult(
            answer=self.answers.pop(0),
            request_id="resp_fake",
            latency_ms=5,
            input_tokens=10,
            output_tokens=10,
            model="gpt-5.6-terra",
        )


def _passage() -> RetrievedPassage:
    return RetrievedPassage(
        passage_id="known",
        document_type="rule",
        citation_label="Comprehensive Rules 704.5d",
        canonical_url="https://magic.wizards.com/rules#704.5d",
        text="A token in a zone other than the battlefield ceases to exist.",
    )


def _answer(passage_id: str) -> GroundedAnswer:
    return GroundedAnswer(
        answer="A token ceases to exist.",
        citations=[ModelCitation(passage_id=passage_id, claim="The token ceases to exist.")],
        assumptions=[],
        confidence="high",
        needs_clarification=False,
    )


@pytest.mark.asyncio
async def test_unknown_citation_gets_exactly_one_repair_attempt() -> None:
    adapter = FakeAdapter(answers=[_answer("invented"), _answer("known")])
    service = GroundedGenerationService(adapter)

    result = await service.answer(
        question="What happens to a token in a graveyard?",
        passages=[_passage()],
        safety_identifier="stable-private-id",
    )

    assert result.answer.citations[0].passage_id == "known"
    assert adapter.repair_requests == [None, ("invented",)]


@pytest.mark.asyncio
async def test_second_invalid_citation_returns_grounded_abstention() -> None:
    adapter = FakeAdapter(answers=[_answer("invented"), _answer("still-invented")])
    service = GroundedGenerationService(adapter)

    result = await service.answer(
        question="What happens?",
        passages=[_passage()],
        safety_identifier="stable-private-id",
    )

    assert result.answer.confidence == "low"
    assert result.answer.citations == []
    assert "couldn't verify" in result.answer.answer
    assert len(adapter.repair_requests) == 2

