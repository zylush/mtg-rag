from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import uuid
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Protocol

from google.api_core.exceptions import GoogleAPICallError, PreconditionFailed
from google.cloud import storage  # type: ignore[import-untyped]
from google.cloud.storage import Bucket  # type: ignore[import-untyped]
from openai import AsyncOpenAI
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.auth import AuthenticatedUser
from app.api.schemas import AskResponse
from app.ask.context import (
    ConversationContext,
    ConversationContextMessage,
    PostgresConversationContextLoader,
    build_conversation_context,
    render_retrieval_query,
)
from app.ask.repository import PostgresAnswerCommitter
from app.ask.retrieval import AskRetrievalAdapter
from app.ask.service import AskApplicationService, RetrievalBundle
from app.cache.context import PostgresCacheContextProvider
from app.cache.repository import PostgresCacheRepository
from app.config import Settings, get_settings
from app.db.models import (
    ApplicationUser,
    Conversation,
    Message,
    Passage,
    SemanticCacheEntry,
)
from app.db.session import create_engine, create_session_factory
from app.evals.harness import (
    Behavior,
    CaseResult,
    EvalCase,
    EvaluationRun,
    EvaluationSuite,
    EvaluationSuiteError,
    load_suite,
)
from app.generation.citations import normalize_citation_excerpt
from app.generation.openai_adapter import OpenAIResponsesAdapter, RetrievedPassage
from app.generation.service import GenerationOutcome, GroundedGenerationService
from app.retrieval.analysis import QuestionAnalysis
from app.retrieval.embeddings import OpenAIEmbeddingAdapter
from app.retrieval.repository import PostgresRetrievalRepository
from app.retrieval.service import (
    HybridRetrievalService,
    PreparedRetrieval,
    RetrievalCandidate,
    RetrievalRepository,
)
from app.usage.repository import PostgresUsageRepository
from app.users.repository import PostgresUserRepository


@dataclass(frozen=True)
class PassageIdentity:
    document_type: str
    canonical_key: str
    metadata: dict[str, object]
    text: str


class CaseExecutor(Protocol):
    async def execute(self, case: EvalCase) -> CaseResult: ...


@dataclass(frozen=True)
class RetrievalComponentTimings:
    exact_latency_ms: float | None = None
    lexical_latency_ms: float | None = None
    vector_latency_ms: float | None = None


class RetrievalTimingSource(Protocol):
    @property
    def timings(self) -> RetrievalComponentTimings: ...

    def reset(self) -> None: ...


class RecordingRetrievalRepository:
    def __init__(self, base: RetrievalRepository) -> None:
        self._base = base
        self.reset()

    @property
    def timings(self) -> RetrievalComponentTimings:
        return RetrievalComponentTimings(
            exact_latency_ms=self._exact_latency_ms,
            lexical_latency_ms=self._lexical_latency_ms,
            vector_latency_ms=self._vector_latency_ms,
        )

    def reset(self) -> None:
        self._exact_latency_ms: float | None = None
        self._lexical_latency_ms: float | None = None
        self._vector_latency_ms: float | None = None

    async def exact(
        self,
        analysis: QuestionAnalysis,
        *,
        limit: int,
    ) -> Sequence[RetrievalCandidate]:
        started = perf_counter()
        try:
            return await self._base.exact(
                analysis,
                limit=limit,
            )
        finally:
            self._exact_latency_ms = max(0.0, (perf_counter() - started) * 1000)

    async def lexical(
        self, question: str, *, limit: int
    ) -> Sequence[RetrievalCandidate]:
        started = perf_counter()
        try:
            return await self._base.lexical(question, limit=limit)
        finally:
            self._lexical_latency_ms = max(
                0.0, (perf_counter() - started) * 1000
            )

    async def vector(
        self, embedding: list[float], *, limit: int
    ) -> Sequence[RetrievalCandidate]:
        started = perf_counter()
        try:
            return await self._base.vector(embedding, limit=limit)
        finally:
            self._vector_latency_ms = max(
                0.0, (perf_counter() - started) * 1000
            )


