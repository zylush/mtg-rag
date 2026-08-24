from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, cast

Behavior = Literal["answer", "clarify", "abstain"]
CacheStatus = Literal["exact", "semantic", "miss", "ineligible"]
Confidence = Literal["high", "medium", "low"]
ReviewState = Literal["pending", "approved"]
ConversationRole = Literal["user", "assistant"]

REQUIRED_CATEGORIES = frozenset(
    {
        "exact_rule",
        "oracle_text",
        "glossary",
        "layers",
        "replacement_trigger",
        "state_priority",
        "multiface_zone",
        "clarification",
        "abstention",
        "prompt_injection",
        "semantic_cache",
        "follow_up_context",
    }
)
_PARENT_RULE_REFERENCE = re.compile(r"\d{3}\.\d+")
_RULE_REFERENCE = re.compile(r"\d{3}\.\d+[a-z]?")


class EvaluationSuiteError(ValueError):
    """Raised when a versioned evaluation artifact violates its schema."""


def reference_key_matches(expected: str, observed: str) -> bool:
    """Match exact keys, allowing a declared parent rule to accept one subrule."""
    if expected == observed:
        return True
    return bool(
        _PARENT_RULE_REFERENCE.fullmatch(expected)
        and _RULE_REFERENCE.fullmatch(observed)
        and observed.startswith(expected)
        and len(observed) == len(expected) + 1
    )


@dataclass(frozen=True)
class Review:
    status: ReviewState
    reviewer: str | None
    reviewed_at: str | None


@dataclass(frozen=True)
class EvalConversationMessage:
    role: ConversationRole
    content: str


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    category: str
    question: str
    expected_reference_keys: tuple[str, ...]
    expected_behavior: Behavior
    conversation: tuple[EvalConversationMessage, ...] = ()


@dataclass(frozen=True)
class CachePair:
    pair_id: str
    first_case_id: str
    second_case_id: str


@dataclass(frozen=True)
class EvaluationSuite:
    version: str
    rules_effective_date: str
    review: Review
    cases: tuple[EvalCase, ...]
    positive_pairs: tuple[CachePair, ...]
    negative_pairs: tuple[CachePair, ...]


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    retrieved_reference_keys: tuple[str, ...]
    citation_reference_keys: tuple[str, ...]
    unknown_citation_ids: tuple[str, ...]
    behavior: Behavior
    retrieval_latency_ms: float
    api_latency_ms: float
    cache_hit: bool
    cache_status: CacheStatus | None = None
    confidence: Confidence | None = None
    unsupported_citation_ids: tuple[str, ...] = ()
    embedding_latency_ms: float | None = None
    exact_latency_ms: float | None = None
    lexical_latency_ms: float | None = None
    vector_latency_ms: float | None = None
    answer: str | None = None
    model: str | None = None
    model_latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    citation_repaired: bool | None = None
    initial_model_latency_ms: int | None = None
    initial_input_tokens: int | None = None
    initial_output_tokens: int | None = None
    repair_latency_ms: int | None = None
    repair_input_tokens: int | None = None
    repair_output_tokens: int | None = None


@dataclass(frozen=True)
class EvaluationRun:
    suite_version: str
    cases: tuple[CaseResult, ...]
    semantic_cache_reuse_pair_ids: tuple[str, ...]


@dataclass(frozen=True)
class EvaluationReport:
    passed: bool
    suite_version: str
    case_count: int
    retrieval_recall_at_8: float
    citation_identifier_validity: float
    citation_excerpt_validity: float
    citation_coverage: float
    behavior_accuracy: float
    incorrect_negative_pair_reuse: int
    retrieval_latency_p95_ms: float
    cached_api_latency_p95_ms: float
    cache_status_counts: dict[str, int]
    failures: tuple[str, ...]


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise EvaluationSuiteError(f"{name} must be an object")
    return cast(dict[str, object], value)


