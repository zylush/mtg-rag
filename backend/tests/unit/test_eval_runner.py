from __future__ import annotations

import asyncio
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest
from google.api_core.exceptions import PreconditionFailed

from app.api.auth import AuthenticatedUser
from app.api.schemas import AskResponse, CitationResponse
from app.ask.context import ConversationContext, ConversationContextMessage
from app.ask.service import RetrievalBundle
from app.config import Settings
from app.evals.harness import (
    CachePair,
    CaseResult,
    EvalCase,
    EvaluationRun,
    EvaluationSuite,
    EvaluationSuiteError,
    Review,
)
from app.evals.runner import (
    PassageIdentity,
    RecordingRetrievalProvider,
    RecordingRetrievalRepository,
    RetrievalComponentTimings,
    RetrievalObservation,
    SeededConversation,
    StagingCaseExecutor,
    _behavior,
    _evaluation_openai_client,
    capture_suite,
    evaluation_settings,
    reference_key,
    run_payload,
    validate_capture_output,
    write_run_capture,
    write_run_capture_to_gcs,
)
from app.generation.citations import ResolvedAnswer
from app.generation.openai_adapter import RetrievedPassage
from app.generation.service import GenerationOutcome
from app.retrieval.analysis import QuestionAnalysis, analyze_question
from app.retrieval.service import PreparedRetrieval, RetrievalCandidate


def test_behavior_uses_explicit_model_abstention_even_with_citations() -> None:
    response = AskResponse(
        conversation_id=uuid.uuid4(),
        message_id=uuid.uuid4(),
        answer="The supplied passages do not contain current prices.",
        citations=[
            CitationResponse(
                passage_id="00000000-0000-0000-0000-000000000101",
                claim="The passage contains card data only.",
                label="Card data",
                url="https://example.test/card",
            )
        ],
        assumptions=[],
        confidence="low",
        needs_clarification=False,
        quota_remaining=199,
        cache_status="ineligible",
    )
    generation = GenerationOutcome(
        answer=ResolvedAnswer(
            answer=response.answer,
            citations=[],
            assumptions=[],
            confidence="low",
            needs_clarification=False,
            behavior="abstain",
        ),
        request_id="resp_eval",
        latency_ms=41,
        input_tokens=321,
        output_tokens=45,
        model="gpt-5.6-luna",
        citation_repaired=False,
    )

    assert _behavior(response, generation) == "abstain"


def _case(case_id: str) -> EvalCase:
    return EvalCase(
        case_id=case_id,
        category="exact_rule",
        question=f"Question {case_id}",
        expected_reference_keys=("100.1",),
        expected_behavior="answer",
    )


def _result(case_id: str, *, cache_hit: bool = False) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        retrieved_reference_keys=("100.1",),
        citation_reference_keys=("100.1",),
        unknown_citation_ids=(),
        behavior="answer",
        retrieval_latency_ms=12.5,
        embedding_latency_ms=2.0,
        exact_latency_ms=3.0,
        lexical_latency_ms=4.0,
        vector_latency_ms=5.0,
        api_latency_ms=25.0,
        cache_hit=cache_hit,
    )


def _suite() -> EvaluationSuite:
    return EvaluationSuite(
        version="runner-v1",
        rules_effective_date="2026-08-07",
        review=Review(status="pending", reviewer=None, reviewed_at=None),
        cases=(_case("first"), _case("second"), _case("unrelated")),
        positive_pairs=(CachePair("positive-1", "first", "second"),),
        negative_pairs=(CachePair("negative-1", "first", "unrelated"),),
    )


@dataclass
class FakeExecutor:
    results: dict[str, CaseResult]
    calls: list[str] = field(default_factory=list)

    async def execute(self, case: EvalCase) -> CaseResult:
        self.calls.append(case.case_id)
        return self.results[case.case_id]


