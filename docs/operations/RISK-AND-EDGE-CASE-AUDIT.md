# MTG Rules Desk Risk and Edge-Case Audit

**Audit date:** 2026-08-24
**Assessment:** 72/100, blocked for public launch
**Scope:** Runtime, RAG correctness, caching, ingestion, identity, persistence, scaling, and operations

This document records likely production failures and missing edge cases. It complements
[architecture-essentials.md](../architecture/architecture-essentials.md), which explains the intended safeguards,
and [PRODUCTION-AUDIT.md](PRODUCTION-AUDIT.md), which records the broader launch recommendation.

This is not a patch-notes document. Patch notes should describe fixes after they are implemented.

## 1. Summary

The development deployment has a coherent architecture and good local test coverage. Versioned
sources, exact and hybrid retrieval, server-side secrets, citation-ID validation, atomic quota
updates, and safe source activation are already present.

The main remaining risks are interactions between otherwise-correct operations:

- A request succeeds on the server but the client retries it. The implementation prevents duplicate
  work, and the r4 Cloud Build plus successful `0002` migration now provide development PostgreSQL
  proof.
- A conversation grows beyond the response boundary.
- Application deletion succeeds but Firebase deletion fails.
- A semantic-cache query looks similar while changing an important MTG fact.
- A generated answer uses a valid exact excerpt that does not semantically support its prose. The
  local `v11` candidate now prevents paraphrased or nonexistent citation excerpts, but deterministic
  substring validation is not an entailment judge.
- One source version updates while another source fails.
- Concurrent ingestion jobs repeat expensive work.

## 2. Highest-priority risks

| Priority | Risk | User-visible outcome | Recommended control |
| --- | --- | --- | --- |
| Cleared in development | Follow-up context qualification | Retained `v10` passes every strict context/citation/latency/cleanup gate | Preserve the immutable packet; repeat production-equivalent qualification only under separate authorization |
| Cleared in development | `/v1/ask` request retry | The implementation uses a client UUID, database uniqueness, an expiring single-owner claim, atomic response retention, and committed-response replay; r4 passed the live PostgreSQL integration gate and `0002` executed successfully once | Preserve the build/migration evidence and repeat production-equivalent verification separately |
| P0 qualification failed | Citation excerpt validation | Deployed `v11` achieved 100% normalized exact-excerpt validity, but its immutable 121-case packet failed required-reference citation coverage (0.8586), behavior (0.8678), and cached-latency evidence (no cache hits) | Improve deterministic citation selection/repair and restore qualifying positive cache hits; obtain a separately authorized zero-retry changed-candidate cycle before claiming release approval |
| P0 local remediation ready | v12 changed candidate | Prior-candidate repair, bounded exact excerpt options, narrow behavior guards, and cache status/confidence diagnostics pass 303 database-free tests and 80.28% focused branch coverage without lowering cache safety | Use frozen manifest `bd151f9ce5574473913a4866c6da4dba8202e3e5a32a85dc27509579f728e0ea`, then obtain one separately authorized external changed-candidate cycle; local tests cannot establish model quality or same-region latency |
| P1 | Conversation history is unpaginated | A long history can exceed the one-megabyte response limit and return `500` | Add cursor pagination for conversation lists and message pages |
| P1 | Account deletion is a two-system partial operation | Local data can be deleted while the Firebase identity remains | Use a durable deletion state, retryable worker, or compensating workflow |
| P1 | Semantic-cache classification is incomplete | A subtly different question may reuse an answer for up to seven days | Expand ambiguity detection and release semantic caching only after adversarial evaluation |
| P1 | Ingestion jobs have no job-wide lease | Scheduled and manual jobs can duplicate downloads and embedding cost | Acquire a PostgreSQL advisory lock or managed lease before discovery and embedding |
| P1 | Independent source activation can mix update dates | New rules may temporarily be combined with older card or ruling data | Add an ingestion-run manifest and activation barrier, or expose source freshness clearly |
| P2 | Cloud SQL pool behavior is implicit | Requests can wait for connections and reach the application timeout | Configure pool size, overflow, and pool timeout based on Cloud SQL capacity and load tests |
| P2 | Per-user limits do not cap total project spend | Many authenticated accounts can consume OpenAI quota simultaneously | Add a project-wide token or cost budget and an emergency circuit breaker |

## 3. Conversation and request edge cases

### 3.1 Follow-up context

The backend now loads bounded, ownership-scoped conversation context before downstream work and
uses prior user context in retrieval and generation. The remaining release risk is that a valid
follow-up may retrieve the governing rule but omit it from the answer, or clarify/abstain when the
retrieved evidence supports a useful answer.

Test cases:

- Ask a complete scenario, then ask `What if it has hexproof?`.
- Refer to `that creature`, `the second trigger`, or `the active player` in a follow-up.
- Change one fact from the preceding scenario without restating the other facts.
- Open two browser tabs and continue the same conversation simultaneously.

If conversation context is introduced, cache fingerprints must include the relevant context. An
identical question can have different answers in different conversation states.

#### Implemented foundation and completed development remediation

**Status:** Retained `v10` passes all nine P0 criteria in development; independent public-launch
blockers remain
**Revision:** 14
**Plan date:** 2026-08-24
**P0 closure rule:** Satisfied by immutable execution `mrzzf` and its exact retained generation.

The standalone [P0 conversation-context release remediation architecture
plan](../architecture/P0-CONVERSATION-CONTEXT-REMEDIATION-PLAN.md) owns the remaining failure model,
component decisions, acceptance criteria, rollout, rollback, cost boundary, and verification
matrix. This section retains the original context contract and evidence history.

##### Goal

When an authenticated user continues an owned conversation, retrieval and generation use a
bounded snapshot of recent messages so references such as `it`, `that creature`, or `the
second trigger` can be interpreted without leaking another conversation, reusing a
standalone cache entry, or committing an answer against stale context.

##### Scope

In scope:

- Load recent messages only when `conversation_id` is supplied and belongs to the authenticated
  application user.
- Keep the public `POST /v1/ask` request shape unchanged.
- Build a deterministic retrieval query from the current question and bounded recent context.
- Pass the same bounded context separately to generation as untrusted conversation data.
- Preserve standalone-question behavior when no conversation context exists.
- Disable exact and semantic cache reads and writes for context-bearing turns in the first
  release.
- Detect when another request advances the conversation between context loading and commit.
- Add unit, PostgreSQL integration, API, frontend, and multi-turn evaluation coverage.

Out of scope:

- Cross-conversation memory, user profiles, or inferred long-term preferences.
- Model-generated conversation summaries or a second model call that rewrites the question.
- Conversation-list and message pagination, which remains a separate P1 risk.
- Ask-request idempotency, which remains a separate P0 risk.
- Resuming a saved conversation from the history drawer; this plan covers requests that already
  supply a `conversation_id`.

##### Discovered implementation facts

- `frontend/src/App.tsx` stores the returned conversation ID and sends it with later questions.
- `backend/app/ask/service.py` loads owned bounded context before cache, embedding, retrieval, and
  generation while retaining the original question for persistence.
- `backend/app/ask/repository.py` enforces ownership before downstream work and compares the
  stored conversation tail under the existing row lock before quota or message writes.
- `backend/app/db/models.py` stores ordered user and assistant messages, so the context foundation
  required no schema migration.
- `backend/app/generation/openai_adapter.py` receives bounded history as untrusted data; prior
  assistant text is not rules evidence.
- Context-bearing turns bypass exact and semantic answer-cache reads and writes.

The supplied business constraint for the remaining remediation is to leave production unchanged.
The context bounds remain configurable engineering defaults.

##### Target request flow

1. Authenticate the Firebase user and resolve the internal application user ID.
2. If `conversation_id` is absent, keep the existing standalone flow.
3. If `conversation_id` is present, load an owned context snapshot before any cache, embedding,
   retrieval, or model call. Return the existing non-disclosing `404` for a missing or unowned
   conversation.
4. Select at most the latest six messages, ordered chronologically, with a serialized maximum of
   6,000 characters. Remove the oldest complete exchange first when the character limit is
   exceeded; never truncate the current question. If the newest exchange alone exceeds the
   limit, truncate its oldest content at a Unicode boundary and add an explicit truncation
   marker.
5. Record the snapshot's final message ID as `expected_tail_message_id`. Keep message contents
   and content-derived hashes out of logs.
6. Construct a deterministic retrieval query with the current question first, followed by the
   bounded prior user and assistant messages with role labels. Use this query for question
   analysis, embedding, lexical search, and vector search.
7. Send the original current question, bounded conversation messages, and retrieved passages to
   generation as separate fields. Conversation messages are context only: they cannot override
   system instructions, serve as rules authority, or satisfy citation requirements.
8. Mark a context-bearing turn cache-ineligible. Skip exact and semantic cache reads and writes.
   Standalone requests retain the current cache behavior.
9. During commit, lock the owned conversation and compare its current final message ID with
   `expected_tail_message_id`. If they differ, commit neither messages nor successful-answer
   quota and return `409 Conversation Changed`.
10. On success, atomically commit the current user message, grounded assistant answer, citations,
    and quota exactly as the service does today.

##### Implementation work packages

1. **Context contract and bounded loader**
   - Add `backend/app/ask/context.py` with immutable `ConversationContext` and
     `ConversationContextMessage` types, a loader protocol, deterministic bounding, and retrieval
     query rendering.
   - Implement the PostgreSQL loader with an ownership-scoped query and newest-first database
     limit, then restore chronological order in memory.
   - Add `conversation_context_max_messages=6` and
     `conversation_context_max_characters=6000` settings, positive-value validation, environment
     examples, and runtime wiring.

