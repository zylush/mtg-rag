from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SourceVersion(Base):
    __tablename__ = "source_versions"
    __table_args__ = (
        UniqueConstraint("source_name", "sha256"),
        CheckConstraint("status IN ('staged', 'active', 'inactive', 'failed')", name="valid_status"),
        Index(
            "uq_active_source_version",
            "source_name",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_name: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    effective_date: Mapped[date | None] = mapped_column(Date)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_gcs_uri: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="staged")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="valid_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_name: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_versions.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_category: Mapped[str | None] = mapped_column(String(64))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class RuleSection(Base):
    __tablename__ = "rule_sections"
    __table_args__ = (UniqueConstraint("source_version_id", "rule_number"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_number: Mapped[str] = mapped_column(String(32), nullable=False)
    section_heading: Mapped[str] = mapped_column(Text, nullable=False)
    parent_rule: Mapped[str | None] = mapped_column(String(32))
    previous_rule: Mapped[str | None] = mapped_column(String(32))
    next_rule: Mapped[str | None] = mapped_column(String(32))
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)


class GlossaryEntry(Base):
    __tablename__ = "glossary_entries"
    __table_args__ = (UniqueConstraint("source_version_id", "term"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    term: Mapped[str] = mapped_column(String(255), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)


class Card(Base):
    __tablename__ = "cards"
    __table_args__ = (UniqueConstraint("source_version_id", "oracle_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    oracle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    source_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    representative_printing_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    layout: Mapped[str] = mapped_column(String(64), nullable=False)
    document_text: Mapped[str] = mapped_column(Text, nullable=False)

    faces: Mapped[list[CardFace]] = relationship(back_populates="card", cascade="all, delete-orphan")
    aliases: Mapped[list[CardAlias]] = relationship(
        back_populates="card", cascade="all, delete-orphan"
    )


class CardFace(Base):
    __tablename__ = "card_faces"
    __table_args__ = (UniqueConstraint("card_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    oracle_text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    card: Mapped[Card] = relationship(back_populates="faces")


class CardAlias(Base):
    __tablename__ = "card_aliases"
    __table_args__ = (UniqueConstraint("card_id", "normalized_alias"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    card: Mapped[Card] = relationship(back_populates="aliases")


class Ruling(Base):
    __tablename__ = "rulings"
    __table_args__ = (UniqueConstraint("source_version_id", "oracle_id", "published_at", "comment"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    oracle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    published_at: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    attribution: Mapped[str] = mapped_column(String(64), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)


class Passage(Base):
    __tablename__ = "passages"
    __table_args__ = (
        UniqueConstraint("source_version_id", "document_type", "canonical_key"),
        Index("ix_passages_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_passages_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_key: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    passage_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    search_vector: Mapped[Any] = mapped_column(TSVECTOR, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(1536), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)


class SemanticCacheEntry(Base, TimestampMixin):
    __tablename__ = "semantic_cache_entries"
    __table_args__ = (
        Index(
            "ix_semantic_cache_embedding_hnsw",
            "question_embedding",
            postgresql_using="hnsw",
            postgresql_ops={"question_embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    exact_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    normalized_question: Mapped[str] = mapped_column(Text, nullable=False)
    question_embedding: Mapped[list[float]] = mapped_column(VECTOR(1536), nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    citation_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False)
    corpus_versions: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    generation_model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieval_version: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class ApplicationUser(Base, TimestampMixin):
    __tablename__ = "application_users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    firebase_uid: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(320))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class DailyUsage(Base):
    __tablename__ = "daily_usage"
    __table_args__ = (
        UniqueConstraint("user_id", "usage_date"),
        CheckConstraint("successful_answers >= 0", name="nonnegative_answers"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application_users.id", ondelete="CASCADE"), nullable=False
    )
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    successful_answers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AskAttempt(Base):
    __tablename__ = "ask_attempts"
    __table_args__ = (Index("ix_ask_attempt_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application_users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    user: Mapped[ApplicationUser] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="valid_role"),
        Index("ix_message_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(String(128))
    request_id: Mapped[str | None] = mapped_column(String(128))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_status: Mapped[str | None] = mapped_column(String(32))
    confidence: Mapped[str | None] = mapped_column(String(16))
    needs_clarification: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    citations: Mapped[list[AnswerCitation]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )


class AnswerCitation(Base):
    __tablename__ = "answer_citations"
    __table_args__ = (UniqueConstraint("message_id", "passage_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    passage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("passages.id", ondelete="RESTRICT"), nullable=False
    )
    claim: Mapped[str] = mapped_column(Text, nullable=False)

    message: Mapped[Message] = relationship(back_populates="citations")
    passage: Mapped[Passage] = relationship()


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint("rating IN (-1, 1)", name="valid_rating"),
        UniqueConstraint("user_id", "answer_message_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    answer_message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
