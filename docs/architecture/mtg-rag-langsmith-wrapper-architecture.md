# MTG-RAG LangSmith wrapper architecture

**Status:** Proposed observability and evaluation integration
**Decision:** Add LangSmith around the existing MTG-RAG service. Do not replace the traditional
RAG path with LangChain or make telemetry a request dependency.
**Last reconciled:** 2026-08-20

## 1. Purpose

This document describes how LangSmith will provide tracing, experiment tracking, and evaluation
for MTG Rules Desk while the application keeps its existing typed Python services, versioned
corpus, hybrid retrieval, semantic cache, OpenAI Responses adapter, and server-side citation
validation.

LangChain and LangSmith are different layers:

| Product | Role in this design |
| --- | --- |
| LangChain | Not required for the current request path. It may be considered later for a bounded tool workflow. |
| LangSmith | Optional trace collection, dataset management, evaluation runs, and quality analysis. |
| MTG-RAG services | Authoritative authentication, policy, retrieval, cache, generation, citations, persistence, and answer decisions. |

## 2. Design principles

1. **The answer path remains traditional RAG.** The backend retrieves evidence and asks the model
   to write from that bounded evidence.
2. **The server owns truth.** Corpus versions, active passages, cache compatibility, citation IDs,
   quotas, and abstention policy do not move into LangSmith or a generic framework.
3. **Observability is fail-open.** A LangSmith outage, timeout, or quota issue must not prevent a
   valid MTG answer from returning.
4. **Evaluation runs the real service.** Experiments must exercise the same cache, retrieval,
   generation, citation, and clarification logic used by the API.
5. **MTG correctness is deterministic where possible.** Exact references, citation validity,
   retrieval recall, and safety behavior are code-evaluated. LLM judges are supplemental.
6. **Data minimization is mandatory.** Traces contain identifiers, versions, metrics, and
   redacted payloads by default, not secrets or unrestricted user history.

## 3. Runtime placement

```text
Desktop or mobile browser
        |
        v
Firebase Hosting and Authentication
        |
        v
Cloud Run FastAPI service
        |
        v
AskApplicationService
  |  auth, quotas, conversation policy
  |  exact and semantic cache
  |  hybrid retrieval
  |  OpenAI generation
  |  citation validation and persistence
  |
  +---- always: Cloud Logging and Cloud Monitoring
  |
  +---- optional, sampled: LangSmith trace wrapper
              |
              v
        LangSmith project
        traces, datasets, experiments, feedback

Cloud SQL PostgreSQL + pgvector
Google Secret Manager
OpenAI Responses and Embeddings APIs
```

LangSmith is an analysis destination, not a proxy between Cloud Run and OpenAI. The backend
continues to call OpenAI directly with a server-side secret.

## 4. Trace boundary and span tree

The root trace wraps one `POST /v1/ask` execution. Nested spans describe the decisions that
matter for debugging and quality analysis:

```text
mtg.ask
  +-- request.policy
  |     +-- auth.verify
  |     +-- quota.check
  |     +-- conversation.snapshot
  +-- cache.exact_lookup
  +-- query.analyze
  +-- cache.semantic_lookup              [eligible standalone requests only]
  +-- retrieval.hybrid
  |     +-- retrieval.exact
  |     +-- retrieval.lexical
  |     +-- retrieval.vector
  |     +-- retrieval.rrf_fusion
  +-- generation.openai
  +-- citations.validate
  |     +-- citations.repair              [at most once]
  +-- response.commit
  +-- cache.semantic_write                [best effort]
```

The wrapper can use the LangSmith Python SDK's `traceable` function around existing service
methods. No `ChatOpenAI`, LangChain retriever, or LangChain agent is required. The direct OpenAI
Responses adapter remains the model boundary. LangSmith's tracing documentation supports wrapping
custom, non-LangChain functions with `traceable`.

### Trace metadata contract

Every root trace should include searchable metadata such as:

| Field | Example | Reason |
| --- | --- | --- |
| `request_id` | UUID | Correlate with Cloud Logging |
| `correlation_id` | UUID | Follow a request across services |
| `environment` | `staging` | Prevent mixing test and production traces |
| `corpus_versions` | rules/cards/rulings IDs | Explain which evidence was active |
| `embedding_model` | `text-embedding-3-small` | Detect vector incompatibility |
| `retrieval_version` | `retrieval-v3` | Compare retrieval changes |
| `prompt_version` | `grounded-v5` | Compare prompt changes |
| `generation_model` | configured model name | Compare answer behavior and cost |
| `cache_status` | `exact_hit`, `semantic_miss` | Diagnose reuse decisions |
| `citation_repaired` | boolean | Find grounding failures |
| `needs_clarification` | boolean | Measure ambiguity handling |
| `confidence` | `high`, `medium`, `low` | Segment quality analysis |
| `latency_ms` and token counts | numeric | Capacity and cost analysis |