@dataclass(frozen=True)
class RetrievalObservation:
    passages: tuple[RetrievedPassage, ...]
    latency_ms: float
    embedding_latency_ms: float
    exact_latency_ms: float | None
    lexical_latency_ms: float | None
    vector_latency_ms: float | None


class BaseRetrieval(Protocol):
    async def embed_question(self, question: str) -> list[float]: ...

    async def prepare_retrieval(self, question: str) -> PreparedRetrieval: ...

    async def retrieve_with_embedding(
        self,
        question: str,
        embedding: list[float],
        *,
        prepared: PreparedRetrieval | asyncio.Task[PreparedRetrieval] | None = None,
    ) -> RetrievalBundle: ...


class BaseGeneration(Protocol):
    async def answer(
        self,
        *,
        question: str,
        passages: list[RetrievedPassage],
        safety_identifier: str,
        conversation: tuple[ConversationContextMessage, ...] = (),
    ) -> GenerationOutcome: ...


class RecordingRetrievalProvider:
    def __init__(
        self,
        base: BaseRetrieval,
        *,
        timing_source: RetrievalTimingSource | None = None,
    ) -> None:
        self._base = base
        self._timing_source = timing_source
        self._started: float | None = None
        self._embedding_latency_ms = 0.0
        self._observation: RetrievalObservation | None = None

    @property
    def observation(self) -> RetrievalObservation | None:
        return self._observation

    def reset(self) -> None:
        self._started = None
        self._embedding_latency_ms = 0.0
        self._observation = None
        if self._timing_source is not None:
            self._timing_source.reset()

    async def embed_question(self, question: str) -> list[float]:
        started = perf_counter()
        if self._started is None:
            self._started = started
        try:
            return await self._base.embed_question(question)
        finally:
            self._embedding_latency_ms = max(
                0.0, (perf_counter() - started) * 1000
            )

    async def prepare_retrieval(self, question: str) -> PreparedRetrieval:
        if self._started is None:
            self._started = perf_counter()
        return await self._base.prepare_retrieval(question)

    async def retrieve_with_embedding(
        self,
        question: str,
        embedding: list[float],
        *,
        prepared: PreparedRetrieval | asyncio.Task[PreparedRetrieval] | None = None,
    ) -> RetrievalBundle:
        started = self._started if self._started is not None else perf_counter()
        bundle = await self._base.retrieve_with_embedding(
            question,
            embedding,
            prepared=prepared,
        )
        timings = (
            self._timing_source.timings
            if self._timing_source is not None
            else RetrievalComponentTimings()
        )
        self._observation = RetrievalObservation(
            passages=tuple(bundle.passages),
            latency_ms=max(0.0, (perf_counter() - started) * 1000),
            embedding_latency_ms=self._embedding_latency_ms,
            exact_latency_ms=timings.exact_latency_ms,
            lexical_latency_ms=timings.lexical_latency_ms,
            vector_latency_ms=timings.vector_latency_ms,
        )
        return bundle

    async def evaluate(self, question: str) -> RetrievalObservation:
        self.reset()
        embedding_task = asyncio.create_task(self.embed_question(question))
        prepared_task = asyncio.create_task(self.prepare_retrieval(question))
        try:
            embedding = await embedding_task
            await self.retrieve_with_embedding(
                question,
                embedding,
                prepared=prepared_task,
            )
        except BaseException:
            embedding_task.cancel()
            prepared_task.cancel()
            await asyncio.gather(
                embedding_task,
                prepared_task,
                return_exceptions=True,
            )
            raise
        if self._observation is None:
            raise RuntimeError("retrieval completed without an observation")
        return self._observation


