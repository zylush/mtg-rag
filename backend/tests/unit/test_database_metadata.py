from pgvector.sqlalchemy import VECTOR

from app.db.base import Base
from app.db import models  # noqa: F401


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
        "conversations",
        "messages",
        "answer_citations",
        "feedback",
    }.issubset(Base.metadata.tables)


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