Passage IDs, ranks, and scores may be recorded. Raw passage text, complete conversation history,
Firebase tokens, OpenAI keys, database credentials, and unnecessary personal data should be
redacted or omitted by default. A controlled staging mode may capture bounded evidence text for
debugging after access and retention have been reviewed.

## 5. Operational observability split

| Concern | System of record | LangSmith role |
| --- | --- | --- |
| Uptime, HTTP status, Cloud Run errors | Cloud Logging and Monitoring | Optional linked trace |
| Billing, quotas, database health | Google Cloud metrics and SQL telemetry | Supporting latency/token context |
| One request's RAG decisions | Cloud log correlation plus LangSmith trace | Interactive execution tree |
| MTG correctness gates | CI and `backend/app/evals/harness.py` | Experiment view and comparison |
| User feedback | Application database | Optional feedback attached to trace |

LangSmith must not become the only place where incidents, quotas, or audit records exist.

## 6. Evaluation architecture

```text
Versioned gold JSONL
  - question
  - expected rule/card/ruling references
  - expected behavior: answer, clarify, or abstain
  - category and expert review status
        |
        +------------------------------+
        |                              |
        v                              v
Existing deterministic harness       LangSmith private dataset
CI quality gate                       experiment and trace UI
        |                              |
        +--------------+---------------+
                       v
       Real MTG-RAG target function
       AskApplicationService.ask(...)
                       |
                       v
             evaluator results and traces
```

The target function must call the real application service with controlled dependencies or a
staging database. It must not call a simplified LangChain chain that bypasses semantic-cache
eligibility, active-passage checks, citation repair, or conversation policy.

### Evaluator layers

#### Required deterministic evaluators

These remain blocking gates in the existing evaluator and CI:

- Expected card or rule reference appears in retrieval results.
- Retrieval recall at the configured top-k.
- Every returned citation ID is known and active.
- Expected citations cover substantive claims.
- Answer, clarification, or abstention behavior matches the case.
- Negative semantic-cache pairs are never reused.
- Retrieved prompt-injection text does not override system policy.
- Latency and token budgets remain within the service thresholds.

#### Supplemental evaluators

LangSmith can add experiment-level evaluators for:

- Faithfulness to supplied passages.
- Explanation clarity and completeness.
- Whether assumptions are stated when a scenario is underspecified.
- Pairwise comparison of prompts, models, retrieval versions, or cache policies.
- Human MTG-expert review attached to a trace.

An LLM judge receives the question, structured answer, retrieved evidence identifiers or bounded
passages, and expected references. Its score is evidence for analysis, not proof that an answer is
rules-correct.

If bounded read-only tools are added later, trajectory evaluation should check tool name,
argument validation, call count, ordering, forbidden operations, and citation preservation.

## 7. Offline versus production evaluation

### Offline regression evaluation

- Use the versioned `backend/evals/mtg_rules_v1.json` as the seed dataset.
- Copy only reviewed, non-sensitive examples into a private LangSmith dataset.
- Tag every run with corpus, embedding, prompt, retrieval, and generation versions.
- Compare baseline direct-OpenAI runs against any future wrapper or tool mode.
- Keep CI thresholds in the local harness so a SaaS outage cannot bypass release gates.

### Staging traces

- Enable tracing for a dedicated staging LangSmith project.
- Capture full bounded inputs and evidence only after redaction checks pass.
- Inspect trace shape before writing evaluators that depend on nested fields.
- Verify that trace metadata maps back to Cloud Logging through `request_id`.

### Production traces

- Start with configurable sampling, such as 1 to 5 percent.
- Always trace failures, citation repairs, cache anomalies, and low-confidence responses where
  privacy policy permits.
- Keep production traces in a separate project with restricted access and a documented retention
  period.
- Never upload Firebase tokens, API keys, or raw account data.

## 8. Google Cloud integration

Cloud Run receives the LangSmith configuration from Secret Manager and runtime environment
bindings:

