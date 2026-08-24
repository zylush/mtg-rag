from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = 1
CANONICAL_HEADER = b"mtg-rag-cloud-build-source-manifest-v1\n"
WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:($|/)")

Manifest = dict[str, Any]


class ManifestError(RuntimeError):
    """Raised when a source manifest cannot be produced or trusted."""


def _normalize_upload_path(raw_path: str) -> str:
    value = raw_path.strip().replace("\\", "/")
    if not value or "\x00" in value or "\n" in value or "\r" in value:
        raise ManifestError("upload paths must be non-empty single-line relative paths")
    if value.startswith("/") or WINDOWS_DRIVE.match(value):
        raise ManifestError(f"upload path must be relative: {raw_path!r}")

    path = PurePosixPath(value)
    if ".." in path.parts:
        raise ManifestError(f"upload path must stay relative to the source root: {raw_path!r}")
    normalized = path.as_posix()
    if normalized in {"", "."}:
        raise ManifestError("upload paths must identify regular files")
    return normalized


def _resolve_upload_file(root: Path, relative_path: str) -> Path:
    candidate = root.joinpath(*PurePosixPath(relative_path).parts)
    if candidate.is_symlink():
        raise ManifestError(f"upload path must not be a symbolic link: {relative_path}")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (FileNotFoundError, ValueError) as error:
        raise ManifestError(
            f"upload path must resolve inside the source root: {relative_path}"
        ) from error
    if not resolved.is_file():
        raise ManifestError(f"upload path must identify a regular file: {relative_path}")
    return resolved


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                size += len(chunk)
                digest.update(chunk)
    except OSError as error:
        raise ManifestError(f"could not hash upload file: {path}") from error
    return size, digest.hexdigest()


