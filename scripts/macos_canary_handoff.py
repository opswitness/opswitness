#!/usr/bin/env python3
"""Prepare a private, host-bound handoff for Alpha canary observations."""

from __future__ import annotations

import argparse
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Sequence


SHARED_ROOT = Path("/Users/Shared")
HANDOFF_ROOT = SHARED_ROOT / "OpsWitnessAlphaCanary"
HOST_IDENTITY_FILE = Path(
    "/Library/Application Support/OpsWitnessCanary/host-identity.sha256"
)
SHA256_RE = re.compile(r"[0-9a-f]{64}")


class HandoffError(RuntimeError):
    """Raised when the local canary host trust boundary is not exact."""


def _permission_field(path: Path) -> str:
    try:
        completed = subprocess.run(
            ["/bin/ls", "-lde", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise HandoffError(f"cannot inspect ACLs for {path}") from exc
    first_line = completed.stdout.splitlines()
    if not first_line:
        raise HandoffError(f"cannot inspect permissions for {path}")
    fields = first_line[0].split()
    if not fields:
        raise HandoffError(f"cannot inspect permissions for {path}")
    return fields[0]


def _without_xattr_marker(permission_field: str) -> str:
    if permission_field.endswith("@"):
        return permission_field[:-1]
    return permission_field


def _lstat(path: Path) -> os.stat_result:
    try:
        return path.lstat()
    except OSError as exc:
        raise HandoffError(f"cannot inspect {path}") from exc


def _validate_directory(
    path: Path,
    *,
    expected_uid: int,
    expected_gid: int | None,
    expected_mode: int,
) -> None:
    metadata = _lstat(path)
    if not stat.S_ISDIR(metadata.st_mode):
        raise HandoffError(f"{path} must be a real directory, not a link or file")
    if metadata.st_uid != expected_uid:
        raise HandoffError(f"{path} has an unexpected owner")
    if expected_gid is not None and metadata.st_gid != expected_gid:
        raise HandoffError(f"{path} has an unexpected group")
    if stat.S_IMODE(metadata.st_mode) != expected_mode:
        raise HandoffError(f"{path} has unsafe permissions")
    expected_permissions = stat.filemode(stat.S_IFDIR | expected_mode)
    if _without_xattr_marker(_permission_field(path)) != expected_permissions:
        raise HandoffError(f"{path} has an ACL or unexpected permission metadata")


def _validate_identity_file(
    path: Path,
    *,
    expected_uid: int,
    expected_identity_sha256: str,
) -> str:
    metadata = _lstat(path)
    if not stat.S_ISREG(metadata.st_mode):
        raise HandoffError("canary host identity marker must be a regular file")
    if metadata.st_uid != expected_uid:
        raise HandoffError("canary host identity marker has an unexpected owner")
    if stat.S_IMODE(metadata.st_mode) != 0o444:
        raise HandoffError("canary host identity marker must have mode 0444")
    if _without_xattr_marker(_permission_field(path)) != "-r--r--r--":
        raise HandoffError("canary host identity marker has an ACL")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise HandoffError("cannot read canary host identity marker") from exc
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    try:
        identity = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise HandoffError("canary host identity marker is not ASCII") from exc
    if not SHA256_RE.fullmatch(identity):
        raise HandoffError("canary host identity marker must contain one SHA-256")
    if identity != expected_identity_sha256:
        raise HandoffError("canary host identity does not match the protected value")
    return identity


def _ensure_private_directory(path: Path, *, uid: int) -> None:
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        pass
    except OSError as exc:
        raise HandoffError(f"cannot create {path}") from exc
    _validate_directory(
        path,
        expected_uid=uid,
        expected_gid=None,
        expected_mode=0o700,
    )


def prepare_handoff(
    *,
    shared_root: Path,
    handoff_root: Path,
    identity_file: Path,
    expected_host_identity_sha256: str,
    run_id: int,
    run_attempt: int,
    runner_uid: int,
    shared_uid: int = 0,
    shared_gid: int = 0,
    identity_uid: int = 0,
) -> Path:
    if (
        isinstance(run_id, bool)
        or not isinstance(run_id, int)
        or run_id <= 0
        or isinstance(run_attempt, bool)
        or not isinstance(run_attempt, int)
        or run_attempt <= 0
    ):
        raise HandoffError("workflow run identity must use positive integers")
    if not SHA256_RE.fullmatch(expected_host_identity_sha256):
        raise HandoffError("expected host identity must be a lowercase SHA-256")

    _validate_directory(
        shared_root,
        expected_uid=shared_uid,
        expected_gid=shared_gid,
        expected_mode=0o1777,
    )
    _validate_directory(
        identity_file.parent,
        expected_uid=identity_uid,
        expected_gid=None,
        expected_mode=0o755,
    )
    _validate_identity_file(
        identity_file,
        expected_uid=identity_uid,
        expected_identity_sha256=expected_host_identity_sha256,
    )

    _ensure_private_directory(handoff_root, uid=runner_uid)
    requests = handoff_root / "requests"
    runs = handoff_root / "runs"
    _ensure_private_directory(requests, uid=runner_uid)
    _ensure_private_directory(runs, uid=runner_uid)

    run_key = f"{run_id}-{run_attempt}"
    run_root = runs / run_key
    if os.path.lexists(run_root):
        raise HandoffError("canary observation run handoff already exists")
    _ensure_private_directory(run_root, uid=runner_uid)
    request = requests / f"{run_key}.json"
    if os.path.lexists(request):
        raise HandoffError("canary observation export request already exists")
    return run_root


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--expected-host-identity-sha256", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.root != HANDOFF_ROOT:
            raise HandoffError(f"handoff root must be exactly {HANDOFF_ROOT}")
        run_root = prepare_handoff(
            shared_root=SHARED_ROOT,
            handoff_root=HANDOFF_ROOT,
            identity_file=HOST_IDENTITY_FILE,
            expected_host_identity_sha256=args.expected_host_identity_sha256,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            runner_uid=os.getuid(),
        )
    except HandoffError as exc:
        print(f"canary handoff failed: {exc}", file=sys.stderr)
        return 1
    print(run_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
