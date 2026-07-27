"""Private metadata for the read-only, evidence-bound project file library."""

from __future__ import annotations

import fcntl
import json
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from opswitness.console.schemas import ProjectLibraryMetadata
from opswitness.fsutil import atomic_write, fsync_dir


class ProjectLibraryMetadataError(ValueError):
    pass


class ProjectLibraryMetadataStore:
    """Atomically store tags/version links without copying source file bytes."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser()
        self.metadata_dir = self.root / "project-library"

    def _ensure(self) -> None:
        if self.root.is_symlink() or self.metadata_dir.is_symlink():
            raise ProjectLibraryMetadataError("project library storage is unavailable")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.metadata_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        os.chmod(self.metadata_dir, 0o700)
        if (
            stat.S_IMODE(self.root.stat().st_mode) != 0o700
            or stat.S_IMODE(self.metadata_dir.stat().st_mode) != 0o700
        ):
            raise ProjectLibraryMetadataError("project library storage permissions are unsafe")

    def _path(self, asset_id: str) -> Path:
        if len(asset_id) != 64 or any(char not in "0123456789abcdef" for char in asset_id):
            raise ProjectLibraryMetadataError("invalid project library asset id")
        return self.metadata_dir / f"{asset_id}.json"

    def _lock_path(self, asset_id: str) -> Path:
        return self.metadata_dir / f".{asset_id}.lock"

    def _global_lock_path(self) -> Path:
        return self.metadata_dir / ".metadata.lock"

    @contextmanager
    def _metadata_lock(self, *, exclusive: bool) -> Iterator[None]:
        self._ensure()
        try:
            fd = os.open(
                self._global_lock_path(),
                os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
        except OSError as exc:
            raise ProjectLibraryMetadataError(
                "project library metadata lock is unavailable"
            ) from exc
        try:
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _get_unlocked(self, asset_id: str) -> ProjectLibraryMetadata | None:
        self._ensure()
        path = self._path(asset_id)
        try:
            if path.is_symlink():
                raise ProjectLibraryMetadataError("project library metadata must not be a symlink")
            mode = stat.S_IMODE(path.stat().st_mode)
            if mode != 0o600:
                raise ProjectLibraryMetadataError(
                    "project library metadata permissions are unsafe"
                )
            return ProjectLibraryMetadata.model_validate_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            if isinstance(exc, ProjectLibraryMetadataError):
                raise
            raise ProjectLibraryMetadataError("project library metadata is invalid") from exc

    def get(self, asset_id: str) -> ProjectLibraryMetadata | None:
        with self._metadata_lock(exclusive=False):
            return self._get_unlocked(asset_id)

    def _list_all_unlocked(self) -> dict[str, ProjectLibraryMetadata]:
        self._ensure()
        rows: dict[str, ProjectLibraryMetadata] = {}
        for path in sorted(self.metadata_dir.glob("*.json")):
            if path.is_symlink():
                raise ProjectLibraryMetadataError(
                    "project library metadata must not be a symlink"
                )
            row = self._get_unlocked(path.stem)
            if row is None or row.asset_id != path.stem:
                raise ProjectLibraryMetadataError("project library metadata identity is invalid")
            rows[row.asset_id] = row
        return rows

    def list_all(self) -> dict[str, ProjectLibraryMetadata]:
        with self._metadata_lock(exclusive=False):
            return self._list_all_unlocked()

    def put(self, metadata: ProjectLibraryMetadata) -> ProjectLibraryMetadata:
        """Write only when the persisted identity is absent or exactly bound."""
        with self._metadata_lock(exclusive=True):
            lock_path = self._lock_path(metadata.asset_id)
            fd = os.open(
                lock_path,
                os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            try:
                os.fchmod(fd, 0o600)
                fcntl.flock(fd, fcntl.LOCK_EX)
                current = self._get_unlocked(metadata.asset_id)
                if current is not None and (
                    current.source_kind != metadata.source_kind
                    or current.plan_id != metadata.plan_id
                    or current.source_ref != metadata.source_ref
                    or current.name != metadata.name
                    or current.sha256 != metadata.sha256
                ):
                    raise ProjectLibraryMetadataError(
                        "project library metadata binding does not match the current file"
                    )
                encoded = (
                    json.dumps(
                        metadata.model_dump(mode="json"),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode()
                atomic_write(self._path(metadata.asset_id), encoded, mode=0o600)
                return metadata
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def remove_for_plan(self, plan_id: str) -> int:
        """Idempotently remove private metadata bound to one exact plan."""
        if (
            len(plan_id) != 26
            or any(char not in "0123456789ABCDEFGHJKMNPQRSTVWXYZ" for char in plan_id)
        ):
            raise ProjectLibraryMetadataError("invalid project library plan id")
        with self._metadata_lock(exclusive=True):
            rows = self._list_all_unlocked()
            target_ids = sorted(
                asset_id
                for asset_id, row in rows.items()
                if row.plan_id == plan_id
            )
            removed = 0
            try:
                for asset_id in target_ids:
                    if self._path(asset_id).is_symlink() or self._lock_path(asset_id).is_symlink():
                        raise ProjectLibraryMetadataError(
                            "project library metadata must not be a symlink"
                        )
                for asset_id in target_ids:
                    path = self._path(asset_id)
                    self._lock_path(asset_id).unlink(missing_ok=True)
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass
                    else:
                        removed += 1
                fsync_dir(self.metadata_dir)
            except OSError as exc:
                raise ProjectLibraryMetadataError(
                    "project library metadata could not be erased"
                ) from exc
            return removed
