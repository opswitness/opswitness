import plistlib

import yaml
from typer.testing import CliRunner

from quarterdeck.bootstrap import generate_schedules, init_workspace
from quarterdeck.cli import app


def _plist(dir_path, label, interval=None, calendar=None):
    data = {"Label": label, "ProgramArguments": ["/bin/true"]}
    if interval:
        data["StartInterval"] = interval
    if calendar:
        data["StartCalendarInterval"] = calendar
    with open(dir_path / f"{label}.plist", "wb") as f:
        plistlib.dump(data, f)


def test_init_creates_config_and_schedules(tmp_path):
    la = tmp_path / "LaunchAgents"
    la.mkdir()
    _plist(la, "com.t.feed-monitor", interval=1500)
    _plist(la, "com.t.tci-screen", calendar={"Hour": 7, "Minute": 30})

    cfg = tmp_path / "conf"
    summary = init_workspace(cfg, la)
    assert (cfg / "config.yaml").exists() and (cfg / "schedules.yaml").exists()
    assert summary["stats"] == {
        "discovered": 2,
        "added": 2,
        "kept": 0,
        "calendar_unsupported": 1,
    }
    jobs = {j["job"]: j for j in yaml.safe_load((cfg / "schedules.yaml").read_text())["jobs"]}
    assert jobs["feed-monitor"]["expected_interval_seconds"] == 1500
    assert jobs["feed-monitor"]["grace_seconds"] == 300
    assert "note" in jobs["tci-screen"]  # calendar: present but unsupported (fail-closed)


def test_reinit_preserves_user_edits_and_adds_new(tmp_path):
    la = tmp_path / "LaunchAgents"
    la.mkdir()
    _plist(la, "com.t.feed-monitor", interval=1500)
    cfg = tmp_path / "conf"
    init_workspace(cfg, la)

    # User tightens grace by hand.
    sched = cfg / "schedules.yaml"
    data = yaml.safe_load(sched.read_text())
    data["jobs"][0]["grace_seconds"] = 60
    sched.write_text(yaml.safe_dump(data))
    config_before = (cfg / "config.yaml").read_text()

    _plist(la, "com.t.sox-monitor", interval=21600)
    summary = init_workspace(cfg, la)
    assert summary["stats"]["kept"] == 1 and summary["stats"]["added"] == 1
    jobs = {j["job"]: j for j in yaml.safe_load(sched.read_text())["jobs"]}
    assert jobs["feed-monitor"]["grace_seconds"] == 60  # user edit survives re-init
    assert jobs["sox-monitor"]["expected_interval_seconds"] == 21600
    assert (cfg / "config.yaml").read_text() == config_before  # never overwritten


def test_generate_schedules_pure_merge():
    entries = [{"label": "com.t.a", "job": "a", "expected_interval_seconds": 100, "wrapped": False}]
    existing = {"jobs": [{"job": "a", "expected_interval_seconds": 999, "grace_seconds": 1}]}
    merged, stats = generate_schedules(entries, existing)
    assert merged["jobs"][0]["expected_interval_seconds"] == 999  # user wins
    assert stats == {"discovered": 1, "added": 0, "kept": 1, "calendar_unsupported": 0}


def test_init_cli_end_to_end(tmp_path, monkeypatch):
    la = tmp_path / "LaunchAgents"
    la.mkdir()
    _plist(la, "com.t.demo", interval=300)
    monkeypatch.setenv("QD_CONFIG_DIR", str(tmp_path / "conf"))
    r = CliRunner().invoke(app, ["init", "--launchagents", str(la)])
    assert r.exit_code == 0
    assert "1 jobs discovered" in r.output or "discovered" in r.output
    assert "qd wrap" in r.output  # tells the user it's usable immediately
