"""Validated boundary between the macOS supervisor and the Python backend.

The descriptor intentionally contains only process identity and integrity
metadata.  It is not a configuration or credential transport.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


DESKTOP_MODE_ENV = "OPSWITNESS_DESKTOP_MODE"
DESKTOP_RUNTIME_FILE_ENV = "OPSWITNESS_DESKTOP_RUNTIME_FILE"
DESKTOP_CREDENTIAL_FILE_ENV = "OPSWITNESS_DESKTOP_CREDENTIAL_FILE"
DESKTOP_PROCESS_NAMES = frozenset({"paperclip", "aioncore", "backend"})
_INSTANCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DESCRIPTOR_KEYS = frozenset(
    {
        "schema_version",
        "instance_id",
        "supervisor_pid",
        "resource_root",
        "resource_manifest",
        "resource_manifest_sha256",
        "codex_executable",
        "processes",
    }
)
_PROCESS_KEYS = frozenset({"name", "pid", "executable", "port"})


@dataclass(frozen=True)
class DesktopProcess:
    name: str
    pid: int
    executable: Path
    port: int


@dataclass(frozen=True)
class DesktopRuntime:
    instance_id: str
    supervisor_pid: int
    resource_root: Path
    resource_manifest: Path
    resource_manifest_sha256: str
    codex_executable: Path
    processes: tuple[DesktopProcess, ...]

    def process(self, name: str) -> DesktopProcess | None:
        return next((process for process in self.processes if process.name == name), None)


@dataclass(frozen=True)
class DesktopPaperclipCredentials:
    company_id: str
    agent_id: str
    api_key: str


def desktop_mode_requested() -> bool:
    """Return whether the process explicitly opted into the desktop boundary."""

    marker = os.environ.get(DESKTOP_MODE_ENV, "").strip().lower()
    return marker in {"1", "true", "yes", "on"} or bool(
        os.environ.get(DESKTOP_RUNTIME_FILE_ENV, "").strip()
    )


def load_desktop_paperclip_credentials(
    path: Path | None = None,
) -> DesktopPaperclipCredentials:
    """Load the supervisor-owned Paperclip token without copying it into AionCore config."""

    if not desktop_mode_requested():
        raise ValueError("desktop Paperclip credentials require explicit desktop mode")
    if path is None:
        raw_path = os.environ.get(DESKTOP_CREDENTIAL_FILE_ENV, "").strip()
        if not raw_path:
            raise ValueError(f"{DESKTOP_CREDENTIAL_FILE_ENV} is required")
        path = Path(raw_path)
    if not path.is_absolute():
        raise ValueError("desktop Paperclip credential path must be absolute")
    try:
        metadata = path.lstat()
        parent_metadata = path.parent.lstat()
    except OSError as exc:
        raise ValueError(f"desktop Paperclip credential is unavailable: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("desktop Paperclip credential must be a regular file, not a symlink")
    if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
        raise ValueError("desktop Paperclip credential must be owned by the current user")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ValueError("desktop Paperclip credential must have mode 0600")
    if (
        stat.S_ISLNK(parent_metadata.st_mode)
        or not stat.S_ISDIR(parent_metadata.st_mode)
        or (hasattr(os, "getuid") and parent_metadata.st_uid != os.getuid())
        or stat.S_IMODE(parent_metadata.st_mode) & 0o077
    ):
        raise ValueError("desktop Paperclip credential directory must be private")
    if metadata.st_size > 16 * 1024:
        raise ValueError("desktop Paperclip credential exceeds 16 KiB")
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"desktop Paperclip credential is invalid JSON: {exc}") from exc
    payload = _mapping(
        decoded,
        label="desktop Paperclip credential",
        keys=frozenset({"company_id", "agent_id", "api_key"}),
    )
    fields: dict[str, str] = {}
    for key in ("company_id", "agent_id", "api_key"):
        value = payload[key]
        if not isinstance(value, str) or not value or len(value) > 4096:
            raise ValueError(f"desktop Paperclip credential field is invalid: {key}")
        fields[key] = value
    return DesktopPaperclipCredentials(
        company_id=fields["company_id"],
        agent_id=fields["agent_id"],
        api_key=fields["api_key"],
    )


def apply_desktop_mcp_credentials() -> bool:
    """Install the private token only inside the App-managed MCP process."""

    if not os.environ.get(DESKTOP_CREDENTIAL_FILE_ENV, "").strip():
        return False
    credentials = load_desktop_paperclip_credentials()
    os.environ["OPSWITNESS_PAPERCLIP__COMPANY_ID"] = credentials.company_id
    os.environ["OPSWITNESS_PAPERCLIP__API_KEY"] = credentials.api_key
    os.environ.pop(DESKTOP_CREDENTIAL_FILE_ENV, None)
    return True


def _private_regular_file(path: Path, *, executable: bool = False) -> Path:
    if not path.is_absolute():
        raise ValueError(f"desktop runtime path must be absolute: {path}")
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError(f"desktop runtime path is unavailable: {path}: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"desktop runtime path must be a regular file: {path}")
    if executable and not os.access(path, os.X_OK):
        raise ValueError(f"desktop runtime executable is not executable: {path}")
    return path.resolve()


def _owned_private_descriptor(path: Path) -> None:
    if not path.is_absolute():
        raise ValueError("desktop runtime descriptor path must be absolute")
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError(f"desktop runtime descriptor is unavailable: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("desktop runtime descriptor must be a regular file, not a symlink")
    if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
        raise ValueError("desktop runtime descriptor must be owned by the current user")
    mode = stat.S_IMODE(metadata.st_mode)
    if mode != 0o600:
        raise ValueError(f"desktop runtime descriptor must have mode 0600, found {mode:04o}")
    parent = path.parent
    parent_metadata = parent.stat()
    parent_mode = stat.S_IMODE(parent_metadata.st_mode)
    if parent_mode & 0o077:
        raise ValueError(
            "desktop runtime descriptor directory must not grant group/other access: "
            f"{parent_mode:04o}"
        )


def _mapping(value: Any, *, label: str, keys: frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    actual = frozenset(str(key) for key in value)
    unknown = actual - keys
    missing = keys - actual
    if unknown or missing:
        raise ValueError(
            f"{label} fields do not match schema; "
            f"missing={sorted(missing)} unknown={sorted(unknown)}"
        )
    return value


def _positive_int(value: Any, *, label: str, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label} must not exceed {maximum}")
    return value


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _lexical_symlink_destination(relative_link: PurePosixPath, target: PurePosixPath) -> PurePosixPath:
    """Normalize one relative link target without permitting payload escape."""

    parts: list[str] = []
    for part in (*relative_link.parent.parts, *target.parts):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                raise ValueError("desktop resource symlink target escapes resource_root")
            parts.pop()
            continue
        parts.append(part)
    return PurePosixPath(*parts)


def _validate_runtime_symlink(
    resource_root: Path,
    relative_link: PurePosixPath,
    absolute_link: Path,
    target_text: str,
) -> None:
    """Validate an exact, relative, contained, and non-broken runtime symlink."""

    if not target_text:
        raise ValueError(f"desktop resource symlink target is empty: {relative_link}")
    target = PurePosixPath(target_text)
    if target.is_absolute():
        raise ValueError(f"desktop resource symlink target must be relative: {relative_link}")
    _lexical_symlink_destination(relative_link, target)
    try:
        resolved = (absolute_link.parent / Path(*target.parts)).resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"desktop resource symlink target is broken: {relative_link}") from exc
    try:
        resolved.relative_to(resource_root)
    except ValueError as exc:
        raise ValueError(
            f"desktop resource symlink resolves outside resource_root: {relative_link}"
        ) from exc


def _runtime_inventory(resource_root: Path, manifest_path: Path) -> set[str]:
    """List regular files and symlinks without traversing linked directories."""

    actual: set[str] = set()
    for directory, directory_names, file_names in os.walk(resource_root, followlinks=False):
        directory_path = Path(directory)
        for name in (*directory_names, *file_names):
            path = directory_path / name
            if path.name == ".gitkeep" or path == manifest_path:
                continue
            try:
                metadata = path.lstat()
            except OSError as exc:
                raise ValueError(f"desktop resource cannot be inspected: {path}") from exc
            if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
                continue
            if not (stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)):
                raise ValueError(f"desktop resource has unsupported file type: {path}")
            actual.add(path.relative_to(resource_root).as_posix())
    return actual


def _verify_resource_inventory(resource_root: Path, manifest_path: Path) -> None:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"desktop resource manifest is invalid JSON: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 2:
        raise ValueError("unsupported desktop resource manifest schema")
    if manifest.get("target") != "aarch64-apple-darwin":
        raise ValueError("desktop resource manifest target must be aarch64-apple-darwin")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("desktop resource manifest files must be a JSON array")

    expected: set[str] = set()
    for index, raw_entry in enumerate(files):
        if not isinstance(raw_entry, dict):
            raise ValueError(f"desktop resource manifest entry {index} is invalid")
        kind = raw_entry.get("kind")
        required_keys = (
            {"path", "kind", "sha256", "size", "executable"}
            if kind == "file"
            else {"path", "kind", "target"}
            if kind == "symlink"
            else set()
        )
        if not required_keys or frozenset(raw_entry) != frozenset(required_keys):
            raise ValueError(f"desktop resource manifest entry {index} is invalid")
        relative = raw_entry["path"]
        parsed = PurePosixPath(relative) if isinstance(relative, str) else PurePosixPath()
        if (
            not relative
            or parsed.is_absolute()
            or any(part in {"", ".", ".."} for part in parsed.parts)
            or relative in expected
        ):
            raise ValueError(f"unsafe or duplicate desktop resource path: {relative!r}")
        expected.add(relative)
        absolute = resource_root.joinpath(*parsed.parts)
        if kind == "file":
            resolved = _private_regular_file(absolute)
            try:
                resolved.relative_to(resource_root)
            except ValueError as exc:
                raise ValueError(f"desktop resource escapes resource_root: {relative}") from exc
            expected_size = raw_entry["size"]
            if (
                isinstance(expected_size, bool)
                or not isinstance(expected_size, int)
                or expected_size < 0
                or absolute.stat().st_size != expected_size
            ):
                raise ValueError(f"desktop resource size mismatch: {relative}")
            expected_sha256 = raw_entry["sha256"]
            if (
                not isinstance(expected_sha256, str)
                or not _SHA256.fullmatch(expected_sha256)
                or _sha256(absolute) != expected_sha256
            ):
                raise ValueError(f"desktop resource digest mismatch: {relative}")
            executable = raw_entry["executable"]
            if not isinstance(executable, bool) or executable != os.access(absolute, os.X_OK):
                raise ValueError(f"desktop resource executable mode mismatch: {relative}")
            continue

        try:
            metadata = absolute.lstat()
        except OSError as exc:
            raise ValueError(f"desktop resource symlink is unavailable: {relative}") from exc
        if not stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"desktop resource is not the recorded symlink: {relative}")
        recorded_target = raw_entry["target"]
        if not isinstance(recorded_target, str):
            raise ValueError(f"desktop resource symlink target is invalid: {relative}")
        try:
            actual_target = os.readlink(absolute)
        except OSError as exc:
            raise ValueError(f"desktop resource symlink cannot be read: {relative}") from exc
        if actual_target != recorded_target:
            raise ValueError(f"desktop resource symlink target mismatch: {relative}")
        _validate_runtime_symlink(resource_root, parsed, absolute, recorded_target)

    actual = _runtime_inventory(resource_root, manifest_path)
    if actual != expected:
        raise ValueError(
            "desktop resource inventory mismatch; "
            f"missing={sorted(expected - actual)} unlisted={sorted(actual - expected)}"
        )


def _load_desktop_descriptor(path: Path | None = None) -> tuple[dict[str, Any], str, int]:
    if path is None:
        raw_path = os.environ.get(DESKTOP_RUNTIME_FILE_ENV, "").strip()
        if not raw_path:
            raise ValueError(f"{DESKTOP_RUNTIME_FILE_ENV} is required in desktop mode")
        path = Path(raw_path)
    _owned_private_descriptor(path)
    if path.stat().st_size > 128 * 1024:
        raise ValueError("desktop runtime descriptor exceeds 128 KiB")
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"desktop runtime descriptor is invalid JSON: {exc}") from exc
    payload = _mapping(decoded, label="desktop runtime descriptor", keys=_DESCRIPTOR_KEYS)

    if payload["schema_version"] != 1:
        raise ValueError("unsupported desktop runtime descriptor schema")
    instance_id = payload["instance_id"]
    if not isinstance(instance_id, str) or not _INSTANCE_ID.fullmatch(instance_id):
        raise ValueError("desktop runtime instance_id is invalid")
    supervisor_pid = _positive_int(payload["supervisor_pid"], label="supervisor_pid")
    return payload, instance_id, supervisor_pid


def load_desktop_supervisor_instance_id(path: Path | None = None) -> str:
    """Read the private supervisor identity without rehashing the runtime payload."""

    _, instance_id, _ = _load_desktop_descriptor(path)
    return instance_id


def load_desktop_runtime(path: Path | None = None) -> DesktopRuntime:
    """Load and fail-closed validate a supervisor-owned runtime descriptor."""

    payload, instance_id, supervisor_pid = _load_desktop_descriptor(path)

    resource_root = Path(str(payload["resource_root"]))
    if not resource_root.is_absolute() or resource_root.is_symlink() or not resource_root.is_dir():
        raise ValueError("desktop runtime resource_root must be an absolute regular directory")
    resource_root = resource_root.resolve()
    resource_manifest = _private_regular_file(Path(str(payload["resource_manifest"])))
    try:
        resource_manifest.relative_to(resource_root)
    except ValueError as exc:
        raise ValueError("desktop resource manifest must be inside resource_root") from exc
    expected_manifest_sha256 = payload["resource_manifest_sha256"]
    if (
        not isinstance(expected_manifest_sha256, str)
        or not _SHA256.fullmatch(expected_manifest_sha256)
    ):
        raise ValueError("desktop resource_manifest_sha256 must be lowercase SHA-256")
    actual_manifest_sha256 = _sha256(resource_manifest)
    if actual_manifest_sha256 != expected_manifest_sha256:
        raise ValueError("desktop resource manifest digest does not match descriptor")
    _verify_resource_inventory(resource_root, resource_manifest)

    codex_executable = _private_regular_file(
        Path(str(payload["codex_executable"])), executable=True
    )
    try:
        codex_executable.relative_to(resource_root)
    except ValueError as exc:
        raise ValueError("desktop Codex executable must be inside resource_root") from exc

    raw_processes = payload["processes"]
    if not isinstance(raw_processes, list):
        raise ValueError("desktop runtime processes must be a JSON array")
    processes: list[DesktopProcess] = []
    seen: set[str] = set()
    for index, raw_process in enumerate(raw_processes):
        process = _mapping(
            raw_process,
            label=f"desktop runtime process {index}",
            keys=_PROCESS_KEYS,
        )
        name = process["name"]
        if not isinstance(name, str) or name not in DESKTOP_PROCESS_NAMES:
            raise ValueError(f"desktop runtime process name is not allowed: {name!r}")
        if name in seen:
            raise ValueError(f"duplicate desktop runtime process: {name}")
        seen.add(name)
        executable = _private_regular_file(Path(str(process["executable"])), executable=True)
        try:
            executable.relative_to(resource_root)
        except ValueError as exc:
            raise ValueError(
                f"desktop runtime executable for {name} must be inside resource_root"
            ) from exc
        processes.append(
            DesktopProcess(
                name=name,
                pid=_positive_int(process["pid"], label=f"{name}.pid"),
                executable=executable,
                port=_positive_int(process["port"], label=f"{name}.port", maximum=65535),
            )
        )

    return DesktopRuntime(
        instance_id=instance_id,
        supervisor_pid=supervisor_pid,
        resource_root=resource_root,
        resource_manifest=resource_manifest,
        resource_manifest_sha256=expected_manifest_sha256,
        codex_executable=codex_executable,
        processes=tuple(processes),
    )


def process_identity_matches(process: DesktopProcess) -> tuple[bool, str]:
    """Verify that a descriptor PID still belongs to the recorded executable."""

    try:
        import psutil

        observed = Path(psutil.Process(process.pid).exe()).resolve()
    except (OSError, psutil.Error) as exc:
        return False, f"pid={process.pid} cannot be inspected: {exc}"
    matches = observed == process.executable
    return (
        matches,
        f"pid={process.pid} executable={observed}"
        if matches
        else (
            f"pid={process.pid} executable mismatch; "
            f"expected={process.executable} observed={observed}"
        ),
    )