class RecordingGenerationProvider:
    def __init__(self, base: BaseGeneration) -> None:
        self._base = base
        self._observation: GenerationOutcome | None = None

    @property
    def observation(self) -> GenerationOutcome | None:
        return self._observation

    def reset(self) -> None:
        self._observation = None

    async def answer(
        self,
        *,
        question: str,
        passages: list[RetrievedPassage],
        safety_identifier: str,
        conversation: tuple[ConversationContextMessage, ...] = (),
    ) -> GenerationOutcome:
        self._observation = await self._base.answer(
            question=question,
            passages=passages,
            safety_identifier=safety_identifier,
            conversation=conversation,
        )
        return self._observation


@dataclass(frozen=True)
class SeededConversation:
    conversation_id: uuid.UUID | None
    context: ConversationContext


def evaluation_settings(settings: Settings, *, run_id: uuid.UUID) -> Settings:
    if settings.is_production:
        raise EvaluationSuiteError("evaluation capture refuses production settings")
    suffix = f"-eval-{run_id.hex[:12]}"
    base_version = settings.retrieval_version[: 64 - len(suffix)]
    return settings.model_copy(
        update={
            "conversation_context_enabled": True,
            "daily_answer_limit": max(settings.daily_answer_limit, 1_000),
            "burst_limit_per_minute": max(
                settings.burst_limit_per_minute, 1_000
            ),
            "retrieval_version": f"{base_version}{suffix}",
        }
    )


class AskCaseService(Protocol):
    async def ask(
        self,
        *,
        user: AuthenticatedUser,
        question: str,
        conversation_id: uuid.UUID | None,
    ) -> AskResponse: ...


class ConversationSeeder(Protocol):
    async def seed(
        self, case: EvalCase, *, user: AuthenticatedUser
    ) -> SeededConversation: ...


class ObservedRetrieval(Protocol):
    @property
    def observation(self) -> RetrievalObservation | None: ...

    def reset(self) -> None: ...

    async def evaluate(self, question: str) -> RetrievalObservation: ...


class ObservedGeneration(Protocol):
    @property
    def observation(self) -> GenerationOutcome | None: ...

    def reset(self) -> None: ...


class PassageResolver(Protocol):
    async def resolve(
        self, passage_ids: tuple[str, ...]
    ) -> dict[str, PassageIdentity]: ...


class PostgresEvaluationState:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        max_messages: int,
        max_characters: int,
        retrieval_version: str,
    ) -> None:
        self._session_factory = session_factory
        self._max_messages = max_messages
        self._max_characters = max_characters
        self._retrieval_version = retrieval_version
        self._users = PostgresUserRepository(session_factory)

    async def seed(
        self, case: EvalCase, *, user: AuthenticatedUser
    ) -> SeededConversation:
        if not case.conversation:
            return SeededConversation(
                conversation_id=None,
                context=ConversationContext(messages=(), tail_message_id=None),
            )

        user_id = await self._users.get_or_create(user)
        conversation_id = uuid.uuid4()
        started = datetime.now(UTC)
        context_messages = tuple(
            ConversationContextMessage(
                message_id=uuid.uuid4(),
                role=message.role,
                content=message.content,
            )
            for message in case.conversation
        )
        async with self._session_factory.begin() as session:
            session.add(
                Conversation(
                    id=conversation_id,
                    user_id=user_id,
                    title=f"Evaluation: {case.case_id}"[:255],
                    created_at=started,
                    updated_at=started,
                )
            )
            session.add_all(
                [
                    Message(
                        id=message.message_id,
                        conversation_id=conversation_id,
                        role=message.role,
                        content=message.content,
                        created_at=started + timedelta(microseconds=index),
                    )
                    for index, message in enumerate(context_messages)
                ]
            )

        context = build_conversation_context(
            context_messages,
            tail_message_id=context_messages[-1].message_id,
            max_messages=self._max_messages,
            max_characters=self._max_characters,
        )
        return SeededConversation(conversation_id=conversation_id, context=context)

    async def resolve(
        self, passage_ids: tuple[str, ...]
    ) -> dict[str, PassageIdentity]:
        parsed_ids: list[uuid.UUID] = []
        for passage_id in dict.fromkeys(passage_ids):
            try:
                parsed_ids.append(uuid.UUID(passage_id))
            except ValueError:
                continue
        if not parsed_ids:
            return {}

        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(
                        Passage.id,
                        Passage.document_type,
                        Passage.canonical_key,
                        Passage.passage_metadata,
                        Passage.text,
                    ).where(Passage.id.in_(parsed_ids))
                )
            ).all()
        return {
            str(row.id): PassageIdentity(
                document_type=row.document_type,
                canonical_key=row.canonical_key,
                metadata=dict(row.passage_metadata),
                text=row.text,
            )
            for row in rows
        }

    async def cleanup(self, *, user: AuthenticatedUser) -> None:
        async with self._session_factory.begin() as session:
            await session.execute(
                delete(ApplicationUser).where(
                    ApplicationUser.firebase_uid == user.firebase_uid
                )
            )
            await session.execute(
                delete(SemanticCacheEntry).where(
                    SemanticCacheEntry.retrieval_version == self._retrieval_version
                )
            )


