from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

from app.api.auth import AuthenticatedUser
from app.api.schemas import AskResponse, CitationResponse
from app.api.services import BurstLimitExceededError, QuotaExceededError
from app.cache.policy import (
    CacheContext,
    CacheQuestionProfile,
    cache_fingerprint,
    is_semantic_cache_eligible,
)
from app.cache.repository import CachedAnswer
from app.generation.citations import ResolvedAnswer
from app.generation.openai_adapter import RetrievedPassage
from app.generation.service import GenerationOutcome
from app.retrieval.analysis import analyze_question

logger = logging.getLogger(__name__)
CacheStatus = Literal["exact", "semantic", "miss", "ineligible"]


@dataclass(frozen=True)
class RetrievalBundle:
    embedding: list[float]
    passages: list[RetrievedPassage]


@dataclass(frozen=True)
class CommittedExchange:
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    successful_answers: int


class UserRepository(Protocol):
    async def get_or_create(self, user: AuthenticatedUser) -> uuid.UUID: ...


class UsageRepository(Protocol):
    async def register_ask_attempt(
        self, user_id: uuid.UUID, *, now: datetime, limit: int
    ) -> bool: ...


class ContextProvider(Protocol):
    async def current(self) -> CacheContext: ...


class CacheRepository(Protocol):
    async def get_exact(
        self, *, key: str, context: CacheContext, now: datetime
    ) -> CachedAnswer | None: ...

    async def get_semantic(
        self,
        *,
        question_embedding: list[float],
        context: CacheContext,
        threshold: float,
        now: datetime,
    ) -> CachedAnswer | None: ...

    async def put(self, **kwargs: object) -> str: ...


class RetrievalProvider(Protocol):
    async def embed_question(self, question: str) -> list[float]: ...

    async def retrieve_with_embedding(
        self, question: str, embedding: list[float]
    ) -> RetrievalBundle: ...


class GenerationProvider(Protocol):
    async def answer(
        self,
        *,
        question: str,
        passages: list[RetrievedPassage],
        safety_identifier: str,
    ) -> GenerationOutcome: ...


class AnswerCommitter(Protocol):
    async def commit(self, **kwargs: object) -> CommittedExchange | None: ...


def _base_profile(question: str) -> CacheQuestionProfile:
    analysis = analyze_question(question)
    normalized = analysis.normalized
    kind = "scenario"
    if analysis.rule_references:
        kind = "direct_rule"
    elif normalized.startswith(("what is ", "define ")):
        kind = "definition"
    multiplayer = any(
        token in normalized for token in ("multiplayer", "commander pod", "each opponent")
    )
    ambiguous = kind == "scenario" or any(
        token in normalized for token in ("what happens if", "in response", "at the same time")
    )
    return CacheQuestionProfile(
        kind=kind,
        confidence="high",
        card_count=len(analysis.quoted_card_names),
        multiplayer=multiplayer,
        ambiguous=ambiguous,
    )


def _safety_identifier(firebase_uid: str) -> str:
    return hashlib.sha256(f"mtg-rag:{firebase_uid}".encode()).hexdigest()


def _api_response(
    answer: ResolvedAnswer,
    committed: CommittedExchange,
    *,
    daily_limit: int,
    cache_status: CacheStatus,
) -> AskResponse:
    return AskResponse(
        conversation_id=committed.conversation_id,
        message_id=committed.message_id,
        answer=answer.answer,
        citations=[
            CitationResponse(
                passage_id=citation.passage_id,
                claim=citation.claim,
                label=citation.label,
                url=citation.url,
            )
            for citation in answer.citations
        ],
        assumptions=answer.assumptions,
        confidence=answer.confidence,
        needs_clarification=answer.needs_clarification,
        quota_remaining=max(0, daily_limit - committed.successful_answers),
        cache_status=cache_status,
    )


def _completed_response(
    answer: ResolvedAnswer,
    committed: CommittedExchange,
    *,
    daily_limit: int,
    cache_status: CacheStatus,
    context: CacheContext,
    model_result: GenerationOutcome | None,
) -> AskResponse:
    logger.info(
        "answer_completed",
        extra={
            "conversation_id": str(committed.conversation_id),
            "message_id": str(committed.message_id),
            "cache_status": cache_status,
            "source_versions": dict(sorted(context.corpus_versions.items())),
            "model": model_result.model if model_result is not None else context.generation_model,
            "openai_request_id": (
                model_result.request_id if model_result is not None else None
            ),
            "model_latency_ms": model_result.latency_ms if model_result is not None else 0,
            "input_tokens": model_result.input_tokens if model_result is not None else 0,
            "output_tokens": model_result.output_tokens if model_result is not None else 0,
            "citation_repaired": (
                model_result.citation_repaired if model_result is not None else False
            ),
            "citation_count": len(answer.citations),
        },
    )
    return _api_response(
        answer,
        committed,
        daily_limit=daily_limit,
        cache_status=cache_status,
    )


