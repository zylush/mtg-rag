# P0 Version Documentation

## What this document explains

This is the plain-language history of the P0 conversation-context and retrieval remediation. For
each version it explains:

1. what problem was found;
2. what changed to address it; and
3. what the resulting evidence proved or failed to prove.

The important distinction is that `mtg-rules-v1` is the versioned **121-case evaluation suite and
capture namespace**. It is not an application release called v1. The application contract history
starts with `mtg-answer-v2`/`rrf-v2`, and the retained development candidates are summarized as
v5 through v10.

## Executive summary

The project improved through repeated RED/GREEN cycles. A RED result means a test or qualification
exposed a real problem. A GREEN result means the implementation or release gate was corrected and
verified. A passed local test was not treated as proof of a deployed same-region release; each
retained candidate needed its own immutable build, deployment, 121-case capture, cleanup check, and
grade.

`v10` is the first retained development candidate in this history that passes all nine P0 criteria
in one immutable same-region packet. It passed the quality and latency thresholds, but it does not
authorize public production. Production still needs separate policy, infrastructure, and operations
evidence.

## Version at a glance

| Version | Main problem entering the version | What fixed or improved it | Result |
| --- | --- | --- | --- |
| Foundation / pre-v2 | Conversation context was not safely owned, bounded, concurrency-aware, or isolated from shared cache behavior. | Added ownership-scoped bounded context, newest-suffix truncation, stale-tail conflict detection, cache exclusion, no-retry `409` behavior, and multi-turn tests. | Local contract became testable; the first real evaluation then exposed citation persistence and quality failures. |
| v2 | The generator did not distinguish answer, clarify, and abstain reliably; old cached payloads could cross the new output contract; parent/child citation matching was too strict. | Added structured behavior, rotated the prompt cache boundary to `mtg-answer-v2`, corrected parent/child citation semantics, and made abstentions explicit and cache-ineligible. | The old capture regraded more accurately, but recall, citation coverage, behavior, and latency still failed. |
| v3 | Retrieval missed domain evidence, retrieval timing was opaque, card-source selection could omit the paper Oracle card, and citation instructions were too loose. | Added component telemetry, better exact/glossary/rule retrieval, `default_cards` ingestion handling, sparse embedding batching, and stricter governing-citation instructions. | The replacement capture improved safety but still failed recall, citation coverage, and retrieval latency. |
| v4 | Retrieval paths ran serially; a broad 64-term query produced noisy candidates; vector authority scoring prevented a clean HNSW candidate stage; required governing citations were not enforced. | Started exact, GIN lexical, and HNSW vector paths concurrently; bounded lexical/vector candidates; protected exact evidence; added one bounded citation repair; rotated to `mtg-answer-v4`/`rrf-v3`. | Retrieval p95 fell from about 4,173 ms to 1,809 ms, but recall, citation coverage, latency, and expected-answer behavior still failed. |
| v5 | The new bounded retrieval path improved latency, but required evidence was still lost during fusion and context cases still missed citations. | Added a bounded indexed lexical anchor, dynamic exact-pin spillover, current/prior-user term budgeting, explicit required-evidence selection, and all-case behavior grading. | `mwmjq` passed recall, behavior, citation validity, and latency, but citation coverage was only 0.89899. |
| v6 | v5's citation misses remained; protected evidence did not always become the required citation. A first v6 build also stopped on a browser visual timeout. | Added protected top-four anchors, contextual priority projection, explicit rule/card/definition requirements, governing evidence repair, and `mtg-answer-v6`/`rrf-v6`. Browser recovery used one worker, zero retries, and a 60-second test timeout. | Replacement capture `xnbcb` passed recall and most safety gates, but citation coverage was 0.92929 and retrieval p95 was 513.617 ms. |
| v7 | The remaining misses needed governing language rather than brittle rule-ID mappings; the GIN candidate bound was also larger than necessary. | Added rule-ID-free governing-language projections, governing-parent coverage, current-question priority, a 32-row GIN anchor, zero-transport-retry evaluation, and `mtg-answer-v7`/`rrf-v7`. | The final `r7lbf` capture passed recall, behavior, and latency, but citation coverage remained 0.92929 because seven required citations were still missed. |
| v8 | v7's seven citation misses needed more precise selection, especially child-versus-parent rules, procedure branches, and card-linked abilities. | Added one bounded governing winner per domain clause, child-before-parent ordering, both pre-priority branches, contextual linked-ability evidence, and `mtg-answer-v8`/`rrf-v8`. | `sbmjv` improved correctness but still failed citation coverage at 0.90909 and retrieval p95 at 512.004 ms. |
| v9 | Citation correctness was essentially fixed, but exact lookup and lexical startup still made the service just over the 500 ms retrieval limit. | Overlapped embedding-independent exact/card-alias/glossary work with the question embedding, kept HNSW independent, and hardened concurrent failure handling. | `jkb54` passed recall 1.0 and citation coverage 0.98990, but retrieval p95 remained 525.002 ms. |
| v10 | v9 had the right results but missed the strict retrieval-latency gate; speculative concurrent work also needed safe cancellation and draining. | Started exact and GIN lexical retrieval while the one embedding was in flight; started HNSW when embedding became ready; cancelled and drained speculative siblings on failure; retained exact, GIN, HNSW, and RRF as separate paths. | `mrzzf` is the first all-green retained P0 packet. Retrieval p95 is 322.349 ms and cached API p95 is 54.808 ms. |

