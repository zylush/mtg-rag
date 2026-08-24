from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.auth import AuthenticatedUser
from app.config import Settings
from app.db.models import ApplicationUser, Passage, SemanticCacheEntry, SourceVersion
from app.evals.harness import EvalCase, EvalConversationMessage
from app.evals.runner import PostgresEvaluationState


@pytest.fixture
async def session_factory():  # type: ignore[no-untyped-def]
    engine = create_async_engine(Settings().database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        await session.execute(
            delete(ApplicationUser).where(
                ApplicationUser.firebase_uid.like("eval-runner-test-%")
            )
        )
        await session.execute(
            delete(SemanticCacheEntry).where(
                SemanticCacheEntry.retrieval_version.like("eval-runner-test-%")
            )
        )
        await session.execute(
            delete(SourceVersion).where(
                SourceVersion.source_name.like("eval-runner-test-%")
            )
        )
    yield factory
    async with factory.begin() as session:
        await session.execute(
            delete(ApplicationUser).where(
                ApplicationUser.firebase_uid.like("eval-runner-test-%")
            )
        )
        await session.execute(
            delete(SemanticCacheEntry).where(
                SemanticCacheEntry.retrieval_version.like("eval-runner-test-%")
            )
        )
        await session.execute(
            delete(SourceVersion).where(
                SourceVersion.source_name.like("eval-runner-test-%")
            )
        )
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_eval_runner_postgres_state_seeds_resolves_and_cleans_up(
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    suffix = uuid.uuid4().hex
    firebase_uid = f"eval-runner-test-user-{suffix}"
    retrieval_version = f"eval-runner-test-{suffix}"
    now = datetime.now(UTC)
    version = SourceVersion(
        source_name=f"eval-runner-test-source-{suffix}",
        source_type="rules",
        source_url=f"https://media.wizards.com/{suffix}.txt",
        effective_date=date(2026, 8, 1),
        fetched_at=now,
        sha256=suffix.ljust(64, "0"),
        parser_version="1",
        schema_version="1",
        raw_gcs_uri=f"gs://snapshots/{suffix}",
        status="active",
        is_active=True,
        activated_at=now,
    )
    async with session_factory.begin() as session:
        session.add(version)
        await session.flush()
        passage = Passage(
            source_version_id=version.id,
            document_type="rule",
            canonical_key="702.9",
            text="702.9. Flying restricts blockers.",
            passage_metadata={"citation_label": "Comprehensive Rules 702.9"},
            search_vector=func.to_tsvector("english", "Flying restricts blockers."),
            embedding=[0.1, *([0.0] * 1535)],
            is_active=True,
        )
        session.add(passage)
        session.add(
            SemanticCacheEntry(
                exact_key=(suffix * 2)[:64],
                normalized_question="evaluation cleanup",
                question_embedding=[0.0] * 1536,
                response={"answer": "test"},
                citation_ids=[],
                corpus_versions={},
                embedding_model="test",
                embedding_dimensions=1536,
                generation_model="test",
                prompt_version="test",
                retrieval_version=retrieval_version,
                language="en",
                filters=[],
                expires_at=now + timedelta(days=1),
            )
        )
        await session.flush()
        passage_id = passage.id

    state = PostgresEvaluationState(
        session_factory,
        max_messages=6,
        max_characters=6_000,
        retrieval_version=retrieval_version,
    )
    user = AuthenticatedUser(firebase_uid=firebase_uid, email=None)
    case = EvalCase(
        case_id="follow-up",
        category="follow_up_context",
        question="Can reach block it?",
        expected_reference_keys=("702.9",),
        expected_behavior="answer",
        conversation=(
            EvalConversationMessage(role="user", content="My attacker has flying."),
            EvalConversationMessage(
                role="assistant", content="Only creatures with flying or reach can block it."
            ),
        ),
    )

    seeded = await state.seed(case, user=user)
    identities = await state.resolve((str(passage_id), "not-a-uuid"))

    assert seeded.conversation_id is not None
    assert [message.content for message in seeded.context.messages] == [
        "My attacker has flying.",
        "Only creatures with flying or reach can block it.",
    ]
    assert seeded.context.tail_message_id == seeded.context.messages[-1].message_id
    assert identities[str(passage_id)].canonical_key == "702.9"

    await state.cleanup(user=user)

    async with session_factory() as session:
        remaining_user = await session.scalar(
            select(ApplicationUser.id).where(
                ApplicationUser.firebase_uid == firebase_uid
            )
        )
        remaining_cache = await session.scalar(
            select(func.count(SemanticCacheEntry.id)).where(
                SemanticCacheEntry.retrieval_version == retrieval_version
            )
        )
    assert remaining_user is None
    assert remaining_cache == 0
