# MTG Rules Desk release eval

- Suite: `backend/evals/mtg_rules_v1.json`
- Grader: `mtg-rag-eval` in `backend/app/evals/harness.py`
- Type: deterministic retrieval, citation, behavior, latency, and cache-safety gate
- Dataset: 110 versioned cases, including 10 positive and 10 negative cache pairs
- Human gate: an independent MTG rules expert must approve the suite

The authoritative result schema, thresholds, and execution instructions are documented
in `backend/evals/README.md`. A passing result is necessary but not sufficient for
release: infrastructure, security, accessibility, policy, and operational checks also
must pass.
