# Production readiness audit

**Audit date:** 2026-08-24
**Recommendation:** 72/100, blocked for public launch by required qualified policy/legal review,
source-use review, and remaining production-specific controls and drills. The conversation-context
P0 and the later exact-excerpt contract are closed in development by retained `v10` and `v14`
packets respectively.

## Blockers

1. **Engineering decision implemented 2026-08-24:** the public question path no longer requires
   sign-in or email registration; sign-in remains optional for saved history and account controls.
   Obtain qualified WotC policy/legal review of the final source presentation and corpus use, or
   obtain written permission/change the product before production.
2. **Cleared in development 2026-08-24:** the retained immutable `v14` packet passes the stricter
   exact-excerpt contract as well as the original conversation-context gates: recall 1.0, citation
   coverage 0.9797979798, behavior 1.0, citation ID/excerpt validity 1.0, retrieval p95
   291.119934 ms, cached API p95 45.788348 ms, cache safety, cleanup, exactly-once retention, and
   complete telemetry. Production-equivalent qualification remains separate and is not implied by
   this development packet.
3. Supply operator-owned projects, secrets, DNS, billing budget, monitoring
   channel, publish the reviewed privacy/terms/support copy, and execute the documented
   bootstrap, migration, ingestion, backup-restore, and rollback drills.

## Public development-preview decision

The operator intends to publish the development deployment while clearly labeling it as a
development preview that is not production-ready. Under that release target, blocker 3 and
production-equivalent qualification are deferred production gates, not preview-publication
blockers. The development-preview gate status is:

1. Qualified review of WotC/Scryfall source use and publication of the reviewed legal/support
   copy. Exactly one authorized Firebase Hosting-only deploy of the tested 19-file artifact
   `2c23d3d48194327cec675e2b9cf70fc7dc9afda3777b20384c92453f94e80fae` completed in development
   without retry. Read-only live QA confirmed the complete operational Terms replaced the old
   placeholder and that Terms, Privacy, About, preview labeling, attribution, and support render
   without inspected console errors. Qualified review and any resulting revision remain the gate;
   development publication does not constitute that approval.
2. **Cleared in development:** remediate and requalify the deployed `mtg-answer-v11` exact-excerpt
   contract. The r4 build,
   live PostgreSQL gate, `0002` migration, two-phase image rollout, same-region capture, cleanup,
   and immutable retention all completed correctly. The authoritative 121-case packet nevertheless
   failed required-reference citation coverage, expected behavior, and cached-latency evidence.
   No retry is authorized or implied by the deployment.

   A local `mtg-answer-v12` remediation now preserves the prior answer during citation-only repair,
   supplies bounded exact excerpt options, deterministically handles the two independent behavior
   policy classes, and captures cache status/confidence. Its 303 database-free tests, focused 80.28%
   coverage, Ruff, and mypy are green. Authorized build
   `3f15a847-9bab-4bfb-816f-e2a6db4cf107` passed all eight gates and published immutable digest
   `sha256:3ec25eef7b5bd5095a681ea496ed2a89f39611959a2ff3129e9b05a09d9653e5`. The initial Terraform
   plan command failed during local argument parsing; a separately authorized one-shot replacement
   reached Terraform but failed before plan creation because the GCS backend lacked ADC. Neither
   attempt created a saved plan or reached apply/capture. A tested non-persistent bridge now passes
   the existing gcloud user token only to Terraform's child environment without changing credential
   configuration. A final authorized continuation then created and reviewed one full saved plan,
   SHA-256 `6D7292A19EEBC7DD3BDFDD1F76068A376C4247EC331ABB6AB600A0BBBACE2A2B`, whose only actionable
   changes were the three development application image leaves. One exact apply moved API,
   ingestion, and evaluation to v12 while migration remained on v11. API revision
   `mtg-rag-dev-api-00023-2q9` is Ready at 100% traffic. Exactly one zero-retry capture,
   `mtg-rag-dev-evaluation-h5v65`, created exactly one generation-pinned retained object.

   The strict 121-case grade still failed: citation coverage 0.8383838384, behavior accuracy
   0.8760330579, and retrieval p95 548.277258 ms missed their 0.95, 0.90, and 500 ms gates. Recall,
   citation ID/excerpt validity, negative-pair safety, and cached API latency passed; the capture
   produced one exact cache hit and a finite 56.067938 ms cached p95. Cleanup was complete and the
   corpus remained unchanged. No retry is authorized or implied, so v12 does not clear this gate.
   Its create-only 197-file
   manifest is `.tmp/v12-source-manifest-r1.json`,
   aggregate SHA-256 `bd151f9ce5574473913a4866c6da4dba8202e3e5a32a85dc27509579f728e0ea`.

   v13 was built and qualified once against its frozen manifest. Build
   `7e2c44df-293a-4b7a-bcc8-945a9a2f36bc` passed and published digest
   `sha256:a3d2a51a861cb75fc90d458963f48f852ed594dad5589b719c09e4a305fbb0df`. A locally corrected
   split-baseline reviewer proved unchanged saved-plan SHA-256
   `D6F0224521E945FC47AAD9D63B0ABADF2228BBE6BA90B76F21B7A26643397ABF` contained only the three
   authorized application image updates while migration remained v11. Its exact apply completed
   `0 added, 3 changed, 0 destroyed`; API revision `mtg-rag-dev-api-00024-kc9` is Ready at 100%.
   Exactly one zero-retry execution, `mtg-rag-dev-evaluation-5p48n`, produced exactly one retained
   generation. Retrieval improved and passed at 273.895557 ms p95; recall, citation ID/excerpt
   validity, cache latency, and negative-pair safety also passed. Citation coverage 0.8282828283 and
   behavior 0.8595041322 failed. All 17 citation misses were post-retrieval, and 16 expected answers
   plus one clarification became abstentions. Cleanup was complete and the corpus was unchanged.
   No retry is authorized or implied, so deployed v13 remains immutable negative evidence.

   `mtg-answer-v14` addresses that exact regression without accepting
   paraphrases. After the one model repair fails, an answer can be recovered only when it attempted
   a citation and an explicit required canonical passage is present. Unknown IDs and unsupported
   claims are removed; already-valid exact excerpts are retained; bounded exact excerpts are added
   for required passages; and the whole result must pass validation again. Missing-all-citation and
   no-required-anchor answers still abstain. Clarifications retain only valid citations. RED was
   four failures with the missing-all-citation counterexample already passing; GREEN is five focused
   tests. The expanded focused suite passes 37 tests at 94.53% branch-aware coverage; 326
   database-free tests, Ruff, and strict mypy pass. The create-only 199-file manifest is
   `.tmp/v14-source-manifest-r1.json`, aggregate SHA-256
   `a93aa3543b5d010840d21d525cf1fc6c2b3f61fcbdfe14b8f4fb10d176588745`, and immediate independent
   verification matched. Exactly one build, `c9fbaffb-b43f-46de-8475-c609221ee79f`, passed all
   eight gates and published immutable digest
   `sha256:189f95be9f6e6eec14be7fe87afbd1797eefc0a0093121d75f2a868dfe474400`. Terraform input SHA-256
   `9E52CF8FA53B3D2D3FA066F57339322153C3BF180407990E1539C7EBE2FB6E6C` produced one full saved plan,
   SHA-256 `4F2F650ABF0E22BEAC7ABAC3AB489C466D555CC4512C7A5CAAB1E820E0CFBFD0`. Its 54-resource review
   passed with 51 no-ops, exactly three application image updates, migration retained on v11, and
   zero violations. One exact apply completed `0 added, 3 changed, 0 destroyed`; API revision
   `mtg-rag-dev-api-00025-tbt` is Ready at 100% traffic.

   Exactly one zero-retry execution, `mtg-rag-dev-evaluation-tmj5d`, succeeded in 8m58.08s and
   increased evaluation executions 14 to 15 and retained objects 13 to 14. The sole new object is
   generation `1787592286883780`, 182,988 bytes, SHA-256
   `dfc7bfec96673f73869ce5b9cf4ee1c73263e86c122d2b6e39403a3552794ad2`. The strict 121-case grade
   passes: recall 1.0, citation ID/excerpt validity 1.0, citation coverage 0.9797979798, behavior 1.0,
   retrieval p95 291.119934 ms, cached API p95 45.788348 ms, and negative reuse zero. Reconciliation
   found no behavior or retrieval misses and two citation-only misses. Cleanup returned all six
   temporary tables to zero and preserved all corpus hashes. v14 therefore clears this development
   engineering gate without retry; production qualification remains separate.