def test_reference_keys_match_the_release_suite_contract() -> None:
    assert reference_key(
        PassageIdentity("rule", "702.9", {}, "702.9. Flying")
    ) == "702.9"
    assert reference_key(
        PassageIdentity(
            "glossary",
            "flying",
            {"citation_label": "Comprehensive Rules Glossary: Flying"},
            "Flying\nA keyword ability.",
        )
    ) == "glossary:Flying"
    assert reference_key(
        PassageIdentity(
            "card",
            "00000000-0000-0000-0000-000000000001",
            {"card_name": "Lightning Bolt"},
            "Lightning Bolt\nLightning Bolt deals 3 damage.",
        )
    ) == "card:Lightning Bolt"
    assert reference_key(
        PassageIdentity("glossary", "flying", {}, "Flying\nA keyword ability.")
    ) == "glossary:Flying"
    assert reference_key(PassageIdentity("ruling", "ruling-1", {}, "Text")) == (
        "ruling-1"
    )
    with pytest.raises(EvaluationSuiteError, match="no reference term"):
        reference_key(PassageIdentity("glossary", "empty", {}, "   "))
    with pytest.raises(EvaluationSuiteError, match="no card_name"):
        reference_key(PassageIdentity("card", "card-1", {}, "Card text"))


@pytest.mark.asyncio
async def test_capture_runs_in_suite_order_and_reports_observed_cache_pairs() -> None:
    executor = FakeExecutor(
        {
            "first": _result("first"),
            "second": _result("second", cache_hit=True),
            "unrelated": _result("unrelated"),
        }
    )

    progress: list[str] = []
    run = await capture_suite(_suite(), executor, progress=progress.append)

    assert executor.calls == ["first", "second", "unrelated"]
    assert progress == executor.calls
    assert [result.case_id for result in run.cases] == executor.calls
    assert run.semantic_cache_reuse_pair_ids == ("positive-1",)
    assert run_payload(run)["suite_version"] == "runner-v1"
    assert run_payload(run)["cases"][0]["id"] == "first"  # type: ignore[index]
    first_payload = run_payload(run)["cases"][0]
    assert first_payload["unsupported_citation_ids"] == ()  # type: ignore[index]
    assert first_payload["citation_repaired"] is None  # type: ignore[index]
    assert first_payload["repair_latency_ms"] is None  # type: ignore[index]


@pytest.mark.asyncio
async def test_capture_rejects_a_result_for_the_wrong_case() -> None:
    executor = FakeExecutor(
        {
            "first": _result("wrong"),
            "second": _result("second"),
            "unrelated": _result("unrelated"),
        }
    )

    with pytest.raises(EvaluationSuiteError, match="returned result"):
        await capture_suite(_suite(), executor)


@dataclass
class FakeAsk:
    response: AskResponse
    calls: list[tuple[str, uuid.UUID | None]] = field(default_factory=list)

    async def ask(
        self,
        *,
        user: AuthenticatedUser,
        question: str,
        conversation_id: uuid.UUID | None,
    ) -> AskResponse:
        self.calls.append((question, conversation_id))
        return self.response


@dataclass
class FakeSeeder:
    seeded: SeededConversation
    calls: list[str] = field(default_factory=list)

    async def seed(
        self, case: EvalCase, *, user: AuthenticatedUser
    ) -> SeededConversation:
        self.calls.append(case.case_id)
        return self.seeded


@dataclass
class FakeObservedRetrieval:
    observation: RetrievalObservation | None = None
    evaluated: list[str] = field(default_factory=list)

    def reset(self) -> None:
        self.observation = None

    async def evaluate(self, question: str) -> RetrievalObservation:
        self.evaluated.append(question)
        return RetrievalObservation(
            passages=(
                RetrievedPassage(
                    passage_id="00000000-0000-0000-0000-000000000101",
                    document_type="rule",
                    citation_label="Comprehensive Rules 702.9",
                    canonical_url="https://magic.wizards.com/rules#702.9",
                    text="702.9. Flying",
                ),
            ),
            latency_ms=17.0,
            embedding_latency_ms=2.0,
            exact_latency_ms=3.0,
            lexical_latency_ms=4.0,
            vector_latency_ms=5.0,
        )


