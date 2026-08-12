# MTG Rules Desk

MTG Rules Desk is an English-only, citation-first rules expert for Magic: The Gathering.
It is a traditional RAG system: a React PWA calls an authenticated FastAPI service, which
retrieves from versioned WotC rules and Scryfall card/ruling corpora before using the
OpenAI Responses API. The browser never calls OpenAI.

The implementation includes local development, database migrations, idempotent ingestion,
hybrid retrieval, citation repair and abstention, version-aware semantic caching, Firebase
authentication, quotas, history/deletion, an installable PWA, Terraform for Google Cloud,
Cloud Build quality gates, and a versioned 110-case RAG evaluation suite.

## Repository map

- `backend/app` - API, ingestion, retrieval, generation, caching, and persistence.
- `backend/migrations` - PostgreSQL/pgvector schema migration.
- `backend/evals` - versioned evaluation suite and release-gate input format.
- `frontend` - React PWA and browser acceptance tests.
- `infra` - Google Cloud dev/prod Terraform.
- `cloudbuild.yaml` - CI and versioned container delivery.
- `docs/OPERATIONS.md` - bootstrap, deploy, rollback, and recovery runbook.
- `docs/SECURITY.md` - trust boundaries and security verification.
- `docs/ATTRIBUTION-AND-LAUNCH.md` - policy evidence and launch blockers.
- `docs/PRODUCTION-AUDIT.md` - evidence-backed ship/block recommendation.

## Local development

Prerequisites are Docker, Python 3.12, and Node.js 24.

1. Copy `.env.example` to `.env` and fill only the values needed for the task.
2. Start PostgreSQL: `docker compose up -d db`.
3. Install the backend:
   `python -m venv .venv`, then `.venv/Scripts/pip install -e "backend[dev]"`.
4. From `backend`, run `alembic upgrade head` and then
   `uvicorn app.main:app --reload --port 8080`.
5. Copy `frontend/.env.example` to `frontend/.env.local`, configure Firebase and the
   local API URL, then run `npm ci` and `npm run dev` from `frontend`.

The full containerized API can instead be started with `docker compose up --build api`.
The ingestion job is opt-in: `docker compose --profile jobs run --rm ingestion`.

## Verification

Backend, from `backend`:

```text
ruff check app tests
mypy app
pip-audit
pytest --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=80
```

Frontend, from `frontend`:

```text
npm audit --audit-level=high
npm run lint
npm run test:coverage
npm run check:pwa
npm run e2e
```

Infrastructure:

```text
terraform -chdir=infra fmt -check -recursive
terraform -chdir=infra init -backend=false
terraform -chdir=infra validate
```

The Cloud Build pipeline runs these gates, secret scanning, non-root image inspection, and
a pinned Trivy HIGH/CRITICAL image scan before publishing a commit-tagged Artifact Registry
image.

## Evaluation

The checked-in suite is structurally complete but intentionally marked `pending` for
independent MTG rules-expert review. Grade a staging result:

```text
mtg-rag-eval --suite evals/mtg_rules_v1.json --run path/to/staging-run.json
```

The command fails unless all release thresholds pass and the suite review is approved.
`--allow-pending-review` exists only for harness development and cannot establish launch
readiness. See `backend/evals/README.md`.

## Public-release status

No cloud resources are created by this repository alone, and no deployment was performed
during implementation. Production launch requires operator-supplied Google Cloud, Firebase,
OpenAI, billing, DNS, monitoring, and legal-review decisions. In particular, the current
WotC Fan Content Policy creates a potential conflict with mandatory sign-in and requires a
human go/no-go decision before public access. See `docs/ATTRIBUTION-AND-LAUNCH.md`.
