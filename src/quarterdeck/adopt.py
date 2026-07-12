"""qd adopt — wrap launchd jobs under the ledger. Dry-run by default.

Doctrine: never mutate a plist without --apply; every apply keeps a .qd-bak backup
(first backup wins — it always holds the pristine pre-Quarterdeck state); rollback
restores it byte-identically. launchctl reload is printed, never executed.
"""

import difflib
import os
import plistlib
import shutil
import sys
from pathlib import Path
from typing import Any

from quarterdeck.fsutil import atomic_write as _atomic_write
from quarterdeck.fsutil import mode_of as _mode_of
from quarterdeck.fsutil import publish_no_clobber

BACKUP_SUFFIX = ".qd-bak"


def job_name_from_label(label: str) -> str:
    return label.rsplit(".", 1)[-1]


def resolve_qd_bin(explicit: str = "") -> str:
    """Resolve qd to a verified absolute executable — launchd has no cwd/PATH to lean on."""
    candidate = explicit or shutil.which("qd") or sys.argv[0]
    p = Path(candidate).expanduser()
    if not p.is_absolute():
        p = p.resolve()
    if not (p.is_file() and os.access(p, os.X_OK)):
        raise ValueError(
            f"cannot resolve qd to an absolute executable (got {candidate!r}); "
            f"pass --qd-bin /abs/path/to/qd"
        )
    return str(p)


def collisions(entries: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Short job names claimed by more than one label — adoption must fail closed on these."""
    by_job: dict[str, list[str]] = {}
    for e in entries:
        if "job" in e and "label" in e:
            by_job.setdefault(e["job"], []).append(e["label"])
    return {job: labels for job, labels in by_job.items() if len(labels) > 1}


def _publish_backup(backup: Path, pristine: bytes, mode: int) -> None:
    """Atomically publish the pristine backup, no-clobber (first backup always wins)."""
    publish_no_clobber(backup, pristine, mode)


def _load(plist_path: Path) -> dict[str, Any]:
    with open(plist_path, "rb") as f:
        return plistlib.load(f)


def _command_of(data: dict[str, Any]) -> list[str] | None:
    if isinstance(data.get("ProgramArguments"), list):
        return [str(a) for a in data["ProgramArguments"]]
    if data.get("Program"):
        return [str(data["Program"])]
    return None


def is_wrapped(data: dict[str, Any]) -> bool:
    cmd = _command_of(data) or []
    return any(part.endswith("qd") for part in cmd[:1]) and "wrap" in cmd[:3]


def scan(dir_path: Path) -> list[dict[str, Any]]:
    """Inventory launchd plists: schedule + command + wrapped state. Read-only."""
    entries = []
    for plist in sorted(dir_path.glob("*.plist")):
        try:
            data = _load(plist)
        except Exception as exc:  # unparseable plist: report, don't die
            entries.append({"path": str(plist), "error": str(exc)})
            continue
        label = str(data.get("Label", plist.stem))
        entry: dict[str, Any] = {
            "path": str(plist),
            "label": label,
            "job": job_name_from_label(label),
            "command": _command_of(data),
            "wrapped": is_wrapped(data),
        }
        if "StartInterval" in data:
            entry["expected_interval_seconds"] = int(data["StartInterval"])
        if "StartCalendarInterval" in data:
            entry["calendar"] = data["StartCalendarInterval"]
        entries.append(entry)
    return entries


def plan(plist_path: Path, qd_bin: str, job: str) -> tuple[bytes, bytes, str] | None:
    """Compute the wrapped plist. Returns (old, new, unified_diff) or None if already wrapped."""
    data = _load(plist_path)
    if is_wrapped(data):
        return None
    original_cmd = _command_of(data)
    if not original_cmd:
        raise ValueError(f"{plist_path}: no Program/ProgramArguments")
    old_bytes = plist_path.read_bytes()
    data["ProgramArguments"] = [qd_bin, "wrap", "--job", job, "--", *original_cmd]
    data.pop("Program", None)
    new_bytes = plistlib.dumps(data)
    diff = "\n".join(
        difflib.unified_diff(
            plistlib.dumps(plistlib.loads(old_bytes)).decode().splitlines(),
            new_bytes.decode().splitlines(),
            fromfile=str(plist_path),
            tofile=f"{plist_path} (wrapped)",
            lineterm="",
        )
    )
    return old_bytes, new_bytes, diff


def apply(plist_path: Path, new_bytes: bytes) -> Path:
    """Atomically write the wrapped plist, preserving the pristine backup.

    Backup uses exclusive create (first backup wins — it always holds the
    pre-Quarterdeck original); the plist write is temp+fsync+rename. Caller
    reloads launchd.
    """
    backup = plist_path.with_suffix(plist_path.suffix + BACKUP_SUFFIX)
    pristine = plist_path.read_bytes()
    mode = _mode_of(plist_path)
    _publish_backup(backup, pristine, mode)
    _atomic_write(plist_path, new_bytes, mode=mode)
    return backup


def rollback(plist_path: Path) -> bool:
    backup = plist_path.with_suffix(plist_path.suffix + BACKUP_SUFFIX)
    if not backup.exists():
        return False
    _atomic_write(plist_path, backup.read_bytes())
    return True
