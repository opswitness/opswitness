import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import respx
from httpx import Response
from typer.testing import CliRunner

from opswitness.artifacts import (
    artifact_root,
    evaluate_artifact,
    register_artifact,
    register_console_artifact,
    signoff_artifact,
    verify_registration,
)
from opswitness.cli import app
from opswitness.digest import build_digest, render_markdown
from opswitness.index import query_artifacts, rebuild
from opswitness.ledger import Ledger
from opswitness.paperclip import PaperclipClient
from opswitness.projector import Projector, pending_events

BASE = "http://paperclip.test"


def _seed_run(ledger: Ledger, run_id="run-1", job="artifact-job"):
    started = ledger.append("run_started", run_id, {"job": job, "argv": ["true"]})
    finished = ledger.append(
        "run_finished",
        run_id,
        {"job": job, "status": "succeeded", "exit_code": 0, "duration_s": 0.1},
    )
    assert started and finished
    return started, finished


def _ack(ledger: Ledger, *events):
    for event in events:
        ledger.append(
            "projection_ack",
            event["run_id"],
            {"event_id": event["event_id"], "remote_kind": "fixture", "remote_id": "x"},
        )


def test_cas_survives_source_overwrite_and_preserves_multiple_lineages(tmp_path):
    ledger = Ledger(tmp_path / "state" / "ledger")
    _seed_run(ledger)
    source = tmp_path / "report.txt"
    source.write_text("immutable report v1")
    first = register_artifact(
        ledger,
        source,
        run_id="run-1",
        logical_name="report.txt",
        labels=["requires-signoff", "report"],
    )
    second = register_artifact(ledger, source, run_id="run-1", logical_name="report-copy.txt")
    assert first["event_id"] != second["event_id"]
    assert first["payload"]["sha256"] == second["payload"]["sha256"]
    source.write_text("overwritten source v2")
    assert verify_registration(ledger, first)["ok"] is True
    target = artifact_root(ledger) / "sha256" / first["payload"]["sha256"][:2]
    assert [path for path in target.iterdir() if path.is_file()] == [
        target / first["payload"]["sha256"]
    ]


def test_console_artifact_registration_is_plan_bound_and_idempotent(tmp_path):
    ledger = Ledger(tmp_path / "state" / "ledger")
    source = tmp_path / "report.pdf"
    source.write_bytes(b"synthetic pdf")

    first = register_console_artifact(
        ledger,
        source,
        plan_id="01KXRXK1BHC8RDEJGXNZNVGM3G",
        logical_name="report.pdf",
        labels=["console-output"],
        paperclip_issue_id="issue-1",
    )
    repeated = register_console_artifact(
        ledger,
        source,
        plan_id="01KXRXK1BHC8RDEJGXNZNVGM3G",
        logical_name="report.pdf",
        labels=["console-output"],
        paperclip_issue_id="issue-1",
    )

    assert repeated["event_id"] == first["event_id"]
    assert first["run_id"] == "01KXRXK1BHC8RDEJGXNZNVGM3G"
    assert first["payload"]["plan_id"] == first["run_id"]
    assert first["payload"]["job"] == f"console:{first['run_id']}"
    assert first["payload"]["paperclip_issue_id"] == "issue-1"
    assert verify_registration(ledger, first)["ok"] is True
    assert (
        len([event for event in ledger.read_all() if event["kind"] == "artifact_registered"]) == 1
    )


def test_cas_corruption_is_visible_and_cli_returns_nonzero(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir(mode=0o700)
    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(config))
    monkeypatch.setenv("OPSWITNESS_LEDGER_DIR", str(tmp_path / "state" / "ledger"))
    ledger = Ledger(tmp_path / "state" / "ledger")
    _seed_run(ledger)
    source = tmp_path / "artifact.bin"
    source.write_bytes(b"good bytes")
    event = register_artifact(ledger, source, run_id="run-1", logical_name="artifact.bin")
    cas = (
        artifact_root(ledger)
        / "sha256"
        / event["payload"]["sha256"][:2]
        / event["payload"]["sha256"]
    )
    cas.write_bytes(b"corrupt")
    assert verify_registration(ledger, event)["ok"] is False
    result = CliRunner().invoke(app, ["artifacts", "verify", event["event_id"]])
    assert result.exit_code == 1
    assert json.loads(result.output)[0]["reason"] == "digest_or_size_mismatch"


