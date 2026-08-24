from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "qualification" / "terraform_plan_review.py"
OLD_IMAGE = (
    "asia-east1-docker.pkg.dev/mtg-rules-desk-dev/mtg-rag-dev/api@sha256:"
    + "1" * 64
)
NEW_IMAGE = (
    "asia-east1-docker.pkg.dev/mtg-rules-desk-dev/mtg-rag-dev/api@sha256:"
    + "2" * 64
)
RETAINED_MIGRATION_IMAGE = (
    "asia-east1-docker.pkg.dev/mtg-rules-desk-dev/mtg-rag-dev/api@sha256:"
    + "3" * 64
)
ALLOWED_ADDRESSES = [
    "google_cloud_run_v2_job.evaluation[0]",
    "google_cloud_run_v2_job.ingestion",
    "google_cloud_run_v2_job.migration",
    "google_cloud_run_v2_service.api",
]


def _load_plan_review_module():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("qualification_plan_review", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


plan_review = _load_plan_review_module()


def _resource(address: str, actions: list[str], before: object, after: object) -> dict:
    return {
        "address": address,
        "mode": "managed",
        "change": {"actions": actions, "before": before, "after": after},
    }


def _valid_plan() -> dict:
    image_updates = [
        _resource(
            address,
            ["update"],
            {
                "id": f"projects/mtg-rules-desk-dev/locations/asia-east1/{address}",
                "template": [{"containers": [{"image": OLD_IMAGE}]}],
            },
            {
                "id": f"projects/mtg-rules-desk-dev/locations/asia-east1/{address}",
                "template": [{"containers": [{"image": NEW_IMAGE}]}],
            },
        )
        for address in ALLOWED_ADDRESSES
    ]
    noops = [
        _resource(
            f"google_project_service.noop[{index}]",
            ["no-op"],
            {"id": f"projects/mtg-rules-desk-dev/services/service-{index}"},
            {"id": f"projects/mtg-rules-desk-dev/services/service-{index}"},
        )
        for index in range(50)
    ]
    artifact_before = {
        "id": "projects/mtg-rules-desk-dev/locations/asia-east1/repositories/mtg-rag-dev",
        "update_time": "before",
    }
    artifact_after = {**artifact_before, "update_time": "after"}
    evaluation_before = {
        "id": "projects/mtg-rules-desk-dev/locations/asia-east1/jobs/mtg-rag-dev-evaluation",
        "execution_count": 9,
        "latest_created_execution": [
            {"name": "execution-before", "create_time": "before", "completion_time": "before"}
        ],
    }
    evaluation_after = {
        **evaluation_before,
        "execution_count": 10,
        "latest_created_execution": [
            {"name": "execution-after", "create_time": "after", "completion_time": "after"}
        ],
    }
    return {
        "format_version": "1.2",
        "terraform_version": "1.15.8",
        "applyable": True,
        "complete": True,
        "errored": False,
        "variables": {
            "project_id": {"value": "mtg-rules-desk-dev"},
            "environment": {"value": "dev"},
            "region": {"value": "asia-east1"},
            "api_image": {"value": NEW_IMAGE},
        },
        "resource_changes": [*noops, *image_updates],
        "resource_drift": [
            _resource(
                "google_artifact_registry_repository.containers",
                ["update"],
                artifact_before,
                artifact_after,
            ),
            _resource(
                "google_cloud_run_v2_job.evaluation[0]",
                ["update"],
                evaluation_before,
                evaluation_after,
            ),
        ],
        "output_changes": {
            "api_url": {"actions": ["no-op"]},
            "evaluation_job_name": {"actions": ["no-op"]},
        },
        "checks": [
            {
                "address": {"to_display": "var.api_image"},
                "status": "pass",
                "instances": [{"status": "pass"}],
            }
        ],
    }


def _review(plan: dict) -> dict:
    return plan_review.review_plan(
        plan,
        project_id="mtg-rules-desk-dev",
        environment="dev",
        region="asia-east1",
        old_image=OLD_IMAGE,
        new_image=NEW_IMAGE,
        expected_resource_count=54,
    )


def test_valid_complete_plan_passes_exact_scope_and_drift_allowlists() -> None:
    report = _review(_valid_plan())

    assert report["gate"] == "PASS"
    assert report["violations"] == []
    assert report["resource_count"] == 54
    assert report["no_op_count"] == 50
    assert report["actionable_count"] == 4
    assert [resource["address"] for resource in report["resources"]] == sorted(
        ALLOWED_ADDRESSES
    )
    assert report["resource_drift"] == [
        {
            "address": "google_artifact_registry_repository.containers",
            "changes": ["update_time"],
        },
        {
            "address": "google_cloud_run_v2_job.evaluation[0]",
            "changes": [
                "execution_count",
                "latest_created_execution[0].completion_time",
                "latest_created_execution[0].create_time",
                "latest_created_execution[0].name",
            ],
        },
    ]


def test_migration_phase_allows_only_the_migration_image_leaf() -> None:
    plan = _valid_plan()
    plan["variables"]["api_image"]["value"] = OLD_IMAGE
    plan["variables"]["migration_image"] = {"value": NEW_IMAGE}
    for resource in plan["resource_changes"]:
        if (
            resource["change"]["actions"] == ["update"]
            and resource["address"] != "google_cloud_run_v2_job.migration"
        ):
            resource["change"]["actions"] = ["no-op"]
            resource["change"]["after"] = resource["change"]["before"]

    report = plan_review.review_plan(
        plan,
        project_id="mtg-rules-desk-dev",
        environment="dev",
        region="asia-east1",
        old_image=OLD_IMAGE,
        new_image=NEW_IMAGE,
        expected_resource_count=54,
        phase="migration",
    )

    assert report["gate"] == "PASS"
    assert report["phase"] == "migration"
    assert [resource["address"] for resource in report["resources"]] == [
        "google_cloud_run_v2_job.migration"
    ]


def test_application_phase_allows_only_the_three_post_migration_image_leaves() -> None:
    plan = _valid_plan()
    plan["variables"]["migration_image"] = {"value": NEW_IMAGE}
    migration = next(
        resource
        for resource in plan["resource_changes"]
        if resource["address"] == "google_cloud_run_v2_job.migration"
    )
    migration["change"]["actions"] = ["no-op"]
    migration["change"]["before"] = migration["change"]["after"]

    report = plan_review.review_plan(
        plan,
        project_id="mtg-rules-desk-dev",
        environment="dev",
        region="asia-east1",
        old_image=OLD_IMAGE,
        new_image=NEW_IMAGE,
        expected_resource_count=54,
        phase="application",
    )

    assert report["gate"] == "PASS"
    assert report["phase"] == "application"
    assert [resource["address"] for resource in report["resources"]] == sorted(
        address
        for address in ALLOWED_ADDRESSES
        if address != "google_cloud_run_v2_job.migration"
    )


def test_no_migration_application_phase_keeps_migration_on_old_image() -> None:
    plan = _valid_plan()
    plan["variables"]["migration_image"] = {"value": OLD_IMAGE}
    migration = next(
        resource
        for resource in plan["resource_changes"]
        if resource["address"] == "google_cloud_run_v2_job.migration"
    )
    migration["change"]["actions"] = ["no-op"]
    migration["change"]["after"] = migration["change"]["before"]

    report = plan_review.review_plan(
        plan,
        project_id="mtg-rules-desk-dev",
        environment="dev",
        region="asia-east1",
        old_image=OLD_IMAGE,
        new_image=NEW_IMAGE,
        expected_resource_count=54,
        phase="application-no-migration",
    )

    assert report["gate"] == "PASS"
    assert report["phase"] == "application-no-migration"
    assert report["variables"]["migration_image"] == OLD_IMAGE
    assert [resource["address"] for resource in report["resources"]] == sorted(
        address
        for address in ALLOWED_ADDRESSES
        if address != "google_cloud_run_v2_job.migration"
    )


def test_no_migration_application_phase_accepts_distinct_retained_migration_image(
) -> None:
    plan = _valid_plan()
    plan["variables"]["migration_image"] = {"value": RETAINED_MIGRATION_IMAGE}
    migration = next(
        resource
        for resource in plan["resource_changes"]
        if resource["address"] == "google_cloud_run_v2_job.migration"
    )
    migration["change"]["actions"] = ["no-op"]
    migration["change"]["before"] = migration["change"]["after"]

    report = plan_review.review_plan(
        plan,
        project_id="mtg-rules-desk-dev",
        environment="dev",
        region="asia-east1",
        old_image=OLD_IMAGE,
        new_image=NEW_IMAGE,
        retained_migration_image=RETAINED_MIGRATION_IMAGE,
        expected_resource_count=54,
        phase="application-no-migration",
    )

    assert report["gate"] == "PASS"
    assert report["variables"]["migration_image"] == RETAINED_MIGRATION_IMAGE


def test_no_migration_application_phase_rejects_wrong_retained_migration_image(
) -> None:
    plan = _valid_plan()
    plan["variables"]["migration_image"] = {"value": OLD_IMAGE}
    migration = next(
        resource
        for resource in plan["resource_changes"]
        if resource["address"] == "google_cloud_run_v2_job.migration"
    )
    migration["change"]["actions"] = ["no-op"]
    migration["change"]["after"] = migration["change"]["before"]

    report = plan_review.review_plan(
        plan,
        project_id="mtg-rules-desk-dev",
        environment="dev",
        region="asia-east1",
        old_image=OLD_IMAGE,
        new_image=NEW_IMAGE,
        retained_migration_image=RETAINED_MIGRATION_IMAGE,
        expected_resource_count=54,
        phase="application-no-migration",
    )

    assert report["gate"] == "FAIL"
    assert any("variable gate" in item for item in report["violations"])


def test_retained_migration_image_is_digest_pinned_and_phase_scoped() -> None:
    plan = _valid_plan()
    plan["variables"]["migration_image"] = {"value": NEW_IMAGE}
    migration = next(
        resource
        for resource in plan["resource_changes"]
        if resource["address"] == "google_cloud_run_v2_job.migration"
    )
    migration["change"]["actions"] = ["no-op"]
    migration["change"]["before"] = migration["change"]["after"]

    wrong_phase = plan_review.review_plan(
        plan,
        project_id="mtg-rules-desk-dev",
        environment="dev",
        region="asia-east1",
        old_image=OLD_IMAGE,
        new_image=NEW_IMAGE,
        retained_migration_image=RETAINED_MIGRATION_IMAGE,
        expected_resource_count=54,
        phase="application",
    )
    tagged = plan_review.review_plan(
        plan,
        project_id="mtg-rules-desk-dev",
        environment="dev",
        region="asia-east1",
        old_image=OLD_IMAGE,
        new_image=NEW_IMAGE,
        retained_migration_image=(
            "asia-east1-docker.pkg.dev/mtg-rules-desk-dev/mtg-rag-dev/api:v11"
        ),
        expected_resource_count=54,
        phase="application-no-migration",
    )

    assert wrong_phase["gate"] == "FAIL"
    assert any("only valid" in item for item in wrong_phase["violations"])
    assert tagged["gate"] == "FAIL"
    assert any("immutable digest" in item for item in tagged["violations"])


def test_no_migration_application_phase_rejects_migration_image_drift() -> None:
    plan = _valid_plan()
    plan["variables"]["migration_image"] = {"value": NEW_IMAGE}
    migration = next(
        resource
        for resource in plan["resource_changes"]
        if resource["address"] == "google_cloud_run_v2_job.migration"
    )
    migration["change"]["actions"] = ["no-op"]
    migration["change"]["before"] = migration["change"]["after"]

    report = plan_review.review_plan(
        plan,
        project_id="mtg-rules-desk-dev",
        environment="dev",
        region="asia-east1",
        old_image=OLD_IMAGE,
        new_image=NEW_IMAGE,
        expected_resource_count=54,
        phase="application-no-migration",
    )

    assert report["gate"] == "FAIL"
    assert any("variable gate" in item for item in report["violations"])


def test_rollout_phase_rejects_an_image_update_from_the_other_phase() -> None:
    plan = _valid_plan()
    plan["variables"]["api_image"]["value"] = OLD_IMAGE
    plan["variables"]["migration_image"] = {"value": NEW_IMAGE}

    report = plan_review.review_plan(
        plan,
        project_id="mtg-rules-desk-dev",
        environment="dev",
        region="asia-east1",
        old_image=OLD_IMAGE,
        new_image=NEW_IMAGE,
        expected_resource_count=54,
        phase="migration",
    )

    assert report["gate"] == "FAIL"
    assert any("resource allowlist" in item for item in report["violations"])


def test_plan_reviewer_rejects_every_scope_expansion() -> None:
    cases: list[tuple[str, dict]] = []

    targeted = _valid_plan()
    targeted["resource_changes"].pop(0)
    cases.append(("resource count", targeted))

    wrong_address = _valid_plan()
    wrong_address["resource_changes"][-1]["address"] = "google_cloud_run_v2_service.other"
    cases.append(("resource allowlist", wrong_address))

    create = _valid_plan()
    create["resource_changes"][-1]["change"]["actions"] = ["create"]
    cases.append(("actions", create))

    extra_leaf = _valid_plan()
    extra_leaf["resource_changes"][-1]["change"]["after"]["timeout"] = 90
    cases.append(("leaf changes", extra_leaf))

    production = _valid_plan()
    production["resource_changes"][-1]["change"]["before"]["id"] = (
        "projects/mtg-rules-desk-prod/services/mtg-rag-prod-api"
    )
    cases.append(("production id", production))

    variables = _valid_plan()
    variables["variables"]["environment"]["value"] = "prod"
    cases.append(("variable gate", variables))

    output = _valid_plan()
    output["output_changes"]["api_url"]["actions"] = ["update"]
    cases.append(("changed outputs", output))

    incomplete = _valid_plan()
    incomplete["complete"] = False
    cases.append(("complete=true", incomplete))

    check = _valid_plan()
    check["checks"][0]["instances"][0]["status"] = "fail"
    cases.append(("failed checks", check))

    drift = _valid_plan()
    drift["resource_drift"][0]["change"]["after"]["description"] = "unexpected"
    cases.append(("resource drift", drift))

    for expected_violation, plan in cases:
        report = _review(plan)
        assert report["gate"] == "FAIL"
        assert any(expected_violation in violation for violation in report["violations"])


def test_plan_reviewer_rejects_tags_and_wrong_digest_transition() -> None:
    tagged = _valid_plan()
    tagged["variables"]["api_image"]["value"] = (
        "asia-east1-docker.pkg.dev/mtg-rules-desk-dev/mtg-rag-dev/api:latest"
    )
    report = plan_review.review_plan(
        tagged,
        project_id="mtg-rules-desk-dev",
        environment="dev",
        region="asia-east1",
        old_image=OLD_IMAGE,
        new_image="asia-east1-docker.pkg.dev/mtg-rules-desk-dev/mtg-rag-dev/api:latest",
        expected_resource_count=54,
    )
    assert report["gate"] == "FAIL"
    assert any("immutable digest" in item for item in report["violations"])

    wrong_transition = _valid_plan()
    wrong_transition["resource_changes"][-1]["change"]["before"]["template"][0][
        "containers"
    ][0]["image"] = NEW_IMAGE
    assert any(
        "leaf changes" in item for item in _review(wrong_transition)["violations"]
    )


def test_cli_reviews_pre_rendered_json_without_mutating_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(_valid_plan()), encoding="utf-8")
    original_hash = plan_path.read_bytes()
    arguments = [
        "--plan-json",
        str(plan_path),
        "--project-id",
        "mtg-rules-desk-dev",
        "--environment",
        "dev",
        "--region",
        "asia-east1",
        "--old-image",
        OLD_IMAGE,
        "--new-image",
        NEW_IMAGE,
        "--expected-resource-count",
        "54",
    ]

    assert plan_review.main(arguments) == 0
    assert json.loads(capsys.readouterr().out)["gate"] == "PASS"
    assert plan_path.read_bytes() == original_hash

    invalid = json.loads(plan_path.read_text(encoding="utf-8"))
    invalid["complete"] = False
    plan_path.write_text(json.dumps(invalid), encoding="utf-8")
    assert plan_review.main(arguments) == 2
    assert json.loads(capsys.readouterr().out)["gate"] == "FAIL"