def _behavior(
    response: AskResponse, generation: GenerationOutcome | None = None
) -> Behavior:
    if generation is not None:
        return generation.answer.behavior
    if response.needs_clarification:
        return "clarify"
    if not response.citations:
        return "abstain"
    return "answer"


class StagingCaseExecutor:
    def __init__(
        self,
        *,
        ask: AskCaseService,
        retrieval: ObservedRetrieval,
        generation: ObservedGeneration,
        seeder: ConversationSeeder,
        resolver: PassageResolver,
        user: AuthenticatedUser,
    ) -> None:
        self._ask = ask
        self._retrieval = retrieval
        self._generation = generation
        self._seeder = seeder
        self._resolver = resolver
        self._user = user

    async def execute(self, case: EvalCase) -> CaseResult:
        seeded = await self._seeder.seed(case, user=self._user)
        self._retrieval.reset()
        self._generation.reset()
        started = perf_counter()
        response = await self._ask.ask(
            user=self._user,
            question=case.question,
            conversation_id=seeded.conversation_id,
        )
        api_latency_ms = max(0.0, (perf_counter() - started) * 1000)

        observation = self._retrieval.observation
        if observation is None:
            observation = await self._retrieval.evaluate(
                render_retrieval_query(case.question, seeded.context)
            )
        model_observation = self._generation.observation

        retrieved_ids = tuple(
            passage.passage_id for passage in observation.passages
        )
        citation_ids = tuple(citation.passage_id for citation in response.citations)
        identities = await self._resolver.resolve(
            tuple(dict.fromkeys((*retrieved_ids, *citation_ids)))
        )
        retrieved_keys = tuple(
            reference_key(identities[passage_id])
            for passage_id in retrieved_ids
            if passage_id in identities
        )
        citation_keys = tuple(
            reference_key(identities[passage_id])
            for passage_id in citation_ids
            if passage_id in identities
        )
        unknown_citation_ids = tuple(
            passage_id for passage_id in citation_ids if passage_id not in identities
        )
        unsupported_citation_ids = tuple(
            dict.fromkeys(
                citation.passage_id
                for citation in response.citations
                if citation.passage_id in identities
                and (
                    len(citation.claim) > 320
                    or normalize_citation_excerpt(citation.claim)
                    not in normalize_citation_excerpt(
                        identities[citation.passage_id].text
                    )
                )
            )
        )
        return CaseResult(
            case_id=case.case_id,
            retrieved_reference_keys=retrieved_keys,
            citation_reference_keys=citation_keys,
            unknown_citation_ids=unknown_citation_ids,
            unsupported_citation_ids=unsupported_citation_ids,
            behavior=_behavior(response, model_observation),
            retrieval_latency_ms=observation.latency_ms,
            embedding_latency_ms=observation.embedding_latency_ms,
            exact_latency_ms=observation.exact_latency_ms,
            lexical_latency_ms=observation.lexical_latency_ms,
            vector_latency_ms=observation.vector_latency_ms,
            api_latency_ms=api_latency_ms,
            cache_hit=response.cache_status in {"exact", "semantic"},
            cache_status=response.cache_status,
            confidence=response.confidence,
            answer=response.answer,
            model=(model_observation.model if model_observation is not None else None),
            model_latency_ms=(
                model_observation.latency_ms if model_observation is not None else None
            ),
            input_tokens=(
                model_observation.input_tokens if model_observation is not None else None
            ),
            output_tokens=(
                model_observation.output_tokens if model_observation is not None else None
            ),
            citation_repaired=(
                model_observation.citation_repaired
                if model_observation is not None
                else None
            ),
            initial_model_latency_ms=(
                model_observation.initial_latency_ms
                if model_observation is not None
                else None
            ),
            initial_input_tokens=(
                model_observation.initial_input_tokens
                if model_observation is not None
                else None
            ),
            initial_output_tokens=(
                model_observation.initial_output_tokens
                if model_observation is not None
                else None
            ),
            repair_latency_ms=(
                model_observation.repair_latency_ms
                if model_observation is not None
                else None
            ),
            repair_input_tokens=(
                model_observation.repair_input_tokens
                if model_observation is not None
                else None
            ),
            repair_output_tokens=(
                model_observation.repair_output_tokens
                if model_observation is not None
                else None
            ),
        )


