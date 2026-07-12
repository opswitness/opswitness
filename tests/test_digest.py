from datetime import UTC, datetime, timedelta

import respx
import yaml
from httpx import Response
from typer.testing import CliRunner

from quarterdeck.digest import build_digest, render_markdown, render_telegram_html
from quarterdeck.notify.telegram import _split


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


def test_digest_aggregates_windows_and_traceability():
    now = datetime.now(UTC)
    events = (
        _run_events("feed-monitor", "succeeded", now - timedelta(hours=1), "R1")
        + _run_events("feed-monitor", "failed", now - timedelta(hours=2), "R2")
        + _run_events("old-job", "succeeded", now - timedelta(hours=48), "R3")
    )
    d = build_digest(events, now, hours=24, missed=[], watchdog_coverage=True)
    assert d["total_runs"] == 2 and "old-job" not in d["jobs"]
    p = d["problems"][0]
    assert p["run_id"] == "R2" and p["ts"] and p["duration_s"] == 5.0  # traceable
    assert d["healthy"] is False
    md = render_markdown(d)
    assert "run=`R2`" in md and "execution-evidence-based" in md and "🔴" in md


def test_spawn_failed_is_never_green():
    now = datetime.now(UTC)
    events = [
        {"event_id": "E1", "kind": "run_started", "run_id": "RS",
         "ts": (now - timedelta(minutes=5)).isoformat(), "payload": {"job": "demo"}},
        {"event_id": "E2", "kind": "run_finished", "run_id": "RS",
         "ts": (now - timedelta(minutes=5)).isoformat(),
         "payload": {"job": "demo", "status": "spawn_failed", "exit_code": 127}},
    ]
    d = build_digest(events, now, missed=[], watchdog_coverage=True)
    assert d["problems"][0]["status"] == "spawn_failed"
    md = render_markdown(d)
    assert "❌" in md and "起失败 1" in md and "✅" not in md


def test_running_is_neutral_and_long_runners_counted():
    now = datetime.now(UTC)
    # Started 30h ago, still running: must appear despite starting outside the window.
    events = _run_events("long-job", "running", now, "RL", started_offset_h=30)
    d = build_digest(events, now, hours=24, missed=[], watchdog_coverage=True)
    assert d["jobs"]["long-job"]["running"] == 1
    assert d["healthy"] is True  # running alone is not a problem
    assert "✅" in render_markdown(d)


def test_no_coverage_is_never_green():
    now = datetime.now(UTC)
    events = _run_events("demo", "succeeded", now - timedelta(hours=1), "R1")
    d = build_digest(events, now, watchdog_coverage=False)
    assert d["healthy"] is False
    md = render_markdown(d)
    assert "coverage unavailable" in md and "漏跑 0" not in md and "🔴" in md


def test_digest_cli_exit_codes(tmp_path, monkeypatch):
    from quarterdeck.cli import app
    from quarterdeck.ledger import Ledger

    monkeypatch.setenv("QD_LEDGER_DIR", str(tmp_path / "ledger"))
    monkeypatch.setenv("QD_CONFIG_DIR", str(tmp_path / "conf"))
    led = Ledger(tmp_path / "ledger")
    led.append("run_started", "R9", {"job": "demo"})
    led.append("run_finished", "R9", {"job": "demo", "status": "succeeded", "exit_code": 0})

    r = CliRunner().invoke(app, ["digest"])  # no schedules.yaml -> coverage unavailable
    assert r.exit_code == 1 and "coverage unavailable" in r.output

    conf = tmp_path / "conf"
    conf.mkdir(parents=True, exist_ok=True)
    (conf / "schedules.yaml").write_text(
        yaml.safe_dump({"jobs": [{"job": "demo", "expected_interval_seconds": 999999}]})
    )
    r2 = CliRunner().invoke(app, ["digest"])
    assert r2.exit_code == 0 and "🟢" in r2.output


def test_telegram_html_renderer_and_paragraph_chunking():
    now = datetime.now(UTC)
    events = _run_events("feed<&>monitor", "failed", now - timedelta(hours=1), "R1")
    d = build_digest(events, now, missed=[], watchdog_coverage=True)
    html_text = render_telegram_html(d)
    assert "<b>" in html_text and "&lt;&amp;&gt;" in html_text  # escaped
    assert "#" not in html_text.split("\n")[0]  # no markdown headings

    paras = ["段落" + str(i) + " " + "x" * 500 for i in range(12)]
    chunks = _split("\n\n".join(paras))
    assert all(len(c) <= 3900 for c in chunks)
    for c in chunks:  # paragraph-aware: chunks never cut mid-line
        assert not c.startswith("x") and not c.endswith("段")


@respx.mock
def test_telegram_send_uses_parse_mode(monkeypatch, tmp_path):
    from quarterdeck.config import Settings
    from quarterdeck.notify.telegram import send_telegram

    monkeypatch.setenv("QD_CONFIG_DIR", str(tmp_path))
    (tmp_path / "secrets.yaml").write_text("telegram:\n  bot_token: T\n  chat_id: '42'\n")
    route = respx.post("https://api.telegram.org/botT/sendMessage").mock(
        return_value=Response(200, json={"ok": True})
    )
    assert send_telegram("<b>hi</b>", Settings(), parse_mode="HTML") is True
    body = route.calls[0].request.content
    assert b"parse_mode" in body and b"HTML" in body

    monkeypatch.setenv("QD_CONFIG_DIR", str(tmp_path / "empty"))
    assert send_telegram("hello", Settings()) is False
    assert route.call_count == 1
