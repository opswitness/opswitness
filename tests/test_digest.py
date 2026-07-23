from datetime import UTC, datetime, timedelta

import respx
import yaml
from httpx import Response
from typer.testing import CliRunner

from opswitness.digest import build_digest, render_markdown, render_telegram_html
from opswitness.notify.telegram import _split


def _sched(*jobs):
    return [{"job": j, "expected_interval_seconds": 999999, "grace_seconds": 300} for j in jobs]


def _run_events(job, status, ts, run_id, started_offset_h=0.0):
    started = ts - timedelta(hours=started_offset_h)
    events = [
        {"event_id": f"{run_id}-S", "kind": "run_started", "run_id": run_id,
         "ts": started.isoformat(), "payload": {"job": job}},
    ]
    if status != "running":
        events.append(
            {"event_id": f"{run_id}-F", "kind": "run_finished", "run_id": run_id,
             "ts": (ts + timedelta(seconds=5)).isoformat(),
             "payload": {"job": job, "status": status, "duration_s": 5.0,
                         "exit_code": 0 if status == "succeeded" else 1}}
        )
    return events


def _lifecycle(kind, job, ts, event_id):
    return {
        "event_id": event_id,
        "kind": kind,
        "run_id": event_id,
        "ts": ts.isoformat(),
        "payload": {"schema_version": 1, "job": job, "reason": "test"},
    }


def test_digest_aggregates_windows_and_traceability():
    now = datetime.now(UTC)
    events = (
        _run_events("feed-monitor", "succeeded", now - timedelta(hours=1), "R1")
        + _run_events("feed-monitor", "failed", now - timedelta(hours=2), "R2")
        + _run_events("old-job", "succeeded", now - timedelta(hours=48), "R3")
    )
    d = build_digest(events, now, hours=24, missed=[], schedules=_sched("feed-monitor"))
    assert d["total_runs"] == 2 and "old-job" not in d["jobs"]  # window scopes STATS...
    # ...but never the coverage universe: old-job is ledger-known and unmonitored.
    assert d["coverage"]["status"] == "partial"
    assert d["coverage"]["observed_unregistered"] == ["old-job"]
    p = d["problems"][0]
    assert p["run_id"] == "R2" and p["ts"] and p["duration_s"] == 5.0
    assert d["healthy"] is False
    md = render_markdown(d)
    assert "run=`R2`" in md and "execution-evidence-based" in md and "🔴" in md


def test_partial_coverage_names_uncovered_jobs_and_is_never_green():
    now = datetime.now(UTC)
    events = (
        _run_events("covered-job", "succeeded", now - timedelta(hours=1), "R1")
        + _run_events("stray-job", "succeeded", now - timedelta(hours=1), "R2")
    )
    d = build_digest(events, now, missed=[], schedules=_sched("covered-job"))
    assert d["coverage"]["status"] == "partial"
    assert d["coverage"]["observed_unregistered"] == ["stray-job"]
    assert d["healthy"] is False  # partial coverage can never be green
    md = render_markdown(d)
    assert "覆盖不完整" in md and "stray-job" in md and "🔴" in md


def test_disabled_schedule_is_registered_not_covered():
    now = datetime.now(UTC)
    events = _run_events("demo", "succeeded", now - timedelta(hours=1), "R1")
    schedules = [{"job": "demo", "expected_interval_seconds": 999, "enabled": False}]
    d = build_digest(events, now, missed=[], schedules=schedules)
    # "in the file" is not "actively monitored": a lone disabled entry gives NO coverage.
    assert d["coverage"]["status"] == "none"
    assert d["coverage"]["observed_disabled"] == ["demo"]
    assert d["healthy"] is False


def test_unsupported_schedule_is_registered_not_covered():
    now = datetime.now(UTC)
    events = _run_events("cal-job", "succeeded", now - timedelta(hours=1), "R1")
    schedules = [{"job": "cal-job"}]  # calendar entry: no interval
    d = build_digest(events, now, missed=[], schedules=schedules)
    assert d["coverage"]["status"] == "none"
    assert d["coverage"]["observed_unsupported"] == ["cal-job"]
    assert d["healthy"] is False


