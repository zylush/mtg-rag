# MTG Rules Desk Architecture

**Status:** Development architecture implemented and verified; production launch gated
**Last reconciled:** 2026-08-15

## 1. Architectural objective

MTG Rules Desk is a traditional Retrieval-Augmented Generation application. It retrieves
versioned evidence before asking a model to produce a structured answer. The browser never calls
OpenAI, the model receives no arbitrary tools, and the backend owns authentication, retrieval,
citations, quotas, persistence, and policy enforcement.

## 2. System context

### Verified development delivery

```text
Desktop or mobile browser
        |
        v
Firebase Hosting
  - React PWA and static assets
  - same-origin /v1/** rewrite
        |
        v
Cloud Run FastAPI service, asia-east1
  - Firebase token verification
  - quotas, cache, retrieval, generation, history
        |
        +--> Cloud SQL PostgreSQL + pgvector
        +--> OpenAI Responses and Embeddings APIs
        +--> Secret Manager
        +--> Cloud Logging and Monitoring

Cloud Scheduler
        |
        v
Cloud Run ingestion job
        +--> WotC and Scryfall
        +--> GCS immutable snapshots
        +--> Cloud SQL staged and active corpora
```

The active development configuration uses `public_delivery_mode =
"firebase_hosting_proxy"`. Firebase Hosting serves the application and sends `/v1/**` requests
to Cloud Run. FastAPI still verifies every protected request.

### Production delivery option

```text
Browser --> Firebase Hosting frontend
    |
    +--> Google external Application Load Balancer
           |
           +--> HTTPS certificate and global IP
           +--> Cloud Armor policy
           +--> serverless NEG
                    |
                    v
              Cloud Run FastAPI service
```

When `public_delivery_mode = "load_balancer"`, Terraform creates the external load balancer,
Cloud Armor policy, managed certificate, HTTP-to-HTTPS redirect, global address, backend service,
and serverless network endpoint group. Cloud Run ingress is then restricted to internal traffic
and Cloud Load Balancing. The configured production Cloud Armor policy allows Taiwan, Japan,
South Korea, and Singapore and denies other countries by default.

Terraform declares and provisions these resources. Terraform does not handle user traffic, and
the load balancer does not create Cloud Run instances. The Cloud Run autoscaler creates and
removes instances according to demand and configured limits.

## 3. Major components

| Component | Technology | Responsibility |
| --- | --- | --- |
| Web client | React 19, TypeScript 6, Vite 8, Tailwind CSS 4 | Public pages, authentication UI, chat, citations, history, settings, PWA |
| Authentication | Firebase Authentication | Google sign-in and browser ID tokens |
| Static hosting | Firebase Hosting | PWA assets, SPA fallback, development `/v1/**` rewrite |
| API | Python 3.12, FastAPI, Uvicorn, Pydantic | Request boundaries, auth, quotas, RAG orchestration, user data |
| Generation | OpenAI Responses API | Structured answer from bounded retrieved evidence |
| Embeddings | OpenAI Embeddings API | 1,536-dimensional question and passage vectors |
| Database | Cloud SQL PostgreSQL | Application records, full-text indexes, semantic cache, active corpora |
| Vector search | pgvector | HNSW-indexed cosine-distance search |
| Ingestion | Cloud Run Job | Download, snapshot, parse, validate, embed, and activate sources |
| Snapshot storage | Google Cloud Storage | Immutable raw WotC and Scryfall payloads |
| Secrets | Secret Manager | Runtime OpenAI and database credentials |
| Scheduling | Cloud Scheduler | Daily ingestion trigger |
| Delivery | Cloud Build and Artifact Registry | Quality gates, image build, image publication, deployment |
| Infrastructure | Terraform | Repeatable development and production resources |
| Observability | Cloud Logging and Monitoring | Request timing, errors, alerts, and operational evidence |

## 4. Application request flow

An authenticated ask request follows this sequence:

1. The browser obtains a Firebase ID token and assigns a UUID to the user submission. An unchanged
   retry reuses that UUID; editing the question or conversation creates a new one.
2. The browser sends `POST /v1/ask` with the UUID to the configured same-origin or API endpoint.
3. FastAPI bounds request size and total request time.
4. The Firebase token is verified.
5. When context is enabled and a conversation ID is supplied, the backend loads an
   ownership-scoped snapshot of at most six messages and 6,000 serialized characters.
6. The application user is loaded or created and the `(user, request UUID)` claim is acquired.
   A completed match replays its stored response, a live duplicate returns a retryable conflict,
   and reuse with different content returns an idempotency conflict.
