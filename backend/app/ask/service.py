from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, Protocol

from app.api.auth import AuthenticatedUser
from app.api.schemas import AskResponse, CitationResponse
from app.api.services import BurstLimitExceededError, QuotaExceededError
from app.ask.context import (
    ConversationContext,
    ConversationContextMessage,
    render_retrieval_query,
)
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
from app.retrieval.service import PreparedRetrieval

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


class ConversationContextLoader(Protocol):
    async def load(
        self, *, firebase_uid: str, conversation_id: uuid.UUID
    ) -> ConversationContext: ...


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

    async def put(
        self,
        *,
        question: str,
        question_embedding: list[float],
        response: dict[str, Any],
        citation_ids: tuple[uuid.UUID, ...],
        context: CacheContext,
        created_at: datetime,
        expires_at: datetime,
    ) -> str: ...


class RetrievalProvider(Protocol):
    async def embed_question(self, question: str) -> list[float]: ...

    async def prepare_retrieval(self, question: str) -> PreparedRetrieval: ...

    async def retrieve_with_embedding(
        self,
        question: str,
        embedding: list[float],
        *,
        prepared: PreparedRetrieval | asyncio.Task[PreparedRetrieval] | None = None,
    ) -> RetrievalBundle: ...


async def _cancel_prepared_retrieval(
    task: asyncio.Task[PreparedRetrieval],
) -> None:
    if task.done():
        with suppress(asyncio.CancelledError, Exception):
            task.result()
        return
    task.cancel()
    with suppress(asyncio.CancelledError, Exception):
        await task


class GenerationProvider(Protocol):
    async def answer(
        self,
        *,
        question: str,
        passages: list[RetrievedPassage],
        safety_identifier: str,
        conversation: tuple[ConversationContextMessage, ...] = (),
    ) -> GenerationOutcome: ...


class AnswerCommitter(Protocol):
    async def begin_request(
        self,
        *,
        user_id: uuid.UUID,
        request_id: uuid.UUID,
        request_hash: str,
        claim_token: uuid.UUID,
        now: datetime,
    ) -> AskResponse | None: ...

    async def release_request(
        self,
        *,
        user_id: uuid.UUID,
        request_id: uuid.UUID,
        request_hash: str,
        claim_token: uuid.UUID,
    ) -> None: ...

    async def commit(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        question: str,
        answer: ResolvedAnswer,
        cache_status: CacheStatus,
        model_result: GenerationOutcome | None,
        usage_date: date,
        daily_limit: int,
        request_id: uuid.UUID | None = None,
        request_hash: str | None = None,
        claim_token: uuid.UUID | None = None,
        expected_tail_message_id: uuid.UUID | None = None,
        enforce_conversation_tail: bool = False,
    ) -> CommittedExchange | None: ...


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


def _request_fingerprint(question: str, conversation_id: uuid.UUID | None) -> str:
    conversation = str(conversation_id) if conversation_id is not None else ""
    return hashlib.sha256(f"{conversation}\x1e{question}".encode()).hexdigest()


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
    conversation_context: ConversationContext | None,
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
            "initial_model_latency_ms": (
                model_result.initial_latency_ms if model_result is not None else None
            ),
            "initial_input_tokens": (
                model_result.initial_input_tokens if model_result is not None else None
            ),
            "initial_output_tokens": (
                model_result.initial_output_tokens if model_result is not None else None
            ),
            "repair_latency_ms": (
                model_result.repair_latency_ms if model_result is not None else None
            ),
            "repair_input_tokens": (
                model_result.repair_input_tokens if model_result is not None else None
            ),
            "repair_output_tokens": (
                model_result.repair_output_tokens if model_result is not None else None
            ),
            "citation_count": len(answer.citations),
            "context_message_count": (
                len(conversation_context.messages)
                if conversation_context is not None
                else 0
            ),
            "context_truncated": (
                conversation_context.truncated
                if conversation_context is not None
                else False
            ),
        },
    )
    return _api_response(
        answer,
        committed,
        daily_limit=daily_limit,
        cache_status=cache_status,
    )


def _ephemeral_exchange() -> CommittedExchange:
    """Return identifiers for a public answer that is not saved to account history."""
    return CommittedExchange(
        conversation_id=uuid.uuid4(),
        message_id=uuid.uuid4(),
        successful_answers=0,
    )