## Foundation: the original conversation-context contract

Before the numbered retrieval candidates, the project established the conversation safety contract.
The initial RED tests found that the required context module and conflict error did not exist. They
also found two dangerous boundary issues: ownership work could happen before authorization failed,
and oversized messages kept their oldest text instead of the newest suffix.

The foundation fixed those problems by adding:

- bounded, Unicode-safe, newest-suffix conversation rendering;
- ownership-scoped loading before rate limits, embedding, retrieval, or model calls;
- context-bearing turns excluded from shared semantic caches;
- prior assistant text treated as untrusted and excluded from retrieval evidence;
- stale conversation-tail detection mapped to HTTP `409`;
- browser recovery that explains the conflict and does not automatically retry; and
- a capture runner that creates synthetic data, observes the real path, cleans up, and writes only
  create-only retained objects.

The first real capture also found a duplicate-citation persistence bug. Two claims could cite the
same passage, while the database allowed only one citation row per message/passage pair. Stable
deduplication was added during citation validation and again at the commit boundary.

## Early contract versions: v2 through v4

### v2: structured answer behavior and citation semantics

The first major contract change made the model output explicit: `answer`, `clarify`, or `abstain`.
Previously, some supported abstentions were counted as answers merely because they cited evidence
about a product boundary. v2 also rotated the prompt/cache version so old cached payloads could not
cross the new structured-output contract.

The citation checker was corrected to accept a required parent rule when the model cited its valid
one-letter child rule, such as expected `603.3` and observed `603.3b`. The metric was renamed from
citation precision to required-reference citation coverage because expected references are minimum
evidence, not an exclusive list.

The old artifact regraded more honestly after these changes, but it still failed recall, citation
coverage, behavior accuracy, and both latency gates. That was useful evidence: the grader was no
longer hiding behavior failures, but the retrieval path still needed work.

### v3: better corpus inputs, telemetry, and grounded citations

v3 added component-level retrieval timings and corrected several corpus and ingestion assumptions:

- use Scryfall `default_cards` so paper Oracle identities such as Black Lotus are not omitted;
- parse large gzip JSONL snapshots lazily under a bounded size guard;
- ignore only records without an Oracle identity;
- batch sparse changed documents independently from passage staging; and
- require the directly governing Comprehensive Rules passage for material conclusions.

