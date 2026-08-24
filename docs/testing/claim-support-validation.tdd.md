# Claim-support validation TDD evidence

**Date:** 2026-08-24
**Source:** Operator-approved 320-character normalized exact-excerpt design; no plan file used.

## User journeys

- As a rules-desk user, I want each displayed citation claim copied from its cited passage so that
  I can inspect the evidence instead of trusting a model-written paraphrase.
- As an operator, I want substantive answers without citations or with unsupported excerpts to
  receive only one repair attempt and then abstain so that invalid prose is not persisted or cached.
- As a release reviewer, I want the prompt/cache boundary rotated when the output contract changes
  so that v10 paraphrased claims cannot be reused as v11 exact excerpts.

## RED and GREEN report

The RED test target was:

```text
..\.venv\Scripts\pytest.exe tests\unit\test_citations.py tests\unit\test_generation_service.py tests\unit\test_openai_adapter.py tests\unit\test_config.py -q
```

It failed during collection with the intended missing-contract error:

```text
ImportError: cannot import name 'CitationSupportError' from 'app.generation.citations'
```

After the minimal implementation, the same target passed:

```text
25 passed in 1.36s
```

## Test specification

| # | What is guaranteed | Test target | Type | Result |
| --- | --- | --- | --- | --- |
| 1 | A citation claim is capped at 320 input characters | `test_model_citation_excerpt_is_limited_to_320_characters` | Schema unit | PASS |
| 2 | NFKC compatibility and whitespace differences normalize deterministically | `test_normalized_exact_excerpt_matches_unicode_and_whitespace_variants` | Validator unit | PASS |
| 3 | A paraphrase that is not a contiguous source excerpt is rejected with its passage ID | `test_paraphrased_claim_raises_repairable_support_error` | Validator unit | PASS |
| 4 | An unsupported excerpt receives exactly one repair and a valid exact excerpt can recover | `test_unsupported_excerpt_gets_exactly_one_repair_attempt` | Service unit | PASS |
| 5 | A substantive answer with no citations receives exactly one repair | `test_substantive_answer_without_citations_gets_one_repair_attempt` | Service unit | PASS |
| 6 | A second unsupported excerpt discards the prose and returns a grounded abstention | `test_second_unsupported_excerpt_returns_grounded_abstention` | Service unit | PASS |
| 7 | Initial and repair prompts state the exact-excerpt, 320-character, no-paraphrase contract | `test_adapter_uses_responses_structured_output_without_server_storage_or_tools`; `test_adapter_labels_required_evidence_and_missing_citation_repair` | Adapter unit | PASS |
| 8 | The default prompt/cache boundary is `mtg-answer-v11` while retrieval remains `rrf-v10` | `test_default_generation_model_is_luna` | Configuration unit | PASS |
| 9 | A release capture independently records unsupported excerpt IDs and requires 100% validity | evaluation harness and staging-runner tests | Evaluation unit | PASS |
| 10 | A v10 capture without explicit excerpt-validation evidence cannot load as v11 evidence | `test_v11_run_loader_requires_explicit_excerpt_validation_evidence` | Capture-contract unit | PASS |

## Coverage and broader gates

The original four-module slice passed at 95.06% branch-aware coverage. The expanded generation and
evaluation slice passes 56 tests at 80.28% branch-aware coverage. The complete database-free
backend gate passed `296 passed, 57 deselected`; Ruff passed and strict mypy passed across 61 source
files. The unchanged frontend contract also passed 65 Vitest tests, ESLint, and the production
TypeScript/Vite/PWA build; Vite reported only its existing advisory for a chunk over 500 kB.

## Known gaps and release boundary

- Deterministic substring validation proves the displayed excerpt exists in the cited passage. It
  does not prove semantic entailment between every answer sentence and that excerpt; the retained
  citation-precision and behavior evaluation gates remain required.
- PostgreSQL-backed request-idempotency integration and the `0002` migration have since passed in
  the r4 replacement Cloud Build and development migration execution.
- The deployed development service is now v11, but the retained v11 evidence is a failed
  qualification packet. Deployment success is not release-gate success.
- The v11 grader now requires `unsupported_citation_ids=[]` for every case. Retained v10 captures
  do not contain this field and cannot be reused as v11 qualification evidence.
- Operator design approval is not qualified WotC/Scryfall source-use or legal clearance.

No checkpoint commit was created because the worktree already contains unrelated user changes and
the task did not authorize committing them.

## Qualification continuation

