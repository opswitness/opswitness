"""Append-only JSONL outbox — the authoritative run ledger (ADR-0001 v2).

Write protocol invariants:
- one event = one JSON line = one write() under an exclusive flock;
- files are opened O_APPEND; a torn tail (no trailing newline) is healed by prepending
  a newline before the next event, so a good event never merges into a torn one;
- readers quarantine undecodable lines to <file>.torn and keep going;
- ledger failures NEVER propagate to the caller's job — append() returns None on failure
  and the caller decides how to alert.
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
            self.root.mkdir(parents=True, exist_ok=True)
            path = self._file_for_today()
            with open(path, "ab") as f:  # 'a' => O_APPEND
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    # Heal a torn tail so this event starts on its own line.
                    if f.tell() > 0:
                        with open(path, "rb") as check:
                            check.seek(-1, os.SEEK_END)
                            if check.read(1) != b"\n":
                                f.write(b"\n")
                    f.write(line.encode())
                    f.flush()
                    if fsync:
                        os.fsync(f.fileno())
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            return event
        except OSError:
            return None

    def read_events(self, path: Path) -> list[dict[str, Any]]:
        """Read one ledger file; quarantine undecodable lines to <file>.torn."""
        events: list[dict[str, Any]] = []
        torn: list[str] = []
        try:
            raw = path.read_text(errors="replace")
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
            try:
                with open(path.with_suffix(path.suffix + ".torn"), "a") as tf:
                    tf.write("\n".join(torn) + "\n")
            except OSError:
                pass
        return events

    def read_all(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        if not self.root.exists():
            return events
        for path in sorted(self.root.glob("*.jsonl")):
            events.extend(self.read_events(path))
        return events
