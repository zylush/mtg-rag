# Firebase account deletion IAM integration: TDD evidence

## Source and user journey

Derived during the Google Cloud and Firebase integration audit for MTG Rules Desk.

As a signed-in player, I can permanently delete my MTG Rules Desk account, so that
the API removes both application data and the associated Firebase identity.

## RED

The deployment audit found that the FastAPI account-deletion endpoint calls the
Firebase Admin SDK, while the Cloud Run API service account had no Firebase user
management permission.

Command:

    cd backend
    ..\.venv\Scripts\pytest.exe tests\unit\test_runtime_manifests.py::test_api_service_identity_can_delete_the_current_users_firebase_identity -q

Result: FAIL. The new assertion could not find the required Firebase user-management
role in infra/core.tf.

## GREEN

Terraform now enables identitytoolkit.googleapis.com and defines a project custom
role with only firebaseauth.users.delete. That custom role is bound to the API
service account; the ingestion service account receives no Firebase user-management
permission.

Command:

    cd backend
    ..\.venv\Scripts\pytest.exe tests\unit\test_runtime_manifests.py -q

Result: PASS, 6 passed.

Additional checks:

    ..\.venv\Scripts\ruff.exe check app tests
    ..\.venv\Scripts\mypy.exe app

Result: PASS. Ruff reported all checks passed and mypy reported no issues in 56
source files.

## Guarantees

| Guarantee | Evidence | Type | Result |
| --- | --- | --- | --- |
| The required Identity Toolkit API is declared in Terraform. | test_api_service_identity_can_delete_the_current_users_firebase_identity | Manifest unit test | PASS |
| The API can receive the exact Firebase user-delete permission. | test_api_service_identity_can_delete_the_current_users_firebase_identity | Manifest unit test | PASS |
| Ingestion does not receive Firebase user-management access. | test_api_service_identity_can_delete_the_current_users_firebase_identity | Manifest unit test | PASS |
| Backend linting and static typing remain clean. | Ruff and mypy commands above | Quality gate | PASS |

## Coverage and known gap

The full backend suite needs the local PostgreSQL pgvector container. Docker Desktop
was unavailable during this verification, so database-backed integration tests could
not run. The unit suite executed 83 tests successfully, but its 75.33 percent total
coverage does not represent the full project because database integration tests supply
coverage for repositories. The full test suite must be rerun after Docker is available.

## Git checkpoint

Commit 9a0c28c records the GREEN Terraform implementation. This report is recorded
in the follow-up documentation checkpoint.