The preview must identify itself as development/beta and must not claim production availability,
operational readiness, or an SLA.

### v11 r3 qualification attempt and r4 replacement-ready remediation — 2026-08-24

The exact 197-file r3 source manifest,
`65dd9df07fb12849607e3ac2aac0dbf2545ff3e39a36373902b8afb99350cc3b`, was submitted once under
the scoped authorization. Cloud Build `a669ac15-5367-48b0-abd6-f2c691ae3a5b` failed its temporary
PostgreSQL backend gate at `352 passed, 1 failed`: the idempotency claim insert serialized Python
`None` as JSON `null`, violating the intentional `response IS NULL` in-progress constraint. No
runtime image was published, so the migration apply/execution, application apply, evaluation,
cleanup, and retained-object phases did not run.

The constraint remains unchanged. A new regression first failed with `1 failed, 6 passed`; mapping
the response as `JSONB(none_as_null=True)` made the focused suite pass 7 tests and the complete
database-free gate pass `297 passed, 57 deselected`, with Ruff and strict mypy also green. The
corrected exact 197-file r4 manifest is frozen and reverified at
`9568309a7087cc1abee6da05e14e8c67d3621fe5b3acd03d66c6d8d04b7cac7f`. It differs from r3 only
in the model mapping and its unit regression.

Read-only reconciliation at that point confirmed API revision `mtg-rag-dev-api-00021-7pf` and all four development
runtime leaves remain on retained v10 digest
`sha256:870b46a23e6406142f89eb04969e2d5b623b4f69d72d6b24c19497764b3ffefc`; migration/ingestion/
evaluation execution counts remained 3/21/11; and retained inventory remained 10 objects. The safe
replacement cycle required two reviewed image-only applies: migration job first, then
API/ingestion/evaluation only after one zero-retry development migration succeeds. The subsequent
121-case capture must additionally report citation-excerpt validity 1.0. Because the original
authorization excluded retries and was consumed, r4 required fresh explicit authorization.

### v11 r4 migration-first qualification result — 2026-08-24

The separately authorized r4 cycle used exact aggregate source manifest
`9568309a7087cc1abee6da05e14e8c67d3621fe5b3acd03d66c6d8d04b7cac7f`. Cloud Build
`5fd9a8ed-d4fd-4b48-911f-fb9414186cfa` passed all eight gates and published immutable digest
`sha256:df0644eb31a4fafccd4e55deeccabd2dfe5dc3d1ca40d29fccde70ca0f6d7b66`. Saved migration plan
`D8EFC70E7B7E1E9D40839FBEE371000CD8B7043E668396AA6281A17E416FC239` changed only the development
migration image; execution `mtg-rag-dev-migration-mmqd5` then succeeded once with `maxRetries=0`.
Saved application plan `C79CA6C5BC8378CD385C99CDE519930FEB922F8EC71746550971A1FDE6F0172B` changed only the API,
ingestion, and evaluation image leaves. All four development leaves are Ready on the r4 digest;
the API serves revision `mtg-rag-dev-api-00022-gp7` at 100% traffic. Ingestion execution count
remains 21 with latest execution `mtg-rag-dev-ingestion-ld56k`.

