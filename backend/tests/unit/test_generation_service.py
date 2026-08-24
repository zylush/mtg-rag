from dataclasses import dataclass, field

import pytest

from app.ask.context import ConversationContextMessage
from app.generation.citations import GroundedAnswer, ModelCitation
from app.generation.openai_adapter import ModelResult, RetrievedPassage
from app.generation.service import GroundedGenerationService


@dataclass
class FakeAdapter:
    answers: list[GroundedAnswer]
    repair_requests: list[tuple[str, ...] | None] = field(default_factory=list)
    missing_repair_requests: list[tuple[str, ...] | None] = field(default_factory=list)
    unsupported_repair_requests: list[tuple[str, ...] | None] = field(
        default_factory=list
    )
    missing_citation_repair_requests: list[bool] = field(default_factory=list)
    conversation_requests: list[tuple[ConversationContextMessage, ...]] = field(
        default_factory=list
    )
    repair_candidates: list[GroundedAnswer | None] = field(default_factory=list)

    async def generate(
        self,
        *,
        question: str,
        passages: list[RetrievedPassage],
        conversation: tuple[ConversationContextMessage, ...],
        safety_identifier: str,
        repair_unknown_ids: tuple[str, ...] | None = None,
        repair_missing_ids: tuple[str, ...] | None = None,
        repair_unsupported_ids: tuple[str, ...] | None = None,
        repair_missing_citations: bool = False,
        repair_candidate: GroundedAnswer | None = None,
    ) -> ModelResult:
        self.repair_requests.append(repair_unknown_ids)
        self.missing_repair_requests.append(repair_missing_ids)
        self.unsupported_repair_requests.append(repair_unsupported_ids)
        self.missing_citation_repair_requests.append(repair_missing_citations)
        self.conversation_requests.append(conversation)
        self.repair_candidates.append(repair_candidate)
        return ModelResult(
            answer=self.answers.pop(0),
            request_id="resp_fake",
            latency_ms=5,
            input_tokens=10,
            output_tokens=10,
            model="gpt-5.6-luna",
        )


def _passage(
    *,
    passage_id: str = "known",
    citation_required: bool = False,
    text: str = "A token in a zone other than the battlefield ceases to exist.",
) -> RetrievedPassage:
    return RetrievedPassage(
        passage_id=passage_id,
        document_type="rule",
        citation_label="Comprehensive Rules 704.5d",
        canonical_url="https://magic.wizards.com/rules#704.5d",
        text=text,
        citation_required=citation_required,
    )


def _answer(
    passage_id: str,
    *,
    claim: str = "A token in a zone other than the battlefield ceases to exist.",
) -> GroundedAnswer:
    return GroundedAnswer(
        answer="A token ceases to exist.",
        citations=[ModelCitation(passage_id=passage_id, claim=claim)],
        assumptions=[],
        confidence="high",
        needs_clarification=False,
        behavior="answer",
    )


@pytest.mark.asyncio
async def test_blank_model_answer_returns_non_empty_grounded_abstention() -> None:
    adapter = FakeAdapter(
        answers=[
            GroundedAnswer(
                answer="   ",
                citations=[],
                assumptions=["The model omitted its user-facing answer."],
                confidence="low",
                needs_clarification=False,
                behavior="abstain",
            )
        ]
    )

    result = await GroundedGenerationService(adapter).answer(
        question="Can you answer this unsupported question?",
        passages=[_passage()],
        safety_identifier="stable-private-id",
    )

    assert result.answer.answer == (
        "I couldn't find enough supported rules evidence to answer this question."
    )
    assert result.answer.behavior == "abstain"
    assert result.answer.confidence == "low"
    assert result.answer.needs_clarification is False
    assert result.answer.citations == []
    assert result.answer.assumptions == []
    assert adapter.repair_requests == [None]
    assert result.initial_latency_ms == 5
    assert result.initial_input_tokens == 10
    assert result.initial_output_tokens == 10
    assert result.repair_latency_ms is None
    assert result.repair_input_tokens is None
    assert result.repair_output_tokens is None


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
    assert result.latency_ms == 10
    assert result.input_tokens == 20
    assert result.output_tokens == 20
    assert result.initial_latency_ms == 5
    assert result.initial_input_tokens == 10
    assert result.initial_output_tokens == 10
    assert result.repair_latency_ms == 5
    assert result.repair_input_tokens == 10
    assert result.repair_output_tokens == 10