class AskApplicationService:
    def __init__(
        self,
        *,
        users: UserRepository,
        usage: UsageRepository,
        contexts: ContextProvider,
        conversation_contexts: ConversationContextLoader | None,
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
        self._conversation_contexts = conversation_contexts
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
        conversation_context: ConversationContext | None,
        request_id: uuid.UUID | None,
        request_hash: str | None,
        claim_token: uuid.UUID | None,
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
            request_id=request_id,
            request_hash=request_hash,
            claim_token=claim_token,
            expected_tail_message_id=(
                conversation_context.tail_message_id
                if conversation_context is not None
                else None
            ),
            enforce_conversation_tail=conversation_context is not None,
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
        request_id: uuid.UUID | None = None,
    ) -> AskResponse:
        now = datetime.now(UTC)
        conversation_context: ConversationContext | None = None
        if conversation_id is not None and self._conversation_contexts is not None:
            conversation_context = await self._conversation_contexts.load(
                firebase_uid=user.firebase_uid,
                conversation_id=conversation_id,
            )
        user_id = await self._users.get_or_create(user)
        if request_id is None:
            return await self._execute_authenticated(
                user=user,
                user_id=user_id,
                question=question,
                conversation_id=conversation_id,
                conversation_context=conversation_context,
                now=now,
                request_id=None,
                request_hash=None,
                claim_token=None,
            )

        request_hash = _request_fingerprint(question, conversation_id)
        claim_token = uuid.uuid4()
        replay = await self._committer.begin_request(
            user_id=user_id,
            request_id=request_id,
            request_hash=request_hash,
            claim_token=claim_token,
            now=now,
        )
        if replay is not None:
            logger.info(
                "answer_idempotency_replay",
                extra={"request_id": str(request_id)},
            )
            return replay

        try:
            return await self._execute_authenticated(
                user=user,
                user_id=user_id,
                question=question,
                conversation_id=conversation_id,
                conversation_context=conversation_context,
                now=now,
                request_id=request_id,
                request_hash=request_hash,
                claim_token=claim_token,
            )
        except BaseException:
            cleanup = asyncio.create_task(
                self._committer.release_request(
                    user_id=user_id,
                    request_id=request_id,
                    request_hash=request_hash,
                    claim_token=claim_token,
                )
            )
            with suppress(asyncio.CancelledError, Exception):
                await asyncio.shield(cleanup)
            raise

    async def _execute_authenticated(
        self,
        *,
        user: AuthenticatedUser,
        user_id: uuid.UUID,
        question: str,
        conversation_id: uuid.UUID | None,
        conversation_context: ConversationContext | None,
        now: datetime,
        request_id: uuid.UUID | None,
        request_hash: str | None,
        claim_token: uuid.UUID | None,
    ) -> AskResponse:
        if not await self._usage.register_ask_attempt(
            user_id, now=now, limit=self._burst_limit
        ):
            raise BurstLimitExceededError
        contextual = bool(
            conversation_context is not None and conversation_context.messages
        )
        retrieval_question = (
            render_retrieval_query(question, conversation_context)
            if contextual and conversation_context is not None
            else question
        )

        context = await self._contexts.current()
        exact: CachedAnswer | None = None
        if not contextual:
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
                conversation_context=conversation_context,
                request_id=request_id,
                request_hash=request_hash,
                claim_token=claim_token,
            )
            return _completed_response(
                answer,
                committed,
                daily_limit=self._daily_limit,
                cache_status="exact",
                context=context,
                model_result=None,
                conversation_context=conversation_context,
            )

        profile = _base_profile(retrieval_question)
        prepared_task = asyncio.create_task(
            self._retrieval.prepare_retrieval(retrieval_question)
        )
        try:
            question_embedding = await self._retrieval.embed_question(retrieval_question)
            semantic: CachedAnswer | None = None
            if not contextual and is_semantic_cache_eligible(profile):
                semantic = await self._cache.get_semantic(
                    question_embedding=question_embedding,
                    context=context,
                    threshold=self._semantic_threshold,
                    now=now,
                )
        except BaseException:
            await _cancel_prepared_retrieval(prepared_task)
            raise
        if semantic is not None:
            await _cancel_prepared_retrieval(prepared_task)
            answer = ResolvedAnswer.model_validate(semantic.response)
            committed = await self._commit(
                user_id=user_id,
                conversation_id=conversation_id,
                question=question,
                answer=answer,
                cache_status="semantic",
                model_result=None,
                now=now,
                conversation_context=conversation_context,
                request_id=request_id,
                request_hash=request_hash,
                claim_token=claim_token,
            )
            return _completed_response(
                answer,
                committed,
                daily_limit=self._daily_limit,
                cache_status="semantic",
                context=context,
                model_result=None,
                conversation_context=conversation_context,
            )

        retrieval = await self._retrieval.retrieve_with_embedding(
            retrieval_question,
            question_embedding,
            prepared=prepared_task,
        )
        generated = await self._generation.answer(
            question=question,
            passages=retrieval.passages,
            safety_identifier=_safety_identifier(user.firebase_uid),
            conversation=(
                conversation_context.messages
                if conversation_context is not None
                else ()
            ),
        )
        final_profile = CacheQuestionProfile(
            kind=profile.kind,
            confidence=generated.answer.confidence,
            card_count=profile.card_count,
            multiplayer=profile.multiplayer,
            ambiguous=(
                profile.ambiguous
                or generated.answer.needs_clarification
                or generated.answer.behavior != "answer"
            ),
        )
        final_cache_eligible = (
            not contextual and is_semantic_cache_eligible(final_profile)
        )
        cache_status: CacheStatus = "miss" if final_cache_eligible else "ineligible"
        committed = await self._commit(
            user_id=user_id,
            conversation_id=conversation_id,
            question=question,
            answer=generated.answer,
            cache_status=cache_status,
            model_result=generated,
            now=now,
            conversation_context=conversation_context,
            request_id=request_id,
            request_hash=request_hash,
            claim_token=claim_token,
        )

        if final_cache_eligible:
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
            conversation_context=conversation_context,
        )

    async def ask_public(self, *, question: str, client_key: str) -> AskResponse:
        """Answer a free public question without creating an account or history row.

        Public questions may still populate the shared semantic cache when they meet the
        same confidence and ambiguity rules as authenticated questions. The API boundary
        supplies a bounded client key for abuse control; the key is never sent to the model
        in raw form.
        """
        now = datetime.now(UTC)
        context = await self._contexts.current()
        exact_key = cache_fingerprint(question, context)
        exact = await self._cache.get_exact(key=exact_key, context=context, now=now)
        if exact is not None:
            answer = ResolvedAnswer.model_validate(exact.response)
            return _completed_response(
                answer,
                _ephemeral_exchange(),
                daily_limit=0,
                cache_status="exact",
                context=context,
                model_result=None,
                conversation_context=None,
            )

        profile = _base_profile(question)
        prepared_task = asyncio.create_task(self._retrieval.prepare_retrieval(question))
        try:
            question_embedding = await self._retrieval.embed_question(question)
            semantic: CachedAnswer | None = None
            if is_semantic_cache_eligible(profile):
                semantic = await self._cache.get_semantic(
                    question_embedding=question_embedding,
                    context=context,
                    threshold=self._semantic_threshold,
                    now=now,
                )
        except BaseException:
            await _cancel_prepared_retrieval(prepared_task)
            raise

        if semantic is not None:
            await _cancel_prepared_retrieval(prepared_task)
            answer = ResolvedAnswer.model_validate(semantic.response)
            return _completed_response(
                answer,
                _ephemeral_exchange(),
                daily_limit=0,
                cache_status="semantic",
                context=context,
                model_result=None,
                conversation_context=None,
            )

        retrieval = await self._retrieval.retrieve_with_embedding(
            question,
            question_embedding,
            prepared=prepared_task,
        )
        generated = await self._generation.answer(
            question=question,
            passages=retrieval.passages,
            safety_identifier=_safety_identifier(f"public:{client_key}"),
        )
        final_profile = CacheQuestionProfile(
            kind=profile.kind,
            confidence=generated.answer.confidence,
            card_count=profile.card_count,
            multiplayer=profile.multiplayer,
            ambiguous=(
                profile.ambiguous
                or generated.answer.needs_clarification
                or generated.answer.behavior != "answer"
            ),
        )
        final_cache_eligible = is_semantic_cache_eligible(final_profile)
        cache_status: CacheStatus = "miss" if final_cache_eligible else "ineligible"
        if final_cache_eligible:
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
                logger.warning(
                    "public_semantic_cache_write_failed",
                    extra={"category": "cache_write"},
                )

        return _completed_response(
            generated.answer,
            _ephemeral_exchange(),
            daily_limit=0,
            cache_status=cache_status,
            context=context,
            model_result=generated,
            conversation_context=None,
        )