Exactly one zero-retry evaluation execution, `mtg-rag-dev-evaluation-nmh8x`, completed and created
exactly one immutable 169,162-byte retained object at generation `1787574988434922`, SHA-256
`310db56bce7739fbc3c8712dec02a3a26bfe95ca7e9907b2c92e3be32f99142c`. The authoritative grader
passed recall 1.0, citation-ID validity 1.0, citation-excerpt validity 1.0, negative-pair reuse 0,
and retrieval p95 385.570353 ms. It failed citation coverage at 0.8585858586, behavior at
0.8677685950, and cached API latency because all 121 cases were uncached and therefore supplied no
finite p95 sample. Fourteen citation-only misses had their required passages in the retrieved top
eight, and 16 cases had behavior mismatches.

Post-capture reconciliation used a read-only database transaction and found zero evaluation users,
conversations, messages, daily-usage rows, ask attempts, and evaluation cache rows. The active
cards/rules/rulings hashes and 118,771 passages were unchanged. Retained inventory increased exactly
from 10 to 11 objects. The Firebase `/v1/**` edge reached the deployed API and returned the expected
signed-out `401 authentication required`. The failed packet is valid immutable negative evidence,
not public-release approval. The scoped authorization excluded retries, and no second capture ran.

### Development-preview labeling follow-up - 2026-08-24

The signed-out site and authenticated desk now identify themselves as a public development preview,
and the Terms expressly disclaim production readiness, guaranteed availability, and an SLA. The
required Wizards Fan Content Policy notice remains unchanged. Focused RED/GREEN tests, all 66
frontend unit tests, coverage above 89% on every dimension, lint, production/PWA build, and all 110
desktop/mobile browser tests pass. This resolves the product-labeling portion of the preview gate;
it does not decide the separate corpus-download, storage, embedding, processor, excerpt, or mark-use
questions reserved for qualified review.

## High-value follow-up

- Replace the initial metadata-driven Alembic revision with a frozen explicit
  schema revision before the first later schema change. It is deterministic for
  this first empty-workspace deployment, but importing current ORM metadata is
  unsafe once the model evolves.
- Add a dependency-readiness endpoint if operators later need load-balancer
  gating on database/corpus availability. The current `/healthz` is deliberately
  the minimal process health endpoint specified in the plan.
- Preserve the passing development Cloud Build provenance and Artifact Registry digest. Repeat
  equivalent qualification for production only under separate authorization; development evidence
  cannot prove production IAM, quota, DNS, certificate, or provider state.

## Evidence checked

- 115 backend tests, including real PostgreSQL/pgvector migration, ingestion,
  retrieval, cache, ownership, quota, rollback, auth, and failure boundaries.
- Backend branch coverage above 85%, Ruff clean, strict mypy clean, and
  `pip-audit` with no known third-party vulnerabilities.
- Nine frontend unit tests with all coverage dimensions above 80%, production
  build, PWA validation, and seven Playwright paths including desktop/mobile
  axe WCAG 2.1 AA checks and keyboard use.
- Terraform formatting/provider validation for dev/prod Cloud Run, Cloud SQL,
  GCS, Secret Manager, Scheduler, HTTPS load balancer, Cloud Armor, alerts, and
  budgets.
- Non-root test/runtime container builds, runtime import smoke test, absence of
  runtime pip/setuptools, repository history secret scan, and zero fixed
  HIGH/CRITICAL Trivy findings.
- CI, environment examples, Firebase Hosting headers, migration/ingestion jobs,
  immutable image delivery, rollback, recovery, incident, attribution, and
  release documentation.

## Evidence missing

The deployed v11 candidate now has immutable build provenance, reviewed migration-first applies,
same-region capture, cleanup reconciliation, and create-only retained evidence. What is missing is a
passing changed-candidate quality packet: the sole v11 packet failed citation coverage, behavior,
and cached-latency evidence. Production also lacks a reviewed apply, managed-certificate and DNS
proof, alert delivery, backup restore, Firebase identity deletion, qualified policy/source-use
review, and external publication of the reviewed legal copy. These independent omissions cap
readiness regardless of the closed v10 development P0.

## Development deployment addendum - 2026-08-13

The preceding section records the evidence available during the original audit. Since then,
the operator authorized and supplied an owned Google Cloud project, billing, and an OpenAI
secret. The development integration now has direct evidence for:

- Firebase Hosting at `https://mtg-rules-desk-dev.web.app`, including exact security
  headers and a same-origin `/v1/**` rewrite to Cloud Run;
- enabled Firebase Google authentication with only the Firebase Hosting domains on the
  authorized-domain list;
- a private OpenAI credential injected from Secret Manager into dedicated Cloud Run API and
  ingestion identities, without exposing it to the browser or build context;
- a Cloud Run API, Cloud SQL/pgvector, immutable source snapshots, migration and ingestion
  jobs, three active versioned corpora, and an idempotent re-ingestion result;
- Artifact Registry, Cloud Scheduler, monitoring and alert resources, and a successful
  Cloud Build with backend/frontend/Terraform, secret-scan, and container-vulnerability
  gates; and
- live signed-out edge verification: public pages return `200`, protected API access returns
  `401`, and the Hosting-to-Cloud-Run route preserves the authentication boundary; and
- a real signed-in Google account flow producing a grounded OpenAI answer with WotC glossary
  and Scryfall Oracle citations, quota reporting, and History persistence.

These results remove the original "no cloud evidence" limitation for development. They do
not change the public-launch recommendation. Remaining launch evidence includes qualified
WotC policy/source-use review, publication of the reviewed legal copy, independent expert approval
and execution of the RAG evaluation suite, and production-specific
DNS, budget, alert-delivery, backup/restore, rollback, and identity-deletion drills.

## P0 remediation evidence addendum - 2026-08-22

Local remediation and corpus-scale lexical-plan verification are now green. The backend suite
passes 261 tests at 85.62% branch coverage, including 62 focused retrieval service/repository unit
and PostgreSQL integration tests. Read-only `EXPLAIN (ANALYZE, BUFFERS)` checks for all 121 suite
queries against 118,771 active development passages used the GIN search-vector index, bounded the
anchor stage at 50 rows, and reported 55.11 ms server-side execution p95 and 155.424 ms maximum.

