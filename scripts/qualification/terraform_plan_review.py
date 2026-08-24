from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

MIGRATION_ADDRESS = "google_cloud_run_v2_job.migration"
APPLICATION_ADDRESSES = sorted(
    [
        "google_cloud_run_v2_job.evaluation[0]",
        "google_cloud_run_v2_job.ingestion",
        "google_cloud_run_v2_service.api",
    ]
)
ALLOWED_ADDRESSES = sorted([*APPLICATION_ADDRESSES, MIGRATION_ADDRESS])
PHASE_ADDRESSES = {
    "all": ALLOWED_ADDRESSES,
    "migration": [MIGRATION_ADDRESS],
    "application": APPLICATION_ADDRESSES,
    "application-no-migration": APPLICATION_ADDRESSES,
}
ALLOWED_RESOURCE_DRIFT = {
    "google_artifact_registry_repository.containers": ["update_time"],
    "google_cloud_run_v2_job.evaluation[0]": [
        "execution_count",
        "latest_created_execution[0].completion_time",
        "latest_created_execution[0].create_time",
        "latest_created_execution[0].name",
    ],
}
PRODUCTION_ID = re.compile(r"(?:^|[-_/])prod(?:$|[-_/])", re.IGNORECASE)

JsonObject = dict[str, Any]


class PlanReviewError(RuntimeError):
    """Raised when a saved Terraform plan cannot be parsed or reviewed."""


def differences(
    before: Any, after: Any, path: str = ""
) -> list[dict[str, Any]]:
    if before == after:
        return []
    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            return [{"path": path, "before": before, "after": after}]
        result: list[dict[str, Any]] = []
        for index, value in enumerate(before):
            child_path = f"{path}[{index}]"
            result.extend(differences(value, after[index], child_path))
        return result
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(set(before) | set(after)):
            child_path = f"{path}.{key}" if path else str(key)
            result.extend(differences(before.get(key), after.get(key), child_path))
        return result
    return [{"path": path, "before": before, "after": after}]


def _change_actions(resource: Mapping[str, Any]) -> list[str]:
    change = resource.get("change")
    if not isinstance(change, dict):
        return []
    actions = change.get("actions")
    if not isinstance(actions, list) or not all(
        isinstance(action, str) for action in actions
    ):
        return []
    return actions


def _resource_change(resource: Mapping[str, Any]) -> Mapping[str, Any]:
    change = resource.get("change")
    if not isinstance(change, dict):
        raise PlanReviewError("resource change is missing its change object")
    return change


def _resource_address(resource: Mapping[str, Any]) -> str:
    address = resource.get("address")
    if not isinstance(address, str):
        raise PlanReviewError("resource change is missing its address")
    return address