class AskApplicationService:
    def __init__(
        self,
        *,
        users: UserRepository,
        usage: UsageRepository,
        contexts: ContextProvider,
        cache: CacheRepository,
        retrieval: RetrievalProvider,
        generation: GenerationProvider,
        committer: AnswerCommitter,
        daily_limit: int,
        burst_limit: int,
        semantic_threshold: float,
        cache_ttl_days: int,
    ) -> None:
        self._users = users
        self._usage = usage
        self._contexts = contexts
        self._cache = cache
        self._retrieval = retrieval
        self._generation = generation
        self._committer = committer
        self._daily_limit = daily_limit
        self._burst_limit = burst_limit
        self._semantic_threshold = semantic_threshold
        self._cache_ttl_days = cache_ttl_days

    async def _commit(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        question: str,
        answer: ResolvedAnswer,
        cache_status: CacheStatus,
        model_result: GenerationOutcome | None,
        now: datetime,
    ) -> CommittedExchange:
        committed = await self._committer.commit(
            user_id=user_id,
            conversation_id=conversation_id,
            question=question,
            answer=answer,
            cache_status=cache_status,
            model_result=model_result,
            usage_date=now.date(),
            daily_limit=self._daily_limit,
        )
        if committed is None:
            raise QuotaExceededError
        return committed

    async def ask(
        self,
        *,
        user: AuthenticatedUser,
        question: str,
        conversation_id: uuid.UUID | None,
    ) -> AskResponse:
        now = datetime.now(UTC)
        user_id = await self._users.get_or_create(user)
        if not await self._usage.register_ask_attempt(
            user_id, now=now, limit=self._burst_limit
        ):
            raise BurstLimitExceededError

        context = await self._contexts.current()
        exact_key = cache_fingerprint(question, context)
        exact = await self._cache.get_exact(key=exact_key, context=context, now=now)
        if exact is not None:
            answer = ResolvedAnswer.model_validate(exact.response)
            committed = await self._commit(
                user_id=user_id,
                conversation_id=conversation_id,
                question=question,
                answer=answer,
                cache_status="exact",
                model_result=None,
                now=now,
            )
            return _completed_response(
                answer,
                committed,
                daily_limit=self._daily_limit,
                cache_status="exact",
                context=context,
                model_result=None,
            )

        profile = _base_profile(question)
        question_embedding = await self._retrieval.embed_question(question)
        semantic: CachedAnswer | None = None
        if is_semantic_cache_eligible(profile):
            semantic = await self._cache.get_semantic(
                question_embedding=question_embedding,
                context=context,
                threshold=self._semantic_threshold,
                now=now,
            )
        if semantic is not None:
            answer = ResolvedAnswer.model_validate(semantic.response)
            committed = await self._commit(
                user_id=user_id,
                conversation_id=conversation_id,
                question=question,
                answer=answer,
                cache_status="semantic",
                model_result=None,
                now=now,
            )
            return _completed_response(
                answer,
                committed,
                daily_limit=self._daily_limit,
                cache_status="semantic",
                context=context,
                model_result=None,
            )

        retrieval = await self._retrieval.retrieve_with_embedding(question, question_embedding)
        generated = await self._generation.answer(
            question=question,
            passages=retrieval.passages,
            safety_identifier=_safety_identifier(user.firebase_uid),
        )
        cache_status: CacheStatus = (
            "miss" if is_semantic_cache_eligible(profile) else "ineligible"
        )
        committed = await self._commit(
            user_id=user_id,
            conversation_id=conversation_id,
            question=question,
            answer=generated.answer,
            cache_status=cache_status,
            model_result=generated,
            now=now,
        )

        final_profile = CacheQuestionProfile(
            kind=profile.kind,
            confidence=generated.answer.confidence,
            card_count=profile.card_count,
            multiplayer=profile.multiplayer,
            ambiguous=profile.ambiguous or generated.answer.needs_clarification,
        )
        if is_semantic_cache_eligible(final_profile):
            try:
                await self._cache.put(
                    question=question,
                    question_embedding=retrieval.embedding,
                    response=generated.answer.model_dump(mode="json"),
                    citation_ids=tuple(
                        uuid.UUID(citation.passage_id)
                        for citation in generated.answer.citations
                    ),
                    context=context,
                    created_at=now,
                    expires_at=now + timedelta(days=self._cache_ttl_days),
                )
            except (ValueError, RuntimeError):
                logger.warning("semantic_cache_write_failed", extra={"category": "cache_write"})

        return _completed_response(
            generated.answer,
            committed,
            daily_limit=self._daily_limit,
            cache_status=cache_status,
            context=context,
            model_result=generated,
        )
