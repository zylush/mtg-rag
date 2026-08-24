from __future__ import annotations

from collections.abc import Callable

from firebase_admin import auth as firebase_auth  # type: ignore[import-untyped]
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.accounts.service import AccountDeletionService
from app.api.auth import FirebaseTokenVerifier
from app.api.services import AppServices, TokenVerifier
from app.ask.context import PostgresConversationContextLoader
from app.ask.repository import PostgresAnswerCommitter
from app.ask.retrieval import AskRetrievalAdapter
from app.ask.service import AskApplicationService
from app.cache.context import PostgresCacheContextProvider
from app.cache.repository import PostgresCacheRepository
from app.config import Settings
from app.feedback.service import SqlFeedbackService
from app.generation.openai_adapter import OpenAIResponsesAdapter
from app.generation.service import GroundedGenerationService
from app.history.repository import SqlConversationService
from app.retrieval.embeddings import OpenAIEmbeddingAdapter
from app.retrieval.repository import PostgresRetrievalRepository
from app.retrieval.service import HybridRetrievalService
from app.usage.repository import PostgresUsageRepository
from app.users.repository import PostgresUserRepository


def build_services(
    *,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    openai_client: AsyncOpenAI,
    auth: TokenVerifier | None = None,
    delete_firebase_user: Callable[[str], object] = firebase_auth.delete_user,
) -> AppServices:
    embedding = OpenAIEmbeddingAdapter(
        client=openai_client,
        model=settings.openai_embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    retrieval_repository = PostgresRetrievalRepository(session_factory)
    hybrid = HybridRetrievalService(
        repository=retrieval_repository,
        embedding=embedding,
    )
    ask_retrieval = AskRetrievalAdapter(embedding=embedding, hybrid=hybrid)
    generation = GroundedGenerationService(
        OpenAIResponsesAdapter(
            client=openai_client,
            model=settings.openai_generation_model,
            prompt_version=settings.prompt_version,
        )
    )
    contexts = PostgresCacheContextProvider(
        session_factory,
        embedding_model=settings.openai_embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
        generation_model=settings.openai_generation_model,
        prompt_version=settings.prompt_version,
        retrieval_version=settings.retrieval_version,
    )
    conversation_contexts = (
        PostgresConversationContextLoader(
            session_factory,
            max_messages=settings.conversation_context_max_messages,
            max_characters=settings.conversation_context_max_characters,
        )
        if settings.conversation_context_enabled
        else None
    )
    ask = AskApplicationService(
        users=PostgresUserRepository(session_factory),
        usage=PostgresUsageRepository(session_factory),
        contexts=contexts,
        conversation_contexts=conversation_contexts,
        cache=PostgresCacheRepository(session_factory),
        retrieval=ask_retrieval,
        generation=generation,
        committer=PostgresAnswerCommitter(session_factory),
        daily_limit=settings.daily_answer_limit,
        burst_limit=settings.burst_limit_per_minute,
        semantic_threshold=settings.semantic_cache_similarity,
        cache_ttl_days=settings.semantic_cache_ttl_days,
    )
    return AppServices(
        auth=auth or FirebaseTokenVerifier(),
        ask=ask,
        conversations=SqlConversationService(session_factory),
        feedback=SqlFeedbackService(session_factory),
        accounts=AccountDeletionService(
            session_factory,
            delete_firebase_user=delete_firebase_user,
        ),
    )