The initial authorized Cloud Build upload was frozen and reverified at 197 files with aggregate
SHA-256 `65dd9df07fb12849607e3ac2aac0dbf2545ff3e39a36373902b8afb99350cc3b`. Cloud Build
`a669ac15-5367-48b0-abd6-f2c691ae3a5b` used generation-pinned source object
`source/1787571088.827693-b5801a2a2ca84daa850d72a2104fc978.tgz#1787571089457834` and failed
the temporary PostgreSQL backend gate at `352 passed, 1 failed`. The exact-excerpt tests were not
the failure: the request-idempotency insert mapped Python `None` to JSON `null`, violating the
intentional SQL-NULL response-state constraint.

The corrected response mapping and its regression test are frozen in a new create-only 197-file r4
manifest with aggregate SHA-256
`9568309a7087cc1abee6da05e14e8c67d3621fe5b3acd03d66c6d8d04b7cac7f`. The manifest was
immediately reverified and differs from r3 only in `backend/app/db/models.py` and
`backend/tests/unit/test_database_metadata.py`. Local post-fix gates pass `297 passed, 57
deselected`, Ruff, and strict mypy.

Read-only cloud reconciliation at that point confirmed the failed build published no tagged image
and triggered no downstream phase. API revision `mtg-rag-dev-api-00021-7pf` still served 100% of
traffic, and the API and all three jobs still used retained v10 digest
`sha256:870b46a23e6406142f89eb04969e2d5b623b4f69d72d6b24c19497764b3ffefc`.
Migration and ingestion generations remained 22, evaluation remained generation 12, execution
counts remained 3/21/11, and retained evaluation inventory remained 10 objects. The consumed
authorization excluded retries; r4 therefore required a separately authorized replacement cycle.

An earlier 199-file preliminary manifest remains create-only evidence of the detected source-scope
problem: uppercase `Documentation/` was included even though lowercase `docs/` was excluded. A
RED/GREEN manifest-policy test added `Documentation/` to `cloudbuild.ignore`. The 197-file r2 and r3
manifests are retained as historical evidence; only r4 is eligible for a replacement submission.

## r4 development qualification result

The authorized replacement cycle used aggregate source manifest
`9568309a7087cc1abee6da05e14e8c67d3621fe5b3acd03d66c6d8d04b7cac7f`. Cloud Build
`5fd9a8ed-d4fd-4b48-911f-fb9414186cfa` passed all eight build gates and published immutable image
`sha256:df0644eb31a4fafccd4e55deeccabd2dfe5dc3d1ca40d29fccde70ca0f6d7b66`. One reviewed
migration-only apply, successful zero-retry migration execution `mtg-rag-dev-migration-mmqd5`, and
one reviewed API/ingestion/evaluation image-only apply placed all four development leaves on that
digest. The ingestion job was not executed.

Exactly one evaluation execution, `mtg-rag-dev-evaluation-nmh8x`, completed successfully in
`asia-east1` with `maxRetries=0` and produced exactly one create-only retained object:

`gs://mtg-rules-desk-dev-mtg-rag-dev-snapshots/evaluation-captures/mtg-rules-v1/2026/08/24/ad5c988f-d0a2-4f63-8050-55e5274107b7.json#1787574988434922`

The 169,162-byte object's metadata SHA-256 and the exact downloaded generation both equal
`310db56bce7739fbc3c8712dec02a3a26bfe95ca7e9907b2c92e3be32f99142c`; its retention expiration is
`2027-08-24T12:36:28Z`. The authoritative grader was run without `--allow-pending-review` and
returned:

| Gate | Observed | Required | Result |
| --- | ---: | ---: | --- |
| Recall@8 | 1.0 | At least 0.90 | PASS |
| Citation-ID validity | 1.0 | Exactly 1.0 | PASS |
| Citation-excerpt validity | 1.0 | Exactly 1.0 | PASS |
| Required-reference citation coverage | 0.8585858586 | At least 0.95 | **FAIL** |
| Expected-behavior accuracy | 0.8677685950 | At least 0.90 | **FAIL** |
| Negative-pair reuse | 0 | Exactly 0 | PASS |
| Retrieval p95 | 385.570353 ms | At most 500 ms | PASS |
| Cached API p95 | Infinity (no cache hits) | At most 1,500 ms | **FAIL** |

All 14 citation misses were citation-only: the required passage was present in the retrieved top
eight, but the final response did not cite it. Sixteen cases had behavior mismatches: fourteen
expected answers (including two context cases) became abstentions after the one repair boundary,
`clarify-002` became an abstention, and `abstain-008` answered.
All 121 cases were uncached, so the run contains no qualifying cached-latency sample. The
excerpt-validity design itself worked—every retained citation claim passed the independent
320-character normalized exact-excerpt check—but generation/repair precision and cache-hit
evidence did not meet the release gate.

