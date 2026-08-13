# Production readiness audit

**Audit date:** 2026-08-12
**Recommendation:** 68/100, blocked for public launch by external review and
production-like evidence, not by a known failing code gate.

## Blockers

1. Resolve the mandatory-sign-in conflict identified in
   `ATTRIBUTION-AND-LAUNCH.md` through a qualified WotC policy/legal decision,
   written permission, or a product change.
2. Have an independent MTG rules expert approve the 110-case suite, then run it
   against a production-like staging corpus and record all accuracy and latency
   gates.
3. Supply operator-owned projects, secrets, DNS, billing budget, monitoring
   channel, privacy/terms/support copy, and execute the documented bootstrap,
   migration, ingestion, backup-restore, and rollback drills.

## High-value follow-up

- Replace the initial metadata-driven Alembic revision with a frozen explicit
  schema revision before the first later schema change. It is deterministic for
  this first empty-workspace deployment, but importing current ORM metadata is
  unsafe once the model evolves.
- Add a dependency-readiness endpoint if operators later need load-balancer
  gating on database/corpus availability. The current `/healthz` is deliberately
  the minimal process health endpoint specified in the plan.
- Run the repository Cloud Build in the target project and preserve its build
  provenance and Artifact Registry digest; local verification cannot prove
  project IAM, quota, DNS, certificate, or provider state.

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

No cloud deployment or third-party mutation was authorized or performed. The
audit therefore has no real Google Cloud/Firebase IAM plan, Cloud Build run,
managed-certificate/DNS check, production alert delivery, production backup
restore, Firebase identity deletion, staging OpenAI/corpus evaluation, or
independent legal/rules approvals. These omissions cap readiness regardless of
local test quality.

## Development deployment addendum ? 2026-08-13

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
  `401`, and the Hosting-to-Cloud-Run route preserves the authentication boundary.

These results remove the original ?no cloud evidence? limitation for development. They do
not change the public-launch recommendation. Remaining launch evidence includes a qualified
WotC policy/legal decision, final legal copy, independent expert approval and execution of
the RAG evaluation suite, a real signed-in browser acceptance run, and production-specific
DNS, budget, alert-delivery, backup/restore, rollback, and identity-deletion drills.
