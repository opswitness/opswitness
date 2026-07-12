"""qd adopt — wrap launchd jobs under the ledger. Dry-run by default.

Doctrine: never mutate a plist without --apply; every apply keeps a .qd-bak backup
(first backup wins — it always holds the pristine pre-Quarterdeck state); rollback
restores it byte-identically. launchctl reload is printed, never executed.
"""

import difflib
import plistlib
import shutil
from pathlib import Path
from typing import Any

BACKUP_SUFFIX = ".qd-bak"


def job_name_from_label(label: str) -> str:
    return label.rsplit(".", 1)[-1]


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
    """Write the wrapped plist, preserving the pristine backup. Caller reloads launchd."""
    backup = plist_path.with_suffix(plist_path.suffix + BACKUP_SUFFIX)
    if not backup.exists():  # first backup wins: always the pre-Quarterdeck original
        shutil.copy2(plist_path, backup)
    plist_path.write_bytes(new_bytes)
    return backup


def rollback(plist_path: Path) -> bool:
    backup = plist_path.with_suffix(plist_path.suffix + BACKUP_SUFFIX)
    if not backup.exists():
        return False
    plist_path.write_bytes(backup.read_bytes())
    return True
