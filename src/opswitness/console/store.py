"""Private crash-safe plan storage; the ledger stores transition hashes, not plan text."""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Callable, Sequence
from pathlib import Path

from opswitness.console.schemas import PlanRecord, TaskTemplate, TeamBlueprint, utc_now
from opswitness.fsutil import atomic_write


class PlanNotFound(ValueError):
    pass


class BlueprintNotFound(ValueError):
    pass


class TaskTemplateNotFound(ValueError):
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

    def list(
        self,
        limit: int = 50,
        *,
        exclude_ids: set[str] | None = None,
    ) -> list[PlanRecord]:
        self._ensure()
        excluded = exclude_ids or set()
        rows: list[PlanRecord] = []
        for path in sorted(self.plans_dir.glob("*.json"), reverse=True):
            if path.stem in excluded:
                continue
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


class TeamBlueprintStore:
    """Private immutable topology snapshots with only an archive state transition."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser()
        self.blueprints_dir = self.root / "team-blueprints"

    def _ensure(self) -> None:
        if self.root.is_symlink() or self.blueprints_dir.is_symlink():
            raise ValueError("console state directories must not be symlinks")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.blueprints_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        os.chmod(self.blueprints_dir, 0o700)

    def _path(self, blueprint_id: str) -> Path:
        if not blueprint_id or any(
            char not in "0123456789ABCDEFGHJKMNPQRSTVWXYZ" for char in blueprint_id
        ):
            raise BlueprintNotFound("invalid team blueprint id")
        return self.blueprints_dir / f"{blueprint_id}.json"

    def _lock_path(self, blueprint_id: str) -> Path:
        return self.blueprints_dir / f".{blueprint_id}.lock"

    def create(self, blueprint: TeamBlueprint) -> TeamBlueprint:
        self._ensure()
        path = self._path(blueprint.blueprint_id)
        if path.exists():
            raise ValueError(f"team blueprint already exists: {blueprint.blueprint_id}")
        atomic_write(path, self._encode(blueprint), mode=0o600)
        return blueprint

    def get(self, blueprint_id: str) -> TeamBlueprint:
        self._ensure()
        path = self._path(blueprint_id)
        try:
            if path.is_symlink():
                raise ValueError("team blueprint must not be a symlink")
            return TeamBlueprint.model_validate_json(path.read_text())
        except FileNotFoundError as exc:
            raise BlueprintNotFound(f"unknown team blueprint: {blueprint_id}") from exc

    def list(self, limit: int = 50, *, include_archived: bool = False) -> list[TeamBlueprint]:
        self._ensure()
        rows: list[TeamBlueprint] = []
        for path in sorted(self.blueprints_dir.glob("*.json"), reverse=True):
            if path.is_symlink():
                continue
            try:
                blueprint = TeamBlueprint.model_validate_json(path.read_text())
            except (OSError, ValueError):
                continue
            if not include_archived and blueprint.archived_at is not None:
                continue
            rows.append(blueprint)
            if len(rows) >= limit:
                break
        return rows

    def mutate(
        self,
        blueprint_id: str,
        fn: Callable[[TeamBlueprint], TeamBlueprint],
    ) -> TeamBlueprint:
        self._ensure()
        lock_path = self._lock_path(blueprint_id)
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            updated = fn(self.get(blueprint_id))
            atomic_write(self._path(blueprint_id), self._encode(updated), mode=0o600)
            return updated
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @staticmethod
    def _encode(blueprint: TeamBlueprint) -> bytes:
        return (
            json.dumps(
                blueprint.model_dump(mode="json"),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()


class TaskTemplateStore:
    """Private immutable task objectives with only an archive state transition."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser()
        self.templates_dir = self.root / "task-templates"

    def _ensure(self) -> None:
        if self.root.is_symlink() or self.templates_dir.is_symlink():
            raise ValueError("console state directories must not be symlinks")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.templates_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        os.chmod(self.templates_dir, 0o700)

    def _path(self, template_id: str) -> Path:
        if not template_id or any(
            char not in "0123456789ABCDEFGHJKMNPQRSTVWXYZ" for char in template_id
        ):
            raise TaskTemplateNotFound("invalid task template id")
        return self.templates_dir / f"{template_id}.json"

    def _lock_path(self, template_id: str) -> Path:
        return self.templates_dir / f".{template_id}.lock"

    def create(self, template: TaskTemplate) -> TaskTemplate:
        self._ensure()
        path = self._path(template.template_id)
        if path.exists():
            raise ValueError(f"task template already exists: {template.template_id}")
        atomic_write(path, self._encode(template), mode=0o600)
        return template

    def get(self, template_id: str) -> TaskTemplate:
        self._ensure()
        path = self._path(template_id)
        try:
            if path.is_symlink():
                raise ValueError("task template must not be a symlink")
            return TaskTemplate.model_validate_json(path.read_text())
        except FileNotFoundError as exc:
            raise TaskTemplateNotFound(f"unknown task template: {template_id}") from exc

    def list(self, limit: int = 100, *, include_archived: bool = False) -> list[TaskTemplate]:
        self._ensure()
        rows: list[TaskTemplate] = []
        for path in sorted(self.templates_dir.glob("*.json"), reverse=True):
            if path.is_symlink():
                continue
            try:
                template = TaskTemplate.model_validate_json(path.read_text())
            except (OSError, ValueError):
                continue
            if not include_archived and template.archived_at is not None:
                continue
            rows.append(template)
            if len(rows) >= limit:
                break
        return rows

    def mutate(
        self,
        template_id: str,
        fn: Callable[[TaskTemplate], TaskTemplate],
    ) -> TaskTemplate:
        self._ensure()
        lock_path = self._lock_path(template_id)
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            updated = fn(self.get(template_id))
            atomic_write(self._path(template_id), self._encode(updated), mode=0o600)
            return updated
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @staticmethod
    def _encode(template: TaskTemplate) -> bytes:
        return (
            json.dumps(
                template.model_dump(mode="json"),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
