# MTG Rules Desk - Architecture and Delivery Plan

**Status:** Development integration complete; public production launch gated
**Last reconciled:** 2026-08-14
**Product:** English-language MTG rules expert delivered as an installable desktop PWA on Google Cloud.

This is the canonical product, architecture, security, and release plan. [`plan.md`](plan.md)
is the scoped implementation record for the public UX, legal-page, navigation, responsive-browser,
and development-safe SEO work. Verified development
evidence and lessons are recorded in [`INTEGRATION-LESSONS.md`](INTEGRATION-LESSONS.md);
the current ship/block assessment is in
[`PRODUCTION-AUDIT.md`](PRODUCTION-AUDIT.md).

Status terms in this document are deliberate:

- **Implemented** means the behavior exists in the repository and passed its documented checks.
- **Development verified** means it was also exercised in `mtg-rules-desk-dev`.
- **Production pending** means public launch still needs human approval, operator-owned
  production configuration, or production-specific evidence.

## 1. Product and Architecture

Build a traditional RAG application, not an autonomous agent loop. It will answer questions using three versioned knowledge sources:

1. Wizards of the Coast Comprehensive Rules.
2. Oracle card data through Scryfall Bulk Data.
3. Card rulings through Scryfall Bulk Data, ranking WotC-authored rulings above Scryfall editorial rulings.

The web client will be an installable PWA. Users must sign in, receive 20 completed answers per UTC day, retain conversation history until deletion, and be able to delete conversations or their account.

Initial public availability is restricted to Taiwan, Japan, South Korea, and Singapore. The application will be English-only and will not provide offline answers.

The diagram below is the production target. The verified development environment instead
uses a Firebase Hosting same-origin `/v1/**` rewrite to Cloud Run. Production must resolve
the delivery-mode decision in Section 10 before deployment.

```text
React PWA ── Firebase Authentication
     │
     ▼
Google Load Balancer + Cloud Armor
     │
     ▼
Cloud Run FastAPI service
     ├── OpenAI Responses API
     ├── Cloud SQL PostgreSQL + pgvector
     ├── Secret Manager
     └── Cloud Logging/Monitoring

Cloud Scheduler
     │
     ▼
Cloud Run ingestion job
     ├── WotC rules
     ├── Scryfall Oracle cards
     ├── Scryfall rulings
     └── GCS versioned snapshots
```

## 2. Technology Stack

### Frontend

- React and TypeScript.
- Vite for builds.
- Tailwind CSS for styling.
- TanStack Query for server state.
- Firebase Authentication SDK.
- `vite-plugin-pwa` for installation, manifests, and static asset caching.
- Markdown renderer with raw HTML disabled and sanitized citation links.
- Vitest, React Testing Library, and Playwright.

Host the static frontend with Firebase Hosting.

### Backend and RAG

- Python 3.12.
- FastAPI, Uvicorn, Pydantic 2.
- SQLAlchemy 2 and Alembic.
- PostgreSQL full-text search, `pg_trgm`, and `pgvector`.
- OpenAI Python SDK and Responses API.
- `httpx` and `tenacity` for bounded downloads and retries.
- `pytest`, `pytest-cov`, Ruff, mypy, and `pip-audit`.

Use custom, deterministic retrieval orchestration instead of an agent framework or unrestricted model tools.

### OpenAI defaults

- Generation model: `gpt-5.6-luna`.
- Embedding model: `text-embedding-3-small`.
- Embedding column: `vector(1536)`.
- Responses API requests use `store=false`; Cloud SQL owns conversation history.
- Keep model names configurable and pin a tested snapshot before production deployment.
- Record model, request ID, latency, and token usage without logging prompts or answers.