The cache boundary moved to `mtg-answer-v3`/`rrf-v2`. A read-only corpus check confirmed better
glossary and DFC retrieval, but the active development corpus was not silently refreshed. The
following retained capture still failed recall, citation coverage, and retrieval latency, so the
project moved to a broader retrieval-architecture fix.

### v4: parallel retrieval and bounded candidate search

The v3 failure analysis identified four general causes:

1. exact, lexical, and vector retrieval were awaited one after another;
2. the conversation-wide 64-term query produced broad, low-information lexical matches;
3. authority scoring was mixed into a full-corpus vector sort, preventing a clean HNSW nearest-
   neighbor stage; and
4. the generator validated citation IDs but did not reject an answer that omitted governing
   evidence already found by retrieval.

v4 addressed them by making the three retrieval paths independent, limiting lexical terms to a
bounded current-question/prior-user projection, selecting a bounded HNSW candidate set before
authority reranking, protecting exact evidence, and allowing one combined citation-repair attempt.

The first v4 replacement capture reduced retrieval p95 from roughly 4,173 ms to 1,809 ms. It still
failed the strict recall, citation-coverage, retrieval-latency, and expected-answer gates. The
parallel design was directionally correct, but the candidate and citation-selection rules needed
more domain-specific structure.

## Retained development candidates: v5 through v10

### v5: bounded anchors and explicit required evidence

v5 introduced the first mature bounded retrieval shape: a 50-row indexed lexical anchor, a limited
term budget, dynamic exact-pin spillover, and all-case behavior grading. It also made the evaluator
report component timings and repair telemetry instead of only aggregate scores.

The retained `mwmjq` packet demonstrated a substantial improvement:

| Gate | Result |
| --- | ---: |
| Recall@8 | 0.95960 - pass |
| Required-reference citation coverage | 0.89899 - fail |
| Behavior | 0.95868 - pass |
| Retrieval p95 | 489.128 ms - pass |
| Cached API p95 | 46.099 ms - pass |

The remaining issue was not primarily latency. Four cases missed retrieval, ten missed required
citations, and five missed expected behavior. The next fix had to preserve governing evidence
through fusion and make only the right evidence citation-required.

### v6: protected anchors and contextual evidence rules

v6 added protected top-four lexical anchors, recency-aware current/prior-user projection, explicit
requirements for a rule, exact card, or definition glossary citation, and one bounded repair when
required evidence was omitted. It also rotated the contracts to `mtg-answer-v6`/`rrf-v6`.

The first v6 build failed before publication because a 375px Chromium snapshot check exceeded the
visual threshold. This was a test-environment/visual-threshold issue, not a Cloud Run or Terraform
failure. The recovery made the browser test deterministic with one worker, zero retries, and a
60-second test timeout; 105/105 browser cases then passed locally.

The authorized replacement `xnbcb` capture passed recall, behavior, citation-ID validity, cached
latency, cache safety, cleanup, and telemetry. It still failed:

- citation coverage: 0.92929, below 0.95; and
- retrieval p95: 513.617 ms, above 500 ms.

The evidence showed that protected retrieval candidates still did not guarantee the required rule
would be the citation selected by generation.

### v7: governing-language projections and the 32-row GIN bound

v7 stopped relying on case-specific rule IDs. It projected general governing MTG language for the
observed miss families, added bounded governing-parent coverage, favored current-question terms over
the prior-user tail, reduced the GIN anchor from 50 to 32 rows, and rotated to
`mtg-answer-v7`/`rrf-v7`.

There were two build events. The first authorized build failed when Firefox and Mobile Safari
Playwright checks timed out under one-CPU contention; it produced no image or deployment. A
separately authorized retry passed all eight Cloud Build gates and published the image.

The retained `r7lbf` packet passed recall, behavior, citation-ID validity, retrieval p95, cached
latency, negative-pair safety, cleanup, and telemetry. Its single strict failure was citation
coverage at 0.92929. Seven cases still missed required citations, including contextual `702.11`
and `509.1b`. This was complete negative evidence: the retrieval-latency fix worked, but citation
selection was not complete.

