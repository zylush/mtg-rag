from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.evals.harness import (
    CaseResult,
    EvaluationRun,
    EvaluationSuiteError,
    Review,
    grade_run,
    load_run,
    load_suite,
    reference_key_matches,
)

SUITE_PATH = Path(__file__).parents[2] / "evals" / "mtg_rules_v1.json"


def test_v11_run_loader_requires_explicit_excerpt_validation_evidence(
    tmp_path: Path,
) -> None:
    run_path = tmp_path / "run.json"
    case = {
        "id": "case-1",
        "retrieved_reference_keys": ["100.1"],
        "citation_reference_keys": ["100.1"],
        "unknown_citation_ids": [],
        "unsupported_citation_ids": [],
        "behavior": "answer",
        "retrieval_latency_ms": 100,
        "api_latency_ms": 200,
        "cache_hit": False,
        "cache_status": "miss",
        "confidence": "high",
    }
    run = {
        "suite_version": "mtg-rules-v1",
        "cases": [case],
        "semantic_cache_reuse_pair_ids": [],
    }
    run_path.write_text(json.dumps(run), encoding="utf-8")

    loaded = load_run(run_path).cases[0]
    assert loaded.unsupported_citation_ids == ()
    assert loaded.cache_status == "miss"
    assert loaded.confidence == "high"
    del case["unsupported_citation_ids"]
    run_path.write_text(json.dumps(run), encoding="utf-8")
    with pytest.raises(EvaluationSuiteError, match="unsupported_citation_ids"):
        load_run(run_path)


def test_versioned_suite_contains_required_coverage_and_review_metadata() -> None:
    suite = load_suite(SUITE_PATH)

    assert suite.version == "mtg-rules-v1"
    assert suite.rules_effective_date == "2026-08-07"
    assert len(suite.cases) >= 100
    assert len(suite.positive_pairs) >= 10
    assert len(suite.negative_pairs) >= 10
    assert suite.review.status == "approved"
    assert suite.review.reviewer == "Project owner (independent human review)"
    assert suite.review.reviewed_at == "2026-08-19"


def test_audited_cases_reference_the_rules_effective_on_the_suite_date() -> None:
    suite = load_suite(SUITE_PATH)
    cases = {case.case_id: case for case in suite.cases}

    assert cases["state-001"].expected_reference_keys == ("117.3a",)
    assert cases["replace-003"].expected_reference_keys == ("614.4",)