def test_artifact_cli_register_list_show_eval_signoff(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir(mode=0o700)
    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(config))
    monkeypatch.setenv("OPSWITNESS_LEDGER_DIR", str(tmp_path / "state" / "ledger"))
    ledger = Ledger(tmp_path / "state" / "ledger")
    _seed_run(ledger)
    source = tmp_path / "report.md"
    source.write_text("# Report")
    runner = CliRunner()
    registered = runner.invoke(
        app,
        [
            "artifacts",
            "register",
            str(source),
            "--run-id",
            "run-1",
            "--label",
            "requires-signoff",
        ],
    )
    assert registered.exit_code == 0
    event_id = json.loads(registered.output)["event_id"]
    assert event_id in runner.invoke(app, ["artifacts", "list"]).output
    evaluated = runner.invoke(
        app,
        [
            "artifacts",
            "eval",
            event_id,
            "--verdict",
            "pass",
            "--evaluator",
            "golden-test",
            "--summary",
            "all checks pass",
        ],
    )
    assert evaluated.exit_code == 0
    signed = runner.invoke(
        app,
        [
            "artifacts",
            "signoff",
            event_id,
            "--decision",
            "approved",
            "--signed-by",
            "reviewer@example.test",
            "--note",
            "approved for delivery",
        ],
    )
    assert signed.exit_code == 0
    shown = json.loads(runner.invoke(app, ["artifacts", "show", event_id]).output)
    assert [item["kind"] for item in shown["outcomes"]] == [
        "artifact_eval",
        "artifact_signoff",
    ]


def test_artifact_index_is_rebuilt_from_ledger(tmp_path):
    ledger = Ledger(tmp_path / "state" / "ledger")
    _seed_run(ledger)
    source = tmp_path / "x.json"
    source.write_text("{}")
    event = register_artifact(ledger, source, run_id="run-1", logical_name="x.json")
    evaluate_artifact(
        ledger,
        event["event_id"],
        verdict="pass",
        evaluator="schema",
        summary="valid",
    )
    db = tmp_path / "index.db"
    info = rebuild(db, ledger)
    assert info["artifacts"] == 1
    rows = query_artifacts(db, run_id="run-1")
    assert rows[0]["sha256"] == event["payload"]["sha256"]


def test_artifact_index_excludes_erased_run_content(tmp_path):
    ledger = Ledger(tmp_path / "state" / "ledger")
    _seed_run(ledger)
    source = tmp_path / "private.json"
    source.write_text('{"private":true}')
    event = register_artifact(
        ledger,
        source,
        run_id="run-1",
        logical_name="private.json",
    )
    evaluate_artifact(
        ledger,
        event["event_id"],
        verdict="pass",
        evaluator="schema",
        summary="valid",
    )
    ledger.append(
        "task_run_erased",
        "run-1",
        {
            "schema_version": 1,
            "source": "local_console",
            "plan_sha256": "0" * 64,
        },
        fsync=True,
    )

    db = tmp_path / "index.db"
    info = rebuild(db, ledger)
    assert info["artifacts"] == 0
    assert query_artifacts(db, run_id="run-1") == []


def test_artifact_index_concurrent_rebuilds_publish_complete_databases(tmp_path):
    ledger = Ledger(tmp_path / "state" / "ledger")
    _seed_run(ledger)
    source = tmp_path / "x.json"
    source.write_text("{}")
    event = register_artifact(ledger, source, run_id="run-1", logical_name="x.json")
    db = tmp_path / "index.db"

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: rebuild(db, ledger), range(32)))

    assert {result["runs"] for result in results} == {1}
    assert {result["artifacts"] for result in results} == {1}
    rows = query_artifacts(db, run_id="run-1")
    assert [row["event_id"] for row in rows] == [event["event_id"]]
    assert not list(tmp_path.glob(".index.db.*.qd-index-tmp*"))


def test_digest_separates_execution_and_outcome_evidence(tmp_path):
    ledger = Ledger(tmp_path / "state" / "ledger")
    _seed_run(ledger)
    source = tmp_path / "report.pdf"
    source.write_bytes(b"pdf")
    event = register_artifact(
        ledger,
        source,
        run_id="run-1",
        logical_name="report.pdf",
        labels=["requires-signoff"],
    )
    schedule = [{"job": "artifact-job", "expected_interval_seconds": 3600}]
    pending = build_digest(ledger.read_all(), datetime.now(UTC), schedules=schedule)
    assert pending["healthy"] is False
    assert pending["outcomes"]["pending_required"] == 1
    evaluate_artifact(
        ledger,
        event["event_id"],
        verdict="fail",
        evaluator="pdf-check",
        summary="broken",
    )
    failed = build_digest(ledger.read_all(), datetime.now(UTC), schedules=schedule)
    assert failed["outcomes"]["eval_fail"] == 1 and failed["outcomes"]["problems"]
    evaluate_artifact(
        ledger,
        event["event_id"],
        verdict="pass",
        evaluator="pdf-check",
        summary="valid",
    )
    signoff_artifact(
        ledger,
        event["event_id"],
        decision="changes_requested",
        signed_by="reviewer",
        note="fix citations",
    )
    changes = build_digest(ledger.read_all(), datetime.now(UTC), schedules=schedule)
    assert changes["outcomes"]["changes_requested"] == 1
    signoff_artifact(
        ledger,
        event["event_id"],
        decision="approved",
        signed_by="reviewer",
        note="ship",
    )
    approved = build_digest(ledger.read_all(), datetime.now(UTC), schedules=schedule)
    assert approved["healthy"] is True
    report = render_markdown(approved)
    assert "execution evidence" in report and "outcome evidence" in report
    assert "report.pdf" in report and "signoff=approved" in report


