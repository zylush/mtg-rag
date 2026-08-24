import pytest
from pydantic import ValidationError

from app.config import Settings


def test_default_generation_model_is_luna() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://mtg:mtg@localhost:5432/mtg",
        frontend_origin="http://localhost:5173",
    )

    assert settings.openai_generation_model == "gpt-5.6-luna"
    assert settings.prompt_version == "mtg-answer-v14"
    assert settings.retrieval_version == "rrf-v10"


def test_conversation_context_defaults_and_limits_are_validated() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://mtg:mtg@localhost:5432/mtg",
        frontend_origin="http://localhost:5173",
    )

    assert settings.conversation_context_enabled is False
    assert settings.conversation_context_max_messages == 6
    assert settings.conversation_context_max_characters == 6_000
    with pytest.raises(ValidationError, match="limit must be positive"):
        Settings(
            database_url="postgresql+asyncpg://mtg:mtg@localhost:5432/mtg",
            frontend_origin="http://localhost:5173",
            conversation_context_max_messages=0,
        )


def test_prod_alias_requires_secret_and_cloud_runtime_settings() -> None:
    with pytest.raises(ValidationError, match="production settings require"):
        Settings(
            environment="prod",
            database_url="postgresql+asyncpg://mtg:mtg@localhost:5432/mtg",
            frontend_origin="https://rules.example.com",
        )


def test_complete_prod_settings_are_recognized_as_production() -> None:
    settings = Settings(
        environment="prod",
        database_url="postgresql+asyncpg://mtg:mtg@localhost:5432/mtg",
        frontend_origin="https://rules.example.com",
        openai_api_key="test-placeholder",
        gcp_project_id="mtg-production",
        gcs_snapshot_bucket="mtg-production-snapshots",
    )

    assert settings.is_production
