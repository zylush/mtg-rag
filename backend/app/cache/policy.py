from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Literal

from app.retrieval.query import normalize_question


Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class CacheContext:
    corpus_versions: dict[str, str]
    embedding_model: str
    embedding_dimensions: int
    generation_model: str
    prompt_version: str
    retrieval_version: str
    language: str
    filters: tuple[str, ...]


@dataclass(frozen=True)
class CacheQuestionProfile:
    kind: str
    confidence: Confidence
    card_count: int
    multiplayer: bool = False
    ambiguous: bool = False


@dataclass(frozen=True)
class CacheEntryMetadata:
    context: CacheContext
    citation_ids: tuple[str, ...]
    created_at: datetime
    expires_at: datetime


def cache_fingerprint(question: str, context: CacheContext) -> str:
    payload = {
        "question": normalize_question(question),
        "context": asdict(context),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def is_semantic_cache_eligible(profile: CacheQuestionProfile) -> bool:
    return (
        profile.confidence == "high"
        and profile.kind in {"definition", "direct_rule", "card_text"}
        and profile.card_count <= 1
        and not profile.multiplayer
        and not profile.ambiguous
    )


def is_semantic_hit_reusable(
    entry: CacheEntryMetadata,
    *,
    context: CacheContext,
    active_citation_ids: set[str],
    similarity: float,
    threshold: float,
    now: datetime,
) -> bool:
    if entry.context != context or similarity < threshold:
        return False
    if not set(entry.citation_ids).issubset(active_citation_ids):
        return False
    if not entry.created_at <= now < entry.expires_at:
        return False
    return entry.expires_at - entry.created_at <= timedelta(days=7)