def _projector(ledger, tmp_path):
    return Projector(
        ledger,
        PaperclipClient(BASE, "test", "company-1"),
        tmp_path / "projector.lease",
    )


@respx.mock
def test_artifact_projects_to_work_product_and_lost_ack_reconciles(tmp_path):
    ledger = Ledger(tmp_path / "state" / "ledger")
    run_events = _seed_run(ledger)
    _ack(ledger, *run_events)
    source = tmp_path / "report.txt"
    source.write_text("report")
    artifact = register_artifact(ledger, source, run_id="run-1", logical_name="report.txt")
    evaluate_artifact(
        ledger,
        artifact["event_id"],
        verdict="pass",
        evaluator="schema",
        summary="valid",
    )
    signoff_artifact(
        ledger,
        artifact["event_id"],
        decision="approved",
        signed_by="reviewer",
        note="ship",
    )
    respx.get(f"{BASE}/api/companies/company-1/issues").mock(
        return_value=Response(200, json=[{"id": "issue-1", "title": "[qd] artifact-job"}])
    )
    products = respx.get(f"{BASE}/api/issues/issue-1/work-products").mock(
        return_value=Response(200, json=[])
    )
    created = respx.post(f"{BASE}/api/issues/issue-1/work-products").mock(
        return_value=Response(200, json={"id": "wp-1"})
    )
    respx.get(f"{BASE}/api/issues/issue-1/comments").mock(return_value=Response(200, json=[]))
    comments = respx.post(f"{BASE}/api/issues/issue-1/comments").mock(
        return_value=Response(200, json={"id": "comment-1"})
    )
    stats = _projector(ledger, tmp_path).drain()
    assert stats["projected"] == 3 and stats["pending_after"] == 0
    body = json.loads(created.calls[0].request.content)
    assert body["externalId"] == artifact["event_id"]
    assert body["metadata"]["sha256"] == artifact["payload"]["sha256"]
    assert comments.call_count == 2

    # Lost local ack copy: remote externalId reconciles, never reposts.
    other = Ledger(tmp_path / "other" / "ledger")
    other.root.mkdir(parents=True, exist_ok=True)
    (other.root / "2026-07-12.jsonl").write_text(json.dumps(artifact) + "\n")
    # Copy the immutable blob to the isolated ledger's CAS to make the fixture valid.
    digest = artifact["payload"]["sha256"]
    target = artifact_root(other) / "sha256" / digest[:2]
    target.mkdir(parents=True)
    source_blob = artifact_root(ledger) / "sha256" / digest[:2] / digest
    (target / digest).write_bytes(source_blob.read_bytes())
    products.return_value = Response(200, json=[{"externalId": artifact["event_id"]}])
    reconciled = _projector(other, tmp_path / "other").drain()
    assert reconciled["reconciled"] == 1
    assert created.call_count == 1


@respx.mock
def test_artifact_projection_failure_stays_pending(tmp_path):
    ledger = Ledger(tmp_path / "state" / "ledger")
    run_events = _seed_run(ledger)
    _ack(ledger, *run_events)
    source = tmp_path / "report.txt"
    source.write_text("report")
    artifact = register_artifact(ledger, source, run_id="run-1", logical_name="report.txt")
    evaluate_artifact(
        ledger,
        artifact["event_id"],
        verdict="pass",
        evaluator="schema",
        summary="valid",
    )
    respx.get(f"{BASE}/api/companies/company-1/issues").mock(
        return_value=Response(200, json=[{"id": "issue-1", "title": "[qd] artifact-job"}])
    )
    respx.get(f"{BASE}/api/issues/issue-1/work-products").mock(return_value=Response(200, json=[]))
    respx.post(f"{BASE}/api/issues/issue-1/work-products").mock(
        return_value=Response(500, text="down")
    )
    stats = _projector(ledger, tmp_path).drain()
    assert stats["skipped_errors"] == 1 and stats["blocked"] == 1
    assert stats["pending_after"] == 2
    assert len(pending_events(ledger.read_all())) == 2
