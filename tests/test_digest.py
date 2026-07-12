from datetime import UTC, datetime, timedelta

import respx
from httpx import Response
from typer.testing import CliRunner

from quarterdeck.digest import build_digest, render_markdown


def _run_events(job: str, status: str, ts: datetime, run_id: str) -> list[dict]:
    return [
        {
            "event_id": f"{run_id}-S",
            "kind": "run_started",
            "run_id": run_id,
            "ts": ts.isoformat(),
            "payload": {"job": job},
        },
        {
            "event_id": f"{run_id}-F",
            "kind": "run_finished",
            "run_id": run_id,
            "ts": (ts + timedelta(seconds=5)).isoformat(),
            "payload": {"job": job, "status": status, "exit_code": 0 if status == "succeeded" else 1},
        },
    ]


def test_digest_aggregates_and_windows():
    now = datetime.now(UTC)
    events = (
        _run_events("feed-monitor", "succeeded", now - timedelta(hours=1), "R1")
        + _run_events("feed-monitor", "failed", now - timedelta(hours=2), "R2")
        + _run_events("old-job", "succeeded", now - timedelta(hours=48), "R3")  # outside window
    )
    d = build_digest(events, now, hours=24)
    assert d["total_runs"] == 2 and "old-job" not in d["jobs"]
    assert d["jobs"]["feed-monitor"]["failed"] == 1
    assert d["problems"] == [{"job": "feed-monitor", "status": "failed", "exit_code": 1}]

    md = render_markdown(d)
    assert "feed-monitor" in md and "今日问题" in md and "❌" in md


def test_digest_cli_runs_without_telegram(tmp_path, monkeypatch):
    from quarterdeck.cli import app
    from quarterdeck.ledger import Ledger

    monkeypatch.setenv("QD_LEDGER_DIR", str(tmp_path / "ledger"))
    monkeypatch.setenv("QD_CONFIG_DIR", str(tmp_path / "conf"))
    led = Ledger(tmp_path / "ledger")
    led.append("run_started", "R9", {"job": "demo"})
    led.append("run_finished", "R9", {"job": "demo", "status": "succeeded", "exit_code": 0})
    r = CliRunner().invoke(app, ["digest"])
    assert r.exit_code == 0 and "demo" in r.output and "舰队日报" in r.output


@respx.mock
def test_telegram_send_chunks_and_reports(monkeypatch, tmp_path):
    from quarterdeck.config import Settings
    from quarterdeck.notify.telegram import send_telegram

    monkeypatch.setenv("QD_CONFIG_DIR", str(tmp_path))
    (tmp_path / "secrets.yaml").write_text("telegram:\n  bot_token: T\n  chat_id: '42'\n")
    route = respx.post("https://api.telegram.org/botT/sendMessage").mock(
        return_value=Response(200, json={"ok": True})
    )
    assert send_telegram("x" * 5000, Settings()) is True
    assert route.call_count == 2  # chunked at 3900

    # Unconfigured: refuse quietly with False, zero network calls.
    monkeypatch.setenv("QD_CONFIG_DIR", str(tmp_path / "empty"))
    assert send_telegram("hello", Settings()) is False
    assert route.call_count == 2