@dataclass
class FakeObservedGeneration:
    observation: GenerationOutcome | None
    resets: int = 0

    def reset(self) -> None:
        self.resets += 1


@dataclass
class FakeBaseRetrieval:
    passages: list[RetrievedPassage]
    embedded: list[str] = field(default_factory=list)
    retrieved: list[tuple[str, list[float]]] = field(default_factory=list)

    async def embed_question(self, question: str) -> list[float]:
        self.embedded.append(question)
        return [0.25]

    async def prepare_retrieval(self, question: str) -> PreparedRetrieval:
        return PreparedRetrieval(question=question, exact=(), lexical=())

    async def retrieve_with_embedding(
        self,
        question: str,
        embedding: list[float],
        *,
        prepared: PreparedRetrieval | asyncio.Task[PreparedRetrieval] | None = None,
    ) -> RetrievalBundle:
        if isinstance(prepared, asyncio.Task):
            await prepared
        self.retrieved.append((question, embedding))
        return RetrievalBundle(embedding=embedding, passages=self.passages)


@dataclass
class VectorOverlapBaseRetrieval(FakeBaseRetrieval):
    retrieve_started: asyncio.Event = field(default_factory=asyncio.Event)
    prepared_was_pending: bool = False

    async def prepare_retrieval(self, question: str) -> PreparedRetrieval:
        await self.retrieve_started.wait()
        return PreparedRetrieval(question=question, exact=(), lexical=())

    async def retrieve_with_embedding(
        self,
        question: str,
        embedding: list[float],
        *,
        prepared: PreparedRetrieval | asyncio.Task[PreparedRetrieval] | None = None,
    ) -> RetrievalBundle:
        self.prepared_was_pending = isinstance(prepared, asyncio.Task) and not prepared.done()
        self.retrieve_started.set()
        assert isinstance(prepared, asyncio.Task)
        resolved = await prepared
        return await super().retrieve_with_embedding(
            question,
            embedding,
            prepared=resolved,
        )


@dataclass
class FakeTimingSource:
    resets: int = 0

    @property
    def timings(self) -> RetrievalComponentTimings:
        return RetrievalComponentTimings(
            exact_latency_ms=3.0,
            lexical_latency_ms=4.0,
            vector_latency_ms=5.0,
        )

    def reset(self) -> None:
        self.resets += 1


@dataclass
class FakeRetrievalRepository:
    calls: list[str] = field(default_factory=list)

    async def exact(
        self,
        analysis: QuestionAnalysis,
        *,
        limit: int,
        embedding: list[float] | None = None,
    ) -> list[RetrievalCandidate]:
        self.calls.append("exact")
        return []

    async def lexical(
        self, question: str, *, limit: int
    ) -> list[RetrievalCandidate]:
        self.calls.append("lexical")
        return []

    async def vector(
        self, embedding: list[float], *, limit: int
    ) -> list[RetrievalCandidate]:
        self.calls.append("vector")
        return []


@pytest.mark.asyncio
async def test_recording_repository_captures_each_retrieval_component() -> None:
    base = FakeRetrievalRepository()
    repository = RecordingRetrievalRepository(base)

    await repository.exact(
        analyze_question("Can reach block flying?"),
        limit=20,
    )
    await repository.lexical("can reach block flying", limit=20)
    await repository.vector([0.25], limit=20)

    assert base.calls == ["exact", "lexical", "vector"]
    assert repository.timings.exact_latency_ms is not None
    assert repository.timings.exact_latency_ms >= 0
    assert repository.timings.lexical_latency_ms is not None
    assert repository.timings.lexical_latency_ms >= 0
    assert repository.timings.vector_latency_ms is not None
    assert repository.timings.vector_latency_ms >= 0

    repository.reset()

    assert repository.timings == RetrievalComponentTimings()