2. **Ask orchestration and cache isolation**
   - Update `backend/app/ask/service.py` to load context immediately after resolving the user.
   - Use the rendered contextual query for analysis and retrieval while retaining the original
     question for persistence and the answer prompt.
   - Bypass all cache repository operations when the loaded context contains messages and report
     `cache_status=ineligible`.
   - Leave standalone cache keys and eligibility behavior unchanged.

3. **Grounded generation boundary**
   - Extend `backend/app/generation/service.py` and
     `backend/app/generation/openai_adapter.py` to accept structured conversation messages.
   - Label both conversation history and retrieved passages as untrusted data. State that prior
     assistant text may explain references but is not evidence.
   - Continue permitting citations only to IDs in the current retrieved passage set, including
     during the existing single repair attempt.

4. **Optimistic concurrency and API behavior**
   - Pass `expected_tail_message_id` into `PostgresAnswerCommitter.commit`.
   - Compare it with the final stored message while holding the existing conversation row lock.
   - Add a typed `ConversationChangedError` and map it to a non-sensitive `409` response in
     `backend/app/api/app.py`.
   - Map `409` to a dedicated frontend error message instructing the user to review the latest
     conversation and submit again. Do not automatically retry a potentially charged model call.

5. **Evaluation, documentation, and rollout**
   - Add multi-turn fixtures for pronouns, changed facts, listed objects, insufficient context,
     unrelated conversations, and adversarial instructions in prior messages.
   - Update the PRD, agent contract, and architecture documents only after implementation behavior
     is verified.
   - Release behind `MTG_RAG_CONVERSATION_CONTEXT_ENABLED`, disabled by default, then enable it
     in development and staging. Close this P0 only after the evaluation gate passes; production
     rollback is the configuration toggle.

##### Acceptance criteria

###### AC-CTX-001: An owned follow-up uses recent conversation state

- **Scenario:** An authenticated user has an owned conversation containing a complete scenario
  and grounded answer.
- **Action:** The user asks `What if it has hexproof?` with that `conversation_id`.
- **Expected:** Retrieval receives a bounded query containing the current question and selected
  prior messages, and generation receives the original question plus the same context.
- **Must not:** Treat another conversation or a prior assistant answer as rules evidence.
- **Verification:** Ask-service unit test, generation-adapter payload test, and a staged multi-turn
  evaluation with expected rule or card reference keys.
- **Priority:** Required.

###### AC-CTX-002: Standalone requests do not change

- **Scenario:** An authenticated request omits `conversation_id`.
- **Action:** The user asks a supported standalone rules question.
- **Expected:** The context loader is not called and existing exact-cache, semantic-cache,
  retrieval, generation, response, and persistence behavior remains compatible.
- **Verification:** Existing ask-service and API suites plus explicit no-context regression tests.
- **Priority:** Required.

###### AC-CTX-003: Ownership is enforced before external or shared work

- **Scenario:** A user supplies a missing conversation ID or one owned by another user.
- **Action:** The user submits `POST /v1/ask`.
- **Expected:** The API returns the same non-disclosing `404 resource not found` response.
- **Must not:** Read message content, call cache, create an embedding, run retrieval, call OpenAI,
  consume successful-answer quota, or reveal whether the ID exists.
- **Verification:** Unit spy assertions and PostgreSQL integration tests with two synthetic users.
- **Priority:** Required.

###### AC-CTX-004: Context is deterministically bounded

- **Scenario:** An owned conversation exceeds either configured context limit.
- **Action:** A follow-up is submitted.
- **Expected:** At most six prior messages and 6,000 serialized characters are supplied, newest
  relevant exchanges are retained, order is chronological, and truncation is explicitly marked.
- **Must not:** Truncate the current question or split invalid Unicode.
- **Verification:** Table-driven unit tests for zero, odd, oversized, Unicode, and over-limit
  message sequences.
- **Priority:** Required.

###### AC-CTX-005: Contextual answers cannot reuse shared standalone caches

- **Scenario:** Two conversations contain the same follow-up text but different preceding facts.
- **Action:** Each conversation submits that follow-up.
- **Expected:** Both requests skip exact and semantic cache lookup and generate from their own
  bounded context.
- **Must not:** Read or write a shared answer keyed only by the current question.
- **Verification:** Ask-service unit tests asserting zero cache calls and distinct rendered
  retrieval inputs.
- **Priority:** Required.

###### AC-CTX-006: Concurrent turns cannot commit against stale context

- **Scenario:** Two requests load the same conversation tail before either commits.
- **Action:** The first request commits and the second then attempts to commit.
- **Expected:** The first succeeds; the second returns `409`, adds no message pair, and consumes
  no successful-answer quota.
- **Must not:** Hold a database transaction or row lock across retrieval or an OpenAI request.
- **Verification:** PostgreSQL integration test using two context snapshots and API contract test
  for the `409` mapping.
- **Priority:** Required.

###### AC-CTX-007: Missing context produces clarification, not invention

- **Scenario:** The bounded history does not identify what `it`, `that trigger`, or another
  reference means.
- **Action:** The user submits the ambiguous follow-up.
- **Expected:** The answer sets `needs_clarification=true` and asks for the missing game-state
  fact.
- **Must not:** Invent a card, permanent, player, zone, or event from unrelated text.
- **Verification:** Multi-turn evaluation fixtures and structured-output assertions.
- **Priority:** Required.

###### AC-CTX-008: Conversation content remains private operational data

- **Scenario:** Contextual requests succeed, fail ownership checks, encounter model errors, or
  hit a concurrency conflict.
- **Action:** Application and request logs are inspected.
- **Expected:** Logs may contain counts, truncation status, IDs already allowed by the logging
  policy, latency, and error category.
- **Must not:** Log current questions, previous messages, generated answers, prompts, or
  content-derived context hashes.
- **Verification:** Log-capture unit tests using unique synthetic marker strings.
- **Priority:** Required.

###### AC-CTX-009: The user receives actionable conflict feedback

- **Scenario:** The API returns `409` because another tab advanced the conversation.
- **Action:** The frontend receives the response.
- **Expected:** The UI explains that the conversation changed and asks the user to review and
  resubmit.
- **Must not:** Automatically retry the request or silently append a stale answer.
- **Verification:** API-client unit test and React interaction test.
- **Priority:** Important.

##### Verification and release gate

Run the focused tests first, then the complete quality gates:

```powershell
.venv\Scripts\pytest.exe backend\tests\unit -q
.venv\Scripts\pytest.exe backend\tests\integration -m integration -q
.venv\Scripts\ruff.exe check backend\app backend\tests
.venv\Scripts\mypy.exe backend\app
npm test --prefix frontend
npm run e2e --prefix frontend
```

Use synthetic conversations and a non-production database for integration and evaluation runs.
The P0 passes only when every required AC is green, the existing standalone suite has no
regressions, and the curated multi-turn set meets all expected behavior and reference-key checks.
Track model latency and input tokens before and after enabling the feature in staging. If the
context cap causes timeouts, token growth outside the staged budget, or answer regressions,
disable the feature flag and retain the standalone behavior while adjusting the bounds.

##### Implementation record (2026-08-19)

The code path, rollout controls, and local automated coverage are implemented. Production remains
disabled, development examples enable the flag, and this P0 intentionally remains open.

| Acceptance criterion | Current evidence | Gate status |
| --- | --- | --- |
| AC-CTX-001 | Ask-service, generation-service, adapter, versioned fixtures, and immutable `v10` execution `mrzzf` | Every answer-bearing follow-up answers, retrieves and cites all declared references, and bypasses cache; `followup-007` and `followup-009` clarify as expected; Pass |
| AC-CTX-002 | Standalone regression tests plus the complete backend unit suite | Pass |
| AC-CTX-003 | Early ownership-failure spies plus missing-ID and two-user PostgreSQL assertions | Pass, including PostgreSQL |
| AC-CTX-004 | Empty, odd, count-bound, character-bound, truncation-marker, newest-suffix, and Unicode unit tests | Pass |
| AC-CTX-005 | Same follow-up with distinct history produces distinct retrieval inputs and zero cache calls | Pass |
| AC-CTX-006 | Row-lock/tail comparison implementation, PostgreSQL integration scenario, and API `409` test | Pass, including PostgreSQL |
| AC-CTX-007 | Insufficient-, unrelated-, and corrected-context fixtures; `followup-007` and `followup-009` both clarified in the development capture | Pass for the required missing-context scenarios |
| AC-CTX-008 | Context log-capture tests assert counts only and exclude unique message/user markers | Pass |
| AC-CTX-009 | API-client, React interaction, and five-project Playwright conflict coverage | Pass |

Local evidence captured on 2026-08-19:

- PostgreSQL-backed backend suite: 179 passed with 85% branch coverage (80% gate).
- Evaluation capture runner: 8 unit and 1 PostgreSQL integration test passed.
- Ruff: passed; mypy: passed for 59 source files under local Python 3.14 and the CI Python 3.12 image.
- Frontend unit suite: 48 passed; ESLint and production build passed.
- Playwright: 90 passed across Chromium, Firefox, WebKit, mobile Chrome, and mobile Safari.
- Terraform 1.15.8: recursive formatting check and configuration validation passed.
- Dependency audits: npm and pip reported no known vulnerabilities; pip skipped the local package
  because it is not published on PyPI.

Docker PostgreSQL is healthy, migrations are at head, and the previous local PostgreSQL and
Terraform blockers are cleared. The new `mtg-rag-capture` command refuses production, reconstructs
fixture conversations, observes retrieval, isolates and cleans run-specific data, and writes a
non-overwriting capture artifact. Its dry run correctly stopped before external work when the
OpenAI key was explicitly absent and created no partial file.

