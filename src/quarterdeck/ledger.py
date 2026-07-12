"""Append-only JSONL outbox — the authoritative run ledger (ADR-0001 v2).

Write protocol invariants:
- ledger dir 0700, files 0600 — argv/log tails are sensitive;
- one event = one JSON line = one write() under an exclusive flock;
- files are opened O_APPEND; a torn tail (no trailing newline) is healed by prepending
  a newline before the next event, so a good event never merges into a torn one;
- readers hold a shared flock, so an in-flight write is never misread as torn;
- undecodable lines are quarantined to <file>.torn exactly once;
- ledger failures NEVER propagate to the caller's job — append() returns None on failure.

Global ordering: file append order under the exclusive lock IS the commit order.
The projector drains by (file date, line position); ULIDs are identities, not a clock.
"""

import fcntl
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quarterdeck.ids import new_ulid


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


class Ledger:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _file_for_today(self) -> Path:
        return self.root / f"{datetime.now(UTC):%Y-%m-%d}.jsonl"

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)

    def append(
        self,
        kind: str,
        run_id: str,
        payload: dict[str, Any],
        *,
        fsync: bool = False,
        degraded: bool = False,
    ) -> dict[str, Any] | None:
        """Durably append one event. Returns the event, or None if the write failed."""
        event: dict[str, Any] = {
            "event_id": new_ulid(),
            "ts": _utcnow(),
            "kind": kind,
            "run_id": run_id,
            "payload": payload,
        }
        if degraded:
            event["degraded"] = True
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        try:
            self._ensure_root()
            path = self._file_for_today()
            fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                os.chmod(path, 0o600)  # enforce even if the file predates this policy
                fcntl.flock(fd, fcntl.LOCK_EX)
                try:
                    # Heal a torn tail so this event starts on its own line.
                    size = os.fstat(fd).st_size
                    if size > 0:
                        with open(path, "rb") as check:
                            check.seek(size - 1)
                            if check.read(1) != b"\n":
                                os.write(fd, b"\n")
                    data = memoryview(line.encode())
                    while data:  # os.write may short-write
                        written = os.write(fd, data)
                        data = data[written:]
                    if fsync:
                        os.fsync(fd)
                finally:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
            return event
        except OSError:
            return None

    def read_events(self, path: Path) -> list[dict[str, Any]]:
        """Read one ledger file under a shared lock; quarantine bad lines exactly once."""
        events: list[dict[str, Any]] = []
        torn: list[str] = []
        try:
            with open(path, "rb") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    raw = f.read().decode(errors="replace")
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except OSError:
            return events
        for lineno, line in enumerate(raw.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                torn.append(f"{path.name}:{lineno}\t{line}")
        if torn:
            torn_path = path.with_suffix(path.suffix + ".torn")
            try:
                seen = torn_path.read_text().splitlines() if torn_path.exists() else []
                fresh = [t for t in torn if t not in seen]
                if fresh:
                    fd = os.open(torn_path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
                    try:
                        os.write(fd, ("\n".join(fresh) + "\n").encode())
                    finally:
                        os.close(fd)
            except OSError:
                pass
        return events

    def read_all(self) -> list[dict[str, Any]]:
        """All events in commit order: (file date asc, line position asc)."""
        events: list[dict[str, Any]] = []
        if not self.root.exists():
            return events
        for path in sorted(self.root.glob("*.jsonl")):
            events.extend(self.read_events(path))
        return events
