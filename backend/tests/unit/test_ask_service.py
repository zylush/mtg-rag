from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime

import pytest

from app.api.auth import AuthenticatedUser
from app.api.schemas import AskResponse
from app.api.services import BurstLimitExceededError, QuotaExceededError, ResourceNotFoundError
from app.ask.context import ConversationContext, ConversationContextMessage
from app.ask.service import AskApplicationService, CommittedExchange, RetrievalBundle
from app.cache.policy import CacheContext
from app.cache.repository import CachedAnswer
from app.generation.citations import ResolvedAnswer, ResolvedCitation
from app.generation.openai_adapter import RetrievedPassage
from app.generation.service import GenerationOutcome

USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
CONVERSATION_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")
MESSAGE_ID = uuid.UUID("00000000-0000-0000-0000-000000000011")
PASSAGE_ID = uuid.UUID("00000000-0000-0000-0000-000000000020")
REQUEST_ID = uuid.UUID("00000000-0000-0000-0000-000000000030")


def _context() -> CacheContext:
    return CacheContext(
        corpus_versions={"rules": "r1", "cards": "c1", "rulings": "u1"},
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
        generation_model="gpt-5.6-luna",
        prompt_version="p1",
        retrieval_version="rrf1",
        language="en",
        filters=("paper",),
    )


def _answer() -> ResolvedAnswer:
    return ResolvedAnswer(
        answer="Flying restricts which creatures can block.",
        citations=[
            ResolvedCitation(
                passage_id=str(PASSAGE_ID),
                claim="Flying restricts blockers.",
                label="Comprehensive Rules 702.9",
                url="https://magic.wizards.com/rules#702.9",
            )
        ],
        assumptions=[],
        confidence="high",
        needs_clarification=False,
        behavior="answer",
    )


def _response() -> AskResponse:
    return AskResponse(
        conversation_id=CONVERSATION_ID,
        message_id=MESSAGE_ID,
        answer=_answer().answer,
        citations=[
            {
                "passage_id": citation.passage_id,
                "claim": citation.claim,
                "label": citation.label,
                "url": citation.url,
            }
            for citation in _answer().citations
        ],
        assumptions=[],
        confidence="high",
        needs_clarification=False,
        quota_remaining=19,
        cache_status="miss",
    )


@dataclass
class FakeUsers:
    calls: int = 0

    async def get_or_create(self, user: AuthenticatedUser) -> uuid.UUID:
        self.calls += 1
        return USER_ID


@dataclass
class FakeUsage:
    admitted: bool = True
    calls: int = 0

    async def register_ask_attempt(self, user_id: uuid.UUID, *, now: datetime, limit: int) -> bool:
        self.calls += 1
        return self.admitted


@dataclass
class FakeContexts:
    async def current(self) -> CacheContext:
        return _context()


@dataclass
class FakeConversationContexts:
    context: ConversationContext = field(
        default_factory=lambda: ConversationContext(messages=(), tail_message_id=None)
    )
    error: Exception | None = None
    calls: list[tuple[str, uuid.UUID]] = field(default_factory=list)

    async def load(
        self, *, firebase_uid: str, conversation_id: uuid.UUID
    ) -> ConversationContext:
        self.calls.append((firebase_uid, conversation_id))
        if self.error is not None:
            raise self.error
        return self.context


@dataclass
class FakeCache:
    exact: CachedAnswer | None = None
    semantic: CachedAnswer | None = None
    exact_calls: int = 0
    semantic_calls: int = 0
    put_calls: int = 0

    async def get_exact(self, **kwargs: object) -> CachedAnswer | None:
        self.exact_calls += 1
        return self.exact

    async def get_semantic(self, **kwargs: object) -> CachedAnswer | None:
        self.semantic_calls += 1
        return self.semantic

    async def put(self, **kwargs: object) -> str:
        self.put_calls += 1
        return "cache-key"


