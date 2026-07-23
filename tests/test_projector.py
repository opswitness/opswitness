import fcntl
import os

import respx
from httpx import Response

from opswitness.artifacts import register_console_artifact
from opswitness.ledger import Ledger
from opswitness.paperclip import PaperclipClient
from opswitness.projector import Projector, pending_events, qd_metadata

BASE = "http://pp.test"


def _seed_run(led: Ledger, job: str = "demo") -> list[str]:
    e1 = led.append("run_started", "01RUN", {"job": job, "argv": ["true"]})
    e2 = led.append(
        "run_finished",
        "01RUN",
        {"job": job, "exit_code": 0, "status": "succeeded", "duration_s": 0.1},
    )
    assert e1 and e2
    return [e1["event_id"], e2["event_id"]]


def _client() -> PaperclipClient:
    return PaperclipClient(BASE, "test-key", "c1")


@respx.mock
def test_drain_projects_creates_issue_and_acks(tmp_path):
    led = Ledger(tmp_path / "ledger")
    _seed_run(led)
    respx.get(f"{BASE}/api/companies/c1/issues").mock(
        return_value=Response(200, json={"issues": []})
    )
    respx.post(f"{BASE}/api/companies/c1/issues").mock(
        return_value=Response(200, json={"id": "iss-1"})
    )
    respx.get(f"{BASE}/api/issues/iss-1/comments").mock(
        return_value=Response(200, json={"comments": []})
    )
    posted = respx.post(f"{BASE}/api/issues/iss-1/comments").mock(
        return_value=Response(200, json={"id": "c-1"})
    )

    stats = Projector(led, _client(), tmp_path / "lease").drain()
    assert stats["projected"] == 2 and stats["pending_after"] == 0
    assert posted.call_count == 2
    assert all("metadata" not in call.request.content.decode() for call in posted.calls)
    assert all("qd:event:" in call.request.content.decode() for call in posted.calls)
    events = led.read_all()
    assert sum(1 for e in events if e["kind"] == "projection_ack") == 2

    # Second drain: everything acked — zero new remote writes.
    stats2 = Projector(led, _client(), tmp_path / "lease").drain()
    assert stats2["projected"] == 0 and stats2["pending_after"] == 0
    assert posted.call_count == 2


@respx.mock
def test_lost_ack_is_reconciled_without_repost(tmp_path):
    led = Ledger(tmp_path / "ledger")
    ids = _seed_run(led)
    remote_comments = [
        {"body": f"whatever qd:event:{ids[0]}", "metadata": {}},
        {"body": "no marker here", "metadata": qd_metadata(ids[1])},
    ]
    respx.get(f"{BASE}/api/companies/c1/issues").mock(
        return_value=Response(200, json={"issues": [{"id": "iss-9", "title": "[qd] demo"}]})
    )
    respx.get(f"{BASE}/api/issues/iss-9/comments").mock(
        return_value=Response(200, json={"comments": remote_comments})
    )
    posted = respx.post(f"{BASE}/api/issues/iss-9/comments").mock(
        return_value=Response(200, json={"id": "never"})
    )

    stats = Projector(led, _client(), tmp_path / "lease").drain()
    assert stats["reconciled"] == 2 and stats["projected"] == 0
    assert posted.call_count == 0  # crash-window duplicates healed, not reposted
    assert stats["pending_after"] == 0


@respx.mock
def test_console_artifact_projects_to_bound_work_issue(tmp_path):
    led = Ledger(tmp_path / "ledger")
    source = tmp_path / "report.pdf"
    source.write_bytes(b"report")
    event = register_console_artifact(
        led,
        source,
        plan_id="01PLAN",
        logical_name="report.pdf",
        paperclip_issue_id="work-issue-1",
    )
    listed_issues = respx.get(f"{BASE}/api/companies/c1/issues").mock(
        return_value=Response(200, json={"issues": []})
    )
    respx.get(f"{BASE}/api/issues/work-issue-1/work-products").mock(
        return_value=Response(200, json={"workProducts": []})
    )
    posted = respx.post(f"{BASE}/api/issues/work-issue-1/work-products").mock(
        return_value=Response(200, json={"id": "product-1"})
    )

    stats = Projector(led, _client(), tmp_path / "lease").drain()

    assert stats["projected"] == 1
    assert stats["pending_after"] == 0
    assert listed_issues.call_count == 0
    assert posted.call_count == 1
    assert event["event_id"] in posted.calls[0].request.content.decode()


@respx.mock
def test_paperclip_down_leaves_events_pending(tmp_path):
    led = Ledger(tmp_path / "ledger")
    _seed_run(led)
    respx.get(f"{BASE}/api/companies/c1/issues").mock(return_value=Response(500, text="boom"))

    stats = Projector(led, _client(), tmp_path / "lease").drain()
    assert stats["projected"] == 0
    assert stats["skipped_errors"] == 1 and stats["blocked"] == 1  # fail-stop per job
    assert stats["pending_after"] == 2
    assert all(e["kind"] != "projection_ack" for e in led.read_all())


def test_lease_excludes_second_projector(tmp_path):
    led = Ledger(tmp_path / "ledger")
    _seed_run(led)
    lease = tmp_path / "lease"
    lease.parent.mkdir(parents=True, exist_ok=True)
    holder = os.open(lease, os.O_CREAT | os.O_WRONLY, 0o600)
    fcntl.flock(holder, fcntl.LOCK_EX)
    try:
        stats = Projector(led, _client(), lease).drain()
        assert stats["projected"] == 0 and stats["skipped_errors"] == 1
    finally:
        os.close(holder)
    assert len(pending_events(led.read_all())) == 2  # untouched


def test_index_and_cli_status(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from opswitness.cli import app
    from opswitness.config import Settings
    from opswitness.index import job_summary, query_runs, rebuild

    monkeypatch.setenv("OPSWITNESS_LEDGER_DIR", str(tmp_path / "ledger"))
    led = Ledger(Settings().ledger_dir)
    _seed_run(led, job="feed-monitor")

    db = tmp_path / "index.db"
    info = rebuild(db, led)
    assert info["runs"] == 1 and info["pending_projection"] == 2
    runs = query_runs(db)
    assert runs[0]["job"] == "feed-monitor" and runs[0]["status"] == "succeeded"
    assert job_summary(db)[0]["last_status"] == "succeeded"

    r = CliRunner().invoke(app, ["status"])
    assert r.exit_code == 0 and "feed-monitor" in r.output
    r2 = CliRunner().invoke(app, ["runs"])
    assert r2.exit_code == 0 and "feed-monitor" in r2.output