### v8: one governing winner per domain branch

v8 addressed the seven v7 citation misses by adding one bounded official governing-rule winner per
domain clause. It also:

- kept directly matched subrules ahead of supplemental parents;
- required both branches of the pre-priority procedure;
- required a contextual card's linked ability rule; and
- rotated the prompt/retrieval boundary to `mtg-answer-v8`/`rrf-v8`.

Local corpus plans were GIN-backed and bounded, but the retained `sbmjv` packet showed that the
changed candidate still needed real same-region proof. It passed recall at 0.95960, behavior at
0.96694, citation validity, cached latency, cache safety, and cleanup. It failed citation coverage
at 0.90909 and retrieval p95 at 512.004 ms.

### v9: correctness closure and retrieval startup overlap

v9 fixed the remaining governing-parent and exact-lookup issues. Exact card aliases, glossary reads,
and related text work could overlap the question embedding, while HNSW remained an independent
retrieval input. The v9 local work also hardened concurrent joins so failures or cancellations do
not leave sibling work running.

The retained `jkb54` packet closed the correctness side:

- recall@8: 1.0;
- citation coverage: 0.98990;
- behavior: 0.96694;
- citation validity: 1.0;
- cached API p95: 47.965 ms; and
- negative-pair reuse: 0.

It still failed the 500 ms retrieval-p95 gate at 525.002 ms. v9 proved the selected evidence was
right; it did not yet prove the full retrieval service was fast enough.

### v10: latency closure and safe concurrent retrieval

v10 made exact lookup independent of the embedding. The service now starts exact and GIN lexical
retrieval while the one question embedding is in flight. HNSW starts as soon as that embedding is
ready. Hybrid, Ask, and evaluator paths share the same behavior, and failures cancel and drain
speculative siblings safely.

This does **not** replace vector search with GIN search. Exact retrieval, GIN lexical retrieval, and
HNSW vector retrieval remain separate inputs that are fused through RRF. The change removes avoidable
startup waiting and bounds the lexical stage; it does not remove semantic retrieval.

The final authorized packet used:

- Build: `4dba8ba5-684f-4dd3-83f3-6ebbf7b5049c`;
- image: `sha256:870b46a23e6406142f89eb04969e2d5b623b4f69d72d6b24c19497764b3ffefc`;
- API revision: `mtg-rag-dev-api-00021-7pf`;
- evaluation generation: 12;
- execution: `mtg-rag-dev-evaluation-mrzzf`; and
- retained object generation: `1787508036393785`.

The exact 121-case result was:

| Gate | Observed | Required | Result |
| --- | ---: | ---: | --- |
| Recall@8 | 1.0 | At least 0.90 | Pass |
| Required-reference citation coverage | 0.97980 | At least 0.95 | Pass |
| Behavior | 0.96694 | At least 0.90 | Pass |
| Citation-ID validity | 1.0 | Exactly 1.0 | Pass |
| Retrieval p95 | 322.349 ms | At most 500 ms | Pass |
| Cached API p95 | 54.808 ms | At most 1,500 ms | Pass |
| Negative-pair reuse | 0 | Exactly 0 | Pass |

The packet still reports its imperfections honestly: citation-only misses are `layers-002` and
`multiface-005`; behavior mismatches are those two plus `clarify-002` and `abstain-008`. They do not
push the aggregate score below the release thresholds.

### v11: deterministic exact-excerpt validation (deployed; qualification failed)

v11 changes the citation `claim` field from model-written supporting prose into evidence copied
from the cited passage. Every substantive answer must include a citation. Each claim is limited to
320 characters, normalized with Unicode NFKC and collapsed whitespace, and accepted only when the
result occurs contiguously in the server-supplied passage with case and punctuation preserved.
Unknown IDs, missing citations, omitted required passages, and unsupported excerpts share the
existing one-repair boundary; a second invalid result becomes a grounded abstention.

