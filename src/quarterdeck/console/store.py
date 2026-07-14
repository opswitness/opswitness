"""Private crash-safe plan storage; the ledger stores transition hashes, not plan text."""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Callable, Sequence
from pathlib import Path

from quarterdeck.console.schemas import PlanRecord, utc_now
from quarterdeck.fsutil import atomic_write


class PlanNotFound(ValueError):
    pass


class PlanStore:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser()
        self.plans_dir = self.root / "plans"

    def _ensure(self) -> None:
        if self.root.is_symlink() or self.plans_dir.is_symlink():
            raise ValueError("console state directories must not be symlinks")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.plans_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        os.chmod(self.plans_dir, 0o700)

    def _path(self, plan_id: str) -> Path:
        if not plan_id or any(char not in "0123456789ABCDEFGHJKMNPQRSTVWXYZ" for char in plan_id):
            raise PlanNotFound("invalid plan id")
        return self.plans_dir / f"{plan_id}.json"

    def _lock_path(self, plan_id: str) -> Path:
        return self.plans_dir / f".{plan_id}.lock"

    def create(self, record: PlanRecord) -> PlanRecord:
        self._ensure()
        path = self._path(record.plan_id)
        if path.exists():
            raise ValueError(f"plan already exists: {record.plan_id}")
        atomic_write(path, self._encode(record), mode=0o600)
        return record

    def get(self, plan_id: str) -> PlanRecord:
        self._ensure()
        path = self._path(plan_id)
        try:
            if path.is_symlink():
                raise ValueError("plan record must not be a symlink")
            return PlanRecord.model_validate_json(path.read_text())
        except FileNotFoundError as exc:
            raise PlanNotFound(f"unknown plan: {plan_id}") from exc

    def list(self, limit: int = 50) -> list[PlanRecord]:
        self._ensure()
        rows: list[PlanRecord] = []
        for path in sorted(self.plans_dir.glob("*.json"), reverse=True):
            if path.is_symlink():
                continue
            try:
                rows.append(PlanRecord.model_validate_json(path.read_text()))
            except (OSError, ValueError):
                continue
            if len(rows) >= limit:
                break
        return rows

    def list_all(self) -> Sequence[PlanRecord]:
        """Return every durable plan record, failing closed on corruption."""
        self._ensure()
        rows: list[PlanRecord] = []
        for path in sorted(self.plans_dir.glob("*.json"), reverse=True):
            if path.is_symlink():
                raise ValueError("plan record must not be a symlink")
            rows.append(PlanRecord.model_validate_json(path.read_text()))
        return rows

    def mutate(self, plan_id: str, fn: Callable[[PlanRecord], PlanRecord]) -> PlanRecord:
        self._ensure()
        lock_path = self._lock_path(plan_id)
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            current = self.get(plan_id)
            updated = fn(current)
            updated.updated_at = utc_now()
            atomic_write(self._path(plan_id), self._encode(updated), mode=0o600)
            return updated
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @staticmethod
    def _encode(record: PlanRecord) -> bytes:
        return (
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
            + "\n"
        ).encode()