def test_cli_accepts_no_migration_application_phase(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = _valid_plan()
    plan["variables"]["migration_image"] = {"value": OLD_IMAGE}
    migration = next(
        resource
        for resource in plan["resource_changes"]
        if resource["address"] == "google_cloud_run_v2_job.migration"
    )
    migration["change"]["actions"] = ["no-op"]
    migration["change"]["after"] = migration["change"]["before"]
    plan_path = tmp_path / "no-migration-plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    result = plan_review.main(
        [
            "--plan-json",
            str(plan_path),
            "--project-id",
            "mtg-rules-desk-dev",
            "--environment",
            "dev",
            "--region",
            "asia-east1",
            "--old-image",
            OLD_IMAGE,
            "--new-image",
            NEW_IMAGE,
            "--expected-resource-count",
            "54",
            "--phase",
            "application-no-migration",
        ]
    )

    assert result == 0
    assert json.loads(capsys.readouterr().out)["gate"] == "PASS"


def test_cli_accepts_distinct_retained_migration_image(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = _valid_plan()
    plan["variables"]["migration_image"] = {"value": RETAINED_MIGRATION_IMAGE}
    migration = next(
        resource
        for resource in plan["resource_changes"]
        if resource["address"] == "google_cloud_run_v2_job.migration"
    )
    migration["change"]["actions"] = ["no-op"]
    migration["change"]["before"] = migration["change"]["after"]
    plan_path = tmp_path / "split-baseline-plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    result = plan_review.main(
        [
            "--plan-json",
            str(plan_path),
            "--project-id",
            "mtg-rules-desk-dev",
            "--environment",
            "dev",
            "--region",
            "asia-east1",
            "--old-image",
            OLD_IMAGE,
            "--new-image",
            NEW_IMAGE,
            "--retained-migration-image",
            RETAINED_MIGRATION_IMAGE,
            "--expected-resource-count",
            "54",
            "--phase",
            "application-no-migration",
        ]
    )

    assert result == 0
    assert json.loads(capsys.readouterr().out)["gate"] == "PASS"


def test_terraform_show_failure_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FailedProcess:
        returncode = 1
        stdout = ""
        stderr = "provider unavailable"

    monkeypatch.setattr(plan_review.shutil, "which", lambda _name: "terraform.exe")
    monkeypatch.setattr(
        plan_review.subprocess, "run", lambda *_args, **_kwargs: FailedProcess()
    )
    plan_path = tmp_path / "plan.tfplan"
    plan_path.write_bytes(b"saved plan")

    with pytest.raises(plan_review.PlanReviewError, match="terraform show failed"):
        plan_review.terraform_plan_json(plan_path, tmp_path, "terraform")
