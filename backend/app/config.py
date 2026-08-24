from __future__ import annotations

from functools import lru_cache
from typing import Any, Self, cast

from pydantic import HttpUrl, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MTG_RAG_", env_file=".env", extra="ignore", case_sensitive=False
    )

    environment: str = "development"
    database_url: str
    frontend_origin: str
    openai_api_key: SecretStr | None = None
    openai_generation_model: str = "gpt-5.6-luna"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    prompt_version: str = "mtg-answer-v14"
    retrieval_version: str = "rrf-v10"
    semantic_cache_similarity: float = 0.98
    semantic_cache_ttl_days: int = 7
    conversation_context_enabled: bool = False
    conversation_context_max_messages: int = 6
    conversation_context_max_characters: int = 6000
    daily_answer_limit: int = 20
    burst_limit_per_minute: int = 5
    max_question_characters: int = 2000
    request_timeout_seconds: float = 30.0
    max_request_body_bytes: int = 64 * 1024
    max_response_body_bytes: int = 1024 * 1024
    gcp_project_id: str | None = None
    gcs_snapshot_bucket: str | None = None
    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.environment.casefold() in {"prod", "production"}

    @field_validator("frontend_origin")
    @classmethod
    def validate_frontend_origin(cls, value: str) -> str:
        parsed = HttpUrl(value)
        if parsed.scheme != "https" and parsed.host not in {"localhost", "127.0.0.1"}:
            raise ValueError("frontend_origin must use HTTPS outside local development")
        return value.rstrip("/")

    @field_validator("semantic_cache_similarity")
    @classmethod
    def validate_similarity(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("semantic cache similarity must be between 0 and 1")
        return value

    @field_validator(
        "daily_answer_limit",
        "burst_limit_per_minute",
        "max_question_characters",
        "conversation_context_max_messages",
        "conversation_context_max_characters",
        "max_request_body_bytes",
        "max_response_body_bytes",
    )
    @classmethod
    def validate_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("limit must be positive")
        return value

    @field_validator("request_timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeout must be positive")
        return value

    @model_validator(mode="after")
    def validate_production_requirements(self) -> Self:
        if not self.is_production:
            return self

        missing = []
        if self.openai_api_key is None or not self.openai_api_key.get_secret_value().strip():
            missing.append("openai_api_key")
        if not self.gcp_project_id:
            missing.append("gcp_project_id")
        if not self.gcs_snapshot_bucket:
            missing.append("gcs_snapshot_bucket")
        if missing:
            raise ValueError(f"production settings require: {', '.join(missing)}")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Required values are supplied by BaseSettings from MTG_RAG_* environment variables.
    return cast(Settings, cast(Any, Settings)())
