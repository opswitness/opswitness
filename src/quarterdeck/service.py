"""Secure launchd rendering and service exec boundary."""

from __future__ import annotations

import os
import plistlib
from importlib.resources import files
from pathlib import Path
from typing import Any

from quarterdeck.config import Settings, config_dir
from quarterdeck.fsutil import atomic_write

SERVICE_NAMES = ("paperclip", "projector", "watchdog", "gate-recovery", "console")
KEEPALIVE_SERVICE_NAMES = frozenset({"paperclip", "console"})


def _template_bytes(name: str) -> bytes:
    if name not in SERVICE_NAMES:
        raise ValueError(f"unknown service {name!r}; expected one of {SERVICE_NAMES}")
    return (
        files("quarterdeck")
        .joinpath("templates", "quant-fleet", "launchd", f"com.quarterdeck.{name}.plist")
        .read_bytes()
    )


def _replace(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, str):
        for marker, replacement in replacements.items():
            value = value.replace(marker, replacement)
        return value
    if isinstance(value, list):
        return [_replace(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _replace(item, replacements) for key, item in value.items()}
    return value


def render_launchd(name: str, settings: Settings) -> bytes:
    qd_bin = settings.services.qd_bin.expanduser().resolve()
    if not qd_bin.is_absolute() or not qd_bin.is_file() or not os.access(qd_bin, os.X_OK):
        raise ValueError(f"services.qd_bin is not an executable absolute file: {qd_bin}")
    data = plistlib.loads(_template_bytes(name))
    rendered = _replace(
        data,
        {
            "__QD_BIN__": str(qd_bin),
            "__QD_CONFIG_DIR__": str(config_dir().resolve()),
            "__QD_LOG_DIR__": str(settings.services.log_dir.expanduser().resolve()),
        },
    )
    return plistlib.dumps(rendered, fmt=plistlib.FMT_XML, sort_keys=False)


def write_launchd(name: str, output: Path, settings: Settings, *, force: bool = False) -> Path:
    output = output.expanduser().resolve()
    if output.exists() and not force:
        raise ValueError(f"refusing to overwrite {output}; pass --force")
    atomic_write(output, render_launchd(name, settings), mode=0o644)
    return output


def build_service_exec(
    name: str, settings: Settings, *, paperclip_mode: str = "run"
) -> tuple[list[str], dict[str, str]]:
    if name not in SERVICE_NAMES:
        raise ValueError(f"unknown service {name!r}; expected one of {SERVICE_NAMES}")
    env = dict(os.environ)
    env["QD_CONFIG_DIR"] = str(config_dir().resolve())
    if name == "paperclip":
        argv = list(settings.services.paperclip_command)
        if not argv:
            raise ValueError("services.paperclip_command is not configured")
        executable = Path(argv[0]).expanduser().resolve()
        if not executable.is_absolute() or not executable.is_file() or not os.access(executable, os.X_OK):
            raise ValueError(f"Paperclip executable is not an executable absolute file: {executable}")
        argv[0] = str(executable)
        if len(argv) != 2:
            raise ValueError(
                "services.paperclip_command must be exactly [absolute node, absolute dist/index.js]"
            )
        script = Path(argv[1]).expanduser().resolve()
        if not script.is_absolute() or not script.is_file():
            raise ValueError(f"Paperclip script is not an absolute file: {script}")
        argv[1] = str(script)
        if paperclip_mode == "run":
            argv.append("run")
        elif paperclip_mode == "onboard":
            argv.extend(["onboard", "--yes"])
        elif paperclip_mode == "backup":
            argv.extend(["db:backup", "--json"])
        else:
            raise ValueError("paperclip mode must be run, onboard, or backup")
        if not settings.database_url:
            raise ValueError("database_url is missing from secrets.yaml or QD_DATABASE_URL")
        env["DATABASE_URL"] = settings.database_url
        env["PAPERCLIP_TELEMETRY_DISABLED"] = "1"
        env["PAPERCLIP_HOME"] = str(settings.services.paperclip_home.expanduser().resolve())
        return argv, env
    qd_bin = settings.services.qd_bin.expanduser().resolve()
    if not qd_bin.is_file() or not os.access(qd_bin, os.X_OK):
        raise ValueError(f"services.qd_bin is not executable: {qd_bin}")
    if name == "projector":
        argv = [str(qd_bin), "project"]
    elif name == "watchdog":
        argv = [str(qd_bin), "watchdog", "--once"]
    elif name == "gate-recovery":
        argv = [str(qd_bin), "gate", "recover", "--once"]
    else:
        argv = [str(qd_bin), "console", "serve", "--port", str(settings.console.port)]
    return argv, env


def exec_service(name: str, settings: Settings, *, paperclip_mode: str = "run") -> None:
    argv, env = build_service_exec(name, settings, paperclip_mode=paperclip_mode)
    os.umask(0o077)
    os.execve(argv[0], argv, env)
