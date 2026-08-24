# MTG rules evaluation

`mtg_rules_v1.json` is the versioned release-gate suite. It contains 121 cases across
exact rules, Oracle text, glossary, layers, replacement and trigger interactions,
state-based actions and priority, multi-face and zone behavior, clarification,
abstention, prompt injection, semantic-cache boundaries, and bounded follow-up context.

Cases may include a `conversation` array of `{"role":"user|assistant","content":"..."}`
messages. Those messages are the prior context for the current `question`; the staging runner
must create or reproduce that history, submit the follow-up with its conversation ID, and report
`cache_hit=false`.

An independent MTG rules expert must approve the expected answers and references by
changing `review.status` to `approved`, recording their name and review date, and
committing that review. The author of an implementation must not self-approve it.

## Result capture contract

Run the suite against a staging deployment using an account exempt from ordinary
consumer quotas. Capture one JSON object with this shape:

```json
{
  "suite_version": "mtg-rules-v1",
  "cases": [
    {
      "id": "exact-001",
      "retrieved_reference_keys": ["100.1"],
      "citation_reference_keys": ["100.1"],
      "unknown_citation_ids": [],
      "unsupported_citation_ids": [],
      "behavior": "answer",
      "retrieval_latency_ms": 125.0,
      "api_latency_ms": 412.5,
      "cache_hit": false,
      "answer": "Observed answer text with passage-backed citations.",
      "model": "gpt-5.6-luna",
      "model_latency_ms": 387.0,
      "input_tokens": 1180,
      "output_tokens": 164,
      "citation_repaired": false,
      "initial_model_latency_ms": 387,
      "initial_input_tokens": 1180,
      "initial_output_tokens": 164,
      "repair_latency_ms": null,
      "repair_input_tokens": null,
      "repair_output_tokens": null
    }
  ],
  "semantic_cache_reuse_pair_ids": []
}
```

From an installed backend environment, configure a non-production PostgreSQL database with a
complete active `rules`, `cards`, and `rulings` corpus plus an OpenAI API key, then run:

```text
mtg-rag-capture --suite evals/mtg_rules_v1.json --output staging-run.json --confirm-non-production
```

The development Cloud Run evaluation job uses the same capture contract but writes directly to the
regional snapshot bucket under a unique `evaluation-captures/` object name. The upload uses a
create-only generation precondition, records the payload SHA-256 in object metadata, and runs as a
dedicated evaluation service account that can create objects but cannot overwrite or delete them.
Terraform does not create this job or its service account in production.

The capture command refuses `prod`/`production`, enables bounded context for the run, uses a unique
retrieval version so evaluation cache entries cannot collide with ordinary traffic, raises the
quota ceilings above the suite size, and deletes its synthetic user, conversations, usage, ask
attempts, and run-specific semantic-cache entries on exit. It prints case IDs only, never question
or conversation content. The output path must not already exist.

Reference keys are the canonical CR rule number, glossary term, card name, or ruling
identifier declared by the case. `behavior` is one of `answer`, `clarify`, or
`abstain`. Record `cache_hit` from the API response metadata or the correlated
cache telemetry event; do not infer it from latency.

Every case must include the observed answer. Every uncached case must also include the model and
aggregate telemetry, `citation_repaired`, and initial model latency/token fields. Repair latency
and token fields must be explicit `null` when no repair occurs, or all be populated when the one
allowed citation-repair call occurs. Older artifacts without these fields remain loadable for
diagnosis, but they cannot pass the release gate.

Every current capture must also include `unsupported_citation_ids`. The staging runner independently
normalizes each returned citation claim and cited passage using the runtime NFKC/whitespace contract,
checks the 320-character bound and contiguous occurrence, and records any failures. A capture that
omits this field is rejected rather than being treated as v11 evidence.

Grade the capture from an installed backend environment:

```text
mtg-rag-eval --suite evals/mtg_rules_v1.json --run staging-run.json
```

The process exits nonzero unless every gate passes: recall@8 at least 0.90, citation-ID
validity 1.00, citation-excerpt validity 1.00, required-reference citation coverage at least 0.95,
expected-behavior accuracy at least 0.90, zero unsafe negative-pair cache reuse,
retrieval p95 at most 500 ms, cached
API p95 at most 1.5 s, and an approved expert review.
Any cache hit on a case with conversation context also fails the gate.

Current captures also retain each response's exact cache status (`exact`, `semantic`, `miss`, or
`ineligible`) and confidence. The grader reports cache-status counts, rejects disagreement between
the status and the legacy `cache_hit` boolean, and rejects a partially populated current telemetry
set. Older immutable captures remain loadable with empty cache-status counts so their historical
grades stay reproducible.

Required-reference citation coverage asks whether every reference declared by a case is represented
by at least one citation. Declared references are minimum required evidence, not an exhaustive list,
so additional valid supporting citations do not count as false positives.

The expert review packet includes the observed answer for every case plus every declared positive
and negative semantic-cache pair. The reviewer must check both the case expectations and the pair
definitions; generating or opening a packet does not approve the suite.

`--allow-pending-review` is solely for testing the grader. Its output is not release
evidence. Preserve every staging capture as a build artifact and link it from the
release record.