An authorized development-corpus run completed all 121 cases with `gpt-5.6-luna`. The capture at
`.tmp/staging-run-20260819-reviewable.json` contains every observed answer and complete telemetry
for all 120 uncached cases: 146,281 input tokens and 23,245 output tokens. The one cache hit was
`inject-004`; no contextual case used cache. Cleanup confirmed zero synthetic users, messages, and
run-specific cache entries.

The original diagnostic grader fails recall@8 (0.5859), its then-named citation precision (0.3005), behavior accuracy
(0.6818), retrieval p95 (3037.8 ms through a local Cloud SQL proxy), and the one-sample cached API
p95 (2372.2 ms). Citation-ID validity is 1.0 and unsafe negative-pair reuse is zero. Retrieval RED/
GREEN work added a bounded lexical fallback, equal authority for official CR rules/glossary,
retrieval-query cleanup, and safe split-card face-alias matching, but the nine answer-bearing
follow-ups still reach only 3/9 strict declared-reference recall in a retrieval-only check.

Regional Cloud Build `064a922b-518c-4544-aa69-a05387cec0b4` passed every application, browser,
Terraform, and image-security gate and published digest
`sha256:6fe259ae20142dcf0fb2f938a0141cb02d51c0bca2296b26da47cdeb5d446c25`. Trivy reports zero
HIGH/CRITICAL findings after the Dockerfile's fixed Debian security-update layer. A saved Terraform
plan applied exactly three development-only in-place updates and no destructive actions, moving the
API, migration job, and ingestion job to the immutable digest and enabling context at 6 messages/
6,000 characters. Migration `mtg-rag-dev-migration-smvfx` and ingestion
`mtg-rag-dev-ingestion-t5h6z` completed successfully. API revision
`mtg-rag-dev-api-00009-4df` is Ready on `gpt-5.6-luna`, and the Firebase `/v1/ask` route reaches
FastAPI. Post-ingestion inventory is 36,494 cards, 3,901 rules/glossary passages effective
2026-08-07, and 77,314 rulings, with zero evaluation residue.

The project owner completed the personal review on 2026-08-19 and approved all 121 observed case
answers plus all 20 cache-pair definitions. The versioned suite records
`review.status=approved`, reviewer `Project owner (independent human review)`, and review date
`2026-08-19`; the review did not alter case expectations or pair definitions. The focused metadata
test was RED at 1 failed/5 passed before approval and GREEN at 6 passed afterward. Regrading the
saved capture without the pending-review bypass removes the expert-review failure but still fails
recall@8, required-reference citation coverage, behavior accuracy, retrieval p95, and cached API p95.

Post-review remediation now uses explicit structured behavior, marks abstentions cache-ineligible,
bumps the prompt/cache contract to `mtg-answer-v2`, corrects parent/subrule reference matching, and
names the minimum-evidence citation metric accurately. Retrieval follows glossary rule and section
links, caps protected exact evidence, prevents glossary crowding, and reuses the existing query
embedding to rank only bounded linked sections.

The first authorized nine-embedding follow-up diagnostic completed at 7/9 strict reference hits.
`followup-002` placed `702.9` on exact and vector paths but allowed broad section expansions to
consume the protected slots; `followup-003` did not place `704.5d` on any candidate path. Two new
PostgreSQL regressions reproduced those failures. Fully qualified glossary links are now ordered
before broad section expansions. Broad-section ranking reuses the stored embeddings of other
matched glossary concepts, orders sections by the specificity of their matched heading phrase,
and uses full-query lexical rank only as a tie-breaker. This adds no OpenAI call and hard-codes no
rule number. The real development corpus now puts both `702.9` and `704.5d` in the first four
protected exact candidates without an API call.

A separately authorized confirmation then completed all nine answer-bearing follow-up retrievals
with `text-embedding-3-small` and passed 9/9 strict declared-reference hits. The two former misses
now return `702.9` at fused rank 1 and `704.5d` at fused rank 2. The non-overwriting artifact is
`.tmp/followup-retrieval-after-contextual-ranking-20260819.json` (5,096 bytes; SHA-256
`fa49633373bfd1af1bb7a5b79ec47ce0d75074715d6380ef4ba466361c147927`). Independent validation
confirmed the exact nine-case ID set, nine unique cases, no failed case, at least one expected
reference per case, and no fused result over the eight-passage bound.

The complete local backend gate is GREEN at 189 tests and 85.00% branch coverage, including 10
PostgreSQL retrieval integration tests, with Ruff, mypy across 59 files, and `git diff --check`
passing.
The refreshed client gate is also GREEN: 50 frontend tests, lint, production build, and 95/95
Playwright cases on both Windows and the official Playwright 1.62.1 Linux image. The six responsive
baselines were inspected at 375px, 768px, and 1440px before replacement.
Regrading the immutable old artifact under the corrected metric gives recall and citation coverage
of `0.6364`; it remains historical evidence rather than proof of the new runtime. The nine-query
embedding confirmation is green, and the authorized same-region capture described below is now
complete. The P0 remains open because that current artifact does not meet every technical gate;
production stays disabled.

##### Same-region capture-path addendum (2026-08-20)

A read-only development inventory confirmed that Cloud Run, Cloud SQL, the OpenAI/database secrets,
and the retained snapshot bucket are all in `asia-east1`; no evaluation job existed. The locally
verified Terraform change now defines `mtg-rag-dev-evaluation` only for non-production environments.
It runs `mtg-rag-capture` beside Cloud SQL with zero automatic retries and a dedicated identity that
has Cloud SQL client, logging/metric writer, the two required secret-access bindings, and
`roles/storage.objectCreator` on the existing non-public bucket. It receives neither
`storage.objectAdmin` nor Firebase user-management permissions.

The runner writes the completed artifact directly to a unique GCS object with
`if_generation_match=0` and SHA-256 metadata. The evaluation identity cannot read, overwrite, or
delete the object, and the bucket's existing one-year retention policy applies. The runtime image
now includes the versioned suite, while Terraform omits the job, identity, and bindings entirely in
production.

TDD was RED on the missing GCS writer and missing `infra/evaluation.tf`, then GREEN at 35 focused
tests, 196/196 backend tests, and 84.66% branch coverage. Ruff passed, mypy passed all 59 source
files, Terraform formatting passed, and `terraform validate` reported a valid configuration. The
local runtime image built successfully, contains the 26,371-byte versioned suite, exposes the GCS
capture options, and passes the pinned Trivy HIGH/CRITICAL policy with zero Debian or Python-package
findings and no reported secrets. At this pre-deployment checkpoint, no cloud image had been
published, no Terraform change had been applied, and no additional OpenAI call had been made. The
owner subsequently authorized and completed that external evidence step as recorded next.

###### Authorized same-region execution result (2026-08-20)

Cloud Build `ddf791a3-3bf5-43dd-98b8-c50592c9e35d` passed every application,
browser, Terraform, credential, and image-security gate and published digest
`sha256:dd214f99b75bc3708c8c31562c120c38fa22ddf7f42642eb68f45e91eecfffb7`.
The inspected development plan contained eight additions, three in-place image updates, zero
deletions, and zero replacements. Applying that exact plan created the least-privilege evaluation
resources and moved the development API and jobs to the verified image; production was untouched.

Execution `mtg-rag-dev-evaluation-sg2kq` completed all 121 cases exactly once in 9 minutes
41 seconds with no retry. It wrote one retained, create-only object:
`gs://mtg-rules-desk-dev-mtg-rag-dev-snapshots/evaluation-captures/mtg-rules-v1/2026/08/20/91f6970e-2852-44a1-9505-fd46901f5848.json`.
Generation `1787223393503920` is 125,237 bytes and records SHA-256
`ac007a949726fe70be0c7c011ccd2197e9c83adc31bb5292dfe1a3db1edc9cf4`; the downloaded exact
generation has the same digest. The object has the existing one-year retention expiration.
All 120 uncached calls used `gpt-5.6-luna` and reported 193,867 input tokens plus 25,013 output
tokens. The only cache hit was non-contextual `inject-004`; no context-bearing case used cache,
no negative semantic-cache pair was reused, and no second full capture was started.

The release evaluator correctly rejects the immutable artifact because `abstain-010` contains a
blank `answer` even though Luna returned an explicit abstention and 38 output tokens. A
non-release, in-memory diagnostic substitution was used only to expose independent measurements;
it did not alter or replace the artifact. Under that diagnostic, behavior accuracy and citation-ID
validity are 100%, incorrect negative-pair reuse is zero, and cached API p95 is 53.4 ms. Three
measured gates fail: retrieval recall@8 is 79.80%, required-reference citation coverage is 74.75%,
and combined embedding-plus-retrieval p95 is 3,755.8 ms.

Case-level analysis found 20 retrieval misses: seven `state_priority`, four `multiface_zone`,
three `replacement_trigger`, two `prompt_injection`, two `semantic_cache`, one `oracle_text`,
and one `glossary`. There are 25 citation-coverage misses in total. Five are citation-only misses
where the required reference was retrieved but not cited: `glossary-002`, `glossary-005`,
`layers-001`, `replace-006`, and `followup-002`. The capture's latency field combines the
OpenAI embedding request and PostgreSQL retrieval, so the artifact does not support attributing the
latency failure to either component.

Direct post-run database counts are zero for the synthetic application user, conversations,
messages, daily usage, ask attempts, and run-specific semantic-cache entries. This independently
confirms cleanup in addition to the runner's finally-path guarantee. The temporary Cloud SQL audit
proxy was stopped after those aggregate checks.

