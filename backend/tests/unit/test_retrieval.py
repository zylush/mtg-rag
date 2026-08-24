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


def test_exact_matches_leave_half_the_context_for_multi_path_evidence() -> None:
    exact = [
        RankedPassage(f"exact-{index}", rank=index, source="exact", exact=True)
        for index in range(1, 9)
    ]
    lexical = [
        RankedPassage(f"corroborated-{index}", rank=index, source="lexical")
        for index in range(1, 5)
    ]
    vector = [
        RankedPassage(f"corroborated-{index}", rank=index, source="vector")
        for index in range(1, 5)
    ]

    result = reciprocal_rank_fusion(lexical, vector, exact=exact, limit=8)

    assert [item.passage_id for item in result[:4]] == [
        "exact-1",
        "exact-2",
        "exact-3",
        "exact-4",
    ]
    assert {item.passage_id for item in result[4:]} == {
        "corroborated-1",
        "corroborated-2",
        "corroborated-3",
        "corroborated-4",
    }


def test_protected_anchored_rule_survives_exact_pins_and_multi_path_noise() -> None:
    exact = [
        RankedPassage(f"exact-{index}", rank=index, source="exact", exact=True)
        for index in range(1, 5)
    ]
    lexical = [
        RankedPassage("lexical-1", rank=1, source="lexical"),
        RankedPassage("lexical-2", rank=2, source="lexical"),
        RankedPassage("governing-rule", rank=3, source="lexical", protected=True),
        RankedPassage("lexical-4", rank=4, source="lexical"),
    ]
    vector = [
        RankedPassage(f"vector-{index}", rank=index, source="vector")
        for index in range(1, 9)
    ]

    result = reciprocal_rank_fusion(lexical, vector, exact=exact, limit=8)

    assert "governing-rule" in {item.passage_id for item in result}
    assert next(item for item in result if item.passage_id == "governing-rule").protected
