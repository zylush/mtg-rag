from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class RankedPassage:
    passage_id: str
    rank: int
    source: str
    exact: bool = False
    protected: bool = False


@dataclass(frozen=True)
class FusedPassage:
    passage_id: str
    score: float
    exact: bool
    protected: bool
    sources: tuple[str, ...]


def reciprocal_rank_fusion(
    lexical: Iterable[RankedPassage],
    vector: Iterable[RankedPassage],
    *,
    exact: Iterable[RankedPassage] = (),
    limit: int = 8,
    candidate_limit: int = 20,
    rank_constant: int = 60,
    exact_pin_limit: int = 4,
    protected_lexical_limit: int = 4,
) -> list[FusedPassage]:
    """Fuse bounded candidates while reserving half the context for multi-path evidence."""
    if exact_pin_limit < 0:
        raise ValueError("exact pin limit must not be negative")
    if protected_lexical_limit < 0:
        raise ValueError("protected lexical limit must not be negative")
    scores: dict[str, float] = {}
    sources: dict[str, set[str]] = {}
    exact_ids: set[str] = set()
    protected_ids: set[str] = set()

    exact_path = tuple(exact)
    lexical_path = tuple(lexical)[:candidate_limit]
    paths = (exact_path, lexical_path, tuple(vector)[:candidate_limit])
    for path in paths:
        for candidate in path:
            if candidate.rank < 1:
                raise ValueError("rank must be positive")
            scores[candidate.passage_id] = scores.get(candidate.passage_id, 0.0) + 1 / (
                rank_constant + candidate.rank
            )
            sources.setdefault(candidate.passage_id, set()).add(candidate.source)
            if candidate.exact or candidate.source == "exact":
                exact_ids.add(candidate.passage_id)
            if candidate.protected:
                protected_ids.add(candidate.passage_id)

    pinned_exact_order = tuple(
        dict.fromkeys(
            candidate.passage_id
            for candidate in exact_path
            if candidate.passage_id in exact_ids
        )
    )[:exact_pin_limit]
    pinned_exact_ids = set(pinned_exact_order)
    protected_lexical_ids = tuple(
        dict.fromkeys(
            candidate.passage_id
            for candidate in lexical_path
            if candidate.protected and candidate.passage_id not in pinned_exact_ids
        )
    )[:protected_lexical_limit]
    priority = {
        passage_id: index
        for index, passage_id in enumerate(
            (*pinned_exact_order, *protected_lexical_ids)
        )
    }

    fused = [
        FusedPassage(
            passage_id=passage_id,
            score=score,
            exact=passage_id in exact_ids,
            protected=passage_id in protected_ids,
            sources=tuple(sorted(sources[passage_id])),
        )
        for passage_id, score in scores.items()
    ]
    fused.sort(
        key=lambda item: (
            priority.get(item.passage_id, len(priority)),
            -item.score,
            item.passage_id,
        )
    )
    return fused[:limit]