def test_a_perfect_completed_run_passes_every_automated_gate() -> None:
    suite = load_suite(SUITE_PATH)
    results = tuple(
        CaseResult(
            case_id=case.case_id,
            retrieved_reference_keys=case.expected_reference_keys,
            citation_reference_keys=(
                case.expected_reference_keys
                if case.expected_behavior == "answer"
                else ()
            ),
            unknown_citation_ids=(),
            behavior=case.expected_behavior,
            retrieval_latency_ms=100,
            embedding_latency_ms=20,
            exact_latency_ms=20,
            lexical_latency_ms=20,
            vector_latency_ms=20,
            api_latency_ms=200,
            cache_hit=index < 20,
            cache_status="semantic" if index < 20 else "miss",
            confidence="high",
            answer="Reviewed fixture answer.",
            model=None if index < 20 else "gpt-5.6-luna",
            model_latency_ms=None if index < 20 else 50,
            input_tokens=None if index < 20 else 100,
            output_tokens=None if index < 20 else 20,
            citation_repaired=None if index < 20 else False,
            initial_model_latency_ms=None if index < 20 else 50,
            initial_input_tokens=None if index < 20 else 100,
            initial_output_tokens=None if index < 20 else 20,
            repair_latency_ms=None,
            repair_input_tokens=None,
            repair_output_tokens=None,
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

    repaired_case_id = suite.cases[20].case_id
    incomplete_repair = tuple(
        replace(result, citation_repaired=True)
        if result.case_id == repaired_case_id
        else result
        for result in results
    )
    incomplete_report = grade_run(
        suite,
        EvaluationRun(
            suite_version=suite.version,
            cases=incomplete_repair,
            semantic_cache_reuse_pair_ids=(),
        ),
        require_expert_review=False,
    )
    assert (
        "repair telemetry must be complete when repaired and null otherwise"
        in incomplete_report.failures
    )

    complete_repair = tuple(
        replace(
            result,
            citation_repaired=True,
            repair_latency_ms=10,
            repair_input_tokens=50,
            repair_output_tokens=10,
        )
        if result.case_id == repaired_case_id
        else result
        for result in results
    )
    complete_report = grade_run(
        suite,
        EvaluationRun(
            suite_version=suite.version,
            cases=complete_repair,
            semantic_cache_reuse_pair_ids=(),
        ),
        require_expert_review=False,
    )
    assert complete_report.passed
    assert report.retrieval_recall_at_8 == 1
    assert report.citation_identifier_validity == 1
    assert report.citation_excerpt_validity == 1
    assert report.citation_coverage == 1
    assert report.behavior_accuracy == 1
    assert report.incorrect_negative_pair_reuse == 0
    assert report.cache_status_counts == {"miss": 101, "semantic": 20}

    inconsistent_cache_status = (
        replace(results[0], cache_status="miss"),
        *results[1:],
    )
    inconsistent_report = grade_run(
        suite,
        EvaluationRun(
            suite_version=suite.version,
            cases=inconsistent_cache_status,
            semantic_cache_reuse_pair_ids=(),
        ),
        require_expert_review=False,
    )
    assert "cache hit and cache status must agree" in inconsistent_report.failures

    unsupported_excerpt = (
        replace(
            results[0],
            unsupported_citation_ids=("00000000-0000-0000-0000-000000000001",),
        ),
        *results[1:],
    )
    unsupported_report = grade_run(
        suite,
        EvaluationRun(
            suite_version=suite.version,
            cases=unsupported_excerpt,
            semantic_cache_reuse_pair_ids=(),
        ),
        require_expert_review=False,
    )
    assert unsupported_report.citation_excerpt_validity < 1
    assert "citation excerpt validity must be 100%" in unsupported_report.failures


def test_expected_answer_downgrades_count_toward_behavior_gate() -> None:
    suite = load_suite(SUITE_PATH)
    downgraded_ids = {
        case.case_id
        for case in suite.cases
        if case.expected_behavior == "answer"
    }
    downgraded_ids = set(sorted(downgraded_ids)[:19])
    results = tuple(
        CaseResult(
            case_id=case.case_id,
            retrieved_reference_keys=case.expected_reference_keys,
            citation_reference_keys=case.expected_reference_keys,
            unknown_citation_ids=(),
            behavior=(
                "abstain" if case.case_id in downgraded_ids else case.expected_behavior
            ),
            retrieval_latency_ms=100,
            embedding_latency_ms=20,
            exact_latency_ms=20,
            lexical_latency_ms=20,
            vector_latency_ms=20,
            api_latency_ms=200,
            cache_hit=index < 20,
            answer="Reviewed fixture answer.",
            model=None if index < 20 else "gpt-5.6-luna",
            model_latency_ms=None if index < 20 else 50,
            input_tokens=None if index < 20 else 100,
            output_tokens=None if index < 20 else 20,
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

    assert report.behavior_accuracy < 0.90
    assert "expected behavior accuracy must be at least 90%" in report.failures


def test_parent_rule_accepts_descendants_but_not_parent_or_sibling_for_child() -> None:
    assert reference_key_matches("613.4", "613.4a")
    assert reference_key_matches("614.1", "614.1a")
    assert not reference_key_matches("613.4a", "613.4")
    assert not reference_key_matches("613.4a", "613.4b")
    assert not reference_key_matches("card:Black Lotus", "card:Blacker Lotus")


def test_additional_unlabeled_supporting_citations_do_not_reduce_coverage() -> None:
    suite = load_suite(SUITE_PATH)
    results = tuple(
        CaseResult(
            case_id=case.case_id,
            retrieved_reference_keys=case.expected_reference_keys,
            citation_reference_keys=(
                (*case.expected_reference_keys, "supporting-reference")
                if case.expected_reference_keys
                else ()
            ),
            unknown_citation_ids=(),
            behavior=case.expected_behavior,
            retrieval_latency_ms=100,
            api_latency_ms=200,
            cache_hit=index < 20,
            answer="Reviewed fixture answer.",
            model=None if index < 20 else "gpt-5.6-luna",
            model_latency_ms=None if index < 20 else 50,
            input_tokens=None if index < 20 else 100,
            output_tokens=None if index < 20 else 20,
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

    assert report.citation_coverage == 1


def test_negative_pair_reuse_and_pending_review_block_release() -> None:
    suite = replace(
        load_suite(SUITE_PATH),
        review=Review(status="pending", reviewer=None, reviewed_at=None),
    )
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


def test_missing_answers_and_uncached_model_telemetry_block_release() -> None:
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
            cache_hit=False,
        )
        for case in suite.cases
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

    assert "evaluation capture must include every generated answer" in report.failures
    assert "uncached cases must include model and token telemetry" in report.failures
    assert "cases must include retrieval component telemetry" in report.failures


def test_uncached_cases_require_repair_telemetry_with_explicit_null_when_unused() -> None:
    suite = load_suite(SUITE_PATH)
    results = tuple(
        CaseResult(
            case_id=case.case_id,
            retrieved_reference_keys=case.expected_reference_keys,
            citation_reference_keys=(
                case.expected_reference_keys
                if case.expected_behavior == "answer"
                else ()
            ),
            unknown_citation_ids=(),
            behavior=case.expected_behavior,
            retrieval_latency_ms=100,
            embedding_latency_ms=20,
            exact_latency_ms=20,
            lexical_latency_ms=20,
            vector_latency_ms=20,
            api_latency_ms=200,
            cache_hit=index < 20,
            answer="Reviewed fixture answer.",
            model=None if index < 20 else "gpt-5.6-luna",
            model_latency_ms=None if index < 20 else 50,
            input_tokens=None if index < 20 else 100,
            output_tokens=None if index < 20 else 20,
            citation_repaired=None if index < 20 else False,
            initial_model_latency_ms=None if index < 20 else 50,
            initial_input_tokens=None if index < 20 else 100,
            initial_output_tokens=None if index < 20 else 20,
            repair_latency_ms=None,
            repair_input_tokens=None,
            repair_output_tokens=None,
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


def test_contextual_case_is_loaded_and_any_cache_hit_fails_the_gate(tmp_path: Path) -> None:
    payload = {
        'version': 'follow-up-v1',
        'rules_effective_date': '2026-08-07',
        'review': {'status': 'pending', 'reviewer': None, 'reviewed_at': None},
        'cases': [
            {
                'id': 'follow-up-001',
                'category': 'follow_up_context',
                'conversation': [
                    {'role': 'user', 'content': 'My creature is Slippery Bogle.'},
                    {'role': 'assistant', 'content': 'It has hexproof.'},
                ],
                'question': 'What if it loses that ability?',
                'expected_reference_keys': ['702.11'],
                'expected_behavior': 'answer',
            }
        ],
        'semantic_cache_positive_pairs': [],
        'semantic_cache_negative_pairs': [],
    }
    path = tmp_path / 'follow-up.json'
    path.write_text(json.dumps(payload), encoding='utf-8')
    suite = load_suite(path, enforce_release_shape=False)

    assert [message.role for message in suite.cases[0].conversation] == ['user', 'assistant']
    report = grade_run(
        suite,
        EvaluationRun(
            suite_version=suite.version,
            cases=(
                CaseResult(
                    case_id='follow-up-001',
                    retrieved_reference_keys=('702.11',),
                    citation_reference_keys=('702.11',),
                    unknown_citation_ids=(),
                    behavior='answer',
                    retrieval_latency_ms=100,
                    api_latency_ms=200,
                    cache_hit=True,
                ),
            ),
            semantic_cache_reuse_pair_ids=(),
        ),
        require_expert_review=False,
    )

    assert 'context-bearing cases must not use cached answers' in report.failures


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