@pytest.mark.asyncio
async def test_recording_retrieval_captures_the_complete_retrieval_path() -> None:
    passage = RetrievedPassage(
        passage_id="00000000-0000-0000-0000-000000000101",
        document_type="rule",
        citation_label="Comprehensive Rules 702.9",
        canonical_url="https://magic.wizards.com/rules#702.9",
        text="702.9. Flying",
    )
    base = FakeBaseRetrieval([passage])
    timing_source = FakeTimingSource()
    retrieval = RecordingRetrievalProvider(base, timing_source=timing_source)

    observation = await retrieval.evaluate("Can reach block flying?")

    assert base.embedded == ["Can reach block flying?"]
    assert base.retrieved == [("Can reach block flying?", [0.25])]
    assert observation.passages == (passage,)
    assert observation.latency_ms >= 0
    assert observation.embedding_latency_ms >= 0
    assert observation.exact_latency_ms == 3.0
    assert observation.lexical_latency_ms == 4.0
    assert observation.vector_latency_ms == 5.0
    assert retrieval.observation == observation
    assert timing_source.resets == 1


@pytest.mark.asyncio
async def test_recording_retrieval_starts_vector_before_text_preparation_finishes() -> None:
    base = VectorOverlapBaseRetrieval([])
    retrieval = RecordingRetrievalProvider(base)

    observation = await asyncio.wait_for(
        retrieval.evaluate("Can reach block flying?"),
        timeout=0.5,
    )

    assert base.prepared_was_pending is True
    assert observation.passages == ()


def test_evaluation_settings_are_non_production_contextual_and_cache_isolated() -> None:
    base = Settings(
        database_url="postgresql+asyncpg://mtg:mtg@localhost:5432/mtg",
        frontend_origin="http://localhost:5173",
        retrieval_version="r" * 64,
    )

    configured = evaluation_settings(base, run_id=uuid.UUID(int=1))

    assert configured.conversation_context_enabled is True
    assert configured.daily_answer_limit >= 121
    assert configured.burst_limit_per_minute >= 121
    assert configured.retrieval_version != base.retrieval_version
    assert len(configured.retrieval_version) <= 64

    production = base.model_copy(update={"environment": "production"})
    with pytest.raises(EvaluationSuiteError, match="production"):
        evaluation_settings(production, run_id=uuid.UUID(int=2))


@pytest.mark.asyncio
async def test_evaluation_openai_client_disables_transport_retries() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://mtg:mtg@localhost:5432/mtg",
        frontend_origin="http://localhost:5173",
        openai_api_key="test-key",
    )

    client = _evaluation_openai_client(settings)
    try:
        assert client.max_retries == 0
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_run_capture_is_written_exclusively(tmp_path: Path) -> None:
    suite = _suite()
    run = await capture_suite(
        suite,
        FakeExecutor(
            {
                "first": _result("first"),
                "second": _result("second"),
                "unrelated": _result("unrelated"),
            }
        ),
    )
    output = tmp_path / "capture.json"

    write_run_capture(output, run)

    assert '"suite_version": "runner-v1"' in output.read_text(encoding="utf-8")
    with pytest.raises(EvaluationSuiteError, match="already exists"):
        write_run_capture(output, run)


def test_capture_output_is_validated_before_external_work(tmp_path: Path) -> None:
    output = tmp_path / "capture.json"

    validate_capture_output(output)

    output.write_text("existing evidence", encoding="utf-8")
    with pytest.raises(EvaluationSuiteError, match="already exists"):
        validate_capture_output(output)
    with pytest.raises(EvaluationSuiteError, match="directory does not exist"):
        validate_capture_output(tmp_path / "missing" / "capture.json")


class FakeCaptureBlob:
    def __init__(self, name: str, *, collision: bool = False) -> None:
        self.name = name
        self.cache_control: str | None = None
        self.metadata: dict[str, str] | None = None
        self.calls: list[dict[str, object]] = []
        self._collision = collision

    def upload_from_string(self, payload: bytes, **kwargs: object) -> None:
        if self._collision:
            raise PreconditionFailed("capture already exists")
        self.calls.append({"payload": payload, **kwargs})


