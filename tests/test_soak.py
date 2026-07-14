from datetime import UTC, datetime, timedelta

import pytest
from typer.testing import CliRunner

from quarterdeck.cli import app
from quarterdeck.ledger import Ledger
from quarterdeck.soak import (
    evaluate_ledger_soak,
    evaluate_soak,
    record_checkpoint,
    record_contract,
)


BASE = datetime(2026, 7, 13, 20, 0, tzinfo=UTC)
JOB = "com.example.canary"


def _schedule(job=JOB, interval=10, grace=2):
    return {
        "job": job,
        "expected_interval_seconds": interval,
        "grace_seconds": grace,
    }


def _contract(ts=BASE, *, kind="soak_started", event_id="C1", minimum=30):
    return {
        "event_id": event_id,
        "kind": kind,
        "run_id": "soak:canary",
        "ts": ts.isoformat(),
        "payload": {
            "schema_version": 1,
            "name": "canary",
            "reason": "test",
            "minimum_seconds": minimum,
            "evidence_since": ts.isoformat(),
            "schedules": [_schedule()],
        },
    }


def _run(run_id, started, *, status="succeeded", degraded=False, job=JOB):
    start_id = f"{run_id}-S"
    finish_id = f"{run_id}-F"
    start = {
        "event_id": start_id,
        "kind": "run_started",
        "run_id": run_id,
        "ts": started.isoformat(),
        "payload": {"job": job},
    }
    finish = {
        "event_id": finish_id,
        "kind": "run_finished",
        "run_id": run_id,
        "ts": (started + timedelta(seconds=1)).isoformat(),
        "payload": {
            "job": job,
            "status": status,
            "exit_code": 0 if status == "succeeded" else 1,
        },
    }
    if degraded:
        finish["degraded"] = True
    acks = [
        {
            "event_id": f"A-{event_id}",
            "kind": "projection_ack",
            "run_id": run_id,
            "ts": (started + timedelta(seconds=2)).isoformat(),
            "payload": {"event_id": event_id},
        }
        for event_id in (start_id, finish_id)
    ]
    return [start, finish, *acks]


def _passing_events():
    events = [_contract()]
    for index, offset in enumerate((0, 10, 20), start=1):
        events += _run(f"R{index}", BASE + timedelta(seconds=offset))
    return events


def test_soak_is_pending_until_minimum_elapsed():
    result = evaluate_soak(
        _passing_events(),
        "canary",
        BASE + timedelta(seconds=25),
        [_schedule()],
    )
    assert result["state"] == "pending"
    assert [item["code"] for item in result["blockers"]] == ["minimum_duration"]


def test_soak_passes_only_with_elapsed_cadence_success_and_acks():
    result = evaluate_soak(
        _passing_events(),
        "canary",
        BASE + timedelta(seconds=30),
        [_schedule()],
    )
    assert result["state"] == "passed"
    assert result["healthy"] is True
    assert result["jobs"][JOB]["successes"] == 3
    assert result["projection_backlog"] == 0


def test_one_manual_success_cannot_fake_continuous_soak():
    events = [_contract(), *_run("R1", BASE)]
    result = evaluate_soak(
        events,
        "canary",
        BASE + timedelta(seconds=30),
        [_schedule()],
    )
    assert result["state"] == "failed"
    assert any(item["code"] == "cadence_gap" for item in result["blockers"])


