"""Crash-safe, source-preserving first-use state for the local desktop console."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from opswitness.fsutil import atomic_write, fsync_dir, write_all
from opswitness.ids import new_ulid


REQUIRED_FREE_BYTES = 5 * 1024 * 1024 * 1024
_STATE_SCHEMA_VERSION = 2
_LEGACY_STATE_SCHEMA_VERSION = 1
_MANIFEST_SCHEMA_VERSION = 1


class OnboardingStateError(RuntimeError):
    """The durable first-use state cannot be trusted or updated safely."""


class LegacyImportError(ValueError):
    """A legacy source is unsafe or changed while it was copied."""


DiskUsage = Callable[[Path], Any]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


class OnboardingStore:
    """Own only desktop first-use metadata and immutable legacy import snapshots."""

    def __init__(
        self,
        state_dir: Path,
        *,
        app_support_dir: Path | None = None,
        home: Path | None = None,
        disk_usage: DiskUsage = shutil.disk_usage,
    ) -> None:
        self.state_dir = state_dir.expanduser()
        self.root = self.state_dir / "onboarding"
        configured_support = os.environ.get("OPSWITNESS_APP_SUPPORT_DIR")
        self.app_support_dir = (
            app_support_dir.expanduser()
            if app_support_dir is not None
            else Path(configured_support).expanduser()
            if configured_support
            else self.state_dir.parent
        )
        self.workspaces_dir = self.app_support_dir / "workspaces"
        self.home = (home or Path.home()).expanduser()
        self._disk_usage = disk_usage

    @property
    def state_path(self) -> Path:
        return self.root / "state.json"

    @property
    def lock_path(self) -> Path:
        return self.root / "state.lock"

    def _ensure_root(self) -> None:
        if self.state_dir.is_symlink() or self.root.is_symlink():
            raise OnboardingStateError("onboarding state directories must not be symlinks")
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.state_dir, 0o700)
        os.chmod(self.root, 0o700)

    def _default_state(self) -> dict[str, Any]:
        return {
            "schema_version": _STATE_SCHEMA_VERSION,
            "migration_choice": None,
            "import_id": None,
            "provider_choice": None,
            "first_work_plan_id": None,
            "failure": None,
            "updated_at": _now(),
        }

    def _read_state_unlocked(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return self._default_state()
        try:
            if self.state_path.is_symlink():
                raise OnboardingStateError("onboarding state must not be a symlink")
            if stat.S_IMODE(self.state_path.stat().st_mode) != 0o600:
                raise OnboardingStateError("onboarding state permissions are insecure")
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise OnboardingStateError("onboarding state is unreadable") from exc
        expected_v1 = {
            "schema_version",
            "migration_choice",
            "import_id",
            "first_work_plan_id",
            "failure",
            "updated_at",
        }
        expected_v2 = {*expected_v1, "provider_choice"}
        if not isinstance(payload, dict):
            raise OnboardingStateError("onboarding state has an invalid schema")
        schema_version = payload.get("schema_version")
        expected = (
            expected_v1
            if schema_version == _LEGACY_STATE_SCHEMA_VERSION
            else expected_v2
            if schema_version == _STATE_SCHEMA_VERSION
            else None
        )
        if expected is None:
            raise OnboardingStateError("onboarding state version is unsupported")
        if set(payload) != expected:
            raise OnboardingStateError("onboarding state has an invalid schema")
        if payload.get("migration_choice") not in {None, "fresh", "import"}:
            raise OnboardingStateError("onboarding migration choice is invalid")
        if schema_version == _STATE_SCHEMA_VERSION and payload.get("provider_choice") not in {
            None,
            "openai",
            "anthropic",
        }:
            raise OnboardingStateError("onboarding provider choice is invalid")
        for key in ("import_id", "first_work_plan_id"):
            value = payload.get(key)
            if value is not None and (
                not isinstance(value, str)
                or len(value) != 26
                or any(char not in "0123456789ABCDEFGHJKMNPQRSTVWXYZ" for char in value)
            ):
                raise OnboardingStateError(f"onboarding {key} is invalid")
        failure = payload.get("failure")
        if failure is not None and (
            not isinstance(failure, dict)
            or set(failure) != {"code", "detail", "retryable"}
            or not isinstance(failure.get("code"), str)
            or not isinstance(failure.get("detail"), str)
            or not isinstance(failure.get("retryable"), bool)
        ):
            raise OnboardingStateError("onboarding failure state is invalid")
        if not isinstance(payload.get("updated_at"), str):
            raise OnboardingStateError("onboarding update timestamp is invalid")
        return payload

    def read(self) -> dict[str, Any]:
        self._ensure_root()
        return self._read_state_unlocked()

    def _locked_update(self, update: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        self._ensure_root()
        fd = os.open(
            self.lock_path,
            os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            current = self._read_state_unlocked()
            changed = update(dict(current))
            changed["schema_version"] = _STATE_SCHEMA_VERSION
            changed.setdefault("provider_choice", None)
            changed["updated_at"] = _now()
            atomic_write(
                self.state_path,
                (
                    json.dumps(changed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    + "\n"
                ).encode(),
                mode=0o600,
            )
            return changed
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def set_failure(self, code: str, detail: str, *, retryable: bool) -> dict[str, Any]:
        return self._locked_update(
            lambda state: {
                **state,
                "failure": {
                    "code": code[:100],
                    "detail": detail[:500],
                    "retryable": retryable,
                },
            }
        )

    def clear_failure(self) -> dict[str, Any]:
        return self._locked_update(lambda state: {**state, "failure": None})

    def set_provider_choice(
        self,
        provider: str,
        *,
        allow_existing_first_work: bool = False,
    ) -> dict[str, Any]:
        if provider not in {"openai", "anthropic"}:
            raise ValueError("onboarding provider choice is invalid")

        def update(state: dict[str, Any]) -> dict[str, Any]:
            current = state.get("provider_choice")
            if current == provider:
                return state
            if state.get("first_work_plan_id") is not None and not (
                allow_existing_first_work and current is None
            ):
                raise OnboardingStateError(
                    "onboarding provider cannot change after the first Work exists"
                )
            if current is not None and allow_existing_first_work:
                raise OnboardingStateError(
                    "an inferred onboarding provider cannot replace an existing choice"
                )
            return {
                **state,
                "provider_choice": provider,
                "failure": None,
            }

        return self._locked_update(update)

    def set_first_work_plan_id(
        self,
        plan_id: str,
        *,
        replace_terminal: bool = False,
    ) -> dict[str, Any]:
        return self._locked_update(
            lambda state: {
                **state,
                "first_work_plan_id": (
                    plan_id
                    if replace_terminal
                    else state.get("first_work_plan_id") or plan_id
                ),
                "failure": None,
            }
        )

    def prepare_first_work_workspace(self, plan_id: str) -> Path:
        """Create one private, empty workspace whose identity is bound to the plan."""
        if (
            len(plan_id) != 26
            or any(char not in "0123456789ABCDEFGHJKMNPQRSTVWXYZ" for char in plan_id)
        ):
            raise ValueError("first Work plan id is invalid")
        if self.app_support_dir.is_symlink() or self.workspaces_dir.is_symlink():
            raise OnboardingStateError("desktop workspace directories must not be symlinks")
        self.app_support_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.workspaces_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.app_support_dir, 0o700)
        os.chmod(self.workspaces_dir, 0o700)
        workspace = self.workspaces_dir / f"my-first-evidence-work-{plan_id}"
        if workspace.is_symlink():
            raise OnboardingStateError("first Work workspace must not be a symlink")
        workspace.mkdir(mode=0o700, exist_ok=True)
        os.chmod(workspace, 0o700)
        if any(workspace.iterdir()):
            raise OnboardingStateError("first Work workspace is not empty")
        return workspace.resolve(strict=True)

    def _legacy_candidates(self) -> list[tuple[str, Path]]:
        candidates = [
            (
                "opswitness-config",
                Path(
                    os.environ.get(
                        "OPSWITNESS_LEGACY_CONFIG_DIR",
                        self.home / ".config" / "opswitness",
                    )
                ),
            ),
            (
                "opswitness-state",
                Path(
                    os.environ.get(
                        "OPSWITNESS_LEGACY_STATE_DIR",
                        self.home / ".local" / "state" / "opswitness",
                    )
                ),
            ),
            (
                "config",
                Path(os.environ.get("QD_CONFIG_DIR", self.home / ".config" / "quarterdeck")),
            ),
            (
                "state",
                Path(
                    os.environ.get(
                        "QD_STATE_DIR",
                        self.home / ".local" / "state" / "quarterdeck",
                    )
                ),
            ),
            ("logs", self.home / "Library" / "Logs" / "Quarterdeck"),
        ]
        seen: set[Path] = set()
        unique: list[tuple[str, Path]] = []
        for kind, candidate in candidates:
            normalized = candidate.expanduser().absolute()
            if normalized in seen:
                continue
            seen.add(normalized)
            unique.append((kind, normalized))
        return unique

    def legacy_sources(self) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        target = self.root.absolute()
        for kind, path in self._legacy_candidates():
            try:
                exists = path.exists()
                eligible = exists and path.is_dir() and not path.is_symlink()
                resolved = path.resolve(strict=True) if eligible else path.absolute()
                if eligible and (
                    _is_relative_to(target, resolved) or _is_relative_to(resolved, target)
                ):
                    eligible = False
                sources.append(
                    {
                        "kind": kind,
                        "path": str(path),
                        "eligible": eligible,
                    }
                )
            except OSError:
                sources.append({"kind": kind, "path": str(path), "eligible": False})
        return [source for source in sources if Path(source["path"]).exists()]

    def disk_status(self) -> dict[str, int | bool]:
        probe = self.app_support_dir
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        usage = self._disk_usage(probe)
        available = int(usage.free)
        return {
            "required_free_bytes": REQUIRED_FREE_BYTES,
            "available_free_bytes": available,
            "disk_ready": available >= REQUIRED_FREE_BYTES,
        }

    def choose_fresh(self) -> dict[str, Any]:
        def update(state: dict[str, Any]) -> dict[str, Any]:
            current = state.get("migration_choice")
            if current not in {None, "fresh"}:
                raise LegacyImportError("an import migration was already selected")
            return {
                **state,
                "migration_choice": "fresh",
                "import_id": None,
                "failure": None,
            }

        return self._locked_update(update)

    @staticmethod
    def _copy_regular_file(source: Path, destination: Path) -> dict[str, Any]:
        source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        destination_fd: int | None = None
        digest = hashlib.sha256()
        size = 0
        try:
            before = os.fstat(source_fd)
            if not stat.S_ISREG(before.st_mode):
                raise LegacyImportError(f"legacy source contains a non-regular file: {source}")
            destination_fd = os.open(
                destination,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            while chunk := os.read(source_fd, 1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
                write_all(destination_fd, chunk)
            after = os.fstat(source_fd)
            if (
                before.st_dev != after.st_dev
                or before.st_ino != after.st_ino
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or size != after.st_size
            ):
                raise LegacyImportError(f"legacy source changed during import: {source}")
            os.fchmod(destination_fd, 0o600)
            os.fsync(destination_fd)
            return {
                "size_bytes": size,
                "sha256": digest.hexdigest(),
                "source_mode": stat.S_IMODE(before.st_mode),
                "source_mtime_ns": before.st_mtime_ns,
            }
        finally:
            os.close(source_fd)
            if destination_fd is not None:
                os.close(destination_fd)

    def _copy_source(self, kind: str, source: Path, destination: Path) -> dict[str, Any]:
        if source.is_symlink() or not source.is_dir():
            raise LegacyImportError(f"legacy {kind} source is not a safe directory")
        resolved = source.resolve(strict=True)
        if _is_relative_to(self.root.resolve(), resolved):
            raise LegacyImportError("legacy source cannot contain onboarding state")
        destination.mkdir(mode=0o700)
        files: list[dict[str, Any]] = []
        for current, dir_names, file_names in os.walk(resolved, followlinks=False):
            current_path = Path(current)
            relative_dir = current_path.relative_to(resolved)
            target_dir = destination / relative_dir
            target_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(target_dir, 0o700)
            for directory_name in sorted(dir_names):
                directory = current_path / directory_name
                if directory.is_symlink():
                    raise LegacyImportError(
                        f"legacy source contains a symlink: {directory.relative_to(resolved)}"
                    )
            for file_name in sorted(file_names):
                source_file = current_path / file_name
                relative_file = source_file.relative_to(resolved)
                if source_file.is_symlink():
                    raise LegacyImportError(
                        f"legacy source contains a symlink: {relative_file}"
                    )
                destination_file = destination / relative_file
                destination_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                copied = self._copy_regular_file(source_file, destination_file)
                files.append({"relative_path": relative_file.as_posix(), **copied})
        return {
            "kind": kind,
            "source_path": str(source),
            "destination": kind,
            "files": files,
            "file_count": len(files),
            "size_bytes": sum(int(item["size_bytes"]) for item in files),
        }

    def import_legacy(self) -> dict[str, Any]:
        detected = self.legacy_sources()
        unsafe = [source for source in detected if source["eligible"] is not True]
        if unsafe:
            kinds = ", ".join(str(source["kind"]) for source in unsafe)
            raise LegacyImportError(f"unsafe legacy sources require manual review: {kinds}")
        sources = [
            (str(source["kind"]), Path(str(source["path"])))
            for source in detected
        ]
        if not sources:
            raise LegacyImportError("no eligible OpsWitness or Quarterdeck data was detected")
        disk = self.disk_status()
        if disk["disk_ready"] is not True:
            raise LegacyImportError("at least 5 GB of free space is required")

        def reserve(state: dict[str, Any]) -> dict[str, Any]:
            if state.get("migration_choice") == "import" and state.get("import_id"):
                return state
            if state.get("migration_choice") not in {None, "import"}:
                raise LegacyImportError("a fresh migration was already selected")
            return {**state, "failure": None}

        current = self._locked_update(reserve)
        if current.get("migration_choice") == "import" and current.get("import_id"):
            return current

        import_id = new_ulid()
        imports_root = self.root / "legacy-imports"
        imports_root.mkdir(mode=0o700, exist_ok=True)
        os.chmod(imports_root, 0o700)
        temporary = imports_root / f".{import_id}.incomplete"
        final = imports_root / import_id
        temporary.mkdir(mode=0o700)
        manifests: list[dict[str, Any]] = []
        try:
            for kind, source in sources:
                manifests.append(self._copy_source(kind, source, temporary / kind))
            manifest = {
                "schema_version": _MANIFEST_SCHEMA_VERSION,
                "import_id": import_id,
                "created_at": _now(),
                "source_untouched": True,
                "sources": manifests,
                "total_files": sum(int(item["file_count"]) for item in manifests),
                "total_size_bytes": sum(int(item["size_bytes"]) for item in manifests),
            }
            atomic_write(
                temporary / "manifest.json",
                (
                    json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    + "\n"
                ).encode(),
                mode=0o600,
            )
            os.rename(temporary, final)
            fsync_dir(imports_root)
        except BaseException:
            self.set_failure(
                "legacy_import_failed",
                "The legacy copy could not be completed; the source was left unchanged.",
                retryable=True,
            )
            raise

        def commit(state: dict[str, Any]) -> dict[str, Any]:
            if state.get("migration_choice") not in {None, "import"}:
                raise LegacyImportError("migration choice changed while import was running")
            return {
                **state,
                "migration_choice": "import",
                "import_id": import_id,
                "failure": None,
            }

        return self._locked_update(commit)
