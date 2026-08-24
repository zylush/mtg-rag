# MTG Rules Desk Product Requirements Document

**Status:** Development implementation verified; public production launch gated
**Revision:** 1
**Last reconciled:** 2026-08-15
**Product:** English-language, citation-first Magic: The Gathering rules assistant

## 1. Product summary

MTG Rules Desk helps players resolve Magic: The Gathering rules questions without searching a
large rulebook manually. It retrieves evidence from versioned rules, Oracle card text, and card
rulings before an OpenAI model writes an answer. Every supported material claim is expected to
have a source citation.

The product is a traditional Retrieval-Augmented Generation system, not an autonomous agent
loop. The model cannot browse the web, issue SQL, or choose arbitrary tools.

The initial public-release plan is English-only and limited to Taiwan, Japan, South Korea, and
Singapore, subject to the production delivery and policy gates in this document.

## 2. Problem

Magic rules questions can depend on exact card wording, numbered rules, glossary definitions,
timing, zones, controller, ownership, and game state. A language model answering from memory can
use outdated wording or produce unsupported explanations. Players need a faster interface that
still exposes the evidence used for the answer.

## 3. Intended users and jobs

### Players and local rules helpers

- Ask an English-language rules question during or after a game.
- See the answer, assumptions, confidence label, and supporting sources.
- Continue a conversation and return to saved history.
- Delete individual conversations or the entire account.

### Operator

- Refresh WotC and Scryfall sources without replacing a healthy corpus with a failed import.
- Monitor cost, latency, ingestion, retrieval, and model failures.
- Roll back the application or active corpus.
- Review evaluation, legal, attribution, and operational evidence before launch.

## 4. Product principles

1. Evidence before prose.
2. Exact identifiers before approximate similarity.
3. Clarification before guessing.
4. Abstention before unsupported claims.
5. User secrets and provider credentials stay on the server.
6. Source versions and citations remain auditable.
7. Development verification is not public-launch approval.

## 5. Goals

- Answer supported MTG rules, Oracle-text, and dated ruling questions with citations.
- Prefer deterministic card, rule-number, alias, and glossary lookup when possible.
- Support conceptual questions through hybrid lexical and vector retrieval.
- Provide an installable desktop and mobile browser experience.
- Keep public rules questions free without account/email registration; require Google sign-in only
  for saved history, feedback, quotas, and account controls.
- Keep source refreshes versioned, idempotent, validated, and reversible.
- Control model cost through quotas, bounded context, autoscaling limits, and safe caching.
- Make failure visible through clarification, abstention, user-facing errors, and operational logs.

## 6. Non-goals for v1

- Strategy or deck-building recommendations.
- Card prices, market data, or metagame analysis.
- Tournament policy or judge certification guidance.
- Broad format-legality analysis.
- Offline answer generation.
- Multilingual answers.
- Native desktop binaries.
- An autonomous tool-using model loop.
- A public ingestion endpoint, arbitrary source URLs, raw SQL, or general web browsing.

## 7. Product scope and current status

| Capability | Requirement | Current status |
| --- | --- | --- |
| Public experience | Welcome, About, operational Terms/Privacy, attribution, support, and a free no-account question path | Development verified |
| Authentication | Direct Google sign-in through Firebase Authentication | Development verified |
| Rules chat | Free public question path plus authenticated citation-first history flow | Development verified |
| Knowledge | Versioned rules, cards, and rulings corpora | Development verified |
| Retrieval | Exact, lexical, vector, and fused ranking | Development verified |
| Generation | Structured answer, citation validation, repair, and abstention | Development verified |
| User data | History, feedback, conversation deletion, account deletion | Development verified |
| PWA | Installable responsive React application | Development verified |
| Infrastructure | Cloud Run, Cloud SQL, GCS, Secret Manager, Scheduler, Cloud Build | Development verified |
| Public launch | Legal, independent rules evaluation, production configuration, recovery drills | Pending |

## 8. User experience and navigation

### Public routes

