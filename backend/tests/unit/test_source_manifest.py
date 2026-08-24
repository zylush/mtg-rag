from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "qualification" / "source_manifest.py"


def _load_source_manifest_module():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("qualification_source_manifest", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


source_manifest = _load_source_manifest_module()


def test_manifest_is_deterministic_and_normalizes_paths(tmp_path: Path) -> None:
    alpha = b"alpha\n"
    beta = b"\x00beta"
    (tmp_path / "a.txt").write_bytes(alpha)
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "b.bin").write_bytes(beta)

    first = source_manifest.build_manifest(
        tmp_path, ["nested\\b.bin", "a.txt"]
    )
    second = source_manifest.build_manifest(
        tmp_path, ["a.txt", "nested/b.bin"]
    )

    assert first == second
    assert [entry["path"] for entry in first["files"]] == [
        "a.txt",
        "nested/b.bin",
    ]
    canonical = (
        "mtg-rag-cloud-build-source-manifest-v1\n"
        f"a.txt\0{len(alpha)}\0{hashlib.sha256(alpha).hexdigest()}\n"
        f"nested/b.bin\0{len(beta)}\0{hashlib.sha256(beta).hexdigest()}\n"
    ).encode()
    assert first["aggregate_sha256"] == hashlib.sha256(canonical).hexdigest()


@pytest.mark.parametrize(
    ("paths", "message"),
    [
        (["../outside.txt"], "relative"),
        (["C:/outside.txt"], "relative"),
        (["a.txt", ".\\a.txt"], "duplicate"),
        (["nested"], "regular file"),
    ],
)
def test_manifest_rejects_unsafe_or_ambiguous_paths(
    tmp_path: Path, paths: list[str], message: str
) -> None:
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    (tmp_path / "nested").mkdir()

    with pytest.raises(source_manifest.ManifestError, match=message):
        source_manifest.build_manifest(tmp_path, paths)


def test_manifest_rejects_empty_missing_and_non_directory_sources(
    tmp_path: Path,
) -> None:
    with pytest.raises(source_manifest.ManifestError, match="empty"):
        source_manifest.build_manifest(tmp_path, [])
    with pytest.raises(source_manifest.ManifestError, match="inside the source root"):
        source_manifest.build_manifest(tmp_path, ["missing.txt"])
    root_file = tmp_path / "root.txt"
    root_file.write_text("not a directory", encoding="utf-8")
    with pytest.raises(source_manifest.ManifestError, match="must be a directory"):
        source_manifest.build_manifest(root_file, ["anything"])


def test_manifest_detects_a_file_that_changes_during_hashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    real_hash_file = source_manifest._hash_file
    calls = 0

    def changing_hash(path: Path) -> tuple[int, str]:
        nonlocal calls
        calls += 1
        if calls == 2:
            return 99, "0" * 64
        return real_hash_file(path)

    monkeypatch.setattr(source_manifest, "_hash_file", changing_hash)

    with pytest.raises(source_manifest.ManifestError, match="changed while"):
        source_manifest.build_manifest(tmp_path, ["source.txt"])


