import hashlib
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opswitness.config import Settings
from opswitness.console.app import create_app
from opswitness.console.service import ConsoleService
from opswitness.desktop_runtime import (
    DESKTOP_CREDENTIAL_FILE_ENV,
    DESKTOP_RUNTIME_FILE_ENV,
    DesktopRuntime,
    apply_desktop_mcp_credentials,
    load_desktop_paperclip_credentials,
    load_desktop_runtime,
    load_desktop_supervisor_instance_id,
)
from opswitness.doctor import run_doctor


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(0o755)
    return path


def _descriptor(tmp_path: Path) -> tuple[Path, dict]:
    private = tmp_path / "runtime-cache"
    private.mkdir(mode=0o700)
    private.chmod(0o700)
    resources = tmp_path / "App.app" / "Contents" / "Resources" / "runtime" / "payload"
    executables = {
        "paperclip": _executable(resources / "node" / "node"),
        "aioncore": _executable(resources / "aioncore" / "aioncore"),
        "backend": _executable(resources / "backend" / "opswitness-backend"),
        "codex": _executable(resources / "codex" / "codex"),
    }
    entries = []
    for path in sorted(executables.values()):
        entries.append(
            {
                "path": path.relative_to(resources).as_posix(),
                "kind": "file",
                "sha256": _sha256(path),
                "size": path.stat().st_size,
                "executable": True,
            }
        )
    manifest = resources / "resource-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "target": "aarch64-apple-darwin",
                "distribution_mode": "adhoc",
                "files": entries,
            }
        )
    )
    payload = {
        "schema_version": 1,
        "instance_id": "desktop-test-0001",
        "supervisor_pid": os.getpid(),
        "resource_root": str(resources),
        "resource_manifest": str(manifest),
        "resource_manifest_sha256": _sha256(manifest),
        "codex_executable": str(executables["codex"]),
        "processes": [
            {
                "name": name,
                "pid": os.getpid(),
                "executable": str(executables[name]),
                "port": 41000 + index,
            }
            for index, name in enumerate(("paperclip", "aioncore", "backend"))
        ],
    }
    descriptor = private / "instance.json"
    descriptor.write_text(json.dumps(payload))
    descriptor.chmod(0o600)
    return descriptor, payload


def _rewrite_descriptor_manifest(descriptor: Path, payload: dict, entries: list[dict]) -> None:
    manifest = Path(payload["resource_manifest"])
    manifest_payload = json.loads(manifest.read_text())
    manifest_payload["files"] = entries
    manifest.write_text(json.dumps(manifest_payload))
    payload["resource_manifest_sha256"] = _sha256(manifest)
    descriptor.write_text(json.dumps(payload))
    descriptor.chmod(0o600)


def test_desktop_runtime_descriptor_verifies_private_complete_inventory(
    tmp_path, monkeypatch
):
    descriptor, _ = _descriptor(tmp_path)
    monkeypatch.setenv(DESKTOP_RUNTIME_FILE_ENV, str(descriptor))

    runtime = load_desktop_runtime()

    assert runtime.instance_id == "desktop-test-0001"
    assert load_desktop_supervisor_instance_id(descriptor) == "desktop-test-0001"
    assert {process.name for process in runtime.processes} == {
        "paperclip",
        "aioncore",
        "backend",
    }
    assert runtime.codex_executable.name == "codex"


def test_desktop_runtime_descriptor_rejects_mode_symlink_and_unknown_process(
    tmp_path,
):
    descriptor, payload = _descriptor(tmp_path)
    descriptor.chmod(0o644)
    with pytest.raises(ValueError, match="mode 0600"):
        load_desktop_runtime(descriptor)

    descriptor.chmod(0o600)
    link = tmp_path / "instance-link.json"
    link.symlink_to(descriptor)
    with pytest.raises(ValueError, match="not a symlink"):
        load_desktop_runtime(link)

    payload["processes"][0]["name"] = "postgres"
    descriptor.write_text(json.dumps(payload))
    descriptor.chmod(0o600)
    with pytest.raises(ValueError, match="not allowed"):
        load_desktop_runtime(descriptor)


def test_desktop_runtime_descriptor_rejects_resource_tampering(tmp_path):
    descriptor, payload = _descriptor(tmp_path)
    Path(payload["codex_executable"]).write_text("tampered\n")

    with pytest.raises(ValueError, match="(size|digest) mismatch"):
        load_desktop_runtime(descriptor)