| Route | Behavior |
| --- | --- |
| `/` | Welcome page with product purpose, cited-answer preview, free public question form, limitations, and optional sign-in |
| `/about` | Methodology, scope, attribution, limitations, and account controls |
| `/terms` | Operational Terms with public access, attribution, AI limits, deletion, and support; pending qualified legal review |
| `/privacy` | Implementation-aligned Privacy Policy covering public questions, accounts, providers, cache, deletion, and support |

### Authenticated routes

| Route | Behavior |
| --- | --- |
| `/desk` | Rules chat and cited answers |
| `/desk/history` | Route-backed conversation-history drawer |
| `/desk/settings` | Route-backed settings, product links, installation, and account controls |

Public sign-in controls invoke Firebase Google authentication directly. Signed-out access to a
desk route returns to `/`. Successful authentication routes to `/desk`. Logout and account
deletion return to `/`. Legacy `/login` and `/auth` paths normalize to the first screen.

The desktop experience uses a persistent side navigation. Compact browser widths use a single
mobile navigation pattern. History and Settings behave as labelled modal drawers with focus
entry, Escape handling, and focus restoration.

## 9. Functional requirements

### FR-001: Authoritative knowledge sources

The system shall maintain three independently versioned corpora:

1. WotC Comprehensive Rules for general rules and glossary definitions.
2. Oracle card data through Scryfall Bulk Data for current card wording.
3. Card rulings through Scryfall Bulk Data, preserving source and date and ranking WotC-authored
   rulings above Scryfall editorial rulings.

The answer must expose source identity and version metadata when needed to explain inconsistency
or freshness.

### FR-002: Versioned ingestion

The scheduled or manually invoked ingestion job shall download only allowlisted HTTPS sources,
store immutable raw snapshots, parse into staging, validate record counts and relationships,
embed new or changed passages, and atomically activate a complete version. A failed import must
leave the previous active version available.

### FR-003: Authenticated question submission

`POST /v1/ask` shall require a valid Firebase ID token, a caller-generated UUID request ID, and a
question of at most 2,000 characters with an optional owned conversation ID. Reusing the UUID for
the same request shall replay the one committed response without consuming quota or creating
messages again. Reusing it for different request content shall return a non-disclosing conflict,
and a concurrent duplicate shall not execute downstream work. The browser must never receive or
use the OpenAI API key. When bounded conversation context is enabled, an owned conversation ID shall load
at most the six latest prior messages and 6,000 serialized characters before cache, retrieval, or
model work. Missing and unowned IDs return the same non-disclosing `404`.

### FR-004: Retrieval

For every uncached standalone question or cache-ineligible contextual follow-up, the service shall:

1. Normalize and analyze the current question, or a deterministic query containing that question
   followed by bounded role-labeled history for a contextual follow-up.
2. Run deterministic exact lookup first.
3. Run PostgreSQL full-text and pgvector similarity search.
4. Fuse bounded candidate lists with reciprocal-rank fusion.
5. Pin validated exact matches ahead of approximate results.
6. Send no more than eight active passages to generation.

### FR-005: Grounded answer

The generated result shall contain:

- Answer text.
- Material-claim citations whose `claim` value is a normalized exact source excerpt of no more
  than 320 characters.
- Assumptions.
- A `high`, `medium`, or `low` confidence label.
- A `needs_clarification` flag.

Every `behavior=answer` result shall contain at least one citation. The backend shall resolve
model-supplied passage IDs to canonical labels and URLs, normalize Unicode with NFKC, collapse
whitespace, and require each normalized excerpt to occur contiguously in the cited passage while
preserving case and punctuation. Unknown IDs, omitted citations, omitted required passages, or
unsupported excerpts receive one repair attempt. A second failure returns a low-confidence
grounded abstention.
Prior conversation messages are untrusted reference-resolution context, not rules evidence, and
cannot supply valid citation IDs.

### FR-006: Clarification and scope

The service shall ask a concise clarification question when zone, timing, controller, ownership,
multiplayer state, or another missing game-state fact could change the result. It shall abstain
when retrieved evidence does not support an answer and shall not silently expand into excluded
strategy, price, tournament-policy, or metagame content.

### FR-007: Version-aware answer caching

