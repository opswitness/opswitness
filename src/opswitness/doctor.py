"""Read-only install diagnostics with structured, fail-closed results."""

from __future__ import annotations

import os
import plistlib
import re
import shutil
import socket
import stat
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import psutil

from opswitness.config import Settings, config_dir, resolve_api_key, validate_config_files
from opswitness.service import KEEPALIVE_SERVICE_NAMES, SERVICE_NAMES, _template_bytes
from opswitness.workflows import load_workflows, workflow_catalog


SERVICE_LABEL_PREFIX = "com.opswitness"
LEGACY_SERVICE_LABEL_PREFIX = "com.quarterdeck"


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
        settings.services.paperclip_home.expanduser() / "instances" / "default" / "data" / "backups"
    )
    if backup_dir.is_symlink() or not backup_dir.is_dir():
        return False, f"missing or unsafe directory: {backup_dir}"
    directory_mode = stat.S_IMODE(backup_dir.stat().st_mode)
    if directory_mode & 0o077 or not os.access(backup_dir, os.R_OK | os.W_OK | os.X_OK):
        return (
            False,
            f"directory must be private and writable: {backup_dir} mode={directory_mode:04o}",
        )
    backups = sorted(backup_dir.glob("*.sql.gz"))
    unsafe: list[str] = []
    for path in backups:
        try:
            mode = stat.S_IMODE(path.lstat().st_mode)
        except OSError:
            unsafe.append(f"{path.name}:unreadable")
            continue
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
        try:
            mode = stat.S_IMODE(path.lstat().st_mode)
        except OSError:
            unsafe.append(f"{path.name}:unreadable")
            continue
        if path.is_symlink() or not path.is_file() or mode & 0o077:
            unsafe.append(f"{path.name}:{mode:04o}")
    if unsafe:
        return False, "log files must not grant group/other access: " + ", ".join(unsafe)
    return True, f"private directory mode={directory_mode:04o}; files={len(logs)}"


def _installed_service_security(
    name: str, settings: Settings, launchagents_dir: Path
) -> tuple[bool, str]:
    candidates = {
        SERVICE_LABEL_PREFIX: launchagents_dir / f"{SERVICE_LABEL_PREFIX}.{name}.plist",
        LEGACY_SERVICE_LABEL_PREFIX: launchagents_dir
        / f"{LEGACY_SERVICE_LABEL_PREFIX}.{name}.plist",
    }
    installed = [
        (prefix, path)
        for prefix, path in candidates.items()
        if path.exists() or path.is_symlink()
    ]
    if len(installed) > 1:
        return False, f"new and legacy launchd services both exist for {name}"
    if not installed:
        return False, f"installed plist is missing: {candidates[SERVICE_LABEL_PREFIX]}"
    prefix, path = installed[0]
    if path.is_symlink() or not path.is_file():
        return False, f"installed plist is missing or a symlink: {path}"
    try:
        parsed = plistlib.loads(path.read_bytes())
    except (OSError, ValueError, plistlib.InvalidFileException) as exc:
        return False, f"cannot read {path}: {exc}"
    expected_args = [str(settings.services.qd_bin.expanduser().resolve()), "service", "exec", name]
    serialized = repr(parsed)
    safe = (
        parsed.get("Label") == f"{prefix}.{name}"
        and parsed.get("ProgramArguments") == expected_args
        and parsed.get("Umask") == 0o077
        and "DATABASE_URL" not in serialized
        and "api_key" not in serialized.lower()
    )
    if not safe:
        return False, f"installed plist is stale, unsafe, or points at the wrong executable: {path}"
    identity = "legacy compatible" if prefix == LEGACY_SERVICE_LABEL_PREFIX else "canonical"
    return True, f"{identity} plist has private umask and stable command path: {path}"


def _installed_service_prefix(name: str, launchagents_dir: Path) -> str | None:
    prefixes = [
        prefix
        for prefix in (SERVICE_LABEL_PREFIX, LEGACY_SERVICE_LABEL_PREFIX)
        if (launchagents_dir / f"{prefix}.{name}.plist").exists()
        or (launchagents_dir / f"{prefix}.{name}.plist").is_symlink()
    ]
    return prefixes[0] if len(prefixes) == 1 else None


