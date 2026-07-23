from datetime import UTC, datetime, timedelta

from typer.testing import CliRunner

from opswitness.digest import build_digest, render_page_html


def _run_events(job, status, ts, run_id):
    return [
        {"event_id": f"{run_id}-S", "kind": "run_started", "run_id": run_id,
         "ts": ts.isoformat(), "payload": {"job": job}},
        {"event_id": f"{run_id}-F", "kind": "run_finished", "run_id": run_id,
         "ts": (ts + timedelta(seconds=5)).isoformat(),
         "payload": {"job": job, "status": status, "duration_s": 5.0,
                     "exit_code": 0 if status == "succeeded" else 1}},
    ]


def _sched(*jobs):
    return [{"job": j, "expected_interval_seconds": 999999, "grace_seconds": 300} for j in jobs]


def test_html_report_is_selfcontained_and_escaped():
    now = datetime.now(UTC)
    hostile = 'job<script>alert("x")</script>'
    events = _run_events(hostile, "failed", now - timedelta(hours=1), "R1")
    d = build_digest(events, now, missed=[], schedules=_sched(hostile))
    page = render_page_html(d)
    assert page.startswith("<!doctype html>")
    assert "<script>alert" not in page  # hostile job name escaped
    assert "&lt;script&gt;" in page
    assert "http://" not in page and "https://" not in page  # no external assets
    assert "prefers-color-scheme" in page  # dark mode handled
    assert "R1" in page and "今日问题" in page  # traceable problem row present
    assert "🔴" in page  # failed run: never a green banner


def test_html_report_outcome_section_and_verdict():
    now = datetime.now(UTC)
    events = _run_events("demo", "succeeded", now - timedelta(hours=1), "R1")
    d = build_digest(events, now, missed=[], schedules=_sched("demo"))
    page = render_page_html(d)
    assert "🟢" in page and "outcome evidence" in page
    assert "execution evidence 证明进程行为" in page  # honesty footer preserved


def test_digest_cli_writes_html_file(tmp_path, monkeypatch):
    from opswitness.cli import app
    from opswitness.ledger import Ledger

    monkeypatch.setenv("OPSWITNESS_LEDGER_DIR", str(tmp_path / "ledger"))
    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(tmp_path / "conf"))
    led = Ledger(tmp_path / "ledger")
    led.append("run_started", "R9", {"job": "demo"})
    led.append("run_finished", "R9", {"job": "demo", "status": "succeeded", "exit_code": 0})
    out = tmp_path / "report" / "digest.html"
    result = CliRunner().invoke(app, ["digest", "--html", str(out)])
    assert out.exists()
    text = out.read_text()
    assert text.startswith("<!doctype html>") and "demo" in text
    assert oct(out.stat().st_mode & 0o777) == "0o600"
    assert result.exit_code in (0, 1)  # exit code still carries health, not file success