def test_desktop_runtime_descriptor_accepts_contained_relative_symlink(tmp_path):
    descriptor, payload = _descriptor(tmp_path)
    resources = Path(payload["resource_root"])
    target = resources / "paperclip" / "node_modules" / "tool" / "bin" / "tool.js"
    target.parent.mkdir(parents=True)
    target.write_text("#!/usr/bin/env node\n")
    link = resources / "paperclip" / "node_modules" / ".bin" / "tool"
    link.parent.mkdir(parents=True)
    link.symlink_to("../tool/bin/tool.js")
    entries = json.loads(Path(payload["resource_manifest"]).read_text())["files"]
    entries.extend(
        [
            {
                "path": target.relative_to(resources).as_posix(),
                "kind": "file",
                "sha256": _sha256(target),
                "size": target.stat().st_size,
                "executable": False,
            },
            {
                "path": link.relative_to(resources).as_posix(),
                "kind": "symlink",
                "target": "../tool/bin/tool.js",
            },
        ]
    )
    _rewrite_descriptor_manifest(descriptor, payload, entries)

    runtime = load_desktop_runtime(descriptor)

    assert runtime.resource_root == resources


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("/tmp/opswitness-outside", "must be relative"),
        ("../../../../../opswitness-outside", "escapes resource_root"),
        ("../missing/tool.js", "broken"),
    ],
)
def test_desktop_runtime_descriptor_rejects_unsafe_symlink(
    tmp_path,
    target,
    expected,
):
    descriptor, payload = _descriptor(tmp_path)
    resources = Path(payload["resource_root"])
    outside = tmp_path / "opswitness-outside"
    outside.write_text("outside")
    link = resources / "paperclip" / "node_modules" / ".bin" / "tool"
    link.parent.mkdir(parents=True)
    link.symlink_to(target)
    entries = json.loads(Path(payload["resource_manifest"]).read_text())["files"]
    entries.append(
        {
            "path": link.relative_to(resources).as_posix(),
            "kind": "symlink",
            "target": target,
        }
    )
    _rewrite_descriptor_manifest(descriptor, payload, entries)

    with pytest.raises(ValueError, match=expected):
        load_desktop_runtime(descriptor)


def test_desktop_doctor_uses_dynamic_bundle_boundary_not_system_tools(
    tmp_path, monkeypatch
):
    descriptor, _ = _descriptor(tmp_path)
    runtime = load_desktop_runtime(descriptor)
    config = tmp_path / "config"
    config.mkdir(mode=0o700)
    config.chmod(0o700)
    logs = tmp_path / "logs"
    logs.mkdir(mode=0o700)
    logs.chmod(0o700)
    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(config))
    monkeypatch.setenv("OPSWITNESS_DESKTOP_MODE", "1")
    settings = Settings(services={"log_dir": logs})

    result = run_doctor(
        settings_loader=lambda: settings,
        which=lambda name: (_ for _ in ()).throw(AssertionError(f"unexpected tool: {name}")),
        port_open=lambda host, port: host == "127.0.0.1" and port >= 41000,
        desktop_runtime_loader=lambda: runtime,
        desktop_process_identity=lambda process: (True, f"pid={process.pid} matched"),
    )

    checks = {check["name"]: check for check in result["checks"]}
    assert result["healthy"] is True
    assert checks["desktop_runtime_descriptor"]["status"] == "pass"
    assert checks["desktop_paperclip_port"]["detail"].startswith("127.0.0.1:41000")
    assert not {"node", "psql", "pg_dump", "age", "postgres_port"} & checks.keys()


def test_desktop_doctor_fails_closed_when_descriptor_is_incomplete(
    tmp_path, monkeypatch
):
    descriptor, _ = _descriptor(tmp_path)
    runtime = load_desktop_runtime(descriptor)
    incomplete = DesktopRuntime(
        instance_id=runtime.instance_id,
        supervisor_pid=runtime.supervisor_pid,
        resource_root=runtime.resource_root,
        resource_manifest=runtime.resource_manifest,
        resource_manifest_sha256=runtime.resource_manifest_sha256,
        codex_executable=runtime.codex_executable,
        processes=tuple(
            process
            for process in runtime.processes
            if process.name != "backend"
        ),
    )
    config = tmp_path / "config"
    config.mkdir(mode=0o700)
    config.chmod(0o700)
    logs = tmp_path / "logs"
    logs.mkdir(mode=0o700)
    logs.chmod(0o700)
    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(config))
    monkeypatch.setenv("OPSWITNESS_DESKTOP_MODE", "1")

    result = run_doctor(
        settings_loader=lambda: Settings(services={"log_dir": logs}),
        port_open=lambda host, port: True,
        desktop_runtime_loader=lambda: incomplete,
        desktop_process_identity=lambda process: (True, "matched"),
    )

    checks = {check["name"]: check for check in result["checks"]}
    assert result["healthy"] is False
    assert checks["desktop_backend_identity"]["status"] == "fail"
    assert checks["desktop_backend_port"]["status"] == "fail"