The prompt/cache boundary rotates to `mtg-answer-v11`; retrieval remains `rrf-v10`. Focused and
database-free local gates passed, and the r4 Cloud Build later passed the complete temporary
PostgreSQL/pgvector gate. The deterministic check proves that displayed evidence was copied from the
cited passage; it does not by itself prove that the excerpt entails every sentence in the generated
answer.

Because v11 also introduces durable request idempotency table `ask_requests`, its rollout is
migration-first: update only the migration job image, execute `0002` once, then update the API,
ingestion, and evaluation image leaves. The fail-closed Terraform reviewer now enforces those two
phases; routing traffic to v11 before the migration is no longer an accepted deployment sequence.

The first authorization-ready source packet contained 197 files and was frozen at
`65dd9df07fb12849607e3ac2aac0dbf2545ff3e39a36373902b8afb99350cc3b`. Its one authorized Cloud
Build, `a669ac15-5367-48b0-abd6-f2c691ae3a5b`, stopped at the temporary PostgreSQL backend gate:
352 tests passed and one idempotency integration test failed because Python `None` was serialized
as JSON `null` instead of SQL `NULL`. The build published no runtime image, and no Terraform,
migration execution, evaluation, cleanup, or retained-object phase ran.

The database constraint was correct. The model now uses `JSONB(none_as_null=True)`, guarded by a
bind-semantics regression test. The corrected 197-file r4 packet was frozen and reverified at
`9568309a7087cc1abee6da05e14e8c67d3621fe5b3acd03d66c6d8d04b7cac7f`; only the model and its
regression test differed from the failed packet.

The replacement Cloud Build, `5fd9a8ed-d4fd-4b48-911f-fb9414186cfa`, passed all eight gates and
published image `sha256:df0644eb31a4fafccd4e55deeccabd2dfe5dc3d1ca40d29fccde70ca0f6d7b66`.
The reviewed migration-only plan applied first, migration execution
`mtg-rag-dev-migration-mmqd5` succeeded once with zero retries, and the reviewed application plan
then updated only API, ingestion, and evaluation. All four development leaves are Ready on v11;
ingestion was not executed.

The single 121-case run, `mtg-rag-dev-evaluation-nmh8x`, produced one create-only retained object.
It passed recall (1.0), citation-ID validity (1.0), the new citation-excerpt validity gate (1.0),
negative-pair safety (0), and retrieval latency (385.570353 ms p95). It failed required-reference
citation coverage (0.8585858586), behavior accuracy (0.8677685950), and cached API latency evidence
because all 121 cases were uncached. Fourteen cases retrieved every required rule but did not cite
it, and 16 cases produced the wrong answer/clarify/abstain behavior. Cleanup was complete and the
active 118,771-passage corpus was unchanged. This means the exact-excerpt mechanism worked, but v11
as a whole did **not** qualify. The failed immutable packet must not be described as release
approval, and no retry ran under the consumed authorization.

### v12: repair stability, bounded behavior policy, and cache diagnostics (deployed; qualification failed)

v12 uses the immutable v11 failure packet as its regression definition. A citation repair now sees
the prior structured candidate and bounded exact source options for only the cited or failing
passages. It is instructed to preserve a supported answer and behavior while repairing citations,
instead of regenerating the whole response without seeing the prior candidate. The approved
320-character normalized exact-excerpt validator, one-repair limit, and final abstention boundary
are unchanged.

Two narrow post-generation policy guards remove the independent behavior misses: a context-free
unresolved comparison asks which trigger/events should be compared, while a request to locate a
current nearby store or tournament abstains. Conversation-backed comparisons and ordinary
tournament rules questions are regression-tested counterexamples and remain answerable.

New captures retain `cache_status` and confidence for every case, and the grader reports cache
status counts and rejects status/hit disagreement. The semantic threshold stays at 0.98. This is
important because the v11 zero-hit result may be downstream of citation repair: the two identical
normalized questions `glossary-008` and `inject-004` both abstained, leaving no eligible first answer
for an exact-cache hit.

