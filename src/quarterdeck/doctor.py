"""Read-only install diagnostics with structured, fail-closed results."""

from __future__ import annotations

import os
import plistlib
import shutil
import socket
import stat
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import psutil

from quarterdeck.config import Settings, config_dir, resolve_api_key, validate_config_files
from quarterdeck.service import SERVICE_NAMES, _template_bytes


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str


def _version(path: str, args: tuple[str, ...] = ("--version",)) -> str:
    try:
        result = subprocess.run(
            [path, *args], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"error: {exc}"
    text = (result.stdout or result.stderr).strip().splitlines()
    return text[0] if result.returncode == 0 and text else f"exit {result.returncode}"


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False


def _paperclip_processes() -> list[int]:
    found: list[int] = []
    for process in psutil.process_iter(["pid", "cmdline"]):
        try:
            command = " ".join(process.info.get("cmdline") or []).lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        argv = process.info.get("cmdline") or []
        executable = Path(argv[0]).name.lower() if argv else ""
        # Count the actual Node runtime, not npm parents, Postgres workers whose
        # application name is paperclip, or arbitrary commands discussing Paperclip.
        if executable.startswith("node") and "paperclip" in command:
            found.append(int(process.info["pid"]))
    return sorted(found)


def _paperclip_backup_security(settings: Settings) -> tuple[bool, str]:
    backup_dir = (
        settings.services.paperclip_home.expanduser()
        / "instances"
        / "default"
        / "data"
        / "backups"
    )
    if backup_dir.is_symlink() or not backup_dir.is_dir():
        return False, f"missing or unsafe directory: {backup_dir}"
    directory_mode = stat.S_IMODE(backup_dir.stat().st_mode)
    if directory_mode & 0o077 or not os.access(backup_dir, os.R_OK | os.W_OK | os.X_OK):
        return False, f"directory must be private and writable: {backup_dir} mode={directory_mode:04o}"
    backups = sorted(backup_dir.glob("*.sql.gz"))
    unsafe: list[str] = []
    for path in backups:
        mode = stat.S_IMODE(path.stat().st_mode)
        if path.is_symlink() or not path.is_file() or mode & 0o077:
            unsafe.append(f"{path.name}:{mode:04o}")
    if unsafe:
        return False, "backup files must not grant group/other access: " + ", ".join(unsafe)
    return True, f"private directory mode={directory_mode:04o}; files={len(backups)}"


def _service_log_security(settings: Settings) -> tuple[bool, str]:
    log_dir = settings.services.log_dir.expanduser()
    if log_dir.is_symlink() or not log_dir.is_dir():
        return False, f"missing or unsafe directory: {log_dir}"
    directory_mode = stat.S_IMODE(log_dir.stat().st_mode)
    if directory_mode & 0o077 or not os.access(log_dir, os.R_OK | os.W_OK | os.X_OK):
        return False, f"directory must be private and writable: {log_dir} mode={directory_mode:04o}"
    logs = sorted(log_dir.glob("*.log"))
    unsafe: list[str] = []
    for path in logs:
        mode = stat.S_IMODE(path.stat().st_mode)
        if path.is_symlink() or not path.is_file() or mode & 0o077:
            unsafe.append(f"{path.name}:{mode:04o}")
    if unsafe:
        return False, "log files must not grant group/other access: " + ", ".join(unsafe)
    return True, f"private directory mode={directory_mode:04o}; files={len(logs)}"


def _installed_service_security(name: str, settings: Settings, launchagents_dir: Path) -> tuple[bool, str]:
    path = launchagents_dir / f"com.quarterdeck.{name}.plist"
    try:
        parsed = plistlib.loads(path.read_bytes())
    except (OSError, ValueError, plistlib.InvalidFileException) as exc:
        return False, f"cannot read {path}: {exc}"
    expected_args = [str(settings.services.qd_bin.expanduser().resolve()), "service", "exec", name]
    serialized = repr(parsed)
    safe = (
        parsed.get("Label") == f"com.quarterdeck.{name}"
        and parsed.get("ProgramArguments") == expected_args
        and parsed.get("Umask") == 0o077
        and "DATABASE_URL" not in serialized
        and "api_key" not in serialized.lower()
    )
    if not safe:
        return False, f"installed plist is stale, unsafe, or points at the wrong executable: {path}"
    return True, f"installed plist has private umask and stable qd path: {path}"


def run_doctor(
    *,
    settings_loader: Callable[[], Settings] = Settings,
    which: Callable[[str], str | None] = shutil.which,
    version: Callable[[str, tuple[str, ...]], str] = _version,
    port_open: Callable[[str, int], bool] = _port_open,
    paperclip_processes: Callable[[], list[int]] = _paperclip_processes,
    launchagents_dir: Path | None = None,
) -> dict:
    checks: list[DoctorCheck] = []

    try:
        validate_config_files(config_dir())
        checks.append(DoctorCheck("config_security", "pass", "config boundary valid"))
        settings = settings_loader()
    except (ValueError, OSError) as exc:
        settings = None
        checks.append(DoctorCheck("config_security", "fail", str(exc)))

    python_ok = sys.version_info >= (3, 12)
    checks.append(
        DoctorCheck(
            "python",
            "pass" if python_ok else "fail",
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
    )

    for tool in ("node", "psql", "pg_dump", "age"):
        path = which(tool)
        checks.append(
            DoctorCheck(
                tool,
                "pass" if path else "fail",
                f"{Path(path).resolve()} ({version(path, ('--version',))})" if path else "not found",
            )
        )

    if settings is None:
        checks.extend(
            [
                DoctorCheck("qd_bin", "fail", "settings unavailable"),
                DoctorCheck("paperclip_command", "fail", "settings unavailable"),
                DoctorCheck("paperclip_credentials", "fail", "settings unavailable"),
                DoctorCheck("backup_target", "fail", "settings unavailable"),
                DoctorCheck("paperclip_backup_security", "fail", "settings unavailable"),
                DoctorCheck("service_log_security", "fail", "settings unavailable"),
            ]
        )
    else:
        qd_bin = settings.services.qd_bin.expanduser().resolve()
        qd_ok = qd_bin.is_file() and os.access(qd_bin, os.X_OK)
        checks.append(DoctorCheck("qd_bin", "pass" if qd_ok else "fail", str(qd_bin)))
        command = settings.services.paperclip_command
        command_ok = bool(command)
        if command_ok:
            executable = Path(command[0]).expanduser().resolve()
            script = Path(command[1]).expanduser().resolve() if len(command) == 2 else None
            command_ok = (
                executable.is_file()
                and os.access(executable, os.X_OK)
                and script is not None
                and script.is_file()
                and script.is_absolute()
            )
            command_detail = " ".join(
                [str(executable), str(script) if script is not None else "<invalid-base-command>"]
            )
        else:
            command_detail = "not configured"
        checks.append(
            DoctorCheck("paperclip_command", "pass" if command_ok else "fail", command_detail)
        )
        credentials_ok = bool(
            settings.database_url and resolve_api_key(settings) and settings.paperclip.company_id
        )
        checks.append(
            DoctorCheck(
                "paperclip_credentials",
                "pass" if credentials_ok else "fail",
                "database_url + api_key + company_id configured"
                if credentials_ok
                else "database_url, api_key, or company_id missing",
            )
        )
        backup_dir = settings.backup.directory.expanduser()
        checks.append(
            DoctorCheck(
                "backup_target",
                "pass" if backup_dir.is_absolute() and bool(settings.backup.age_recipient) else "fail",
                f"{backup_dir} recipient={'configured' if settings.backup.age_recipient else 'missing'}",
            )
        )
        backup_security_ok, backup_security_detail = _paperclip_backup_security(settings)
        checks.append(
            DoctorCheck(
                "paperclip_backup_security",
                "pass" if backup_security_ok else "fail",
                backup_security_detail,
            )
        )
        log_security_ok, log_security_detail = _service_log_security(settings)
        checks.append(
            DoctorCheck(
                "service_log_security",
                "pass" if log_security_ok else "fail",
                log_security_detail,
            )
        )

    for name in SERVICE_NAMES:
        try:
            raw = _template_bytes(name)
            parsed = plistlib.loads(raw)
            serialized = repr(parsed)
            safe = (
                "DATABASE_URL" not in serialized
                and "api_key" not in serialized.lower()
                and parsed.get("Umask") == 0o077
            )
            checks.append(
                DoctorCheck(
                    f"template_{name}",
                    "pass" if safe else "fail",
                    "valid plist; private umask; no secret fields"
                    if safe
                    else "secret field found or private umask missing",
                )
            )
        except (OSError, ValueError, plistlib.InvalidFileException) as exc:
            checks.append(DoctorCheck(f"template_{name}", "fail", str(exc)))

    if settings is not None:
        installed_dir = launchagents_dir or (Path.home() / "Library" / "LaunchAgents")
        for name in ("paperclip", "projector", "watchdog"):
            installed_ok, installed_detail = _installed_service_security(
                name, settings, installed_dir
            )
            checks.append(
                DoctorCheck(
                    f"installed_{name}",
                    "pass" if installed_ok else "fail",
                    installed_detail,
                )
            )

    for name, port in (("postgres_port", 5432), ("paperclip_port", 3100)):
        opened = port_open("127.0.0.1", port)
        checks.append(
            DoctorCheck(name, "pass" if opened else "fail", f"127.0.0.1:{port} " + ("open" if opened else "closed"))
        )

    try:
        pids = paperclip_processes()
        checks.append(
            DoctorCheck(
                "paperclip_single_instance",
                "pass" if len(pids) <= 1 else "fail",
                f"matching pids={pids}",
            )
        )
    except (OSError, psutil.Error) as exc:
        checks.append(DoctorCheck("paperclip_single_instance", "fail", f"cannot inspect: {exc}"))

    encoded = [asdict(check) for check in checks]
    return {
        "healthy": all(check.status == "pass" for check in checks),
        "checks": encoded,
    }
