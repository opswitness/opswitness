"""Private crash-safe plan storage; the ledger stores transition hashes, not plan text."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from collections.abc import Callable, Sequence
from pathlib import Path

from opswitness.console.schemas import (
    PlanRecord,
    TaskTemplate,
    TeamBlueprint,
    WorkspaceMemoryVersion,
    utc_now,
)
from opswitness.fsutil import atomic_write


class PlanNotFound(ValueError):
    pass


class BlueprintNotFound(ValueError):
    pass


class TaskTemplateNotFound(ValueError):
    pass


class WorkspaceMemoryNotFound(ValueError):
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


class WorkspaceMemoryStore:
    """Immutable Markdown memory versions with private machine-readable metadata."""

    BODY_MARKER = "<!-- opswitness-memory-body -->\n"

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser() / "workspace-memory"
        self.vault_dir = self.root / "vault"
        self.metadata_dir = self.root / ".opswitness" / "versions"

    def _ensure(self) -> None:
        for path in (self.root, self.vault_dir, self.metadata_dir):
            if path.is_symlink():
                raise ValueError("workspace memory directories must not be symlinks")
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(path, 0o700)

    def _metadata_path(self, version_id: str) -> Path:
        self._validate_id(version_id)
        return self.metadata_dir / f"{version_id}.json"

    def _document_path(self, version: WorkspaceMemoryVersion) -> Path:
        self._validate_id(version.memory_id)
        self._validate_id(version.version_id)
        return (
            self.vault_dir
            / version.kind
            / version.memory_id
            / f"v{version.version_number:04d}-{version.version_id}.md"
        )

    @staticmethod
    def _validate_id(value: str) -> None:
        if not value or any(char not in "0123456789ABCDEFGHJKMNPQRSTVWXYZ" for char in value):
            raise WorkspaceMemoryNotFound("invalid workspace memory id")

    @classmethod
    def render_document(cls, version: WorkspaceMemoryVersion, content: str) -> bytes:
        def quoted(value: str) -> str:
            return json.dumps(value, ensure_ascii=False)

        lines = [
            "---",
            "opswitness_schema: 1",
            f"memory_id: {quoted(version.memory_id)}",
            f"version_id: {quoted(version.version_id)}",
            f"version_number: {version.version_number}",
            f"kind: {quoted(version.kind)}",
            f"title: {quoted(version.title)}",
            f"created_at: {quoted(version.created_at)}",
            f"content_sha256: {quoted(version.content_sha256)}",
        ]
        if version.tags:
            lines.append("tags:")
            lines.extend(f"  - {quoted(tag)}" for tag in version.tags)
        else:
            lines.append("tags: []")
        if version.workspace:
            lines.append(f"workspace: {quoted(version.workspace)}")
        if version.source_plan_id:
            lines.append(f"source_plan_id: {quoted(version.source_plan_id)}")
        if version.source_plan_sha256:
            lines.append(f"source_plan_sha256: {quoted(version.source_plan_sha256)}")
        if version.parent_version_id:
            lines.append(f"parent_version_id: {quoted(version.parent_version_id)}")
        lines.extend(
            [
                "---",
                "",
                f"# {version.title}",
                "",
                cls.BODY_MARKER.rstrip("\n"),
                content.rstrip(),
                "",
            ]
        )
        return "\n".join(lines).encode()

    def relative_document_path(self, version: WorkspaceMemoryVersion) -> str:
        return str(self._document_path(version).relative_to(self.root))

    def discard_uncommitted(self, version: WorkspaceMemoryVersion) -> None:
        """Remove a version only when its immutable bytes still match the caller's record."""
        metadata_path = self._metadata_path(version.version_id)
        document_path = self._document_path(version)
        if metadata_path.exists():
            stored = WorkspaceMemoryVersion.model_validate_json(metadata_path.read_text())
            if stored != version:
                raise ValueError("workspace memory metadata changed during rollback")
        if document_path.exists():
            document = document_path.read_bytes()
            if hashlib.sha256(document).hexdigest() != version.document_sha256:
                raise ValueError("workspace memory document changed during rollback")
        metadata_path.unlink(missing_ok=True)
        document_path.unlink(missing_ok=True)

    def create(self, version: WorkspaceMemoryVersion, content: str) -> WorkspaceMemoryVersion:
        self._ensure()
        metadata_path = self._metadata_path(version.version_id)
        document_path = self._document_path(version)
        if metadata_path.exists() or document_path.exists():
            raise ValueError(f"workspace memory version already exists: {version.version_id}")
        document = self.render_document(version, content)
        if hashlib.sha256(document).hexdigest() != version.document_sha256:
            raise ValueError("workspace memory document hash does not match")
        document_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(document_path.parent, 0o700)
        atomic_write(document_path, document, mode=0o600)
        atomic_write(
            metadata_path,
            (
                json.dumps(
                    version.model_dump(mode="json"),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode(),
            mode=0o600,
        )
        return version

    def get(self, version_id: str) -> tuple[WorkspaceMemoryVersion, str]:
        self._ensure()
        metadata_path = self._metadata_path(version_id)
        try:
            if metadata_path.is_symlink():
                raise ValueError("workspace memory metadata must not be a symlink")
            version = WorkspaceMemoryVersion.model_validate_json(metadata_path.read_text())
            document_path = self._document_path(version)
            if document_path.is_symlink():
                raise ValueError("workspace memory document must not be a symlink")
            document = document_path.read_bytes()
        except FileNotFoundError as exc:
            raise WorkspaceMemoryNotFound(f"unknown workspace memory version: {version_id}") from exc
        if hashlib.sha256(document).hexdigest() != version.document_sha256:
            raise ValueError("workspace memory document integrity failed")
        marker = self.BODY_MARKER.encode()
        if marker not in document:
            raise ValueError("workspace memory body marker is missing")
        content = document.split(marker, 1)[1].decode().rstrip()
        if hashlib.sha256(content.encode()).hexdigest() != version.content_sha256:
            raise ValueError("workspace memory content integrity failed")
        return version, content

    def list_versions(self) -> list[WorkspaceMemoryVersion]:
        self._ensure()
        rows: list[WorkspaceMemoryVersion] = []
        for path in sorted(self.metadata_dir.glob("*.json")):
            if path.is_symlink():
                raise ValueError("workspace memory metadata must not be a symlink")
            rows.append(WorkspaceMemoryVersion.model_validate_json(path.read_text()))
        return rows