def _launchd_service_runtime(
    name: str,
    *,
    label_prefix: str = SERVICE_LABEL_PREFIX,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[bool, str]:
    label = f"{label_prefix}.{name}"
    domain = f"gui/{os.getuid()}/{label}"
    try:
        result = run(
            ["launchctl", "print", domain],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"cannot inspect {label}: {exc}"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        return False, f"launchd service unavailable: {detail[0] if detail else label}"

    output = result.stdout
    state = re.search(r"^\s*state = ([^\s]+)\s*$", output, re.MULTILINE)
    runs = re.search(r"^\s*runs = (\d+)\s*$", output, re.MULTILINE)
    if name in KEEPALIVE_SERVICE_NAMES:
        running = state is not None and state.group(1) == "running"
        return running, f"state={state.group(1) if state else 'unknown'}"

    pending = re.search(
        r"^\s*pended nondemand spawn = ([^\s]+)\s*$", output, re.MULTILINE
    )
    if pending is not None:
        return (
            False,
            "launchd trigger is pending without execution: "
            f"reason={pending.group(1)} runs={runs.group(1) if runs else 'unknown'}",
        )

    last_exit = re.search(r"^\s*last exit code = (-?\d+)\s*$", output, re.MULTILINE)
    if last_exit is None:
        return False, f"runs={runs.group(1) if runs else 'unknown'} last_exit=unknown"
    code = int(last_exit.group(1))
    return code == 0, f"runs={runs.group(1) if runs else 'unknown'} last_exit={code}"


def _qd_command_surface(
    executable: Path,
    *,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[bool, str]:
    required = ("soak", "console")
    missing: list[str] = []
    for command in required:
        try:
            result = run(
                [str(executable), command, "--help"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"cannot inspect installed qd command surface: {exc}"
        if result.returncode != 0:
            missing.append(command)
    if missing:
        return False, "installed qd is missing required commands: " + ", ".join(missing)
    return True, "required commands available: " + ", ".join(required)


def run_doctor(
    *,
    settings_loader: Callable[[], Settings] = Settings,
    which: Callable[[str], str | None] = shutil.which,
    version: Callable[[str, tuple[str, ...]], str] = _version,
    port_open: Callable[[str, int], bool] = _port_open,
    paperclip_processes: Callable[[], list[int]] = _paperclip_processes,
    launchagents_dir: Path | None = None,
    launchd_runtime: Callable[[str], tuple[bool, str]] | None = None,
    mail_probe: Callable[[Settings], dict] | None = None,
) -> dict:
    checks: list[DoctorCheck] = []

    try:
        validate_config_files(config_dir())
        checks.append(DoctorCheck("config_security", "pass", "config boundary valid"))
        settings = settings_loader()
    except (ValueError, OSError) as exc:
        settings = None
        checks.append(DoctorCheck("config_security", "fail", str(exc)))

    try:
        manifest = load_workflows()
        catalog = workflow_catalog()
        invalid = [row for row in catalog if row["error"]]
        ready = sum(bool(row["ready"]) for row in catalog)
        checks.append(
            DoctorCheck(
                "workflow_manifest",
                "pass" if not invalid else "fail",
                f"registered={len(manifest.workflows)} ready={ready}"
                if not invalid
                else "; ".join(str(row["error"]) for row in invalid),
            )
        )
    except (OSError, ValueError) as exc:
        checks.append(DoctorCheck("workflow_manifest", "fail", str(exc)))

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
                f"{Path(path).resolve()} ({version(path, ('--version',))})"
                if path
                else "not found",
            )
        )

    if settings is None:
        checks.extend(
            [
                DoctorCheck("qd_bin", "fail", "settings unavailable"),
                DoctorCheck("qd_command_surface", "fail", "settings unavailable"),
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
        if qd_ok:
            command_surface_ok, command_surface_detail = _qd_command_surface(qd_bin)
        else:
            command_surface_ok, command_surface_detail = False, "qd executable unavailable"
        checks.append(
            DoctorCheck(
                "qd_command_surface",
                "pass" if command_surface_ok else "fail",
                command_surface_detail,
            )
        )
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
                "pass"
                if backup_dir.is_absolute() and bool(settings.backup.age_recipient)
                else "fail",
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
        if not settings.mail.enabled:
            checks.append(DoctorCheck("mail_adapter", "pass", "disabled"))
        else:
            try:
                if mail_probe is None:
                    from opswitness.mail import mail_status

                    mail_result = mail_status(settings)
                else:
                    mail_result = mail_probe(settings)
                checks.append(
                    DoctorCheck(
                        "mail_adapter",
                        "pass" if mail_result.get("ready") is True else "fail",
                        "metadata-only Gmail adapter ready"
                        if mail_result.get("ready") is True
                        else str(mail_result.get("error", "mail adapter is not ready")),
                    )
                )
            except (OSError, ValueError) as exc:
                checks.append(DoctorCheck("mail_adapter", "fail", str(exc)))

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

    console_installed = False
    if settings is not None:
        installed_dir = launchagents_dir or (Path.home() / "Library" / "LaunchAgents")
        installed_names = ["paperclip", "projector", "watchdog"]
        optional_gate = any(
            (installed_dir / f"{prefix}.gate-recovery.plist").exists()
            or (installed_dir / f"{prefix}.gate-recovery.plist").is_symlink()
            for prefix in (SERVICE_LABEL_PREFIX, LEGACY_SERVICE_LABEL_PREFIX)
        )
        if optional_gate:
            installed_names.append("gate-recovery")
        optional_console = any(
            (installed_dir / f"{prefix}.console.plist").exists()
            or (installed_dir / f"{prefix}.console.plist").is_symlink()
            for prefix in (SERVICE_LABEL_PREFIX, LEGACY_SERVICE_LABEL_PREFIX)
        )
        if optional_console:
            console_installed = True
            installed_names.append("console")
        for name in installed_names:
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
        if launchd_runtime is not None:
            for name in installed_names:
                runtime_ok, runtime_detail = launchd_runtime(name)
                checks.append(
                    DoctorCheck(
                        f"runtime_{name}",
                        "pass" if runtime_ok else "fail",
                        runtime_detail,
                    )
                )
        elif launchagents_dir is None and sys.platform == "darwin":
            for name in installed_names:
                prefix = _installed_service_prefix(name, installed_dir)
                if prefix is None:
                    runtime_ok, runtime_detail = False, "service identity is missing or ambiguous"
                else:
                    runtime_ok, runtime_detail = _launchd_service_runtime(
                        name, label_prefix=prefix
                    )
                checks.append(
                    DoctorCheck(
                        f"runtime_{name}",
                        "pass" if runtime_ok else "fail",
                        runtime_detail,
                    )
                )

    service_ports = [("postgres_port", 5432), ("paperclip_port", 3100)]
    if settings is not None and console_installed:
        service_ports.append(("console_port", settings.console.port))
    for name, port in service_ports:
        opened = port_open("127.0.0.1", port)
        checks.append(
            DoctorCheck(
                name,
                "pass" if opened else "fail",
                f"127.0.0.1:{port} " + ("open" if opened else "closed"),
            )
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
