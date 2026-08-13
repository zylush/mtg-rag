# Development Integration Postmortem and Lessons

**Environment:** `mtg-rules-desk-dev` in `asia-east1`  
**Web app:** `https://mtg-rules-desk-dev.web.app`  
**Review date:** 2026-08-14  
**Scope:** Development integration, not approval for public production launch

## Outcome

The development application now works end to end:

1. Firebase Hosting serves the installable React PWA.
2. Firebase Authentication signs in a real Google account.
3. The browser obtains a Firebase ID token and calls the same-origin `/v1` API.
4. Firebase Hosting forwards the request to Cloud Run.
5. Cloud Run verifies the token, retrieves active passages from Cloud SQL/pgvector,
   calls OpenAI using a Secret Manager-injected key, validates citations, stores the
   conversation, and returns a typed response.
6. The UI renders the answer, confidence, remaining quota, and source links, and the
   conversation appears in History.

The final live question asked for the Comprehensive Rules glossary definition of
"target" and Lightning Bolt's Oracle text. The response supplied both with high
confidence and cited:

- `Comprehensive Rules Glossary: Target`; and
- `Oracle text: Lightning Bolt`.

Cloud Run revision `mtg-rag-dev-api-00008-589` serves image `api:ba9165e` at 100%
traffic. Cloud Build `78760892-d133-4e12-a112-421622e349ed` passed and published
digest `sha256:10c832b045361995d66a136cdc5643555f03eec3f4e25d3808167dd8abe66c31`.
Terraform reports no drift after aligning the API, migration job, and ingestion job
to that image.

## Glaring issues and what they taught us

### 1. The browser hid useful request failures

**Symptom:** Several different failures appeared as a generic unsuccessful request.

**Root cause:** The client treated authentication, network, quota, and backend
availability failures too similarly.

**Fix:** The API client now maps safe status classes to typed client errors and the UI
shows actionable, non-sensitive messages. Provider details and credentials remain hidden.

**Prevention:** Test failure behavior at both the API-client and rendered-UI layers.
An error path is part of the product contract, not an afterthought.

**Lesson:** Good observability includes what the user can safely act on. Generic errors
are secure only if they do not make diagnosis impossible.

### 2. Firebase token verification needed one more IAM permission

**Symptom:** Signed-in API requests failed even though token verification was configured.

**Root cause:** Revocation-aware verification reads the Firebase user record, but the API
service account initially lacked `firebaseauth.users.get`.

**Fix:** A narrow custom role now includes only the Firebase user read/delete permissions
needed by token revocation checks and account deletion.

**Prevention:** Derive IAM from runtime SDK behavior, then prove it with a real identity
flow. Avoid replacing revocation checks with a weaker verification mode just to make IAM
simpler.

**Lesson:** "Can verify a signature" and "can perform the configured authentication
policy" are different capabilities.

### 3. A nullable Terraform budget value broke validation

**Symptom:** The dev plan failed while evaluating an optional budget condition.

**Root cause:** Terraform boolean validation still evaluated a nullable expression in a
way that was unsafe for `null`.

**Fix:** The validation uses a null-safe expression with `try` and has a regression test.

**Prevention:** Test optional variables with omitted, null, valid, and invalid values.

**Lesson:** Infrastructure languages have evaluation rules of their own; familiar-looking
boolean expressions are not automatically null-safe.

### 4. An inactive source snapshot was mistaken for current data

**Symptom:** Re-ingestion saw the same SHA-256 and reported the corpus unchanged even when
the matching version was inactive or failed.

**Root cause:** Content identity and activation state were conflated.

**Fix:** SHA lookup reuses only an active healthy version. A matching inactive, staged, or
failed version is cleared and safely restaged before atomic activation.

**Prevention:** Model version state explicitly and test recovery from every non-active
state, not only first ingestion and happy-path idempotency.

**Lesson:** "We have seen these bytes" does not mean "these bytes are currently serving."

### 5. The rulings feed contained canonical duplicates

**Symptom:** Duplicate ruling rows could reach staging and collide or waste embeddings.

**Root cause:** Feed records were treated as unique transport objects rather than one
canonical ruling identity.

**Fix:** Rulings are deduplicated deterministically by Oracle identity, publication date,
and comment; an identical WotC-attributed ruling wins over secondary editorial attribution.

**Prevention:** Define corpus identity before defining database uniqueness, and make source
precedence executable rather than leaving it only in documentation.

**Lesson:** Versioned RAG ingestion is data engineering. Normalization and provenance are
as important as embeddings.

### 6. Filtered cards left unsupported rulings behind

**Symptom:** Rulings could refer to Oracle IDs excluded by the active English/non-digital
card policy, causing relationship validation failures after expensive embedding work.

**Root cause:** Card eligibility was applied to the card corpus but not early enough to the
rulings corpus.

**Fix:** The pipeline filters ruling documents to active eligible Oracle IDs before
embedding and staging, while retaining the database integrity check as a second guard.

**Prevention:** Apply referential filters before expensive transformations and keep a
separate persistence boundary check.

**Lesson:** Validate cheap invariants early and critical invariants again at commit time.

### 7. Automatic Cloud Run job retries repeated expensive ingestion

**Symptom:** A failed ingestion attempt was automatically repeated, consuming time and
potential OpenAI embedding cost while obscuring which attempt produced which logs.

**Root cause:** A generic retry default was inappropriate for a long, externally billed,
stateful batch operation.