def test_stray_outside_window_still_breaks_coverage_and_ledger_retire_excuses_it():
    now = datetime.now(UTC)
    events = (
        _run_events("covered-job", "succeeded", now - timedelta(hours=1), "R1")
        + _run_events("stray-old", "succeeded", now - timedelta(hours=48), "R2")
    )
    d = build_digest(events, now, hours=24, missed=[], schedules=_sched("covered-job"))
    assert d["coverage"]["status"] == "partial"  # ran 48h ago => still a stray today
    assert d["coverage"]["observed_unregistered"] == ["stray-old"]

    events.append(_lifecycle("job_retired", "stray-old", now, "RET1"))
    d2 = build_digest(events, now, hours=24, missed=[], schedules=_sched("covered-job"))
    assert d2["coverage"]["status"] == "full"  # the audited excuse path
    assert d2["coverage"]["retired"] == ["stray-old"]
    assert d2["healthy"] is True


def test_retired_job_running_in_window_resurfaces():
    now = datetime.now(UTC)
    events = _run_events("covered-job", "succeeded", now - timedelta(hours=1), "R1")
    events += [_lifecycle("job_retired", "zombie", now - timedelta(hours=3), "RET1")]
    events += _run_events("zombie", "succeeded", now - timedelta(hours=2), "R2")
    d = build_digest(events, now, hours=24, missed=[], schedules=_sched("covered-job"))
    assert d["coverage"]["status"] == "partial"
    assert d["coverage"]["resurrected"] == ["zombie"]
    assert d["healthy"] is False
    md = render_markdown(d)
    assert "退休后再次运行" in md and "zombie" in md


def test_unretire_clears_resurrection_but_returns_job_to_coverage_universe():
    now = datetime.now(UTC)
    events = [_lifecycle("job_retired", "zombie", now - timedelta(hours=3), "RET1")]
    events += _run_events("zombie", "succeeded", now - timedelta(hours=2), "R2")
    events += [_lifecycle("job_unretired", "zombie", now - timedelta(hours=1), "UNRET1")]
    d = build_digest(events, now, schedules=[])
    assert d["coverage"]["resurrected"] == []
    assert d["coverage"]["observed_unregistered"] == ["zombie"]


def test_none_coverage_still_names_known_gaps():
    now = datetime.now(UTC)
    events = _run_events("ghost-job", "succeeded", now - timedelta(hours=40), "R1")
    d = build_digest(events, now, hours=24, schedules=[])
    assert d["coverage"]["status"] == "none"
    md = render_markdown(d)
    assert "coverage unavailable" in md
    assert "ghost-job" in md  # historical gap named even with zero coverage
    tg = render_telegram_html(d)
    assert "ghost-job" in tg


def test_watchdog_refuses_green_on_empty_explicit_schedules(tmp_path, monkeypatch):
    from opswitness.cli import app
    from opswitness.ledger import Ledger

    monkeypatch.setenv("OPSWITNESS_LEDGER_DIR", str(tmp_path / "ledger"))
    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(tmp_path / "conf"))
    Ledger(tmp_path / "ledger").append("run_started", "R1", {"job": "demo"})
    empty = tmp_path / "empty.yaml"
    empty.write_text("")
    r = CliRunner().invoke(app, ["watchdog", "--schedules", str(empty)])
    assert r.exit_code == 2  # zero schedules can never verdict green
    assert "refusing" in r.output


def test_empty_schedules_is_no_coverage():
    now = datetime.now(UTC)
    events = _run_events("demo", "succeeded", now - timedelta(hours=1), "R1")
    d = build_digest(events, now, schedules=[])
    assert d["coverage"]["status"] == "none" and d["healthy"] is False
    md = render_markdown(d)
    assert "coverage unavailable" in md and "漏跑 0" not in md


