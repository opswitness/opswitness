import json
import plistlib
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from quarterdeck.backup import (
    _pg_restore_command,
    _rebase_paperclip_config,
    backup_plan,
    create_backup,
    restore_plan,
)
from quarterdeck.cli import app
from quarterdeck.config import Settings
from quarterdeck.doctor import run_doctor
from quarterdeck.service import SERVICE_NAMES, build_service_exec, render_launchd


def _executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(0o755)
    return path


def _settings(tmp_path, monkeypatch) -> Settings:
    config = tmp_path / "config"
    config.mkdir(exist_ok=True)
    config.chmod(0o700)
    monkeypatch.setenv("QD_CONFIG_DIR", str(config))
    qd = _executable(tmp_path / "qd")
    node = _executable(tmp_path / "node")
    paperclip_script = tmp_path / "paperclip-index.js"
    paperclip_script.write_text("// fixture\n")
    return Settings(
        database_url="postgresql://qd:secret@127.0.0.1:5432/quarterdeck",
        paperclip={"api_key": "api-key", "company_id": "company"},
        services={
            "qd_bin": qd,
            "paperclip_command": [str(node), str(paperclip_script)],
            "paperclip_home": tmp_path / "paperclip",
            "log_dir": tmp_path / "logs",
        },
        backup={"directory": tmp_path / "backups", "age_recipient": "age1test"},
        ledger_dir=tmp_path / "state" / "ledger",
    )