The citation-miss IDs are `exact-009`, `glossary-008`, `glossary-009`, `replace-004`,
`replace-007`, `replace-010`, `state-010`, `multiface-005`, `inject-003`, `inject-004`,
`inject-010`, `cache-007`, `followup-005`, and `followup-006`. The behavior-miss set is those 14
plus `clarify-002` and `abstain-008`. Component p95 values were 249.174 ms embedding, 231.185 ms
exact, 316.606 ms lexical, and 119.954 ms vector. No cache-write warning was present in the
execution logs; because the capture stores only the final cache-hit boolean, the next candidate
should retain cache eligibility, write outcome, candidate similarity, and rejection reason before
changing any safety threshold.

Post-capture read-only reconciliation found zero evaluation users, conversations, messages,
daily-usage rows, ask attempts, and run-version cache entries. The three active corpus hashes and
118,771 total passages were unchanged; the temporary proxy stopped, and its credential environment
was cleared. The failed packet is retained as immutable negative evidence. The authorization
excluded retries, so no second capture was run.

## v12 local remediation TDD — external qualification pending

The immutable v11 packet made the next acceptance criteria concrete before implementation:

1. A citation-only repair receives the prior structured candidate, so it does not have to recreate
   the answer, assumptions, confidence, and behavior from scratch.
2. The repair receives normalized, contiguous source excerpt options of at most 320 characters only
   for candidate/error passages; the validator still rejects unsupported text, permits one repair,
   and then abstains.
3. A context-free unresolved comparison clarifies deterministically, while a current local-event
   lookup abstains; conversation-backed comparisons and ordinary tournament rules questions remain
   answerable.
4. Every new capture records cache status and confidence, and the grader reports status counts and
   rejects status/hit disagreement. Legacy retained packets remain reproducible.
5. The prompt/cache boundary rotates to `mtg-answer-v12`; retrieval and its 0.98 semantic-cache
   safety threshold remain `rrf-v10` and unchanged.

The first RED target failed during collection because `_citation_excerpt_options` did not exist.
After the initial implementation, 36 tests passed and two existing prompt assertions exposed a
line-break mismatch and removed compatibility wording; both were reconciled without changing the
contract. Separate RED cases then proved that behavior policy was not enforced (`answer` observed
instead of `clarify`/`abstain`) and that the grader did not expose cache-status counts. The final
local evidence is:

- focused generation/evaluation/cache/config suite: `74 passed`;
- expanded branch-aware generation/evaluation/config slice: `77 passed`, total coverage 80.28%;
- complete database-free backend suite: `303 passed, 57 deselected`;
- repository-wide Ruff: pass;
- strict mypy: pass across 59 source files; and
- immutable v11 packet regrade: the exact original three failures and metrics were reproduced, with
  an empty cache-status count for the legacy capture.

The cache remediation does not lower the semantic threshold. `glossary-008` and `inject-004` have
the same normalized question; v11 abstained on both after citation repair, so no eligible first
answer existed for the later exact-cache read. v12 preserves a supported high-confidence candidate
during citation-only repair and records whether the later request is `exact`, `semantic`, `miss`,
or `ineligible`.

This is a local candidate, not release evidence. No OpenAI validation call, Cloud Build, image
publication, Terraform action, migration or ingestion execution, evaluation capture, database/GCS
write, or retained object was created. The create-only 197-file v12 source manifest is
`.tmp/v12-source-manifest-r1.json`, aggregate SHA-256
`bd151f9ce5574473913a4866c6da4dba8202e3e5a32a85dc27509579f728e0ea`. A future external cycle
must use that frozen manifest and a single zero-retry 121-case capture. A read-only
`gcloud meta list-files-for-upload` verification matched the same 197-file hash. The existing
`0002` migration already succeeded and this local change adds no schema migration.

## v12 next external qualification boundary

The changed candidate cannot clear the development-preview engineering gate through more local
tests. A separately authorized cycle must be limited to one build/publication against manifest
`bd151f9ce5574473913a4866c6da4dba8202e3e5a32a85dc27509579f728e0ea`; if successful, one reviewed
hash-pinned update-only Terraform plan/apply for the development API, ingestion-job, and
evaluation-job image leaves; exactly one zero-retry 121-case `asia-east1` capture; temporary
evaluation writes and cleanup; and one create-only retained object. No schema change exists, so the
migration image and migration execution are outside this cycle. Production, ingestion execution,
credential changes, unrelated Terraform changes, rollbacks, and retries remain excluded.

Read-only reconciliation immediately before this handoff confirmed:

- all four current development leaves use retained v11 digest
  `sha256:df0644eb31a4fafccd4e55deeccabd2dfe5dc3d1ca40d29fccde70ca0f6d7b66`;
- API revision `mtg-rag-dev-api-00022-gp7` is the latest ready revision;
- the latest migration, ingestion, and evaluation executions remain `mtg-rag-dev-migration-mmqd5`,
  `mtg-rag-dev-ingestion-ld56k`, and `mtg-rag-dev-evaluation-nmh8x`; and
