from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from app.evals.harness import (
    CaseResult,
    EvaluationRun,
    EvaluationSuite,
    EvaluationSuiteError,
    load_run,
    load_suite,
)


def _inline(value: str) -> str:
    return " ".join(value.splitlines()).strip()


def _references(values: tuple[str, ...]) -> str:
    return ", ".join(values) if values else "(none)"


def _result_map(
    suite: EvaluationSuite, run: EvaluationRun | None
) -> dict[str, CaseResult]:
    if run is None:
        return {}
    if run.suite_version != suite.version:
        raise EvaluationSuiteError("review run suite version does not match")
    result_by_id = {result.case_id: result for result in run.cases}
    if len(result_by_id) != len(run.cases):
        raise EvaluationSuiteError("review run contains duplicate case IDs")
    expected_ids = {case.case_id for case in suite.cases}
    if set(result_by_id) != expected_ids:
        raise EvaluationSuiteError("review run must contain exactly every suite case")
    return result_by_id


def render_review_packet(
    suite: EvaluationSuite, run: EvaluationRun | None = None
) -> str:
    """Render a complete human-review surface without changing review state."""
    result_by_id = _result_map(suite, run)
    category_counts = Counter(case.category for case in suite.cases)
    observations = "yes" if run is not None else "no"
    lines = [
        f"# {suite.version} personal review packet",
        "",
        f"- Rules effective date: {suite.rules_effective_date}",
        f"- Case count: {len(suite.cases)}",
        f"- Current review status: {suite.review.status}",
        f"- Staging observations included: {observations}",
        "",
        "Review scope: verify every question, prior conversation, expected behavior, and "
        "expected reference. The suite does not contain prose expected answers. When staging "
        "observations are included, verify each generated answer against those expectations; "
        "a staging observation is evidence, not an automatic approval.",
        "",
        "## Reviewer record",
        "",
        "- Reviewer name:",
        "- Review date (YYYY-MM-DD):",
        "- Verdict: approve all cases / request changes",
        "- Change requests, if any:",
        "",
        "Only an explicit verdict after all case checkboxes are reviewed may be copied into "
        "the suite metadata. Opening or reading this packet does not approve it.",
        "",
        "## Category summary",
        "",
    ]
    for category, count in category_counts.items():
        lines.append(f"- `{category}`: {count}")

    case_by_id = {case.case_id: case for case in suite.cases}
    observed_reuse = (
        set(run.semantic_cache_reuse_pair_ids) if run is not None else set()
    )
    lines.extend(["", "## Semantic-cache pair review", ""])
    for heading, pairs in (
        ("Expected reusable pairs", suite.positive_pairs),
        ("Must-not-reuse pairs", suite.negative_pairs),
    ):
        lines.extend([f"### {heading}", ""])
        if not pairs:
            lines.extend(["(none)", ""])
            continue
        for pair in pairs:
            first = case_by_id[pair.first_case_id]
            second = case_by_id[pair.second_case_id]
            lines.extend(
                [
                    "- [ ] Reviewed",
                    f"- `{pair.pair_id}`: `{pair.first_case_id}` -> `{pair.second_case_id}`",
                    f"  - First question: {_inline(first.question)}",
                    f"  - Second question: {_inline(second.question)}",
                ]
            )
            if run is not None:
                reused = "yes" if pair.pair_id in observed_reuse else "no"
                lines.append(f"  - Observed reuse: {reused}")
            lines.extend(["  - Reviewer notes:", ""])

    active_category: str | None = None
    for index, case in enumerate(suite.cases, start=1):
        if case.category != active_category:
            active_category = case.category
            lines.extend(["", f"## Category: `{active_category}`", ""])
        lines.extend(
            [
                f"### {index}. `{case.case_id}`",
                "",
                "- [ ] Reviewed",
                f"- Current question: {_inline(case.question)}",
                f"- Expected behavior: `{case.expected_behavior}`",
                f"- Expected references: {_references(case.expected_reference_keys)}",
            ]
        )
        if case.conversation:
            lines.append("- Prior conversation:")
            for message in case.conversation:
                lines.append(f"  - **{message.role}:** {_inline(message.content)}")
        else:
            lines.append("- Prior conversation: (none)")

        result = result_by_id.get(case.case_id)
        if result is not None:
            cache_hit = "yes" if result.cache_hit else "no"
            observed_answer = (
                _inline(result.answer)
                if result.answer is not None
                else "(not captured; rerun required before answer review)"
            )
            observed_model = result.model or "(not captured)"
            observed_model_latency = (
                f"{result.model_latency_ms} ms"
                if result.model_latency_ms is not None
                else "(not captured)"
            )
            observed_tokens = (
                f"{result.input_tokens} input / {result.output_tokens} output"
                if result.input_tokens is not None and result.output_tokens is not None
                else "(not captured)"
            )
            lines.extend(
                [
                    f"- Observed answer: {observed_answer}",
                    f"- Observed behavior: `{result.behavior}`",
                    f"- Observed retrieval: {_references(result.retrieved_reference_keys)}",
                    f"- Observed citations: {_references(result.citation_reference_keys)}",
                    f"- Unknown citation IDs: {_references(result.unknown_citation_ids)}",
                    f"- Observed cache hit: {cache_hit}",
                    f"- Observed model: {observed_model}",
                    f"- Model latency: {observed_model_latency}",
                    f"- Tokens: {observed_tokens}",
                    f"- Retrieval latency: {result.retrieval_latency_ms:.1f} ms",
                    f"- API latency: {result.api_latency_ms:.1f} ms",
                ]
            )
        lines.extend(["- Reviewer notes:", ""])

    return "\n".join(lines).rstrip() + "\n"


def write_review_packet(path: Path, packet: str) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as output:
            output.write(packet)
    except FileExistsError as exc:
        raise EvaluationSuiteError(
            f"review packet already exists: {path}"
        ) from exc
    except OSError as exc:
        raise EvaluationSuiteError(f"unable to write review packet: {exc}") from exc


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Render a complete human-review packet for an MTG evaluation suite."
    )
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        suite = load_suite(args.suite)
        run = load_run(args.run) if args.run is not None else None
        write_review_packet(args.output, render_review_packet(suite, run))
    except EvaluationSuiteError as exc:
        parser.error(str(exc))
    print(f"review packet written: {args.output}")


if __name__ == "__main__":
    main()