Local evidence is 74 focused tests, 303 database-free tests, 80.28% branch-aware focused coverage,
Ruff, and strict mypy. Regrading the retained v11 object reproduces its original failure exactly.
The default prompt/cache version is now `mtg-answer-v12`, while retrieval remains `rrf-v10`.
The create-only 197-file source manifest is `.tmp/v12-source-manifest-r1.json`, aggregate SHA-256
`bd151f9ce5574473913a4866c6da4dba8202e3e5a32a85dc27509579f728e0ea`. The one authorized build,
`3f15a847-9bab-4bfb-816f-e2a6db4cf107`, passed all eight gates and published digest
`sha256:3ec25eef7b5bd5095a681ea496ed2a89f39611959a2ff3129e9b05a09d9653e5`. The initial Terraform-plan
command was rejected during local argument parsing. A separately authorized one-shot replacement
then reached Terraform but stopped before plan creation because the GCS backend lacked ADC. Neither
attempt deployed anything. A tested ephemeral bridge then supplied the existing gcloud user token
only to Terraform's child process without changing credential configuration. Under the final
authorized continuation, saved-plan SHA-256
`6D7292A19EEBC7DD3BDFDD1F76068A376C4247EC331ABB6AB600A0BBBACE2A2B` passed the exact three-leaf
review and applied once. API, ingestion, and evaluation moved to v12; migration remained on v11.
API revision `mtg-rag-dev-api-00023-2q9` is Ready at 100% traffic.

The one zero-retry run, `mtg-rag-dev-evaluation-h5v65`, created one retained 176,947-byte object at
generation `1787583506045893`, SHA-256
`80278e0e402d12174c0fff64711673966223868407741968811042f44d3cca1b`. It proved that v12 fixed the
cache-evidence issue: one exact cache hit produced a valid 56.067938 ms cached API p95. Recall,
citation ID validity, citation excerpt validity, and negative-pair safety also passed. However,
citation coverage was 0.8383838384, behavior accuracy was 0.8760330579, and retrieval p95 was
548.277258 ms, so all three missed their release gates. All 16 citation misses were citation-only,
15 expected-answer cases abstained, and embedding p95 alone was 508.702424 ms. Cleanup returned all
six evaluation residue counts to zero and preserved the 118,771-passage corpus. v12 is deployed in
development but is not technically qualified; the retained capture is immutable negative evidence
and no retry ran.

### v13: compact embedding transport passed; narrow citation fallback did not

v13 was built once from source manifest
`c0aae548693c23b1fc2b76dd32ab556ca28824a045f4d40526dee9ad39137db7`. Cloud Build
`7e2c44df-293a-4b7a-bcc8-945a9a2f36bc` passed all eight gates and published immutable digest
`sha256:a3d2a51a861cb75fc90d458963f48f852ed594dad5589b719c09e4a305fbb0df`. A reviewer defect initially
blocked rollout because one option represented both the old application image and the retained
migration image. A tested local correction introduced a separate immutable retained-migration pin.
The unchanged plan, SHA-256 `D6F0224521E945FC47AAD9D63B0ABADF2228BBE6BA90B76F21B7A26643397ABF`,
then passed: 51 no-ops and exactly three image-only updates, with migration still v11. One exact
apply completed `0 added, 3 changed, 0 destroyed`; API revision `mtg-rag-dev-api-00024-kc9` is Ready
at 100% traffic on v13.

Exactly one zero-retry capture, `mtg-rag-dev-evaluation-5p48n`, completed in 8m52.42s and created
exactly one retained object. Its generation is `1787589068740296`, size 175,431 bytes, and SHA-256
`09ac8674e581bf34637dcf57ef878da58516c4e3409929aa1c9f0ff65fa0703a`. The compact embedding
transport worked: retrieval p95 improved from v12's 548.277258 ms to 273.895557 ms. Recall remained
1.0; citation IDs and exact excerpts remained 1.0; cached API p95 was 44.110189 ms; negative reuse
was zero.

