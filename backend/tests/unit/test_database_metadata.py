from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB

from app.db import models  # noqa: F401
from app.db.base import Base


def test_schema_contains_every_core_entity_from_the_plan() -> None:
    assert {
        "source_versions",
        "ingestion_runs",
        "rule_sections",
        "glossary_entries",
        "cards",
        "card_faces",
        "card_aliases",
        "rulings",
        "passages",
        "semantic_cache_entries",
        "application_users",
        "daily_usage",
        "ask_attempts",
        "ask_requests",
        "conversations",
        "messages",
        "answer_citations",
        "feedback",
    }.issubset(Base.metadata.tables)


def test_ask_request_keys_are_unique_per_user_and_cascade_with_account_deletion() -> None:
    ask_requests = Base.metadata.tables["ask_requests"]
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in ask_requests.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert ("user_id", "client_request_id") in unique_columns
    user_foreign_key = next(iter(ask_requests.c.user_id.foreign_keys))
    assert user_foreign_key.target_fullname == "application_users.id"
    assert user_foreign_key.ondelete == "CASCADE"


def test_in_progress_ask_request_response_none_binds_as_sql_null() -> None:
    response_type = Base.metadata.tables["ask_requests"].c.response.type
    bind_processor = response_type.bind_processor(postgresql.dialect())

    assert isinstance(response_type, JSONB)
    assert response_type.none_as_null is True
    assert bind_processor is not None
    assert bind_processor(None) is None


def test_passage_embeddings_are_pinned_to_1536_dimensions() -> None:
    embedding_type = Base.metadata.tables["passages"].c.embedding.type

    assert isinstance(embedding_type, VECTOR)
    assert embedding_type.dim == 1536


def test_user_owned_records_have_backend_enforceable_foreign_keys() -> None:
    tables = Base.metadata.tables

    assert next(iter(tables["conversations"].c.user_id.foreign_keys)).target_fullname == (
        "application_users.id"
    )
    assert next(iter(tables["feedback"].c.user_id.foreign_keys)).target_fullname == (
        "application_users.id"
    )
    assert tables["application_users"].c.firebase_uid.unique is True


def test_source_activation_has_only_one_active_version_per_source() -> None:
    indexes = Base.metadata.tables["source_versions"].indexes
    active_indexes = [index for index in indexes if index.name == "uq_active_source_version"]

    assert len(active_indexes) == 1
    assert active_indexes[0].unique is True
    assert str(active_indexes[0].dialect_options["postgresql"]["where"]) == "is_active"


def test_card_identity_is_version_scoped_so_previous_corpora_remain_rollbackable() -> None:
    cards = Base.metadata.tables["cards"]
    card_faces = Base.metadata.tables["card_faces"]
    card_aliases = Base.metadata.tables["card_aliases"]

    assert [column.name for column in cards.primary_key.columns] == ["id"]
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in cards.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("source_version_id", "oracle_id") in unique_columns
    assert next(iter(card_faces.c.card_id.foreign_keys)).target_fullname == "cards.id"
    assert next(iter(card_aliases.c.card_id.foreign_keys)).target_fullname == "cards.id"