This evidence does not change the blocked public-launch recommendation. It is database-side plan
evidence gathered through a local proxy, not proof of the deployed same-region service path, final
hybrid top-eight recall, answer behavior, citation coverage, or shipped repair telemetry. This
continuation made no model call, database or GCS write, image publication, Terraform apply, or
production change. A separately authorized development deployment and one retained 121-case
capture must pass every remediation criterion before P0 can close.

## P0 development qualification result - 2026-08-22

One scoped development qualification was authorized and executed. Cloud Build
`f801bb1e-1b41-4a16-ae6a-ec9aea120035` passed its secret, backend, frontend, Terraform, runtime,
and vulnerability gates and published immutable digest
`sha256:42a74482b61e86f22671fcd9cae3dbaf2a1db9e1ab1a3c1153f13157a1961a67`. The reviewed
development plan, SHA-256
`FC72BF41609CBB97A8240EFFF89CEF4C13940F3DEDAB43F533D18368E369107F`, applied four
update-only actions with `0 added, 4 changed, 0 destroyed`. API revision
`mtg-rag-dev-api-00014-kcx` and the evaluation job became Ready on the same digest in
`asia-east1`. No migration, ingestion, corpus, or production action occurred.

The exactly-once zero-retry execution `mtg-rag-dev-evaluation-9p8m8` failed on task attempt zero
during `exact-008`. A Luna answer contained `U+0000`, which PostgreSQL/asyncpg rejected at the
assistant-message persistence boundary. The run produced no retained capture, so it cannot prove
recall, citation coverage, expected behavior, service-path latency, or shipped per-repair
telemetry.

The cleanup and immutability controls did pass: independent database queries found zero synthetic
evaluation users, conversations, messages, usage, attempts, or evaluation-cache rows, and retained
GCS state stayed at the same three objects and 421,865 bytes. A test-first local fix now strips NUL
characters from provider-returned answer, citation-claim, and assumption text and revalidates the
structured answer. A second RED/GREEN regression maps post-sanitization schema invalidity to the
existing content-free `ModelOutputError` path. The current backend gate is 263 tests at 85.66%
branch coverage, with a 49-test recovery slice, Ruff, and strict mypy green.

The public-launch recommendation remains blocked. The authorization was consumed; a fresh scoped
authorization is required to build and deploy the fix and run one complete create-only
same-region capture. Production authorization remains separate.

## Replacement P0 development qualification result - 2026-08-22

The operator separately authorized and consumed one replacement development qualification. Cloud
Build `a5d7a3b3-d010-4c0c-87ad-db17869d81e8` passed all eight release steps and published digest
`sha256:4895406d6c848d2dcecff3dd5ce6ef8d4a2927d9d5cac92f203d161406dd4fc2`. Saved-plan
SHA-256 `11B2A0D4764B5034E7371838BF8978631929F93FF1C6DAB8CD47E81F0E802D79` applied four
development image updates with `0 added, 4 changed, 0 destroyed`. Revision
`mtg-rag-dev-api-00015-znf` and evaluation job generation 6 were Ready on the same digest in
`asia-east1`; no migration, ingestion, corpus, or production action occurred.

Exactly one new execution, `mtg-rag-dev-evaluation-9hzsj`, succeeded on task attempt 0 with one
task and zero retries. It created exactly one retained 179,878-byte object, generation
`1787349338322494`, whose metadata and local SHA-256 both equal
`3805FBC3A13A3B415E21C3FB746B24067DFD3A298C7375D6DE88C413E2AC5A1D`. Post-run cleanup
left all synthetic evaluation row families and eval cache at zero, while corpus identities, hashes,
and counts remained unchanged.

The complete packet is negative release evidence rather than an evidence gap. The authoritative
121-case grader passes expected behavior (0.9008264463), citation-ID validity (1.0), cached API p95
(39.478 ms), and negative-pair reuse (0), but fails recall@8 (0.8989898990), required-reference
citation coverage (0.8181818182), and retrieval p95 (959.974 ms). Context-specific failures remain
at `followup-003`, `followup-010`, and `followup-007`. Repair telemetry is complete and consistent
for all 120 uncached cases, including 45 repaired cases.

The public-launch recommendation remains blocked. P0-AC-001, P0-AC-002, and P0-AC-004 require
engineering remediation and a separately authorized future artifact; this result does not authorize
a retry and does not authorize production.

## Latest P0 development qualification and local continuation - 2026-08-22

One later authorized development cycle supersedes the preceding packet as latest evidence. Cloud
Build `9f1e9c11-6c7e-477d-aa13-0cc887bfb17a` passed all eight release steps and published digest
`sha256:aed0c9ebdf2bd41a1cc8b638ef41f905bcdf108413573362ef7908417afa60a7`. Saved plan
SHA-256 `3576673770294B03D265F28A1812AB14AB6474869450BCDEE621EEBE567DB8CA` applied four
development image updates with `0 added, 4 changed, 0 destroyed`. Revision
`mtg-rag-dev-api-00016-9dc` and evaluation job generation 7 were Ready on the same digest in
`asia-east1`; no migration, ingestion, corpus, or production action occurred.

Exactly one execution, `mtg-rag-dev-evaluation-mwmjq`, succeeded on task attempt 0 with zero
retries. It created one retained 181,146-byte object, generation `1787396385333503`, whose metadata
and local SHA-256 equal
`41C9DC11B28F580B64B103E651BD91BBAD4586C01BD74A7AF16BAD1BCE1A1AB9`. Cleanup left all
evaluation row families and evaluation cache at zero, while corpus identities and suite hash stayed
unchanged.