def test_multi_job_soak_starts_at_contract_and_requires_every_job(tmp_path):
    second_job = "com.example.second"
    schedules = [_schedule(), _schedule(job=second_job)]
    ledger = Ledger(tmp_path / "ledger")
    contract = record_contract(
        ledger,
        "production",
        [JOB, second_job],
        schedules,
        minimum_seconds=20,
        reason="post-canary production adoption",
        now=BASE,
    )
    assert contract["payload"]["evidence_since"] == BASE.isoformat()
    assert "anchor_run_id" not in contract["payload"]

    first_job_only = [contract]
    first_job_only += _run("A1", BASE, job=JOB)
    first_job_only += _run("A2", BASE + timedelta(seconds=10), job=JOB)
    pending = evaluate_soak(
        first_job_only,
        "production",
        BASE + timedelta(seconds=12),
        schedules,
    )
    assert pending["state"] == "pending"
    assert any(
        item["code"] == "no_successful_run" and item["job"] == second_job
        for item in pending["blockers"]
    )

    complete = list(first_job_only)
    complete += _run("B1", BASE, job=second_job)
    complete += _run("B2", BASE + timedelta(seconds=10), job=second_job)
    passed = evaluate_soak(
        complete,
        "production",
        BASE + timedelta(seconds=22),
        schedules,
    )
    assert passed["state"] == "passed"
    assert passed["healthy"] is True
    assert passed["jobs"][JOB]["successes"] == 2
    assert passed["jobs"][second_job]["successes"] == 2


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda events: events + _run("BAD", BASE + timedelta(seconds=25), status="failed"),
         "run_not_succeeded"),
        (lambda events: events + _run("DEG", BASE + timedelta(seconds=25), degraded=True),
         "degraded_evidence"),
        (
            lambda events: events
            + [
                {
                    "event_id": "TREE",
                    "kind": "tree_signal_degraded",
                    "run_id": "R2",
                    "ts": (BASE + timedelta(seconds=15)).isoformat(),
                    "degraded": True,
                    "payload": {"job": JOB, "survivors": [123]},
                }
            ],
            "tree_signal_degraded",
        ),
    ],
)
def test_bad_terminal_and_degraded_evidence_permanently_fail(mutation, expected):
    result = evaluate_soak(
        mutation(_passing_events()),
        "canary",
        BASE + timedelta(seconds=30),
        [_schedule()],
    )
    assert result["state"] == "failed"
    assert any(item["code"] == expected for item in result["blockers"])


def test_schedule_drift_and_torn_ledger_fail_closed():
    result = evaluate_soak(
        _passing_events(),
        "canary",
        BASE + timedelta(seconds=30),
        [_schedule(grace=99)],
        torn_files=["2026-07-13.jsonl.torn"],
    )
    codes = {item["code"] for item in result["blockers"]}
    assert result["state"] == "failed"
    assert {"schedule_changed", "ledger_torn_lines"} <= codes


