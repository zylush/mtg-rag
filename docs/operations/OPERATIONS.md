# Operations runbook

This runbook separates reproducible infrastructure from operator-owned credentials,
DNS, billing, and release approvals. Run commands from the repository root unless a
different directory is shown.

## Prerequisites and ownership

Use Google Cloud and Firebase projects owned by the operator. Required local tools are
Google Cloud CLI, Terraform 1.10 or newer, Docker, Python 3.12, and Node.js 24. The
operator must provide:

- a billing account and monthly budget for production;
- an HTTPS API hostname and exact Firebase Hosting origin;
- OpenAI and Firebase configuration;
- at least one notification channel for production alerts;
- DNS control and named security, operations, legal, and MTG rules reviewers.

Never put secret values in Terraform variables, tfvars, Cloud Build substitutions,
source control, shell history, or container images. Terraform creates Secret Manager
containers only. Add versions through the Cloud Console or a protected standard-input
workflow.

## Bootstrap

1. Create a dedicated, versioned GCS bucket for Terraform state. Restrict it to the
   deployment identity, enable public-access prevention, and document its recovery
   owners. This one-time resource is deliberately outside this Terraform state.
2. Copy `infra/environments/dev.tfvars.example` or
   `infra/environments/prod.tfvars.example` to an ignored `.tfvars` file and replace
   every placeholder. Production validation requires billing and alert-channel IDs.
3. Initialize remote state:

   ```text
   terraform -chdir=infra init -backend-config="bucket=STATE_BUCKET" -backend-config="prefix=mtg-rag/ENV"
   ```

4. Review `terraform -chdir=infra plan -var-file=PATH`. The first apply has a bootstrap
   dependency: Cloud Run needs an existing image and secret versions. Apply the APIs,
   Artifact Registry, service accounts, Cloud SQL, database, bucket, and secret
   containers first using reviewed resource targets. Do not use targeted apply for
   normal updates.
5. Set the PostgreSQL user password through a protected prompt, construct the Unix-socket
   SQLAlchemy URL, and add `database-url` and `openai-api-key` secret versions.
   Record their numeric Secret Manager version IDs in the production `.tfvars` as
   `database_url_secret_version` and `openai_secret_version`; production deliberately
   rejects `latest`. The Firebase project ID is configured by Terraform and is not a
   secret. Do not create Terraform-managed secret versions because that stores plaintext
   in state.
6. Submit `cloudbuild.yaml` with a frozen source manifest, confirm every quality and scan step
   passes, and record the immutable Artifact Registry digest.
7. For a release with no schema migration, put that digest in `api_image`, run and approve the
   complete plan, and apply it. For a schema-changing release, use the migration-first sequence
   below; never update the API before its required migration succeeds. Point the API DNS A record at the
   `api_ip_address` output and wait for the managed certificate to become active.

Terraform has separate service accounts for the API, ingestion job, and scheduler. The
API has load-balancer-only ingress; Cloud Armor allows Taiwan, Japan, South Korea, and
Singapore and denies other regions.

## Bounded conversation-context rollout

The `conversation_context_enabled` Terraform variable and
`MTG_RAG_CONVERSATION_CONTEXT_ENABLED` container setting default to `false`. The two bounds
default to six prior messages and 6,000 serialized characters. This change has no database
migration.

Enable the flag in development first, then staging. Before production, run the versioned
multi-turn evaluation and PostgreSQL concurrency tests with synthetic users. Compare model input
tokens and latency with the standalone baseline, inspect `context_message_count` and
`context_truncated` logs, and confirm contextual responses report `cache_status=ineligible`.
Conversation content and content-derived hashes must not appear in logs.

If latency, token growth, clarification accuracy, ownership behavior, or stale-tail conflicts
regress, set the flag back to `false` and deploy the configuration change. This rollback restores
the prior standalone behavior and requires neither a schema rollback nor data cleanup. Keep the P0
risk open until the expert-reviewed staging gate passes.

## Database and corpus activation

### Migration-first image rollout