- the most recent regional build remains successful v11 build
  `5fd9a8ed-d4fd-4b48-911f-fb9414186cfa`; no v12 build has been submitted.

## v12 authorized qualification result — stopped before Terraform planning

The operator authorized exactly one zero-retry v12 development cycle against the frozen manifest.
Immediately before submission, the actual `gcloud` upload listing matched all 197 files and
aggregate SHA-256
`bd151f9ce5574473913a4866c6da4dba8202e3e5a32a85dc27509579f728e0ea`. Cloud Build
`3f15a847-9bab-4bfb-816f-e2a6db4cf107` succeeded once and published immutable digest
`sha256:3ec25eef7b5bd5095a681ea496ed2a89f39611959a2ff3129e9b05a09d9653e5`. All eight build steps
passed. Its generation-pinned source is `1787580090134996`, with Cloud Build provenance SHA-256
`B20FE7D8F3BD7BA50F5142557F8E8A67B7C87B55612A961BF5700A79E89989A4`.

The sole authorized Terraform-plan invocation was rejected by the local Terraform CLI in 0.55
seconds with `Too many command line arguments`. This occurred at argument parsing, before a plan
file was created; `.tmp/v12-application-3f15a847.tfplan` does not exist. The intended immutable
input file SHA-256 is
`85316617266B97E6BC99A71EEF2B5FBE2EDC18056B55F3CCB05F4DBCF9BC2CB3`. Because retries were
excluded, the command was not reformulated or rerun. Read-only reconciliation confirmed API
revision `mtg-rag-dev-api-00022-gp7`, all four v11 image digests, and the latest migration,
ingestion, and evaluation execution identities were unchanged. No Terraform apply, evaluation
execution, temporary evaluation write, cleanup cycle, or retained object occurred. A narrowly
authorized replacement Terraform plan/apply-and-capture continuation is required to qualify the
successfully built digest; another Cloud Build is neither needed nor justified.

## v12 post-build Terraform blocker remediation — local only

User journey: as a release reviewer, I need a no-schema application rollout to update only the
development API, ingestion, and evaluation image leaves while proving that the migration image
remains pinned, so that review does not depend on fragile targeted-plan arguments.

The prior reviewer modeled only `migration` and post-migration `application` phases. Its
`application` variable gate required both `api_image` and `migration_image` to use the new digest,
which forced the no-schema v12 attempt to exclude migration through three `-target` arguments. The
PowerShell/Terraform boundary rejected that command before planning.

RED added two guarantees for a new `application-no-migration` phase: a 54-resource synthetic full
plan with 51 no-ops and exactly three image-only updates must pass when `migration_image` equals the
old immutable digest, and the same phase must fail if the excluded migration variable points at the
new digest. Before implementation, the focused run reported `2 failed, 8 passed` for precisely the
missing phase.

GREEN adds `application-no-migration` to the checked phase allowlist, reuses the exact three
application resource addresses, requires `api_image=new`, and requires `migration_image=old`. A CLI
regression also proves that `--phase application-no-migration` is accepted and returns a PASS for
the valid plan. Evidence:

| Guarantee | Command | Result |
| --- | --- | --- |
| No-migration phase permits exactly API, ingestion, and evaluation image leaves | `pytest backend/tests/unit/test_terraform_plan_review.py -q` | 11 passed |
| Migration variable cannot drift to v12 in that phase | same focused unit run | PASS |
| Reviewer branch-aware coverage | focused `pytest --cov=qualification_plan_review --cov-branch --cov-fail-under=80` | 80.51%, PASS |
| Repository-configured Python lint | `ruff check app tests ../scripts/qualification` from `backend/` | PASS |
| Strict typing | `mypy app ../scripts/qualification` from `backend/` | 61 source files, PASS |

No Cloud Build, Terraform plan/apply, remote refresh, service update, job execution, database write,
or GCS write occurred during this remediation. The replacement input is
`.tmp/v12-dev-application-no-migration-3f15a847.tfvars`; it pins the three application consumers to
v12 digest `sha256:3ec25eef7b5bd5095a681ea496ed2a89f39611959a2ff3129e9b05a09d9653e5`
and the migration job to deployed v11 digest
`sha256:df0644eb31a4fafccd4e55deeccabd2dfe5dc3d1ca40d29fccde70ca0f6d7b66`. The next authorized
plan can therefore be a normal full plan with no `-target` arguments, reviewed fail-closed with
`--phase application-no-migration`, 54 expected resources, and exactly three actionable leaves.

## v12 one-shot Terraform plan launcher — local hardening

User journey: as the operator, I need the replacement plan to cross the Windows shell boundary
without argument reinterpretation, while preserving the one-plan/no-retry authorization and the
authorized input hash.