def _resource_list(plan: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = plan.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise PlanReviewError(f"{key} must be a list of resource objects")
    return value


def _variable_values(plan: Mapping[str, Any]) -> dict[str, Any]:
    variables = plan.get("variables")
    if not isinstance(variables, dict):
        return {}
    return {
        name: value.get("value") if isinstance(value, dict) else None
        for name, value in variables.items()
        if isinstance(name, str)
    }


def _contains_production_id(change: Mapping[str, Any]) -> bool:
    for state in (change.get("before"), change.get("after")):
        if isinstance(state, dict):
            resource_id = state.get("id")
            if isinstance(resource_id, str) and PRODUCTION_ID.search(resource_id):
                return True
    return False


def _check_failures(plan: Mapping[str, Any]) -> list[str]:
    checks = plan.get("checks")
    if not isinstance(checks, list) or not checks:
        return ["checks missing"]
    failures: list[str] = []
    for check in checks:
        if not isinstance(check, dict):
            failures.append("malformed check")
            continue
        address_value = check.get("address")
        address = (
            address_value.get("to_display", "unknown")
            if isinstance(address_value, dict)
            else "unknown"
        )
        status = check.get("status")
        if status != "pass":
            failures.append(f"{address}:{status}")
        instances = check.get("instances", [])
        if not isinstance(instances, list):
            failures.append(f"{address}:malformed instances")
            continue
        failures.extend(
            f"{address}[{index}]:{instance.get('status')}"
            for index, instance in enumerate(instances)
            if not isinstance(instance, dict) or instance.get("status") != "pass"
        )
    return failures


def _immutable_image_pattern(project_id: str, region: str) -> re.Pattern[str]:
    prefix = (
        f"{region}-docker.pkg.dev/{project_id}/mtg-rag-dev/api@sha256:"
    )
    return re.compile(rf"{re.escape(prefix)}[0-9a-f]{{64}}$")


def review_plan(
    plan: Mapping[str, Any],
    *,
    project_id: str,
    environment: str,
    region: str,
    old_image: str,
    new_image: str,
    expected_resource_count: int,
    retained_migration_image: str | None = None,
    phase: str = "all",
) -> JsonObject:
    violations: list[str] = []
    expected_addresses = PHASE_ADDRESSES.get(phase)
    if expected_addresses is None:
        violations.append(f"unsupported rollout phase={phase}")
        expected_addresses = []
    if plan.get("applyable") is not True:
        violations.append("plan must be applyable=true")
    if plan.get("complete") is not True:
        violations.append("plan must be complete=true")
    if plan.get("errored") is not False:
        violations.append("plan must be errored=false")

    image_pattern = _immutable_image_pattern(project_id, region)
    if not image_pattern.fullmatch(old_image) or not image_pattern.fullmatch(new_image):
        violations.append("old and new images must be immutable digest references")
    if old_image == new_image:
        violations.append("old and new image digests must differ")
    if retained_migration_image is not None:
        if not image_pattern.fullmatch(retained_migration_image):
            violations.append(
                "retained migration image must be an immutable digest reference"
            )
        if phase != "application-no-migration":
            violations.append(
                "retained migration image is only valid in application-no-migration phase"
            )

    variables = _variable_values(plan)
    expected_variables: dict[str, object] = {
        "project_id": project_id,
        "environment": environment,
        "region": region,
    }
    if phase == "migration":
        expected_variables.update(
            {"api_image": old_image, "migration_image": new_image}
        )
    elif phase == "application":
        expected_variables.update(
            {"api_image": new_image, "migration_image": new_image}
        )
    elif phase == "application-no-migration":
        expected_variables.update(
            {
                "api_image": new_image,
                "migration_image": retained_migration_image or old_image,
            }
        )
    else:
        expected_variables["api_image"] = new_image
    observed_variables = {
        name: variables.get(name) for name in expected_variables
    }
    if observed_variables != expected_variables:
        violations.append(f"variable gate={json.dumps(observed_variables, sort_keys=True)}")
    if phase == "all" and variables.get("migration_image") not in {None, new_image}:
        violations.append("migration_image must be null or match api_image in all phase")

    resource_changes = _resource_list(plan, "resource_changes")
    if len(resource_changes) != expected_resource_count:
        violations.append(
            f"resource count={len(resource_changes)} expected={expected_resource_count}"
        )
    no_op_resources = [
        resource
        for resource in resource_changes
        if _change_actions(resource) == ["no-op"]
    ]
    actionable_resources = [
        resource
        for resource in resource_changes
        if _change_actions(resource) != ["no-op"]
    ]
    actionable_addresses = sorted(
        _resource_address(resource) for resource in actionable_resources
    )
    if actionable_addresses != expected_addresses:
        violations.append(
            "resource allowlist mismatch: " + ",".join(actionable_addresses)
        )

    resources: list[JsonObject] = []
    for resource in sorted(
        actionable_resources, key=lambda item: _resource_address(item)
    ):
        address = _resource_address(resource)
        change = _resource_change(resource)
        actions = _change_actions(resource)
        leaf_changes = differences(change.get("before"), change.get("after"))
        if actions != ["update"]:
            violations.append(f"{address} actions={json.dumps(actions)}")
        if _contains_production_id(change):
            violations.append(f"{address} has a production id")
        if (
            len(leaf_changes) != 1
            or not leaf_changes[0]["path"].endswith(".image")
            or leaf_changes[0]["before"] != old_image
            or leaf_changes[0]["after"] != new_image
        ):
            violations.append(
                f"{address} leaf changes={json.dumps(leaf_changes, sort_keys=True)}"
            )
        resources.append(
            {"address": address, "actions": actions, "changes": leaf_changes}
        )

    output_changes = plan.get("output_changes", {})
    if not isinstance(output_changes, dict):
        raise PlanReviewError("output_changes must be an object")
    changed_outputs = sorted(
        name
        for name, change in output_changes.items()
        if not isinstance(change, dict) or change.get("actions") != ["no-op"]
    )
    if changed_outputs:
        violations.append("changed outputs=" + ",".join(changed_outputs))

    drift_report: list[JsonObject] = []
    for resource in sorted(
        _resource_list(plan, "resource_drift"),
        key=lambda item: _resource_address(item),
    ):
        address = _resource_address(resource)
        change = _resource_change(resource)
        drift_changes = differences(change.get("before"), change.get("after"))
        drift_paths = sorted(item["path"] for item in drift_changes)
        if (
            _change_actions(resource) != ["update"]
            or ALLOWED_RESOURCE_DRIFT.get(address) != drift_paths
            or _contains_production_id(change)
        ):
            violations.append(
                f"resource drift {address}={json.dumps(drift_paths)}"
            )
        drift_report.append({"address": address, "changes": drift_paths})

    check_failures = _check_failures(plan)
    if check_failures:
        violations.append("failed checks=" + ",".join(check_failures))

    return {
        "format_version": plan.get("format_version"),
        "terraform_version": plan.get("terraform_version"),
        "applyable": plan.get("applyable"),
        "complete": plan.get("complete"),
        "errored": plan.get("errored"),
        "variables": observed_variables,
        "phase": phase,
        "resource_count": len(resource_changes),
        "no_op_count": len(no_op_resources),
        "actionable_count": len(actionable_resources),
        "resources": resources,
        "resource_drift": drift_report,
        "changed_outputs": changed_outputs,
        "gate": "FAIL" if violations else "PASS",
        "violations": violations,
    }


def load_plan_json(path: Path) -> JsonObject:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PlanReviewError(f"could not read Terraform plan JSON: {path}") from error
    if not isinstance(value, dict):
        raise PlanReviewError("Terraform plan JSON must be an object")
    return value


def terraform_plan_json(
    plan_path: Path, working_directory: Path, executable: str = "terraform"
) -> JsonObject:
    resolved_executable = shutil.which(executable)
    if resolved_executable is None:
        raise PlanReviewError(f"could not resolve Terraform executable: {executable}")
    try:
        resolved_plan = plan_path.resolve(strict=True)
        resolved_working_directory = working_directory.resolve(strict=True)
    except OSError as error:
        raise PlanReviewError("Terraform plan or working directory does not exist") from error
    # `which` resolves one operator-selected executable; all arguments are fixed literals.
    process = subprocess.run(  # noqa: S603
        [resolved_executable, "show", "-json", str(resolved_plan)],
        cwd=resolved_working_directory,
        check=False,
        capture_output=True,
        text=True,
    )
    if process.returncode != 0:
        raise PlanReviewError("terraform show failed")
    try:
        value = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise PlanReviewError("terraform show returned invalid JSON") from error
    if not isinstance(value, dict):
        raise PlanReviewError("terraform show JSON must be an object")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Review a complete saved development Terraform image rollout plan."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--plan", type=Path)
    source.add_argument("--plan-json", type=Path)
    parser.add_argument("--working-directory", type=Path, default=Path("infra"))
    parser.add_argument("--terraform", default="terraform")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--old-image", required=True)
    parser.add_argument("--new-image", required=True)
    parser.add_argument(
        "--retained-migration-image",
        help=(
            "Immutable migration image retained during an application-no-migration "
            "rollout; defaults to --old-image for backward compatibility."
        ),
    )
    parser.add_argument("--expected-resource-count", required=True, type=int)
    parser.add_argument(
        "--phase",
        choices=tuple(PHASE_ADDRESSES),
        default="all",
        help="Exact image-leaf rollout phase allowed by this plan.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        plan = (
            load_plan_json(arguments.plan_json)
            if isinstance(arguments.plan_json, Path)
            else terraform_plan_json(
                arguments.plan, arguments.working_directory, arguments.terraform
            )
        )
        report = review_plan(
            plan,
            project_id=arguments.project_id,
            environment=arguments.environment,
            region=arguments.region,
            old_image=arguments.old_image,
            new_image=arguments.new_image,
            expected_resource_count=arguments.expected_resource_count,
            retained_migration_image=arguments.retained_migration_image,
            phase=arguments.phase,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["gate"] == "PASS" else 2
    except (PlanReviewError, OSError) as error:
        print(
            json.dumps({"status": "error", "error": str(error)}, sort_keys=True),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