def test_desktop_backend_never_falls_back_to_launchd_or_open(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSWITNESS_DESKTOP_MODE", "1")
    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(tmp_path / "config"))
    settings = Settings(
        ledger_dir=tmp_path / "state" / "ledger",
        console={"state_dir": tmp_path / "state" / "console"},
        services={"log_dir": tmp_path / "logs"},
    )

    service = ConsoleService(settings, background=False)
    try:
        assert service._owns_aion_runtime is False
        assert service._owns_paperclip_runtime is False
    finally:
        service.close()


def test_desktop_drain_endpoint_requires_descriptor_identity_and_can_cancel(
    tmp_path, monkeypatch
):
    descriptor, payload = _descriptor(tmp_path)
    monkeypatch.setenv(DESKTOP_RUNTIME_FILE_ENV, str(descriptor))
    monkeypatch.setenv("OPSWITNESS_DESKTOP_MODE", "1")
    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(tmp_path / "config"))
    settings = Settings(
        ledger_dir=tmp_path / "state" / "ledger",
        console={"state_dir": tmp_path / "state" / "console", "port": 8765},
        services={"log_dir": tmp_path / "logs"},
    )
    service = ConsoleService(settings, background=False)
    try:
        app = create_app(settings, service=service)
        client = TestClient(app, base_url="http://127.0.0.1:8765")
        headers = {
            "Content-Type": "application/json",
            "X-QD-CSRF": app.state.csrf_token,
            "X-OpsWitness-Desktop-Instance": "desktop-test-wrong",
        }
        denied = client.post(
            "/api/v1/desktop/drain",
            headers=headers,
            json={"action": "begin"},
        )
        assert denied.status_code == 503

        headers["X-OpsWitness-Desktop-Instance"] = payload["instance_id"]
        begun = client.post(
            "/api/v1/desktop/drain",
            headers=headers,
            json={"action": "begin"},
        )
        assert begun.status_code == 200
        assert begun.json() == {
            "draining": True,
            "active_work": False,
            "active_work_ids": [],
        }
        cancelled = client.post(
            "/api/v1/desktop/drain",
            headers=headers,
            json={"action": "cancel"},
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["draining"] is False
    finally:
        service.close()


def _desktop_credentials(tmp_path: Path) -> Path:
    private = tmp_path / "runtime-cache"
    private.mkdir(mode=0o700)
    private.chmod(0o700)
    credentials = private / "paperclip-service.json"
    credentials.write_text(
        json.dumps(
            {
                "company_id": "company-test",
                "agent_id": "agent-test",
                "api_key": "paperclip-secret-test",
            }
        )
    )
    credentials.chmod(0o600)
    return credentials


def test_desktop_mcp_loads_private_credentials_without_leaving_file_pointer(
    tmp_path, monkeypatch
):
    credentials = _desktop_credentials(tmp_path)
    monkeypatch.setenv("OPSWITNESS_PAPERCLIP__COMPANY_ID", "")
    monkeypatch.setenv("OPSWITNESS_PAPERCLIP__API_KEY", "")
    monkeypatch.setenv("OPSWITNESS_DESKTOP_MODE", "1")
    monkeypatch.setenv(DESKTOP_CREDENTIAL_FILE_ENV, str(credentials))

    assert apply_desktop_mcp_credentials() is True
    assert os.environ["OPSWITNESS_PAPERCLIP__COMPANY_ID"] == "company-test"
    assert os.environ["OPSWITNESS_PAPERCLIP__API_KEY"] == "paperclip-secret-test"
    assert DESKTOP_CREDENTIAL_FILE_ENV not in os.environ


def test_desktop_mcp_credentials_fail_closed_on_mode_and_symlink(
    tmp_path, monkeypatch
):
    credentials = _desktop_credentials(tmp_path)
    credentials.chmod(0o644)
    monkeypatch.setenv("OPSWITNESS_DESKTOP_MODE", "1")
    with pytest.raises(ValueError, match="mode 0600"):
        load_desktop_paperclip_credentials(credentials)

    credentials.chmod(0o600)
    link = tmp_path / "credentials-link.json"
    link.symlink_to(credentials)
    with pytest.raises(ValueError, match="not a symlink"):
        load_desktop_paperclip_credentials(link)

    monkeypatch.delenv("OPSWITNESS_DESKTOP_MODE")
    with pytest.raises(ValueError, match="explicit desktop mode"):
        load_desktop_paperclip_credentials(credentials)