7. The rolling one-minute burst allowance is checked.
8. The backend loads active rules, cards, and rulings version IDs into a cache context.
9. Standalone requests check exact cache; contextual requests skip all shared cache operations.
10. The standalone question or deterministic contextual query is embedded once.
11. Eligible standalone questions check semantic cache similarity.
12. Exact, lexical, and vector retrieval run and their rankings are fused.
13. At most eight active passages are sent to OpenAI with the original question and separately
    labeled untrusted conversation messages.
14. The model returns a structured answer with internal passage IDs.
15. The backend validates citations, performs at most one repair call, and resolves canonical
    labels and URLs.
16. For a contextual request, the committer locks the conversation and returns `409` if its tail
    changed after the snapshot was loaded.
17. The answer, usage counter, conversation messages, citations, and replayable idempotency
    response are committed atomically.
18. A high-confidence eligible standalone answer is written to semantic cache. Cache-write failure is logged
    without failing the completed answer.

The query embedding generated at step 10 is reused by semantic-cache search and vector
retrieval. This avoids a second embedding call and guarantees both comparisons use the same query
vector.

## 5. Knowledge architecture

### Source precedence

1. Current WotC Comprehensive Rules for general game rules and glossary definitions.
2. Current Oracle text via Scryfall for what a card says.
3. Dated card rulings for card-specific clarification.

Ruling source and publication date are preserved. WotC-authored rulings receive a small ranking
bonus over Scryfall editorial rulings. Apparent source inconsistencies should expose source dates
and versions instead of being silently hidden.

### Document construction

- Numbered rules and subrules are atomic passages.
- Rule passages preserve canonical number, section, parent, neighboring references, and source
  version metadata.
- Glossary entries are separately retrievable and participate in whole-phrase exact lookup.
- Oracle cards are normalized by Oracle identity.
- Multi-face card text preserves printed face order.
- Rulings preserve Oracle identity, source, attribution, and publication date.
- Non-English and digital-only cards are excluded from the initial paper-card corpus.

## 6. Ingestion architecture

```text
Allowlisted HTTPS source
        |
        v
Bounded download and validation
        |
        v
Immutable GCS raw snapshot
        |
        v
Parser -> CorpusDocument records
        |
        v
Staged metadata and relationships
        |
        v
Reuse unchanged vectors; embed changed text
        |
        v
Validate counts, identities, duplicates, and links
        |
        v
Atomic source-version activation
```

Each source version records its URL, effective and fetch times, SHA-256 digest, parser version,
schema version, status, and active state. Identical downloaded content is idempotent. Changed
documents are embedded in batches; documents whose canonical key and content hash are unchanged
reuse their active vectors.

Any parse, staging, validation, or activation failure marks the ingestion run failed and preserves
the previous active source version. The GCS snapshot bucket enforces one-year object retention.
Raw snapshots and preceding active versions support audit and rollback.

### Embedding compatibility constraint

The current passage and semantic-cache columns are PostgreSQL `vector(1536)`. The configured
embedding model is `text-embedding-3-small` with 1,536 dimensions. The OpenAI adapter validates
response count, response indexes, and every vector length.

Cache context includes embedding model and dimensions, so changing them invalidates old answer
cache entries. Passage embedding reuse currently keys on canonical key and content hash. Therefore,
an embedding-model change requires a deliberate full corpus re-embedding and any required vector
column migration before the new model serves queries.

## 7. Retrieval architecture

### Query analysis

Question analysis trims and case-folds text while preserving meaningful MTG punctuation and rule
numbers. It identifies explicit rule references, quoted card names, active aliases, and glossary
phrases.

### Retrieval paths

| Path | Best for | Implementation |
| --- | --- | --- |
| Exact | Rule IDs, card names, aliases, glossary phrases | Deterministic active-record lookup |
| Lexical | Shared words and rules terminology | PostgreSQL `websearch_to_tsquery` and `ts_rank_cd` |
| Vector | Similar meaning expressed with different words | pgvector cosine distance |

Exact lookup never depends on embeddings. Lexical and vector paths each return at most twenty
candidates. Only active passages participate.

### Reciprocal-rank fusion

Raw lexical and cosine scores use different scales. Reciprocal-rank fusion combines positions
instead:

```text
score contribution = 1 / (60 + rank)
```

A passage found by multiple search paths accumulates contributions. Validated exact matches are
pinned first, followed by fused score and deterministic passage-ID tie-breaking. Generation
receives at most eight passages.

Vector retrieval intentionally has no absolute similarity cutoff. Exact and lexical evidence can
correct a semantically related but imprecise vector result. The `0.98` threshold belongs to
semantic answer-cache reuse, not passage retrieval.

## 8. Semantic-cache architecture

### Exact cache

The exact key hashes the normalized question together with:

- Active source version IDs.
- Embedding model and dimensions.
- Generation model.
- Prompt version.
- Retrieval version.
- Language.
- Corpus filters.

