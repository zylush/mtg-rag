from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_local_stack_uses_postgres_pgvector_and_no_redis() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert services["db"]["image"].startswith("pgvector/pgvector:pg16")
    assert "healthcheck" in services["db"]
    assert "api" in services
    assert "ingestion" in services
    assert "redis" not in services
    assert "memorystore" not in services


def test_ingestion_job_does_not_retry_non_resumable_embedding_work() -> None:
    ingestion = (ROOT / "infra" / "ingestion.tf").read_text(encoding="utf-8")

    assert "max_retries     = 0" in ingestion


def test_development_ingestion_scheduler_is_card_only_but_production_is_not() -> None:
    ingestion = (ROOT / "infra" / "ingestion.tf").read_text(encoding="utf-8")

    assert 'args    = var.environment == "prod" ? [] : ["cards"]' in ingestion


def test_evaluation_job_is_development_only_same_region_and_least_privilege() -> None:
    evaluation = (ROOT / "infra" / "evaluation.tf").read_text(encoding="utf-8")
    core = (ROOT / "infra" / "core.tf").read_text(encoding="utf-8")
    outputs = (ROOT / "infra" / "outputs.tf").read_text(encoding="utf-8")
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")

    assert 'resource "google_cloud_run_v2_job" "evaluation"' in evaluation
    assert (
        "count",
        "=",
        "var.environment",
        "==",
        '"prod"',
        "?",
        "0",
        ":",
        "1",
    ) in {tuple(line.split()) for line in evaluation.splitlines()}
    assert "location            = var.region" in evaluation
    assert "service_account = google_service_account.evaluation[0].email" in evaluation
    assert 'command = ["mtg-rag-capture"]' in evaluation
    assert '"--confirm-non-production"' in evaluation
    assert '"--output-gcs-bucket"' in evaluation
    assert '"--output-gcs-prefix"' in evaluation
    assert '"/app/evals/mtg_rules_v1.json"' in evaluation
    assert "max_retries     = 0" in evaluation
    assert "cloud_sql_instance" in evaluation

    assert 'resource "google_service_account" "evaluation"' in core
    assert 'role   = "roles/storage.objectCreator"' in core
    evaluation_iam = core.split(
        'resource "google_storage_bucket_iam_member" "evaluation_captures"', 1
    )[1]
    assert 'roles/storage.objectAdmin' not in evaluation_iam
    assert "google_secret_manager_secret_iam_member.evaluation_database" in evaluation
    assert "google_secret_manager_secret_iam_member.evaluation_openai" in evaluation
    assert 'try(google_cloud_run_v2_job.evaluation[0].name, null)' in outputs
    assert "COPY evals ./evals" in dockerfile.split("FROM base AS runtime", 1)[1]


def test_api_container_is_python_312_and_keeps_openai_key_out_of_image() -> None:
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")

    assert dockerfile.startswith("FROM python:3.12-slim")
    assert "OPENAI_API_KEY" not in dockerfile
    assert "ARG OPENAI" not in dockerfile
    assert "USER app" in dockerfile


def test_api_container_installs_current_debian_security_updates() -> None:
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")

    assert "apt-get update" in dockerfile
    assert "apt-get upgrade -y" in dockerfile
    assert "rm -rf /var/lib/apt/lists/*" in dockerfile