RED introduced `test_terraform_plan_create.py` before its implementation. Collection failed with
`FileNotFoundError` for the intentionally absent `terraform_plan_create.py`, proving the missing
launcher boundary. GREEN adds a Python launcher that resolves Terraform once and calls it once with
the fixed argument array `plan`, `-input=false`, `-lock-timeout=0s`, one absolute `-var-file`, and
one absolute `-out`. It has no retry loop.

The launcher fails before invocation unless the working directory is exactly `infra/`, the input
is a non-symlink `.tmp/*.tfvars` inside the repository, its SHA-256 equals the explicit authorized
hash, and the output is a new `.tmp/*.tfplan` path. After Terraform returns success, it requires the
input hash to remain unchanged and the saved plan to exist and be non-empty; it then reports the
saved-plan SHA-256. It leaves any unexpected artifact intact for investigation rather than deleting
evidence.

| Guarantee | Evidence | Result |
| --- | --- | --- |
| One fixed-argument Terraform invocation and no shell-native target parsing | focused launcher unit suite | PASS |
| Hash mismatch, existing output, and outside-root output fail before invocation | focused launcher unit suite | PASS |
| Terraform failure is not retried | focused launcher unit suite | PASS, one invocation |
| Missing output or input mutation fails closed | focused launcher unit suite | PASS |
| Launcher branch-aware coverage | `pytest ... --cov=qualification_plan_create --cov-branch --cov-fail-under=80` | 8 passed, 89.47% |
| Complete database-free backend regression | `pytest backend/tests -m "not integration" -q` | 314 passed, 57 deselected |
| Repository-configured lint and strict typing | Ruff and mypy over `app`, `tests`, and qualification tools | PASS, 62 typed source files |

No Terraform command or external mutation was executed while building or testing the launcher. It
is post-build qualification tooling and does not alter the generation-pinned v12 runtime image.
Checkpoint commits were not created because the repository already contains a mixed dirty
worktree of operator changes; RED/GREEN command evidence is retained here without staging or
committing unrelated work.

## v12 replacement plan attempt — stopped at missing ADC

The operator authorized one replacement post-build continuation against the same published digest
and input SHA-256. The hash-pinned one-shot launcher invoked Terraform exactly once. Terraform
stopped before creating a saved plan because the GCS backend could not find Application Default
Credentials: `storage.NewClient() failed: ... could not find default credentials`. The launcher
reported failure and did not retry. The expected
`.tmp/v12-application-no-migration-3f15a847.tfplan` remains absent, so no review, apply, service or
job update, evaluation execution, temporary evaluation write, cleanup cycle, or retained-object
write followed.

Read-only diagnosis established that ADC is absent while the existing gcloud user session remains
valid. Passing a token obtained from `gcloud auth print-access-token` only through a temporary
`GOOGLE_OAUTH_ACCESS_TOKEN` child environment allowed `terraform state list` to read all 55 remote
state addresses. The environment variable was removed immediately afterward. This did not run a
plan, alter Terraform state, change credential configuration, write a credential file, or expose
the token in retained output.

TDD then added an opt-in version of that bridge to the one-shot launcher. RED was `2 failed, 8
passed`: the launcher did not accept the bridge flag. GREEN is 10 focused tests at 90.67%
branch-aware coverage. Tests prove one private gcloud token process, exactly one Terraform process,
token presence only in the copied child environment, no token in the JSON report, and no Terraform
invocation when token acquisition fails. The complete database-free suite passes 316 tests with 57
integration tests deselected; Ruff and strict mypy pass over 62 source files. The corrected launcher
SHA-256 is `7671985B74F9018692C64BD055903855CADC465DD0A48EB79F0FA66CCEB9C510` and the authorized
Terraform input remains unchanged at SHA-256
`58C4B76E41D3CDFC5716BC93D5F07CA1ECA5F18E93DAFB6B8D83BB2D5F46F277`.

A fresh replacement authorization is required because the previous authorization allowed one plan
and excluded retries. Another Cloud Build is not required. The next plan invocation can use the
tested ephemeral bridge without changing credentials, then proceed only if the existing
`application-no-migration` reviewer passes the exact saved plan.

## v12 second replacement post-build qualification result — immutable negative evidence

The operator authorized one final post-build continuation against published digest
`sha256:3ec25eef7b5bd5095a681ea496ed2a89f39611959a2ff3129e9b05a09d9653e5` and unchanged Terraform
input SHA-256 `58C4B76E41D3CDFC5716BC93D5F07CA1ECA5F18E93DAFB6B8D83BB2D5F46F277`. The tested bridge used one
existing gcloud user access token only in Terraform's child environment and cleared it afterward;
credential files and configuration did not change.

