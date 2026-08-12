from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evals.harness import (
    CaseResult,
    EvaluationRun,
    EvaluationSuiteError,
    grade_run,
    load_suite,
)

SUITE_PATH = Path(__file__).parents[2] / "evals" / "mtg_rules_v1.json"


def test_versioned_suite_contains_required_coverage_and_review_metadata() -> None:
    suite = load_suite(SUITE_PATH)

    assert suite.version == "mtg-rules-v1"
    assert suite.rules_effective_date == "2026-08-07"
    assert len(suite.cases) >= 100
    assert len(suite.positive_pairs) >= 10
    assert len(suite.negative_pairs) >= 10
    assert suite.review.status in {"pending", "approved"}


def test_a_perfect_completed_run_passes_every_automated_gate() -> None:
    suite = load_suite(SUITE_PATH)
    results = tuple(
        CaseResult(
            case_id=case.case_id,
            retrieved_reference_keys=case.expected_reference_keys,
            citation_reference_keys=(
                case.expected_reference_keys[:1]
                if case.expected_behavior == "answer"
                else ()
            ),
            unknown_citation_ids=(),
            behavior=case.expected_behavior,
            retrieval_latency_ms=100,
            api_latency_ms=200,
            cache_hit=index < 20,
        )
        for index, case in enumerate(suite.cases)
    )

    report = grade_run(
        suite,
        EvaluationRun(
            suite_version=suite.version,
            cases=results,
            semantic_cache_reuse_pair_ids=(),
        ),
        require_expert_review=False,
    )

    assert report.passed
    assert report.retrieval_recall_at_8 == 1
    assert report.citation_identifier_validity == 1
    assert report.citation_precision == 1
    assert report.behavior_accuracy == 1
    assert report.incorrect_negative_pair_reuse == 0


def test_negative_pair_reuse_and_pending_review_block_release() -> None:
    suite = load_suite(SUITE_PATH)
    results = tuple(
        CaseResult(
            case_id=case.case_id,
            retrieved_reference_keys=case.expected_reference_keys,
            citation_reference_keys=case.expected_reference_keys[:1],
            unknown_citation_ids=(),
            behavior=case.expected_behavior,
            retrieval_latency_ms=100,
            api_latency_ms=200,
            cache_hit=True,
        )
        for case in suite.cases
    )

    report = grade_run(
        suite,
        EvaluationRun(
            suite_version=suite.version,
            cases=results,
            semantic_cache_reuse_pair_ids=(suite.negative_pairs[0].pair_id,),
        ),
    )

    assert not report.passed
    assert "expert review is not approved" in report.failures
    assert "semantic-cache negative-pair reuse must be zero" in report.failures


def test_loader_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    payload = {
        "version": "bad",
        "rules_effective_date": "2026-08-07",
        "review": {"status": "pending", "reviewer": None, "reviewed_at": None},
        "cases": [
            {
                "id": "duplicate",
                "category": "exact_rule",
                "question": "Question one?",
                "expected_reference_keys": ["100.1"],
                "expected_behavior": "answer",
            },
            {
                "id": "duplicate",
                "category": "exact_rule",
                "question": "Question two?",
                "expected_reference_keys": ["100.2"],
                "expected_behavior": "answer",
            },
        ],
        "semantic_cache_positive_pairs": [],
        "semantic_cache_negative_pairs": [],
    }
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EvaluationSuiteError, match="duplicate case IDs"):
        load_suite(path, enforce_release_shape=False)
