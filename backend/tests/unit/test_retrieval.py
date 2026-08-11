from app.retrieval.fusion import RankedPassage, reciprocal_rank_fusion
from app.retrieval.query import normalize_question


def test_question_normalization_is_deterministic_without_destroying_rule_numbers() -> None:
    assert normalize_question("  What DOES Rule 704.5d mean?  ") == "what does rule 704.5d mean?"


def test_rrf_fuses_top_twenty_from_each_path_and_returns_at_most_eight() -> None:
    lexical = [RankedPassage(f"p{i}", rank=i + 1, source="lexical") for i in range(25)]
    vector = [RankedPassage(f"p{i}", rank=i + 1, source="vector") for i in range(10, 35)]

    result = reciprocal_rank_fusion(lexical, vector, limit=8)

    assert len(result) == 8
    assert {item.passage_id for item in result}.issubset({f"p{i}" for i in range(30)})
    assert result == sorted(result, key=lambda item: (-item.score, item.passage_id))


def test_valid_exact_matches_are_pinned_above_approximate_results() -> None:
    lexical = [RankedPassage("approx", rank=1, source="lexical")]
    vector = [RankedPassage("approx", rank=1, source="vector")]
    exact = [RankedPassage("exact", rank=1, source="exact", exact=True)]

    result = reciprocal_rank_fusion(lexical, vector, exact=exact, limit=8)

    assert [item.passage_id for item in result] == ["exact", "approx"]