def _aggregate_sha256(files: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    digest.update(CANONICAL_HEADER)
    for entry in files:
        path = entry.get("path")
        size = entry.get("size")
        sha256 = entry.get("sha256")
        if (
            not isinstance(path, str)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or not isinstance(sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", sha256)
        ):
            raise ManifestError("manifest contains an invalid file record")
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(sha256.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def build_manifest(root: Path, upload_paths: Sequence[str]) -> Manifest:
    source_root = root.resolve(strict=True)
    if not source_root.is_dir():
        raise ManifestError(f"source root must be a directory: {source_root}")

    normalized_paths = [_normalize_upload_path(path) for path in upload_paths]
    if len(normalized_paths) != len(set(normalized_paths)):
        raise ManifestError("upload listing contains duplicate normalized paths")
    normalized_paths.sort()
    if not normalized_paths:
        raise ManifestError("upload listing is empty")

    resolved_files = {
        relative_path: _resolve_upload_file(source_root, relative_path)
        for relative_path in normalized_paths
    }
    files = [
        {
            "path": relative_path,
            "size": size,
            "sha256": sha256,
        }
        for relative_path in normalized_paths
        for size, sha256 in [_hash_file(resolved_files[relative_path])]
    ]

    first_pass = {entry["path"]: (entry["size"], entry["sha256"]) for entry in files}
    second_pass = {
        relative_path: _hash_file(resolved_files[relative_path])
        for relative_path in normalized_paths
    }
    changed_during_hash = [
        relative_path
        for relative_path in normalized_paths
        if first_pass[relative_path] != second_pass[relative_path]
    ]
    if changed_during_hash:
        raise ManifestError(
            "source changed while the manifest was being hashed: "
            + ", ".join(changed_during_hash)
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "hash_algorithm": "sha256",
        "canonical_format": "path\\0size\\0sha256\\n sorted by normalized path",
        "file_count": len(files),
        "aggregate_sha256": _aggregate_sha256(files),
        "files": files,
    }


def _validated_manifest(value: Any) -> Manifest:
    if not isinstance(value, dict):
        raise ManifestError("manifest root must be a JSON object")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError("manifest schema version is not supported")
    if value.get("hash_algorithm") != "sha256":
        raise ManifestError("manifest hash algorithm must be sha256")
    files = value.get("files")
    if not isinstance(files, list) or not files:
        raise ManifestError("manifest files must be a non-empty list")
    paths: list[str] = []
    for entry in files:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ManifestError("manifest contains an invalid file record")
        paths.append(entry["path"])
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ManifestError("manifest file paths must be unique and sorted")
    if value.get("file_count") != len(files):
        raise ManifestError("manifest file count does not match its records")
    expected_aggregate = _aggregate_sha256(files)
    if value.get("aggregate_sha256") != expected_aggregate:
        raise ManifestError("manifest aggregate hash does not match its records")
    return value


def load_manifest(path: Path) -> Manifest:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ManifestError(f"could not read source manifest: {path}") from error
    return _validated_manifest(value)


def write_manifest_create_only(path: Path, manifest: Mapping[str, Any]) -> None:
    validated = _validated_manifest(dict(manifest))
    with path.open("x", encoding="utf-8", newline="\n") as destination:
        json.dump(validated, destination, indent=2, sort_keys=True, ensure_ascii=False)
        destination.write("\n")


def _validate_manifest_output(root: Path, output: Path) -> Path:
    source_root = root.resolve(strict=True)
    resolved_output = output.resolve(strict=False)
    try:
        relative_output = resolved_output.relative_to(source_root)
    except ValueError:
        return resolved_output
    if not relative_output.parts or relative_output.parts[0] != ".tmp":
        raise ManifestError(
            "manifest output must be outside the source root or under .tmp"
        )
    return resolved_output


def _file_map(manifest: Mapping[str, Any]) -> dict[str, tuple[int, str]]:
    validated = _validated_manifest(dict(manifest))
    return {
        entry["path"]: (entry["size"], entry["sha256"])
        for entry in validated["files"]
    }


def manifest_diff(
    expected: Mapping[str, Any], observed: Mapping[str, Any]
) -> dict[str, list[str]]:
    expected_files = _file_map(expected)
    observed_files = _file_map(observed)
    expected_paths = set(expected_files)
    observed_paths = set(observed_files)
    return {
        "added": sorted(observed_paths - expected_paths),
        "removed": sorted(expected_paths - observed_paths),
        "changed": sorted(
            path
            for path in expected_paths & observed_paths
            if expected_files[path] != observed_files[path]
        ),
    }


def gcloud_upload_paths(executable: str = "gcloud", root: Path | None = None) -> list[str]:
    resolved_executable = shutil.which(executable)
    if resolved_executable is None:
        raise ManifestError(f"could not resolve gcloud executable: {executable}")
    # `which` resolves one operator-selected executable; all arguments are fixed literals.
    process = subprocess.run(  # noqa: S603
        [resolved_executable, "meta", "list-files-for-upload"],
        cwd=(root or Path.cwd()).resolve(),
        check=False,
        capture_output=True,
        text=True,
    )
    if process.returncode != 0:
        raise ManifestError("gcloud upload listing failed")
    paths: list[str] = [line for line in process.stdout.splitlines() if line.strip()]
    if not paths:
        raise ManifestError("gcloud upload listing returned no files")
    return paths


def _paths_for_arguments(arguments: argparse.Namespace) -> list[str]:
    paths_file = arguments.paths_file
    if isinstance(paths_file, Path):
        try:
            paths: list[str] = paths_file.read_text(encoding="utf-8").splitlines()
            return paths
        except OSError as error:
            raise ManifestError(
                f"could not read upload paths file: {paths_file}"
            ) from error
    if paths_file is not None:
        raise ManifestError("upload paths file must be a filesystem path")
    return gcloud_upload_paths(arguments.gcloud, arguments.root)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Freeze or recheck the exact gcloud Cloud Build upload source."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_source_arguments(command: argparse.ArgumentParser) -> None:
        command.add_argument("--root", type=Path, default=Path.cwd())
        command.add_argument("--gcloud", default="gcloud")
        command.add_argument(
            "--paths-file",
            type=Path,
            help="Offline/test input; omit for release evidence so gcloud is queried directly.",
        )

    freeze = subparsers.add_parser("freeze", help="Create a new immutable manifest file.")
    add_source_arguments(freeze)
    freeze.add_argument("--output", type=Path, required=True)

    verify = subparsers.add_parser("verify", help="Fail if current upload source has drifted.")
    add_source_arguments(verify)
    verify.add_argument("--manifest", type=Path, required=True)
    return parser


def _emit(value: Mapping[str, Any], *, error: bool = False) -> None:
    print(json.dumps(value, sort_keys=True), file=sys.stderr if error else sys.stdout)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        paths = _paths_for_arguments(arguments)
        observed = build_manifest(arguments.root, paths)
        if arguments.command == "freeze":
            output = _validate_manifest_output(arguments.root, arguments.output)
            write_manifest_create_only(output, observed)
            _emit(
                {
                    "status": "frozen",
                    "manifest": str(output),
                    "file_count": observed["file_count"],
                    "aggregate_sha256": observed["aggregate_sha256"],
                }
            )
            return 0

        expected = load_manifest(arguments.manifest)
        difference = manifest_diff(expected, observed)
        if any(difference.values()):
            _emit(
                {
                    "status": "drift",
                    "expected_aggregate_sha256": expected["aggregate_sha256"],
                    "observed_aggregate_sha256": observed["aggregate_sha256"],
                    "diff": difference,
                },
                error=True,
            )
            return 2
        _emit(
            {
                "status": "match",
                "file_count": observed["file_count"],
                "aggregate_sha256": observed["aggregate_sha256"],
            }
        )
        return 0
    except (ManifestError, FileExistsError, OSError) as error:
        _emit({"status": "error", "error": str(error)}, error=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
