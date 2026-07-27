"""Allowlisted, detached workflow launches for AionUi and the CLI.

This is intentionally a launcher, not a workflow engine. Each workflow is a fixed,
shell-free argv registered in ``workflows.yaml``. OpsWitness owns dispatch evidence,
single-workflow concurrency, and the run ledger; LangGraph, a script, or another proven
runtime remains responsible for the workflow's internal graph.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from opswitness.config import Settings, config_dir
from opswitness.fsutil import atomic_write
from opswitness.ids import new_ulid
from opswitness.ledger import Ledger
from opswitness.notify import alert
from opswitness.redact import redact_argv

WORKFLOW_SCHEMA_VERSION = 1
_WORKFLOW_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class WorkflowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    enabled: bool = True
    argv: list[str] = Field(min_length=1, max_length=128)
    cwd: Path
    concurrency: Literal["forbid"] = "forbid"

    @field_validator("argv")
    @classmethod
    def validate_argv(cls, argv: list[str]) -> list[str]:
        if any(not arg or "\x00" in arg for arg in argv):
            raise ValueError("argv entries must be non-empty and contain no NUL bytes")
        if not Path(argv[0]).expanduser().is_absolute():
            raise ValueError("argv[0] must be an absolute executable path; shells are not resolved")
        if Path(argv[0]).name in {"sh", "bash", "zsh", "fish", "dash", "ksh", "env"}:
            raise ValueError("shell and env launchers are forbidden; register the real executable")
        if redact_argv(argv) != argv:
            raise ValueError("workflow argv appears to contain a credential; load secrets in-process")
        return argv

    @field_validator("cwd")
    @classmethod
    def validate_cwd(cls, cwd: Path) -> Path:
        cwd = cwd.expanduser()
        if not cwd.is_absolute():
            raise ValueError("cwd must be absolute")
        return cwd


class WorkflowManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    workflows: dict[str, WorkflowDefinition] = Field(default_factory=dict)

    @field_validator("workflows")
    @classmethod
    def validate_ids(
        cls, workflows: dict[str, WorkflowDefinition]
    ) -> dict[str, WorkflowDefinition]:
        invalid = [workflow_id for workflow_id in workflows if not _WORKFLOW_ID.fullmatch(workflow_id)]
        if invalid:
            raise ValueError(
                "invalid workflow id(s): "
                + ", ".join(sorted(invalid))
                + "; use 1-64 letters, digits, dot, underscore, or hyphen"
            )
        return workflows


def workflows_path(root: Path | None = None) -> Path:
    return (root or config_dir()) / "workflows.yaml"


def _read_manifest(path: Path) -> WorkflowManifest:
    if path.is_symlink():
        raise ValueError(f"{path}: workflow manifest must not be a symlink")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode != 0o600:
        raise ValueError(f"{path}: workflow manifest mode must be 0600, found {mode:04o}")
    try:
        raw = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"{path}: cannot read valid YAML - {exc}") from exc
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping at top level")
    try:
        return WorkflowManifest.model_validate(raw)
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from exc


def load_workflows(root: Path | None = None) -> WorkflowManifest:
    path = workflows_path(root)
    if path.is_symlink():
        raise ValueError(f"{path}: workflow manifest must not be a symlink")
    if not path.exists():
        return WorkflowManifest()
    return _read_manifest(path)


def _normalised_definition(definition: WorkflowDefinition) -> WorkflowDefinition:
    # Preserve the registered executable path: resolving a venv's python symlink to the
    # base interpreter changes Python's environment discovery and loses installed deps.
    executable = Path(os.path.abspath(Path(definition.argv[0]).expanduser()))
    executable_target = executable.resolve(strict=True)
    cwd = definition.cwd.expanduser().resolve(strict=True)
    if not executable_target.is_file() or not os.access(executable, os.X_OK):
        raise ValueError(f"workflow executable is not an executable file: {executable}")
    if not cwd.is_dir():
        raise ValueError(f"workflow cwd is not a directory: {cwd}")
    return definition.model_copy(update={"argv": [str(executable), *definition.argv[1:]], "cwd": cwd})


def definition_hash(definition: WorkflowDefinition) -> str:
    payload = json.dumps(
        definition.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def workflow_catalog(root: Path | None = None) -> list[dict[str, Any]]:
    manifest = load_workflows(root)
    catalog: list[dict[str, Any]] = []
    for workflow_id, definition in sorted(manifest.workflows.items()):
        error: str | None = None
        digest: str | None = None
        try:
            normalised = _normalised_definition(definition)
            digest = definition_hash(normalised)
        except (OSError, ValueError) as exc:
            error = str(exc)
        catalog.append(
            {
                "workflow_id": workflow_id,
                "title": definition.title,
                "description": definition.description,
                "enabled": definition.enabled,
                "ready": definition.enabled and error is None,
                "definition_sha256": digest,
                "error": error,
            }
        )
    return catalog


def register_workflow(
    workflow_id: str,
    *,
    title: str,
    description: str,
    argv: list[str],
    cwd: Path,
    replace: bool = False,
    root: Path | None = None,
) -> Path:
    if not _WORKFLOW_ID.fullmatch(workflow_id):
        raise ValueError("workflow id must use 1-64 letters, digits, dot, underscore, or hyphen")
    root = (root or config_dir()).expanduser()
    if root.is_symlink():
        raise ValueError(f"{root}: config directory must not be a symlink")
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(root, 0o700)
    path = workflows_path(root)
    manifest = load_workflows(root)
    if workflow_id in manifest.workflows and not replace:
        raise ValueError(f"workflow already exists: {workflow_id}; pass --replace to update it")
    definition = _normalised_definition(
        WorkflowDefinition(title=title, description=description, argv=argv, cwd=cwd)
    )
    manifest.workflows[workflow_id] = definition
    payload = yaml.safe_dump(
        manifest.model_dump(mode="json"), sort_keys=False, allow_unicode=True
    ).encode()
    atomic_write(path, payload, mode=0o600)
    return path


def _state_root(settings: Settings) -> Path:
    return settings.ledger_dir.parent / "workflows"


def _acquire_launch_lock(settings: Settings, workflow_id: str) -> int:
    lock_dir = _state_root(settings) / "locks"
    lock_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(lock_dir, 0o700)
    lock_path = lock_dir / f"{workflow_id}.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    os.chmod(lock_path, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise ValueError(f"workflow already running: {workflow_id}") from None
    return fd


def _worker_environment(settings: Settings) -> dict[str, str]:
    allowed = ("HOME", "PATH", "LANG", "LC_ALL", "TMPDIR", "TZ")
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env.setdefault("HOME", str(Path.home()))
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin")
    env["OPSWITNESS_CONFIG_DIR"] = str(config_dir())
    env["OPSWITNESS_LEDGER_DIR"] = str(settings.ledger_dir)
    env["OPSWITNESS_SERVICES__LOG_DIR"] = str(settings.services.log_dir)
    return env


def start_workflow(
    workflow_id: str,
    *,
    source: Literal["cli", "mcp", "console"] = "cli",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Dispatch one fixed workflow and return immediately with its ledger run id."""
    settings = settings or Settings()
    ledger = Ledger(settings.ledger_dir)
    run_id = new_ulid()
    try:
        manifest = load_workflows()
        definition = manifest.workflows.get(workflow_id)
        if definition is None:
            raise ValueError(f"unknown workflow: {workflow_id}")
        if not definition.enabled:
            raise ValueError(f"workflow is disabled: {workflow_id}")
        definition = _normalised_definition(definition)
        digest = definition_hash(definition)
        lock_fd = _acquire_launch_lock(settings, workflow_id)
    except (OSError, ValueError) as exc:
        ledger.append(
            "workflow_launch_rejected",
            run_id,
            {
                "schema_version": WORKFLOW_SCHEMA_VERSION,
                "workflow_id": workflow_id,
                "source": source,
                "reason": str(exc),
            },
            fsync=True,
        )
        return {"accepted": False, "run_id": run_id, "workflow_id": workflow_id, "error": str(exc)}

    requested = ledger.append(
        "workflow_launch_requested",
        run_id,
        {
            "schema_version": WORKFLOW_SCHEMA_VERSION,
            "workflow_id": workflow_id,
            "job": f"workflow:{workflow_id}",
            "source": source,
            "definition_sha256": digest,
        },
        fsync=True,
    )
    if requested is None:
        os.close(lock_fd)
        message = f"audit evidence unavailable; workflow not started: {workflow_id}"
        alert(message)
        return {"accepted": False, "run_id": run_id, "workflow_id": workflow_id, "error": message}

    log_dir = _state_root(settings) / "logs"
    log_path = log_dir / f"{run_id}.log"
    try:
        log_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(log_dir, 0o700)
        log_fd = os.open(log_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except OSError as exc:
        os.close(lock_fd)
        ledger.append(
            "workflow_launch_failed",
            run_id,
            {
                "schema_version": WORKFLOW_SCHEMA_VERSION,
                "workflow_id": workflow_id,
                "job": f"workflow:{workflow_id}",
                "reason": f"secure log creation failed: {exc}",
            },
            fsync=True,
            degraded=True,
        )
        return {
            "accepted": False,
            "run_id": run_id,
            "workflow_id": workflow_id,
            "error": f"secure log creation failed: {exc}",
        }
    start_r: int | None = None
    start_w: int | None = None
    try:
        start_r, start_w = os.pipe()
        worker_argv = [
            sys.executable,
            "-m",
            "opswitness.workflow_worker",
            "--workflow-id",
            workflow_id,
            "--run-id",
            run_id,
            "--definition-sha256",
            digest,
            "--lock-fd",
            str(lock_fd),
            "--start-fd",
            str(start_r),
        ]
        process = subprocess.Popen(
            worker_argv,
            stdin=subprocess.DEVNULL,
            stdout=log_fd,
            stderr=subprocess.STDOUT,
            cwd="/",
            env=_worker_environment(settings),
            start_new_session=True,
            close_fds=True,
            pass_fds=(lock_fd, start_r),
        )
    except OSError as exc:
        os.close(lock_fd)
        for fd in (start_r, start_w):
            if fd is not None:
                os.close(fd)
        ledger.append(
            "workflow_launch_failed",
            run_id,
            {
                "schema_version": WORKFLOW_SCHEMA_VERSION,
                "workflow_id": workflow_id,
                "job": f"workflow:{workflow_id}",
                "reason": f"supervisor spawn failed: {exc}",
            },
            fsync=True,
            degraded=True,
        )
        return {
            "accepted": False,
            "run_id": run_id,
            "workflow_id": workflow_id,
            "error": f"supervisor spawn failed: {exc}",
        }
    finally:
        os.close(log_fd)

    assert start_r is not None and start_w is not None
    os.close(start_r)
    os.close(lock_fd)
    dispatched = ledger.append(
        "workflow_launch_dispatched",
        run_id,
        {
            "schema_version": WORKFLOW_SCHEMA_VERSION,
            "workflow_id": workflow_id,
            "job": f"workflow:{workflow_id}",
            "supervisor_pid": process.pid,
            "log_path": str(log_path),
        },
        fsync=True,
    )
    if dispatched is None:
        os.close(start_w)  # worker sees EOF and refuses to execute the command
        message = f"dispatch evidence unavailable; workflow not started: {workflow_id}"
        alert(message)
        return {
            "accepted": False,
            "run_id": run_id,
            "workflow_id": workflow_id,
            "error": message,
        }
    try:
        os.write(start_w, b"\x01")
    except OSError as exc:
        message = f"could not release workflow start barrier: {exc}"
        alert(f"{message}: {workflow_id} run={run_id}")
        return {
            "accepted": False,
            "run_id": run_id,
            "workflow_id": workflow_id,
            "error": message,
        }
    finally:
        os.close(start_w)
    return {
        "accepted": True,
        "run_id": run_id,
        "workflow_id": workflow_id,
        "status": "dispatched",
        "supervisor_pid": process.pid,
        "evidence_degraded": False,
    }


def workflow_runs(
    events: list[dict[str, Any]], *, run_id: str | None = None, limit: int = 20
) -> list[dict[str, Any]]:
    """Fold workflow launch events and wrapped run events in ledger commit order."""
    launches: dict[str, dict[str, Any]] = {}
    for event in events:
        kind = event.get("kind")
        current_run_id = str(event.get("run_id", ""))
        payload = event.get("payload", {})
        if kind == "workflow_launch_requested":
            launches[current_run_id] = {
                "run_id": current_run_id,
                "workflow_id": payload.get("workflow_id"),
                "status": "requested",
                "requested_ts": event.get("ts"),
                "source": payload.get("source"),
                "definition_sha256": payload.get("definition_sha256"),
                "degraded": bool(event.get("degraded")),
            }
        elif kind == "workflow_launch_rejected":
            launches[current_run_id] = {
                "run_id": current_run_id,
                "workflow_id": payload.get("workflow_id"),
                "status": "rejected",
                "requested_ts": event.get("ts"),
                "error": payload.get("reason"),
                "source": payload.get("source"),
                "degraded": bool(event.get("degraded")),
            }
        elif current_run_id in launches:
            launch = launches[current_run_id]
            launch["degraded"] = bool(launch.get("degraded") or event.get("degraded"))
            if kind == "workflow_launch_dispatched":
                launch.update(
                    {
                        "status": "dispatched",
                        "dispatched_ts": event.get("ts"),
                        "supervisor_pid": payload.get("supervisor_pid"),
                    }
                )
            elif kind == "workflow_launch_failed":
                launch.update(
                    {
                        "status": "failed",
                        "finished_ts": event.get("ts"),
                        "error": payload.get("reason"),
                    }
                )
            elif kind == "run_started":
                launch.update({"status": "running", "started_ts": event.get("ts")})
            elif kind == "run_finished":
                launch.update(
                    {
                        "status": payload.get("status", "unknown"),
                        "finished_ts": event.get("ts"),
                        "exit_code": payload.get("exit_code"),
                        "duration_s": payload.get("duration_s"),
                    }
                )
    rows = list(launches.values())
    if run_id:
        rows = [row for row in rows if row["run_id"] == run_id]
    rows.sort(key=lambda row: str(row.get("requested_ts", "")), reverse=True)
    return rows[: max(1, min(limit, 200))]


def workflow_status(
    run_id: str | None = None, *, limit: int = 20, settings: Settings | None = None
) -> list[dict[str, Any]]:
    settings = settings or Settings()
    return workflow_runs(Ledger(settings.ledger_dir).read_all(), run_id=run_id, limit=limit)