The authoritative packet passes recall@8 (0.9595959596), expected behavior (0.9586776860),
citation-ID validity (1.0), retrieval p95 (489.128 ms), cached API p95 (46.099 ms), and negative-pair
reuse (0). Required-reference citation coverage fails at 0.8989898990. Context-specific failures
are `followup-003` retrieval/citation and `followup-004` retrieval/citation/behavior; both
missing-context cases clarify and all context cases remain cache-ineligible. P0-AC-004 now passes;
P0-AC-001 and P0-AC-002 remain open.

The subsequent local-only candidate rotates changed contracts to `mtg-answer-v6`/`rrf-v6`,
protects bounded anchored rules through fusion, and limits mandatory evidence to explicit
rule/card/definition targets while preferring the specific governing procedure. Final read-only
development evidence protects both `state-010` references (`704.3` rank 1 and `117.3b` rank 3).
It passes 279 backend tests at 85.71% branch coverage, Ruff, strict mypy across 59 source files, and
dependency audit, but has not been built or captured. Exactly one development-only build, reviewed
update-only apply, zero-retry capture, cleanup, and create-only object were authorized. Build
`d9f99669-6f73-48fe-a23b-8115e1acf29f` consumed that cycle and failed 1/105 frontend E2E checks on
a small 375px rasterization drift before runtime-image publication, Terraform, or capture. The
scale-aware 0.1% correction passes ten consecutive focused Linux Chromium runs and the complete
frontend gate in two isolated Linux environments. The Cloud Build-equivalent
`node:24-bookworm-slim` run passed zero-vulnerability audit, lint, 58/58 unit tests at 92.25%
statement/90.19% branch coverage, production/PWA build, fresh Playwright 1.62.1 browser
installation, and 105/105 E2E cases across all five projects. API/job state and execution count are
unchanged, and no apply, database write, or object occurred. Public launch remains blocked; another
build and every production action require fresh explicit authorization.

## Prior retained `v6` qualification - 2026-08-23 local

The separately authorized replacement cycle completed without a retry. Cloud Build
`1125f44f-fd7d-4beb-8450-38a146a3a1a4` passed all eight release steps and published immutable
digest `sha256:556e44947091064aef6fce3f0e2de2ca29e31efc62b881e8ebc88a0e1df186a8`. Reviewed
saved-plan SHA-256 `785026F47FEC4A42DEBCE643C45CB6A00D36A4CA22C851D74DD24C7C1DE2D3B1` contained exactly
four update-only development image changes; its one hash-guarded apply reported
`0 added, 4 changed, 0 destroyed`. Ready revision `mtg-rag-dev-api-00017-jlk` took 100% traffic and
evaluation job generation 8 used the same digest with one task and `maxRetries=0`. Startup and
liveness health probes returned 200. Migration and ingestion jobs did not execute, and production
was neither planned nor changed.

Exactly one execution, `mtg-rag-dev-evaluation-xnbcb`, succeeded on task attempt 0 in 6m59.43s and
created exactly one retained object:

`gs://mtg-rules-desk-dev-mtg-rag-dev-snapshots/evaluation-captures/mtg-rules-v1/2026/08/22/a6537442-fc07-4347-b728-a1ef7bc4f3d8.json#1787416391304068`

The object is 173,144 bytes and retained through 2027-08-22T16:33:11Z. Its metadata and local
SHA-256 both equal
`64801CEDAFC981286C520436551140691105E9839B9F5BE7743466A8B689B61D`. Execution and object
inventories each increased by exactly one. Read-only cleanup verification found every evaluation
row/cache category at zero; cards/rules/rulings identities and counts were unchanged; the temporary
proxy and listener were stopped.

The authoritative grader passes recall@8 (0.9696969697), expected behavior (0.9669421488),
citation-ID validity (1.0), cached API p95 (54.690 ms), and negative-pair reuse (0). It fails
required-reference citation coverage (0.9292929293) and retrieval p95 (513.617 ms). Eight of nine
answer-bearing follow-ups retrieve and cite all declared references; all nine answer, both
missing-context cases clarify, and none of the eleven context cases hits cache. `followup-011` is
the sole context miss. Telemetry is complete for 120 uncached cases, with 9 repaired and 111
unrepaired.

At that checkpoint the public-launch recommendation remained blocked. This packet closed P0-AC-003
and P0-AC-005 through P0-AC-009, but P0-AC-001, P0-AC-002, and P0-AC-004 remained failed on complete
same-region evidence. No retry or production action was authorized for that cycle.

## Local `v7` continuation - 2026-08-23

The changed local candidate keeps vector search and the GIN lexical path as independent RRF inputs.
It narrows only the GIN candidate anchor from 50 to 32 rows, ranks current-question terms ahead of
prior context, selects one protected governing citation when no explicit target owns the
requirement, uses rule-ID-free governing language with bounded parent-heading coverage, and rotates
prompt/retrieval boundaries to `mtg-answer-v7`/`rrf-v7`.

Read-only development-corpus checks place every retained citation-miss reference at lexical rank 1
with protection: `613.1a`, `614.1`, `614.4`, `704.5a`, `712.10`, `117.4`, and `603.3`. All 121
read-only corpus-scale EXPLAIN plans use `ix_passages_search_vector`, cap anchor output at 32 rows,
and report query-only p95/max of 53.930/74.819 ms. This is local proxy evidence and cannot replace
the <=500 ms same-region service-path gate.

Local/build-equivalent qualification passes 284 backend tests at 85.74% branch coverage, the
Python 3.12.14 container gate, Ruff, strict mypy across 59 files, dependency audits, 59/59 frontend
tests, PWA, 105/105 Playwright cases, Terraform format/validation, runtime non-root/secret
inspection, and pinned Trivy with zero HIGH/CRITICAL or secret findings. Migration execution was
intentionally omitted from the final container gate.

The evaluation client now has an explicit focused contract for zero OpenAI transport retries in
addition to the Cloud Run job's zero task retries. The one replacement authorization was then
consumed by the failed build recorded below. Every production action, migration, ingestion
execution, and retry remains excluded.

## Authorized `v7` build failure and current release boundary - 2026-08-23

