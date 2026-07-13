import json
import stat
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from quarterdeck.cli import app
from quarterdeck.config import Settings
from quarterdeck.digest import build_digest
from quarterdeck.ledger import Ledger
from quarterdeck.workflows import (
    WorkflowDefinition,
    load_workflows,
    register_workflow,
    start_workflow,
    workflow_catalog,
    workflow_status,
)


@pytest.fixture()
def workflow_env(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir(mode=0o700)
    monkeypatch.setenv("QD_CONFIG_DIR", str(config))
    monkeypatch.setenv("QD_LEDGER_DIR", str(tmp_path / "state" / "ledger"))
    return tmp_path, config


def _register(config: Path, workflow_id: str = "demo", argv: list[str] | None = None) -> None:
    register_workflow(
        workflow_id,
        title="Demo workflow",
        description="fixed test command",
        argv=argv or ["/usr/bin/true"],
        cwd=config.parent,
        root=config,
    )


def _wait_for_terminal(settings: Settings, run_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        rows = workflow_status(run_id, settings=settings)
        if rows and rows[0]["status"] not in {"requested", "dispatched", "running"}:
            return rows[0]
        time.sleep(0.03)
    pytest.fail(f"workflow {run_id} did not reach a terminal state")


def test_manifest_is_strict_and_secret_safe(workflow_env):
    _, config = workflow_env
    with pytest.raises(ValueError, match="shell"):
        WorkflowDefinition(title="bad", argv=["/bin/sh", "-c", "true"], cwd=config)
    with pytest.raises(ValueError, match="credential"):
        WorkflowDefinition(title="bad", argv=["/usr/bin/true", "--api-key=secret"], cwd=config)
    with pytest.raises(ValueError, match="absolute executable"):
        WorkflowDefinition(title="bad", argv=["true"], cwd=config)

    path = config / "workflows.yaml"
    path.write_text("schema_version: 1\nworkflows: {}\n")
    path.chmod(0o644)
    with pytest.raises(ValueError, match="0600"):
        load_workflows(config)


def test_manifest_symlink_is_rejected(workflow_env, tmp_path):
    _, config = workflow_env
    target = tmp_path / "outside.yaml"
    target.write_text("schema_version: 1\nworkflows: {}\n")
    target.chmod(0o600)
    (config / "workflows.yaml").symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        load_workflows(config)


def test_register_and_catalog_normalise_paths(workflow_env):
    _, config = workflow_env
    _register(config)
    path = config / "workflows.yaml"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    raw = yaml.safe_load(path.read_text())
    assert raw["schema_version"] == 1
    assert raw["workflows"]["demo"]["argv"][0] == "/usr/bin/true"
    catalog = workflow_catalog(config)
    assert catalog[0]["workflow_id"] == "demo"
    assert catalog[0]["ready"] is True
    assert len(catalog[0]["definition_sha256"]) == 64


def test_executable_symlink_path_is_preserved_for_venv_semantics(workflow_env, tmp_path):
    _, config = workflow_env
    target = tmp_path / "python-base"
    target.write_text("#!/bin/sh\nexit 0\n")
    target.chmod(0o755)
    venv_bin = tmp_path / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    link = venv_bin / "python"
    link.symlink_to(target)
    _register(config, argv=[str(link)])
    raw = yaml.safe_load((config / "workflows.yaml").read_text())
    assert raw["workflows"]["demo"]["argv"][0] == str(link)


def test_workflow_executes_from_registered_cwd(workflow_env):
    tmp_path, config = workflow_env
    workflow_cwd = tmp_path / "workflow-cwd"
    workflow_cwd.mkdir()
    output = tmp_path / "cwd.txt"
    register_workflow(
        "cwd-check",
        title="CWD check",
        description="",
        argv=[
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; Path(sys.argv[1]).write_text(str(Path.cwd()))",
            str(output),
        ],
        cwd=workflow_cwd,
        root=config,
    )

    settings = Settings()
    launched = start_workflow("cwd-check", settings=settings)
    assert launched["accepted"] is True
    terminal = _wait_for_terminal(settings, launched["run_id"])

    assert terminal["status"] == "succeeded"
    assert output.read_text() == str(workflow_cwd.resolve())
    started = next(
        event
        for event in Ledger(settings.ledger_dir).read_all()
        if event["run_id"] == launched["run_id"] and event["kind"] == "run_started"
    )
    assert started["payload"]["cwd"] == str(workflow_cwd.resolve())


def test_detached_launch_has_ordered_evidence_and_terminal_status(workflow_env):
    tmp_path, config = workflow_env
    _register(config)
    settings = Settings()
    result = start_workflow("demo", source="mcp", settings=settings)
    assert result["accepted"] is True
    terminal = _wait_for_terminal(settings, result["run_id"])
    assert terminal["status"] == "succeeded"
    assert terminal["exit_code"] == 0
    assert terminal["source"] == "mcp"

    events = [
        event
        for event in Ledger(settings.ledger_dir).read_all()
        if event["run_id"] == result["run_id"]
    ]
    assert [event["kind"] for event in events] == [
        "workflow_launch_requested",
        "workflow_launch_dispatched",
        "run_started",
        "run_finished",
    ]
    assert events[2]["payload"]["job"] == "workflow:demo"
    log_path = tmp_path / "state" / "workflows" / "logs" / f"{result['run_id']}.log"
    assert stat.S_IMODE(log_path.stat().st_mode) == 0o600


def test_same_workflow_concurrency_is_fail_closed(workflow_env):
    _, config = workflow_env
    _register(config, argv=["/bin/sleep", "0.5"])
    settings = Settings()
    first = start_workflow("demo", settings=settings)
    second = start_workflow("demo", settings=settings)
    assert first["accepted"] is True
    assert second["accepted"] is False
    assert "already running" in second["error"]
    assert workflow_status(second["run_id"], settings=settings)[0]["status"] == "rejected"
    assert _wait_for_terminal(settings, first["run_id"])["status"] == "succeeded"


def test_missing_dispatch_evidence_never_releases_worker(workflow_env, monkeypatch):
    _, config = workflow_env
    _register(config)
    settings = Settings()
    real_append = Ledger.append

    def fail_dispatch(self, kind, run_id, payload, **kwargs):
        if kind == "workflow_launch_dispatched":
            return None
        return real_append(self, kind, run_id, payload, **kwargs)

    monkeypatch.setattr(Ledger, "append", fail_dispatch)
    result = start_workflow("demo", settings=settings)
    assert result["accepted"] is False
    assert "dispatch evidence unavailable" in result["error"]

    deadline = time.monotonic() + 5
    events = []
    while time.monotonic() < deadline:
        events = [
            event
            for event in Ledger(settings.ledger_dir).read_all()
            if event["run_id"] == result["run_id"]
        ]
        if any(event["kind"] == "workflow_launch_failed" for event in events):
            break
        time.sleep(0.03)
    kinds = [event["kind"] for event in events]
    assert kinds == ["workflow_launch_requested", "workflow_launch_failed"]
    assert "run_started" not in kinds


def test_on_demand_workflow_is_not_a_watchdog_gap_but_failure_still_counts(workflow_env):
    _, _ = workflow_env
    settings = Settings()
    ledger = Ledger(settings.ledger_dir)
    ledger.append(
        "workflow_launch_requested",
        "WORKFLOW1",
        {"workflow_id": "demo", "job": "workflow:demo", "source": "mcp"},
    )
    ledger.append("run_started", "WORKFLOW1", {"job": "workflow:demo", "argv": []})
    ledger.append(
        "run_finished",
        "WORKFLOW1",
        {"job": "workflow:demo", "status": "failed", "exit_code": 1, "duration_s": 0.1},
    )
    ledger.append("run_started", "CANARY1", {"job": "canary", "argv": []})
    ledger.append(
        "run_finished",
        "CANARY1",
        {"job": "canary", "status": "succeeded", "exit_code": 0, "duration_s": 0.1},
    )

    digest = build_digest(
        ledger.read_all(),
        datetime.now(UTC),
        schedules=[{"job": "canary", "expected_interval_seconds": 3600}],
    )
    assert digest["coverage"]["status"] == "full"
    assert digest["coverage"]["on_demand"] == ["workflow:demo"]
    assert digest["coverage"]["observed_unregistered"] == []
    assert digest["healthy"] is False
    assert digest["problems"][0]["job"] == "workflow:demo"


def test_unknown_and_disabled_workflows_do_not_spawn(workflow_env):
    _, config = workflow_env
    settings = Settings()
    unknown = start_workflow("missing", settings=settings)
    assert unknown["accepted"] is False
    assert workflow_status(unknown["run_id"], settings=settings)[0]["status"] == "rejected"

    _register(config)
    path = config / "workflows.yaml"
    raw = yaml.safe_load(path.read_text())
    raw["workflows"]["demo"]["enabled"] = False
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    path.chmod(0o600)
    disabled = start_workflow("demo", settings=settings)
    assert disabled["accepted"] is False
    assert "disabled" in disabled["error"]


def test_cli_register_list_start_and_status(workflow_env):
    tmp_path, _ = workflow_env
    runner = CliRunner()
    registered = runner.invoke(
        app,
        [
            "workflow",
            "register",
            "demo",
            "--cwd",
            str(tmp_path),
            "--",
            "/usr/bin/true",
        ],
    )
    assert registered.exit_code == 0, registered.output
    listed = runner.invoke(app, ["workflow", "list"])
    assert listed.exit_code == 0
    assert json.loads(listed.output)[0]["workflow_id"] == "demo"
    started = runner.invoke(app, ["workflow", "start", "demo"])
    assert started.exit_code == 0, started.output
    run_id = json.loads(started.output)["run_id"]
    _wait_for_terminal(Settings(), run_id)
    status_result = runner.invoke(app, ["workflow", "status", "--run-id", run_id])
    assert status_result.exit_code == 0
    assert json.loads(status_result.output)[0]["status"] == "succeeded"
