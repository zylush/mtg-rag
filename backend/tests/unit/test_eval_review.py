import pytest

from app.evals.harness import (
    CachePair,
    CaseResult,
    EvalCase,
    EvalConversationMessage,
    EvaluationRun,
    EvaluationSuite,
    Review,
)
from app.evals.review import render_review_packet, write_review_packet


def test_review_packet_exposes_every_decision_and_observed_result() -> None:
    suite = EvaluationSuite(
        version="review-v1",
        rules_effective_date="2026-08-07",
        review=Review(status="pending", reviewer=None, reviewed_at=None),
        cases=(
            EvalCase(
                case_id="followup-001",
                category="follow_up_context",
                conversation=(
                    EvalConversationMessage(role="user", content="My creature has flying."),
                    EvalConversationMessage(role="assistant", content="Noted."),
                ),
                question="Can it be blocked?",
                expected_reference_keys=("702.9", "509.1b"),
                expected_behavior="answer",
            ),
        ),
        positive_pairs=(
            CachePair("positive-001", "followup-001", "followup-001"),
        ),
        negative_pairs=(
            CachePair("negative-001", "followup-001", "followup-001"),
        ),
    )
    run = EvaluationRun(
        suite_version="review-v1",
        cases=(
            CaseResult(
                case_id="followup-001",
                retrieved_reference_keys=("702.9", "509.1b"),
                citation_reference_keys=("702.9",),
                unknown_citation_ids=(),
                behavior="answer",
                retrieval_latency_ms=12.5,
                api_latency_ms=50.0,
                cache_hit=False,
                answer="A creature with reach can block an attacker with flying.",
                model="gpt-5.6-luna",
                model_latency_ms=41,
                input_tokens=321,
                output_tokens=45,
            ),
        ),
        semantic_cache_reuse_pair_ids=(),
    )

    packet = render_review_packet(suite, run)

    assert "Reviewer name:" in packet
    assert "Verdict: approve all cases / request changes" in packet
    assert "The suite does not contain prose expected answers" in packet
    assert "My creature has flying." in packet
    assert "Can it be blocked?" in packet
    assert "702.9, 509.1b" in packet
    assert "Observed citations: 702.9" in packet
    assert (
        "Observed answer: A creature with reach can block an attacker with flying."
        in packet
    )
    assert "Observed cache hit: no" in packet
    assert "Observed model: gpt-5.6-luna" in packet
    assert "Model latency: 41 ms" in packet
    assert "Tokens: 321 input / 45 output" in packet
    assert "Expected reusable pairs" in packet
    assert "Must-not-reuse pairs" in packet
    assert "`positive-001`: `followup-001` -> `followup-001`" in packet
    assert "`negative-001`: `followup-001` -> `followup-001`" in packet
    assert packet.count("- [ ] Reviewed") == 3


def test_review_packet_rejects_a_run_for_another_suite() -> None:
    suite = EvaluationSuite(
        version="review-v1",
        rules_effective_date="2026-08-07",
        review=Review(status="pending", reviewer=None, reviewed_at=None),
        cases=(),
        positive_pairs=(),
        negative_pairs=(),
    )
    run = EvaluationRun(
        suite_version="other-v1",
        cases=(),
        semantic_cache_reuse_pair_ids=(),
    )

    try:
        render_review_packet(suite, run)
    except ValueError as exc:
        assert "suite version" in str(exc)
    else:
        raise AssertionError("mismatched review run must be rejected")


def test_review_packet_is_written_exclusively(tmp_path) -> None:  # type: ignore[no-untyped-def]
    output = tmp_path / "review.md"

    write_review_packet(output, "review evidence\n")

    assert output.read_text(encoding="utf-8") == "review evidence\n"
    with pytest.raises(ValueError, match="already exists"):
        write_review_packet(output, "replacement\n")