The blank-output regression was RED before implementation and now converts any whitespace-only
model answer to a deterministic, non-empty, low-confidence abstention before API, cache, commit, or
capture boundaries. The focused generation tests pass 4/4; the complete backend passes 197/197 at
84.69% branch coverage; Ruff and strict mypy pass. Cloud Build
`9aaef735-edd8-49bc-a0f1-ea81d9328c70` passed the complete pipeline and published fixed digest
`sha256:6cca08fe1398c60cc1d18e155b2869d870e80d31e4c7730a07db6a0d8cca6a2d`.
An inspected plan applied four development-only in-place image updates, zero additions, and zero
deletions. Revision `mtg-rag-dev-api-00011-kgk` is Ready with 100% traffic, the evaluation job
definition uses the same digest, and its execution list still contains only `sg2kq`.

The next remediation cycle is deliberately bounded:

1. Add RED PostgreSQL regressions for the retrieval-miss clusters, starting with state/priority,
   multiface-zone, and replacement/trigger behavior; avoid case-ID or rule-number special cases.
2. Add content-free timing fields around embedding, exact, lexical, and vector work so the next
   artifact identifies the slow component before optimization.
3. Address the five citation-only misses at the grounded-generation boundary. If instructions or
   schema change, increment the prompt/cache version.
4. Rerun complete local and PostgreSQL gates, then request separate authorization before any new
   paid 121-case capture.

The bounded remediation is now locally implemented and verified:

- Capture telemetry records total retrieval plus embedding, exact, lexical, and vector timings;
  the grader rejects a future artifact that omits component telemetry.
- Retrieval now preserves longest card-alias intent, protects only query-supported broad-section
  candidates, matches maximal glossary phrases with safe singular/plural and DFC/SBA acronym
  expansion, bounds glossary-linked protected rules, and expands matched subrules with their
  governing parent rule. These are corpus/general retrieval rules, not case-ID result injection.
- The card ingestion contract now selects Scryfall `default_cards` and uses parser version
  `scryfall-cards-v2`. The read-only corpus audit proved why this is required: Scryfall's current
  `Black Lotus` representative is digital, so `oracle_cards` plus the paper-only filter omitted the
  paper Oracle identity. The development corpus remains unchanged until an explicitly scoped card
  refresh is run.
- Two stale suite expectations were corrected against the pinned 2026-08-07 rules:
  `state-001` now requires `117.3a`, and `replace-003` now requires `614.4`.
- The generation instructions now require the directly governing Comprehensive Rules passage for
  material conclusions and reject irrelevant citation padding. `prompt_version` is
  `mtg-answer-v3` and `retrieval_version` is `rrf-v2`, preventing old semantic-cache reuse.
- A read-only post-fix development-corpus spot check surfaced `glossary:Mana Ability` as the sole
  protected exact glossary for `glossary-003`, surfaced `712.8a` for the full DFC question, and
  surfaced `712.8a` for the `DFC` acronym question. Both temporary Cloud SQL proxies were stopped.
- A second read-only `default_cards` preflight found two upstream compatibility defects before
  deployment: the current JSONL snapshot exceeds the old 512 MiB uncompressed guard, and it
  contains non-Oracle objects without `oracle_id`. The parser now consumes gzip JSONL lazily under
  a bounded 1 GiB guard and skips only records that cannot identify an Oracle card. Focused TDD was
  RED on both defects and is GREEN at 15 tests.
- The corrected no-write comparison against the active development hashes found 36,494 unchanged
  card documents, 1,062 additions, zero changed documents, and zero removals. All existing
  embeddings can be reused. The preflight initially projected 288 sparse requests because
  embedding calls were coupled to 128-document storage batches. A RED/GREEN batching regression
  now compacts changed documents independently, so activating this snapshot would send 1,062 paid
  embedding inputs in nine requests while retaining bounded passage staging. `Black Lotus` is
  present. The comparison made no OpenAI call or database write, and its exact Cloud SQL proxy
  process and listener were stopped.

Verification evidence:

```text
pytest tests/integration/test_postgres_retrieval.py -q
# 16 passed

pytest --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=80 -q
# 211 passed; 85.24% total branch coverage

pytest tests/integration/test_postgres_ingestion.py -q
# 4 passed

ruff check app tests
# All checks passed

mypy app
# Success: no issues found in 59 source files

git diff --check
# No whitespace errors; only existing LF/CRLF conversion warnings
```

The P0 remains open because the current immutable evidence fails three measured technical gates.
The blank-answer safeguard, remediation image, card refresh, and one replacement paid capture were
subsequently executed under explicit development-only authorization as recorded below. Production
remains disabled and unchanged.

###### Authorized card-only deployment and replacement capture (2026-08-20 UTC)

The operator explicitly authorized the development scheduler guard, remediation image, capped card
refresh, and one new 121-case Luna capture. The saved guard plan applied exactly one in-place
development ingestion-job change (`0 added, 1 changed, 0 destroyed`). Live generation 12 was
`Ready` with command `mtg-rag-ingest`, arguments `[cards]`, and `maxRetries=0`. Scheduled and
ordinary manual development executions therefore default to cards only; rules and rulings require
an explicit future override.

Cloud Build `cf4fc5ab-88e8-40d2-96cc-e0687f1caae3` passed secret, backend, frontend,
Terraform, runtime-inspection, and vulnerability gates and published:

`asia-east1-docker.pkg.dev/mtg-rules-desk-dev/mtg-rag-dev/api@sha256:5142c179060c6058433461c91ee36a353d3fb83c95a2239a96d1b4986b70d865`

A fresh saved plan contained exactly four development image updates in place, with zero additions,
deletions, or replacements. Applying that exact plan moved the API, migration, ingestion, and
evaluation definitions to the immutable digest. API revision `mtg-rag-dev-api-00012-9kb` and all
three job definitions were `Ready`; ingestion still had `args=[cards]` and zero retries. There
were no migration changes, so no unnecessary migration execution was run. Every cloud command and
Terraform variable file targeted `mtg-rules-desk-dev`; no production plan, apply, job, or service
command was issued.

The final read-only source comparison repeated the authorized card estimate exactly: 36,494
unchanged cards, 1,062 additions, zero changes, zero removals, 1,062 embedding inputs, and nine
embedding requests. It also showed that a rulings refresh would exceed scope, so rulings remained
unselected. Execution `mtg-rag-dev-ingestion-s7tff` ran once on task attempt zero and completed
successfully. Its logs contain exactly nine successful embedding requests and report
`new_embedding_count=1062`, `source=cards`, `status=activated`, version
`77b19b9f-bbae-4d93-a050-ed21243d6d65`.

The active development corpus now contains 37,556 card passages and exactly one `Black Lotus`
passage. Rules remain frozen at version `bd0b2abc-c4d9-4efa-80bd-34a7c5aee3ca`, SHA-256
`68dab840bfb200a4fca4a061793269c40d57f83364cb1091ea9094b5b8f04769`, and 3,901 passages.
Rulings remain frozen at version `6a0662bc-d599-4497-b857-4c1630601dd2`, SHA-256
`350c3dd1a62d0a19683620006c2f0e610680ecc2f93ae973d4d1771666901617`, and 77,314 passages.

Exactly one replacement capture, execution `mtg-rag-dev-evaluation-khr2j`, completed 121 cases
successfully in 9 minutes 54 seconds on task attempt zero with `maxRetries=0`. It wrote:

`gs://mtg-rules-desk-dev-mtg-rag-dev-snapshots/evaluation-captures/mtg-rules-v1/2026/08/20/03642b69-feb1-4ce3-bd7e-c3d987861f67.json`

The create-only object is generation `1787241728710079`, 143,769 bytes, retained until
2027-08-20T16:02:08Z, and records SHA-256
`c6528c5edc9c83a273740c0aa7dda4ee77af26bea753207584cdd9c410be8e92`. The downloaded exact
generation has the same size and digest. All 120 uncached calls used `gpt-5.6-luna` and recorded
191,789 input tokens plus 23,093 output tokens. The sole cache hit was non-contextual
`inject-004`; no context-bearing case used cache, no unsafe negative pair was reused, and no
answer was blank.

The strict release grader reports:

```text
retrieval recall@8                 0.8585858585858586  FAIL (minimum 0.90)
required-reference citation       0.7676767676767676  FAIL (minimum 0.95)
clarify/abstain behavior           0.9545454545454546  PASS
citation identifier validity      1.0                 PASS
incorrect negative-pair reuse      0                   PASS
retrieval latency p95              4172.736 ms         FAIL (maximum 500 ms)
cached API latency p95             53.451 ms           PASS
```

Component p95 telemetry attributes most measured retrieval delay to lexical work: embedding
206.680 ms, exact 244.100 ms, lexical 2,697.050 ms, and vector 667.503 ms. Fourteen cases miss at
least one required reference in the top eight and 23 miss at least one required citation. The
clarification/abstention metric has one mismatch, `abstain-008`.

Conversation-context behavior improved materially but does not close AC-CTX-001: all nine
answer-bearing follow-ups retrieve every declared reference within the top eight; `followup-007`
and `followup-009` clarify; and every contextual result is cache-ineligible. However,
`followup-001` and `followup-002` omit the directly required citation, while
`followup-010` returns an abstention instead of its expected answer.

Independent post-run queries returned zero evaluation users, conversations, messages, daily-usage
rows, ask attempts, and run-specific semantic-cache entries. The active corpus was unchanged by
evaluation, and every temporary Cloud SQL proxy was verified by exact process path, stopped, and
left no listener on port 5433. No second replacement capture was started. The P0 remains open
because AC-CTX-001 and the recall, citation-coverage, and retrieval-latency gates are not green.