def test_malformed_config_surfaces_as_coverage_error():
    now = datetime.now(UTC)
    d = build_digest([], now, schedules=[], coverage_error="schedules.yaml: invalid YAML")
    assert d["coverage"]["status"] == "none" and d["coverage"]["error"]
    assert "invalid YAML" in render_markdown(d)


def test_spawn_failed_is_never_green():
    now = datetime.now(UTC)
    events = [
        {"event_id": "E1", "kind": "run_started", "run_id": "RS",
         "ts": (now - timedelta(minutes=5)).isoformat(), "payload": {"job": "demo"}},
        {"event_id": "E2", "kind": "run_finished", "run_id": "RS",
         "ts": (now - timedelta(minutes=5)).isoformat(),
         "payload": {"job": "demo", "status": "spawn_failed", "exit_code": 127}},
    ]
    d = build_digest(events, now, missed=[], schedules=_sched("demo"))
    assert d["problems"][0]["status"] == "spawn_failed"
    md = render_markdown(d)
    assert "❌" in md and "起失败 1" in md and "✅" not in md


def test_running_renders_neutral_not_success():
    now = datetime.now(UTC)
    events = _run_events("long-job", "running", now, "RL", started_offset_h=30)
    d = build_digest(events, now, hours=24, missed=[], schedules=_sched("long-job"))
    assert d["jobs"]["long-job"]["running"] == 1
    assert d["healthy"] is True  # running doesn't flip red...
    md = render_markdown(d)
    assert "🔄" in md and "`long-job`" in md
    assert "✅ `long-job`" not in md  # ...but it must never wear a success mark
    tg = render_telegram_html(d)
    assert "🔄" in tg and "✅" not in tg


def test_digest_cli_exit_codes(tmp_path, monkeypatch):
    from opswitness.cli import app
    from opswitness.ledger import Ledger

    monkeypatch.setenv("OPSWITNESS_LEDGER_DIR", str(tmp_path / "ledger"))
    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(tmp_path / "conf"))
    led = Ledger(tmp_path / "ledger")
    led.append("run_started", "R9", {"job": "demo"})
    led.append("run_finished", "R9", {"job": "demo", "status": "succeeded", "exit_code": 0})

    r = CliRunner().invoke(app, ["digest"])  # nothing enrolled -> no coverage
    assert r.exit_code == 1 and "coverage unavailable" in r.output

    conf = tmp_path / "conf"
    conf.mkdir(parents=True, exist_ok=True)
    conf.chmod(0o700)
    (conf / "schedules.generated.yaml").write_text(
        yaml.safe_dump(
            {"version": 2, "entries": [
                {"label": "com.t.demo", "class": "interval",
                 "expected_interval_seconds": 999999, "grace_seconds": 300, "job": "demo"}]}
        )
    )
    (conf / "schedules.yaml").write_text('enroll:\n  - "com.t.demo"\n')
    r2 = CliRunner().invoke(app, ["digest"])
    assert r2.exit_code == 0 and "🟢" in r2.output

    # An unregistered job starts running -> partial coverage -> non-zero again.
    led.append("run_started", "R10", {"job": "stray"})
    led.append("run_finished", "R10", {"job": "stray", "status": "succeeded", "exit_code": 0})
    r3 = CliRunner().invoke(app, ["digest"])
    assert r3.exit_code == 1 and "stray" in r3.output and "覆盖不完整" in r3.output


def test_telegram_long_fields_clipped_and_chunks_never_cut_tags():
    now = datetime.now(UTC)
    huge_job = "j" * 5000
    events = _run_events(huge_job, "failed", now - timedelta(hours=1), "R1")
    d = build_digest(events, now, missed=[], schedules=_sched(huge_job))
    tg = render_telegram_html(d)
    for line in tg.split("\n"):
        assert len(line) < 3000  # clipped fields keep every line far below the chunk limit
    chunks = _split(tg)
    assert all(len(c) <= 3900 for c in chunks)
    for c in chunks:
        assert c.count("<code>") == c.count("</code>")  # no tag split across chunks