class FakeCaptureBucket:
    def __init__(self, *, collision: bool = False) -> None:
        self.name = "mtg-rules-desk-dev-mtg-rag-dev-snapshots"
        self.created: list[FakeCaptureBlob] = []
        self._collision = collision

    def blob(self, name: str) -> FakeCaptureBlob:
        blob = FakeCaptureBlob(name, collision=self._collision)
        self.created.append(blob)
        return blob


def test_gcs_run_capture_is_create_only_and_records_integrity_metadata() -> None:
    run = EvaluationRun(
        suite_version="runner-v1",
        cases=(_result("first"),),
        semantic_cache_reuse_pair_ids=(),
    )
    bucket = FakeCaptureBucket()
    run_id = uuid.UUID("11111111-2222-4333-8444-555555555555")

    uri = write_run_capture_to_gcs(
        bucket,  # type: ignore[arg-type]
        prefix="evaluation-captures",
        run=run,
        run_id=run_id,
        captured_at=datetime(2026, 8, 20, 12, 30, tzinfo=UTC),
    )

    blob = bucket.created[0]
    assert blob.name == (
        "evaluation-captures/runner-v1/2026/08/20/"
        "11111111-2222-4333-8444-555555555555.json"
    )
    assert len(blob.calls) == 1
    payload = blob.calls[0]["payload"]
    assert isinstance(payload, bytes)
    assert blob.calls[0]["content_type"] == "application/json; charset=utf-8"
    assert blob.calls[0]["if_generation_match"] == 0
    assert blob.cache_control == "no-store"
    assert blob.metadata == {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "suite_version": "runner-v1",
        "run_id": str(run_id),
    }
    assert uri == f"gs://{bucket.name}/{blob.name}"


def test_gcs_run_capture_reports_an_immutable_name_collision() -> None:
    run = EvaluationRun(
        suite_version="runner-v1",
        cases=(_result("first"),),
        semantic_cache_reuse_pair_ids=(),
    )

    with pytest.raises(EvaluationSuiteError, match="already exists"):
        write_run_capture_to_gcs(
            FakeCaptureBucket(collision=True),  # type: ignore[arg-type]
            prefix="evaluation-captures",
            run=run,
            run_id=uuid.UUID("11111111-2222-4333-8444-555555555555"),
            captured_at=datetime(2026, 8, 20, 12, 30, tzinfo=UTC),
        )


@pytest.mark.parametrize("prefix", ["", "/", "../captures", "captures/../private"])
def test_gcs_run_capture_rejects_unsafe_prefixes(prefix: str) -> None:
    run = EvaluationRun(
        suite_version="runner-v1",
        cases=(_result("first"),),
        semantic_cache_reuse_pair_ids=(),
    )

    with pytest.raises(EvaluationSuiteError, match="prefix"):
        write_run_capture_to_gcs(
            FakeCaptureBucket(),  # type: ignore[arg-type]
            prefix=prefix,
            run=run,
            run_id=uuid.UUID(int=1),
            captured_at=datetime(2026, 8, 20, 12, 30, tzinfo=UTC),
        )


def test_gcs_run_capture_rejects_unsafe_suite_and_naive_timestamp() -> None:
    unsafe = EvaluationRun(
        suite_version="../runner-v1",
        cases=(_result("first"),),
        semantic_cache_reuse_pair_ids=(),
    )
    valid = EvaluationRun(
        suite_version="runner-v1",
        cases=(_result("first"),),
        semantic_cache_reuse_pair_ids=(),
    )
    bucket = FakeCaptureBucket()

    with pytest.raises(EvaluationSuiteError, match="suite version"):
        write_run_capture_to_gcs(
            bucket,  # type: ignore[arg-type]
            prefix="evaluation-captures",
            run=unsafe,
            run_id=uuid.UUID(int=1),
            captured_at=datetime(2026, 8, 20, 12, 30, tzinfo=UTC),
        )
    with pytest.raises(EvaluationSuiteError, match="timezone"):
        write_run_capture_to_gcs(
            bucket,  # type: ignore[arg-type]
            prefix="evaluation-captures",
            run=valid,
            run_id=uuid.UUID(int=1),
            captured_at=datetime(2026, 8, 20, 12, 30),
        )