###### Local post-capture P0 remediation (2026-08-21 UTC)

The consumed khr2j artifact remains immutable and cannot prove post-fix behavior. A new test-first,
no-cost cycle corrected the measured runtime causes without changing an approved evaluation
question, expected behavior, reference key, or cache-pair definition:

- exact, lexical, and vector work now starts concurrently;
- compact current/prior-user lexical evidence replaces the 64-term conversation-wide fallback,
  CR/glossary results receive the highest lexical tier, and zero is projected as 0;
- HNSW cosine distance selects a bounded 100-passage candidate set before authority reranking;
- protected exact evidence may occupy six of eight final slots, with two retained for multi-path
  evidence;
- retrieval marks governing evidence as citation-required, and an answer that omits it receives
  the same single bounded repair opportunity used for unknown citation IDs;
- cache boundaries are mtg-answer-v4 and rrf-v3.

The complete backend gate is 224 passing tests at 85.06% branch coverage. The focused set contains
4 lexical/query unit tests and 17 PostgreSQL retrieval tests. Ruff, mypy across 59 source files,
and git diff --check pass.

A final no-write development check confirmed the HNSW index plan and warm proxy-path repository
samples of 312.169-364.944 ms for vector retrieval. Warm lexical samples across three diagnostic
questions were 265.456-475.449 ms. The current code retrieves 704.5g at rank 7 and 704.5a at rank
5, repairing two observed recall misses without a case-ID or rule-number mapping. The exact
temporary proxy was stopped and port 5433 was closed.

No OpenAI call, database write, build, image publication, deployment, Terraform apply, ingestion,
GCS write, evaluation execution, or production change occurred. The new citation contract can
make at most one additional Luna repair call per uncached answer, so any post-fix paid capture
authorization must include that possible cost. P0 remains open until a separately authorized
development-only remediation deployment and separately authorized paid 121-case same-region
capture pass recall, citation coverage, retrieval latency, behavior, and all existing safety
gates.

###### Authorized post-fix deployment and capture (2026-08-21 local)

Cloud Build `6deca42d-1ec6-414a-8a47-d59d539cf1c8` passed all eight release gates and
published immutable digest
`sha256:df5251a7bffa80eac64d3246a87f09ef6adf7f87648c0a8864ac7b2bba78e8ec`.
The reviewed saved development plan targeted only `mtg-rules-desk-dev` in `asia-east1`
and contained four in-place image updates, with zero additions, deletions, or replacements.
The exact apply completed `0 added, 4 changed, 0 destroyed`; revision
`mtg-rag-dev-api-00013-drv` and all three job definitions are Ready on the digest.
Ingestion remains card-only with zero retries. A final plan reports no drift, and no migration
or ingestion job was executed.

Exactly one paid execution, `mtg-rag-dev-evaluation-lqr2x`, completed 121 cases on task
attempt zero in 12 minutes 56.93 seconds. Its create-only retained artifact is:

`gs://mtg-rules-desk-dev-mtg-rag-dev-snapshots/evaluation-captures/mtg-rules-v1/2026/08/20/c5da9a5b-aff1-4c33-a035-dbcb7e1d264c.json`

Generation `1787252485857575` is 152,859 bytes, retained until
2027-08-20T19:01:25Z, and has matching cloud/local SHA-256
`9f1cbfc8add64271c1f12b1af6cddb7956afd0d67ba9d52fa3b57a08ac98b66a`.
All 121 IDs are unique, no answer is blank, no citation ID is unknown, and uncached telemetry
is complete. All 120 uncached cases used Luna and consumed 296,910 input plus 59,411 output
tokens. `inject-004` is the only cache hit; every contextual case is cache-ineligible.

The capture-cycle grader passes citation-ID validity at 1.0, negative-pair safety at zero
incorrect reuse, and cached API p95 at 45.920 ms. Its reported behavior score of 1.0 considered
only cases expected to clarify or abstain. It fails:

```text
retrieval recall@8                 0.8686868686868687  FAIL
required-reference citation       0.8080808080808081  FAIL
retrieval latency p95              1809.086 ms          FAIL
```

Component p95 is 192.961 ms embedding, 354.948 ms exact, 1,362.111 ms lexical, and
407.804 ms vector. Thirteen cases miss required top-eight retrieval evidence and 20 miss a
required citation. The corrected local all-case grader regrades the same immutable artifact at
0.8429752066 behavior accuracy, below the 0.90 gate, without mutating the artifact or making a
model call. It exposes 19 expected answers that instead abstained or clarified, adding behavior as
the fourth strict failure. Context retrieval and cache isolation pass, but `followup-001` retrieves
702.11 then abstains without citing it; `followup-005`, `followup-010`, and `followup-011` clarify
instead of answering. AC-CTX-001 remains open.

Independent cleanup queries found zero evaluation users, conversations, messages, daily usage,
ask attempts, and run-specific cache entries. Corpus versions and counts were unchanged, the
temporary audit proxy was stopped, and port 5433 was closed. No production command or change
occurred. No second capture was started. P0 remains open on recall, citation coverage, retrieval
latency, and expected-answer behavior.

###### Remaining P0 remediation architecture (2026-08-21 local)

The [standalone remediation plan](../architecture/P0-CONVERSATION-CONTEXT-REMEDIATION-PLAN.md)
preserves the existing ownership, context bounds, cache isolation, one-embedding request, and
eight-passage generation limit. Revision 2 addresses the remaining release failure through a
dynamic eight-current/four-recent term budget with newest-turn precedence, a GIN-backed stage that
sends at most 50 candidates to distinct-term coverage, a four-passage exact pin cap with dynamic
RRF spillover, explicit-or-corroborated citation requirements, supported procedural answers with
narrow assumptions, runtime/evaluation repair parity without deterministic citation injection,
repair-specific telemetry, and all-case behavior grading.

The test-first RED state is resolved locally. The dynamic recency allocation, trusted
assistant-free retrieval projection, four-clause/50-row GIN-backed lexical candidate stage,
exact-pin spillover, `rrf-v5` boundary, and repair-specific capture fields now exist. The complete
backend suite passes 261 tests at 85.62% branch coverage; the focused retrieval set passes 62
service/repository unit and PostgreSQL integration tests. Read-only plans for
all 121 queries against 118,771 active development passages used `ix_passages_search_vector`,
admitted at most 50 anchor rows, and reported 55.11 ms server-side p95 and 155.424 ms maximum
execution time. This evidence does not prove final hybrid recall, same-region Cloud Run retrieval
p95, generation behavior, citation coverage, or shipped telemetry. No OpenAI call, cloud write,
image publication, Terraform apply, evaluation execution, or production change was authorized by
this continuation. P0 closes only when one post-remediation same-region capture passes every
acceptance criterion in the architecture plan.

###### Authorized P0 qualification failure and contained recovery (2026-08-22 local)

The operator authorized one development-only qualification cycle. Cloud Build
`f801bb1e-1b41-4a16-ae6a-ec9aea120035` passed all configured gates and published immutable digest
`sha256:42a74482b61e86f22671fcd9cae3dbaf2a1db9e1ab1a3c1153f13157a1961a67`. Saved-plan
SHA-256 `FC72BF41609CBB97A8240EFFF89CEF4C13940F3DEDAB43F533D18368E369107F` covered four
in-place development image updates and applied with `0 added, 4 changed, 0 destroyed`. Ready API
revision `mtg-rag-dev-api-00014-kcx` and the evaluation job used that digest in `asia-east1`;
no migration, ingestion, corpus, or production action occurred.

Exactly one zero-retry execution, `mtg-rag-dev-evaluation-9p8m8`, failed on task attempt zero
during `exact-008`. The model returned a NUL-bearing answer, and PostgreSQL/asyncpg rejected it
while the assistant message was flushed. The execution did not retry and did not create a retained
object. This is a newly observed provider-output/persistence edge case, not an accuracy-gate result.

Containment succeeded. Independent cleanup queries found zero evaluation users, conversations,
messages, daily usage, ask attempts, and evaluation-cache entries. Retained GCS state remained the
same three objects totaling 421,865 bytes. The active corpus was unchanged, and production was not
touched.

A RED adapter regression reproduced the unsafe `\x00`; GREEN now removes only NUL characters
from provider-generated answer, citation-claim, and assumption text and revalidates the structured
model before persistence. A second RED/GREEN regression proved that post-sanitization invalidity is
categorized as content-free `ModelOutputError`, not raw Pydantic failure. The complete local
backend suite passes 263 tests at 85.66% branch coverage; the 49-test recovery slice, Ruff, and
strict mypy are green. Because the deployed digest predates this fix and the one-shot authorization
is consumed, P0 remains open pending fresh authorization for a replacement build/deploy and one
complete create-only same-region capture.

### 3.2 Request retries and duplication

The UI disables the Ask button while a request is pending, but it cannot prevent every retry. A
server response may be lost after the database commit.

Test cases:

- Disconnect the browser after the server commits but before the response arrives.
- Refresh the page while an ask request is running.
- Submit the same request from two tabs.
- Retry a `504` when OpenAI already charged for the first request.
- Send the same HTTP request twice without using the browser UI.

An idempotency key should identify one logical ask operation independently of the normalized
question. Two intentional identical questions should still be allowed when they have different
keys.

### 3.3 Input validation

The frontend trims questions before submission, but the API schema accepts a string containing
only spaces because its length is greater than zero before normalization.

Test cases:

- Empty, whitespace-only, and newline-only questions.
- Unicode whitespace and zero-width characters.
- Two thousand combining characters rather than two thousand visible characters.
- Invalid UTF-8 or malformed JSON at the HTTP boundary.
- A valid question inside a request larger than the configured body limit.