Cloud Build `b8d54f24-d89b-4a5d-91e9-be42f2f337c8` consumed the one authorized replacement build.
Secret scanning and all 284 backend gates passed; the frontend passed 103/105 browser cases before
the Firefox public-page WCAG check and Mobile Safari welcome-layout check reached the original
30-second Playwright timeout. No assertion, snapshot, accessibility, or application defect was
reported. Terraform, runtime-image construction/inspection, Trivy, and publication never ran.

Test-first recovery sets Playwright to one worker, zero retries, and a 60-second per-test timeout.
The focused configuration test failed before each timeout/worker correction. A one-CPU Linux stress
run passed the two affected checks 20/20 across Firefox and Mobile Safari; its first cold Firefox
welcome check took 31.8 seconds. The exact `node:24-bookworm-slim` sequence then passed audit, lint,
59/59 unit tests at 92.09% statement/90.09% branch coverage, PWA, and 105/105 browser cases in
4.7 minutes with zero retries.

Read-only post-failure checks found no build result image or Artifact Registry build tag. API
revision `mtg-rag-dev-api-00017-jlk`, its prior digest, evaluation job generation 8, seven execution
names, and six retained objects totaling 956,033 bytes are unchanged. No publication, plan/apply,
deployment, evaluation write/cleanup, retained write, migration, ingestion, or production action
occurred. At that checkpoint the public-launch recommendation remained blocked and another build
required fresh explicit authorization; the separately authorized successful retry is recorded next.

## Successful `v7` retry build and pending deployment boundary - 2026-08-23

The operator separately authorized one retry Cloud Build/publication. Build
`04f72f67-4feb-486c-bfe8-23d737be12d4` passed all eight configured gates, including all 284 backend
tests, frontend audit/lint/59 unit tests/PWA/105 zero-retry browser cases, Terraform validation,
runtime inspection, and pinned Trivy. It published immutable digest:

`sha256:251b3cc97d0ca52328290fe7097b6b54e08fd714e406593d119ca7939e295302`

Cloud Build binds that image to generation-pinned source archive
`gs://mtg-rules-desk-dev_cloudbuild/source/1787429598.419983-dd2bd1dab2364b91a1bf6a964848ea21.tgz#1787429602549241`,
SHA-256 `0280650AD94900D3C806DD6D86E59EA48FEEE7A34816806011324210471C07B5`.
Artifact Registry independently resolves the same digest. Its reported SLSA build level is unknown,
so no SLSA attestation claim is made.

Read-only reconciliation confirms no implicit rollout: API revision `mtg-rag-dev-api-00017-jlk`
and evaluation job generation 8 remain on prior digest
`sha256:556e44947091064aef6fce3f0e2de2ca29e31efc62b881e8ebc88a0e1df186a8`; the job remains at
`maxRetries=0`; execution count remains seven; and retained inventory remains six objects totaling
956,033 bytes. No Terraform plan/apply, deployment, evaluation write/cleanup, retained write,
migration, ingestion, or production action occurred.

At that checkpoint the immutable build gate was closed, but deployment and capture still required
separate authorization. The subsequently authorized result is recorded below; production remained
blocked throughout.

## Retained `v7` development qualification - 2026-08-23

The operator authorized one reviewed update-only development Terraform plan/apply and one
zero-task-and-transport-retry 121-case capture. Plan SHA-256
`E37D3553C150E7FBB12FA13814845090D8524D5B575DA61AAD3BFBE8A460F0C9` passed an exact JSON
allowlist and applied as `0 added, 4 changed, 0 destroyed`; every changed leaf was an image update
to the published digest. Revision `mtg-rag-dev-api-00018-cwq` is Ready at 100%, and evaluation job
generation 9 is Ready with one task and `maxRetries=0`. Migration and ingestion did not execute;
production was neither planned nor changed.

The approved suite remained 121/121 unique cases at SHA-256
`DB36213A0105732E5A09F741C16F68EC1FF5C98F72AC9AE9540F113119FAB4A7`. Preflight had seven
executions, six retained objects/956,033 bytes, zero evaluation residue, and 118,771 unchanged
active passages. Exactly one execution, `mtg-rag-dev-evaluation-r7lbf`, completed task 0 with zero
failed/retried tasks in about 8m41s. The only new retained object increased inventory to seven
objects/1,131,529 bytes:

`gs://mtg-rules-desk-dev-mtg-rag-dev-snapshots/evaluation-captures/mtg-rules-v1/2026/08/22/2b156e73-3174-4a22-a094-1c44958f2ec2.json#1787433858431773`

The 175,496-byte exact generation is retained through `2027-08-22T21:24:18Z`; object metadata and
the generation-pinned local copy both have SHA-256
`642607B39D5633FB8EACBBABB9D333EA44FF2161C2E1B65044C6F226E7EC9155`. Post-run read-only checks
found every evaluation residue category at zero and unchanged cards/rules/rulings identities;
both temporary proxy sessions stopped.

The canonical grade is negative on one strict metric:

| Gate | Observed | Required | Result |
| --- | ---: | ---: | --- |
| Retrieval recall at 8 | 0.9696969697 | At least 0.90 | Pass |
| Required-reference citation coverage | 0.9292929293 | At least 0.95 | Fail |
| Expected behavior | 0.9834710744 | At least 0.90 | Pass |
| Citation-ID validity | 1.0 | Exactly 1.0 | Pass |
| Retrieval p95 | 439.582 ms | At most 500 ms | Pass |
| Cached API p95 | 94.924 ms | At most 1,500 ms | Pass |
| Negative-pair reuse | 0 | Exactly 0 | Pass |

Seven cases miss required citations; `followup-001` is citation-only for `702.11`, and
`followup-010` misses retrieval/citation for `509.1b`. All nine answer-bearing follow-ups still
answer, both missing-context cases clarify, and all context cases remain cache-ineligible.
P0-AC-001 and P0-AC-002 fail; P0-AC-003 through P0-AC-009 pass. The development authorization is
consumed, no retry is attempted, and public launch remains blocked.

