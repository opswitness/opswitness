import plistlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from opswitness.adopt import apply, is_wrapped, plan, rollback, scan
from opswitness.watchdog import check


def _write_plist(dir_path: Path, label: str, **extra) -> Path:
    data = {
        "Label": label,
        "ProgramArguments": ["/bin/sh", "/Users/x/feed_monitor_run.sh"],
        "StartInterval": 1500,
        **extra,
    }
    p = dir_path / f"{label}.plist"
    with open(p, "wb") as f:
        plistlib.dump(data, f)
    return p


def test_scan_inventories_schedule_and_wrapped_state(tmp_path):
    _write_plist(tmp_path, "com.t.feed-monitor")
    entries = scan(tmp_path)
    assert entries[0]["job"] == "feed-monitor"
    assert entries[0]["expected_interval_seconds"] == 1500
    assert entries[0]["wrapped"] is False


def test_plan_wraps_command_and_is_idempotent(tmp_path):
    p = _write_plist(tmp_path, "com.t.sox-monitor")
    planned = plan(p, "/opt/qd", "sox-monitor")
    assert planned is not None
    _old, new_bytes, diff = planned
    data = plistlib.loads(new_bytes)
    assert data["ProgramArguments"][:5] == ["/opt/qd", "wrap", "--job", "sox-monitor", "--"]
    assert data["ProgramArguments"][5:] == ["/bin/sh", "/Users/x/feed_monitor_run.sh"]
    assert "wrapped" in diff
    assert is_wrapped(data)
    # Idempotence: planning an already-wrapped plist is refused.
    p.write_bytes(new_bytes)
    assert plan(p, "/opt/qd", "sox-monitor") is None


def test_opswitness_wrapper_is_also_idempotent(tmp_path):
    p = _write_plist(tmp_path, "com.t.opswitness-monitor")
    planned = plan(p, "/opt/opswitness", "com.t.opswitness-monitor")
    assert planned is not None
    _old, new_bytes, _diff = planned
    data = plistlib.loads(new_bytes)
    assert data["ProgramArguments"][0] == "/opt/opswitness"
    assert is_wrapped(data)
    p.write_bytes(new_bytes)
    assert plan(p, "/opt/opswitness", "com.t.opswitness-monitor") is None


def test_dry_run_never_writes_apply_backs_up_rollback_restores(tmp_path):
    p = _write_plist(tmp_path, "com.t.demo")
    pristine = p.read_bytes()
    planned = plan(p, "/opt/qd", "demo")
    assert planned is not None
    assert p.read_bytes() == pristine  # plan() is pure — dry-run untouched

    _old, new_bytes, _diff = planned
    backup = apply(p, new_bytes)
    assert backup.exists() and backup.read_bytes() == pristine
    assert p.read_bytes() == new_bytes

    # Second apply must not clobber the pristine backup.
    apply(p, new_bytes + b"\n")
    assert backup.read_bytes() == pristine

    assert rollback(p) is True
    assert p.read_bytes() == pristine  # byte-identical restore


def _event(job: str, ts: datetime) -> dict:
    return {"kind": "run_started", "ts": ts.isoformat(), "payload": {"job": job}}


def test_watchdog_detects_overdue_never_run_and_unsupported():
    now = datetime.now(UTC)
    schedules = [
        {"job": "fresh", "expected_interval_seconds": 1500, "grace_seconds": 300},
        {"job": "stale", "expected_interval_seconds": 1500, "grace_seconds": 300},
        {"job": "ghost", "expected_interval_seconds": 1500},
        {"job": "disabled", "expected_interval_seconds": 60, "enabled": False},
        {"job": "calendar-job"},  # no interval: must fail closed, never a green light
    ]
    events = [
        _event("fresh", now - timedelta(seconds=600)),
        _event("stale", now - timedelta(seconds=4000)),
        _event("calendar-job", now),
    ]
    missed = check(schedules, events, now)
    by_job = {m["job"]: m for m in missed}
    assert set(by_job) == {"stale", "ghost", "calendar-job"}
    assert by_job["stale"]["reason"] == "overdue" and by_job["stale"]["overdue_seconds"] > 0
    assert by_job["ghost"]["reason"] == "never-run"
    assert by_job["calendar-job"]["reason"] == "unsupported"