## 4. Semantic-cache edge cases

Architecture Essentials correctly states that cosine similarity is not truth. The `0.98`
threshold is strict, but vector similarity can still hide a factual difference.

### 4.1 Negative and contrastive wording

Test these as explicit non-reuse pairs:

- `Can this creature block?` versus `Can't this creature block?`
- `The target is legal` versus `The target is illegal`.
- `Before damage` versus `after damage`.
- `Its owner` versus `its controller`.
- `In the graveyard` versus `in exile`.

### 4.2 Questions misclassified as simple

The current profile treats an explicit rule reference as a direct-rule question and treats text
starting with `what is` or `define` as a definition. It counts quoted card names, but not all
unquoted card aliases found by exact retrieval.

Test cases:

- `What is rule 614.1 when two replacement effects apply?`
- `Define priority after I cast Teferi, Time Raveler.`
- Unquoted single-card and multi-card questions.
- A definition that changes by zone, controller, timing, or multiplayer state.
- A direct rule question containing a hypothetical exception.

### 4.3 Cache lifecycle

Test cases:

- Activate and roll back each source while a cache lookup is running.
- Expire an entry exactly at the request timestamp.
- Deactivate one cited passage while the entry remains otherwise valid.
- Change prompt, retrieval, generation, or embedding versions independently.
- Change embedding dimensions and confirm every old entry becomes unusable.
- Attempt to cache a high-confidence answer with no citations.

## 5. Retrieval edge cases

### 5.1 Exact entity recognition

- Unquoted card names.
- Smart quotes, apostrophes, ligatures, accents, and Unicode normalization.
- Split, adventure, transform, meld, and modal double-faced cards.
- Card names that are also ordinary English phrases.
- Overlapping aliases where one card name contains another card name.
- Several named cards when exact results alone could fill the eight-passage context.

### 5.2 Rule references

- Several rule references in one question.
- A rule range or parent rule without a specific subrule.
- A correctly formatted rule number that is no longer active.
- A mistyped rule number that is semantically close to a real rule.
- A rule reference combined with an unrelated card or glossary term.

### 5.3 Evidence sufficiency

Vector retrieval intentionally has no fixed cutoff. This improves recall, but even a nonsense or
severely misspelled question receives nearest-neighbor results.

Test cases:

- Nonsense input with no relevant exact or lexical evidence.
- A strategy, price, tournament-policy, or deckbuilding question outside the product scope.
- Three or more card interactions requiring more than eight passages.
- Layer or replacement-effect scenarios needing a chain of dependent rules.
- A question for which lexical and vector retrieval strongly disagree.

The system should decide whether evidence is sufficient before treating generation as an ordinary
answer path. The outcome can be answer, clarify, or abstain.

## 6. Citation and generation edge cases

Citation-ID validation prevents invented IDs, but it does not prove entailment or claim coverage.

Test cases:

- A correct retrieved passage cited for the wrong claim.
- A high-confidence answer with zero citations.
- Several substantive claims supported by only one unrelated citation.
- Oracle text cited for a general Comprehensive Rules statement.
- A dated ruling cited without source or publication-date context.
- Conflicting passages from different effective dates.
- Invalid structured output on both the initial and repair calls.
- A repair call that reaches the outer request timeout.

Runtime validation should reject or downgrade unsupported answers even when every citation ID is
real.

## 7. Ingestion and source-version edge cases

### 7.1 Concurrent execution

Activation locks source-version rows, but there is no lease around the complete job. Two jobs can
discover, download, snapshot, parse, and embed the same source before activation serialization.

Test cases:

- Scheduler retry overlaps the original job.
- Manual ingestion begins during the scheduled job.
- Two jobs ingest the same SHA.
- Two jobs ingest different SHAs for the same source.
- A job dies after uploading the snapshot but before creating the staged version.

### 7.2 Cross-source consistency

The job refreshes rules, cards, and rulings sequentially. Each source activates independently.

Test cases:

- Rules activate and card ingestion fails.
- Cards activate and rulings fail.
- Rulings reference cards that were removed or changed in the new card version.
- A rollback affects one source but not the related sources.
- A user request runs during each activation boundary.

### 7.3 Upstream format and freshness

The WotC discovery code expects exactly one qualifying Comprehensive Rules TXT link. A page redesign
or multiple qualifying links will safely fail ingestion, but the corpus can become stale.

Test cases:

- Multiple current-looking WotC TXT links.
- WotC changes encoding, MIME type, filename, or HTML structure.
- Scryfall changes bulk-catalog fields or compression.
- A valid payload has a severe but still above-minimum record-count drop.
- Upstream returns a previous version with a different URL.
- The scheduler fails for several consecutive days.

Add an alert for maximum active-corpus age, not only job failure.

## 8. Persistence and deletion edge cases

### 8.1 Account deletion

Application data is deleted in one database transaction. Firebase identity deletion happens
afterward as a separate operation.

Test cases:

- Firebase permission failure after local deletion.
- Firebase timeout or temporary outage.
- Retrying deletion after the local user no longer exists.
- An ask request commits while account deletion is running.
- The user signs in again after partial deletion.

### 8.2 Conversation growth and races

Conversation lists and message details are returned without pagination, and the request middleware
buffers the complete response.

Test cases:

- A conversation whose JSON response exceeds one megabyte.
- Thousands of conversation summaries.
- Delete a conversation while an answer is being generated.
- Delete an account while history is loading.
- Feedback arrives while its answer message is being deleted.

## 9. Scaling and timeout edge cases

Development permits three Cloud Run instances and twenty concurrent requests per instance. This
is roughly sixty in-flight request slots, not guaranteed throughput.

Test cases:

- Sixty simultaneous uncached questions.
- A mixture of vector searches, history reads, cache hits, and account deletions.
- An ingestion job running while the API is at peak concurrency.
- Cloud SQL pool exhaustion and connection-creation spikes after scale-out.
- Cold start combined with Firebase certificate refresh and database connection setup.
- OpenAI retry behavior when the application deadline is shorter than the full retry sequence.

Explicitly configure and measure database pool size, overflow, acquisition timeout, and maximum
Cloud SQL connections.

### 9.1 Replacement same-region qualification evidence (2026-08-22)

The separately authorized replacement image and update-only development apply completed, followed
by exactly one successful one-task, zero-retry execution: `mtg-rag-dev-evaluation-9hzsj`. The
execution retained one create-only, generation-pinned 121-case object with matching local/object
SHA-256 and complete cleanup proof. Production, migrations, ingestion, and corpus versions were
unchanged.

This closes the previous retained-evidence gap but not the P0. The authoritative artifact fails
retrieval recall@8 at 0.8989898990, required-reference citation coverage at 0.8181818182, and
retrieval p95 at 959.974 ms. All-case behavior passes at 0.9008264463, cached API p95 passes at
39.478 ms, citation-ID validity is 1.0, and negative-pair reuse is zero. Context failures are
`followup-003` retrieval/citation, `followup-010` citation/answer behavior, and `followup-007`
missing-context clarification. Component telemetry is present on all 121 cases; initial/repair
telemetry is consistent on all 120 uncached cases, including 45 repaired cases.

### 9.2 Latest same-region packet and local continuation (2026-08-22)

One later authorized development cycle supersedes section 9.1 as the latest packet. Cloud Build
`9f1e9c11-6c7e-477d-aa13-0cc887bfb17a` passed all eight gates and published digest
`sha256:aed0c9ebdf2bd41a1cc8b638ef41f905bcdf108413573362ef7908417afa60a7`. The reviewed
development-only plan applied four image updates as `0 added, 4 changed, 0 destroyed`. Ready API
revision `mtg-rag-dev-api-00016-9dc` and job generation 7 used that digest; migration and ingestion
did not run.

Exactly one execution, `mtg-rag-dev-evaluation-mwmjq`, succeeded on task attempt 0 and created one
181,146-byte retained object, generation `1787396385333503`, with matching SHA-256
`41C9DC11B28F580B64B103E651BD91BBAD4586C01BD74A7AF16BAD1BCE1A1AB9`. Cleanup returned all
evaluation row families to zero and source fingerprints remained unchanged.

The exact artifact passes recall@8 (0.9595959596), behavior (0.9586776860), citation-ID validity
(1.0), retrieval p95 (489.128 ms), cached API p95 (46.099 ms), and negative-pair reuse (0). It fails
required-reference citation coverage at 0.8989898990. Context failures are `followup-003`
retrieval/citation and `followup-004` retrieval/citation/behavior; both missing-context cases
clarify and no context case hits cache. P0-AC-004 therefore closes on retained evidence, while
P0-AC-001 and P0-AC-002 remain open.

The post-capture local `v6` candidate protects bounded anchored rules through fusion, requires only
explicit rule/card/definition targets rather than every linked exact expansion, improves
specific-procedure repair, and rotates cache boundaries to `mtg-answer-v6`/`rrf-v6`. A final
read-only development check ranks/protects `704.3` at 1/true and `117.3b` at 3/true for
`state-010`. It passes 279 backend tests at 85.71% branch coverage, Ruff, strict mypy across 59
source files, and dependency audit. It has not been built or captured. Exactly one development-only
build was attempted as `d9f99669-6f73-48fe-a23b-8115e1acf29f`; it passed secret/backend gates but
failed 1/105 E2E checks on a 433-pixel 375px snapshot drift before image publication or Terraform.
The 0.1% scale-aware replacement passes ten consecutive focused Linux Chromium runs and two full
isolated Linux gates. The Cloud Build-equivalent `node:24-bookworm-slim` run passed zero-vulnerability
audit, lint, 58/58 unit tests at 92.25% statement/90.19% branch coverage, production/PWA build,
fresh Playwright 1.62.1 browser installation, and 105/105 E2E cases across all five projects. API
revision, evaluation job generation, and execution count remain unchanged; no apply, capture,
database write, or object occurred. At that checkpoint another build required fresh authorization;
the separately authorized successful retry is recorded in section 9.6. Production remained
excluded.