@dataclass
class FakeResolver:
    async def resolve(
        self, passage_ids: tuple[str, ...]
    ) -> dict[str, PassageIdentity]:
        return {
            passage_id: PassageIdentity(
                "rule",
                "702.9",
                {},
                "702.9. Flying. Reach can block flying.",
            )
            for passage_id in passage_ids
        }


@pytest.mark.asyncio
async def test_staging_executor_recreates_context_and_captures_cache_miss() -> None:
    conversation_id = uuid.uuid4()
    tail_id = uuid.uuid4()
    context = ConversationContext(
        messages=(
            ConversationContextMessage(
                message_id=tail_id,
                role="user",
                content="My attacker has flying.",
            ),
        ),
        tail_message_id=tail_id,
    )
    response = AskResponse(
        conversation_id=conversation_id,
        message_id=uuid.uuid4(),
        answer="A creature with reach can block it.",
        citations=[
            CitationResponse(
                passage_id="00000000-0000-0000-0000-000000000101",
                claim="Reach can block flying.",
                label="Comprehensive Rules 702.9",
                url="https://magic.wizards.com/rules#702.9",
            )
        ],
        assumptions=[],
        confidence="high",
        needs_clarification=False,
        quota_remaining=199,
        cache_status="ineligible",
    )
    ask = FakeAsk(response)
    retrieval = FakeObservedRetrieval()
    generation = FakeObservedGeneration(
        GenerationOutcome(
            answer=ResolvedAnswer(
                answer=response.answer,
                citations=[],
                assumptions=[],
                confidence="high",
                needs_clarification=False,
                behavior="answer",
            ),
            request_id="resp_eval",
            latency_ms=41,
            input_tokens=321,
            output_tokens=45,
            model="gpt-5.6-luna",
            citation_repaired=False,
            initial_latency_ms=41,
            initial_input_tokens=321,
            initial_output_tokens=45,
            repair_latency_ms=None,
            repair_input_tokens=None,
            repair_output_tokens=None,
        )
    )
    executor = StagingCaseExecutor(
        ask=ask,
        retrieval=retrieval,
        generation=generation,
        seeder=FakeSeeder(SeededConversation(conversation_id, context)),
        resolver=FakeResolver(),
        user=AuthenticatedUser(firebase_uid="eval-runner", email=None),
    )
    case = EvalCase(
        case_id="followup",
        category="follow_up_context",
        question="Can reach block it?",
        expected_reference_keys=("702.9",),
        expected_behavior="answer",
    )

    result = await executor.execute(case)

    assert ask.calls == [("Can reach block it?", conversation_id)]
    assert retrieval.evaluated[0].startswith("Current question:\nCan reach block it?")
    assert "My attacker has flying." in retrieval.evaluated[0]
    assert result.retrieved_reference_keys == ("702.9",)
    assert result.citation_reference_keys == ("702.9",)
    assert result.unsupported_citation_ids == ()
    assert result.behavior == "answer"
    assert result.answer == "A creature with reach can block it."
    assert result.model == "gpt-5.6-luna"
    assert result.model_latency_ms == 41
    assert result.input_tokens == 321
    assert result.output_tokens == 45
    assert result.citation_repaired is False
    assert result.initial_model_latency_ms == 41
    assert result.initial_input_tokens == 321
    assert result.initial_output_tokens == 45
    assert result.repair_latency_ms is None
    assert result.repair_input_tokens is None
    assert result.repair_output_tokens is None
    assert result.retrieval_latency_ms == 17.0
    assert result.embedding_latency_ms == 2.0
    assert result.exact_latency_ms == 3.0
    assert result.lexical_latency_ms == 4.0
    assert result.vector_latency_ms == 5.0
    assert result.cache_hit is False
    assert result.cache_status == "ineligible"
    assert result.confidence == "high"

    response.citations[0].claim = "This paraphrase is not present."
    unsupported = await executor.execute(case)
    assert unsupported.unsupported_citation_ids == (
        "00000000-0000-0000-0000-000000000101",
    )
    assert generation.resets == 2
