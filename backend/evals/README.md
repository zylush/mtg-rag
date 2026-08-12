# MTG rules evaluation

`mtg_rules_v1.json` is the versioned release-gate suite. It contains 110 cases across
exact rules, Oracle text, glossary, layers, replacement and trigger interactions,
state-based actions and priority, multi-face and zone behavior, clarification,
abstention, prompt injection, and semantic-cache boundaries.

An independent MTG rules expert must approve the expected answers and references by
changing `review.status` to `approved`, recording their name and review date, and
committing that review. The author of an implementation must not self-approve it.

## Result capture contract

Run the suite against a staging deployment using an account exempt from ordinary
consumer quotas. Capture one JSON object with this shape:

```json
{
  "suite_version": "1.0.0",
  "results": [
    {
      "id": "exact-rule-001",
      "latency_ms": 412.5,
      "retrieved_references": ["100.1"],
      "cited_references": ["100.1"],
      "behavior": "answer",
      "cache_reused": false
    }
  ]
}
```

Reference keys are the canonical CR rule number, glossary term, card name, or ruling
identifier declared by the case. `behavior` is one of `answer`, `clarify`, or
`abstain`. Record `cache_reused` from the API response metadata or the correlated
cache telemetry event; do not infer it from latency.

Grade the capture from an installed backend environment:

```text
mtg-rag-eval --suite evals/mtg_rules_v1.json --run staging-run.json
```

The process exits nonzero unless every gate passes: recall@8 at least 0.90, citation-ID
validity 1.00, citation precision at least 0.95, clarification/abstention accuracy at
least 0.90, zero unsafe negative-pair cache reuse, retrieval p95 at most 500 ms, cached
API p95 at most 1.5 s, and an approved expert review.

`--allow-pending-review` is solely for testing the grader. Its output is not release
evidence. Preserve every staging capture as a build artifact and link it from the
release record.