An exact cache hit skips the embedding and generation calls.

### Semantic cache

Semantic lookup compares the new question embedding with cached question embeddings using cosine
distance. Reuse requires:

- Similarity at least `0.98`, equivalent to cosine distance at most `0.02`.
- Exact cache-context equality.
- Expiration in the future and total TTL no greater than seven days.
- Every stored citation still referring to an active passage.
- A high-confidence eligible question profile.

Eligible profiles are simple definitions, direct rule lookups, and policy-supported card-text
questions with at most one detected card and no multiplayer or ambiguous state. The current
request heuristic directly recognizes definitions and explicit rule references; other questions
default to scenario handling. Complex scenarios are regenerated rather than semantically reused.

## 9. Generation and citation architecture

The model receives the original question, bounded structured conversation messages, and a JSON
representation of retrieved passages. System instructions state that history and passages are
untrusted reference data, not instructions, and that prior assistant text is not evidence. Only
current retrieved passage IDs can satisfy citation requirements. The model is given no SQL, HTTP,
ingestion, or general-purpose tools.

The required response schema contains:

```json
{
  "answer": "string",
  "citations": [{"passage_id": "uuid", "claim": "string"}],
  "assumptions": ["string"],
  "confidence": "high | medium | low",
  "needs_clarification": false
}
```

The backend, not the model, maps passage IDs to canonical labels and URLs. Unknown IDs trigger one
bounded repair. If repair fails, the service replaces unsupported prose with a low-confidence
abstention. Active citation IDs are checked again during the atomic answer commit.

The confidence label is model-reported and is not a calibrated probability. It is one input to
cache eligibility. Correctness depends on retrieval quality, source authority, citation support,
clarification behavior, and independent evaluation.

## 10. Persistence model

| Entity group | Main records |
| --- | --- |
| Source control | `source_versions`, `ingestion_runs` |
| Rules | `rule_sections`, `glossary_entries` |
| Cards | `cards`, `card_faces`, `card_aliases`, `rulings` |
| Retrieval | `passages` with full-text and HNSW vector indexes |
| Cache | `semantic_cache_entries` with question vectors and version context |
| Identity and limits | `application_users`, `daily_usage`, `ask_attempts` |
| Conversation | `conversations`, `messages`, `answer_citations` |
| Product feedback | `feedback` |

Firebase UID is the external identity key. Application UUIDs are used internally. Conversation
ownership and active citation membership are enforced by backend repository operations.

## 11. API architecture

| Method and path | Boundary |
| --- | --- |
| `GET /healthz` | Unauthenticated process-health response |
| `POST /v1/ask` | Authenticated, burst-limited, daily successful-answer quota |
| `GET /v1/conversations` | Authenticated current-user list |
| `GET /v1/conversations/{id}` | Authenticated ownership check |
| `DELETE /v1/conversations/{id}` | Authenticated ownership check and permanent deletion |
| `POST /v1/feedback` | Authenticated answer ownership check |
| `DELETE /v1/account` | Authenticated application-data and Firebase-account deletion |

There are no public source-download, ingestion, arbitrary URL, raw SQL, or general model-tool
endpoints.

## 12. Security and trust boundaries

### Browser boundary

- The browser receives Firebase public configuration, never the OpenAI or database credential.
- Firebase ID tokens are sent to FastAPI and verified for protected routes.
- Rendered Markdown has raw HTML disabled and citation links are server-generated and sanitized.
- CORS is restricted to the configured frontend origin.

### API boundary

- Maximum question length: 2,000 characters.
- Maximum request body: 64 KiB.
- Maximum response body: 1 MiB.
- Application request timeout: 30 seconds.
- Cloud Run and load-balancer timeout: 40 seconds.
- OpenAI client timeout: 30 seconds with bounded retries.
- Five ask attempts per user per minute and twenty successful answers per UTC day.

### Retrieval boundary

- Retrieved text is untrusted data and cannot change system instructions.
- Only active, server-owned passages and citation URLs are exposed to generation.
- Context is bounded to eight passages.
- The model has no arbitrary SQL or network tools.

### Secret boundary

- Secret Manager injects OpenAI and database credentials into server-side runtime identities.
- Secrets are excluded from the frontend, source maps, Docker build arguments, image layers,
  Terraform variables, repository, and content logs.
- API, ingestion, and migration identities receive only required roles.

Detailed controls and residual risks are maintained in
[SECURITY.md](../operations/SECURITY.md).

## 13. Scaling and cost behavior

Cloud Run autoscaling is independent of the delivery path. Firebase Hosting or the external load
balancer routes requests; the Cloud Run autoscaler creates and removes API instances.

Development configuration:

