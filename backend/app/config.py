from __future__ import annotations

from functools import lru_cache

from pydantic import Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MTG_RAG_", env_file=".env", extra="ignore", case_sensitive=False
    )

    environment: str = "development"
    database_url: str
    frontend_origin: str
    openai_api_key: SecretStr | None = None
    openai_generation_model: str = "gpt-5.6-terra"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    prompt_version: str = "mtg-answer-v1"
    retrieval_version: str = "rrf-v1"
    semantic_cache_similarity: float = 0.98
    semantic_cache_ttl_days: int = 7
    daily_answer_limit: int = 20
    burst_limit_per_minute: int = 5
    max_question_characters: int = 2000
    gcp_project_id: str | None = None
    gcs_snapshot_bucket: str | None = None
    log_level: str = "INFO"

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

    @field_validator("daily_answer_limit", "burst_limit_per_minute", "max_question_characters")
    @classmethod
    def validate_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("limit must be positive")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