def test_launchd_templates_are_valid_secret_free_and_render_absolute(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    for name in SERVICE_NAMES:
        rendered = render_launchd(name, settings)
        parsed = plistlib.loads(rendered)
        args = parsed["ProgramArguments"]
        assert args[0] == str(settings.services.qd_bin.resolve())
        assert "DATABASE_URL" not in rendered.decode()
        path = tmp_path / f"{name}.plist"
        path.write_bytes(rendered)
        result = subprocess.run(["plutil", "-lint", str(path)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


def test_service_exec_keeps_database_secret_out_of_argv(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    argv, env = build_service_exec("paperclip", settings)
    assert "secret" not in " ".join(argv)
    assert env["DATABASE_URL"] == settings.database_url
    assert env["PAPERCLIP_TELEMETRY_DISABLED"] == "1"
    assert argv[-1] == "run"
    onboard, _ = build_service_exec("paperclip", settings, paperclip_mode="onboard")
    assert onboard[-2:] == ["onboard", "--yes"]
    projector, projector_env = build_service_exec("projector", settings)
    assert projector == [str(settings.services.qd_bin.resolve()), "project"]
    assert "DATABASE_URL" not in projector_env


def test_service_render_is_dry_run_by_default(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    monkeypatch.setenv("QD_SERVICES__QD_BIN", str(settings.services.qd_bin))
    output = tmp_path / "rendered.plist"
    result = CliRunner().invoke(
        app, ["service", "render", "watchdog", "--output", str(output)]
    )
    assert result.exit_code == 0 and "com.quarterdeck.watchdog" in result.output
    assert not output.exists()


def test_doctor_fake_toolchain_all_green(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    tools = {name: str(_executable(tmp_path / name)) for name in ("node", "psql", "pg_dump", "age")}
    result = run_doctor(
        settings_loader=lambda: settings,
        which=lambda name: tools.get(name),
        version=lambda path, args: "test-version",
        port_open=lambda host, port: True,
        paperclip_processes=lambda: [123],
    )
    assert result["healthy"] is True
    assert all(check["status"] == "pass" for check in result["checks"])


def test_doctor_reports_missing_tools_without_traceback(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    result = run_doctor(
        settings_loader=lambda: settings,
        which=lambda name: None,
        version=lambda path, args: "unused",
        port_open=lambda host, port: False,
        paperclip_processes=lambda: [],
    )
    assert result["healthy"] is False
    failed = {check["name"] for check in result["checks"] if check["status"] == "fail"}
    assert {"node", "psql", "pg_dump", "age", "postgres_port", "paperclip_port"} <= failed


def test_backup_and_restore_are_non_mutating_by_default(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    output = tmp_path / "does-not-exist" / "backup.tar.age"
    plan = create_backup(settings, output)
    assert plan == backup_plan(settings, output)
    assert "secret" not in json.dumps(plan)
    assert not output.parent.exists()
    target = tmp_path / "isolated-restore"
    restored = restore_plan(
        settings,
        tmp_path / "backup.tar.age",
        tmp_path / "age.key",
        target,
        "qd_restore_smoke",
        3310,
    )
    assert restored["target_root"] == str(target.resolve()) and not target.exists()
    assert "already exist" in restored["precondition"]


def test_backup_execute_uses_secure_atomic_output(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    tools = tmp_path / "tools"
    tools.mkdir()
    pg_dump = tools / "pg_dump"
    pg_dump.write_text(
        "#!/bin/sh\nwhile [ $# -gt 0 ]; do\n"
        "  if [ \"$1\" = --file ]; then shift; printf DUMP > \"$1\"; exit 0; fi\n"
        "  shift\ndone\nexit 2\n"
    )
    age = tools / "age"
    age.write_text(
        "#!/bin/sh\nlast=\"\"\nfor arg in \"$@\"; do last=\"$arg\"; done\ncat \"$last\"\n"
    )
    pg_dump.chmod(0o755)
    age.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tools}:/bin:/usr/bin")
    settings.ledger_dir.mkdir(parents=True)
    (settings.ledger_dir / "events.jsonl").write_text("{}\n")
    output = settings.backup.directory / "test.tar.age"
    result = create_backup(settings, output, execute=True)
    assert result["executed"] is True and output.exists()
    assert output.stat().st_mode & 0o777 == 0o600
    assert not list(output.parent.glob("*.partial"))
    with __import__("tarfile").open(output, "r") as archive:
        assert {"database.dump", "quarterdeck_state/ledger/events.jsonl"} <= set(
            archive.getnames()
        )


def test_backup_refuses_insecure_existing_directory(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    settings.backup.directory.mkdir()
    settings.backup.directory.chmod(0o755)
    with pytest.raises(ValueError, match="0700"):
        create_backup(settings, settings.backup.directory / "x.age", execute=True)
    assert settings.backup.directory.stat().st_mode & 0o777 == 0o755


def test_restore_rejects_production_paths_ports_and_database_names(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    args = (settings, tmp_path / "b.age", tmp_path / "key")
    with pytest.raises(ValueError, match="isolated"):
        restore_plan(*args, settings.ledger_dir.parent, "qd_restore_x", 3310)
    with pytest.raises(ValueError, match="non-production"):
        restore_plan(*args, tmp_path / "restore", "qd_restore_x", 3100)
    with pytest.raises(ValueError, match="qd_restore_"):
        restore_plan(*args, tmp_path / "restore", "quarterdeck", 3310)


def test_restore_implementation_passes_explicit_database_name():
    assert _pg_restore_command("/opt/pg_restore", "qd_restore_smoke", Path("dump")) == [
        "/opt/pg_restore",
        "--exit-on-error",
        "--dbname",
        "qd_restore_smoke",
        "dump",
    ]


def test_restored_paperclip_paths_are_rebased_to_isolated_root(tmp_path):
    instance = tmp_path / "paperclip" / "instances" / "default"
    instance.mkdir(parents=True)
    config = {
        "server": {"port": 3100},
        "database": {
            "connectionString": "postgresql://user:secret@localhost/production",
            "embeddedPostgresDataDir": "/production/db",
            "backup": {"dir": "/production/backups"},
        },
        "logging": {"logDir": "/production/logs"},
        "storage": {"localDisk": {"baseDir": "/production/storage"}},
        "secrets": {"localEncrypted": {"keyFilePath": "/production/master.key"}},
    }
    (instance / "config.json").write_text(json.dumps(config))
    _rebase_paperclip_config(
        tmp_path,
        "postgresql://user:secret@localhost/production",
        "qd_restore_smoke",
        3310,
    )
    restored = json.loads((instance / "config.json").read_text())
    assert restored["server"]["port"] == 3310
    assert restored["database"]["connectionString"].endswith("/qd_restore_smoke")
    assert "/production/" not in json.dumps(restored)
    assert str(tmp_path) in restored["secrets"]["localEncrypted"]["keyFilePath"]


def test_doctor_cli_json_is_machine_readable(monkeypatch):
    monkeypatch.setattr(
        "quarterdeck.doctor.run_doctor",
        lambda: {"healthy": False, "checks": [{"name": "x", "status": "fail", "detail": "no"}]},
    )
    result = CliRunner().invoke(app, ["doctor", "--json"])
    assert result.exit_code == 1 and json.loads(result.output)["healthy"] is False


def test_doctor_rejects_duplicate_paperclip_processes(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    tools = {name: str(_executable(tmp_path / name)) for name in ("node", "psql", "pg_dump", "age")}
    result = run_doctor(
        settings_loader=lambda: settings,
        which=lambda name: tools.get(name),
        version=lambda path, args: "test",
        port_open=lambda host, port: True,
        paperclip_processes=lambda: [10, 11],
    )
    duplicate = next(check for check in result["checks"] if check["name"] == "paperclip_single_instance")
    assert result["healthy"] is False and duplicate["status"] == "fail"