- Minimum instances: zero.
- Maximum instances: three.
- Maximum concurrent requests per instance: twenty.
- CPU: one vCPU.
- Memory: 1 GiB.

This is a maximum of roughly sixty in-flight requests, not sixty total users and not a throughput
guarantee. OpenAI latency, CPU, Cloud SQL connections, cache hit rate, and request mix determine
real capacity. Per-user quotas and cloud budget alerts protect different cost dimensions. The
instance cap alone does not cap OpenAI, Cloud SQL, storage, logging, or networking costs.

The API backend does not use Cloud CDN because answers are authenticated and version-sensitive.
Static PWA assets can be cached by Firebase Hosting. Answer reuse is controlled by the semantic
cache inside the application.

## 14. Failure behavior and recovery

| Failure | Expected behavior |
| --- | --- |
| Invalid or missing Firebase token | Return `401`; do not expose protected data |
| Burst or daily quota exhausted | Return `429` with an appropriate user message |
| Required corpus missing | Return `503`; do not generate from incomplete sources |
| Request exceeds application timeout | Return bounded `504` response |
| Cache unavailable or write fails | Continue with fresh retrieval/generation when possible |
| Retrieval or model fails | Return bounded error; do not consume successful-answer quota |
| Conversation tail changed | Return `409`; commit no message pair or successful-answer quota |
| Unknown generated citation | One repair call, then low-confidence abstention |
| Ingestion parse or validation fails | Keep the preceding active corpus |
| Bad application revision | Roll back Cloud Run to a known image |
| Bad active source version | Run the corpus rollback command |

Operational procedures are in [OPERATIONS.md](../operations/OPERATIONS.md).

## 15. Observability and verification

Request logs record request ID, method, route, status, duration, error category, cache status,
source versions, model metadata, token usage, and citation-repair status without raw conversation
content or secrets.

Quality gates include:

- Backend unit and PostgreSQL integration tests with at least 80 percent branch coverage.
- Frontend unit, accessibility, responsive, navigation, and multi-browser Playwright tests.
- Dependency audits, secret scans, non-root image checks, and image vulnerability scans.
- Terraform formatting and validation.
- A versioned 121-case RAG evaluation suite covering retrieval, citations, ambiguity, abstention,
  prompt injection, follow-up context, and semantic-cache adversarial pairs.

## 16. Code map

| Concern | Location |
| --- | --- |
| API construction and routes | `backend/app/api/app.py` |
| Runtime dependency wiring | `backend/app/runtime.py` |
| Settings and limits | `backend/app/config.py` |
| Ask orchestration | `backend/app/ask/service.py` |
| Query analysis | `backend/app/retrieval/analysis.py` |
| Hybrid retrieval | `backend/app/retrieval/service.py` |
| Exact, lexical, vector SQL | `backend/app/retrieval/repository.py` |
| Rank fusion | `backend/app/retrieval/fusion.py` |
| OpenAI embeddings | `backend/app/retrieval/embeddings.py` |
| Semantic cache policy and storage | `backend/app/cache/` |
| Model prompt and Responses adapter | `backend/app/generation/openai_adapter.py` |
| Citation validation and repair | `backend/app/generation/` |
| Rules and Scryfall parsing | `backend/app/ingestion/` |
| Database schema | `backend/app/db/models.py`, `backend/migrations/` |
| Evaluation harness and suite | `backend/app/evals/`, `backend/evals/` |
| React application | `frontend/src/` |
| Firebase delivery | `firebase.json` |
| Google Cloud infrastructure | `infra/` |
| Build and release pipeline | `cloudbuild.yaml` |

## 17. Architectural decisions

- Traditional RAG instead of an autonomous agent loop for bounded behavior and testability.
- PostgreSQL as the initial system of record for application data, retrieval, quotas, locks, and
  semantic cache. Redis is deferred until measured load justifies it.
- Exact retrieval before embeddings for rules identifiers and named MTG entities.
- Version-aware caching instead of a global answer cache.
- Firebase Hosting proxy for development simplicity; external load balancer remains a production
  delivery option requiring its own domain, controls, and cost.
- Cloud SQL owns history; OpenAI Responses requests use `store=false`.
- No card images or flavor-text corpus in v1 because they do not improve rules grounding.

## 18. Related documents

- [PRD.md](../PRD.md): product requirements, user experience, metrics, and launch gates.
- [architecture-essentials.md](architecture-essentials.md): concise architecture learning guide.
- [agent.md](agent.md): RAG agent contract and safeguards.
- [OPERATIONS.md](../operations/OPERATIONS.md): deploy, rollback, recovery, and incident procedures.
- [SECURITY.md](../operations/SECURITY.md): security model and evidence.
- [INTEGRATION-LESSONS.md](../operations/INTEGRATION-LESSONS.md): development issues and lessons.