### 9.3 Retained `v6` replacement qualification (2026-08-23 local)

Replacement build `1125f44f-fd7d-4beb-8450-38a146a3a1a4` passed all eight release gates and
published digest `sha256:556e44947091064aef6fce3f0e2de2ca29e31efc62b881e8ebc88a0e1df186a8`.
Reviewed saved-plan SHA-256
`785026F47FEC4A42DEBCE643C45CB6A00D36A4CA22C851D74DD24C7C1DE2D3B1` contained exactly four
development image updates; its one hash-guarded apply reported `0 added, 4 changed, 0 destroyed`.
Revision `mtg-rag-dev-api-00017-jlk` and evaluation job generation 8 became Ready on the digest in
`asia-east1`, and health probes returned 200. No migration, ingestion execution, or production
action occurred.

The sole authorized execution, `mtg-rag-dev-evaluation-xnbcb`, succeeded on task attempt 0 in
6m59.43s with one task and zero retries. It created exactly one 173,144-byte retained object,
generation `1787416391304068`, with matching metadata/local SHA-256
`64801CEDAFC981286C520436551140691105E9839B9F5BE7743466A8B689B61D` and retention through
2027-08-22T16:33:11Z. Execution and object inventories each increased by exactly one. Cleanup left
all six evaluation residue categories at zero, source counts/hashes unchanged, and no proxy or
port 5433 listener.

The exact packet passes recall@8 (0.9696969697), behavior (0.9669421488), citation-ID validity
(1.0), cached API p95 (54.690 ms), negative-pair reuse (0), context cache exclusion, reviewed-suite
identity, and repair telemetry. It fails citation coverage at 0.9292929293 and retrieval p95 at
513.617 ms. Retrieval misses are `replace-003`, `cache-010`, and `followup-011`; citation misses add
`layers-001`, `replace-001`, `state-005`, and `multiface-006`. `followup-011` is the only context
retrieval/citation miss; every answer-bearing follow-up still returns `answer`, both missing-context
cases clarify, and no context case hits cache. This complete negative evidence keeps P0-AC-001,
P0-AC-002, and P0-AC-004 open. No retry is authorized.

### 9.4 Local `v7` continuation after retained negative evidence

The changed local candidate addresses each retained citation miss without replacing vector search.
It keeps the independent exact, GIN lexical, and HNSW vector paths, but narrows the GIN anchor from
50 to 32 rows and ranks current-question coverage ahead of prior context. Rule-ID-free governing
language projections, specific-anchor precedence, and a two-term governing-parent bonus now place
`613.1a`, `614.1`, `614.4`, `704.5a`, `712.10`, `117.4`, and `603.3` at
lexical rank 1 with `protected=true` against the development corpus. The citation policy selects
the first such governing rule only when explicit rule, exact-card, or requested-definition evidence
does not already define the required citation.

The focused retrieval suite passes 54 tests and the evaluation-runner suite passes 17/17, including
an explicit `max_retries=0` assertion for qualification-only OpenAI calls. Complete local gates pass
284 backend tests at 85.74% branch
coverage, Ruff, strict mypy, dependency audits, 59/59 frontend tests, PWA, 105/105 Playwright
cases, Terraform format/validation, Python 3.12 container tests, runtime non-root/secret inspection,
and pinned Trivy with zero HIGH/CRITICAL or secret findings. The final container gate intentionally
omitted migration execution. A corpus-scale, read-only 121-case
`EXPLAIN (ANALYZE, BUFFERS)` audit over 118,771 passages used `ix_passages_search_vector` for
every case, admitted at most 32 anchor rows, and measured query-only p95/max of
53.930/74.819 ms. These proxy measurements do not prove same-region service latency.

Before the authorized build recorded below, no `v7` image was published or deployed and no
plan/apply, Cloud Run job, database write, migration, ingestion, or GCS write occurred. The
diagnostic proxy was stopped and port 5433 closed. The local candidate reduces engineering risk but
does not clear P0-AC-001, P0-AC-002, or P0-AC-004 without a fresh same-region packet.

### 9.5 Authorized `v7` build failure and local recovery

Cloud Build `b8d54f24-d89b-4a5d-91e9-be42f2f337c8` consumed the one authorized replacement build.
Secret scanning, backend test-image construction, and all 284 backend gates passed. The frontend
gate completed 103/105 browser cases, then its compound Firefox public-pages WCAG check and Mobile
Safari release-width welcome check reached the original 30-second Playwright timeout. Neither
failure identified an assertion, snapshot, accessibility, or application defect. Terraform,
runtime-image build/inspection, Trivy, and publication remained queued.

The recovery retained zero retries and addressed contention test-first. The timeout contract first
failed at `undefined` before becoming 60 seconds. A one-CPU/two-worker stress run still timed out
both affected cases, and a second RED required one worker. The final config is one worker, zero
retries, and a 60-second test timeout. A one-CPU Playwright 1.62.1 Linux stress passed five repeats
of both checks across Firefox and Mobile Safari, 20/20; one valid cold Firefox check took 31.8
seconds. The exact `node:24-bookworm-slim` release sequence then passed dependency audit, lint,
59/59 unit tests at 92.09% statement/90.09% branch coverage, PWA, and 105/105 browser cases in 4.7
minutes.

The failed build has no result image and no Artifact Registry tag. Read-only cloud reconciliation
found API revision `mtg-rag-dev-api-00017-jlk` and its prior digest unchanged, evaluation job
generation 8 unchanged with `maxRetries=0`, seven executions, and six retained objects totaling
956,033 bytes. No plan/apply, deployment, evaluation/database write, cleanup cycle, retained write,
migration, ingestion, or production action occurred. The one authorized build is consumed;
another immutable qualification requires fresh explicit authorization.

### 9.6 Successful authorized `v7` retry build/publication

The operator separately authorized one Cloud Build retry. Build
`04f72f67-4feb-486c-bfe8-23d737be12d4` passed all eight configured steps and published immutable
digest `sha256:251b3cc97d0ca52328290fe7097b6b54e08fd714e406593d119ca7939e295302`.
The cloud frontend gate passed audit, lint, 59/59 unit tests, PWA, and all 105 browser cases with one
worker and zero retries. Backend, Terraform validation, runtime inspection, and pinned Trivy gates
also passed.

Post-build checks prove no implicit deployment or capture. API revision
`mtg-rag-dev-api-00017-jlk`, evaluation job generation 8, and their prior digest are unchanged; the
job remains at `maxRetries=0`; there are still seven executions and six retained objects totaling
956,033 bytes. No plan/apply, deployment, evaluation/database write, cleanup cycle, retained write,
migration, ingestion, or production action occurred.

The build-only authorization is consumed. P0-AC-007 now has immutable Cloud Build proof, but
P0-AC-001, P0-AC-002, P0-AC-004, P0-AC-006, P0-AC-008, and P0-AC-009 still require one deployed
same-region `v7` packet. The reviewed update-only plan/apply and exactly-once capture require
separate renewed authorization.

### 9.7 Retained `v7` same-region qualification

The operator authorized one hash-reviewed update-only development apply and exactly one
zero-task-and-transport-retry 121-case capture. Plan SHA-256
`E37D3553C150E7FBB12FA13814845090D8524D5B575DA61AAD3BFBE8A460F0C9` applied only four image
leaves and reported `0 added, 4 changed, 0 destroyed`. API revision
`mtg-rag-dev-api-00018-cwq` and evaluation job generation 9 became Ready on exact digest
`sha256:251b3cc97d0ca52328290fe7097b6b54e08fd714e406593d119ca7939e295302`; the job has one task
and `maxRetries=0`. Migration and ingestion definitions changed image only and did not execute;
production remained excluded.

Preflight proved 121 unique approved cases, seven prior executions, six objects/956,033 bytes,
zero evaluation residue, and unchanged 118,771-passage corpus identities. Sole execution
`mtg-rag-dev-evaluation-r7lbf` completed task 0 with zero failed/retried tasks in about 8m41s. It
created exactly one retained object, increasing inventory to eight executions and seven
objects/1,131,529 bytes:

`gs://mtg-rules-desk-dev-mtg-rag-dev-snapshots/evaluation-captures/mtg-rules-v1/2026/08/22/2b156e73-3174-4a22-a094-1c44958f2ec2.json#1787433858431773`

The object is 175,496 bytes, retained through `2027-08-22T21:24:18Z`, and its metadata/local
SHA-256 is `642607B39D5633FB8EACBBABB9D333EA44FF2161C2E1B65044C6F226E7EC9155`. Post-run residue is
zero and source hashes/counts are unchanged; the temporary proxy stopped.

The packet passes recall 0.9696969697, behavior 0.9834710744, citation-ID validity 1.0, retrieval
p95 439.582 ms, cached API p95 94.924 ms, and negative-pair reuse zero. It fails only strict
required-reference citation coverage at 0.9292929293. `followup-001` omits citation `702.11`, and
`followup-010` misses retrieval/citation `509.1b`; both still answer, both missing-context cases
clarify, and no context case hits cache. Complete repair telemetry covers all 120 uncached cases
(29 repaired, 91 unrepaired). This is complete same-region negative evidence: P0-AC-001 and
P0-AC-002 remain open, P0-AC-003 through P0-AC-009 pass, and no retry is authorized.

