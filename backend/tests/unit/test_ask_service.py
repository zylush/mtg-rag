from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from app.api.auth import AuthenticatedUser
from app.api.services import BurstLimitExceededError, QuotaExceededError
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


def _context() -> CacheContext:
    return CacheContext(
        corpus_versions={"rules": "r1", "cards": "c1", "rulings": "u1"},
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
        generation_model="gpt-5.6-terra",
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
    )


@dataclass
class FakeUsers:
    async def get_or_create(self, user: AuthenticatedUser) -> uuid.UUID:
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

    async def embed_question(self, question: str) -> list[float]:
        self.embed_calls += 1
        return [0.1] * 1536

    async def retrieve_with_embedding(
        self, question: str, embedding: list[float]
    ) -> RetrievalBundle:
        self.retrieve_calls += 1
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
class FakeGeneration:
    calls: int = 0

    async def answer(self, **kwargs: object) -> GenerationOutcome:
        self.calls += 1
        return GenerationOutcome(
            answer=_answer(),
            request_id="resp_1",
            latency_ms=12,
            input_tokens=100,
            output_tokens=30,
            model="gpt-5.6-terra",
            citation_repaired=False,
        )


@dataclass
class FakeCommitter:
    admitted: bool = True
    calls: list[str] = field(default_factory=list)

    async def commit(self, **kwargs: object) -> CommittedExchange | None:
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
    usage: FakeUsage | None = None,
    cache: FakeCache | None = None,
    retrieval: FakeRetrieval | None = None,
    generation: FakeGeneration | None = None,
    committer: FakeCommitter | None = None,
) -> AskApplicationService:
    return AskApplicationService(
        users=FakeUsers(),
        usage=usage or FakeUsage(),
        contexts=FakeContexts(),
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
async def test_atomic_commit_rejection_reports_daily_quota_exhaustion() -> None:
    committer = FakeCommitter(admitted=False)

    with pytest.raises(QuotaExceededError):
        await service(committer=committer).ask(
            user=AuthenticatedUser(firebase_uid="firebase-1", email=None),
            question="What is flying?",
            conversation_id=None,
        )