The narrow citation fallback did not cover the actual model failures. Citation coverage fell to
0.8282828283 and behavior accuracy to 0.8595041322. All 17 citation misses happened after successful
retrieval, and 16 expected answers plus one clarification became final abstentions. The existing
fallback only accepted a first candidate whose citations had already passed exact validation and
whose sole defect was omitted required IDs. The live failures included unknown or unsupported
first-pass citation metadata, so they still reached the final abstention. Cleanup returned all six
evaluation residue counts to zero, corpus identities remained unchanged, and no retry ran. v13 is
deployed in development but is not qualified.

### v14: canonical citation reconstruction (deployed; qualification passed)

v14 keeps the exact-excerpt policy that v11 introduced; it does not restore v10's acceptance of
paraphrased citation claims. After the one model repair fails, an answer may be recovered only if
the first candidate attempted at least one citation and retrieval supplied an explicit
`citation_required` passage. Unknown IDs and unsupported claims are discarded, one already-valid
exact excerpt per known passage is retained, bounded canonical excerpts are inserted for required
passages, and the complete answer is validated again. Answers that never cited evidence, answers
without required anchors, blank answers, and failed reconstructed answers still abstain. A
clarification with invalid citation metadata keeps the clarification but only valid citations. No
third model call is added.

This addresses why v10 looked better without weakening v11's safety improvement: v10 kept the model
answer when the citation ID was useful even if its claim was a paraphrase; v11-v13 rejected that
claim and often discarded the whole answer. v14 keeps the answer only when canonical retrieved
evidence can replace the bad metadata and then pass the same validator.

RED produced four intended failures while the missing-all-citation safety counterexample already
passed. GREEN is five focused tests. The expanded generation/citation/adapter/config suite passes 37
tests at 94.53% branch-aware coverage; the complete database-free suite passes 326 tests with 57
integration tests deselected; Ruff and strict mypy pass. The prompt/cache version is
`mtg-answer-v14`, while retrieval remains `rrf-v10`. The create-only 199-file source manifest is
`.tmp/v14-source-manifest-r1.json`, aggregate SHA-256
`a93aa3543b5d010840d21d525cf1fc6c2b3f61fcbdfe14b8f4fb10d176588745`; immediate verification
matched exactly. Because the v13 retained packet did not store the private first/repair structured
candidates, v14 was not projected by offline regrading. It received a new changed-candidate
same-region qualification instead.

Exactly one Cloud Build, `c9fbaffb-b43f-46de-8475-c609221ee79f`, passed all eight gates and
published immutable digest
`sha256:189f95be9f6e6eec14be7fe87afbd1797eefc0a0093121d75f2a868dfe474400`. Terraform input SHA-256
`9E52CF8FA53B3D2D3FA066F57339322153C3BF180407990E1539C7EBE2FB6E6C` produced one full saved plan,
SHA-256 `4F2F650ABF0E22BEAC7ABAC3AB489C466D555CC4512C7A5CAAB1E820E0CFBFD0`. Its fail-closed review saw
54 resources, 51 no-ops, exactly three application image-only updates, no changed outputs,
migration retained on v11, and zero violations. The exact apply completed `0 added, 3 changed,
0 destroyed`; API revision `mtg-rag-dev-api-00025-tbt` is Ready at 100% traffic, and the API,
ingestion, and evaluation job use v14.

The one zero-retry execution, `mtg-rag-dev-evaluation-tmj5d`, succeeded in 8m58.08s and created the
sole new retained object at generation `1787592286883780`. It is 182,988 bytes, retained through
2027-08-24T17:24:46.888Z, and has matching server/local SHA-256
`dfc7bfec96673f73869ce5b9cf4ee1c73263e86c122d2b6e39403a3552794ad2`. The strict grade passes all
gates: recall 1.0, citation-ID and exact-excerpt validity 1.0, citation coverage 0.9797979798,
behavior accuracy 1.0, retrieval p95 291.119934 ms, cached API p95 45.788348 ms, and negative reuse
zero. There are no behavior or retrieval misses; two citation-only misses remain. Cleanup returned
all six temporary evaluation tables to zero and preserved all 118,771 corpus passages and hashes.
No retry, production action, migration/ingestion execution, credential/configuration change, or
unrelated Terraform change occurred. v14 is the current passing development evidence.