def reference_key(identity: PassageIdentity) -> str:
    if identity.document_type == "rule":
        return identity.canonical_key
    if identity.document_type == "glossary":
        label = identity.metadata.get("citation_label")
        if isinstance(label, str) and ": " in label:
            term = label.rsplit(": ", maxsplit=1)[-1].strip()
        else:
            term = identity.text.partition("\n")[0].strip()
        if not term:
            raise EvaluationSuiteError("glossary passage has no reference term")
        return f"glossary:{term}"
    if identity.document_type == "card":
        card_name = identity.metadata.get("card_name")
        if not isinstance(card_name, str) or not card_name.strip():
            raise EvaluationSuiteError("card passage has no card_name metadata")
        return f"card:{card_name.strip()}"
    return identity.canonical_key


async def capture_suite(
    suite: EvaluationSuite,
    executor: CaseExecutor,
    *,
    progress: Callable[[str], None] | None = None,
) -> EvaluationRun:
    results: list[CaseResult] = []
    for case in suite.cases:
        if progress is not None:
            progress(case.case_id)
        result = await executor.execute(case)
        if result.case_id != case.case_id:
            raise EvaluationSuiteError(
                f"executor returned result for {result.case_id!r} while running {case.case_id!r}"
            )
        results.append(result)

    result_by_id = {result.case_id: result for result in results}
    observed_reuse = tuple(
        pair.pair_id
        for pair in (*suite.positive_pairs, *suite.negative_pairs)
        if result_by_id[pair.second_case_id].cache_hit
    )
    return EvaluationRun(
        suite_version=suite.version,
        cases=tuple(results),
        semantic_cache_reuse_pair_ids=observed_reuse,
    )


def run_payload(run: EvaluationRun) -> dict[str, object]:
    return {
        "suite_version": run.suite_version,
        "cases": [
            {
                "id": result.case_id,
                **{
                    key: value
                    for key, value in asdict(result).items()
                    if key != "case_id"
                },
            }
            for result in run.cases
        ],
        "semantic_cache_reuse_pair_ids": list(
            run.semantic_cache_reuse_pair_ids
        ),
    }