def test_watchdog_loop_mode_is_refused(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from opswitness.cli import app

    monkeypatch.setenv("OPSWITNESS_LEDGER_DIR", str(tmp_path / "ledger"))
    result = CliRunner().invoke(app, ["watchdog", "--loop"])
    assert result.exit_code == 2


def test_watchdog_refuses_all_disabled_explicit_schedules(tmp_path, monkeypatch):
    import yaml
    from typer.testing import CliRunner

    from opswitness.cli import app

    path = tmp_path / "disabled.yaml"
    path.write_text(
        yaml.safe_dump(
            {"jobs": [{"job": "disabled", "expected_interval_seconds": 60, "enabled": False}]}
        )
    )
    monkeypatch.setenv("OPSWITNESS_LEDGER_DIR", str(tmp_path / "ledger"))
    result = CliRunner().invoke(app, ["watchdog", "--schedules", str(path)])
    assert result.exit_code == 2
    assert "no active interval schedules" in result.output


def test_resolve_qd_bin_requires_absolute_executable(tmp_path):
    import pytest

    from opswitness.adopt import resolve_qd_bin

    with pytest.raises(ValueError):
        resolve_qd_bin(str(tmp_path / "does-not-exist"))
    fake = tmp_path / "qd"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    assert resolve_qd_bin(str(fake)) == str(fake)


def test_adopt_defaults_to_full_label_id(tmp_path):
    from typer.testing import CliRunner

    from opswitness.adopt import collisions, scan
    from opswitness.cli import app

    _write_plist(tmp_path, "com.a.gateway")
    _write_plist(tmp_path, "com.b.gateway")
    dup = collisions(scan(tmp_path))
    assert dup == {"gateway": ["com.a.gateway", "com.b.gateway"]}  # reported for display

    fake_qd = tmp_path / "qd"
    fake_qd.write_text("#!/bin/sh\n")
    fake_qd.chmod(0o755)
    r = CliRunner().invoke(
        app,
        ["adopt", "launchd", "com.a.gateway", "--dir", str(tmp_path), "--qd-bin", str(fake_qd)],
    )
    # Full label is the default job ID: unique by construction, collisions are moot,
    # and the ID can never drift when a neighbor appears later.
    assert r.exit_code == 0 and "dry-run" in r.output
    assert r.output.count("com.a.gateway") >= 2  # Label + --job value in the diff


def test_apply_leaves_no_temp_file(tmp_path):
    p = _write_plist(tmp_path, "com.t.atomic")
    planned = plan(p, "/opt/qd", "atomic")
    assert planned is not None
    apply(p, planned[1])
    assert not list(tmp_path.glob(".*.qd-tmp"))  # atomic rename completed, no debris


def test_apply_preserves_file_mode(tmp_path):
    import stat

    p = _write_plist(tmp_path, "com.t.mode")
    p.chmod(0o640)
    planned = plan(p, "/opt/qd", "mode")
    assert planned is not None
    backup = apply(p, planned[1])
    assert stat.S_IMODE(p.stat().st_mode) == 0o640
    assert stat.S_IMODE(backup.stat().st_mode) == 0o640


def test_half_written_backup_cannot_be_mistaken_for_pristine(tmp_path):
    from opswitness.adopt import BACKUP_SUFFIX, _publish_backup

    p = _write_plist(tmp_path, "com.t.crash")
    pristine = p.read_bytes()
    backup = p.with_suffix(p.suffix + BACKUP_SUFFIX)

    # Simulate a crashed earlier attempt: a stale unique temp survives in the dir.
    stale = tmp_path / f".{backup.name}.stale123.qd-tmp"
    stale.write_bytes(b"TRUNCATED")

    _publish_backup(backup, pristine, 0o644)
    assert backup.read_bytes() == pristine  # published atomically, complete
    # A second publish attempt never clobbers the pristine backup.
    _publish_backup(backup, b"different", 0o644)
    assert backup.read_bytes() == pristine
    assert not list(tmp_path.glob(f".{backup.name}.*.qd-tmp")) or stale.exists()