These defaults reflect current official model and embedding guidance as of August 12, 2026. Revalidate them before production deployment. See the [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model) and [embeddings guide](https://developers.openai.com/api/docs/guides/embeddings).

### Google Cloud

- `asia-east1` for Cloud Run, Cloud Run Jobs, Cloud SQL, Artifact Registry, and regional storage.
- Development: Firebase Hosting proxies same-origin `/v1/**` traffic to Cloud Run; the
  FastAPI layer still verifies Firebase tokens on every protected route.
- Production target: External Application Load Balancer with serverless NEG, Cloud Armor
  geo-allowlist for `TW`, `JP`, `KR`, and `SG`, and Cloud Run ingress restricted to
  internal traffic and Cloud Load Balancing.
- Cloud SQL for PostgreSQL with `vector`, `pg_trgm`, and full-text indexes.
- Google Cloud Storage for immutable raw-source snapshots.
- Secret Manager for `OPENAI_API_KEY`.
- Cloud Scheduler for daily ingestion.
- Artifact Registry and Cloud Build for images and CI/CD.
- Terraform for repeatable development and production environments.
- Docker Compose for local development.

Do not introduce Redis/Memorystore in v1. Store quotas, locks, and semantic-cache entries in PostgreSQL until measured load justifies another service.

## 3. Knowledge Pipeline and Retrieval

### Versioned ingestion

Run an idempotent Cloud Run Job daily at `18:00 UTC`.

For every changed source:

1. Download over HTTPS from allowlisted hosts with timeout, size, MIME, and schema validation.
2. Store the immutable raw payload in GCS.
3. Record URL, effective date, fetched date, SHA-256, parser version, and schema version.
4. Parse into staging tables.
5. Validate minimum record counts, identities, relationships, and duplicate rates.
6. Embed only new or changed passages.
7. Atomically activate the new source version.
8. Preserve the preceding version for immediate rollback.

A failed refresh must leave the previous source version active. Retain activated raw snapshots for one year and at least the two newest versions.

### Document construction

- Split Comprehensive Rules on numbered rules and subrules, never arbitrary token boundaries.
- Attach section heading, parent rule, neighboring references, effective date, and canonical rule number.
- Parse glossary entries as separately retrievable passages.
- Store one normalized document per Oracle card identity.
- Combine multiface card faces in printed order.
- Store individual rulings with Oracle ID, publication date, source, and attribution.
- Exclude non-English and digital-only cards from the initial corpus.

### Retrieval flow

1. Normalize the question and identify explicit card names and rule references.
2. Perform exact card-name, alias, or rule-number lookup first.
3. Run lexical PostgreSQL full-text search and vector similarity search.
4. Fuse the top 20 results from each path using reciprocal-rank fusion.
5. Pin valid exact matches above approximate matches.
6. Send no more than eight passages to the generation model.
7. Ask for clarification when missing zone, timing, controller, ownership, or game-state details could change the result.

The model returns a structured object containing:

```json
{
  "answer": "string",
  "citations": [
    {
      "passage_id": "string",
      "claim": "string"
    }
  ],
  "assumptions": ["string"],
  "confidence": "high | medium | low",
  "needs_clarification": false
}
```

The backend resolves passage IDs into canonical citations. Unknown citation IDs trigger one repair attempt; if still invalid, return a grounded abstention instead of unsupported prose.

### Semantic cache

Use two cache layers:

- Exact cache keyed by normalized request and configuration versions.
- Semantic cache using the question embedding and `pgvector`.

A semantic cache entry is reusable only when all of the following match:

- Active corpus versions.
- Embedding model and dimensions.
- Generation model.
- Prompt and retrieval versions.
- Language and applicable filters.
- Citation IDs remain active.
- Cosine similarity meets the initial configurable threshold of `0.98`.

Cache only high-confidence, citation-valid definitions, direct rule lookups, and card-text questions. Do not semantically cache ambiguous scenarios, multiplayer interactions, or complex multi-card questions.

Use a seven-day maximum TTL and immediate logical invalidation when a corpus, model, prompt, or retrieval version changes. Cache entries must not contain user IDs. Cache hits still consume the daily user allowance.

## 4. Public Interfaces and Data

### API endpoints

- `POST /v1/ask` — authenticated request with `conversation_id?` and a question of at most 2,000 characters.
- `GET /v1/conversations` — list the current user’s conversations.
- `GET /v1/conversations/{id}` — retrieve an owned conversation.
- `DELETE /v1/conversations/{id}` — permanently delete an owned conversation.
- `POST /v1/feedback` — submit answer rating and optional comment.
- `DELETE /v1/account` — delete application data and the Firebase account.
- `GET /healthz` — minimal unauthenticated health response.

The `/healthz` process-health endpoint is used by native Cloud Run startup and liveness
probes. It is not exposed as a supported Firebase Hosting route; the development edge smoke
test is an unsigned protected `/v1` request returning backend JSON `401`.

There will be no public ingestion, arbitrary URL, raw SQL, or general-purpose model-tool endpoint.

### Core database entities

- Source versions and ingestion runs.
- Rule sections and glossary entries.
- Cards, card faces, and aliases.
- Rulings.
- Passage embeddings.
- Semantic-cache entries.
- Application users and daily usage counters.
- Conversations and messages.
- Answer citations and feedback.

Use Firebase UID as the application-user identity. Every history operation must enforce ownership in the backend.

### Rate and quota rules

- Limit: 20 successful answers per user per UTC day.
- Burst limit: five ask requests per minute per user.
- Failed authentication, validation, retrieval, or generation attempts do not consume quota.
- Concurrent requests must update quota atomically.
- Cache hits count as successful answers.

## 5. Security and Operations

- Store `OPENAI_API_KEY` only in Secret Manager.
- Grant secret access only to dedicated API and ingestion service accounts.
- Inject the secret at runtime; never place it in the Dockerfile, image layers, frontend variables, repository, build arguments, or logs.
- Verify Firebase ID tokens for every protected endpoint.
- Restrict CORS to the production frontend domain.
- Treat retrieved documents as untrusted reference material, never instructions.
- Sanitize rendered Markdown and allow only server-generated citation links.
- Apply HTTPS, response-size limits, input limits, request timeouts, and bounded retries.
- Log IDs, timings, token counts, cache status, source versions, and error categories; omit API keys and raw conversation content.
- Enable Cloud SQL backups and point-in-time recovery. Use regional HA in production and a smaller single-zone development instance.
- Start Cloud Run with zero minimum instances, maximum ten instances, and concurrency 20; adjust only from measured load.
- Configure budget alerts at 50%, 80%, and 100% of the owner-provided monthly budget.
- Support rollback to the previous Cloud Run revision and previous active corpus version.

Before public launch, confirm WotC and Scryfall attribution, data-use, and redistribution requirements. Follow the current [OpenAI supported-country policy](https://developers.openai.com/api/docs/supported-countries).

## 6. Delivery Status and Remaining Sequence

| Delivery slice | Status | Primary evidence |
| --- | --- | --- |
| Repository, Docker Compose, dependency manifests, linting, typing, and test harness | Implemented | `README.md`, CI, and local verification commands |
| PostgreSQL/pgvector schema, migrations, fixtures, and immutable source versions | Development verified | Migration and ingestion integration tests |
| WotC and Scryfall parsing, staged ingestion, deduplication, and atomic activation | Development verified | Three active corpora and idempotent live re-ingestion |
| Exact, lexical, vector, and fused retrieval | Development verified | Retrieval tests and the live glossary-plus-card answer |
| Version-aware semantic caching | Implemented | Cache eligibility, invalidation, and negative-pair tests |
| OpenAI Responses adapter, citation validation, abstention, and clarification | Development verified | Real authenticated multi-source answer with validated citations |
| Firebase authentication, quota, history, deletion, and feedback APIs | Development verified | Protected edge checks and authenticated browser flow |
| React PWA, public pages, chat, source display, route-backed history/settings, installation, and development-safe SEO | Development verified | 36 unit tests, 80 cross-browser scenarios, PWA checks, and live Firebase QA; see `plan.md` Revision 3 |
| Terraform, Cloud Build, Artifact Registry, Cloud Run, Cloud SQL, Scheduler, monitoring, and Firebase Hosting | Development verified | Successful build/deploy and drift-free development plan |
| Independent evaluation, legal approval, production environment, and controlled launch | Production pending | See Section 10 |

All implementation slices continue to follow test-driven development and maintain at least
80% branch coverage. The remaining sequence is:

1. Resolve the WotC policy/access decision and replace legal/support placeholders with
   reviewed, operator-owned copy.
2. Obtain independent MTG rules-expert approval of the 110-case gold suite, execute it
   against a production-like corpus, and record every release metric in Section 7.
3. Decide the production delivery path, then configure the production project, domain/DNS,
   budget, alert recipients, secrets, and regional infrastructure without copying development
   credentials or state. A load-balancer API domain requires production frontend support for
   that separate origin; a Firebase proxy requires a production-specific rewrite and an
   alternative that enforces the promised regional availability.
4. Run migration, ingestion, backup/restore, rollback, alert-delivery, and account-deletion
   drills; then make a documented human go/no-go decision.

## 7. Test and Acceptance Plan

### Automated tests

- Unit tests for parsers, multiface normalization, deduplication, cache keys, cache eligibility, citation validation, quotas, and ownership.
- Integration tests for fixture ingestion into PostgreSQL, idempotent refreshes, hybrid retrieval, version rollback, fake OpenAI responses, and Firebase token verification.
- End-to-end tests for sign-in, asking a question, viewing citations, opening history, deleting history, quota enforcement, account deletion, and PWA installation.
- Security checks with dependency audits, secret scanning, container-image inspection, authorization tests, injection attempts, and malicious retrieved content.
- Accessibility checks against WCAG 2.1 AA for keyboard navigation, focus, contrast, labels, and screen-reader structure.

### RAG evaluation set

Maintain at least 100 versioned, expert-reviewed questions covering:

- Exact rule-number lookups.
- Card Oracle text.
- Glossary definitions.
- Layers and continuous effects.
- Replacement effects and triggered abilities.
- State-based actions and priority.
- Multifaced cards and zones.
- Ambiguous situations requiring clarification.
- Unsupported questions requiring abstention.
- Prompt injection embedded in retrieved content.
- Semantic-cache positive and adversarial negative pairs.

### Release gates

- Retrieval recall@8 of at least 90% for expected cards and rule references.
- Citation identifiers valid in 100% of evaluated responses.
- Citation precision of at least 95%.
- Clarification or abstention accuracy of at least 90%.
- Zero incorrect semantic-cache reuse across the maintained negative-pair suite.
- Retrieval latency p95 at or below 500 ms in staging.
- Cached-response API latency p95 at or below 1.5 seconds in staging.
- At least 80% backend branch coverage.
- All integration, end-to-end, security, and PWA checks passing.
- No OpenAI credential present in source maps, browser traffic, repository history, Docker layers, or logs.
- New ingestion failures proven unable to replace an active healthy corpus.

## 8. Explicit v1 Boundaries and Assumptions

- The first release is a rules, Oracle-text, and rulings expert.
- Strategy, deck building, card prices, tournament policy, metagame advice, and broad format-legality analysis are excluded.
- There is no autonomous agent loop, native desktop wrapper, or offline answer generation.
- The browser never calls OpenAI directly.
- The operator supplies Google Cloud, Firebase, OpenAI, billing, and domain access.
- Numeric cloud budget and final domain names are deployment configuration, not architecture decisions.
- The project began as a greenfield workspace. It now has persistent schema, API, corpus,
  deployment, and user-data contracts; future changes must preserve or explicitly migrate them.

## 9. Development Integration Status - 2026-08-14

The development environment has implemented the architecture through the controlled
pre-production stage:

- Firebase Hosting serves the installable PWA at
  `https://mtg-rules-desk-dev.web.app` and rewrites same-origin API requests to Cloud Run.
- Firebase Authentication has Google sign-in enabled; the backend verifies Firebase ID
  tokens and keeps all protected endpoints closed to signed-out requests.
- The FastAPI service, migration job, and ingestion job run as Docker images in Cloud Run;
  Cloud SQL/pgvector holds the application data and active versioned corpora.
- WotC Comprehensive Rules, Scryfall Oracle cards, and rulings are active as three separate
  source versions, with immutable raw snapshots and idempotent refresh behavior.
- `OPENAI_API_KEY` is stored in Secret Manager and injected only into server-side runtime
  identities. The browser uses Firebase configuration only and never receives that secret.
- Artifact Registry, Cloud Build, Scheduler, monitoring, alerts, and Terraform-managed IAM
  are provisioned in `asia-east1` for project `mtg-rules-desk-dev`.

This status completes the engineering integration target for development. On 2026-08-14,
a real Google-account browser flow returned a high-confidence, multi-source answer citing
the Comprehensive Rules glossary and Lightning Bolt Oracle text, and persisted it to History.
The external public-launch approvals listed in the release gates remain deliberately separate
acceptance items. See `docs/INTEGRATION-LESSONS.md` for the issue-by-issue postmortem.

## 10. Active Public-Launch Gates

These criteria are intentionally not marked complete by a successful development deployment.

The active frontend refinement and development-hosting deployment is specified in
[`plan.md`](plan.md#revision-3-implementation-plan). It may update Firebase Hosting for
`mtg-rules-desk-dev`, but it does not satisfy or waive any public-launch gate below. In particular,
the development host remains crawler-blocked until the production domain, legal copy, attribution,
and release decision are approved.

### AC-LAUNCH-001: Policy and legal approval

- **Scenario:** The service requires sign-in and is intended for public access in the listed regions.
- **Expected:** A qualified reviewer records a resolution to the WotC policy/access question,
  approves attribution, and replaces the Terms, Privacy, support, owner, jurisdiction, retention,
  and effective-date placeholders.
- **Must not:** Present draft outlines as approved legal terms or imply WotC/Scryfall endorsement.
- **Verification:** Named and dated approval record using
  [`ATTRIBUTION-AND-LAUNCH.md`](ATTRIBUTION-AND-LAUNCH.md).
- **Status:** Production pending.

### AC-LAUNCH-002: Independent rules quality approval

- **Scenario:** The versioned 110-case suite has been reviewed by an independent MTG rules expert.
- **Expected:** A production-like evaluation run passes every retrieval, citation,
  clarification/abstention, cache-safety, and latency threshold in Section 7.
- **Must not:** Use `--allow-pending-review` as launch evidence.
- **Verification:** Approved suite plus a retained evaluator report tied to corpus, prompt,
  retrieval, embedding, and generation versions.
- **Status:** Production pending.

### AC-LAUNCH-003: Production operational readiness

- **Scenario:** Operator-owned production configuration, DNS, budget, alert recipients, and
  secrets are available.
- **Expected:** The operator chooses and documents one production delivery mode. If using the
  load balancer, the frontend calls the reviewed API domain and Cloud Armor enforces the regional
  allowlist. If using Firebase's same-origin proxy, the production rewrite targets only the
  production service and a reviewed control enforces the regional availability promise.
  Deployment, migration, ingestion, alert delivery, backup/restore, application rollback,
  corpus rollback, and Firebase account-deletion drills then succeed with retained evidence.
- **Must not:** Reuse development credentials, expose secrets to build/frontend artifacts, or
  deploy a production bundle that calls the wrong origin. Do not declare readiness from
  Terraform validation alone.
- **Verification:** Complete the production checklist in
  [`OPERATIONS.md`](OPERATIONS.md) and update the production audit.
- **Status:** Production pending.

### AC-LAUNCH-004: Final release decision

- **Scenario:** AC-LAUNCH-001 through AC-LAUNCH-003 are complete and no release gate in Section 7 fails.
- **Expected:** A named owner records the release version, evidence links, known limitations,
  rollback target, and go/no-go decision before enabling public production access.
- **Must not:** Treat the development Firebase URL as the public production release.
- **Verification:** Human release sign-off and post-deploy protected/public endpoint smoke tests.
- **Status:** Blocked by AC-LAUNCH-001 through AC-LAUNCH-003.