### 9.8 Local `v8` post-capture remediation

The changed local candidate preserves exact, bounded GIN lexical, and HNSW vector paths. It adds a
bounded official-rule winner per domain anchor clause, promotes governing evidence without
promoting generic fallback anchors, keeps a directly matched subrule ahead of its parent, requires
both branches of the pre-priority procedure, and requires a contextual card's linked ability rule.
Cache versions rotate to `mtg-answer-v8` and `rrf-v8`.

Real-corpus, read-only service fusion now requires every governing reference from the seven `v7`
citation misses, including `117.3b` plus `704.3`, contextual `702.11`, and corrected-state
`509.1b`. Local gates pass 292 backend tests at 85.87% coverage, 31 PostgreSQL retrieval
integrations, Ruff, strict mypy across 59 source files, and dependency audit. No model or database
write was used for the corpus check.

The verification-loop audit now covers all 121 query plans. Main and winner statements are all
GIN-backed and bounded; main p95/max are 44.407/81.325 ms, while the 45 protected-winner plans have
39.377/42.075 ms p95/max and return at most two rows. A fixed-zero-vector service pass is retained
only as a non-release diagnostic; it cannot establish real-embedding recall or model citation
coverage.

This reduces the engineering likelihood of the observed citation omissions but does not close the
risk. `v8` has no immutable build, deployment attestation, same-region latency measurement,
121-case model-output grade, cleanup proof, or create-only retained object. No cloud mutation or
retry occurred, and a future external cycle requires separately bounded authorization.

### 9.9 Retained `v10` development closure packet

The intervening retained `v8` and `v9` packets exposed citation and latency failures; their full
history is preserved in the linked architecture and TDD records. The final authorized `v10` cycle
passed. Build `4dba8ba5-684f-4dd3-83f3-6ebbf7b5049c` published immutable digest
`sha256:870b46a23e6406142f89eb04969e2d5b623b4f69d72d6b24c19497764b3ffefc`. The reviewed plan
changed exactly four development image leaves as `0 added, 4 changed, 0 destroyed`; API revision
`mtg-rag-dev-api-00021-7pf` and evaluation generation 12 are Ready.

Exactly one zero-retry execution, `mtg-rag-dev-evaluation-mrzzf`, created one retained object
generation `1787508036393785`, SHA-256
`B28ED889EBEF8838F2F7C4FF2520735F107B87D879D8E1212DD7C953C11EEB91`. Immediate read-only
pre/post checks found zero evaluation residue and stable capture-time source identities. The exact
grade passes recall 1.0, citation coverage 0.9797979798, behavior 0.9669421488, citation validity
1.0, retrieval p95 322.348890 ms, cached API p95 54.807516 ms, and negative reuse zero. All 121
cases have component telemetry and all 120 uncached cases have valid repair telemetry.

The enabled daily cards scheduler independently started `mtg-rag-dev-ingestion-ld56k`; the agent
did not invoke it. The evaluation completed at 18:00:39Z and the new cards version activated at
18:05:55Z, proving the capture used the prior stable corpus. The later successful scheduled run is
an out-of-band concurrency/lease signal for section 7.1, not a qualification failure. Conversation
context is closed in development; production and the independent public-launch risks remain open.

## 10. Authentication and delivery edge cases

- Expired, revoked, disabled, or deleted Firebase identities.
- Firebase signing-key rotation during a cold start.
- Sign-in popup blocked by browser settings.
- Third-party storage protection or strict privacy mode.
- Sign-out in one tab while another tab sends a protected request.
- Custom-domain OAuth callback not present in the OAuth client allowlist.
- Firebase `web.app`, custom frontend domain, and API domain disagree about CORS or `authDomain`.
- Cloud Armor geolocation blocks a supported user using a VPN or traveling outside the launch
  countries.

## 11. Cost and abuse edge cases

Per-user quotas protect one Firebase account. They do not cap aggregate use across many accounts.

Add and test:

- A global daily OpenAI token or dollar budget.
- A rolling project-level request ceiling.
- An emergency generation kill switch that preserves cached and public functionality.
- Alerting for unusual account creation or correlated traffic.
- Cleanup of expired ask-attempt, cache, usage, and abandoned staged-version records.

## 12. Public-launch blockers

The existing production audit remains blocked by external and production-specific evidence:

1. **Cleared 2026-08-19:** The independent human review approved all 121 cases and all 20
   semantic-cache pair definitions; the versioned suite records the reviewer and date.
2. **Cleared in development 2026-08-24:** immutable `v10` passes every conversation-context P0
   gate, including same-region quality/latency, cache safety, cleanup, telemetry, and exactly-once
   retention. Production-equivalent evidence remains part of blocker 5, not this closed P0.
3. **Local copy completed 2026-08-24:** Terms and privacy now describe the implemented public
   question path, optional accounts, retention, attribution, deletion, and support. Qualified
   legal review and external publication remain required.
4. **Engineering product change completed 2026-08-24:** public questions no longer require
   sign-in or email registration. Qualified review must still confirm the final WotC source use,
   excerpts, marks, and corpus presentation, or authorize another product change.
5. Production backup restoration, rollback, alert delivery, DNS, certificate, and identity-deletion
   drills still require recorded evidence.

## 13. Safeguards already implemented

- Cache context includes active corpus, embedding, generation, prompt, retrieval, language, and
  filter versions.
- Cached citations must still point to active passages.
- Exact retrieval handles rule references, card aliases, and glossary phrases before vector
  ranking.
- Bounded GIN lexical candidates and HNSW vector candidates remain independent inputs to RRF;
  protected anchored rules prevent governing evidence from being crowded out.
- Generation receives at most eight server-owned passages and no arbitrary SQL or HTTP tools.
- Unknown or omitted required citation IDs receive one combined repair attempt and then a
  low-confidence abstention.
- Whitespace-only model answers are downgraded to a deterministic non-empty abstention.
- Successful-answer quota consumption and message persistence occur in one transaction.
- Failed ingestion preserves the previous active version.
- Snapshot downloads are allowlisted, bounded, hashed, and stored immutably.
- Firebase tokens are verified with revocation checking.
- OpenAI and database credentials remain server-side in Secret Manager.

## 14. Recommended implementation order

### Engineering P0

1. **Cleared in development 2026-08-24:** `/v1/ask` idempotency, duplicate exclusion, stable
   browser retry IDs, committed-response replay, live PostgreSQL integration, and the `0002`
   migration execution.
2. **Completed 2026-08-24:** Close the [P0 conversation-context remediation plan](../architecture/P0-CONVERSATION-CONTEXT-REMEDIATION-PLAN.md) with the retained `v10` packet.
3. **Deployed 2026-08-24; changed-candidate qualification failed:** require citations for
   substantive answers and accept only normalized exact source excerpts of at most 320 characters,
   with one repair then abstention. The exact-excerpt gate passed; citation coverage, behavior, and
   cached-latency evidence did not.
4. Add cursor pagination for history and conversations.
5. Make account deletion durable and retryable across PostgreSQL and Firebase.

### RAG correctness P0

1. Expand semantic-cache negative-pair tests for negation, timing, zones, controllers, and
   multiplayer changes.
2. Add retrieval-sufficiency and unsupported-scope evaluation cases.
3. Run the 121-case suite against production-like staging.
4. **Completed 2026-08-19:** Obtain independent MTG rules expert approval before enabling public
   production traffic.

### Operations P1

1. Add an ingestion job lease and maximum-corpus-age alert.
2. Load-test Cloud Run concurrency against explicit database pool limits.
3. Run and record backup, restore, rollback, alert, and identity-deletion drills.
4. Add a global cost circuit breaker.

## 15. Evidence checked

- `docs/architecture/architecture-essentials.md`
- `docs/architecture/P0-CONVERSATION-CONTEXT-REMEDIATION-PLAN.md`
- `docs/operations/PRODUCTION-AUDIT.md`
- `backend/app/ask/service.py`
- `backend/app/cache/`
- `backend/app/retrieval/`
- `backend/app/generation/`
- `backend/app/history/repository.py`
- `backend/app/accounts/service.py`
- `backend/app/api/`
- `backend/app/ingestion/`
- `backend/evals/`
- `frontend/src/App.tsx`
- `frontend/src/api-client.ts`
- `infra/`
- `firebase.json`

## 16. Evidence still missing

- No changed-candidate conversation-context packet is missing in development. Retained `v10`
  positively proves every P0 criterion.
- No development same-region latency evidence is missing: `v10` retrieval p95 is 322.348890 ms and
  cached API p95 is 54.807516 ms. Future changes must preserve both bounds.
- No `v10` repair-telemetry evidence is missing: all 120 uncached cases have consistent initial and
  null-or-populated repair fields (28 repaired, 92 unrepaired).
- The deployed `mtg-answer-v11` candidate has an immutable build, reviewed migration-first rollout,
  same-region 121-case capture, cleanup reconciliation, and retained object, but the packet is
  negative evidence: citation coverage is 0.8585858586, behavior is 0.8677685950, and cached API p95
  is not finite because all 121 cases were uncached. A passing changed-candidate packet is missing.
- The development database executed `0002` successfully once via zero-retry execution
  `mtg-rag-dev-migration-mmqd5`; no additional migration execution is needed for this deployed
  digest.
- A concurrency test at the configured Cloud Run ceiling.
- Failure-injection tests for Firebase deletion and overlapping ingestion.
- A response-size test for long conversation histories.
- Recorded production backup, restore, rollback, alert, DNS, certificate, and deletion drills.
