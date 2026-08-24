from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "qualification" / "terraform_plan_create.py"


def _load_plan_create_module():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("qualification_plan_create", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


plan_create = _load_plan_create_module()


def _workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "repo"
    (root / "infra").mkdir(parents=True)
    (root / ".tmp").mkdir()
    var_file = root / ".tmp" / "v12.tfvars"
    var_file.write_text('environment = "dev"\n', encoding="utf-8")
    return root, var_file, root / ".tmp" / "v12.tfplan"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_create_plan_invokes_terraform_once_with_fixed_argument_array(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root, var_file, out = _workspace(tmp_path)
    calls: list[tuple[list[str], Path, bool]] = []

    class SuccessfulProcess:
        returncode = 0

    def run(arguments: list[str], *, cwd: Path, check: bool):  # type: ignore[no-untyped-def]
        calls.append((arguments, cwd, check))
        out.write_bytes(b"saved-plan")
        return SuccessfulProcess()

    monkeypatch.setattr(plan_create.shutil, "which", lambda _name: "terraform.exe")
    monkeypatch.setattr(plan_create.subprocess, "run", run)

    report = plan_create.create_plan(
        root=root,
        working_directory=root / "infra",
        var_file=var_file,
        expected_var_file_sha256=_sha256(var_file),
        out=out,
    )

    assert calls == [
        (
            [
                "terraform.exe",
                "plan",
                "-input=false",
                "-lock-timeout=0s",
                f"-var-file={var_file}",
                f"-out={out}",
            ],
            root / "infra",
            False,
        )
    ]
    assert report == {
        "status": "created",
        "var_file": str(var_file),
        "var_file_sha256": _sha256(var_file),
        "plan": str(out),
        "plan_sha256": _sha256(out),
        "terraform_invocations": 1,
    }


@pytest.mark.parametrize("failure", ["hash", "existing-plan", "outside-root"])
def test_create_plan_rejects_unsafe_input_before_invoking_terraform(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: str
) -> None:
    root, var_file, out = _workspace(tmp_path)
    expected_hash = _sha256(var_file)
    if failure == "hash":
        expected_hash = "0" * 64
    elif failure == "existing-plan":
        out.write_bytes(b"retained")
    else:
        out = tmp_path / "outside.tfplan"

    monkeypatch.setattr(plan_create.shutil, "which", lambda _name: "terraform.exe")

    def unexpected_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("terraform must not be invoked")

    monkeypatch.setattr(plan_create.subprocess, "run", unexpected_run)

    with pytest.raises(plan_create.PlanCreateError):
        plan_create.create_plan(
            root=root,
            working_directory=root / "infra",
            var_file=var_file,
            expected_var_file_sha256=expected_hash,
            out=out,
        )


def test_create_plan_does_not_retry_failed_terraform(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root, var_file, out = _workspace(tmp_path)
    invocation_count = 0

    class FailedProcess:
        returncode = 1

    def run(*_args: object, **_kwargs: object) -> FailedProcess:
        nonlocal invocation_count
        invocation_count += 1
        return FailedProcess()

    monkeypatch.setattr(plan_create.shutil, "which", lambda _name: "terraform.exe")
    monkeypatch.setattr(plan_create.subprocess, "run", run)

    with pytest.raises(plan_create.PlanCreateError, match="terraform plan failed"):
        plan_create.create_plan(
            root=root,
            working_directory=root / "infra",
            var_file=var_file,
            expected_var_file_sha256=_sha256(var_file),
            out=out,
        )

    assert invocation_count == 1
    assert not out.exists()


def test_create_plan_requires_nonempty_output_and_unchanged_input(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root, var_file, out = _workspace(tmp_path)
    original_hash = _sha256(var_file)

    class SuccessfulProcess:
        returncode = 0

    def no_output(*_args: object, **_kwargs: object) -> SuccessfulProcess:
        return SuccessfulProcess()

    monkeypatch.setattr(plan_create.shutil, "which", lambda _name: "terraform.exe")
    monkeypatch.setattr(plan_create.subprocess, "run", no_output)
    with pytest.raises(plan_create.PlanCreateError, match="non-empty saved plan"):
        plan_create.create_plan(
            root=root,
            working_directory=root / "infra",
            var_file=var_file,
            expected_var_file_sha256=original_hash,
            out=out,
        )

    def changed_input(*_args: object, **_kwargs: object) -> SuccessfulProcess:
        out.write_bytes(b"saved-plan")
        var_file.write_text('environment = "prod"\n', encoding="utf-8")
        return SuccessfulProcess()

    monkeypatch.setattr(plan_create.subprocess, "run", changed_input)
    with pytest.raises(plan_create.PlanCreateError, match="changed during planning"):
        plan_create.create_plan(
            root=root,
            working_directory=root / "infra",
            var_file=var_file,
            expected_var_file_sha256=original_hash,
            out=out,
        )


def test_create_plan_rejects_invalid_hash_and_missing_terraform(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root, var_file, out = _workspace(tmp_path)

    with pytest.raises(plan_create.PlanCreateError, match="64 hexadecimal"):
        plan_create.create_plan(
            root=root,
            working_directory=root / "infra",
            var_file=var_file,
            expected_var_file_sha256="not-a-hash",
            out=out,
        )

    monkeypatch.setattr(plan_create.shutil, "which", lambda _name: None)
    with pytest.raises(plan_create.PlanCreateError, match="could not resolve"):
        plan_create.create_plan(
            root=root,
            working_directory=root / "infra",
            var_file=var_file,
            expected_var_file_sha256=_sha256(var_file),
            out=out,
        )


def test_cli_reports_success_and_failure_as_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, var_file, out = _workspace(tmp_path)
    cli_arguments = [
        "--root",
        str(root),
        "--working-directory",
        str(root / "infra"),
        "--var-file",
        str(var_file),
        "--expected-var-file-sha256",
        _sha256(var_file),
        "--out",
        str(out),
    ]
    expected_report = {
        "status": "created",
        "terraform_invocations": 1,
    }
    monkeypatch.setattr(
        plan_create, "create_plan", lambda **_kwargs: expected_report
    )

    assert plan_create.main(cli_arguments) == 0
    assert json.loads(capsys.readouterr().out) == expected_report

    def fail(**_kwargs: object) -> None:
        raise plan_create.PlanCreateError("refused")

    monkeypatch.setattr(plan_create, "create_plan", fail)
    assert plan_create.main(cli_arguments) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {"status": "error", "error": "refused"}


def test_create_plan_passes_existing_gcloud_token_only_to_terraform_child(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root, var_file, out = _workspace(tmp_path)
    temporary_value = "ephemeral-test-value"
    calls: list[list[str]] = []

    class TokenProcess:
        returncode = 0
        stdout = temporary_value + "\n"

    class PlanProcess:
        returncode = 0

    def which(name: str) -> str:
        return {"gcloud": "gcloud.cmd", "terraform": "terraform.exe"}[name]

    def run(arguments: list[str], **kwargs: object):  # type: ignore[no-untyped-def]
        calls.append(arguments)
        if arguments[0] == "gcloud.cmd":
            assert kwargs == {"check": False, "capture_output": True, "text": True}
            return TokenProcess()
        child_environment = kwargs["env"]
        assert isinstance(child_environment, dict)
        assert child_environment["GOOGLE_OAUTH_ACCESS_TOKEN"] == temporary_value
        assert "GOOGLE_OAUTH_ACCESS_TOKEN" not in os.environ
        out.write_bytes(b"saved-plan")
        return PlanProcess()

    monkeypatch.delenv("GOOGLE_OAUTH_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(plan_create.shutil, "which", which)
    monkeypatch.setattr(plan_create.subprocess, "run", run)

    report = plan_create.create_plan(
        root=root,
        working_directory=root / "infra",
        var_file=var_file,
        expected_var_file_sha256=_sha256(var_file),
        out=out,
        use_gcloud_access_token=True,
    )

    assert calls == [
        ["gcloud.cmd", "auth", "print-access-token"],
        [
            "terraform.exe",
            "plan",
            "-input=false",
            "-lock-timeout=0s",
            f"-var-file={var_file}",
            f"-out={out}",
        ],
    ]
    assert temporary_value not in json.dumps(report)
    assert report["terraform_invocations"] == 1
    assert report["credential_process_invocations"] == 1


def test_create_plan_does_not_invoke_terraform_when_gcloud_token_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root, var_file, out = _workspace(tmp_path)
    calls: list[list[str]] = []

    class FailedTokenProcess:
        returncode = 1
        stdout = ""

    def run(arguments: list[str], **_kwargs: object) -> FailedTokenProcess:
        calls.append(arguments)
        return FailedTokenProcess()

    monkeypatch.setattr(
        plan_create.shutil,
        "which",
        lambda name: {"gcloud": "gcloud.cmd", "terraform": "terraform.exe"}[name],
    )
    monkeypatch.setattr(plan_create.subprocess, "run", run)

    with pytest.raises(plan_create.PlanCreateError, match="gcloud access token"):
        plan_create.create_plan(
            root=root,
            working_directory=root / "infra",
            var_file=var_file,
            expected_var_file_sha256=_sha256(var_file),
            out=out,
            use_gcloud_access_token=True,
        )

    assert calls == [["gcloud.cmd", "auth", "print-access-token"]]
    assert not out.exists()
