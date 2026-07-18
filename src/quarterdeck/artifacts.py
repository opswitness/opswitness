"""Content-addressed artifact evidence backed by the append-only ledger."""

from __future__ import annotations

import hashlib
import mimetypes
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from quarterdeck.ledger import Ledger

ARTIFACT_KINDS = {"artifact_registered", "artifact_eval", "artifact_signoff"}


def artifact_root(ledger: Ledger) -> Path:
    return ledger.root.parent / "artifacts"


def cas_path(root: Path, digest: str) -> Path:
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("SHA-256 digest must be 64 lowercase hexadecimal characters")
    return root / "sha256" / digest[:2] / digest


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def verify_blob(root: Path, digest: str, expected_size: int | None = None) -> dict[str, Any]:
    path = cas_path(root, digest)
    if not path.is_file():
        return {"ok": False, "digest": digest, "reason": "missing", "path": str(path)}
    actual, size = _hash_file(path)
    ok = actual == digest and (expected_size is None or size == expected_size)
    return {
        "ok": ok,
        "digest": digest,
        "actual_digest": actual,
        "size": size,
        "reason": None if ok else "digest_or_size_mismatch",
        "path": str(path),
    }


def publish_blob(source: Path, root: Path) -> tuple[str, int, Path]:
    source = source.expanduser().resolve()
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    temp_dir = root / ".tmp"
    temp_dir.mkdir(mode=0o700, exist_ok=True)
    os.chmod(temp_dir, 0o700)
    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    temp_fd, temp_name = tempfile.mkstemp(prefix="blob-", dir=temp_dir)
    temp = Path(temp_name)
    digest = hashlib.sha256()
    size = 0
    try:
        before = os.fstat(source_fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"artifact source must be a regular file: {source}")
        while chunk := os.read(source_fd, 1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
            _write_all(temp_fd, chunk)
        after = os.fstat(source_fd)
        if (
            before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or size != after.st_size
        ):
            raise ValueError(f"artifact source changed while being captured: {source}")
        os.fsync(temp_fd)
        hex_digest = digest.hexdigest()
        target = cas_path(root, hex_digest)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(target.parent, 0o700)
        try:
            os.link(temp, target)
            os.chmod(target, 0o600)
            dir_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except FileExistsError:
            verified = verify_blob(root, hex_digest, size)
            if not verified["ok"]:
                raise ValueError(f"existing CAS blob is corrupt: {target}")
        return hex_digest, size, target
    finally:
        os.close(source_fd)
        os.close(temp_fd)
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _job_for_run(events: list[dict[str, Any]], run_id: str) -> str:
    for event in events:
        if event.get("run_id") == run_id and event.get("kind") in {
            "run_started",
            "run_finished",
        }:
            job = event.get("payload", {}).get("job")
            if isinstance(job, str) and job:
                return job
    raise ValueError(f"run_id is not known to the ledger: {run_id}")


def registration(events: list[dict[str, Any]], event_id: str) -> dict[str, Any]:
    for event in events:
        if event.get("event_id") == event_id and event.get("kind") == "artifact_registered":
            return event
    raise ValueError(f"artifact registration not found: {event_id}")


def register_artifact(
    ledger: Ledger,
    source: Path,
    *,
    run_id: str,
    logical_name: str,
    labels: list[str] | None = None,
    mime: str | None = None,
) -> dict[str, Any]:
    logical_name = logical_name.strip()
    if not logical_name or len(logical_name) > 256:
        raise ValueError("logical_name must contain 1-256 characters")
    events = ledger.read_all()
    job = _job_for_run(events, run_id)
    digest, size, _path = publish_blob(source, artifact_root(ledger))
    normalized_labels = sorted({label.strip() for label in labels or [] if label.strip()})
    if len(normalized_labels) > 50 or any(len(label) > 100 for label in normalized_labels):
        raise ValueError("artifact labels are limited to 50 values of 100 characters")
    mime = mime or mimetypes.guess_type(logical_name)[0] or "application/octet-stream"
    event = ledger.append(
        "artifact_registered",
        run_id,
        {
            "schema_version": 1,
            "job": job,
            "logical_name": logical_name,
            "sha256": digest,
            "size": size,
            "mime": mime,
            "labels": normalized_labels,
            "cas_uri": f"cas+sha256://{digest}",
        },
        fsync=True,
    )
    if event is None:
        raise OSError("could not durably record artifact registration")
    return event


def register_console_artifact(
    ledger: Ledger,
    source: Path,
    *,
    plan_id: str,
    logical_name: str,
    labels: list[str] | None = None,
    mime: str | None = None,
    paperclip_issue_id: str | None = None,
) -> dict[str, Any]:
    """Capture one console-run output without pretending it is a wrapped job run."""
    logical_name = logical_name.strip()
    if not logical_name or len(logical_name) > 256:
        raise ValueError("logical_name must contain 1-256 characters")
    normalized_labels = sorted({label.strip() for label in labels or [] if label.strip()})
    if len(normalized_labels) > 50 or any(len(label) > 100 for label in normalized_labels):
        raise ValueError("artifact labels are limited to 50 values of 100 characters")
    if paperclip_issue_id is not None and (
        not paperclip_issue_id.strip() or len(paperclip_issue_id) > 160
    ):
        raise ValueError("paperclip_issue_id must contain 1-160 characters")

    digest, size, _path = publish_blob(source, artifact_root(ledger))
    events = ledger.read_all()
    for existing_event in events:
        payload = existing_event.get("payload", {})
        if (
            existing_event.get("kind") == "artifact_registered"
            and existing_event.get("run_id") == plan_id
            and payload.get("logical_name") == logical_name
            and payload.get("sha256") == digest
        ):
            return existing_event

    selected_mime = mime or mimetypes.guess_type(logical_name)[0] or "application/octet-stream"
    recorded = ledger.append(
        "artifact_registered",
        plan_id,
        {
            "schema_version": 1,
            "job": f"console:{plan_id}",
            "plan_id": plan_id,
            "logical_name": logical_name,
            "sha256": digest,
            "size": size,
            "mime": selected_mime,
            "labels": normalized_labels,
            "cas_uri": f"cas+sha256://{digest}",
            "paperclip_issue_id": paperclip_issue_id,
        },
        fsync=True,
    )
    if recorded is None:
        raise OSError("could not durably record console artifact registration")
    return recorded


def evaluate_artifact(
    ledger: Ledger,
    artifact_event_id: str,
    *,
    verdict: str,
    evaluator: str,
    summary: str,
) -> dict[str, Any]:
    if verdict not in {"pass", "fail", "warn"}:
        raise ValueError("eval verdict must be pass, fail, or warn")
    source = registration(ledger.read_all(), artifact_event_id)
    if not evaluator.strip() or not summary.strip():
        raise ValueError("evaluator and summary are required")
    event = ledger.append(
        "artifact_eval",
        source["run_id"],
        {
            "schema_version": 1,
            "artifact_event_id": artifact_event_id,
            "job": source["payload"]["job"],
            "sha256": source["payload"]["sha256"],
            "verdict": verdict,
            "evaluator": evaluator.strip()[:256],
            "summary": summary.strip()[:2000],
        },
        fsync=True,
    )
    if event is None:
        raise OSError("could not durably record artifact eval")
    return event


def signoff_artifact(
    ledger: Ledger,
    artifact_event_id: str,
    *,
    decision: str,
    signed_by: str,
    note: str,
) -> dict[str, Any]:
    if decision not in {"approved", "changes_requested"}:
        raise ValueError("signoff decision must be approved or changes_requested")
    source = registration(ledger.read_all(), artifact_event_id)
    if not signed_by.strip() or not note.strip():
        raise ValueError("signed_by and note are required")
    event = ledger.append(
        "artifact_signoff",
        source["run_id"],
        {
            "schema_version": 1,
            "artifact_event_id": artifact_event_id,
            "job": source["payload"]["job"],
            "sha256": source["payload"]["sha256"],
            "decision": decision,
            "signed_by": signed_by.strip()[:256],
            "note": note.strip()[:2000],
        },
        fsync=True,
    )
    if event is None:
        raise OSError("could not durably record artifact signoff")
    return event


def artifact_records(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in events if event.get("kind") == "artifact_registered"]


def verify_registration(ledger: Ledger, event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload", {})
    result = verify_blob(artifact_root(ledger), str(payload.get("sha256")), payload.get("size"))
    result.update(
        {
            "event_id": event.get("event_id"),
            "run_id": event.get("run_id"),
            "logical_name": payload.get("logical_name"),
        }
    )
    return result