@dataclass
class FakeRetrieval:
    fail: bool = False
    embed_calls: int = 0
    retrieve_calls: int = 0
    prepare_calls: int = 0
    embedded_questions: list[str] = field(default_factory=list)
    retrieved_questions: list[str] = field(default_factory=list)
    prepared_received: list[object | None] = field(default_factory=list)

    async def prepare_retrieval(self, question: str) -> object:
        self.prepare_calls += 1
        return question

    async def embed_question(self, question: str) -> list[float]:
        self.embed_calls += 1
        self.embedded_questions.append(question)
        return [0.1] * 1536

    async def retrieve_with_embedding(
        self,
        question: str,
        embedding: list[float],
        *,
        prepared: object | None = None,
    ) -> RetrievalBundle:
        if isinstance(prepared, asyncio.Task):
            prepared = await prepared
        self.retrieve_calls += 1
        self.retrieved_questions.append(question)
        self.prepared_received.append(prepared)
        if self.fail:
            raise RuntimeError("retrieval failed")
        return RetrievalBundle(
            embedding=embedding,
            passages=[
                RetrievedPassage(
                    passage_id=str(PASSAGE_ID),
                    document_type="rule",
                    citation_label="Comprehensive Rules 702.9",
                    canonical_url="https://magic.wizards.com/rules#702.9",
                    text="Flying restricts which creatures can block.",
                )
            ],
        )


@dataclass
class OverlapRetrieval(FakeRetrieval):
    prepare_started: asyncio.Event = field(default_factory=asyncio.Event)
    embedding_started: asyncio.Event = field(default_factory=asyncio.Event)

    async def prepare_retrieval(self, question: str) -> object:
        self.prepare_calls += 1
        self.prepare_started.set()
        await self.embedding_started.wait()
        return question

    async def embed_question(self, question: str) -> list[float]:
        self.embed_calls += 1
        self.embedded_questions.append(question)
        self.embedding_started.set()
        await self.prepare_started.wait()
        return [0.1] * 1536


