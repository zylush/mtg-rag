from datetime import UTC, datetime, timedelta

from app.cache.policy import (
    CacheContext,
    CacheEntryMetadata,
    CacheQuestionProfile,
    cache_fingerprint,
    is_semantic_cache_eligible,
    is_semantic_hit_reusable,
)


def _context() -> CacheContext:
    return CacheContext(
        corpus_versions={"rules": "r1", "cards": "c1", "rulings": "u1"},
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
        generation_model="gpt-5.6-luna",
        prompt_version="p1",
        retrieval_version="rrf1",
        language="en",
        filters=("paper",),
    )


def test_cache_fingerprint_changes_for_every_versioned_configuration_dimension() -> None:
    original = _context()
    changed = CacheContext(**{**original.__dict__, "prompt_version": "p2"})

    assert cache_fingerprint("What is flying?", original) != cache_fingerprint(
        "What is flying?", changed
    )


def test_only_simple_high_confidence_questions_are_semantically_cacheable() -> None:
    assert is_semantic_cache_eligible(
        CacheQuestionProfile(kind="definition", confidence="high", card_count=0)
    )
    assert not is_semantic_cache_eligible(
        CacheQuestionProfile(kind="scenario", confidence="high", card_count=3)
    )
    assert not is_semantic_cache_eligible(
        CacheQuestionProfile(kind="card_text", confidence="medium", card_count=1)
    )


def test_semantic_hit_requires_matching_context_active_citations_similarity_and_ttl() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    entry = CacheEntryMetadata(
        context=_context(),
        citation_ids=("passage-1",),
        created_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=6),
    )

    assert is_semantic_hit_reusable(
        entry,
        context=_context(),
        active_citation_ids={"passage-1"},
        similarity=0.98,
        threshold=0.98,
        now=now,
    )
    assert not is_semantic_hit_reusable(
        entry,
        context=_context(),
        active_citation_ids=set(),
        similarity=0.999,
        threshold=0.98,
        now=now,
    )
    assert not is_semantic_hit_reusable(
        entry,
        context=_context(),
        active_citation_ids={"passage-1"},
        similarity=0.979,
        threshold=0.98,
        now=now,
    )
