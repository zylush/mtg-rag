# Authenticated ask idempotency TDD evidence

**Date:** 2026-08-24
**Status:** Local SQL-NULL mapping remediation green; replacement live PostgreSQL qualification pending
**Source:** User-directed remediation of the `/v1/ask` public development-preview blocker

## User journeys

- As an authenticated user whose response is lost in transit, I can retry the unchanged
  submission without creating another exchange or consuming successful-answer quota again.
- As an authenticated user with a request already running, a concurrent duplicate cannot start
  cache, retrieval, model, history, or quota work again.
- As an API caller, I cannot reuse a request UUID for a different question or conversation.
- As a browser user retrying an unchanged failed submission, the client reuses the original UUID;
  editing the request creates a new identity.

## RED evidence

The focused backend RED command executed the new service, schema, and API requirements before
production changes. It failed five intended assertions:

```text
..\.venv\Scripts\pytest.exe \
  tests\unit\test_ask_service.py::test_completed_request_replays_before_rate_limit_cache_or_model_work \
  tests\unit\test_ask_service.py::test_new_request_claim_is_completed_with_the_same_key_and_fingerprint \
  tests\unit\test_ask_service.py::test_failed_request_releases_its_claim_for_a_safe_retry \
  tests\unit\test_database_metadata.py::test_ask_request_keys_are_unique_per_user_and_cascade_with_account_deletion \
  tests\integration\test_api_contract.py::test_authenticated_ask_requires_a_client_request_id
```

Observed failures were the missing `request_id` service argument, absent `ask_requests` table,
and API acceptance of a request without the required UUID. The focused frontend RED test failed
because the authenticated request body contained the question but no `request_id`.

## GREEN evidence

| Guarantee | Evidence | Result |
| --- | --- | --- |
| Completed matches replay before rate-limit, cache, retrieval, or model work | `test_completed_request_replays_before_rate_limit_cache_or_model_work` | PASS |
| New claims carry the same UUID and content fingerprint into atomic commit | `test_new_request_claim_is_completed_with_the_same_key_and_fingerprint` | PASS |
| Failed work releases only its owned claim | `test_failed_request_releases_its_claim_for_a_safe_retry` | PASS |
| API requires and forwards a UUID | `test_authenticated_ask_requires_a_client_request_id` and authenticated contract test | PASS |
| Schema has per-user uniqueness and account-deletion cascade | `test_ask_request_keys_are_unique_per_user_and_cascade_with_account_deletion` | PASS |
| An in-progress response maps Python `None` to SQL `NULL`, not JSON `null` | `test_in_progress_ask_request_response_none_binds_as_sql_null` | PASS |
| Browser sends and reuses the UUID for an unchanged retry | `api-client.test.ts` and `App.test.tsx` | PASS |
| In-progress and mismatched-key conflicts are distinct and content-free | backend boundary and frontend error-mapping tests | PASS |
| Migration is chained after `0001` and handles fresh dynamic-metadata bootstrap | `test_idempotency_revision_is_chained_and_safe_for_fresh_bootstrap` | PASS |
| Upgrade SQL uses the same canonical constraint/index names as ORM metadata | `test_upgrade_sql_matches_canonical_ask_request_metadata_names` | PASS |
| The complete `0001 -> 0002` chain compiles in offline PostgreSQL mode | `python -m alembic upgrade head --sql` | PASS |
| An existing `0001` PostgreSQL schema can create and inspect `ask_requests` transactionally | `test_existing_0001_database_can_apply_idempotency_migration` | PREPARED; live runtime required |

Executed aggregate checks:

- Backend unit plus API contract: `283 passed`.
- Backend strict mypy: success across 59 source files.
- Backend Ruff: clean.
- Frontend full unit suite: `65 passed` across 12 files; the focused API-client suite passed `11`
  tests.
- Frontend coverage: 91.35% statements, 89.65% branches, 89.23% functions, and 93.8% lines.
- Frontend production build and ESLint: pass.
- `git diff --check`: pass; only existing line-ending conversion warnings were emitted.

## PostgreSQL evidence still required