@dataclass
class VectorOverlapRetrieval(FakeRetrieval):
    retrieve_started: asyncio.Event = field(default_factory=asyncio.Event)
    prepared_was_pending: bool = False

    async def prepare_retrieval(self, question: str) -> object:
        self.prepare_calls += 1
        await self.retrieve_started.wait()
        return question

    async def retrieve_with_embedding(
        self,
        question: str,
        embedding: list[float],
        *,
        prepared: object | None = None,
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
class CancellableRetrieval(FakeRetrieval):
    cancelled: bool = False

    async def embed_question(self, question: str) -> list[float]:
        embedding = await super().embed_question(question)
        await asyncio.sleep(0)
        return embedding

    async def prepare_retrieval(self, question: str) -> object:
        self.prepare_calls += 1
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


@dataclass
class FakeGeneration:
    calls: int = 0
    requests: list[dict[str, object]] = field(default_factory=list)

    async def answer(self, **kwargs: object) -> GenerationOutcome:
        self.calls += 1
        self.requests.append(kwargs)
        return GenerationOutcome(
            answer=_answer(),
            request_id="resp_1",
            latency_ms=12,
            input_tokens=100,
            output_tokens=30,
            model="gpt-5.6-luna",
            citation_repaired=False,
            initial_latency_ms=12,
            initial_input_tokens=100,
            initial_output_tokens=30,
            repair_latency_ms=None,
            repair_input_tokens=None,
            repair_output_tokens=None,
        )


@dataclass
class FakeCommitter:
    admitted: bool = True
    replay: AskResponse | None = None
    calls: list[str] = field(default_factory=list)
    requests: list[dict[str, object]] = field(default_factory=list)
    begin_requests: list[dict[str, object]] = field(default_factory=list)
    release_requests: list[dict[str, object]] = field(default_factory=list)

    async def begin_request(self, **kwargs: object) -> AskResponse | None:
        self.begin_requests.append(kwargs)
        return self.replay

    async def release_request(self, **kwargs: object) -> None:
        self.release_requests.append(kwargs)

    async def commit(self, **kwargs: object) -> CommittedExchange | None:
        self.requests.append(kwargs)
        self.calls.append(str(kwargs["cache_status"]))
        if not self.admitted:
            return None
        return CommittedExchange(
            conversation_id=CONVERSATION_ID,
            message_id=MESSAGE_ID,
            successful_answers=1,
        )


def service(
    *,
    users: FakeUsers | None = None,
    usage: FakeUsage | None = None,
    cache: FakeCache | None = None,
    retrieval: FakeRetrieval | None = None,
    generation: FakeGeneration | None = None,
    committer: FakeCommitter | None = None,
    conversation_contexts: FakeConversationContexts | None = None,
) -> AskApplicationService:
    return AskApplicationService(
        users=users or FakeUsers(),
        usage=usage or FakeUsage(),
        contexts=FakeContexts(),
        conversation_contexts=conversation_contexts or FakeConversationContexts(),
        cache=cache or FakeCache(),
        retrieval=retrieval or FakeRetrieval(),
        generation=generation or FakeGeneration(),
        committer=committer or FakeCommitter(),
        daily_limit=20,
        burst_limit=5,
        semantic_threshold=0.98,
        cache_ttl_days=7,
    )


@pytest.mark.asyncio
async def test_completed_request_replays_before_rate_limit_cache_or_model_work() -> None:
    users = FakeUsers()
    usage = FakeUsage()
    cache = FakeCache()
    retrieval = FakeRetrieval()
    generation = FakeGeneration()
    committer = FakeCommitter(replay=_response())

    response = await service(
        users=users,
        usage=usage,
        cache=cache,
        retrieval=retrieval,
        generation=generation,
        committer=committer,
    ).ask(
        user=AuthenticatedUser(firebase_uid="firebase-1", email=None),
        question="What is flying?",
        conversation_id=None,
        request_id=REQUEST_ID,
    )

    assert response == _response()
    assert users.calls == 1
    assert usage.calls == 0
    assert cache.exact_calls == cache.semantic_calls == cache.put_calls == 0
    assert retrieval.embed_calls == retrieval.retrieve_calls == generation.calls == 0
    assert committer.calls == []
    assert committer.release_requests == []


@pytest.mark.asyncio
async def test_new_request_claim_is_completed_with_the_same_key_and_fingerprint() -> None:
    committer = FakeCommitter()

    await service(committer=committer).ask(
        user=AuthenticatedUser(firebase_uid="firebase-1", email=None),
        question="What is flying?",
        conversation_id=None,
        request_id=REQUEST_ID,
    )

    assert committer.begin_requests[0]["request_id"] == REQUEST_ID
    assert len(str(committer.begin_requests[0]["request_hash"])) == 64
    assert committer.requests[0]["request_id"] == REQUEST_ID
    assert committer.requests[0]["request_hash"] == committer.begin_requests[0]["request_hash"]


@pytest.mark.asyncio
async def test_failed_request_releases_its_claim_for_a_safe_retry() -> None:
    committer = FakeCommitter()

    with pytest.raises(RuntimeError, match="retrieval failed"):
        await service(retrieval=FakeRetrieval(fail=True), committer=committer).ask(
            user=AuthenticatedUser(firebase_uid="firebase-1", email=None),
            question="What is flying?",
            conversation_id=None,
            request_id=REQUEST_ID,
        )

    assert committer.release_requests[0]["request_id"] == REQUEST_ID
    assert committer.release_requests[0]["request_hash"] == (
        committer.begin_requests[0]["request_hash"]
    )


@pytest.mark.asyncio
async def test_exact_cache_hit_skips_embedding_retrieval_and_generation_but_counts_quota() -> None:
    cache = FakeCache(
        exact=CachedAnswer(
            entry_id=uuid.uuid4(),
            response=_answer().model_dump(mode="json"),
            citation_ids=(PASSAGE_ID,),
            similarity=1.0,
        )
    )
    retrieval = FakeRetrieval()
    generation = FakeGeneration()
    committer = FakeCommitter()

    response = await service(
        cache=cache, retrieval=retrieval, generation=generation, committer=committer
    ).ask(
        user=AuthenticatedUser(firebase_uid="firebase-1", email=None),
        question="What is flying?",
        conversation_id=None,
    )

    assert response.cache_status == "exact"
    assert response.quota_remaining == 19
    assert retrieval.embed_calls == retrieval.retrieve_calls == generation.calls == 0
    assert committer.calls == ["exact"]


@pytest.mark.asyncio
async def test_public_cache_hit_returns_ephemeral_answer_without_account_persistence() -> None:
    users = FakeUsers()
    usage = FakeUsage()
    committer = FakeCommitter()
    cache = FakeCache(
        exact=CachedAnswer(
            entry_id=uuid.uuid4(),
            response=_answer().model_dump(mode="json"),
            citation_ids=(PASSAGE_ID,),
            similarity=1.0,
        )
    )

    response = await service(
        users=users, usage=usage, cache=cache, committer=committer
    ).ask_public(question="What is flying?", client_key="client-key")

    assert response.cache_status == "exact"
    assert response.quota_remaining == 0
    assert response.conversation_id not in {CONVERSATION_ID}
    assert users.calls == usage.calls == 0
    assert committer.calls == []


@pytest.mark.asyncio
async def test_cache_miss_overlaps_embedding_with_prepared_text_retrieval() -> None:
    retrieval = OverlapRetrieval()

    response = await asyncio.wait_for(
        service(retrieval=retrieval).ask(
            user=AuthenticatedUser(firebase_uid="firebase-1", email=None),
            question="What is flying?",
            conversation_id=None,
        ),
        timeout=0.5,
    )

    assert response.cache_status == "miss"
    assert retrieval.prepare_calls == 1
    assert retrieval.embed_calls == 1
    assert retrieval.retrieve_calls == 1
    assert retrieval.prepared_received == ["What is flying?"]


@pytest.mark.asyncio
async def test_cache_miss_starts_vector_path_before_text_preparation_finishes() -> None:
    retrieval = VectorOverlapRetrieval()

    response = await asyncio.wait_for(
        service(retrieval=retrieval).ask(
            user=AuthenticatedUser(firebase_uid="firebase-1", email=None),
            question="What is flying?",
            conversation_id=None,
        ),
        timeout=0.5,
    )

    assert response.cache_status == "miss"
    assert retrieval.prepared_was_pending is True
    assert retrieval.prepared_received == ["What is flying?"]


@pytest.mark.asyncio
async def test_semantic_cache_hit_cancels_speculative_text_retrieval() -> None:
    retrieval = CancellableRetrieval()
    cache = FakeCache(
        semantic=CachedAnswer(
            entry_id=uuid.uuid4(),
            response=_answer().model_dump(mode="json"),
            citation_ids=(PASSAGE_ID,),
            similarity=0.99,
        )
    )

    response = await service(cache=cache, retrieval=retrieval).ask(
        user=AuthenticatedUser(firebase_uid="firebase-1", email=None),
        question="What is flying?",
        conversation_id=None,
    )

    assert response.cache_status == "semantic"
    assert retrieval.prepare_calls == 1
    assert retrieval.cancelled is True
    assert retrieval.retrieve_calls == 0


@pytest.mark.asyncio
async def test_burst_limit_stops_before_cache_or_model_work() -> None:
    usage = FakeUsage(admitted=False)
    cache = FakeCache()

    with pytest.raises(BurstLimitExceededError):
        await service(usage=usage, cache=cache).ask(
            user=AuthenticatedUser(firebase_uid="firebase-1", email=None),
            question="What is flying?",
            conversation_id=None,
        )

    assert cache.exact_calls == 0


@pytest.mark.asyncio
async def test_retrieval_or_generation_failure_does_not_commit_or_consume_quota() -> None:
    retrieval = FakeRetrieval(fail=True)
    committer = FakeCommitter()

    with pytest.raises(RuntimeError, match="retrieval failed"):
        await service(retrieval=retrieval, committer=committer).ask(
            user=AuthenticatedUser(firebase_uid="firebase-1", email=None),
            question="What is flying?",
            conversation_id=None,
        )

    assert committer.calls == []


@pytest.mark.asyncio
async def test_high_confidence_definition_miss_is_cached_without_user_identity() -> None:
    cache = FakeCache()
    committer = FakeCommitter()

    response = await service(cache=cache, committer=committer).ask(
        user=AuthenticatedUser(firebase_uid="firebase-1", email=None),
        question="What is flying?",
        conversation_id=None,
    )

    assert response.cache_status == "miss"
    assert cache.semantic_calls == 1
    assert cache.put_calls == 1
    assert committer.calls == ["miss"]


@pytest.mark.asyncio
async def test_abstention_is_reported_ineligible_and_not_written_to_shared_cache() -> None:
    class AbstainingGeneration(FakeGeneration):
        async def answer(self, **kwargs: object) -> GenerationOutcome:
            outcome = await super().answer(**kwargs)
            return GenerationOutcome(
                answer=outcome.answer.model_copy(update={"behavior": "abstain"}),
                request_id=outcome.request_id,
                latency_ms=outcome.latency_ms,
                input_tokens=outcome.input_tokens,
                output_tokens=outcome.output_tokens,
                model=outcome.model,
                citation_repaired=outcome.citation_repaired,
            )

    cache = FakeCache()
    committer = FakeCommitter()

    response = await service(
        cache=cache,
        generation=AbstainingGeneration(),
        committer=committer,
    ).ask(
        user=AuthenticatedUser(firebase_uid="firebase-1", email=None),
        question="What is the price of a booster?",
        conversation_id=None,
    )

    assert response.cache_status == "ineligible"
    assert cache.put_calls == 0
    assert committer.calls == ["ineligible"]


@pytest.mark.asyncio
async def test_atomic_commit_rejection_reports_daily_quota_exhaustion() -> None:
    committer = FakeCommitter(admitted=False)

    with pytest.raises(QuotaExceededError):
        await service(committer=committer).ask(
            user=AuthenticatedUser(firebase_uid="firebase-1", email=None),
            question="What is flying?",
            conversation_id=None,
        )


@pytest.mark.asyncio
async def test_unowned_conversation_stops_before_cache_retrieval_or_model() -> None:
    users = FakeUsers()
    contexts = FakeConversationContexts(error=ResourceNotFoundError())
    usage = FakeUsage()
    cache = FakeCache()
    retrieval = FakeRetrieval()
    generation = FakeGeneration()
    committer = FakeCommitter()

    with pytest.raises(ResourceNotFoundError):
        await service(
            users=users,
            usage=usage,
            conversation_contexts=contexts,
            cache=cache,
            retrieval=retrieval,
            generation=generation,
            committer=committer,
        ).ask(
            user=AuthenticatedUser(firebase_uid='firebase-1', email=None),
            question='Use another conversation.',
            conversation_id=CONVERSATION_ID,
        )

    assert users.calls == 0
    assert usage.calls == 0
    assert cache.exact_calls == cache.semantic_calls == cache.put_calls == 0
    assert retrieval.embed_calls == retrieval.retrieve_calls == generation.calls == 0
    assert committer.calls == []


@pytest.mark.asyncio
async def test_standalone_question_does_not_load_conversation_context() -> None:
    contexts = FakeConversationContexts()
    committer = FakeCommitter()

    await service(
        conversation_contexts=contexts,
        committer=committer,
    ).ask(
        user=AuthenticatedUser(firebase_uid='firebase-1', email=None),
        question='What is flying?',
        conversation_id=None,
    )

    assert contexts.calls == []
    assert committer.requests[0]['enforce_conversation_tail'] is False


@pytest.mark.asyncio
async def test_contextual_follow_up_uses_history_for_retrieval_and_skips_shared_cache() -> None:
    tail = uuid.UUID('00000000-0000-0000-0000-000000000099')
    context = ConversationContext(
        messages=(
            ConversationContextMessage(
                message_id=uuid.uuid4(),
                role='user',
                content='My opponent targets Slippery Bogle with Murder.',
            ),
            ConversationContextMessage(
                message_id=tail,
                role='assistant',
                content='Murder cannot target a creature with hexproof.',
            ),
        ),
        tail_message_id=tail,
    )
    contexts = FakeConversationContexts(context=context)
    cache = FakeCache()
    retrieval = FakeRetrieval()
    generation = FakeGeneration()
    committer = FakeCommitter()

    response = await service(
        conversation_contexts=contexts,
        cache=cache,
        retrieval=retrieval,
        generation=generation,
        committer=committer,
    ).ask(
        user=AuthenticatedUser(firebase_uid='firebase-1', email=None),
        question='What if it loses hexproof?',
        conversation_id=CONVERSATION_ID,
    )

    assert response.cache_status == 'ineligible'
    assert contexts.calls == [("firebase-1", CONVERSATION_ID)]
    assert cache.exact_calls == cache.semantic_calls == cache.put_calls == 0
    assert retrieval.embedded_questions == retrieval.retrieved_questions
    assert 'Slippery Bogle' in retrieval.embedded_questions[0]
    assert generation.requests[0]['question'] == 'What if it loses hexproof?'
    assert generation.requests[0]['conversation'] == context.messages
    assert committer.requests[0]['expected_tail_message_id'] == tail
    assert committer.requests[0]['enforce_conversation_tail'] is True


@pytest.mark.asyncio
async def test_identical_follow_up_text_uses_distinct_conversation_facts() -> None:
    async def ask_with_fact(fact: str) -> tuple[str, FakeCache]:
        tail = uuid.uuid4()
        contexts = FakeConversationContexts(
            context=ConversationContext(
                messages=(
                    ConversationContextMessage(
                        message_id=uuid.uuid4(),
                        role="user",
                        content=fact,
                    ),
                    ConversationContextMessage(
                        message_id=tail,
                        role="assistant",
                        content="That fact changes the rules interaction.",
                    ),
                ),
                tail_message_id=tail,
            )
        )
        cache = FakeCache()
        retrieval = FakeRetrieval()
        await service(
            conversation_contexts=contexts,
            cache=cache,
            retrieval=retrieval,
        ).ask(
            user=AuthenticatedUser(firebase_uid="firebase-1", email=None),
            question="What happens to it?",
            conversation_id=CONVERSATION_ID,
        )
        return retrieval.embedded_questions[0], cache

    flying_query, flying_cache = await ask_with_fact("The creature has flying.")
    hexproof_query, hexproof_cache = await ask_with_fact("The creature has hexproof.")

    assert flying_query != hexproof_query
    assert "flying" in flying_query
    assert "hexproof" in hexproof_query
    assert flying_cache.exact_calls == flying_cache.semantic_calls == flying_cache.put_calls == 0
    assert (
        hexproof_cache.exact_calls
        == hexproof_cache.semantic_calls
        == hexproof_cache.put_calls
        == 0
    )


@pytest.mark.asyncio
async def test_context_logs_counts_without_logging_message_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_marker = "private-context-marker-ctx-008"
    tail = uuid.uuid4()
    contexts = FakeConversationContexts(
        context=ConversationContext(
            messages=(
                ConversationContextMessage(
                    message_id=tail,
                    role="user",
                    content=private_marker,
                ),
            ),
            tail_message_id=tail,
            truncated=True,
        )
    )
    caplog.set_level(logging.INFO, logger="app.ask.service")

    await service(conversation_contexts=contexts).ask(
        user=AuthenticatedUser(firebase_uid="private-context-user", email=None),
        question="What happens next?",
        conversation_id=CONVERSATION_ID,
    )

    record = next(item for item in caplog.records if item.message == "answer_completed")
    assert record.context_message_count == 1  # type: ignore[attr-defined]
    assert record.context_truncated is True  # type: ignore[attr-defined]
    assert private_marker not in caplog.text
    assert "private-context-user" not in caplog.text


@pytest.mark.asyncio
async def test_completed_answer_logs_operational_metadata_without_user_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_content = "What is private-flying-content-that-must-not-be-logged?"
    caplog.set_level(logging.INFO, logger="app.ask.service")

    await service().ask(
        user=AuthenticatedUser(firebase_uid="private-firebase-identity", email=None),
        question=private_content,
        conversation_id=None,
    )

    record = next(item for item in caplog.records if item.message == "answer_completed")
    assert record.conversation_id == str(CONVERSATION_ID)  # type: ignore[attr-defined]
    assert record.message_id == str(MESSAGE_ID)  # type: ignore[attr-defined]
    assert record.cache_status == "miss"  # type: ignore[attr-defined]
    assert record.source_versions == {  # type: ignore[attr-defined]
        "rules": "r1",
        "cards": "c1",
        "rulings": "u1",
    }
    assert record.model == "gpt-5.6-luna"  # type: ignore[attr-defined]
    assert record.openai_request_id == "resp_1"  # type: ignore[attr-defined]
    assert record.model_latency_ms == 12  # type: ignore[attr-defined]
    assert record.input_tokens == 100  # type: ignore[attr-defined]
    assert record.output_tokens == 30  # type: ignore[attr-defined]
    assert record.initial_model_latency_ms == 12  # type: ignore[attr-defined]
    assert record.initial_input_tokens == 100  # type: ignore[attr-defined]
    assert record.initial_output_tokens == 30  # type: ignore[attr-defined]
    assert record.repair_latency_ms is None  # type: ignore[attr-defined]
    assert record.repair_input_tokens is None  # type: ignore[attr-defined]
    assert record.repair_output_tokens is None  # type: ignore[attr-defined]
    assert private_content not in caplog.text
    assert "private-firebase-identity" not in caplog.text