The exact cache shall use the normalized question plus active configuration context. Semantic
reuse shall require at least `0.98` cosine similarity, active citations, an unexpired entry, and
matching corpus, embedding, generation, prompt, retrieval, language, and filter versions.

Semantic reuse is limited to high-confidence, simple, non-ambiguous questions. Cache hits count
toward the daily answer allowance. Context-bearing turns bypass exact and semantic cache reads and
writes in the initial release and report `cache_status=ineligible`.

### FR-008: Account and history

Authenticated users shall be able to list and open owned conversations, delete an owned
conversation, submit feedback, and delete application data and the Firebase account. Every
history mutation must enforce ownership in the backend.

### FR-009: Quotas

The service shall enforce five ask attempts per user per rolling minute and twenty successful
answers per user per UTC day. Successful cache hits consume quota. Authentication, validation,
retrieval, and generation failures do not consume the daily successful-answer allowance.

### FR-010: Public pages, accessibility, and PWA

Public pages shall remain readable without authentication. The application shall provide visible
focus, keyboard navigation, semantic landmarks, reduced-motion support, usable touch targets,
and no horizontal overflow at supported desktop and mobile widths. The development host and
authenticated or draft legal routes shall remain non-indexable until launch approval.

## 10. Public API contract

| Method and route | Authentication | Purpose |
| --- | --- | --- |
| `GET /healthz` | No | Minimal process health for Cloud Run probes |
| `POST /v1/ask` | Yes | Ask a rules question |
| `GET /v1/conversations` | Yes | List owned conversations |
| `GET /v1/conversations/{id}` | Yes | Read an owned conversation |
| `DELETE /v1/conversations/{id}` | Yes | Delete an owned conversation |
| `POST /v1/feedback` | Yes | Record answer feedback |
| `DELETE /v1/account` | Yes | Delete application data and Firebase account |

`/healthz` is used by native Cloud Run probes. The Firebase development edge is smoke-tested by
calling a protected `/v1` route without a token and expecting backend JSON `401`.

## 11. Non-functional requirements

### Reliability

- New source versions activate atomically.
- Re-ingestion of the same snapshot is idempotent.
- The preceding active corpus and Cloud Run revision remain rollback targets.
- Cache failure must not prevent generation of a fresh answer.
- Quota and answer persistence use atomic database operations.

### Security and privacy

- Verify Firebase tokens for protected routes and enforce ownership server-side.
- Keep OpenAI and database credentials in Secret Manager and inject them only at runtime.
- Restrict CORS to the configured frontend origin.
- Treat retrieved passages as untrusted data, never instructions.
- Bound question, request, response, context, timeout, retry, and model-repair work.
- Log identifiers, timing, token usage, cache status, and error categories without logging secrets
  or raw conversation content.

### Performance and cost

- Retrieval latency p95 target: at most 500 ms in staging.
- Cached API response latency p95 target: at most 1.5 seconds in staging.
- Development Cloud Run maximum: three instances with concurrency twenty.
- Production starting recommendation: maximum ten instances with concurrency twenty, adjusted
  only from measured load.
- Configure budget alerts at operator-approved thresholds before production launch.

### Quality

- Backend branch coverage: at least 80 percent.
- Retrieval recall@8: at least 90 percent for expected cards and rule references.
- Citation ID validity: 100 percent in the release evaluation.
- Citation precision: at least 95 percent.
- Clarification or abstention accuracy: at least 90 percent.
- Incorrect semantic-cache reuse across maintained negative pairs: zero.

## 12. Acceptance criteria

### AC-001: Supported answer flow

- **Scenario:** An authenticated user asks a supported English MTG rules question.
- **Action:** The user submits the question from `/desk`.
- **Expected:** The API returns an answer, confidence, assumptions, remaining quota, and canonical
  citations supported by active passages.
- **Must not:** Expose the OpenAI key, cite an unknown passage, or use an inactive corpus.
- **Verification:** Backend integration test, browser end-to-end test, and production-like smoke
  test using synthetic or approved questions.
- **Priority:** Required.

### AC-002: Ambiguous question handling