`migration_image` defaults to `api_image`, but a schema-changing release must be split into two
complete, non-targeted plans:

1. Keep `api_image` on the currently deployed digest and set `migration_image` to the new digest.
   Review the saved plan with `terraform_plan_review.py --phase migration`; exactly the migration
   job image may change. Apply it, execute the migration job once with zero retries, and stop if it
   fails.
2. After the migration succeeds, set both `api_image` and `migration_image` to the new digest.
   Review with `--phase application`; exactly the API, ingestion job, and evaluation job image
   leaves may change. Apply it, then run the release evaluation.

Both reviews require a complete plan, immutable old/new digests, the exact development project and
region, passing Terraform checks, unchanged outputs, and only allowlisted provider drift. Do not use
`-target`. A failed migration leaves the old API serving traffic; do not proceed to phase two.

After infrastructure is healthy, execute and wait for the one-shot migration job:

```text
gcloud run jobs execute mtg-rag-ENV-migration --region asia-east1 --wait
```

Then execute ingestion:

```text
gcloud run jobs execute mtg-rag-ENV-ingestion --region asia-east1 --wait
```

Ingestion downloads authoritative sources, validates staged records, writes versioned
snapshots, and atomically activates successful source versions. A failed run leaves the
previous active corpus available. Confirm the job-success metric, source version rows,
and a small citation smoke test before declaring the corpus current.

The scheduler runs daily at 18:00 UTC. Manual execution is the supported recovery path
after a transient upstream or provider failure.

## Frontend and release

Copy `.firebaserc.example` to the ignored `.firebaserc`, set the project alias, and
provide `frontend/.env.production.local` outside source control. Build with
`npm run build`; deploy Firebase Hosting only after the API certificate, CORS origin,
authentication configuration, eval gate, and launch approvals are all verified.

To configure Google sign-in without committing an operator email, copy
`firebase.auth.json.example` to the ignored `firebase.auth.local.json`, replace the
support-email placeholder with the public OAuth support contact, and run
`firebase deploy --only auth --config firebase.auth.local.json --project PROJECT_ID`.
Delete the local auth file after deployment. Keep `firebase.json` as the Hosting
configuration and deploy it separately with `firebase deploy --only hosting`.

`firebase.json` applies security headers, immutable caching to fingerprinted assets,
and no-store handling to the service worker. Verify installation and an authenticated
question flow from a clean browser profile after deployment.

### Firebase Google OAuth callback and sign-in loop prevention

For a deployment served from `PROJECT_ID.web.app`, Firebase Authentication must use
that same `web.app` hostname as its effective `authDomain`. The browser configuration
resolver enforces this for the matching Firebase project. Three separate controls must
agree; one does not substitute for another:

1. Firebase Authentication **Authorized domains** must contain both
   `PROJECT_ID.web.app` and `PROJECT_ID.firebaseapp.com`.
2. The exact Google OAuth web client selected under the Firebase Google provider must
   contain both callbacks under **Authorized redirect URIs**:

   ```text
   https://PROJECT_ID.web.app/__/auth/handler
   https://PROJECT_ID.firebaseapp.com/__/auth/handler
   ```

   Match the scheme, hostname, path, and absence of a trailing slash exactly. Do not add
   wildcards, rotate the client secret, or create a replacement client to repair a missing
   callback.
3. The PWA navigation fallback must deny every `/__/` path so the service worker cannot
   replace Firebase's OAuth handler or iframe with `index.html`. `npm run check:pwa`
   verifies the generated service worker contains this exclusion.

Before a release, and whenever Google reports `redirect_uri_mismatch`:

1. Confirm the Google provider is enabled and `PROJECT_ID.web.app` is an authorized
   Firebase Authentication domain.
2. Confirm the Firebase provider's Web SDK client ID is the same Google OAuth client being
   inspected. Client IDs are identifiers; never copy the client secret into logs or docs.
3. Confirm the deployed page and effective `authDomain` are the same `web.app` origin and
   that the exact `web.app/__/auth/handler` callback is present on that OAuth client.