## Cross-cutting defects fixed during the history

These fixes are easy to miss if the versions are read only as retrieval releases:

| Defect | Fix |
| --- | --- |
| Duplicate passage citations violated the database uniqueness boundary. | Stable claim deduplication during validation and defensive deduplication at commit. |
| Whitespace-only model output could be persisted as an empty answer. | Convert it to a deterministic, non-empty, low-confidence abstention before cache, commit, API, or capture. |
| NUL characters from provider output caused PostgreSQL/asyncpg persistence failure. | Strip NULs from answer, citation-claim, and assumption text, then revalidate the structured output. Invalid post-sanitization output maps to the normal `ModelOutputError` path. |
| Old cached answers could cross changed prompt/retrieval contracts. | Rotate prompt and retrieval cache versions at each contract boundary. |
| Evaluation repair behavior could differ from runtime behavior. | Use the same one-repair policy and require initial/repair telemetry in every uncached case. |
| Retrieval quality could be “proven” by a fake zero-vector diagnostic. | Keep fixed-vector and no-model diagnostics explicitly non-release; require real embedding, generation, and same-region evidence. |
| A failed concurrent branch could leave sibling retrieval work running. | Cancel and drain started siblings before re-raising the failure. |
| Build provenance and Terraform review could rely on ignored or hard-coded helpers. | Add generation-pinned source manifests and a checked-in fail-closed reviewer limited to four development image leaves. |

## What is green now, and what is not

### Green in the current v14 development packet

- all nine P0 acceptance criteria;
- 121-case real-embedding and real-generation evaluation;
- retrieval and cached API latency thresholds;
- citation-ID validity, exact-excerpt validity, and semantic-cache negative-pair safety;
- zero evaluation residue after capture;
- complete component and repair telemetry;
- one build, one reviewed three-leaf apply, one capture, and one create-only retained object; and
- unchanged capture-time corpus identity.

### Still outside this P0 development qualification

Public launch remains separately blocked by:

- qualified WotC policy/source-use review and publication of the reviewed public-facing
  Terms/Privacy/attribution/support copy (the local implementation-aligned copy is now complete;
  the public question path no longer requires account or email registration; one authorized
  Hosting-only development deploy has now published the complete Terms, and read-only live QA
  verified Terms, Privacy, About, attribution, support, and preview labeling);
- production-owned project, billing, secrets, DNS, certificates, monitoring, and budget evidence;
- reviewed production deployment evidence; and
- backup/restore, rollback, alert-delivery, DNS/certificate, and Firebase identity-deletion drills.

The r4 build and migration clear PostgreSQL proof of the `/v1/ask` idempotency path. v14 clears the
development engineering blocker that the immutable v11-v13 packets exposed: canonical exact
citations now recover supported answers without over-abstaining, behavior is 1.0, and retrieval p95
is below 500 ms. The positive-cache and exact-excerpt requirements remain regression gates. Failed
v11-v13 captures remain immutable negative evidence and must not be retried or reclassified. The
risk audit still retains durable account deletion, history pagination, ingestion leases,
concurrency/load testing, semantic-cache adversarial cases, and a production-like 121-case run.

## Source records

- [P0 architecture and acceptance history](../docs/architecture/P0-CONVERSATION-CONTEXT-REMEDIATION-PLAN.md)
- [TDD and retained qualification evidence](../docs/testing/conversation-context.tdd.md)
- [Production readiness audit](../docs/operations/PRODUCTION-AUDIT.md)
- [Risk and edge-case audit](../docs/operations/RISK-AND-EDGE-CASE-AUDIT.md)