@pytest.mark.asyncio
async def test_missing_required_citation_gets_exactly_one_repair_attempt() -> None:
    adapter = FakeAdapter(answers=[_answer("supporting"), _answer("governing")])
    service = GroundedGenerationService(adapter)

    result = await service.answer(
        question="What happens to a token in a graveyard?",
        passages=[
            _passage(passage_id="governing", citation_required=True),
            _passage(passage_id="supporting"),
        ],
        safety_identifier="stable-private-id",
    )

    assert result.answer.citations[0].passage_id == "governing"
    assert adapter.repair_requests == [None, None]
    assert adapter.missing_repair_requests == [None, ("governing",)]
    assert result.citation_repaired is True
    assert result.latency_ms == 10
    assert result.input_tokens == 20
    assert result.output_tokens == 20
    assert result.initial_latency_ms == 5
    assert result.initial_input_tokens == 10
    assert result.initial_output_tokens == 10
    assert result.repair_latency_ms == 5
    assert result.repair_input_tokens == 10
    assert result.repair_output_tokens == 10


@pytest.mark.asyncio
async def test_failed_repair_completes_a_prevalidated_missing_required_citation() -> None:
    first = _answer("supporting")
    adapter = FakeAdapter(
        answers=[
            first,
            _answer("governing", claim="This paraphrase is not an exact excerpt."),
        ]
    )

    result = await GroundedGenerationService(adapter).answer(
        question="What happens to a token in a graveyard?",
        passages=[
            _passage(passage_id="governing", citation_required=True),
            _passage(passage_id="supporting"),
        ],
        safety_identifier="stable-private-id",
    )

    assert result.answer.answer == first.answer
    assert result.answer.behavior == "answer"
    assert [citation.passage_id for citation in result.answer.citations] == [
        "supporting",
        "governing",
    ]
    assert result.answer.citations[1].claim == (
        "A token in a zone other than the battlefield ceases to exist."
    )
    assert result.citation_repaired is True
    assert result.initial_latency_ms == 5
    assert result.repair_latency_ms == 5


@pytest.mark.asyncio
async def test_required_citation_completion_uses_a_bounded_exact_excerpt() -> None:
    long_text = " ".join(f"word{index}" for index in range(100))
    first = _answer("supporting")
    adapter = FakeAdapter(
        answers=[first, _answer("governing", claim="not exact")]
    )

    result = await GroundedGenerationService(adapter).answer(
        question="Which long rule governs?",
        passages=[
            _passage(
                passage_id="governing",
                citation_required=True,
                text=long_text,
            ),
            _passage(passage_id="supporting"),
        ],
        safety_identifier="stable-private-id",
    )

    completed = result.answer.citations[1].claim
    assert 0 < len(completed) <= 320
    assert completed in long_text
    assert result.answer.behavior == "answer"


@pytest.mark.parametrize(
    "first",
    [
        _answer("invented"),
        _answer("governing", claim="This paraphrase is not an exact excerpt."),
    ],
    ids=["unknown-id", "unsupported-excerpt"],
)
@pytest.mark.asyncio
async def test_failed_repair_rebuilds_citations_from_required_canonical_passage(
    first: GroundedAnswer,
) -> None:
    adapter = FakeAdapter(
        answers=[
            first,
            _answer("governing", claim="The repair is still not an exact excerpt."),
        ]
    )

    result = await GroundedGenerationService(adapter).answer(
        question="What happens to a token in a graveyard?",
        passages=[_passage(passage_id="governing", citation_required=True)],
        safety_identifier="stable-private-id",
    )

    assert result.answer.answer == first.answer
    assert result.answer.behavior == "answer"
    assert [citation.passage_id for citation in result.answer.citations] == [
        "governing"
    ]
    assert result.answer.citations[0].claim == (
        "A token in a zone other than the battlefield ceases to exist."
    )
    assert result.citation_repaired is True


@pytest.mark.asyncio
async def test_failed_repair_does_not_recover_answer_that_never_cited_evidence() -> None:
    uncited = GroundedAnswer(
        answer="A token ceases to exist.",
        citations=[],
        assumptions=[],
        confidence="high",
        needs_clarification=False,
        behavior="answer",
    )
    adapter = FakeAdapter(
        answers=[
            uncited,
            _answer("governing", claim="The repair is still not an exact excerpt."),
        ]
    )

    result = await GroundedGenerationService(adapter).answer(
        question="What happens to a token in a graveyard?",
        passages=[_passage(passage_id="governing", citation_required=True)],
        safety_identifier="stable-private-id",
    )

    assert result.answer.behavior == "abstain"
    assert result.answer.citations == []


@pytest.mark.asyncio
async def test_failed_repair_preserves_clarification_without_invalid_citations() -> None:
    clarification = GroundedAnswer(
        answer="What does 'it' refer to?",
        citations=[ModelCitation(passage_id="invented", claim="Unsupported")],
        assumptions=[],
        confidence="low",
        needs_clarification=True,
        behavior="clarify",
    )
    adapter = FakeAdapter(
        answers=[
            clarification,
            _answer("still-invented"),
        ]
    )

    result = await GroundedGenerationService(adapter).answer(
        question="Can it be targeted?",
        passages=[_passage()],
        safety_identifier="stable-private-id",
    )

    assert result.answer.answer == clarification.answer
    assert result.answer.behavior == "clarify"
    assert result.answer.needs_clarification is True
    assert result.answer.citations == []