## Local `v8` changed-candidate addendum - 2026-08-23

Test-first local remediation now chooses one official governing rule per domain anchor branch,
requires both pre-priority procedures, requires a contextual card's linked ability rule, preserves
direct-subrule-before-parent ordering, and rotates cache boundaries to `mtg-answer-v8`/`rrf-v8`.
A read-only service check against the development corpus, with no model call or database write,
requires every reference from the seven retained citation misses. Complete backend evidence is
292/292 tests at 85.87% coverage, Ruff, strict mypy across 59 source files, 31/31 PostgreSQL
retrieval integrations, and a clean dependency audit.

An all-121 read-only plan audit additionally proves the main and protected-winner statements use
the GIN search-vector index and remain bounded. Main p95/max are 44.407/81.325 ms; the 45 winner
plans are limited per clause, return at most two rows, and measure 39.377/42.075 ms. A fixed-zero-
vector service diagnostic is explicitly excluded from release scoring because it uses neither the
configured question embedding nor model output.

This does not change the audit recommendation. No `v8` build, publication, Terraform action,
deployment, evaluation execution, database/GCS write, migration, ingestion, retry, or production
action occurred. Public launch remains blocked until a separately authorized immutable `v8`
same-region packet passes every P0 criterion and the independent policy/production blockers are
resolved.

## Retained `v8` qualification and local `v9` continuation - 2026-08-23

The authorized `v8` cycle completed without retry. Cloud Build
`d6cd330c-0e9a-4c93-a675-52cfa75a378e` passed all eight gates and published digest
`sha256:37b54d7cb996b0f4d9d8e0ea087ec30bdcbdd5c0f3d599402d68c50d9f19db63`.
The reviewed plan changed exactly four development image fields and applied as `0 added, 4 changed,
0 destroyed`. API revision `mtg-rag-dev-api-00019-gbm` and evaluation generation 10 are Ready on
that digest. Exactly one execution, `mtg-rag-dev-evaluation-sbmjv`, succeeded with zero retries and
created exactly one retained generation ending in
`1591ad90-8822-4389-94c9-5b39f45c6632.json#1787477615321283`, SHA-256
`DCD43EE6472A1DAFBD29C99F384ECA887AD0FC8EFF975E8D47C8D127ADDB5630`. Cleanup and
corpus-identity checks passed; migration, ingestion, and production were untouched.

The canonical grade is negative: recall 0.9595959596 passes, citation coverage 0.9090909091 fails,
behavior 0.9669421488 passes, citation-ID validity 1.0 passes, retrieval p95 512.00384 ms fails,
cached API p95 58.986118 ms passes, and negative-pair reuse is zero. The cycle is consumed and no
retry occurred.

Local `v9` fixes the nine retained citation misses with bounded governing-rule projections and
governing-parent constraints, and overlaps independent card-alias/glossary reads to address the
measured exact-lookup latency. Exact, GIN lexical, and HNSW vector retrieval remain independent RRF
inputs. Local qualification passes 297 backend tests at 86% branch-aware coverage, Ruff, strict
mypy, dependency audit, Terraform validation, and real-corpus read-only verification for all 16
targeted regression cases.

At that checkpoint, public launch remained blocked and the then-newly authorized `v9` cycle still
needed an immutable build, reviewed update-only apply, zero-retry capture, cleanup, and one
create-only retained object. The following section records that cycle's actual outcome.

## Retained `v9` qualification and local `v10` continuation - 2026-08-23

The authorized `v9` cycle is complete and consumed. Build
`7c45084a-9db7-4df8-ac3b-9bfe5a7c3f86` passed all eight gates and published immutable digest
`sha256:23fa0bcb79d34b47a591f8f2deda152c9ad15bc091de783e687f0370e9e5707f`. Hash-pinned plan
`83536046D66961765256714BD1D7A1079E7678EDA383C779BB01E784605BC531` applied exactly four
development image updates as `0 added, 4 changed, 0 destroyed`. API revision
`mtg-rag-dev-api-00020-fsp` and evaluation generation 11 are Ready; migration and ingestion did not
execute, and production was excluded.

Exactly one execution, `mtg-rag-dev-evaluation-jkb54`, succeeded with one task and zero retries,
creating exactly one 177,861-byte retained generation:

`gs://mtg-rules-desk-dev-mtg-rag-dev-snapshots/evaluation-captures/mtg-rules-v1/2026/08/23/ac4665f9-7a52-4939-a533-b29594191758.json#1787494400684339`

Server/local SHA-256 is
`6CA9B9C66DB7F33561D77B75434D899ED6FE1F23DE88371B8200086887D0A5DE`; pre/post residue is zero,
the 118,771-passage corpus identities are unchanged, and inventories changed exactly 9→10
executions and 8→9 objects. The grade passes recall 1.0, citation coverage 0.9898989899, behavior
0.9669421488, citation validity 1.0, cached API p95 47.965465 ms, and negative reuse zero. Retrieval
p95 is 525.002083 ms and fails the 500 ms release gate. Public launch therefore remains blocked.

Local `v10` overlaps the existing one embedding with embedding-independent exact and GIN text
retrieval; HNSW vector search remains separate and unchanged, and RRF still performs fusion. RED
reproduced serial startup in both hybrid and Ask workflows. A production-audit pass then found that
plain concurrent joins could propagate one failure while leaving siblings alive; two additional RED
tests reproduced embedding-to-text and exact-to-lexical leakage. GREEN explicitly cancels and drains
started siblings before re-raising. A final audit found that HNSW still waited for exact/GIN
completion in Hybrid, Ask, and evaluator paths; three deadlock REDs reproduced it, and GREEN passes
the in-flight prepared task through so vector work begins on embedding readiness in direct/eval
paths and after the semantic-cache miss in Ask. The final matrix
passes 326/326 under the Python 3.12 test image at 85.43% branch-aware coverage, Ruff, strict mypy,
dependency audit, and 32/32 PostgreSQL integrations. Frontend audit/lint/59-case coverage/PWA and
all 105 zero-retry Playwright cases pass; clean Terraform validation, runtime
non-root/credential inspection, gitleaks, and Trivy also pass. The read-only no-model corpus
diagnostic retains all nine `v8` regression fixes.
Retained-telemetry projection is 366.748525 ms p95, but that is not release evidence. No `v10`
external action is authorized by the consumed cycle; a fresh exact authorization and same-region
packet are required.