Exactly one full `application-no-migration` plan was created. Saved-plan SHA-256
`6D7292A19EEBC7DD3BDFDD1F76068A376C4247EC331ABB6AB600A0BBBACE2A2B` passed the fail-closed reviewer:
0 adds, 3 updates, 0 destroys; the only actionable addresses were the development API,
ingestion-job, and evaluation-job image leaves. The migration image remained pinned to v11. One
apply of that exact plan completed with `0 added, 3 changed, 0 destroyed`. API revision
`mtg-rag-dev-api-00023-2q9` became Ready at 100% traffic on v12; ingestion and evaluation moved to
v12 with `maxRetries=0`; migration remained on v11. Migration execution `mmqd5` and ingestion
execution `ld56k` remained unchanged.

Exactly one zero-retry evaluation execution, `mtg-rag-dev-evaluation-h5v65`, completed one task in
9m28.28s. Retained inventory increased exactly from 11 to 12 objects. The new create-only object is
`evaluation-captures/mtg-rules-v1/2026/08/24/9386016f-6557-4384-a101-ec1af9584f53.json`, generation
`1787583506045893`, 176,947 bytes, retained through 2027-08-24, with SHA-256
`80278e0e402d12174c0fff64711673966223868407741968811042f44d3cca1b`. The generation-pinned local
download matched both the server size and SHA-256.

The strict 121-case grader failed closed. Passing gates were recall@8 1.0, citation identifier
validity 1.0, citation excerpt validity 1.0, negative-pair reuse 0, and cached API p95
56.067938 ms. Cache diagnostics now contain one exact hit (`exact=1`, `miss=19`, `ineligible=101`),
so v12 fixed the missing finite cached-latency evidence. Failing gates were required-reference
citation coverage 0.8383838384 (minimum 0.95), behavior accuracy 0.8760330579 (minimum 0.90), and
retrieval p95 548.277258 ms (maximum 500 ms). All 16 citation misses were citation-only: every
required reference was present in the retrieved top eight. Fifteen expected-answer cases instead
abstained. Component p95 was embedding 508.702424 ms, exact 229.527629 ms, lexical 213.210474 ms,
and vector 68.250647 ms, placing the latency miss in embedding/overall retrieval rather than vector
search.

Post-capture reconciliation ran in a read-only transaction. Evaluation users, conversations,
messages, daily-usage rows, ask attempts, and cache rows were all zero. Cards/rules/rulings remained
37,556/3,901/77,314 passages with their pre-capture hashes unchanged. The temporary proxy stopped,
port 5433 closed, and the database URL environment variable cleared. No migration or ingestion
execution, production change, credential change, rollback, or retry occurred. This packet is valid
immutable negative evidence; v12 does not qualify the current development runtime.

## v13 local remediation TDD — changed candidate, external qualification pending

The immutable v12 packet defines two independent regressions. Fifteen expected-answer cases
retrieved every required reference but fell into the final abstention after the single model repair
also produced invalid citations. Separately, retrieval p95 was 548.277258 ms and embedding p95 was
508.702424 ms. Inspection of the pinned SDK showed that its embedding endpoint defaults to compact
base64 transport and decodes vectors transparently, while the application explicitly forced the
larger JSON-float response.

The RED gate added two citation-completion guarantees and changed two embedding transport
expectations: `4 failed, 14 passed`. The minimal citation fix activates only after all of these
conditions hold: the first candidate is an answer; its existing citation IDs and excerpts already
validated; its sole validation defect is omitted `citation_required` IDs; and the one model repair
still fails validation. In that narrow case the service preserves the prevalidated first answer,
adds one normalized exact source excerpt of at most 320 characters for each omitted required
passage, and runs the full validator again. Unknown IDs, unsupported first excerpts, missing all
citations, and other second failures retain the grounded abstention boundary. There is no third
model call. The embedding adapter now omits the explicit `encoding_format="float"`, allowing the
pinned SDK's compact default while retaining model, dimension, batch-order, and vector-length
checks. Focused GREEN is `18 passed`; branch-aware focused coverage is 91.81%.

A separate cache-boundary RED (`1 failed, 3 passed`) proved the changed answer contract still used
`mtg-answer-v12`. The default is now `mtg-answer-v13`; retrieval remains `rrf-v10` because ranking
and stored vector dimensions are unchanged. GREEN is `4 passed`. Final local gates are 318
database-free tests with 57 integration tests deselected, Ruff clean, and strict mypy clean across
62 source files. No Cloud Build, Terraform, migration, ingestion, evaluation execution, credential
change, or remote write occurred. These local tests reproduce and close the identified code paths,
but they do not prove that a new same-region capture will reach 0.95 citation coverage, 0.90 behavior
accuracy, or 500 ms retrieval p95. At that checkpoint, v13 was an unbuilt local candidate awaiting
separate authorization. The create-only 199-file upload manifest is `.tmp/v13-source-manifest-r1.json`,
aggregate SHA-256 `c0aae548693c23b1fc2b76dd32ab556ca28824a045f4d40526dee9ad39137db7`;
an immediate independent `verify` reported `status=match` for the same 199 files and hash.

