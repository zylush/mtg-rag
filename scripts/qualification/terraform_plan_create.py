from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

SHA256 = re.compile(r"[0-9a-fA-F]{64}")

JsonObject = dict[str, object]


class PlanCreateError(RuntimeError):
    """Raised when a one-shot saved Terraform plan cannot be trusted."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(root: Path, path: Path, *, strict: bool) -> Path:
    resolved = path.resolve(strict=strict)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise PlanCreateError(f"path must stay inside the source root: {path}") from error
    return resolved


def _validated_paths(
    root: Path, working_directory: Path, var_file: Path, out: Path
) -> tuple[Path, Path, Path, Path]:
    source_root = root.resolve(strict=True)
    if not source_root.is_dir():
        raise PlanCreateError("source root must be a directory")

    resolved_working_directory = _inside(
        source_root, working_directory, strict=True
    )
    expected_working_directory = (source_root / "infra").resolve(strict=True)
    if (
        not resolved_working_directory.is_dir()
        or resolved_working_directory != expected_working_directory
    ):
        raise PlanCreateError("working directory must be the source root's infra directory")

    if var_file.is_symlink():
        raise PlanCreateError("Terraform variable file must not be a symbolic link")
    resolved_var_file = _inside(source_root, var_file, strict=True)
    expected_temp_directory = (source_root / ".tmp").resolve(strict=True)
    if (
        not resolved_var_file.is_file()
        or resolved_var_file.parent != expected_temp_directory
        or resolved_var_file.suffix != ".tfvars"
    ):
        raise PlanCreateError("Terraform variable file must be a .tmp/*.tfvars file")

    if out.exists() or out.is_symlink():
        raise PlanCreateError("saved Terraform plan already exists")
    resolved_out = _inside(source_root, out, strict=False)
    if resolved_out.parent != expected_temp_directory or resolved_out.suffix != ".tfplan":
        raise PlanCreateError("saved Terraform plan must be a new .tmp/*.tfplan file")

    return (
        source_root,
        resolved_working_directory,
        resolved_var_file,
        resolved_out,
    )


def create_plan(
    *,
    root: Path,
    working_directory: Path,
    var_file: Path,
    expected_var_file_sha256: str,
    out: Path,
    terraform: str = "terraform",
    gcloud: str = "gcloud",
    use_gcloud_access_token: bool = False,
) -> JsonObject:
    if not SHA256.fullmatch(expected_var_file_sha256):
        raise PlanCreateError("expected variable-file SHA-256 must be 64 hexadecimal characters")
    (
        _source_root,
        resolved_working_directory,
        resolved_var_file,
        resolved_out,
    ) = _validated_paths(root, working_directory, var_file, out)

    expected_hash = expected_var_file_sha256.lower()
    initial_hash = _sha256_file(resolved_var_file)
    if initial_hash != expected_hash:
        raise PlanCreateError("Terraform variable-file SHA-256 does not match authorization")

    resolved_terraform = shutil.which(terraform)
    if resolved_terraform is None:
        raise PlanCreateError(f"could not resolve Terraform executable: {terraform}")
    access_token: str | None = None
    if use_gcloud_access_token:
        resolved_gcloud = shutil.which(gcloud)
        if resolved_gcloud is None:
            raise PlanCreateError(f"could not resolve gcloud executable: {gcloud}")
        token_process = subprocess.run(  # noqa: S603
            [resolved_gcloud, "auth", "print-access-token"],
            check=False,
            capture_output=True,
            text=True,
        )
        access_token = token_process.stdout.strip()
        if token_process.returncode != 0 or not access_token:
            raise PlanCreateError("could not obtain gcloud access token")
    arguments = [
        resolved_terraform,
        "plan",
        "-input=false",
        "-lock-timeout=0s",
        f"-var-file={resolved_var_file}",
        f"-out={resolved_out}",
    ]
    child_environment: dict[str, str] | None = None
    try:
        if access_token is None:
            process = subprocess.run(  # noqa: S603
                arguments,
                cwd=resolved_working_directory,
                check=False,
            )
        else:
            child_environment = os.environ.copy()
            child_environment["GOOGLE_OAUTH_ACCESS_TOKEN"] = access_token
            process = subprocess.run(  # noqa: S603
                arguments,
                cwd=resolved_working_directory,
                check=False,
                env=child_environment,
            )
    finally:
        access_token = None
        if child_environment is not None:
            child_environment.pop("GOOGLE_OAUTH_ACCESS_TOKEN", None)
    if process.returncode != 0:
        raise PlanCreateError("terraform plan failed; no retry was attempted")

    if _sha256_file(resolved_var_file) != initial_hash:
        raise PlanCreateError("Terraform variable file changed during planning")
    if not resolved_out.is_file() or resolved_out.stat().st_size == 0:
        raise PlanCreateError("terraform did not create a non-empty saved plan")

    report: JsonObject = {
        "status": "created",
        "var_file": str(resolved_var_file),
        "var_file_sha256": initial_hash,
        "plan": str(resolved_out),
        "plan_sha256": _sha256_file(resolved_out),
        "terraform_invocations": 1,
    }
    if use_gcloud_access_token:
        report["credential_process_invocations"] = 1
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create one hash-pinned development Terraform plan without retries."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--working-directory", required=True, type=Path)
    parser.add_argument("--var-file", required=True, type=Path)
    parser.add_argument("--expected-var-file-sha256", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--terraform", default="terraform")
    parser.add_argument("--gcloud", default="gcloud")
    parser.add_argument("--use-gcloud-access-token", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        report = create_plan(
            root=arguments.root,
            working_directory=arguments.working_directory,
            var_file=arguments.var_file,
            expected_var_file_sha256=arguments.expected_var_file_sha256,
            out=arguments.out,
            terraform=arguments.terraform,
            gcloud=arguments.gcloud,
            use_gcloud_access_token=arguments.use_gcloud_access_token,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (OSError, PlanCreateError) as error:
        print(
            json.dumps({"status": "error", "error": str(error)}, sort_keys=True),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