def test_manifest_diff_names_added_removed_and_changed_files(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("first", encoding="utf-8")
    (tmp_path / "b.txt").write_text("removed", encoding="utf-8")
    expected = source_manifest.build_manifest(tmp_path, ["a.txt", "b.txt"])

    (tmp_path / "a.txt").write_text("changed", encoding="utf-8")
    (tmp_path / "c.txt").write_text("added", encoding="utf-8")
    observed = source_manifest.build_manifest(tmp_path, ["a.txt", "c.txt"])

    assert source_manifest.manifest_diff(expected, observed) == {
        "added": ["c.txt"],
        "removed": ["b.txt"],
        "changed": ["a.txt"],
    }


def test_manifest_output_is_create_only(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    manifest = source_manifest.build_manifest(tmp_path, ["source.txt"])
    output = tmp_path / "manifest.json"

    source_manifest.write_manifest_create_only(output, manifest)

    assert json.loads(output.read_text(encoding="utf-8")) == manifest
    with pytest.raises(FileExistsError):
        source_manifest.write_manifest_create_only(output, manifest)


def test_retained_manifest_validation_is_fail_closed(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    valid = source_manifest.build_manifest(tmp_path, ["source.txt"])
    invalid_record = deepcopy(valid)
    invalid_record["files"][0]["size"] = True
    unsorted = deepcopy(valid)
    unsorted["files"] = [deepcopy(valid["files"][0]), deepcopy(valid["files"][0])]
    invalid_values = [
        (None, "JSON object"),
        ({**valid, "schema_version": 2}, "schema version"),
        ({**valid, "hash_algorithm": "md5"}, "must be sha256"),
        ({**valid, "files": []}, "non-empty list"),
        ({**valid, "files": [{"path": 4}]}, "invalid file record"),
        (unsorted, "unique and sorted"),
        ({**valid, "file_count": 2}, "file count"),
        ({**valid, "aggregate_sha256": "0" * 64}, "aggregate hash"),
        (invalid_record, "invalid file record"),
    ]

    for value, message in invalid_values:
        with pytest.raises(source_manifest.ManifestError, match=message):
            source_manifest._validated_manifest(value)

    malformed = tmp_path / "malformed.json"
    malformed.write_text("not json", encoding="utf-8")
    with pytest.raises(source_manifest.ManifestError, match="could not read"):
        source_manifest.load_manifest(malformed)


def test_cli_freezes_and_rechecks_an_offline_upload_listing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    paths = tmp_path / "paths.txt"
    paths.write_text("source.txt\n", encoding="utf-8")
    (tmp_path / ".tmp").mkdir()
    output = tmp_path / ".tmp" / "manifest.json"

    assert source_manifest.main(
        [
            "freeze",
            "--root",
            str(tmp_path),
            "--paths-file",
            str(paths),
            "--output",
            str(output),
        ]
    ) == 0
    freeze_summary = json.loads(capsys.readouterr().out)
    assert freeze_summary == {
        "aggregate_sha256": json.loads(output.read_text(encoding="utf-8"))[
            "aggregate_sha256"
        ],
        "file_count": 1,
        "manifest": str(output.resolve()),
        "status": "frozen",
    }

    assert source_manifest.main(
        [
            "verify",
            "--root",
            str(tmp_path),
            "--paths-file",
            str(paths),
            "--manifest",
            str(output),
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "match"

    source.write_text("drift", encoding="utf-8")
    assert source_manifest.main(
        [
            "verify",
            "--root",
            str(tmp_path),
            "--paths-file",
            str(paths),
            "--manifest",
            str(output),
        ]
    ) == 2
    drift = json.loads(capsys.readouterr().err)
    assert drift["diff"] == {
        "added": [],
        "removed": [],
        "changed": ["source.txt"],
    }
    assert drift["status"] == "drift"


def test_cli_refuses_an_output_that_would_pollute_the_source_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "source.txt").write_text("source", encoding="utf-8")
    paths = tmp_path / "paths.txt"
    paths.write_text("source.txt\n", encoding="utf-8")
    output = tmp_path / "manifest.json"

    assert source_manifest.main(
        [
            "freeze",
            "--root",
            str(tmp_path),
            "--paths-file",
            str(paths),
            "--output",
            str(output),
        ]
    ) == 1
    error = json.loads(capsys.readouterr().err)
    assert "outside the source root or under .tmp" in error["error"]
    assert not output.exists()


def test_upload_listing_failure_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailedProcess:
        returncode = 1
        stdout = ""
        stderr = "permission denied"

    monkeypatch.setattr(source_manifest.shutil, "which", lambda _name: "gcloud.cmd")
    monkeypatch.setattr(
        source_manifest.subprocess, "run", lambda *_args, **_kwargs: FailedProcess()
    )

    with pytest.raises(source_manifest.ManifestError, match="listing failed"):
        source_manifest.gcloud_upload_paths("gcloud")


def test_upload_listing_resolves_gcloud_and_filters_blank_lines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class SuccessfulProcess:
        returncode = 0
        stdout = "a.txt\n\nnested\\b.txt\n"
        stderr = ""

    observed: dict[str, object] = {}

    def successful_run(command: list[str], **kwargs: object) -> SuccessfulProcess:
        observed["command"] = command
        observed["cwd"] = kwargs["cwd"]
        return SuccessfulProcess()

    monkeypatch.setattr(source_manifest.shutil, "which", lambda _name: "gcloud.cmd")
    monkeypatch.setattr(source_manifest.subprocess, "run", successful_run)

    assert source_manifest.gcloud_upload_paths("gcloud", tmp_path) == [
        "a.txt",
        "nested\\b.txt",
    ]
    assert observed == {
        "command": ["gcloud.cmd", "meta", "list-files-for-upload"],
        "cwd": tmp_path.resolve(),
    }


def test_upload_listing_rejects_missing_executable_and_empty_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(source_manifest.shutil, "which", lambda _name: None)
    with pytest.raises(source_manifest.ManifestError, match="could not resolve"):
        source_manifest.gcloud_upload_paths("gcloud")

    class EmptyProcess:
        returncode = 0
        stdout = "\n"
        stderr = ""

    monkeypatch.setattr(source_manifest.shutil, "which", lambda _name: "gcloud.cmd")
    monkeypatch.setattr(
        source_manifest.subprocess, "run", lambda *_args, **_kwargs: EmptyProcess()
    )
    with pytest.raises(source_manifest.ManifestError, match="returned no files"):
        source_manifest.gcloud_upload_paths("gcloud")