## v13 development qualification result — immutable negative evidence

The authorized v13 cycle used the exact frozen source manifest above. Cloud Build
`7e2c44df-293a-4b7a-bcc8-945a9a2f36bc` passed all eight gates and published digest
`sha256:a3d2a51a861cb75fc90d458963f48f852ed594dad5589b719c09e4a305fbb0df`. Terraform input SHA-256
`4738CD2CF9C3E00DB3348BEEB37DCBA242520653F51C2542700667CA781B4FFD` produced one full saved plan,
SHA-256 `D6F0224521E945FC47AAD9D63B0ABADF2228BBE6BA90B76F21B7A26643397ABF`.

The first review exposed a qualification-tool defect rather than a plan defect: one `old-image`
parameter represented both the prior application image and the retained migration image, but v13
needed distinct v12 and v11 pins. RED added a split-baseline review contract and failed four focused
tests. GREEN adds `--retained-migration-image`, validates that it is an immutable digest usable only
in `application-no-migration`, and preserves the old fallback for prior callers. The complete
reviewer suite passes 15 tests at 81.23% branch-aware coverage. The unchanged saved plan then passed
with 54 resources, 51 no-ops, exactly three application image-only updates, no changed outputs, the
two existing allowlisted refresh drifts, migration pinned to v11, and zero violations.

One exact apply completed as `0 added, 3 changed, 0 destroyed`. API revision
`mtg-rag-dev-api-00024-kc9` became Ready at 100% traffic on v13; ingestion and evaluation moved to
v13 with `maxRetries=0`; migration remained on v11. Migration execution `mmqd5` and ingestion
execution `ld56k` remained unchanged. Exactly one evaluation execution,
`mtg-rag-dev-evaluation-5p48n`, completed one task in 8m52.42s without retry. Retained inventory
increased exactly from 12 to 13 objects. The sole new object is
`evaluation-captures/mtg-rules-v1/2026/08/24/c1468abb-668b-4dcd-b079-8e4b8c4fdd67.json`, generation
`1787589068740296`, 175,431 bytes, retained through 2027-08-24, with server and downloaded SHA-256
`09ac8674e581bf34637dcf57ef878da58516c4e3409929aa1c9f0ff65fa0703a`.

The strict grade passed recall@8 1.0, citation-ID validity 1.0, citation-excerpt validity 1.0,
negative-pair reuse 0, retrieval p95 273.895557 ms, and cached API p95 44.110189 ms. It failed
required-reference citation coverage at 0.8282828283 and expected-behavior accuracy at
0.8595041322. Cache statuses were one exact hit, 20 misses, and 100 ineligible cases. Reconciliation
found 17 citation-only misses and 17 behavior misses: 16 expected answers and one expected
clarification became final abstentions after citation repair. All required retrieval remained
available; this is a post-generation citation-handling regression, not a retrieval regression.

The post-capture read-only audit found zero users, conversations, messages, daily-usage rows, ask
attempts, and cache entries. Cards/rules/rulings remained 37,556/3,901/77,314 passages with unchanged
hashes. The proxy and temporary credential environments were cleared. No retry, migration or
ingestion execution, production change, rollback, or unrelated Terraform change occurred. v13 is
deployed in development but does not qualify; the retained packet is immutable negative evidence.

## v14 local remediation TDD — canonical citation reconstruction

The v13 packet and retained v10 packet isolate the regression. v10 answered or clarified 16 of the
17 v13 behavior misses with the same retrieved evidence, but v10 predated exact-excerpt validation.
v14 keeps that validation and the one-model-repair limit. If the first answer attempted at least one
citation, an explicit `citation_required` anchor exists, and the model repair still fails, the
service now discards unknown IDs and unsupported claims, keeps at most one already-valid exact
excerpt per known passage, inserts bounded canonical excerpts for missing required passages, and
runs the complete validator again. Answers that never cited evidence, answers without required
anchors, blank output, and any failed reconstructed result still abstain. A failed citation repair
on a clarification preserves the clarification while retaining only valid citations. No third model
call is introduced.

RED was four expected failures with one safety counterexample already passing: two split cases for
unknown IDs and unsupported excerpts, one clarification case, and the `mtg-answer-v14` cache
boundary. GREEN is five focused passes. The expanded generation/citation/adapter/config suite passes
37 tests at 94.53% branch-aware coverage. The complete database-free suite passes 326 tests with 57
integration tests deselected; Ruff and strict mypy across 62 source files pass. The exact-excerpt
validator, 320-character bound, missing-all-citation abstention, no-required-anchor abstention, and
single-repair limit remain regression-tested.

