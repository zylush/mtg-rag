from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.accounts.service import AccountDeletionService
from app.api.auth import AuthenticatedUser
from app.api.services import (
    ConversationChangedError,
    IdempotencyConflictError,
    RequestInProgressError,
    ResourceNotFoundError,
)
from app.ask.context import PostgresConversationContextLoader
from app.ask.repository import PostgresAnswerCommitter
from app.config import Settings
from app.db.models import (
    AnswerCitation,
    ApplicationUser,
    AskRequestRecord,
    Conversation,
    DailyUsage,
    Message,
    Passage,
    SourceVersion,
)
from app.feedback.service import SqlFeedbackService
from app.generation.citations import ResolvedAnswer, ResolvedCitation
from app.users.repository import PostgresUserRepository


@pytest.fixture
async def session_factory():  # type: ignore[no-untyped-def]
    engine = create_async_engine(Settings().database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        await session.execute(
            delete(ApplicationUser).where(ApplicationUser.firebase_uid.like("app-test-%"))
        )
        await session.execute(
            delete(SourceVersion).where(SourceVersion.source_name.like("app-test-%"))
        )
    yield factory
    await engine.dispose()


@pytest.fixture
async def active_passage(session_factory):  # type: ignore[no-untyped-def]
    suffix = uuid.uuid4().hex
    version = SourceVersion(
        source_name=f"app-test-{suffix}",
        source_type="rules",
        source_url=f"https://media.wizards.com/{suffix}.txt",
        effective_date=date(2026, 8, 1),
        fetched_at=datetime.now(UTC),
        sha256=suffix.ljust(64, "0"),
        parser_version="1",
        schema_version="1",
        raw_gcs_uri=f"gs://snapshots/{suffix}",
        status="active",
        is_active=True,
        activated_at=datetime.now(UTC),
    )
    async with session_factory.begin() as session:
        session.add(version)
        await session.flush()
        passage = Passage(
            source_version_id=version.id,
            document_type="rule",
            canonical_key="702.9",
            text="Flying restricts blockers.",
            passage_metadata={
                "citation_label": "Comprehensive Rules 702.9",
                "canonical_url": "https://magic.wizards.com/rules#702.9",
            },
            search_vector=func.to_tsvector("english", "Flying restricts blockers."),
            embedding=[0.1, *([0.0] * 1535)],
            is_active=True,
        )
        session.add(passage)
        await session.flush()
    return passage


def _answer(passage_id: uuid.UUID) -> ResolvedAnswer:
    return ResolvedAnswer(
        answer="Flying restricts which creatures can block.",
        citations=[
            ResolvedCitation(
                passage_id=str(passage_id),
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


@pytest.mark.asyncio
@pytest.mark.integration
async def test_user_upsert_is_stable_by_firebase_uid(session_factory) -> None:  # type: ignore[no-untyped-def]
    repository = PostgresUserRepository(session_factory)
    uid = f"app-test-user-{uuid.uuid4().hex}"

    first = await repository.get_or_create(AuthenticatedUser(firebase_uid=uid, email="old@test"))
    second = await repository.get_or_create(AuthenticatedUser(firebase_uid=uid, email="new@test"))

    assert first == second
    async with session_factory() as session:
        email = await session.scalar(
            select(ApplicationUser.email).where(ApplicationUser.id == first)
        )
    assert email == "new@test"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_context_loader_enforces_ownership_and_keeps_latest_six_messages(
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    users = PostgresUserRepository(session_factory)
    owner_uid = f"app-test-owner-{uuid.uuid4().hex}"
    other_uid = f"app-test-other-{uuid.uuid4().hex}"
    owner_id = await users.get_or_create(
        AuthenticatedUser(firebase_uid=owner_uid, email=None)
    )
    await users.get_or_create(
        AuthenticatedUser(firebase_uid=other_uid, email=None)
    )
    conversation = Conversation(user_id=owner_id, title="Bounded context")
    started = datetime.now(UTC)
    async with session_factory.begin() as session:
        session.add(conversation)
        await session.flush()
        session.add_all(
            [
                Message(
                    conversation_id=conversation.id,
                    role="user" if index % 2 == 0 else "assistant",
                    content=f"message-{index}",
                    created_at=started + timedelta(microseconds=index),
                )
                for index in range(8)
            ]
        )
    loader = PostgresConversationContextLoader(
        session_factory,
        max_messages=6,
        max_characters=6_000,
    )

    context = await loader.load(firebase_uid=owner_uid, conversation_id=conversation.id)

    assert [message.content for message in context.messages] == [
        f"message-{index}" for index in range(2, 8)
    ]
    assert context.tail_message_id == context.messages[-1].message_id
    with pytest.raises(ResourceNotFoundError):
        await loader.load(firebase_uid=other_uid, conversation_id=conversation.id)
    with pytest.raises(ResourceNotFoundError):
        await loader.load(firebase_uid=owner_uid, conversation_id=uuid.uuid4())


@pytest.mark.asyncio
@pytest.mark.integration
async def test_answer_commit_atomically_writes_quota_history_and_citations(
    session_factory, active_passage  # type: ignore[no-untyped-def]
) -> None:
    users = PostgresUserRepository(session_factory)
    uid = f"app-test-user-{uuid.uuid4().hex}"
    user_id = await users.get_or_create(AuthenticatedUser(firebase_uid=uid, email=None))
    committer = PostgresAnswerCommitter(session_factory)

    committed = await committer.commit(
        user_id=user_id,
        conversation_id=None,
        question="What is flying?",
        answer=_answer(active_passage.id),
        cache_status="miss",
        model_result=None,
        usage_date=date(2026, 8, 12),
        daily_limit=1,
    )
    rejected = await committer.commit(
        user_id=user_id,
        conversation_id=committed.conversation_id if committed else None,
        question="Again?",
        answer=_answer(active_passage.id),
        cache_status="exact",
        model_result=None,
        usage_date=date(2026, 8, 12),
        daily_limit=1,
    )

    assert committed is not None and committed.successful_answers == 1
    assert rejected is None
    async with session_factory() as session:
        messages = int(
            await session.scalar(
                select(func.count(Message.id)).where(
                    Message.conversation_id == committed.conversation_id
                )
            )
            or 0
        )
        citations = int(await session.scalar(select(func.count(AnswerCitation.id))) or 0)
    assert messages == 2
    assert citations >= 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_answer_request_idempotency_excludes_duplicates_and_replays_one_commit(
    session_factory, active_passage  # type: ignore[no-untyped-def]
) -> None:
    users = PostgresUserRepository(session_factory)
    user_id = await users.get_or_create(
        AuthenticatedUser(
            firebase_uid=f"app-test-idempotency-{uuid.uuid4().hex}",
            email=None,
        )
    )
    committer = PostgresAnswerCommitter(session_factory)
    request_id = uuid.uuid4()
    first_claim = uuid.uuid4()
    replacement_claim = uuid.uuid4()
    request_hash = "a" * 64
    now = datetime.now(UTC)

    assert (
        await committer.begin_request(
            user_id=user_id,
            request_id=request_id,
            request_hash=request_hash,
            claim_token=first_claim,
            now=now,
        )
        is None
    )
    with pytest.raises(RequestInProgressError):
        await committer.begin_request(
            user_id=user_id,
            request_id=request_id,
            request_hash=request_hash,
            claim_token=replacement_claim,
            now=now,
        )
    with pytest.raises(IdempotencyConflictError):
        await committer.begin_request(
            user_id=user_id,
            request_id=request_id,
            request_hash="b" * 64,
            claim_token=replacement_claim,
            now=now,
        )

    await committer.release_request(
        user_id=user_id,
        request_id=request_id,
        request_hash=request_hash,
        claim_token=first_claim,
    )
    assert (
        await committer.begin_request(
            user_id=user_id,
            request_id=request_id,
            request_hash=request_hash,
            claim_token=replacement_claim,
            now=now,
        )
        is None
    )
    committed = await committer.commit(
        user_id=user_id,
        conversation_id=None,
        question="What is flying?",
        answer=_answer(active_passage.id),
        cache_status="miss",
        model_result=None,
        usage_date=date(2026, 8, 24),
        daily_limit=20,
        request_id=request_id,
        request_hash=request_hash,
        claim_token=replacement_claim,
    )
    assert committed is not None

    replay = await committer.begin_request(
        user_id=user_id,
        request_id=request_id,
        request_hash=request_hash,
        claim_token=uuid.uuid4(),
        now=datetime.now(UTC),
    )

    assert replay is not None
    assert replay.conversation_id == committed.conversation_id
    assert replay.message_id == committed.message_id
    assert replay.quota_remaining == 19
    async with session_factory() as session:
        message_count = await session.scalar(
            select(func.count(Message.id)).where(
                Message.conversation_id == committed.conversation_id
            )
        )
        successful_answers = await session.scalar(
            select(DailyUsage.successful_answers).where(
                DailyUsage.user_id == user_id,
                DailyUsage.usage_date == date(2026, 8, 24),
            )
        )
        request_status = await session.scalar(
            select(AskRequestRecord.status).where(
                AskRequestRecord.user_id == user_id,
                AskRequestRecord.client_request_id == request_id,
            )
        )
    assert message_count == 2
    assert successful_answers == 1
    assert request_status == "completed"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_answer_commit_defensively_merges_duplicate_passage_citations(
    session_factory, active_passage  # type: ignore[no-untyped-def]
) -> None:
    users = PostgresUserRepository(session_factory)
    user_id = await users.get_or_create(
        AuthenticatedUser(firebase_uid=f"app-test-duplicate-{uuid.uuid4().hex}", email=None)
    )
    answer = _answer(active_passage.id)
    answer.citations.append(
        ResolvedCitation(
            passage_id=str(active_passage.id),
            claim="Reach is an exception to the flying restriction.",
            label="Comprehensive Rules 702.9",
            url="https://magic.wizards.com/rules#702.9",
        )
    )

    committed = await PostgresAnswerCommitter(session_factory).commit(
        user_id=user_id,
        conversation_id=None,
        question="How does flying interact with reach?",
        answer=answer,
        cache_status="miss",
        model_result=None,
        usage_date=date(2026, 8, 19),
        daily_limit=20,
    )

    assert committed is not None
    async with session_factory() as session:
        citations = (
            await session.execute(
                select(AnswerCitation).where(
                    AnswerCitation.message_id == committed.message_id
                )
            )
        ).scalars().all()
    assert len(citations) == 1
    assert citations[0].claim == (
        "Flying restricts blockers. Reach is an exception to the flying restriction."
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_answer_commit_rejects_foreign_conversation_without_consuming_quota(
    session_factory, active_passage  # type: ignore[no-untyped-def]
) -> None:
    users = PostgresUserRepository(session_factory)
    owner_id = await users.get_or_create(
        AuthenticatedUser(firebase_uid=f"app-test-owner-{uuid.uuid4().hex}", email=None)
    )
    other_id = await users.get_or_create(
        AuthenticatedUser(firebase_uid=f"app-test-other-{uuid.uuid4().hex}", email=None)
    )
    conversation = Conversation(user_id=owner_id, title="Private")
    async with session_factory.begin() as session:
        session.add(conversation)
    committer = PostgresAnswerCommitter(session_factory)

    with pytest.raises(ResourceNotFoundError):
        await committer.commit(
            user_id=other_id,
            conversation_id=conversation.id,
            question="Steal history",
            answer=_answer(active_passage.id),
            cache_status="miss",
            model_result=None,
            usage_date=date(2026, 8, 12),
            daily_limit=20,
        )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_stale_context_tail_cannot_commit_messages_or_quota(
    session_factory, active_passage  # type: ignore[no-untyped-def]
) -> None:
    users = PostgresUserRepository(session_factory)
    firebase_uid = f"app-test-context-{uuid.uuid4().hex}"
    user_id = await users.get_or_create(
        AuthenticatedUser(firebase_uid=firebase_uid, email=None)
    )
    committer = PostgresAnswerCommitter(session_factory)
    first = await committer.commit(
        user_id=user_id,
        conversation_id=None,
        question="My creature has flying.",
        answer=_answer(active_passage.id),
        cache_status="miss",
        model_result=None,
        usage_date=date(2026, 8, 19),
        daily_limit=20,
    )
    assert first is not None
    loader = PostgresConversationContextLoader(
        session_factory,
        max_messages=6,
        max_characters=6_000,
    )
    snapshot = await loader.load(
        firebase_uid=firebase_uid,
        conversation_id=first.conversation_id,
    )

    second = await committer.commit(
        user_id=user_id,
        conversation_id=first.conversation_id,
        question="What if it gains hexproof?",
        answer=_answer(active_passage.id),
        cache_status="ineligible",
        model_result=None,
        usage_date=date(2026, 8, 19),
        daily_limit=20,
        expected_tail_message_id=snapshot.tail_message_id,
        enforce_conversation_tail=True,
    )
    assert second is not None
    with pytest.raises(ConversationChangedError):
        await committer.commit(
            user_id=user_id,
            conversation_id=first.conversation_id,
            question="A stale simultaneous follow-up",
            answer=_answer(active_passage.id),
            cache_status="ineligible",
            model_result=None,
            usage_date=date(2026, 8, 19),
            daily_limit=20,
            expected_tail_message_id=snapshot.tail_message_id,
            enforce_conversation_tail=True,
        )

    async with session_factory() as session:
        message_count = await session.scalar(
            select(func.count(Message.id)).where(
                Message.conversation_id == first.conversation_id
            )
        )
        successful_answers = await session.scalar(
            select(DailyUsage.successful_answers).where(
                DailyUsage.user_id == user_id,
                DailyUsage.usage_date == date(2026, 8, 19),
            )
        )
    assert message_count == 4
    assert successful_answers == 2


@pytest.mark.asyncio
@pytest.mark.integration
async def test_feedback_is_limited_to_owned_assistant_messages(
    session_factory, active_passage  # type: ignore[no-untyped-def]
) -> None:
    users = PostgresUserRepository(session_factory)
    owner_uid = f"app-test-owner-{uuid.uuid4().hex}"
    other_uid = f"app-test-other-{uuid.uuid4().hex}"
    owner_id = await users.get_or_create(AuthenticatedUser(firebase_uid=owner_uid, email=None))
    await users.get_or_create(AuthenticatedUser(firebase_uid=other_uid, email=None))
    committer = PostgresAnswerCommitter(session_factory)
    committed = await committer.commit(
        user_id=owner_id,
        conversation_id=None,
        question="What is flying?",
        answer=_answer(active_passage.id),
        cache_status="miss",
        model_result=None,
        usage_date=date(2026, 8, 12),
        daily_limit=20,
    )
    assert committed is not None
    feedback = SqlFeedbackService(session_factory)

    await feedback.submit(
        user=AuthenticatedUser(firebase_uid=owner_uid, email=None),
        answer_message_id=committed.message_id,
        rating=1,
        comment="Useful",
    )
    with pytest.raises(ResourceNotFoundError):
        await feedback.submit(
            user=AuthenticatedUser(firebase_uid=other_uid, email=None),
            answer_message_id=committed.message_id,
            rating=-1,
            comment=None,
        )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_account_deletion_removes_app_data_then_firebase_identity(session_factory) -> None:  # type: ignore[no-untyped-def]
    users = PostgresUserRepository(session_factory)
    uid = f"app-test-delete-{uuid.uuid4().hex}"
    await users.get_or_create(AuthenticatedUser(firebase_uid=uid, email=None))
    deleted_from_firebase: list[str] = []
    service = AccountDeletionService(
        session_factory,
        delete_firebase_user=lambda firebase_uid: deleted_from_firebase.append(firebase_uid),
    )

    await service.delete(user=AuthenticatedUser(firebase_uid=uid, email=None))

    assert deleted_from_firebase == [uid]
    async with session_factory() as session:
        remaining = await session.scalar(
            select(ApplicationUser.id).where(ApplicationUser.firebase_uid == uid)
        )
    assert remaining is None
