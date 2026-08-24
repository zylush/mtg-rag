from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.schemas import AskResponse, CitationResponse
from app.api.services import (
    ConversationChangedError,
    IdempotencyConflictError,
    RequestInProgressError,
    ResourceNotFoundError,
)
from app.ask.service import CacheStatus, CommittedExchange
from app.db.models import AnswerCitation, AskRequestRecord, Conversation, Message, Passage
from app.generation.citations import ResolvedAnswer
from app.generation.service import GenerationOutcome
from app.usage.repository import build_consume_success_statement


class PostgresAnswerCommitter:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def begin_request(
        self,
        *,
        user_id: uuid.UUID,
        request_id: uuid.UUID,
        request_hash: str,
        claim_token: uuid.UUID,
        now: datetime,
    ) -> AskResponse | None:
        lease_expires_at = now + timedelta(minutes=5)
        async with self._session_factory.begin() as session:
            inserted_id = await session.scalar(
                insert(AskRequestRecord)
                .values(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    client_request_id=request_id,
                    claim_token=claim_token,
                    request_hash=request_hash,
                    status="in_progress",
                    response=None,
                    lease_expires_at=lease_expires_at,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        AskRequestRecord.user_id,
                        AskRequestRecord.client_request_id,
                    ]
                )
                .returning(AskRequestRecord.id)
            )
            if inserted_id is not None:
                return None

            existing = await session.scalar(
                select(AskRequestRecord)
                .where(
                    AskRequestRecord.user_id == user_id,
                    AskRequestRecord.client_request_id == request_id,
                )
                .with_for_update()
            )
            if existing is None:
                raise RuntimeError("idempotency record disappeared during claim")
            if existing.request_hash != request_hash:
                raise IdempotencyConflictError
            if existing.status == "completed":
                if existing.response is None:
                    raise RuntimeError("completed idempotency record has no response")
                return AskResponse.model_validate(existing.response)
            if existing.lease_expires_at <= now:
                existing.claim_token = claim_token
                existing.lease_expires_at = lease_expires_at
                existing.updated_at = now
                return None
            raise RequestInProgressError

    async def release_request(
        self,
        *,
        user_id: uuid.UUID,
        request_id: uuid.UUID,
        request_hash: str,
        claim_token: uuid.UUID,
    ) -> None:
        async with self._session_factory.begin() as session:
            await session.execute(
                delete(AskRequestRecord).where(
                    AskRequestRecord.user_id == user_id,
                    AskRequestRecord.client_request_id == request_id,
                    AskRequestRecord.request_hash == request_hash,
                    AskRequestRecord.claim_token == claim_token,
                    AskRequestRecord.status == "in_progress",
                )
            )

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
    ) -> CommittedExchange | None:
        citation_claims: dict[uuid.UUID, list[str]] = {}
        try:
            for citation in answer.citations:
                passage_id = uuid.UUID(citation.passage_id)
                claims = citation_claims.setdefault(passage_id, [])
                if citation.claim not in claims:
                    claims.append(citation.claim)
        except ValueError as exc:
            raise ValueError("answer contains a non-UUID passage citation") from exc
        citation_ids = list(citation_claims)

        now = datetime.now(UTC)
        async with self._session_factory.begin() as session:
            request_record: AskRequestRecord | None = None
            idempotency_values = (request_id, request_hash, claim_token)
            if any(value is not None for value in idempotency_values):
                if not all(value is not None for value in idempotency_values):
                    raise ValueError("incomplete idempotency commit values")
                request_record = await session.scalar(
                    select(AskRequestRecord)
                    .where(
                        AskRequestRecord.user_id == user_id,
                        AskRequestRecord.client_request_id == request_id,
                    )
                    .with_for_update()
                )
                if request_record is None:
                    raise RequestInProgressError
                if request_record.request_hash != request_hash:
                    raise IdempotencyConflictError
                if (
                    request_record.status != "in_progress"
                    or request_record.claim_token != claim_token
                ):
                    raise RequestInProgressError

            conversation: Conversation | None = None
            if conversation_id is not None:
                conversation = await session.scalar(
                    select(Conversation)
                    .where(
                        Conversation.id == conversation_id,
                        Conversation.user_id == user_id,
                    )
                    .with_for_update()
                )
                if conversation is None:
                    raise ResourceNotFoundError

                if enforce_conversation_tail:
                    current_tail_message_id = await session.scalar(
                        select(Message.id)
                        .where(Message.conversation_id == conversation.id)
                        .order_by(Message.created_at.desc(), Message.id.desc())
                        .limit(1)
                    )
                    if current_tail_message_id != expected_tail_message_id:
                        raise ConversationChangedError

            if citation_ids:
                active_count = int(
                    await session.scalar(
                        select(func.count(Passage.id)).where(
                            Passage.id.in_(citation_ids), Passage.is_active.is_(True)
                        )
                    )
                    or 0
                )
                if active_count != len(citation_ids):
                    raise ValueError("answer citations are not all active")

            usage = await session.execute(
                build_consume_success_statement(
                    user_id=user_id,
                    usage_date=usage_date,
                    daily_limit=daily_limit,
                )
            )
            successful_answers = usage.scalar_one_or_none()
            if successful_answers is None:
                if request_record is not None:
                    await session.delete(request_record)
                return None

            if conversation is None:
                title = " ".join(question.split())[:120] or "MTG rules question"
                conversation = Conversation(user_id=user_id, title=title)
                session.add(conversation)
                await session.flush()
            else:
                conversation.updated_at = now

            user_message = Message(
                conversation_id=conversation.id,
                role="user",
                content=question,
                cache_status=None,
                created_at=now,
            )
            assistant_message = Message(
                conversation_id=conversation.id,
                role="assistant",
                content=answer.answer,
                model=model_result.model if model_result is not None else None,
                request_id=model_result.request_id if model_result is not None else None,
                latency_ms=model_result.latency_ms if model_result is not None else None,
                input_tokens=model_result.input_tokens if model_result is not None else None,
                output_tokens=model_result.output_tokens if model_result is not None else None,
                cache_status=cache_status,
                confidence=answer.confidence,
                needs_clarification=answer.needs_clarification,
                created_at=now + timedelta(microseconds=1),
            )
            session.add_all([user_message, assistant_message])
            await session.flush()
            for passage_id, claims in citation_claims.items():
                session.add(
                    AnswerCitation(
                        message_id=assistant_message.id,
                        passage_id=passage_id,
                        claim=" ".join(claims),
                    )
                )

            if request_record is not None:
                response = AskResponse(
                    conversation_id=conversation.id,
                    message_id=assistant_message.id,
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
                    quota_remaining=max(0, daily_limit - int(successful_answers)),
                    cache_status=cache_status,
                )
                request_record.status = "completed"
                request_record.response = response.model_dump(mode="json")
                request_record.updated_at = now

            return CommittedExchange(
                conversation_id=conversation.id,
                message_id=assistant_message.id,
                successful_answers=int(successful_answers),
            )