def test_new_torn_line_fails_the_same_ledger_evaluation(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    record_contract(
        ledger,
        "canary",
        [JOB],
        [_schedule()],
        minimum_seconds=60,
        reason="test",
        now=BASE,
    )
    ledger_file = next(ledger.root.glob("*.jsonl"))
    with ledger_file.open("a") as stream:
        stream.write("{broken-json}\n")
    result = evaluate_ledger_soak(
        ledger, "canary", BASE + timedelta(seconds=1), [_schedule()]
    )
    assert result["state"] == "failed"
    assert any(item["code"] == "ledger_torn_lines" for item in result["blockers"])


def test_projection_backlog_keeps_gate_pending_not_green():
    events = _passing_events()
    events.append(
        {
            "event_id": "UNACKED",
            "kind": "run_started",
            "run_id": "R4",
            "ts": (BASE + timedelta(seconds=30)).isoformat(),
            "payload": {"job": JOB},
        }
    )
    result = evaluate_soak(events, "canary", BASE + timedelta(seconds=30), [_schedule()])
    assert result["state"] == "pending"
    assert result["projection_backlog"] == 1


def test_future_run_event_cannot_hide_the_trailing_cadence_gap():
    events = _passing_events()
    events += _run("FUTURE", BASE + timedelta(seconds=300))
    result = evaluate_soak(events, "canary", BASE + timedelta(seconds=30), [_schedule()])
    assert result["state"] == "failed"
    assert any(item["code"] == "event_in_future" for item in result["blockers"])


def test_reasoned_reset_excludes_prior_failure_but_keeps_history():
    old = [_contract(minimum=10), *_run("OLD", BASE, status="failed")]
    reset_at = BASE + timedelta(seconds=100)
    reset = _contract(reset_at, kind="soak_reset", event_id="C2", minimum=20)
    reset["payload"]["reason"] = "maintenance reset"
    reset["payload"]["replaces_event_id"] = "C1"
    events = [*old, reset]
    for index, offset in enumerate((0, 10), start=1):
        events += _run(f"NEW{index}", reset_at + timedelta(seconds=offset))
    result = evaluate_soak(
        events,
        "canary",
        reset_at + timedelta(seconds=20),
        [_schedule()],
    )
    assert result["state"] == "passed"
    assert result["contract_event_id"] == "C2"


def test_anchor_must_be_one_successful_non_degraded_run(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    started = ledger.append("run_started", "ANCHOR", {"job": JOB}, fsync=True)
    finished = ledger.append(
        "run_finished",
        "ANCHOR",
        {"job": JOB, "status": "succeeded", "exit_code": 0},
        fsync=True,
    )
    assert started and finished
    event = record_contract(
        ledger,
        "canary",
        [JOB],
        [_schedule()],
        minimum_seconds=60,
        reason="post-maintenance canary",
        since_run_id="ANCHOR",
    )
    assert event["payload"]["anchor_run_id"] == "ANCHOR"
    assert event["payload"]["evidence_since"] == started["ts"]

    with pytest.raises(ValueError, match="already exists"):
        record_contract(
            ledger,
            "canary",
            [JOB],
            [_schedule()],
            minimum_seconds=60,
            reason="duplicate",
        )


def test_checkpoint_is_append_only_snapshot_and_write_failure_is_fatal(tmp_path, monkeypatch):
    ledger = Ledger(tmp_path / "ledger")
    record_contract(
        ledger,
        "canary",
        [JOB],
        [_schedule()],
        minimum_seconds=60,
        reason="test",
        now=BASE,
    )
    result, event = record_checkpoint(
        ledger, "canary", BASE + timedelta(seconds=1), [_schedule()]
    )
    assert result["state"] == "pending"
    assert event["kind"] == "soak_checkpoint"
    assert event["payload"]["contract_event_id"] == result["contract_event_id"]

    monkeypatch.setattr(ledger, "append", lambda *args, **kwargs: None)
    with pytest.raises(OSError, match="soak_checkpoint"):
        record_checkpoint(ledger, "canary", BASE + timedelta(seconds=2), [_schedule()])


def test_soak_cli_start_status_and_reasoned_reset(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_LEDGER_DIR", str(tmp_path / "ledger"))
    monkeypatch.setenv("QD_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr("quarterdeck.cli._effective_soak_schedules", lambda: [_schedule()])
    runner = CliRunner()

    started = runner.invoke(
        app,
        [
            "soak",
            "start",
            "canary",
            "--job",
            JOB,
            "--minimum-hours",
            "0.001",
            "--reason",
            "cli test",
        ],
    )
    assert started.exit_code == 0, started.output

    status = runner.invoke(app, ["soak", "status", "canary", "--json"])
    assert status.exit_code == 1
    assert '"state": "pending"' in status.output

    reset = runner.invoke(
        app, ["soak", "reset", "canary", "--reason", "explicit maintenance"]
    )
    assert reset.exit_code == 0, reset.output
    kinds = [event["kind"] for event in Ledger(tmp_path / "ledger").read_all()]
    assert kinds == ["soak_started", "soak_reset"]


def test_unknown_soak_and_invalid_name_are_configuration_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_LEDGER_DIR", str(tmp_path / "ledger"))
    monkeypatch.setenv("QD_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr("quarterdeck.cli._effective_soak_schedules", lambda: [_schedule()])
    runner = CliRunner()
    unknown = runner.invoke(app, ["soak", "status", "missing"])
    invalid = runner.invoke(
        app, ["soak", "start", "bad name", "--job", JOB, "--reason", "test"]
    )
    assert unknown.exit_code == 2 and "unknown soak" in unknown.output
    assert invalid.exit_code == 2 and "soak name" in invalid.output