**Fix:** Ingestion has `max_retries = 0`; operators retry deliberately after inspecting the
failed run. The pipeline itself remains resumable and idempotent.

**Prevention:** Choose retry policy per operation. Retry small transient calls internally;
do not blindly replay an entire expensive job.

**Lesson:** Idempotency makes retries safe for data, but not necessarily cheap or easy to
observe.

### 8. A local Terraform plan entered the Cloud Build upload

**Symptom:** A generated `.tfplan` file was included in the source archive and disrupted a
build.

**Root cause:** Local generated artifacts were ignored by habit, not by an enforced upload
manifest rule.

**Fix:** `.tmp/` is excluded from Git and `cloudbuild.ignore`, with a regression test for
the actual upload policy. The exact temporary plan is removed after apply.

**Prevention:** Treat the build context as a security and reproducibility boundary. Test
what is uploaded, not only what Git tracks.

**Lesson:** "Untracked" does not mean "cannot be shipped." Every packaging tool has its own
inclusion rules.

### 9. The production browser bundle called `localhost`

**Symptom:** The deployed UI said the rules desk was unreachable, and Cloud Run logged no
corresponding request.

**Root cause:** Vite loaded a local `VITE_API_BASE_URL=http://localhost:8080` during the
production build. Unit tests exercised a fake API and never inspected the emitted bundle.

**Fix:** Production always resolves the API base to `window.location.origin`; development
alone may use the explicit local override. The final PWA check rejects a generated bundle
containing the configured development endpoint.

**Prevention:** Validate the deployable artifact and the live network boundary. Environment
configuration deserves tests at compile time and runtime.

**Lesson:** Source code can be correct while the compiled artifact is wrong.

### 10. A response existed, but it was not yet a complete expert answer

**Symptom:** The first live answer correctly stated Lightning Bolt's Oracle text but
abstained from identifying the Comprehensive Rules definition of "target."

**Root cause:** Exact retrieval recognized rule numbers and card aliases, but not glossary
terms. Semantic/lexical fusion did not rank the `target` glossary passage into the final
eight passages for that mixed question.

**Fix:** Active glossary canonical keys mentioned as whole phrases now participate in
deterministic exact retrieval. The live retest returned both requested facts and both
citations.

**Prevention:** Evals must assert expected reference keys and answer completeness, not only
that the model returned valid JSON or some citation.

**Lesson:** Availability is not expertise. The best integration test asks a multi-source
question that can expose retrieval omissions.

### 11. Local Cloud Build submissions had no automatic short SHA

**Symptom:** `gcloud builds submit` produced an invalid image name ending in a blank tag.

**Root cause:** Triggered builds populate `$SHORT_SHA`; a local source submission does not
guarantee that substitution.

**Fix:** The submission supplied `SHORT_SHA=ba9165e` explicitly, producing an immutable,
traceable artifact tag.

**Prevention:** Make required provenance substitutions explicit in manual release commands
or wrap the command in a checked release script.

**Lesson:** CI trigger context and an operator's local CLI context are not interchangeable.

### 12. A plausible Firebase health rewrite still failed live

**Symptom:** Several syntactically valid `/healthz` rewrite patterns passed manifest tests
but the Firebase edge returned 404 for the exact path; a slash form forwarded and then
redirected to an internal service URL.

**Root cause:** The configuration-shape test proved only that a rule existed, not that the
deployed edge and application path semantics agreed. Attempts based on glob and RE2 matcher
hypotheses were contradicted by live behavior.

**Final decision:** Remove the misleading public health rewrite. Cloud Run continues to use
`/healthz` for native startup/liveness probes. The supported edge smoke test is
`/v1/conversations` without credentials, which must return the backend JSON `401` rather
than the SPA shell.

**Prevention:** Pair manifest tests with deployed endpoint tests, and remove failed
hypotheses rather than leaving configuration that merely looks correct.

**Lesson:** A green configuration test is weak evidence for managed-edge behavior. Runtime
observation wins.

## Verification evidence

- Cloud Build: `SUCCESS`, build `78760892-d133-4e12-a112-421622e349ed`.
- Backend: 136 tests in the release build, branch coverage above 80%, Ruff and strict mypy
  clean, and `pip-audit` reported no known vulnerable dependencies.
- Frontend: lint, coverage, production/PWA artifact checks, and 13 Chromium E2E tests passed.
- Security: repository secret scan, non-root image check, credential-like environment
  inspection, and blocking HIGH/CRITICAL Trivy scan passed.
- Corpus: WotC Comprehensive Rules, Scryfall Oracle cards, and filtered/deduplicated rulings
  are three independently versioned active sources.
- Secret boundary: `MTG_RAG_OPENAI_API_KEY` is a Cloud Run `secretKeyRef`; the key was never
  printed, placed in Firebase configuration, or embedded in browser/container artifacts.
- Edge: `/v1/conversations` through Firebase Hosting returns the backend JSON `401` when
  unsigned, proving forwarding and authentication enforcement.
- Live authenticated flow: real Google sign-in, generated answer, validated WotC/Scryfall
  citations, quota, History persistence, and deletion confirmation interaction observed.
- Terraform: final plan reports no changes; no temporary saved plan remains.

## What remains before public launch

Development integration is complete, but public launch still needs the separately documented
external gates: qualified WotC policy/legal review, final Terms/Privacy/support copy,
independent MTG rules-expert approval and execution of the gold evaluation suite, and
production-specific budget, alert-delivery, backup/restore, rollback, and account-deletion
drills.
