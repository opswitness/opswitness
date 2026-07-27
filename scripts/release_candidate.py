#!/usr/bin/env python3
"""Bind an immutable release candidate to canary and promotion evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence


CANARY_SCHEMA_VERSION = 2
CANARY_EVIDENCE_TYPE = "opswitness-alpha-canary-evidence"
CANARY_OBSERVATION_SCHEMA_VERSION = 1
CANARY_OBSERVATION_TYPE = "opswitness-alpha-canary-observation"
MIN_CANARY_DURATION = timedelta(hours=24)
MAX_CANARY_DURATION = timedelta(hours=48)
EXPECTED_CHECKS = frozenset(
    {
        "soak",
        "cadence",
        "recovery",
        "clean_install",
        "first_work",
    }
)
EXPECTED_CHECK_AUTHORITIES = {
    "soak": "opswitness-soak-status",
    "cadence": "opswitness-soak-ledger",
    "recovery": "opswitness-desktop-recovery-smoke",
    "clean_install": "opswitness-mounted-dmg-smoke",
    "first_work": "opswitness-first-work-evidence",
}
EXPECTED_SOURCE_FILES = {
    "soak": "sources/soak-status.json",
    "cadence": "sources/cadence-summary.json",
    "recovery": "sources/recovery-summary.json",
    "clean_install": "sources/clean-install-summary.json",
    "first_work": "sources/first-work-summary.json",
}
EXPECTED_SOURCE_TYPES = {
    "soak": "opswitness-alpha-soak-status",
    "cadence": "opswitness-alpha-cadence-summary",
    "recovery": "opswitness-alpha-recovery-summary",
    "clean_install": "opswitness-alpha-clean-install-summary",
    "first_work": "opswitness-alpha-first-work-summary",
}
OBSERVATION_FILE = "alpha-canary-observation.json"
SOURCE_SCHEMA_VERSION = 1
EXPECTED_RUNTIME_CHAIN = [
    "embedded-postgres",
    "paperclip",
    "aioncore",
    "opswitness-backend",
]
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
GIT_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
ASSET_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")
EVIDENCE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
MACOS_VERSION_PATTERN = re.compile(r"[0-9]+(?:\.[0-9]+){1,3}")
CHECKSUM_LINE_PATTERN = re.compile(
    r"(?P<sha256>[0-9a-f]{64})  (?P<name>[A-Za-z0-9][A-Za-z0-9._+-]*)"
)


class CandidateError(ValueError):
    """Raised when release evidence is incomplete or inconsistent."""


@dataclass(frozen=True)
class CandidateBinding:
    """The immutable identity shared by candidate, canary, and promotion."""

    workflow_run_id: int
    workflow_run_attempt: int
    git_commit: str
    tag: str
    dmg_sha256: str
    manifest_sha256: str
    created_at_utc: datetime

    def as_dict(self) -> dict[str, object]:
        return {
            "workflow_run_id": self.workflow_run_id,
            "workflow_run_attempt": self.workflow_run_attempt,
            "git_commit": self.git_commit,
            "tag": self.tag,
            "dmg_sha256": self.dmg_sha256,
            "manifest_sha256": self.manifest_sha256,
        }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CandidateError(f"JSON object contains duplicate key: {key}")
        result[key] = value
    return result


def _read_json_object(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CandidateError(f"{label} is unreadable: {path}") from exc

    def reject_non_finite(value: str) -> None:
        raise CandidateError(f"{label} contains non-finite number: {value}")

    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=reject_non_finite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CandidateError(f"{label} is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise CandidateError(f"{label} must be a JSON object: {path}")
    return payload, raw


def _positive_integer(value: object, *, label: str) -> int:
    if isinstance(value, bool):
        raise CandidateError(f"{label} must be a positive integer")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value):
        result = int(value)
    else:
        raise CandidateError(f"{label} must be a positive integer")
    if result <= 0:
        raise CandidateError(f"{label} must be a positive integer")
    return result


def _expected_sha256(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise CandidateError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _expected_commit(value: str) -> str:
    if not isinstance(value, str) or not GIT_COMMIT_PATTERN.fullmatch(value):
        raise CandidateError("expected commit must be a full lowercase Git object ID")
    return value


def _safe_asset_name(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not ASSET_NAME_PATTERN.fullmatch(value):
        raise CandidateError(f"{label} is not a safe flat asset name")
    if value in {".", "..", "SHA256SUMS", "build-manifest.json"}:
        raise CandidateError(f"{label} is reserved")
    return value


def _require_exact_keys(
    payload: dict[str, Any],
    expected: set[str],
    *,
    label: str,
) -> None:
    actual = set(payload)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        detail: list[str] = []
        if missing:
            detail.append(f"missing {', '.join(missing)}")
        if unexpected:
            detail.append(f"unexpected {', '.join(unexpected)}")
        raise CandidateError(f"{label} fields are invalid: {'; '.join(detail)}")


def _parse_checksums(path: Path) -> dict[str, str]:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise CandidateError(f"SHA256SUMS is unreadable: {path}") from exc
    if not content or not content.endswith("\n"):
        raise CandidateError("SHA256SUMS must be non-empty and newline-terminated")
    result: dict[str, str] = {}
    ordered_names: list[str] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        match = CHECKSUM_LINE_PATTERN.fullmatch(line)
        if match is None:
            raise CandidateError(f"SHA256SUMS line {line_number} is not canonical")
        name = _safe_asset_name(
            match.group("name"),
            label=f"SHA256SUMS line {line_number} name",
        )
        if name in result:
            raise CandidateError(f"SHA256SUMS contains duplicate asset: {name}")
        result[name] = match.group("sha256")
        ordered_names.append(name)
    if ordered_names != sorted(ordered_names):
        raise CandidateError("SHA256SUMS assets must be sorted by name")
    return result


def _manifest_artifacts(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise CandidateError("build manifest artifacts must be a non-empty array")
    result: dict[str, dict[str, Any]] = {}
    ordered_names: list[str] = []
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise CandidateError(f"build manifest artifact {index} must be an object")
        _require_exact_keys(
            artifact,
            {"name", "kind", "sha256", "size"},
            label=f"build manifest artifact {index}",
        )
        name = _safe_asset_name(
            artifact["name"],
            label=f"build manifest artifact {index} name",
        )
        if name in result:
            raise CandidateError(f"build manifest contains duplicate asset: {name}")
        if not isinstance(artifact["kind"], str) or not artifact["kind"]:
            raise CandidateError(f"build manifest artifact {name} has invalid kind")
        digest = artifact["sha256"]
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise CandidateError(f"build manifest artifact {name} has invalid sha256")
        size = artifact["size"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise CandidateError(f"build manifest artifact {name} has invalid size")
        result[name] = artifact
        ordered_names.append(name)
    if ordered_names != sorted(ordered_names):
        raise CandidateError("build manifest artifacts must be sorted by name")
    return result


def _assert_release_ready_macos(payload: dict[str, Any]) -> None:
    platforms = payload.get("platforms")
    if not isinstance(platforms, dict):
        raise CandidateError("build manifest platforms must be an object")
    macos = platforms.get("macos")
    if not isinstance(macos, dict):
        raise CandidateError("build manifest must contain macOS release evidence")
    required_values: dict[str, object] = {
        "architecture": "arm64",
        "minimum_macos": "14.0",
        "bundle_id": "com.opswitness.app",
    }
    for key, expected in required_values.items():
        if macos.get(key) != expected:
            raise CandidateError(f"macOS release evidence requires {key}={expected}")
    signing = macos.get("signing")
    notarization = macos.get("notarization")
    if not isinstance(signing, dict) or not isinstance(notarization, dict):
        raise CandidateError("macOS release evidence requires signing and notarization")
    signing_values: dict[str, object] = {
        "mode": "developer-id",
        "hardened_runtime": True,
        "nested_code_verified": True,
        "app_sandbox": False,
    }
    for key, expected in signing_values.items():
        if signing.get(key) != expected:
            raise CandidateError(f"macOS signing evidence requires {key}={expected}")
    if not isinstance(signing.get("identity"), str) or not signing["identity"]:
        raise CandidateError("macOS signing evidence requires identity")
    if not isinstance(signing.get("cdhash"), str) or not signing["cdhash"]:
        raise CandidateError("macOS signing evidence requires cdhash")
    notarization_values: dict[str, object] = {
        "status": "Accepted",
        "stapled": True,
        "gatekeeper_assessment": "accepted",
    }
    for key, expected in notarization_values.items():
        if notarization.get(key) != expected:
            raise CandidateError(f"macOS notarization evidence requires {key}={expected}")
    if not isinstance(notarization.get("request_id"), str) or not notarization["request_id"]:
        raise CandidateError("macOS notarization evidence requires request_id")


def _assert_closed_dist(
    dist: Path,
    *,
    artifacts: dict[str, dict[str, Any]],
    checksums: dict[str, str],
) -> None:
    try:
        entries = list(dist.iterdir())
    except OSError as exc:
        raise CandidateError(f"candidate dist is unreadable: {dist}") from exc
    expected_names = set(artifacts) | {"SHA256SUMS", "build-manifest.json"}
    actual_names = {entry.name for entry in entries}
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        unexpected = sorted(actual_names - expected_names)
        detail: list[str] = []
        if missing:
            detail.append(f"missing {', '.join(missing)}")
        if unexpected:
            detail.append(f"unexpected {', '.join(unexpected)}")
        raise CandidateError(f"candidate dist contents are invalid: {'; '.join(detail)}")
    if set(checksums) != set(artifacts):
        missing = sorted(set(artifacts) - set(checksums))
        unexpected = sorted(set(checksums) - set(artifacts))
        detail = []
        if missing:
            detail.append(f"missing checksums for {', '.join(missing)}")
        if unexpected:
            detail.append(f"unexpected checksums for {', '.join(unexpected)}")
        raise CandidateError(f"SHA256SUMS does not match manifest: {'; '.join(detail)}")
    for name, artifact in artifacts.items():
        path = dist / name
        if path.is_symlink() or not path.is_file():
            raise CandidateError(f"candidate asset must be a regular non-symlink file: {name}")
        actual_size = path.stat().st_size
        if actual_size != artifact["size"]:
            raise CandidateError(f"candidate asset size mismatch: {name}")
        actual_digest = sha256(path)
        if actual_digest != artifact["sha256"]:
            raise CandidateError(f"candidate asset manifest hash mismatch: {name}")
        if actual_digest != checksums[name]:
            raise CandidateError(f"candidate asset SHA256SUMS mismatch: {name}")
    for name in ("SHA256SUMS", "build-manifest.json"):
        path = dist / name
        if path.is_symlink() or not path.is_file():
            raise CandidateError(f"candidate metadata must be a regular non-symlink file: {name}")


def verify_candidate(
    *,
    dist: Path,
    expected_workflow_run_id: int | str,
    expected_workflow_run_attempt: int | str,
    expected_commit: str,
    expected_tag: str,
    expected_dmg_sha256: str,
    expected_manifest_sha256: str,
) -> CandidateBinding:
    """Verify a complete candidate dist and return its immutable binding."""

    if dist.is_symlink():
        raise CandidateError(f"candidate dist must not be a symlink: {dist}")
    dist = dist.resolve()
    if not dist.is_dir():
        raise CandidateError(f"candidate dist is not a directory: {dist}")
    run_id = _positive_integer(
        expected_workflow_run_id,
        label="expected candidate workflow run id",
    )
    run_attempt = _positive_integer(
        expected_workflow_run_attempt,
        label="expected candidate workflow run attempt",
    )
    commit = _expected_commit(expected_commit)
    dmg_sha256 = _expected_sha256(
        expected_dmg_sha256,
        label="expected DMG SHA-256",
    )
    manifest_sha256 = _expected_sha256(
        expected_manifest_sha256,
        label="expected manifest SHA-256",
    )
    if not isinstance(expected_tag, str) or not expected_tag:
        raise CandidateError("expected tag must be non-empty")

    manifest_path = dist / "build-manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise CandidateError("candidate build-manifest.json is missing or is a symlink")
    if sha256(manifest_path) != manifest_sha256:
        raise CandidateError("candidate build-manifest.json hash mismatch")
    manifest, _ = _read_json_object(manifest_path, label="build manifest")
    schema_version = manifest.get("schema_version")
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise CandidateError("build manifest schema_version must be the integer 3")
    if schema_version != 3:
        raise CandidateError("build manifest must use schema_version 3")
    if manifest.get("release_ready") is not True:
        raise CandidateError("build manifest is not release_ready")
    if manifest.get("git_commit") != commit:
        raise CandidateError("build manifest commit does not match expected candidate")
    if manifest.get("tag") != expected_tag:
        raise CandidateError("build manifest tag does not match expected candidate")
    created_at = _parse_aware_datetime(
        manifest.get("created_at"),
        label="build manifest created_at",
    ).astimezone(timezone.utc)
    if created_at > datetime.now(timezone.utc):
        raise CandidateError("build manifest created_at cannot be in the future")

    candidate = manifest.get("candidate")
    if not isinstance(candidate, dict):
        raise CandidateError("build manifest must contain candidate workflow identity")
    _require_exact_keys(
        candidate,
        {"workflow_run_id", "workflow_run_attempt"},
        label="build manifest candidate",
    )
    if (
        _positive_integer(
            candidate["workflow_run_id"],
            label="build manifest candidate workflow run id",
        )
        != run_id
    ):
        raise CandidateError("build manifest candidate workflow run id mismatch")
    if (
        _positive_integer(
            candidate["workflow_run_attempt"],
            label="build manifest candidate workflow run attempt",
        )
        != run_attempt
    ):
        raise CandidateError("build manifest candidate workflow run attempt mismatch")

    _assert_release_ready_macos(manifest)
    artifacts = _manifest_artifacts(manifest)
    checksums_path = dist / "SHA256SUMS"
    if checksums_path.is_symlink() or not checksums_path.is_file():
        raise CandidateError("candidate SHA256SUMS is missing or is a symlink")
    checksums = _parse_checksums(checksums_path)
    _assert_closed_dist(dist, artifacts=artifacts, checksums=checksums)
    dmgs = [artifact for artifact in artifacts.values() if artifact["kind"] == "macos_dmg"]
    if len(dmgs) != 1:
        raise CandidateError("build manifest must contain exactly one macos_dmg artifact")
    if dmgs[0]["sha256"] != dmg_sha256:
        raise CandidateError("candidate DMG hash does not match expected candidate")
    return CandidateBinding(
        workflow_run_id=run_id,
        workflow_run_attempt=run_attempt,
        git_commit=commit,
        tag=expected_tag,
        dmg_sha256=dmg_sha256,
        manifest_sha256=manifest_sha256,
        created_at_utc=created_at,
    )


def _parse_aware_datetime(value: object, *, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise CandidateError(f"{label} must be a timezone-aware RFC 3339 timestamp")
    normalized = f"{value[:-1]}+00:00" if value.endswith(("Z", "z")) else value
    try:
        result = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CandidateError(f"{label} must be a timezone-aware RFC 3339 timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise CandidateError(f"{label} must include a timezone offset")
    return result


def _utc_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _verified_window(started_at: str, completed_at: str) -> tuple[str, str, int]:
    started = _parse_aware_datetime(started_at, label="canary started_at")
    completed = _parse_aware_datetime(completed_at, label="canary completed_at")
    duration = completed.astimezone(timezone.utc) - started.astimezone(timezone.utc)
    if duration < MIN_CANARY_DURATION or duration > MAX_CANARY_DURATION:
        raise CandidateError("canary window must be between 24 and 48 hours inclusive")
    seconds = duration.total_seconds()
    if not seconds.is_integer():
        raise CandidateError("canary window must use whole-second timestamps")
    return _utc_timestamp(started), _utc_timestamp(completed), int(seconds)


def _normalized_utc_timestamp(value: object, *, label: str) -> datetime:
    parsed = _parse_aware_datetime(value, label=label)
    normalized = _utc_timestamp(parsed)
    if value != normalized:
        raise CandidateError(f"{label} must be normalized to UTC")
    return parsed.astimezone(timezone.utc)


def _evidence_id(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not EVIDENCE_ID_PATTERN.fullmatch(value):
        raise CandidateError(f"{label} must be a safe non-empty evidence identifier")
    return value


def _nonnegative_integer(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CandidateError(f"{label} must be a non-negative integer")
    return value


def _require_boolean(value: object, *, expected: bool, label: str) -> None:
    if not isinstance(value, bool) or value is not expected:
        raise CandidateError(f"{label} must be {str(expected).lower()}")


def _verify_candidate_payload(
    payload: object,
    *,
    binding: CandidateBinding,
    label: str,
) -> None:
    if not isinstance(payload, dict):
        raise CandidateError(f"{label} must be an object")
    _require_exact_keys(
        payload,
        {
            "workflow_run_id",
            "workflow_run_attempt",
            "git_commit",
            "tag",
            "dmg_sha256",
            "manifest_sha256",
        },
        label=label,
    )
    if (
        _positive_integer(
            payload["workflow_run_id"],
            label=f"{label} workflow run id",
        )
        != binding.workflow_run_id
        or _positive_integer(
            payload["workflow_run_attempt"],
            label=f"{label} workflow run attempt",
        )
        != binding.workflow_run_attempt
        or not isinstance(payload["git_commit"], str)
        or payload["git_commit"] != binding.git_commit
        or not isinstance(payload["tag"], str)
        or payload["tag"] != binding.tag
        or not isinstance(payload["dmg_sha256"], str)
        or payload["dmg_sha256"] != binding.dmg_sha256
        or not isinstance(payload["manifest_sha256"], str)
        or payload["manifest_sha256"] != binding.manifest_sha256
    ):
        raise CandidateError(f"{label} is bound to a different candidate")


def _verify_observation_bundle(bundle: Path) -> dict[str, Path]:
    if bundle.is_symlink() or not bundle.is_dir():
        raise CandidateError("canary observation bundle must be a regular directory")
    expected_entries = {
        OBSERVATION_FILE,
        "sources",
        *EXPECTED_SOURCE_FILES.values(),
    }
    actual_entries: set[str] = set()
    try:
        for entry in bundle.rglob("*"):
            actual_entries.add(entry.relative_to(bundle).as_posix())
    except OSError as exc:
        raise CandidateError("canary observation bundle is unreadable") from exc
    if actual_entries != expected_entries:
        missing = sorted(expected_entries - actual_entries)
        unexpected = sorted(actual_entries - expected_entries)
        detail: list[str] = []
        if missing:
            detail.append(f"missing {', '.join(missing)}")
        if unexpected:
            detail.append(f"unexpected {', '.join(unexpected)}")
        raise CandidateError(
            f"canary observation bundle contents are invalid: {'; '.join(detail)}"
        )
    sources_dir = bundle / "sources"
    if sources_dir.is_symlink() or not sources_dir.is_dir():
        raise CandidateError("canary observation sources must be a regular directory")
    observation_path = bundle / OBSERVATION_FILE
    if observation_path.is_symlink() or not observation_path.is_file():
        raise CandidateError("canary observation is missing or is a symlink")
    source_paths: dict[str, Path] = {}
    for name, relative in EXPECTED_SOURCE_FILES.items():
        source_path = bundle / relative
        if source_path.is_symlink() or not source_path.is_file():
            raise CandidateError(f"canary source {name} is missing or is a symlink")
        source_paths[name] = source_path
    return source_paths


def _verify_source_payload(
    source: dict[str, Any],
    *,
    name: str,
    check: dict[str, Any],
    binding: CandidateBinding,
    observation_id: str,
) -> None:
    _require_exact_keys(
        source,
        {
            "schema_version",
            "evidence_type",
            "candidate",
            "observation_run_id",
            "captured_at",
            "authority",
            "evidence",
        },
        label=f"canary check {name} source",
    )
    schema_version = source["schema_version"]
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != SOURCE_SCHEMA_VERSION
    ):
        raise CandidateError(f"canary check {name} source schema_version is unsupported")
    if source["evidence_type"] != EXPECTED_SOURCE_TYPES[name]:
        raise CandidateError(f"canary check {name} source evidence_type is unsupported")
    _verify_candidate_payload(
        source["candidate"],
        binding=binding,
        label=f"canary check {name} source candidate",
    )
    if source["observation_run_id"] != observation_id:
        raise CandidateError(f"canary check {name} source run ID mismatch")
    if source["captured_at"] != check["captured_at"]:
        raise CandidateError(f"canary check {name} source captured_at mismatch")
    _normalized_utc_timestamp(
        source["captured_at"],
        label=f"canary check {name} source captured_at",
    )
    if source["authority"] != check["authority"]:
        raise CandidateError(f"canary check {name} source authority mismatch")
    evidence = source["evidence"]
    if not isinstance(evidence, dict):
        raise CandidateError(f"canary check {name} source evidence must be an object")


def _verify_source_document(
    *,
    source_path: Path,
    name: str,
    check: dict[str, Any],
    binding: CandidateBinding,
    observation_id: str,
) -> dict[str, Any]:
    if sha256(source_path) != check["source_sha256"]:
        raise CandidateError(f"canary check {name} source hash mismatch")
    source, raw = _read_json_object(
        source_path,
        label=f"canary check {name} source",
    )
    if raw != canonical_json_bytes(source):
        raise CandidateError(f"canary check {name} source JSON is not canonical")
    _verify_source_payload(
        source,
        name=name,
        check=check,
        binding=binding,
        observation_id=observation_id,
    )
    return source


def _check_details(
    checks: dict[str, Any],
    *,
    name: str,
    started: datetime,
) -> dict[str, Any]:
    check = checks[name]
    if not isinstance(check, dict):
        raise CandidateError(f"canary check {name} must be an object")
    _require_exact_keys(
        check,
        {
            "authority",
            "format",
            "source_file",
            "source_sha256",
            "captured_at",
            "status",
            "details",
        },
        label=f"canary check {name}",
    )
    if check["authority"] != EXPECTED_CHECK_AUTHORITIES[name]:
        raise CandidateError(f"canary check {name} has unsupported authority")
    if (
        not isinstance(check["format"], str)
        or check["format"] not in {"json", "log_summary"}
    ):
        raise CandidateError(f"canary check {name} has unsupported source format")
    if check["source_file"] != EXPECTED_SOURCE_FILES[name]:
        raise CandidateError(f"canary check {name} source file is invalid")
    _expected_sha256(
        check["source_sha256"],
        label=f"canary check {name} source SHA-256",
    )
    captured = _normalized_utc_timestamp(
        check["captured_at"],
        label=f"canary check {name} captured_at",
    )
    if captured < started:
        raise CandidateError(f"canary check {name} was captured before the canary")
    if captured > datetime.now(timezone.utc):
        raise CandidateError(f"canary check {name} captured_at cannot be in the future")
    if check["status"] != "passed":
        raise CandidateError(f"canary check must explicitly pass: {name}")
    details = check["details"]
    if not isinstance(details, dict):
        raise CandidateError(f"canary check {name} details must be an object")
    return details


def _verify_soak_check(
    details: dict[str, Any],
    *,
    duration_seconds: int,
) -> None:
    _require_exact_keys(
        details,
        {
            "contract_id",
            "state",
            "minimum_duration_seconds",
            "maximum_duration_seconds",
            "observed_duration_seconds",
            "continuous",
            "blocker_codes",
            "ledger_tail_sha256",
        },
        label="canary soak details",
    )
    _evidence_id(details["contract_id"], label="canary soak contract_id")
    if details["state"] != "passed":
        raise CandidateError("canary soak state must be passed")
    if details["minimum_duration_seconds"] != int(MIN_CANARY_DURATION.total_seconds()):
        raise CandidateError("canary soak minimum must be exactly 24 hours")
    if details["maximum_duration_seconds"] != int(MAX_CANARY_DURATION.total_seconds()):
        raise CandidateError("canary soak maximum must be exactly 48 hours")
    if details["observed_duration_seconds"] != duration_seconds:
        raise CandidateError("canary soak duration must match the observation window")
    _require_boolean(
        details["continuous"],
        expected=True,
        label="canary soak continuous",
    )
    if details["blocker_codes"] != []:
        raise CandidateError("canary soak blocker_codes must be empty")
    _expected_sha256(
        details["ledger_tail_sha256"],
        label="canary soak ledger tail SHA-256",
    )


def _verify_cadence_check(
    details: dict[str, Any],
    *,
    started: datetime,
    completed: datetime,
) -> None:
    _require_exact_keys(
        details,
        {
            "expected_interval_seconds",
            "grace_seconds",
            "successful_runs",
            "failed_runs",
            "first_success_at",
            "last_success_at",
            "max_gap_seconds",
            "event_stream_sha256",
        },
        label="canary cadence details",
    )
    expected_interval = _positive_integer(
        details["expected_interval_seconds"],
        label="canary cadence expected interval",
    )
    grace = _nonnegative_integer(
        details["grace_seconds"],
        label="canary cadence grace",
    )
    successful_runs = _positive_integer(
        details["successful_runs"],
        label="canary cadence successful runs",
    )
    if successful_runs < 2:
        raise CandidateError("canary cadence requires at least two successful runs")
    if _nonnegative_integer(
        details["failed_runs"],
        label="canary cadence failed runs",
    ):
        raise CandidateError("canary cadence failed_runs must be zero")
    first_success = _normalized_utc_timestamp(
        details["first_success_at"],
        label="canary cadence first_success_at",
    )
    last_success = _normalized_utc_timestamp(
        details["last_success_at"],
        label="canary cadence last_success_at",
    )
    if not started <= first_success <= last_success <= completed:
        raise CandidateError("canary cadence successes must fall inside the canary window")
    permitted_gap = expected_interval + grace
    max_gap = _nonnegative_integer(
        details["max_gap_seconds"],
        label="canary cadence max gap",
    )
    if max_gap > permitted_gap:
        raise CandidateError("canary cadence max gap exceeds interval plus frozen grace")
    if (first_success - started).total_seconds() > permitted_gap:
        raise CandidateError("canary cadence has an uncovered leading boundary")
    if (completed - last_success).total_seconds() > permitted_gap:
        raise CandidateError("canary cadence has an uncovered trailing boundary")
    _expected_sha256(
        details["event_stream_sha256"],
        label="canary cadence event stream SHA-256",
    )


def _verify_recovery_check(details: dict[str, Any]) -> None:
    _require_exact_keys(
        details,
        {
            "scenario",
            "original_run_id",
            "recovered_run_id",
            "instance_id",
            "duplicate_dispatch_count",
            "unknown_process_stop_count",
            "ledger_reconciled",
            "artifact_reverified",
            "recovery_event_sha256",
        },
        label="canary recovery details",
    )
    if details["scenario"] != "active-work-crash-restart-reconcile":
        raise CandidateError("canary recovery scenario is unsupported")
    original_run_id = _evidence_id(
        details["original_run_id"],
        label="canary recovery original_run_id",
    )
    recovered_run_id = _evidence_id(
        details["recovered_run_id"],
        label="canary recovery recovered_run_id",
    )
    if recovered_run_id != original_run_id:
        raise CandidateError("canary recovery must reconcile the original run ID")
    _evidence_id(details["instance_id"], label="canary recovery instance_id")
    if _nonnegative_integer(
        details["duplicate_dispatch_count"],
        label="canary recovery duplicate dispatch count",
    ):
        raise CandidateError("canary recovery duplicate_dispatch_count must be zero")
    if _nonnegative_integer(
        details["unknown_process_stop_count"],
        label="canary recovery unknown process stop count",
    ):
        raise CandidateError("canary recovery unknown_process_stop_count must be zero")
    _require_boolean(
        details["ledger_reconciled"],
        expected=True,
        label="canary recovery ledger_reconciled",
    )
    _require_boolean(
        details["artifact_reverified"],
        expected=True,
        label="canary recovery artifact_reverified",
    )
    _expected_sha256(
        details["recovery_event_sha256"],
        label="canary recovery event SHA-256",
    )


def _verify_clean_install_check(
    details: dict[str, Any],
    *,
    binding: CandidateBinding,
) -> None:
    _require_exact_keys(
        details,
        {
            "os_version",
            "architecture",
            "dmg_sha256",
            "manifest_sha256",
            "clean_home",
            "preinstalled_runtimes",
            "gatekeeper_assessment",
            "notary_ticket_verified",
            "loopback_only",
            "runtime_chain",
        },
        label="canary clean install details",
    )
    version = details["os_version"]
    if not isinstance(version, str) or not MACOS_VERSION_PATTERN.fullmatch(version):
        raise CandidateError("canary clean install os_version is invalid")
    if int(version.split(".", maxsplit=1)[0]) < 14:
        raise CandidateError("canary clean install requires macOS 14 or newer")
    if details["architecture"] != "arm64":
        raise CandidateError("canary clean install requires arm64")
    if details["dmg_sha256"] != binding.dmg_sha256:
        raise CandidateError("canary clean install DMG hash mismatch")
    if details["manifest_sha256"] != binding.manifest_sha256:
        raise CandidateError("canary clean install manifest hash mismatch")
    _require_boolean(
        details["clean_home"],
        expected=True,
        label="canary clean install clean_home",
    )
    if details["preinstalled_runtimes"] != []:
        raise CandidateError("canary clean install must have no preinstalled runtimes")
    if details["gatekeeper_assessment"] != "accepted":
        raise CandidateError("canary clean install Gatekeeper assessment must be accepted")
    _require_boolean(
        details["notary_ticket_verified"],
        expected=True,
        label="canary clean install notary_ticket_verified",
    )
    _require_boolean(
        details["loopback_only"],
        expected=True,
        label="canary clean install loopback_only",
    )
    if details["runtime_chain"] != EXPECTED_RUNTIME_CHAIN:
        raise CandidateError("canary clean install runtime chain is incomplete")


def _verify_first_work_check(
    details: dict[str, Any],
    *,
    binding: CandidateBinding,
) -> None:
    _require_exact_keys(
        details,
        {
            "work_id",
            "run_id",
            "dmg_sha256",
            "manifest_sha256",
            "codex_login_completed",
            "workspace_was_blank",
            "user_files_read",
            "external_side_effects",
            "explicit_write_approvals",
            "first_work_artifact_sha256",
            "verification_artifact_sha256",
            "verified_artifact_sha256",
            "cas_reverified",
            "artifact_digest_match",
            "business_result_claimed",
            "ledger_tail_sha256",
        },
        label="canary first Work details",
    )
    _evidence_id(details["work_id"], label="canary first Work work_id")
    _evidence_id(details["run_id"], label="canary first Work run_id")
    if details["dmg_sha256"] != binding.dmg_sha256:
        raise CandidateError("canary first Work DMG hash mismatch")
    if details["manifest_sha256"] != binding.manifest_sha256:
        raise CandidateError("canary first Work manifest hash mismatch")
    for key in (
        "codex_login_completed",
        "workspace_was_blank",
        "cas_reverified",
        "artifact_digest_match",
    ):
        _require_boolean(
            details[key],
            expected=True,
            label=f"canary first Work {key}",
        )
    for key in ("user_files_read", "external_side_effects", "business_result_claimed"):
        _require_boolean(
            details[key],
            expected=False,
            label=f"canary first Work {key}",
        )
    if details["explicit_write_approvals"] != 2:
        raise CandidateError(
            "canary first Work must record exactly two explicit write approvals"
        )
    first_work_sha256 = _expected_sha256(
        details["first_work_artifact_sha256"],
        label="canary first Work artifact SHA-256",
    )
    _expected_sha256(
        details["verification_artifact_sha256"],
        label="canary first Work verification SHA-256",
    )
    verified_sha256 = _expected_sha256(
        details["verified_artifact_sha256"],
        label="canary first Work verified artifact SHA-256",
    )
    if verified_sha256 != first_work_sha256:
        raise CandidateError("canary first Work verifier digest does not match the artifact")
    _expected_sha256(
        details["ledger_tail_sha256"],
        label="canary first Work ledger tail SHA-256",
    )


def _finite_number(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CandidateError(f"{label} must be a finite number")
    return float(value)


def _verify_soak_source(
    evidence: dict[str, Any],
    *,
    soak_details: dict[str, Any],
    cadence_details: dict[str, Any],
    started: datetime,
    completed: datetime,
    duration_seconds: int,
) -> None:
    _require_exact_keys(
        evidence,
        {"status", "ledger_tail_sha256"},
        label="canary soak source evidence",
    )
    ledger_tail_sha256 = _expected_sha256(
        evidence["ledger_tail_sha256"],
        label="canary soak source ledger tail SHA-256",
    )
    if ledger_tail_sha256 != soak_details["ledger_tail_sha256"]:
        raise CandidateError("canary soak source ledger tail digest mismatch")
    status = evidence["status"]
    if not isinstance(status, dict):
        raise CandidateError("canary soak source status must be an object")
    _require_exact_keys(
        status,
        {
            "schema_version",
            "name",
            "state",
            "healthy",
            "contract_event_id",
            "contract_kind",
            "evidence_since",
            "checked_at",
            "minimum_seconds",
            "elapsed_seconds",
            "remaining_seconds",
            "anchor_run_id",
            "projection_backlog",
            "jobs",
            "blockers",
        },
        label="canary soak source status",
    )
    if status["schema_version"] != 1 or isinstance(status["schema_version"], bool):
        raise CandidateError("canary soak source status schema_version is unsupported")
    if status["name"] != soak_details["contract_id"]:
        raise CandidateError("canary soak source contract ID mismatch")
    if status["state"] != "passed" or status["state"] != soak_details["state"]:
        raise CandidateError("canary soak source status must be passed")
    _require_boolean(
        status["healthy"],
        expected=True,
        label="canary soak source healthy",
    )
    _evidence_id(
        status["contract_event_id"],
        label="canary soak source contract event ID",
    )
    if status["contract_kind"] not in {"soak_started", "soak_reset"}:
        raise CandidateError("canary soak source contract kind is unsupported")
    evidence_since = _parse_aware_datetime(
        status["evidence_since"],
        label="canary soak source evidence_since",
    ).astimezone(timezone.utc)
    checked_at = _parse_aware_datetime(
        status["checked_at"],
        label="canary soak source checked_at",
    ).astimezone(timezone.utc)
    if evidence_since != started or checked_at != completed:
        raise CandidateError("canary soak source window mismatch")
    if (
        isinstance(status["minimum_seconds"], bool)
        or status["minimum_seconds"] != soak_details["minimum_duration_seconds"]
    ):
        raise CandidateError("canary soak source minimum duration mismatch")
    elapsed_seconds = _finite_number(
        status["elapsed_seconds"],
        label="canary soak source elapsed_seconds",
    )
    if elapsed_seconds != duration_seconds:
        raise CandidateError("canary soak source elapsed duration mismatch")
    if _finite_number(
        status["remaining_seconds"],
        label="canary soak source remaining_seconds",
    ):
        raise CandidateError("canary soak source remaining_seconds must be zero")
    anchor_run_id = status["anchor_run_id"]
    if anchor_run_id is not None:
        _evidence_id(anchor_run_id, label="canary soak source anchor_run_id")
    if _nonnegative_integer(
        status["projection_backlog"],
        label="canary soak source projection backlog",
    ):
        raise CandidateError("canary soak source projection backlog must be zero")
    if status["blockers"] != [] or soak_details["blocker_codes"] != []:
        raise CandidateError("canary soak source blockers must be empty")
    jobs = status["jobs"]
    if not isinstance(jobs, dict) or not jobs:
        raise CandidateError("canary soak source jobs must be a non-empty object")
    total_successes = 0
    permitted_gap = (
        cadence_details["expected_interval_seconds"] + cadence_details["grace_seconds"]
    )
    for job_name, job in jobs.items():
        _evidence_id(job_name, label="canary soak source job name")
        if not isinstance(job, dict):
            raise CandidateError(f"canary soak source job {job_name} must be an object")
        _require_exact_keys(
            job,
            {
                "starts",
                "successes",
                "failures",
                "running",
                "last_started",
                "max_gap_seconds",
                "allowed_gap_seconds",
            },
            label=f"canary soak source job {job_name}",
        )
        starts = _positive_integer(
            job["starts"],
            label=f"canary soak source job {job_name} starts",
        )
        successes = _positive_integer(
            job["successes"],
            label=f"canary soak source job {job_name} successes",
        )
        if starts < successes:
            raise CandidateError(
                f"canary soak source job {job_name} has more successes than starts"
            )
        if _nonnegative_integer(
            job["failures"],
            label=f"canary soak source job {job_name} failures",
        ):
            raise CandidateError(f"canary soak source job {job_name} failures must be zero")
        if _nonnegative_integer(
            job["running"],
            label=f"canary soak source job {job_name} running",
        ):
            raise CandidateError(f"canary soak source job {job_name} must be quiescent")
        last_started = _parse_aware_datetime(
            job["last_started"],
            label=f"canary soak source job {job_name} last_started",
        ).astimezone(timezone.utc)
        if not started <= last_started <= completed:
            raise CandidateError(
                f"canary soak source job {job_name} last_started is outside the window"
            )
        max_gap = _finite_number(
            job["max_gap_seconds"],
            label=f"canary soak source job {job_name} max gap",
        )
        allowed_gap = _finite_number(
            job["allowed_gap_seconds"],
            label=f"canary soak source job {job_name} allowed gap",
        )
        if max_gap > allowed_gap:
            raise CandidateError(f"canary soak source job {job_name} has a cadence gap")
        if allowed_gap != permitted_gap:
            raise CandidateError(
                f"canary soak source job {job_name} frozen cadence mismatch"
            )
        total_successes += successes
    if total_successes != cadence_details["successful_runs"]:
        raise CandidateError("canary soak source success count mismatches cadence evidence")


def _verify_summary_source(
    evidence: dict[str, Any],
    *,
    name: str,
    details: dict[str, Any],
) -> None:
    if name == "cadence":
        _require_exact_keys(
            evidence,
            {"contract_id", "ledger_tail_sha256", "details"},
            label="canary cadence source evidence",
        )
        _evidence_id(
            evidence["contract_id"],
            label="canary cadence source contract_id",
        )
        _expected_sha256(
            evidence["ledger_tail_sha256"],
            label="canary cadence source ledger tail SHA-256",
        )
    else:
        _require_exact_keys(
            evidence,
            {"details"},
            label=f"canary check {name} source evidence",
        )
    if evidence["details"] != details:
        raise CandidateError(f"canary check {name} source details mismatch")


def _verified_checks(
    checks: object,
    *,
    binding: CandidateBinding,
    started: datetime,
    completed: datetime,
    duration_seconds: int,
    observation_id: str,
    source_paths: dict[str, Path] | None = None,
    sealed_sources: object | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(checks, dict):
        raise CandidateError("canary checks must be an object")
    if set(checks) != EXPECTED_CHECKS:
        raise CandidateError("canary checks must contain exactly the required evidence")
    if (source_paths is None) == (sealed_sources is None):
        raise CandidateError("canary sources must have exactly one verification input")
    details = {
        name: _check_details(checks, name=name, started=started)
        for name in sorted(EXPECTED_CHECKS)
    }
    if source_paths is not None:
        sources = {
            name: _verify_source_document(
                source_path=source_paths[name],
                name=name,
                check=checks[name],
                binding=binding,
                observation_id=observation_id,
            )
            for name in sorted(EXPECTED_CHECKS)
        }
    else:
        if not isinstance(sealed_sources, dict):
            raise CandidateError("sealed canary sources must be an object")
        if set(sealed_sources) != EXPECTED_CHECKS:
            raise CandidateError("sealed canary sources must contain exactly five files")
        sources = {}
        for name in sorted(EXPECTED_CHECKS):
            source = sealed_sources[name]
            if not isinstance(source, dict):
                raise CandidateError(f"sealed canary source {name} must be an object")
            if sha256_bytes(canonical_json_bytes(source)) != checks[name]["source_sha256"]:
                raise CandidateError(f"sealed canary source {name} hash mismatch")
            _verify_source_payload(
                source,
                name=name,
                check=checks[name],
                binding=binding,
                observation_id=observation_id,
            )
            sources[name] = source
    source_evidence = {name: sources[name]["evidence"] for name in sources}
    _verify_soak_check(details["soak"], duration_seconds=duration_seconds)
    _verify_cadence_check(
        details["cadence"],
        started=started,
        completed=completed,
    )
    _verify_recovery_check(details["recovery"])
    _verify_clean_install_check(details["clean_install"], binding=binding)
    _verify_first_work_check(details["first_work"], binding=binding)
    _verify_soak_source(
        source_evidence["soak"],
        soak_details=details["soak"],
        cadence_details=details["cadence"],
        started=started,
        completed=completed,
        duration_seconds=duration_seconds,
    )
    for name in ("cadence", "recovery", "clean_install", "first_work"):
        _verify_summary_source(
            source_evidence[name],
            name=name,
            details=details[name],
        )
    cadence_source = source_evidence["cadence"]
    if cadence_source["contract_id"] != details["soak"]["contract_id"]:
        raise CandidateError("canary cadence source contract ID mismatches soak")
    if cadence_source["ledger_tail_sha256"] != details["soak"]["ledger_tail_sha256"]:
        raise CandidateError("canary cadence source ledger tail mismatches soak")
    return (
        {name: checks[name] for name in sorted(EXPECTED_CHECKS)},
        {name: sources[name] for name in sorted(EXPECTED_CHECKS)},
    )


def _verify_observation(
    *,
    observation_bundle: Path,
    expected_observation_sha256: str,
    binding: CandidateBinding,
    expected_observation_workflow_run_id: int | str,
    expected_observation_workflow_run_attempt: int | str,
    expected_host_identity_sha256: str,
) -> tuple[dict[str, object], dict[str, Any], dict[str, Any]]:
    observation_sha256 = _expected_sha256(
        expected_observation_sha256,
        label="expected canary observation SHA-256",
    )
    source_paths = _verify_observation_bundle(observation_bundle)
    observation_path = observation_bundle / OBSERVATION_FILE
    if sha256(observation_path) != observation_sha256:
        raise CandidateError("canary observation hash mismatch")
    observation, raw = _read_json_object(
        observation_path,
        label="canary observation",
    )
    if raw != canonical_json_bytes(observation):
        raise CandidateError("canary observation JSON is not canonical")
    _require_exact_keys(
        observation,
        {"schema_version", "evidence_type", "candidate", "run", "checks"},
        label="canary observation",
    )
    observation_schema_version = observation["schema_version"]
    if (
        isinstance(observation_schema_version, bool)
        or not isinstance(observation_schema_version, int)
        or observation_schema_version != CANARY_OBSERVATION_SCHEMA_VERSION
    ):
        raise CandidateError("canary observation schema_version is unsupported")
    if observation["evidence_type"] != CANARY_OBSERVATION_TYPE:
        raise CandidateError("canary observation evidence_type is unsupported")
    _verify_candidate_payload(
        observation["candidate"],
        binding=binding,
        label="canary observation candidate",
    )
    run = observation["run"]
    if not isinstance(run, dict):
        raise CandidateError("canary observation run must be an object")
    _require_exact_keys(
        run,
        {
            "id",
            "producer_workflow_run_id",
            "producer_workflow_run_attempt",
            "started_at",
            "completed_at",
            "host_identity_sha256",
        },
        label="canary observation run",
    )
    producer_run_id = _positive_integer(
        run["producer_workflow_run_id"],
        label="canary observation producer workflow run id",
    )
    producer_run_attempt = _positive_integer(
        run["producer_workflow_run_attempt"],
        label="canary observation producer workflow run attempt",
    )
    expected_run_id = _positive_integer(
        expected_observation_workflow_run_id,
        label="expected observation workflow run id",
    )
    expected_run_attempt = _positive_integer(
        expected_observation_workflow_run_attempt,
        label="expected observation workflow run attempt",
    )
    if producer_run_id != expected_run_id:
        raise CandidateError("canary observation producer workflow run id mismatch")
    if producer_run_attempt != expected_run_attempt:
        raise CandidateError("canary observation producer workflow run attempt mismatch")
    observation_id = _evidence_id(run["id"], label="canary observation run id")
    started, completed, duration_seconds = _verified_window(
        run["started_at"],
        run["completed_at"],
    )
    if run["started_at"] != started or run["completed_at"] != completed:
        raise CandidateError("canary observation timestamps must be normalized to UTC")
    started_time = _parse_aware_datetime(started, label="canary observation started_at")
    completed_time = _parse_aware_datetime(completed, label="canary observation completed_at")
    if started_time.astimezone(timezone.utc) < binding.created_at_utc:
        raise CandidateError("canary observation predates the candidate manifest")
    if completed_time.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise CandidateError("canary observation completed_at cannot be in the future")
    host_identity_sha256 = _expected_sha256(
        run["host_identity_sha256"],
        label="canary observation host identity SHA-256",
    )
    expected_host_identity = _expected_sha256(
        expected_host_identity_sha256,
        label="expected canary host identity SHA-256",
    )
    if host_identity_sha256 != expected_host_identity:
        raise CandidateError("canary observation host identity mismatch")
    checks, sources = _verified_checks(
        observation["checks"],
        binding=binding,
        started=started_time.astimezone(timezone.utc),
        completed=completed_time.astimezone(timezone.utc),
        duration_seconds=duration_seconds,
        observation_id=observation_id,
        source_paths=source_paths,
    )
    canary: dict[str, object] = {
        "observation_workflow_run_id": producer_run_id,
        "observation_workflow_run_attempt": producer_run_attempt,
        "observation_sha256": observation_sha256,
        "run_id": observation_id,
        "host_identity_sha256": host_identity_sha256,
        "started_at": started,
        "completed_at": completed,
        "duration_seconds": duration_seconds,
    }
    return canary, checks, sources


def record_canary_evidence(
    *,
    binding: CandidateBinding,
    canary_workflow_run_id: int | str,
    canary_workflow_run_attempt: int | str,
    observation_bundle: Path,
    expected_observation_sha256: str,
    expected_observation_workflow_run_id: int | str,
    expected_observation_workflow_run_attempt: int | str,
    expected_host_identity_sha256: str,
    output: Path,
) -> dict[str, object]:
    """Verify authoritative observations and seal immutable candidate evidence."""

    run_id = _positive_integer(
        canary_workflow_run_id,
        label="canary workflow run id",
    )
    run_attempt = _positive_integer(
        canary_workflow_run_attempt,
        label="canary workflow run attempt",
    )
    canary, checks, sources = _verify_observation(
        observation_bundle=observation_bundle,
        expected_observation_sha256=expected_observation_sha256,
        binding=binding,
        expected_observation_workflow_run_id=expected_observation_workflow_run_id,
        expected_observation_workflow_run_attempt=(
            expected_observation_workflow_run_attempt
        ),
        expected_host_identity_sha256=expected_host_identity_sha256,
    )
    canary["workflow_run_id"] = run_id
    canary["workflow_run_attempt"] = run_attempt
    evidence: dict[str, object] = {
        "schema_version": CANARY_SCHEMA_VERSION,
        "evidence_type": CANARY_EVIDENCE_TYPE,
        "candidate": binding.as_dict(),
        "canary": canary,
        "checks": checks,
        "sources": sources,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or (output.exists() and not output.is_file()):
        raise CandidateError("canary evidence output must be a regular non-symlink file")
    output.write_bytes(canonical_json_bytes(evidence))
    return evidence


def _verify_canary_evidence(
    *,
    evidence_path: Path,
    expected_evidence_sha256: str,
    binding: CandidateBinding,
    expected_canary_workflow_run_id: int | str,
    expected_canary_workflow_run_attempt: int | str,
    expected_host_identity_sha256: str,
) -> dict[str, object]:
    evidence_sha256 = _expected_sha256(
        expected_evidence_sha256,
        label="expected canary evidence SHA-256",
    )
    if evidence_path.is_symlink() or not evidence_path.is_file():
        raise CandidateError("canary evidence is missing or is a symlink")
    if sha256(evidence_path) != evidence_sha256:
        raise CandidateError("canary evidence hash mismatch")
    evidence, raw = _read_json_object(evidence_path, label="canary evidence")
    if raw != canonical_json_bytes(evidence):
        raise CandidateError("canary evidence JSON is not canonical")
    _require_exact_keys(
        evidence,
        {"schema_version", "evidence_type", "candidate", "canary", "checks", "sources"},
        label="canary evidence",
    )
    schema_version = evidence["schema_version"]
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise CandidateError("canary evidence schema_version must be an integer")
    if schema_version != CANARY_SCHEMA_VERSION:
        raise CandidateError("canary evidence schema_version is unsupported")
    if evidence["evidence_type"] != CANARY_EVIDENCE_TYPE:
        raise CandidateError("canary evidence_type is unsupported")

    _verify_candidate_payload(
        evidence["candidate"],
        binding=binding,
        label="canary evidence candidate",
    )

    canary = evidence["canary"]
    if not isinstance(canary, dict):
        raise CandidateError("canary evidence canary must be an object")
    _require_exact_keys(
        canary,
        {
            "workflow_run_id",
            "workflow_run_attempt",
            "observation_workflow_run_id",
            "observation_workflow_run_attempt",
            "observation_sha256",
            "run_id",
            "host_identity_sha256",
            "started_at",
            "completed_at",
            "duration_seconds",
        },
        label="canary evidence canary",
    )
    expected_run_id = _positive_integer(
        expected_canary_workflow_run_id,
        label="expected canary workflow run id",
    )
    expected_run_attempt = _positive_integer(
        expected_canary_workflow_run_attempt,
        label="expected canary workflow run attempt",
    )
    canary_run_id = _positive_integer(
        canary["workflow_run_id"],
        label="canary evidence workflow run id",
    )
    canary_run_attempt = _positive_integer(
        canary["workflow_run_attempt"],
        label="canary evidence workflow run attempt",
    )
    if canary_run_id != expected_run_id:
        raise CandidateError("canary evidence workflow run id mismatch")
    if canary_run_attempt != expected_run_attempt:
        raise CandidateError("canary evidence workflow run attempt mismatch")
    _positive_integer(
        canary["observation_workflow_run_id"],
        label="canary evidence observation workflow run id",
    )
    _positive_integer(
        canary["observation_workflow_run_attempt"],
        label="canary evidence observation workflow run attempt",
    )
    _expected_sha256(
        canary["observation_sha256"],
        label="canary evidence observation SHA-256",
    )
    observation_id = _evidence_id(
        canary["run_id"],
        label="canary evidence run id",
    )
    host_identity_sha256 = _expected_sha256(
        canary["host_identity_sha256"],
        label="canary evidence host identity SHA-256",
    )
    expected_host_identity = _expected_sha256(
        expected_host_identity_sha256,
        label="expected canary host identity SHA-256",
    )
    if host_identity_sha256 != expected_host_identity:
        raise CandidateError("canary evidence host identity mismatch")
    started, completed, duration_seconds = _verified_window(
        canary["started_at"],
        canary["completed_at"],
    )
    if canary["started_at"] != started or canary["completed_at"] != completed:
        raise CandidateError("canary evidence timestamps are not normalized to UTC")
    started_time = _parse_aware_datetime(started, label="canary started_at")
    completed_time = _parse_aware_datetime(completed, label="canary completed_at")
    if started_time.astimezone(timezone.utc) < binding.created_at_utc:
        raise CandidateError("canary evidence predates the candidate manifest")
    if completed_time.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise CandidateError("canary evidence completed_at cannot be in the future")
    recorded_duration = canary["duration_seconds"]
    if (
        isinstance(recorded_duration, bool)
        or not isinstance(recorded_duration, int)
        or recorded_duration != duration_seconds
    ):
        raise CandidateError("canary evidence duration does not match its timestamps")

    _verified_checks(
        evidence["checks"],
        binding=binding,
        started=started_time.astimezone(timezone.utc),
        completed=completed_time.astimezone(timezone.utc),
        duration_seconds=duration_seconds,
        observation_id=observation_id,
        sealed_sources=evidence["sources"],
    )
    return evidence


def verify_promotion(
    *,
    dist: Path,
    expected_workflow_run_id: int | str,
    expected_workflow_run_attempt: int | str,
    expected_commit: str,
    expected_tag: str,
    expected_dmg_sha256: str,
    expected_manifest_sha256: str,
    evidence_path: Path,
    expected_canary_workflow_run_id: int | str,
    expected_canary_workflow_run_attempt: int | str,
    expected_evidence_sha256: str,
    expected_host_identity_sha256: str,
) -> CandidateBinding:
    """Verify that promotion uses the exact canaried candidate and evidence."""

    binding = verify_candidate(
        dist=dist,
        expected_workflow_run_id=expected_workflow_run_id,
        expected_workflow_run_attempt=expected_workflow_run_attempt,
        expected_commit=expected_commit,
        expected_tag=expected_tag,
        expected_dmg_sha256=expected_dmg_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
    )
    _verify_canary_evidence(
        evidence_path=evidence_path,
        expected_evidence_sha256=expected_evidence_sha256,
        binding=binding,
        expected_canary_workflow_run_id=expected_canary_workflow_run_id,
        expected_canary_workflow_run_attempt=expected_canary_workflow_run_attempt,
        expected_host_identity_sha256=expected_host_identity_sha256,
    )
    return binding


def _add_candidate_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--candidate-run-id", required=True)
    parser.add_argument("--candidate-run-attempt", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--dmg-sha256", required=True)
    parser.add_argument("--manifest-sha256", required=True)


def _binding_from_arguments(args: argparse.Namespace) -> CandidateBinding:
    return verify_candidate(
        dist=args.dist,
        expected_workflow_run_id=args.candidate_run_id,
        expected_workflow_run_attempt=args.candidate_run_attempt,
        expected_commit=args.commit,
        expected_tag=args.tag,
        expected_dmg_sha256=args.dmg_sha256,
        expected_manifest_sha256=args.manifest_sha256,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    verify = commands.add_parser("verify-candidate")
    _add_candidate_arguments(verify)

    record = commands.add_parser("record-canary")
    _add_candidate_arguments(record)
    record.add_argument("--canary-run-id", required=True)
    record.add_argument("--canary-run-attempt", required=True)
    record.add_argument("--observation-bundle", type=Path, required=True)
    record.add_argument("--observation-sha256", required=True)
    record.add_argument("--observation-run-id", required=True)
    record.add_argument("--observation-run-attempt", required=True)
    record.add_argument("--host-identity-sha256", required=True)
    record.add_argument("--output", type=Path, required=True)

    promote = commands.add_parser("verify-promotion")
    _add_candidate_arguments(promote)
    promote.add_argument("--evidence", type=Path, required=True)
    promote.add_argument("--canary-run-id", required=True)
    promote.add_argument("--canary-run-attempt", required=True)
    promote.add_argument("--evidence-sha256", required=True)
    promote.add_argument("--host-identity-sha256", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        binding = _binding_from_arguments(args)
        if args.command == "record-canary":
            record_canary_evidence(
                binding=binding,
                canary_workflow_run_id=args.canary_run_id,
                canary_workflow_run_attempt=args.canary_run_attempt,
                observation_bundle=args.observation_bundle,
                expected_observation_sha256=args.observation_sha256,
                expected_observation_workflow_run_id=args.observation_run_id,
                expected_observation_workflow_run_attempt=args.observation_run_attempt,
                expected_host_identity_sha256=args.host_identity_sha256,
                output=args.output,
            )
            print(f"canary evidence written: {args.output}")
        elif args.command == "verify-promotion":
            _verify_canary_evidence(
                evidence_path=args.evidence,
                expected_evidence_sha256=args.evidence_sha256,
                binding=binding,
                expected_canary_workflow_run_id=args.canary_run_id,
                expected_canary_workflow_run_attempt=args.canary_run_attempt,
                expected_host_identity_sha256=args.host_identity_sha256,
            )
            print("promotion candidate and canary evidence verified")
        else:
            print("release candidate verified")
    except (CandidateError, OSError) as exc:
        print(f"release candidate failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