def _array(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise EvaluationSuiteError(f"{name} must be an array")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationSuiteError(f"{name} must be a non-empty string")
    return value


def _optional_text(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _text(value, name)


def _text_tuple(value: object, name: str) -> tuple[str, ...]:
    return tuple(_text(item, name) for item in _array(value, name))


def _behavior(value: object, name: str) -> Behavior:
    text = _text(value, name)
    if text not in {"answer", "clarify", "abstain"}:
        raise EvaluationSuiteError(f"{name} has an unsupported behavior")
    return cast(Behavior, text)


def _optional_cache_status(value: object, name: str) -> CacheStatus | None:
    if value is None:
        return None
    text = _text(value, name)
    if text not in {"exact", "semantic", "miss", "ineligible"}:
        raise EvaluationSuiteError(f"{name} has an unsupported cache status")
    return cast(CacheStatus, text)


def _optional_confidence(value: object, name: str) -> Confidence | None:
    if value is None:
        return None
    text = _text(value, name)
    if text not in {"high", "medium", "low"}:
        raise EvaluationSuiteError(f"{name} has an unsupported confidence")
    return cast(Confidence, text)


def _conversation(value: object, name: str) -> tuple[EvalConversationMessage, ...]:
    if value is None:
        return ()
    messages: list[EvalConversationMessage] = []
    for index, item in enumerate(_array(value, name)):
        payload = _object(item, f"{name}[{index}]")
        role = _text(payload.get("role"), f"{name}[{index}].role")
        if role not in {"user", "assistant"}:
            raise EvaluationSuiteError(
                f"{name}[{index}].role must be user or assistant"
            )
        messages.append(
            EvalConversationMessage(
                role=cast(ConversationRole, role),
                content=_text(payload.get("content"), f"{name}[{index}].content"),
            )
        )
    return tuple(messages)


def _pair(value: object, name: str) -> CachePair:
    payload = _object(value, name)
    return CachePair(
        pair_id=_text(payload.get("id"), f"{name}.id"),
        first_case_id=_text(payload.get("first_case_id"), f"{name}.first_case_id"),
        second_case_id=_text(payload.get("second_case_id"), f"{name}.second_case_id"),
    )


def load_suite(path: Path, *, enforce_release_shape: bool = True) -> EvaluationSuite:
    try:
        root = _object(json.loads(path.read_text(encoding="utf-8")), "suite")
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationSuiteError(f"unable to read evaluation suite: {exc}") from exc

    review_payload = _object(root.get("review"), "review")
    review_status = _text(review_payload.get("status"), "review.status")
    if review_status not in {"pending", "approved"}:
        raise EvaluationSuiteError("review.status must be pending or approved")
    review = Review(
        status=cast(ReviewState, review_status),
        reviewer=_optional_text(review_payload.get("reviewer"), "review.reviewer"),
        reviewed_at=_optional_text(review_payload.get("reviewed_at"), "review.reviewed_at"),
    )
    if review.status == "approved" and (review.reviewer is None or review.reviewed_at is None):
        raise EvaluationSuiteError("approved review requires reviewer and reviewed_at")

    cases: list[EvalCase] = []
    for index, value in enumerate(_array(root.get("cases"), "cases")):
        payload = _object(value, f"cases[{index}]")
        expected_keys = _text_tuple(
            payload.get("expected_reference_keys"),
            f"cases[{index}].expected_reference_keys",
        )
        behavior = _behavior(payload.get("expected_behavior"), f"cases[{index}].behavior")
        if behavior == "answer" and not expected_keys:
            raise EvaluationSuiteError("answer cases require expected reference keys")
        cases.append(
            EvalCase(
                case_id=_text(payload.get("id"), f"cases[{index}].id"),
                category=_text(payload.get("category"), f"cases[{index}].category"),
                question=_text(payload.get("question"), f"cases[{index}].question"),
                expected_reference_keys=expected_keys,
                expected_behavior=behavior,
                conversation=_conversation(
                    payload.get("conversation"),
                    f"cases[{index}].conversation",
                ),
            )
        )

    positive_values = _array(
        root.get("semantic_cache_positive_pairs"),
        "semantic_cache_positive_pairs",
    )
    negative_values = _array(
        root.get("semantic_cache_negative_pairs"),
        "semantic_cache_negative_pairs",
    )
    positive_pairs = tuple(
        _pair(value, f"semantic_cache_positive_pairs[{index}]")
        for index, value in enumerate(positive_values)
    )
    negative_pairs = tuple(
        _pair(value, f"semantic_cache_negative_pairs[{index}]")
        for index, value in enumerate(negative_values)
    )

    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise EvaluationSuiteError("duplicate case IDs")
    known_ids = set(case_ids)
    pair_ids = [pair.pair_id for pair in (*positive_pairs, *negative_pairs)]
    if len(pair_ids) != len(set(pair_ids)):
        raise EvaluationSuiteError("duplicate semantic-cache pair IDs")
    if any(
        pair.first_case_id not in known_ids or pair.second_case_id not in known_ids
        for pair in (*positive_pairs, *negative_pairs)
    ):
        raise EvaluationSuiteError("semantic-cache pair references an unknown case")

    if enforce_release_shape:
        if len(cases) < 100:
            raise EvaluationSuiteError("release suite must contain at least 100 cases")
        missing_categories = REQUIRED_CATEGORIES - {case.category for case in cases}
        if missing_categories:
            missing = ", ".join(sorted(missing_categories))
            raise EvaluationSuiteError(f"release suite is missing categories: {missing}")
        if len(positive_pairs) < 10 or len(negative_pairs) < 10:
            raise EvaluationSuiteError(
                "release suite requires at least ten cache pairs of each kind"
            )

    return EvaluationSuite(
        version=_text(root.get("version"), "version"),
        rules_effective_date=_text(root.get("rules_effective_date"), "rules_effective_date"),
        review=review,
        cases=tuple(cases),
        positive_pairs=positive_pairs,
        negative_pairs=negative_pairs,
    )


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationSuiteError(f"{name} must be numeric")
    result = float(value)
    if result < 0 or not math.isfinite(result):
        raise EvaluationSuiteError(f"{name} must be a finite non-negative number")
    return result


def _optional_number(value: object, name: str) -> float | None:
    if value is None:
        return None
    return _number(value, name)


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise EvaluationSuiteError(f"{name} must be boolean")
    return value


def _optional_boolean(value: object, name: str) -> bool | None:
    if value is None:
        return None
    return _boolean(value, name)


def _optional_nonnegative_integer(value: object, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvaluationSuiteError(f"{name} must be a non-negative integer or null")
    return value


def load_run(path: Path) -> EvaluationRun:
    try:
        root = _object(json.loads(path.read_text(encoding="utf-8")), "run")
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationSuiteError(f"unable to read evaluation run: {exc}") from exc

    cases: list[CaseResult] = []
    for index, value in enumerate(_array(root.get("cases"), "cases")):
        payload = _object(value, f"cases[{index}]")
        cases.append(
            CaseResult(
                case_id=_text(payload.get("id"), f"cases[{index}].id"),
                retrieved_reference_keys=_text_tuple(
                    payload.get("retrieved_reference_keys"),
                    f"cases[{index}].retrieved_reference_keys",
                ),
                citation_reference_keys=_text_tuple(
                    payload.get("citation_reference_keys"),
                    f"cases[{index}].citation_reference_keys",
                ),
                unknown_citation_ids=_text_tuple(
                    payload.get("unknown_citation_ids"),
                    f"cases[{index}].unknown_citation_ids",
                ),
                unsupported_citation_ids=_text_tuple(
                    payload.get("unsupported_citation_ids"),
                    f"cases[{index}].unsupported_citation_ids",
                ),
                behavior=_behavior(payload.get("behavior"), f"cases[{index}].behavior"),
                retrieval_latency_ms=_number(
                    payload.get("retrieval_latency_ms"),
                    f"cases[{index}].retrieval_latency_ms",
                ),
                api_latency_ms=_number(
                    payload.get("api_latency_ms"),
                    f"cases[{index}].api_latency_ms",
                ),
                cache_hit=_boolean(payload.get("cache_hit"), f"cases[{index}].cache_hit"),
                cache_status=_optional_cache_status(
                    payload.get("cache_status"), f"cases[{index}].cache_status"
                ),
                confidence=_optional_confidence(
                    payload.get("confidence"), f"cases[{index}].confidence"
                ),
                embedding_latency_ms=_optional_number(
                    payload.get("embedding_latency_ms"),
                    f"cases[{index}].embedding_latency_ms",
                ),
                exact_latency_ms=_optional_number(
                    payload.get("exact_latency_ms"),
                    f"cases[{index}].exact_latency_ms",
                ),
                lexical_latency_ms=_optional_number(
                    payload.get("lexical_latency_ms"),
                    f"cases[{index}].lexical_latency_ms",
                ),
                vector_latency_ms=_optional_number(
                    payload.get("vector_latency_ms"),
                    f"cases[{index}].vector_latency_ms",
                ),
                answer=_optional_text(
                    payload.get("answer"), f"cases[{index}].answer"
                ),
                model=_optional_text(payload.get("model"), f"cases[{index}].model"),
                model_latency_ms=_optional_nonnegative_integer(
                    payload.get("model_latency_ms"),
                    f"cases[{index}].model_latency_ms",
                ),
                input_tokens=_optional_nonnegative_integer(
                    payload.get("input_tokens"), f"cases[{index}].input_tokens"
                ),
                output_tokens=_optional_nonnegative_integer(
                    payload.get("output_tokens"), f"cases[{index}].output_tokens"
                ),
                citation_repaired=_optional_boolean(
                    payload.get("citation_repaired"),
                    f"cases[{index}].citation_repaired",
                ),
                initial_model_latency_ms=_optional_nonnegative_integer(
                    payload.get("initial_model_latency_ms"),
                    f"cases[{index}].initial_model_latency_ms",
                ),
                initial_input_tokens=_optional_nonnegative_integer(
                    payload.get("initial_input_tokens"),
                    f"cases[{index}].initial_input_tokens",
                ),
                initial_output_tokens=_optional_nonnegative_integer(
                    payload.get("initial_output_tokens"),
                    f"cases[{index}].initial_output_tokens",
                ),
                repair_latency_ms=_optional_nonnegative_integer(
                    payload.get("repair_latency_ms"),
                    f"cases[{index}].repair_latency_ms",
                ),
                repair_input_tokens=_optional_nonnegative_integer(
                    payload.get("repair_input_tokens"),
                    f"cases[{index}].repair_input_tokens",
                ),
                repair_output_tokens=_optional_nonnegative_integer(
                    payload.get("repair_output_tokens"),
                    f"cases[{index}].repair_output_tokens",
                ),
            )
        )
    return EvaluationRun(
        suite_version=_text(root.get("suite_version"), "suite_version"),
        cases=tuple(cases),
        semantic_cache_reuse_pair_ids=_text_tuple(
            root.get("semantic_cache_reuse_pair_ids"),
            "semantic_cache_reuse_pair_ids",
        ),
    )


def _p95(values: list[float]) -> float:
    if not values:
        return math.inf
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * 0.95) - 1]


def grade_run(
    suite: EvaluationSuite,
    run: EvaluationRun,
    *,
    require_expert_review: bool = True,
) -> EvaluationReport:
    failures: list[str] = []
    if run.suite_version != suite.version:
        failures.append("run suite version does not match")

    expected_by_id = {case.case_id: case for case in suite.cases}
    result_by_id = {case.case_id: case for case in run.cases}
    if len(result_by_id) != len(run.cases):
        failures.append("run contains duplicate case IDs")
    if set(result_by_id) != set(expected_by_id):
        failures.append("run must contain exactly every suite case")

    matched = [
        (expected_by_id[case_id], result_by_id[case_id])
        for case_id in expected_by_id.keys() & result_by_id.keys()
    ]
    retrieval_cases = [
        (expected, result)
        for expected, result in matched
        if expected.expected_reference_keys
    ]
    recall_hits = sum(
        all(
            any(
                reference_key_matches(required, observed)
                for observed in result.retrieved_reference_keys[:8]
            )
            for required in expected.expected_reference_keys
        )
        for expected, result in retrieval_cases
    )
    retrieval_recall = recall_hits / len(retrieval_cases) if retrieval_cases else 0.0

    citation_validity = (
        sum(not result.unknown_citation_ids for _, result in matched) / len(matched)
        if matched
        else 0.0
    )
    citation_excerpt_validity = (
        sum(not result.unsupported_citation_ids for _, result in matched)
        / len(matched)
        if matched
        else 0.0
    )
    citation_cases = [
        (expected, result)
        for expected, result in matched
        if expected.expected_reference_keys
    ]
    citation_hits = sum(
        all(
            any(
                reference_key_matches(required, observed)
                for observed in result.citation_reference_keys
            )
            for required in expected.expected_reference_keys
        )
        for expected, result in citation_cases
    )
    citation_coverage = citation_hits / len(citation_cases) if citation_cases else 0.0

    behavior_cases = matched
    behavior_accuracy = (
        sum(result.behavior == expected.expected_behavior for expected, result in behavior_cases)
        / len(behavior_cases)
        if behavior_cases
        else 0.0
    )

    known_negative_pairs = {pair.pair_id for pair in suite.negative_pairs}
    observed_pair_ids = set(run.semantic_cache_reuse_pair_ids)
    unknown_pairs = observed_pair_ids - {
        pair.pair_id for pair in (*suite.positive_pairs, *suite.negative_pairs)
    }
    if unknown_pairs:
        failures.append("run reports unknown semantic-cache pair IDs")
    negative_reuse = len(observed_pair_ids & known_negative_pairs)
    retrieval_p95 = _p95([result.retrieval_latency_ms for _, result in matched])
    cached_p95 = _p95(
        [result.api_latency_ms for _, result in matched if result.cache_hit]
    )
    cache_status_counts: dict[str, int] = {}
    for _, result in matched:
        if result.cache_status is not None:
            cache_status_counts[result.cache_status] = (
                cache_status_counts.get(result.cache_status, 0) + 1
            )

    if require_expert_review and suite.review.status != "approved":
        failures.append("expert review is not approved")
    if any(result.answer is None for _, result in matched):
        failures.append("evaluation capture must include every generated answer")
    if any(
        result.cache_status is not None
        and result.cache_hit != (result.cache_status in {"exact", "semantic"})
        for _, result in matched
    ):
        failures.append("cache hit and cache status must agree")
    if cache_status_counts and any(
        result.cache_status is None or result.confidence is None for _, result in matched
    ):
        failures.append(
            "current cache telemetry must include status and confidence for every case"
        )
    if any(
        not result.cache_hit
        and (
            result.model is None
            or result.model_latency_ms is None
            or result.input_tokens is None
            or result.output_tokens is None
        )
        for _, result in matched
    ):
        failures.append("uncached cases must include model and token telemetry")
    if any(
        not result.cache_hit
        and (
            result.citation_repaired is None
            or result.initial_model_latency_ms is None
            or result.initial_input_tokens is None
            or result.initial_output_tokens is None
        )
        for _, result in matched
    ):
        failures.append("uncached cases must include initial and repair telemetry")
    if any(
        not result.cache_hit
        and result.citation_repaired is not None
        and (
            (
                result.citation_repaired
                and (
                    result.repair_latency_ms is None
                    or result.repair_input_tokens is None
                    or result.repair_output_tokens is None
                )
            )
            or (
                not result.citation_repaired
                and any(
                    value is not None
                    for value in (
                        result.repair_latency_ms,
                        result.repair_input_tokens,
                        result.repair_output_tokens,
                    )
                )
            )
        )
        for _, result in matched
    ):
        failures.append(
            "repair telemetry must be complete when repaired and null otherwise"
        )
    if any(
        result.embedding_latency_ms is None
        or result.exact_latency_ms is None
        or result.lexical_latency_ms is None
        or result.vector_latency_ms is None
        for _, result in matched
    ):
        failures.append("cases must include retrieval component telemetry")
    if any(len(result.retrieved_reference_keys) > 8 for _, result in matched):
        failures.append("retrieval output must contain no more than eight passages")
    if retrieval_recall < 0.90:
        failures.append("retrieval recall@8 must be at least 90%")
    if citation_validity < 1:
        failures.append("citation identifier validity must be 100%")
    if citation_excerpt_validity < 1:
        failures.append("citation excerpt validity must be 100%")
    if citation_coverage < 0.95:
        failures.append("required-reference citation coverage must be at least 95%")
    if behavior_accuracy < 0.90:
        failures.append("expected behavior accuracy must be at least 90%")
    if negative_reuse:
        failures.append("semantic-cache negative-pair reuse must be zero")
    if any(expected.conversation and result.cache_hit for expected, result in matched):
        failures.append("context-bearing cases must not use cached answers")
    if retrieval_p95 > 500:
        failures.append("retrieval latency p95 must be at most 500 ms")
    if cached_p95 > 1500:
        failures.append("cached API latency p95 must be at most 1500 ms")

    return EvaluationReport(
        passed=not failures,
        suite_version=suite.version,
        case_count=len(matched),
        retrieval_recall_at_8=retrieval_recall,
        citation_identifier_validity=citation_validity,
        citation_excerpt_validity=citation_excerpt_validity,
        citation_coverage=citation_coverage,
        behavior_accuracy=behavior_accuracy,
        incorrect_negative_pair_reuse=negative_reuse,
        retrieval_latency_p95_ms=retrieval_p95,
        cached_api_latency_p95_ms=cached_p95,
        cache_status_counts=cache_status_counts,
        failures=tuple(failures),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Grade an MTG RAG staging evaluation run.")
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument(
        "--allow-pending-review",
        action="store_true",
        help="Use only for harness development; this cannot approve a public release.",
    )
    args = parser.parse_args()

    try:
        report = grade_run(
            load_suite(args.suite),
            load_run(args.run),
            require_expert_review=not args.allow_pending_review,
        )
    except EvaluationSuiteError as exc:
        parser.exit(2, f"evaluation input error: {exc}\n")
    print(json.dumps(asdict(report), indent=2, sort_keys=True))
    if not report.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
