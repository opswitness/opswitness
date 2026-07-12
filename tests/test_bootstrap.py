import fcntl
import os
import plistlib

import pytest
import yaml
from typer.testing import CliRunner

from quarterdeck.bootstrap import (
    GENERATED_NAME,
    USER_NAME,
    init_workspace,
    load_effective_schedules,
)
from quarterdeck.cli import app


def _plist(dir_path, label, interval=None, calendar=None, keepalive=False):
    data = {"Label": label, "ProgramArguments": ["/bin/sh", f"/opt/{label}.sh"]}
    if interval:
        data["StartInterval"] = interval
    if calendar:
        data["StartCalendarInterval"] = calendar
    if keepalive:
        data["KeepAlive"] = True
    with open(dir_path / f"{label}.plist", "wb") as f:
        plistlib.dump(data, f)


@pytest.fixture()
def real_machine_fixture(tmp_path):
    """Shape of the real finding: 41 plists — 7 interval, 2 calendar, 32 services,
    with short-name collisions (two gateways, two wakes)."""
    la = tmp_path / "LaunchAgents"
    la.mkdir()
    for i, name in enumerate(
        ["feed-monitor", "sox-monitor", "thirteenf-monitor", "insider-buyback-monitor",
         "positioning-probe", "cycle-top-monitor", "register-trigger"]
    ):
        _plist(la, f"com.tianyuzhou.{name}", interval=1500 * (i + 1))
    _plist(la, "com.tianyuzhou.tci-screen", calendar={"Hour": 7, "Minute": 30})
    _plist(la, "com.tianyuzhou.conviction-funnel", calendar={"Weekday": 0, "Hour": 20})
    _plist(la, "com.hermes.gateway", keepalive=True)
    _plist(la, "com.openclaw.gateway", keepalive=True)
    _plist(la, "com.a.wake")
    _plist(la, "com.b.wake")
    for i in range(28):  # updaters / login items — unscheduled services
        _plist(la, f"com.vendor{i}.updater", keepalive=(i % 2 == 0))
    return tmp_path, la


def test_default_run_enrolls_nothing_and_classifies(real_machine_fixture):
    tmp_path, la = real_machine_fixture
    cfg = tmp_path / "conf"
    summary = init_workspace(cfg, la)
    assert summary["counts"] == {"interval": 7, "calendar": 2, "service": 32}
    # Nothing is monitored until a human enrolls:
    eff = load_effective_schedules(cfg)
    assert eff["schedules"] == []
    assert eff["meta"]["candidates"] == 9 and eff["meta"]["services"] == 32


def test_collisions_kept_by_full_label(real_machine_fixture):
    tmp_path, la = real_machine_fixture
    summary = init_workspace(tmp_path / "conf", la)
    assert set(summary["collisions"]) == {"gateway", "wake", "updater"}
    gen = yaml.safe_load((tmp_path / "conf" / GENERATED_NAME).read_text())
    labels = [e["label"] for e in gen["entries"]]
    assert len(labels) == 41 and len(set(labels)) == 41  # nothing silently dropped
    dup_jobs = [e["job"] for e in gen["entries"] if e["label"].endswith(".gateway")]
    assert set(dup_jobs) == {"com.hermes.gateway", "com.openclaw.gateway"}  # job=label on dup


def test_user_file_is_never_rewritten(real_machine_fixture):
    tmp_path, la = real_machine_fixture
    cfg = tmp_path / "conf"
    init_workspace(cfg, la)
    user = cfg / USER_NAME
    custom = "# my precious comment\nenroll:\n  - \"com.tianyuzhou.*\"\nmystery_field: 42\n"
    user.write_text(custom)
    init_workspace(cfg, la)  # re-init regenerates the generated file only
    assert user.read_text() == custom  # byte-identical: comments + unknown fields survive


def test_enroll_globs_merge_and_services_excluded(real_machine_fixture):
    tmp_path, la = real_machine_fixture
    cfg = tmp_path / "conf"
    init_workspace(cfg, la)
    (cfg / USER_NAME).write_text(
        "enroll:\n  - 'com.tianyuzhou.*'\n  - 'com.hermes.gateway'\n  - 'com.nomatch.*'\n"
        "overrides:\n  com.tianyuzhou.feed-monitor:\n    grace_seconds: 60\n"
    )
    eff = load_effective_schedules(cfg)
    by_label = {s["label"]: s for s in eff["schedules"]}
    assert len(by_label) == 9  # 7 interval + 2 calendar; gateway is a service → excluded
    assert "com.hermes.gateway" not in by_label
    assert by_label["com.tianyuzhou.feed-monitor"]["grace_seconds"] == 60  # override wins
    calendar = by_label["com.tianyuzhou.tci-screen"]
    assert "expected_interval_seconds" not in calendar  # → watchdog unsupported, fail-closed
    assert eff["meta"]["unknown_enroll_patterns"] == ["com.nomatch.*"]


def test_drift_reported_between_inits(real_machine_fixture):
    tmp_path, la = real_machine_fixture
    cfg = tmp_path / "conf"
    init_workspace(cfg, la)
    _plist(la, "com.tianyuzhou.new-job", interval=600)
    (la / "com.vendor0.updater.plist").unlink()
    _plist(la, "com.tianyuzhou.feed-monitor", interval=3000)  # changed schedule
    summary = init_workspace(cfg, la)
    drift = summary["drift"]
    assert drift["added"] == ["com.tianyuzhou.new-job"]
    assert drift["removed"] == ["com.vendor0.updater"]
    assert "com.tianyuzhou.feed-monitor" in drift["changed"]


def test_corrupt_generated_is_rebuilt_corrupt_user_fails_loudly(real_machine_fixture):
    tmp_path, la = real_machine_fixture
    cfg = tmp_path / "conf"
    init_workspace(cfg, la)
    (cfg / GENERATED_NAME).write_text("{{{{not yaml")
    summary = init_workspace(cfg, la)  # machine file: rebuild + flag
    assert summary.get("generated_was_corrupt") is True
    (cfg / USER_NAME).write_text("enroll: [unclosed")
    with pytest.raises(ValueError):
        load_effective_schedules(cfg)  # user file: never guess, fail loudly


def test_concurrent_init_is_locked_out(real_machine_fixture):
    tmp_path, la = real_machine_fixture
    cfg = tmp_path / "conf"
    cfg.mkdir()
    holder = os.open(cfg / ".init.lock", os.O_CREAT | os.O_WRONLY, 0o600)
    fcntl.flock(holder, fcntl.LOCK_EX)
    try:
        with pytest.raises(RuntimeError):
            init_workspace(cfg, la)
    finally:
        os.close(holder)


def test_no_launchagents_dir_yields_empty_candidates(tmp_path):
    summary = init_workspace(tmp_path / "conf", tmp_path / "missing")
    assert summary["counts"] == {"interval": 0, "calendar": 0, "service": 0}
    assert not list((tmp_path / "conf").glob("*.qd-tmp"))  # atomic writes, no debris


def test_init_cli_end_to_end(real_machine_fixture, monkeypatch):
    tmp_path, la = real_machine_fixture
    monkeypatch.setenv("QD_CONFIG_DIR", str(tmp_path / "conf"))
    r = CliRunner().invoke(app, ["init", "--launchagents", str(la)])
    assert r.exit_code == 0
    assert "none enrolled automatically" in r.output
    assert "collisions" in r.output and "gateway" in r.output
    assert "enroll:" in r.output  # tells the human how to opt in