The create-only 199-file v14 source manifest is `.tmp/v14-source-manifest-r1.json`, aggregate
SHA-256 `a93aa3543b5d010840d21d525cf1fc6c2b3f61fcbdfe14b8f4fb10d176588745`. Immediate independent
verification reported the same 199 files, hash, and no diff. Compared with v13, only the generation
service/config, their tests, and the split-baseline Terraform reviewer/tests changed. At this
checkpoint v14 was local only; no build, publication, Terraform action, or evaluation execution had
been authorized or run.

The retained v13 capture stores final answer/repair telemetry but not the private first and repair
structured candidates or their validation categories, and the execution logs contain only case
progress. Therefore no deterministic offline v14 regrade is possible or claimed; a new same-region
capture is the required proof.

## v14 development qualification result — immutable passing evidence

Immediately before submission, the read-only database audit found all six evaluation-residue
counts at zero and matched the retained cards/rules/rulings counts and hashes. The actual gcloud
upload listing independently matched the frozen 199-file manifest and aggregate SHA-256 above.
Exactly one Cloud Build, `c9fbaffb-b43f-46de-8475-c609221ee79f`, passed all eight configured gates.
Its generation-pinned source archive is
`gs://mtg-rules-desk-dev_cloudbuild/source/1787590496.002185-58918e381ea641838236410d839ba475.tgz#1787590496865702`,
SHA-256 `dd45bf267ffd538f7165523359becaa11054c1b4800ba08b2903042c608a6966`.
Cloud Build and an independent Artifact Registry lookup both resolved the publication to immutable
digest `sha256:189f95be9f6e6eec14be7fe87afbd1797eefc0a0093121d75f2a868dfe474400`.

Create-only Terraform input SHA-256
`9E52CF8FA53B3D2D3FA066F57339322153C3BF180407990E1539C7EBE2FB6E6C` produced exactly one full
saved plan, SHA-256 `4F2F650ABF0E22BEAC7ABAC3AB489C466D555CC4512C7A5CAAB1E820E0CFBFD0`.
The fail-closed review passed all 54 resources: 51 no-ops, exactly three update-only development
image leaves, no changed outputs, migration pinned to the immutable v11 digest, only the two known
Artifact Registry/evaluation-execution refresh drifts, and zero violations. One apply of that exact
plan completed `0 added, 3 changed, 0 destroyed`. API revision
`mtg-rag-dev-api-00025-tbt` became Ready at 100% traffic; API, ingestion, and evaluation use v14;
migration remains v11. Migration execution `mmqd5` and ingestion execution `ld56k` did not change.
The existing gcloud user token was passed only to Terraform's child environment and was cleared.

Exactly one zero-retry execution, `mtg-rag-dev-evaluation-tmj5d`, completed one task in 8m58.08s.
Evaluation executions changed exactly 14 to 15 and retained objects exactly 13 to 14. The sole new
create-only object is
`evaluation-captures/mtg-rules-v1/2026/08/24/0290fc03-d88b-4704-8fde-c1798456bc0a.json`, generation
`1787592286883780`, 182,988 bytes, retained through 2027-08-24T17:24:46.888Z. Its metadata and
generation-pinned no-clobber download both have SHA-256
`dfc7bfec96673f73869ce5b9cf4ee1c73263e86c122d2b6e39403a3552794ad2` and contain exactly 121 cases.

The strict grade passes with no failures: recall@8 1.0, citation-ID validity 1.0, exact-excerpt
validity 1.0, required-reference citation coverage 0.9797979798, behavior accuracy 1.0,
negative-pair reuse 0, retrieval p95 291.119934 ms, and cached API p95 45.788348 ms. Cache statuses
are one exact hit, 23 misses, and 97 ineligible cases. Reconciliation found no behavior or retrieval
misses; only `replace-006`/`603.1` and `replace-007`/`603.3` are citation-only misses. Thirty-seven
uncached cases used the bounded reconstruction and 83 did not. Component p95 is embedding
163.482477 ms, exact 242.349023 ms, lexical 192.597522 ms, and vector 58.444229 ms.

The post-capture read-only audit again found zero users, conversations, messages, daily-usage rows,
ask attempts, and cache entries. Cards/rules/rulings remained 37,556/3,901/77,314 passages with
unchanged hashes; the proxy port and database environment were cleared. No production action,
migration or ingestion execution, credential/configuration change, unrelated Terraform change,
rollback, or retry occurred. This passing packet qualifies the v14 exact-excerpt contract in the
development environment; it does not constitute production qualification or qualified legal/source-use review.