Read-only preflight on 2026-08-24 confirms the retained `v9` build/digest remains latest, the API
and all three jobs remain Ready on that digest, evaluation executions remain 10, migration and
ingestion execution histories are unchanged, and retained objects remain nine. The working-tree
upload manifest initially included `backend/.tmp-pytest-cache-v10`; a focused RED/GREEN widened
the Cloud Build ignore rule to `.tmp-pytest-cache*/`. The manifest target passes 22/22, the actual
gcloud upload listing excludes that cache. Checked-in source-manifest and Terraform-plan-review
tooling passes 20/20 tests, Ruff, strict mypy, and 86.11% combined branch coverage. Its intermediate
create-only freeze/recheck matched 194 files at aggregate SHA-256
`3ee702406d60d628bf30419292c55a33c3ab51c785ed8d63429b8f2e3fbb1a48`. The generic plan reviewer
also passes against the retained v9 binary plan: 54 resources, 50 no-ops, four image-only updates,
unchanged outputs, all checks green, and only the two reviewed read-only drift shapes. The complete
backend gate then passed 326/326 at 85.43% branch-aware application coverage.

A final configured-gate RED/GREEN on 2026-08-24 binds qualification-tool static analysis into the
actual Cloud Build backend step. Ruff now covers `app`, `tests`, and
`/workspace/scripts/qualification`; mypy covers `app` and the qualification tools. The exact
Python 3.12/PostgreSQL build-equivalent sequence passes migrations, Ruff, strict mypy across 61
source files, dependency audit, 327/327 tests, and 85% displayed branch-aware application coverage
(85.43% exact). Focused source-manifest, saved-plan-review, and runtime-manifest tests pass 43/43.
The final r25 create-only freeze/recheck matches 194 upload files at aggregate SHA-256
`ab22aa01377e12ba655f42b1413751155152431c7f6e0e039139f09495265a74`. The isolated temporary
database and network were removed. No build, publication, Terraform action, deployment, capture,
migration execution, ingestion execution, retained-object write, retry, or production action was
performed. A future authorized cycle must recheck this freeze immediately before submission and
retain the generation-pinned Cloud Build source hash.

## Retained `v10` development qualification - 2026-08-24 local

The exact authorized cycle is complete and consumed. Cloud Build
`4dba8ba5-684f-4dd3-83f3-6ebbf7b5049c` passed all eight gates and published immutable digest
`sha256:870b46a23e6406142f89eb04969e2d5b623b4f69d72d6b24c19497764b3ffefc`. Generation-pinned
source `1787506028707171` has SHA-256
`18F6B1D8AE48FFB0058C96636668747F1A8854CCF59C8F4700CB331001B92907` and matches the frozen
194-file manifest aggregate
`ab22aa01377e12ba655f42b1413751155152431c7f6e0e039139f09495265a74`.

Plan SHA-256 `45E4C6D0EF25E78A90306E640120DB9F4098F8D1BB0EA0E0E24E9F2494F771EB` passed the strict
reviewer with 54 resources, 50 no-ops, exactly four update-only development image leaves, no
output or production changes, and only the allowlisted read-only drift. The exact binary applied
once as `0 added, 4 changed, 0 destroyed`. API revision
`mtg-rag-dev-api-00021-7pf` and evaluation generation 12 are Ready on the digest. A direct
authenticated `/healthz` probe reaches the deployment's ingress boundary as Google 404 and is not
claimed as an application-health pass; Cloud Run Ready state and the successful evaluation job on
the same digest provide the deployment evidence for this packet.

Exactly one execution, `mtg-rag-dev-evaluation-mrzzf`, succeeded with one task and
`maxRetries=0`, creating exactly one retained generation:

`gs://mtg-rules-desk-dev-mtg-rag-dev-snapshots/evaluation-captures/mtg-rules-v1/2026/08/23/1c2ff72d-005e-4a45-b8b8-323f8e39c56f.json#1787508036393785`

It is 177,586 bytes, metageneration 1, retained through 2027-08-23T18:00:36Z, with matching
server/local SHA-256
`B28ED889EBEF8838F2F7C4FF2520735F107B87D879D8E1212DD7C953C11EEB91`. Immediate read-only
pre/post checks found all six residue categories at zero and identical capture-time active-source
identities. The exact grade passes recall 1.0, citation coverage 0.9797979798, behavior
0.9669421488, citation validity 1.0, retrieval p95 322.348890 ms, cached API p95 54.807516 ms, and
negative reuse zero. Telemetry is complete for all 121 cases and all 120 uncached model calls
(28 repaired, 92 unrepaired).

The enabled daily cards scheduler independently started ingestion execution
`mtg-rag-dev-ingestion-ld56k` during the capture window; the agent did not invoke it. Timestamped
source state proves the prior cards version remained active through evaluation completion at
18:00:39Z and the scheduler's new version activated only at 18:05:55Z. The capture therefore used a
stable corpus. The out-of-band execution later succeeded and is disclosed as an operational
scheduling risk, not as part of the authorized cycle. Production, migration execution, credential
changes, unrelated Terraform actions, and retries were not performed.

This packet closed the original conversation-context P0 in development. Subsequent v11-v14 evidence
above proves PostgreSQL request idempotency and the stricter exact-excerpt contract; v14 now clears
the changed-candidate technical development gate. This does not change the overall 72/100
production-readiness recommendation. For the separately scoped public development preview,
qualified policy/source-use review and any resulting publication update remain the non-technical
gate. Operator-owned production state and the listed production drills are deferred production gates.