def test_openai_sdk_is_pinned_to_the_tested_snapshot() -> None:
    pyproject = (ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8")

    assert '"openai==3.0.0"' in pyproject


def test_api_service_identity_has_only_required_firebase_user_permissions() -> None:
    core = (ROOT / 'infra' / 'core.tf').read_text(encoding='utf-8')
    role = chr(34) + 'roles/firebaseauth.admin' + chr(34) + ','
    delete_permission = chr(34) + 'firebaseauth.users.delete' + chr(34)
    get_permission = chr(34) + 'firebaseauth.users.get' + chr(34)
    firebase_auth_api = chr(34) + 'identitytoolkit.googleapis.com' + chr(34) + ','

    ingestion_roles = core.split('ingestion_project_roles', 1)[1]

    assert role not in core
    assert delete_permission in core
    assert get_permission in core
    assert 'google_project_iam_custom_role' in core
    assert role not in ingestion_roles
    assert firebase_auth_api in core


def test_production_requires_pinned_secret_versions() -> None:
    variables = (ROOT / "infra" / "variables.tf").read_text(encoding="utf-8")
    prod_example = (
        ROOT / "infra" / "environments" / "prod.tfvars.example"
    ).read_text(encoding="utf-8")

    assert (
        'var.environment != "prod" || '
        'can(regex("^[1-9][0-9]*$", var.openai_secret_version))'
    ) in variables
    assert (
        'var.environment != "prod" || '
        'can(regex("^[1-9][0-9]*$", var.database_url_secret_version))'
    ) in variables
    assert 'openai_secret_version = "1"' in prod_example
    assert 'database_url_secret_version = "1"' in prod_example


def test_development_budget_validation_accepts_the_documented_null_default() -> None:
    variables = (ROOT / "infra" / "variables.tf").read_text(encoding="utf-8")

    assert (
        'var.environment != "prod" ? true : '
        'try(var.monthly_budget_usd > 0, false)'
    ) in variables


def test_conversation_context_rollout_is_default_off_and_wired_to_cloud_run() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    variables = (ROOT / "infra" / "variables.tf").read_text(encoding="utf-8")
    runtime = (ROOT / "infra" / "runtime.tf").read_text(encoding="utf-8")
    dev = (ROOT / "infra" / "environments" / "dev.tfvars.example").read_text(
        encoding="utf-8"
    )
    prod = (ROOT / "infra" / "environments" / "prod.tfvars.example").read_text(
        encoding="utf-8"
    )

    assert "MTG_RAG_CONVERSATION_CONTEXT_ENABLED" in compose
    assert "CONVERSATION_CONTEXT_ENABLED:-false" in compose
    assert 'variable "conversation_context_enabled"' in variables
    assert "default     = false" in variables
    assert "MTG_RAG_CONVERSATION_CONTEXT_ENABLED" in runtime
    assert "MTG_RAG_CONVERSATION_CONTEXT_MAX_MESSAGES" in runtime
    assert "MTG_RAG_CONVERSATION_CONTEXT_MAX_CHARACTERS" in runtime
    assert "conversation_context_enabled = true" in dev
    assert "conversation_context_enabled = false" in prod


def test_firebase_hosting_proxy_delivery_avoids_a_custom_domain_in_development() -> None:
    variables = (ROOT / "infra" / "variables.tf").read_text(encoding="utf-8")
    runtime = (ROOT / "infra" / "runtime.tf").read_text(encoding="utf-8")
    dev_example = (
        ROOT / "infra" / "environments" / "dev.tfvars.example"
    ).read_text(encoding="utf-8")
    hosting = yaml.safe_load((ROOT / "firebase.json").read_text(encoding="utf-8"))

    assert '"firebase_hosting_proxy"' in variables
    assert 'public_delivery_mode = "firebase_hosting_proxy"' in dev_example
    assert "INGRESS_TRAFFIC_ALL" in runtime
    assert {
        "source": "/v1/**",
        "run": {"serviceId": "mtg-rag-dev-api", "region": "asia-east1"},
    } in hosting["hosting"]["rewrites"]


def test_firebase_google_auth_has_a_reproducible_placeholder_only_template() -> None:
    auth_template_path = ROOT / "firebase.auth.json.example"
    ignore_rules = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert auth_template_path.is_file()
    auth_template = yaml.safe_load(auth_template_path.read_text(encoding="utf-8"))
    google = auth_template["auth"]["providers"]["googleSignIn"]

    assert google == {
        "oAuthBrandDisplayName": "MTG Rules Desk",
        "supportEmail": "replace-with-public-support-email",
    }
    assert {"firebase.auth.local.json", ".firebase/"}.issubset(ignore_rules)


def test_postgres_16_custom_tier_explicitly_uses_cloud_sql_enterprise_edition() -> None:
    core = (ROOT / "infra" / "core.tf").read_text(encoding="utf-8")

    assert ("edition", "=", '"ENTERPRISE"') in {tuple(line.split()) for line in core.splitlines()}


def test_cloud_build_ignore_rules_keep_frontend_quality_scripts_uploadable() -> None:
    cloud_ignore = (ROOT / "cloudbuild.ignore").read_text(encoding="utf-8")

    assert "#!include:" not in cloud_ignore
    assert "scripts/" not in cloud_ignore.splitlines()
    assert "scripts/codex/" in cloud_ignore
    assert "docs/" in cloud_ignore
    assert "Documentation/" in cloud_ignore
    assert {".env", ".env.*", "node_modules/", ".terraform/"}.issubset(
        cloud_ignore.splitlines()
    )
    assert (ROOT / "frontend" / "scripts" / "check-pwa.mjs").is_file()


def test_local_terraform_plans_are_excluded_from_git_and_cloud_build() -> None:
    git_ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    cloud_ignore = (ROOT / "cloudbuild.ignore").read_text(encoding="utf-8").splitlines()

    assert ".tmp/" in git_ignore
    assert ".tmp/" in cloud_ignore


def test_versioned_pytest_caches_are_excluded_from_cloud_build() -> None:
    cloud_ignore = (ROOT / "cloudbuild.ignore").read_text(encoding="utf-8").splitlines()

    assert ".tmp-pytest-cache*/" in cloud_ignore


def test_cloud_build_upload_keeps_runtime_manifest_test_dependencies() -> None:
    cloud_ignore = (ROOT / "cloudbuild.ignore").read_text(encoding="utf-8")
    ignored_paths = set(cloud_ignore.splitlines())

    assert ".gitignore" not in ignored_paths
    assert "firebase.auth.json.example" not in ignored_paths


def test_cloud_build_runtime_image_tag_works_for_manual_submissions() -> None:
    cloud_build = (ROOT / "cloudbuild.yaml").read_text(encoding="utf-8")

    assert "$BUILD_ID" in cloud_build
    assert "$SHORT_SHA" not in cloud_build


def test_cloud_build_static_analysis_includes_qualification_tools() -> None:
    cloud_build = (ROOT / "cloudbuild.yaml").read_text(encoding="utf-8")

    assert "ruff check app tests /workspace/scripts/qualification" in cloud_build
    assert "mypy app /workspace/scripts/qualification" in cloud_build


def test_migration_job_supplies_the_required_frontend_origin_setting() -> None:
    migration = (ROOT / "infra" / "migration.tf").read_text(encoding="utf-8")
    variables = (ROOT / "infra" / "variables.tf").read_text(encoding="utf-8")

    assert 'name  = "MTG_RAG_FRONTEND_ORIGIN"' in migration
    assert "value = var.frontend_origin" in migration
    assert "image   = coalesce(var.migration_image, var.api_image)" in migration
    assert 'variable "migration_image"' in variables
    assert "default     = null" in variables


def test_example_environment_contains_only_placeholders_and_safe_defaults() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "sk-" not in example
    assert "MTG_RAG_OPENAI_API_KEY=" in example
    assert "MTG_RAG_OPENAI_GENERATION_MODEL=gpt-5.6-luna" in example
    assert "MTG_RAG_EMBEDDING_DIMENSIONS=1536" in example
    assert "MTG_RAG_FRONTEND_ORIGIN=http://localhost:5173" in example


def test_alembic_initial_revision_enables_required_postgres_extensions() -> None:
    revisions = list((ROOT / "backend" / "migrations" / "versions").glob("*.py"))

    revision = next(path for path in revisions if path.name.startswith("0001_"))
    revision = revision.read_text(encoding="utf-8")
    assert 'CREATE EXTENSION IF NOT EXISTS "vector"' in revision
    assert 'CREATE EXTENSION IF NOT EXISTS "pg_trgm"' in revision


def test_idempotency_revision_is_chained_and_safe_for_fresh_bootstrap() -> None:
    revision = (
        ROOT / "backend" / "migrations" / "versions" / "0002_ask_request_idempotency.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision: str | None = "0001"' in revision
    assert "CREATE TABLE IF NOT EXISTS ask_requests" in revision
    assert "UNIQUE (user_id, client_request_id)" in revision
