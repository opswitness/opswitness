import plistlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from quarterdeck.adopt import apply, is_wrapped, plan, rollback, scan
from quarterdeck.watchdog import check


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


def test_watchdog_detects_overdue_and_never_run():
    now = datetime.now(UTC)
    schedules = [
        {"job": "fresh", "expected_interval_seconds": 1500, "grace_seconds": 300},
        {"job": "stale", "expected_interval_seconds": 1500, "grace_seconds": 300},
        {"job": "ghost", "expected_interval_seconds": 1500},
        {"job": "disabled", "expected_interval_seconds": 60, "enabled": False},
    ]
    events = [
        _event("fresh", now - timedelta(seconds=600)),
        _event("stale", now - timedelta(seconds=4000)),
    ]
    missed = check(schedules, events, now)
    by_job = {m["job"]: m for m in missed}
    assert set(by_job) == {"stale", "ghost"}
    assert by_job["stale"]["reason"] == "overdue" and by_job["stale"]["overdue_seconds"] > 0
    assert by_job["ghost"]["reason"] == "never-run"
