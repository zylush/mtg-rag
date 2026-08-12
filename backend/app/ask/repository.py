from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.services import ResourceNotFoundError
from app.ask.service import CacheStatus, CommittedExchange
from app.db.models import AnswerCitation, Conversation, Message, Passage
from app.generation.citations import ResolvedAnswer
from app.generation.service import GenerationOutcome
from app.usage.repository import build_consume_success_statement


class PostgresAnswerCommitter:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

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
    ) -> CommittedExchange | None:
        citation_ids: list[uuid.UUID] = []
        try:
            citation_ids = [uuid.UUID(citation.passage_id) for citation in answer.citations]
        except ValueError as exc:
            raise ValueError("answer contains a non-UUID passage citation") from exc

        now = datetime.now(UTC)
        async with self._session_factory.begin() as session:
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

            if citation_ids:
                active_count = int(
                    await session.scalar(
                        select(func.count(Passage.id)).where(
                            Passage.id.in_(citation_ids), Passage.is_active.is_(True)
                        )
                    )
                    or 0
                )
                if active_count != len(set(citation_ids)):
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
            for citation, passage_id in zip(answer.citations, citation_ids, strict=True):
                session.add(
                    AnswerCitation(
                        message_id=assistant_message.id,
                        passage_id=passage_id,
                        claim=citation.claim,
                    )
                )

            return CommittedExchange(
                conversation_id=conversation.id,
                message_id=assistant_message.id,
                successful_answers=int(successful_answers),
            )
