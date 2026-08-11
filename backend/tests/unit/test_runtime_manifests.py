from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]


def test_local_stack_uses_postgres_pgvector_and_no_redis() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert services["db"]["image"].startswith("pgvector/pgvector:pg16")
    assert "healthcheck" in services["db"]
    assert "api" in services
    assert "ingestion" in services
    assert "redis" not in services
    assert "memorystore" not in services


def test_api_container_is_python_312_and_keeps_openai_key_out_of_image() -> None:
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")

    assert dockerfile.startswith("FROM python:3.12-slim")
    assert "OPENAI_API_KEY" not in dockerfile
    assert "ARG OPENAI" not in dockerfile
    assert "USER app" in dockerfile


def test_example_environment_contains_only_placeholders_and_safe_defaults() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "sk-" not in example
    assert "MTG_RAG_OPENAI_API_KEY=" in example
    assert "MTG_RAG_OPENAI_GENERATION_MODEL=gpt-5.6-terra" in example
    assert "MTG_RAG_EMBEDDING_DIMENSIONS=1536" in example
    assert "MTG_RAG_FRONTEND_ORIGIN=http://localhost:5173" in example


def test_alembic_initial_revision_enables_required_postgres_extensions() -> None:
    revisions = list((ROOT / "backend" / "migrations" / "versions").glob("*.py"))

    assert len(revisions) == 1
    revision = revisions[0].read_text(encoding="utf-8")
    assert 'CREATE EXTENSION IF NOT EXISTS "vector"' in revision
    assert 'CREATE EXTENSION IF NOT EXISTS "pg_trgm"' in revision