def test_legacy_schedules_validation_matrix(tmp_path):
    import pytest

    from opswitness.bootstrap import load_legacy_schedules

    empty = tmp_path / "empty.yaml"
    empty.write_text("")
    assert load_legacy_schedules(empty) == []  # valid-empty => no coverage downstream

    bad = tmp_path / "bad.yaml"
    bad.write_text("{{{{nope")
    with pytest.raises(ValueError, match="invalid YAML"):
        load_legacy_schedules(bad)

    seq = tmp_path / "seq.yaml"
    seq.write_text("- a\n- b\n")
    with pytest.raises(ValueError, match="mapping"):
        load_legacy_schedules(seq)

    scalar_jobs = tmp_path / "scalar.yaml"
    scalar_jobs.write_text("jobs: 3\n")
    with pytest.raises(ValueError, match="schema violation"):
        load_legacy_schedules(scalar_jobs)

    with pytest.raises(ValueError, match="not found"):
        load_legacy_schedules(tmp_path / "missing.yaml")

    retired = tmp_path / "retired.yaml"
    retired.write_text("retired: [old-job]\n")
    with pytest.raises(ValueError, match="opswitness retire"):
        load_legacy_schedules(retired)


def test_retire_and_unretire_cli_are_append_only(tmp_path, monkeypatch):
    from opswitness.cli import app
    from opswitness.ledger import Ledger

    ledger_dir = tmp_path / "ledger"
    monkeypatch.setenv("OPSWITNESS_LEDGER_DIR", str(ledger_dir))
    runner = CliRunner()
    retired = runner.invoke(app, ["retire", "old-job", "--reason", "decommissioned"])
    assert retired.exit_code == 0 and "retired: old-job" in retired.output
    unretired = runner.invoke(app, ["unretire", "old-job", "--reason", "restored"])
    assert unretired.exit_code == 0 and "unretired: old-job" in unretired.output
    events = Ledger(ledger_dir).read_all()
    assert [event["kind"] for event in events] == ["job_retired", "job_unretired"]
    assert all(event["payload"]["schema_version"] == 1 for event in events)


def test_explicit_schedules_empty_file_no_traceback(tmp_path, monkeypatch):
    from opswitness.cli import app
    from opswitness.ledger import Ledger

    monkeypatch.setenv("OPSWITNESS_LEDGER_DIR", str(tmp_path / "ledger"))
    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(tmp_path / "conf"))
    Ledger(tmp_path / "ledger").append("run_started", "R1", {"job": "demo"})
    empty = tmp_path / "empty.yaml"
    empty.write_text("")
    r = CliRunner().invoke(app, ["digest", "--schedules", str(empty)])
    assert r.exit_code == 1  # unhealthy, but a report — never a traceback
    assert "coverage unavailable" in r.output

    bad = tmp_path / "bad.yaml"
    bad.write_text("{{{{nope")
    r2 = CliRunner().invoke(app, ["digest", "--schedules", str(bad)])
    assert r2.exit_code == 1 and "invalid YAML" in r2.output

    r3 = CliRunner().invoke(app, ["watchdog", "--schedules", str(bad)])
    assert r3.exit_code == 2  # watchdog: same validator, clean refusal


@respx.mock
def test_telegram_send_uses_parse_mode(monkeypatch, tmp_path):
    from opswitness.config import Settings
    from opswitness.notify.telegram import send_telegram

    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(tmp_path))
    tmp_path.chmod(0o700)
    secrets = tmp_path / "secrets.yaml"
    secrets.write_text("telegram:\n  bot_token: T\n  chat_id: '42'\n")
    secrets.chmod(0o600)
    route = respx.post("https://api.telegram.org/botT/sendMessage").mock(
        return_value=Response(200, json={"ok": True})
    )
    assert send_telegram("<b>hi</b>", Settings(), parse_mode="HTML") is True
    body = route.calls[0].request.content
    assert b"parse_mode" in body and b"HTML" in body

    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(tmp_path / "empty"))
    assert send_telegram("hello", Settings()) is False
    assert route.call_count == 1