4. Request `/__/auth/handler` directly and confirm Firebase Hosting serves the reserved
   helper rather than the SPA shell.
5. Rebuild with `npm run check:pwa`, deploy Hosting, close stale sign-in popups, and
   reload the original tab so the new service worker controls it.
6. Reproduce from a clean supported browser profile. Record the Firebase error code,
   browser/version, deployed commit, and whether popup blocking or storage protection
   is enabled; never record ID tokens or account cookies.

Google notes that OAuth client changes can take from several minutes to several hours to
propagate. During that window, verify the saved URI in the console before retrying; do not
repeat unrelated Hosting deploys or secret rotations.

`/healthz` is reserved for Cloud Run startup and liveness probes and is not exposed by
Firebase Hosting. For an edge-to-service smoke check, request `/v1/conversations`
without credentials and expect the API's JSON `401` response rather than the SPA shell.
The free public question path is `/v1/public/ask`; it deliberately accepts no bearer token,
does not create account history, and must be covered by the production distributed rate limit.

## Rollback

Application images are immutable. To roll back after a forward-compatible migration, keep
`migration_image` on the newest migration-capable digest, change `api_image` to a known-good digest,
review the application-phase Terraform plan, and apply. Do not downgrade the schema merely to roll
back application code, and do not retag or overwrite the failed image. Validate health,
authentication, one cached and one uncached query, citations, and error rate after traffic reaches
the restored revision.

Corpus activation is independent from application rollback. From a protected operator
environment with Cloud SQL connectivity and the production configuration loaded:

```text
mtg-rag-rollback-corpus comprehensive_rules PREVIOUS_VERSION_ID
mtg-rag-rollback-corpus oracle_cards PREVIOUS_VERSION_ID
mtg-rag-rollback-corpus rulings PREVIOUS_VERSION_ID
```

The command verifies that the requested version exists for that source and atomically
reactivates it. Record the incident, previous and restored version IDs, operator, and
validation evidence. Never edit active flags manually.

Firebase Hosting retains deployment history. Use the Firebase Console or CLI rollback
facility to restore the prior release, then repeat the clean-profile install and
authenticated-flow smoke tests.

## Recovery drills

At least quarterly:

1. restore the most recent Cloud SQL backup into an isolated development instance;
2. run migrations, row-count and foreign-key checks, then a representative rules query;
3. retrieve a prior GCS source snapshot and verify its generation and checksum metadata;
4. execute an application and corpus rollback in development;
5. verify that an ingestion failure and sustained API 5xx condition reach the named
   notification channel.

Document recovery-point and recovery-time results. A backup that has not been restored
successfully is not accepted release evidence.

## Monitoring and incident response

Cloud Monitoring alerts on ingestion failures and sustained API 5xx responses. The API
logs request IDs, normalized error classes, latency, cache decisions, and content-free
answer metadata; it does not log bearer tokens, questions, answers, retrieved passages,
or secret values.

For an incident:

1. preserve request IDs, deployment digest, source-version IDs, timestamps, and relevant
   content-free logs;
2. revoke or rotate only the affected credentials;
3. roll back the application or corpus using the procedures above;
4. verify regional access, authentication, quota enforcement, and deletion behavior;
5. record root cause, impact, recovery evidence, and follow-up controls.

## Release checklist

A production release is blocked unless all of the following are recorded:

- backend, frontend, browser, Terraform, audit, secret, and image-scan gates pass;
- the migration and ingestion jobs succeed against production-like staging;
- the 121-case evaluation passes and its independent expert review is approved;
- the public-access product decision and source attribution in
  `docs/operations/ATTRIBUTION-AND-LAUNCH.md` are implemented, and qualified WotC/Scryfall
  policy/source-use review is recorded;
- privacy copy, terms, support contact, deletion flow, billing budget, and alert channel
  have named owners;
- DNS, certificate, Firebase authorized domains, CORS, Cloud Armor geography, and
  OpenAI supported-country assumptions are rechecked;
- rollback and backup-restore evidence is current.
