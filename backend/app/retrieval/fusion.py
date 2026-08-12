from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class RankedPassage:
    passage_id: str
    rank: int
    source: str
    exact: bool = False


@dataclass(frozen=True)
class FusedPassage:
    passage_id: str
    score: float
    exact: bool
    sources: tuple[str, ...]


def reciprocal_rank_fusion(
    lexical: Iterable[RankedPassage],
    vector: Iterable[RankedPassage],
    *,
    exact: Iterable[RankedPassage] = (),
    limit: int = 8,
    candidate_limit: int = 20,
    rank_constant: int = 60,
) -> list[FusedPassage]:
    """Fuse bounded candidates and pin validated exact matches before approximations."""
    scores: dict[str, float] = {}
    sources: dict[str, set[str]] = {}
    exact_ids: set[str] = set()

    paths = (tuple(exact), tuple(lexical)[:candidate_limit], tuple(vector)[:candidate_limit])
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

    fused = [
        FusedPassage(
            passage_id=passage_id,
            score=score,
            exact=passage_id in exact_ids,
            sources=tuple(sorted(sources[passage_id])),
        )
        for passage_id, score in scores.items()
    ]
    fused.sort(key=lambda item: (not item.exact, -item.score, item.passage_id))
    return fused[:limit]