- **Scenario:** A question omits game-state information that can change the answer.
- **Action:** The user submits the question.
- **Expected:** The response asks for the missing information and marks clarification as needed.
- **Must not:** Cache the scenario semantically or invent the missing state.
- **Verification:** Versioned evaluation cases and API integration tests.
- **Priority:** Required.

### AC-003: Source refresh safety

- **Scenario:** A new source download is malformed, incomplete, or fails validation.
- **Action:** The ingestion job processes it.
- **Expected:** The run is marked failed and the previous source version remains active.
- **Must not:** Expose a partially staged corpus to retrieval.
- **Verification:** Ingestion integration tests and a production-like recovery drill.
- **Priority:** Required.

### AC-004: User-data isolation

- **Scenario:** An authenticated user requests or mutates another user's conversation.
- **Action:** The protected endpoint receives the foreign identifier.
- **Expected:** Access is denied without disclosing conversation content.
- **Must not:** Consume another user's quota or alter their records.
- **Verification:** Authorization integration tests.
- **Priority:** Required.

### AC-005: Responsive and accessible navigation

- **Scenario:** A keyboard, mobile, tablet, or desktop user navigates public and desk routes.
- **Action:** The user opens routes, drawers, feedback, and deletion controls.
- **Expected:** Navigation state survives refresh and Back/Forward, focus is managed, mutation
  status is visible, touch targets are usable, and no horizontal overflow appears at release widths.
- **Must not:** Show competing navigation systems, strand focus, or silently fail a mutation.
- **Verification:** Component tests, axe checks, and Chromium, Firefox, WebKit, mobile Chrome, and
  mobile Safari Playwright scenarios.
- **Priority:** Required.

### AC-006: Production release decision

- **Scenario:** Engineering development verification is complete.
- **Action:** The owner evaluates public launch.
- **Expected:** Legal and attribution review, independent MTG expert evaluation, production DNS and
  budget decisions, alert delivery, backup and restore, application rollback, corpus rollback,
  migration, ingestion, and account-deletion drills have retained evidence and a named go/no-go
  decision.
- **Must not:** Treat the development Firebase URL as public production approval.
- **Verification:** `operations/ATTRIBUTION-AND-LAUNCH.md`,
  `operations/PRODUCTION-AUDIT.md`, and `operations/OPERATIONS.md` sign-off.
- **Priority:** Required for public launch.

## 13. Dependencies and constraints

- OpenAI Responses and Embeddings APIs.
- Firebase Authentication and Hosting.
- Google Cloud Run, Cloud SQL, Cloud Storage, Secret Manager, Scheduler, Artifact Registry,
  Cloud Build, Logging, and Monitoring.
- WotC and Scryfall source availability and approved data use.
- PostgreSQL extensions for pgvector, trigram matching, and full-text search.
- Operator-owned cloud project, billing, domains, support identity, legal copy, and approvals.

## 14. Launch gates

Public production remains blocked until:

1. WotC/Scryfall policy, attribution, and legal text are reviewed and approved.
2. The 121-case evaluation suite receives independent MTG rules-expert review and passes every
   required threshold.
3. The production delivery mode, domain, DNS, secrets, budget, alerts, and regional controls are
   configured without reusing development credentials or state.
4. Production migration, ingestion, alert, backup/restore, rollback, and account-deletion drills
   pass with retained evidence.
5. A named owner records a final go/no-go decision and rollback target.

## 15. Related documents

- [Architecture.md](architecture/Architecture.md): complete system design and runtime flows.
- [architecture-essentials.md](architecture/architecture-essentials.md): concise learning and onboarding guide.
- [agent.md](architecture/agent.md): RAG agent behavior and grounding contract.
- [OPERATIONS.md](operations/OPERATIONS.md): deployment, recovery, and rollback runbook.
- [SECURITY.md](operations/SECURITY.md): trust boundaries and security controls.
- [ATTRIBUTION-AND-LAUNCH.md](operations/ATTRIBUTION-AND-LAUNCH.md): policy and launch decision record.
- [PRODUCTION-AUDIT.md](operations/PRODUCTION-AUDIT.md): current ship/block assessment.