@pytest.mark.asyncio
async def test_unsupported_excerpt_gets_exactly_one_repair_attempt() -> None:
    first = _answer("known", claim="The token disappears.")
    adapter = FakeAdapter(
        answers=[
            first,
            _answer("known"),
        ]
    )

    result = await GroundedGenerationService(adapter).answer(
        question="What happens to a token in a graveyard?",
        passages=[_passage()],
        safety_identifier="stable-private-id",
    )

    assert result.answer.citations[0].claim == (
        "A token in a zone other than the battlefield ceases to exist."
    )
    assert adapter.unsupported_repair_requests == [None, ("known",)]
    assert adapter.repair_candidates == [None, first]
    assert result.citation_repaired is True


@pytest.mark.asyncio
async def test_substantive_answer_without_citations_gets_one_repair_attempt() -> None:
    uncited = GroundedAnswer(
        answer="A token ceases to exist.",
        citations=[],
        assumptions=[],
        confidence="high",
        needs_clarification=False,
        behavior="answer",
    )
    adapter = FakeAdapter(answers=[uncited, _answer("known")])

    result = await GroundedGenerationService(adapter).answer(
        question="What happens to a token in a graveyard?",
        passages=[_passage()],
        safety_identifier="stable-private-id",
    )

    assert result.answer.behavior == "answer"
    assert adapter.missing_citation_repair_requests == [False, True]
    assert result.citation_repaired is True


@pytest.mark.asyncio
async def test_conversation_context_is_preserved_during_citation_repair() -> None:
    conversation = (
        ConversationContextMessage(
            message_id=__import__('uuid').uuid4(),
            role='user',
            content='My creature is Slippery Bogle.',
        ),
    )
    adapter = FakeAdapter(answers=[_answer('invented'), _answer('known')])

    await GroundedGenerationService(adapter).answer(
        question='What if it loses hexproof?',
        passages=[_passage()],
        conversation=conversation,
        safety_identifier='stable-private-id',
    )

    assert adapter.conversation_requests == [conversation, conversation]


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


@pytest.mark.asyncio
async def test_second_unsupported_excerpt_returns_grounded_abstention() -> None:
    adapter = FakeAdapter(
        answers=[
            _answer("known", claim="The token disappears."),
            _answer("known", claim="The object vanishes."),
        ]
    )

    result = await GroundedGenerationService(adapter).answer(
        question="What happens?",
        passages=[_passage()],
        safety_identifier="stable-private-id",
    )

    assert result.answer.behavior == "abstain"
    assert result.answer.citations == []
    assert adapter.unsupported_repair_requests == [None, ("known",)]


@pytest.mark.asyncio
async def test_context_free_unresolved_comparison_is_deterministically_clarified() -> None:
    adapter = FakeAdapter(answers=[_answer("known")])

    result = await GroundedGenerationService(adapter).answer(
        question="Does the trigger happen first?",
        passages=[_passage()],
        safety_identifier="stable-private-id",
    )

    assert result.answer.behavior == "clarify"
    assert result.answer.needs_clarification is True
    assert result.answer.citations == []
    assert "which trigger" in result.answer.answer.casefold()
    assert len(adapter.repair_candidates) == 1


@pytest.mark.asyncio
async def test_conversation_resolves_comparison_without_policy_override() -> None:
    conversation = (
        ConversationContextMessage(
            message_id=__import__("uuid").uuid4(),
            role="user",
            content="I control two triggers and put the draw trigger on top.",
        ),
    )
    expected = _answer("known")
    adapter = FakeAdapter(answers=[expected])

    result = await GroundedGenerationService(adapter).answer(
        question="Does the trigger happen first?",
        passages=[_passage()],
        conversation=conversation,
        safety_identifier="stable-private-id",
    )

    assert result.answer.behavior == "answer"
    assert result.answer.answer == expected.answer


@pytest.mark.asyncio
async def test_current_local_event_lookup_is_deterministically_abstained() -> None:
    adapter = FakeAdapter(answers=[_answer("known")])

    result = await GroundedGenerationService(adapter).answer(
        question="Which store near me has a qualifier tonight?",
        passages=[_passage()],
        safety_identifier="stable-private-id",
    )

    assert result.answer.behavior == "abstain"
    assert result.answer.needs_clarification is False
    assert result.answer.citations == []
    assert "current local" in result.answer.answer.casefold()
    assert len(adapter.repair_candidates) == 1


@pytest.mark.asyncio
async def test_tournament_rules_question_is_not_scope_abstained() -> None:
    expected = _answer("known")
    adapter = FakeAdapter(answers=[expected])

    result = await GroundedGenerationService(adapter).answer(
        question="How does priority work at a tournament?",
        passages=[_passage()],
        safety_identifier="stable-private-id",
    )

    assert result.answer.behavior == "answer"
    assert result.answer.answer == expected.answer