`test_answer_request_idempotency_excludes_duplicates_and_replays_one_commit` and
`test_existing_0001_database_can_apply_idempotency_migration` are implemented. The first
checks live duplicate exclusion, mismatched-hash rejection, claim release/reacquisition, atomic
response retention, exactly two messages, and exactly one quota increment. Its first execution
could not reach `localhost:5432` because no PostgreSQL listener or container runtime is available.
The second transactionally removes only `ask_requests`, executes the actual `0002` body, inspects
its constraints and index, then rolls back so the shared integration database is restored. Both
are included in Cloud Build's temporary pgvector PostgreSQL gate. No database or migration
assertion failed locally; connection establishment failed first. Run both tests against PostgreSQL
before changing the audit status from verification pending to cleared. The
unit/API-only backend coverage command reported 72.19% because it excludes every PostgreSQL-backed
repository suite; it is not accepted as the required 80% completion gate. Rerun coverage with the
database integration suite after PostgreSQL becomes available.

No cloud migration, build, publication, or deployment occurred in the initial local TDD cycle
described above; the later v11 attempt is recorded below.

## v11 r3 Cloud Build RED and local remediation

The one authorized v11 r3 build, `a669ac15-5367-48b0-abd6-f2c691ae3a5b`, used the verified
197-file source manifest with aggregate SHA-256
`65dd9df07fb12849607e3ac2aac0dbf2545ff3e39a36373902b8afb99350cc3b`. Its secret scan passed and
its temporary PostgreSQL backend gate reached `352 passed, 1 failed`. The failure was
`test_answer_request_idempotency_excludes_duplicates_and_replays_one_commit`: inserting the
initial `in_progress` claim violated `ck_ask_requests_valid_response_state` because SQLAlchemy's
default JSONB mapping serialized Python `None` as JSON `null`, which is not SQL `NULL`.

The database constraint is intentional and was not weakened. A focused unit regression first
failed with `1 failed, 6 passed` because `response_type.none_as_null` was false. The model now maps
the nullable response as `JSONB(none_as_null=True)`, and the test additionally verifies that the
PostgreSQL bind processor returns SQL `NULL` for Python `None`. Post-fix local evidence is:

- Focused metadata suite: `7 passed`.
- Complete database-free backend suite: `297 passed, 57 deselected`.
- Ruff: pass.
- Strict mypy: pass across 61 source files.

The build stopped at the failed backend quality gate. It published no runtime image and therefore
no migration-phase Terraform action, migration execution, application-phase Terraform action,
evaluation capture, cleanup, or retained evaluation object was attempted. Docker's local daemon
was unavailable, so the corrected integration test still needs the temporary PostgreSQL gate in a
separately authorized replacement build. A successful replacement build and exactly one successful
development migration execution remain prerequisites for the v11 API rollout.

## v11 r4 replacement: live PostgreSQL GREEN and migration-first rollout

The separately authorized r4 replacement used the reverified 197-file aggregate manifest
`9568309a7087cc1abee6da05e14e8c67d3621fe5b3acd03d66c6d8d04b7cac7f`. Cloud Build
`5fd9a8ed-d4fd-4b48-911f-fb9414186cfa` passed all eight gates, including the temporary
PostgreSQL/pgvector backend gate that previously failed. It published immutable image
`sha256:df0644eb31a4fafccd4e55deeccabd2dfe5dc3d1ca40d29fccde70ca0f6d7b66`.

The migration phase applied the existing saved plan with SHA-256
`D8EFC70E7B7E1E9D40839FBEE371000CD8B7043E668396AA6281A17E416FC239`; its only actionable change
was the development migration-job image. The sole zero-retry migration execution,
`mtg-rag-dev-migration-mmqd5`, completed successfully at `2026-08-24T12:20:38.751092Z` on job
generation 23 with `maxRetries=0`. The application phase then applied existing saved plan
`C79CA6C5BC8378CD385C99CDE519930FEB922F8EC71746550971A1FDE6F0172B`, limited to the development
API, ingestion-job, and evaluation-job image leaves. No ingestion execution occurred.

This clears the development PostgreSQL verification and migration-execution prerequisites for
request idempotency. It does not make the full v11 release packet pass: the subsequent single
121-case capture failed citation coverage, behavior, and cached-latency-evidence gates, as recorded
in `claim-support-validation.tdd.md` and the production audit. No qualification retry was run.