def _run_capture_bytes(run: EvaluationRun) -> bytes:
    return (
        json.dumps(run_payload(run), ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")


def write_run_capture(path: Path, run: EvaluationRun) -> None:
    try:
        with path.open("xb") as output:
            output.write(_run_capture_bytes(run))
    except FileExistsError as exc:
        raise EvaluationSuiteError(
            f"capture output already exists: {path}"
        ) from exc
    except OSError as exc:
        raise EvaluationSuiteError(f"unable to write capture output: {exc}") from exc


def write_run_capture_to_gcs(
    bucket: Bucket,
    *,
    prefix: str,
    run: EvaluationRun,
    run_id: uuid.UUID,
    captured_at: datetime | None = None,
) -> str:
    normalized_prefix = prefix.strip("/")
    prefix_parts = normalized_prefix.split("/")
    if (
        not normalized_prefix
        or normalized_prefix != prefix
        or any(part in {"", ".", ".."} for part in prefix_parts)
    ):
        raise EvaluationSuiteError("GCS capture prefix must be a safe relative path")
    if not run.suite_version or any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        for character in run.suite_version
    ):
        raise EvaluationSuiteError("evaluation suite version is unsafe for a GCS object name")

    timestamp = captured_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise EvaluationSuiteError("GCS capture timestamp must include a timezone")
    object_name = (
        f"{normalized_prefix}/{run.suite_version}/{timestamp.astimezone(UTC):%Y/%m/%d}/"
        f"{run_id}.json"
    )
    payload = _run_capture_bytes(run)
    blob = bucket.blob(object_name)
    blob.cache_control = "no-store"
    blob.metadata = {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "suite_version": run.suite_version,
        "run_id": str(run_id),
    }
    try:
        blob.upload_from_string(
            payload,
            content_type="application/json; charset=utf-8",
            if_generation_match=0,
        )
    except PreconditionFailed as exc:
        raise EvaluationSuiteError(
            f"capture output already exists: gs://{bucket.name}/{object_name}"
        ) from exc
    except GoogleAPICallError as exc:
        raise EvaluationSuiteError("unable to store the GCS capture output") from exc
    return f"gs://{bucket.name}/{object_name}"


def validate_capture_output(path: Path) -> None:
    if path.exists():
        raise EvaluationSuiteError(f"capture output already exists: {path}")
    if not path.parent.is_dir():
        raise EvaluationSuiteError(
            f"capture output directory does not exist: {path.parent}"
        )


def _build_executor(
    *,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    openai_client: AsyncOpenAI,
    user: AuthenticatedUser,
) -> tuple[StagingCaseExecutor, PostgresEvaluationState]:
    embedding = OpenAIEmbeddingAdapter(
        client=openai_client,
        model=settings.openai_embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    repository = RecordingRetrievalRepository(
        PostgresRetrievalRepository(session_factory)
    )
    hybrid = HybridRetrievalService(
        repository=repository,
        embedding=embedding,
    )
    retrieval = RecordingRetrievalProvider(
        AskRetrievalAdapter(embedding=embedding, hybrid=hybrid),
        timing_source=repository,
    )
    generation = RecordingGenerationProvider(
        GroundedGenerationService(
            OpenAIResponsesAdapter(
                client=openai_client,
                model=settings.openai_generation_model,
                prompt_version=settings.prompt_version,
            )
        )
    )
    state = PostgresEvaluationState(
        session_factory,
        max_messages=settings.conversation_context_max_messages,
        max_characters=settings.conversation_context_max_characters,
        retrieval_version=settings.retrieval_version,
    )
    ask = AskApplicationService(
        users=PostgresUserRepository(session_factory),
        usage=PostgresUsageRepository(session_factory),
        contexts=PostgresCacheContextProvider(
            session_factory,
            embedding_model=settings.openai_embedding_model,
            embedding_dimensions=settings.embedding_dimensions,
            generation_model=settings.openai_generation_model,
            prompt_version=settings.prompt_version,
            retrieval_version=settings.retrieval_version,
        ),
        conversation_contexts=PostgresConversationContextLoader(
            session_factory,
            max_messages=settings.conversation_context_max_messages,
            max_characters=settings.conversation_context_max_characters,
        ),
        cache=PostgresCacheRepository(session_factory),
        retrieval=retrieval,
        generation=generation,
        committer=PostgresAnswerCommitter(session_factory),
        daily_limit=settings.daily_answer_limit,
        burst_limit=settings.burst_limit_per_minute,
        semantic_threshold=settings.semantic_cache_similarity,
        cache_ttl_days=settings.semantic_cache_ttl_days,
    )
    return (
        StagingCaseExecutor(
            ask=ask,
            retrieval=retrieval,
            generation=generation,
            seeder=state,
            resolver=state,
            user=user,
        ),
        state,
    )


def _evaluation_openai_client(settings: Settings) -> AsyncOpenAI:
    if settings.openai_api_key is None:
        raise EvaluationSuiteError(
            "MTG_RAG_OPENAI_API_KEY is required for a staging capture"
        )
    return AsyncOpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        timeout=settings.request_timeout_seconds,
        max_retries=0,
    )


async def capture_staging_suite(
    suite: EvaluationSuite,
    *,
    settings: Settings,
    run_id: uuid.UUID | None = None,
    progress: Callable[[str], None] | None = None,
) -> EvaluationRun:
    effective_run_id = run_id or uuid.uuid4()
    configured = evaluation_settings(settings, run_id=effective_run_id)
    if (
        configured.openai_api_key is None
        or not configured.openai_api_key.get_secret_value().strip()
    ):
        raise EvaluationSuiteError(
            "MTG_RAG_OPENAI_API_KEY is required for a staging capture"
        )

    user = AuthenticatedUser(
        firebase_uid=f"eval-runner-{effective_run_id.hex}",
        email=None,
    )
    engine = create_engine(configured.database_url)
    session_factory = create_session_factory(engine)
    openai_client = _evaluation_openai_client(configured)
    executor, state = _build_executor(
        settings=configured,
        session_factory=session_factory,
        openai_client=openai_client,
        user=user,
    )
    capture_error: BaseException | None = None
    try:
        return await capture_suite(suite, executor, progress=progress)
    except BaseException as exc:
        capture_error = exc
        raise
    finally:
        try:
            await state.cleanup(user=user)
        except Exception as cleanup_error:
            if capture_error is None:
                raise
            capture_error.add_note(
                "evaluation cleanup also failed: "
                f"{type(cleanup_error).__name__}"
            )
        finally:
            await openai_client.close()
            await engine.dispose()


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Capture the MTG RAG evaluation suite against non-production services."
    )
    parser.add_argument("--suite", type=Path, required=True)
    output_group = parser.add_mutually_exclusive_group(required=True)
    output_group.add_argument("--output", type=Path)
    output_group.add_argument("--output-gcs-bucket")
    parser.add_argument(
        "--output-gcs-prefix",
        default="evaluation-captures",
        help="Create-only object prefix used with --output-gcs-bucket.",
    )
    parser.add_argument(
        "--confirm-non-production",
        action="store_true",
        required=True,
        help="Confirm that the configured database and model traffic are non-production.",
    )
    args = parser.parse_args(argv)

    try:
        if args.output is not None:
            validate_capture_output(args.output)
        suite = load_suite(args.suite)
        run_id = uuid.uuid4()
        run = asyncio.run(
            capture_staging_suite(
                suite,
                settings=get_settings(),
                run_id=run_id,
                progress=lambda case_id: print(
                    f"capturing {case_id}", flush=True
                ),
            )
        )
        if args.output is not None:
            write_run_capture(args.output, run)
            destination = str(args.output)
        else:
            bucket = storage.Client().bucket(args.output_gcs_bucket)
            destination = write_run_capture_to_gcs(
                bucket,
                prefix=args.output_gcs_prefix,
                run=run,
                run_id=run_id,
            )
    except EvaluationSuiteError as exc:
        parser.error(str(exc))
    print(f"capture written: {destination}")