| Setting | Source | Notes |
| --- | --- | --- |
| `LANGSMITH_API_KEY` | Secret Manager | Server-side only; never a frontend variable |
| `LANGSMITH_PROJECT` | Cloud Run environment | Separate `mtg-rules-staging` and `mtg-rules-production` |
| `LANGSMITH_TRACING` | Cloud Run environment | Disabled by default locally; enabled selectively in staging/production |
| `LANGSMITH_ENDPOINT` | Cloud Run environment | Use the approved LangSmith endpoint |
| `LANGCHAIN_CALLBACKS_BACKGROUND` | Cloud Run environment, if needed | Ensure serverless trace delivery completes as configured |

The OpenAI API key remains a separate Secret Manager secret. Docker builds must not receive either
secret as a build argument, and the browser bundle must not contain them.

Tracing should be asynchronous or buffered where supported. A timeout or failed upload is logged
and discarded without changing the user-visible answer.

## 9. Security and privacy controls

- Use a separate LangSmith project per environment.
- Use least-privilege workspace access and rotate the LangSmith key through Secret Manager.
- Hash or omit user identifiers unless a support workflow requires correlation.
- Redact tokens, credentials, email addresses, and unrestricted conversation content.
- Do not automatically send every production query to a third-party evaluator.
- Use curated, expert-reviewed evaluation examples for offline datasets.
- Define retention, deletion, and data-region requirements before production tracing.
- Treat trace inputs and retrieved passages as untrusted data, just as the model does.
- Preserve existing citation and source-version controls in the application database.

## 10. Failure behavior

| Failure | User request behavior | Operational response |
| --- | --- | --- |
| LangSmith key missing | Answer path continues; tracing disabled | Alert only in environments where tracing is required |
| Trace upload timeout | Answer path continues | Record a local warning with request ID |
| LangSmith service unavailable | Answer path continues | Cloud Monitoring and local logs remain available |
| Evaluator unavailable | Deployment gate remains local CI harness | Retry experiment later |
| Trace schema changes | Answer path continues | Update wrapper and evaluator after inspecting a sample trace |
| Sensitive data detected | Redact or drop the span | Record a safe redaction counter |

## 11. Rollout plan

1. **Documentation and schema:** agree on the trace metadata and redaction contract.
2. **Offline evaluator integration:** run the existing gold set through a LangSmith target wrapper
   without enabling production tracing.
3. **Staging instrumentation:** add root and nested spans around the existing service and verify
   request correlation, payload redaction, and fail-open behavior.
4. **Production sampling:** enable a low sampling rate and always trace selected failure classes.
5. **Experiment workflow:** compare retrieval, prompt, model, and cache changes before release.
6. **Optional future tools:** only then evaluate LangChain or LangGraph for a bounded, allowlisted
   evidence workflow.

## 12. Code ownership map

| Concern | Current owner | Wrapper responsibility |
| --- | --- | --- |
| Request policy and orchestration | `backend/app/ask/service.py` | Add root span metadata without changing policy |
| Retrieval and RRF | `backend/app/retrieval/` | Add nested timing and result metadata |
| Semantic cache | `backend/app/cache/` | Record eligibility and hit/miss reason, never cache through LangSmith |
| OpenAI generation | `backend/app/generation/openai_adapter.py` | Trace model timing and usage with redaction |
| Citation validation | `backend/app/generation/` | Record validity, repair, and abstention outcomes |
| Deterministic evaluation | `backend/app/evals/harness.py` | Remains release authority |
| LangSmith adapter | Planned `backend/app/observability/` | Optional trace context, redaction, and fail-open delivery |
| LangSmith experiment target | Planned `backend/app/evals/` adapter | Calls the real ask service and returns a stable output schema |
| Cloud deployment | `infra/`, `cloudbuild.yaml` | Inject server-side LangSmith configuration |

## 13. Non-goals

- Replacing the current RAG retriever with a LangChain retriever.
- Giving an LLM unrestricted SQL, HTTP, or ingestion tools.
- Moving cache invalidation or citation authority into LangSmith.
- Treating an LLM judge as a substitute for MTG expert review.
- Uploading all user conversations to an external service by default.
- Making a SaaS tracing outage visible to end users as an application failure.

## 14. Related documents

- [System architecture](Architecture.md) for the complete runtime and data design.
- [Architecture essentials](architecture-essentials.md) for the concise learning guide.
- [Agent contract](agent.md) for grounding, citations, confidence, and abstention behavior.
- [Security model](../operations/SECURITY.md) for secret and trust-boundary controls.
- [Risk and edge-case audit](../operations/RISK-AND-EDGE-CASE-AUDIT.md) for residual risks.
