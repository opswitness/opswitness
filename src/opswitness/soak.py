"""Append-only elapsed-time gates for canary and production soak evidence.

The contract freezes each job's interval and grace at start/reset time. A verdict is
always recomputed from the authoritative ledger; checkpoint events are audit snapshots,
never a second source of truth.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from opswitness.ledger import Ledger
from opswitness.lifecycle import fold_job_lifecycle
from opswitness.projector import pending_events
from opswitness.schedules import classify_schedule

CONTRACT_KINDS = {"soak_started", "soak_reset"}
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def _normal_name(name: str) -> str:
    name = name.strip()
    if not _NAME.fullmatch(name):
        raise ValueError("soak name must match [A-Za-z0-9][A-Za-z0-9._-]{0,63}")
    return name


def _contract_events(events: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [
        event
        for event in events
        if event.get("kind") in CONTRACT_KINDS
        and event.get("payload", {}).get("name") == name
    ]


def active_contract(events: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    """Return the latest contract in ledger commit order."""
    name = _normal_name(name)
    contracts = _contract_events(events, name)
    return contracts[-1] if contracts else None


def soak_names(events: list[dict[str, Any]]) -> list[str]:
    names = {
        str(event.get("payload", {}).get("name"))
        for event in events
        if event.get("kind") in CONTRACT_KINDS and event.get("payload", {}).get("name")
    }
    return sorted(names)


def _schedule_snapshot(
    jobs: Iterable[str], schedules: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    normalized = sorted({job.strip() for job in jobs if job.strip()})
    if not normalized:
        raise ValueError("at least one non-empty --job is required")
    by_job: dict[str, dict[str, Any]] = {}
    for candidate in schedules:
        job = candidate.get("job")
        if isinstance(job, str):
            if job in by_job:
                raise ValueError(f"duplicate effective schedule for {job}")
            by_job[job] = candidate

    snapshot: list[dict[str, Any]] = []
    for job in normalized:
        schedule = by_job.get(job)
        if schedule is None:
            raise ValueError(f"job is not enrolled in effective schedules: {job}")
        state = classify_schedule(schedule)
        if state != "active":
            raise ValueError(f"job schedule is not actively monitorable: {job} ({state})")
        interval = schedule.get("expected_interval_seconds")
        grace = schedule.get("grace_seconds", 300)
        if not isinstance(interval, (int, float)) or interval <= 0:
            raise ValueError(f"invalid interval for {job}")
        if not isinstance(grace, (int, float)) or grace <= 0:
            raise ValueError(f"invalid grace for {job}")
        snapshot.append(
            {
                "job": job,
                "expected_interval_seconds": float(interval),
                "grace_seconds": float(grace),
            }
        )
    return snapshot


def _anchor_start(
    events: list[dict[str, Any]], run_id: str, expected_job: str, now: datetime
) -> datetime:
    starts = [
        event
        for event in events
        if event.get("run_id") == run_id and event.get("kind") == "run_started"
    ]
    finishes = [
        event
        for event in events
        if event.get("run_id") == run_id and event.get("kind") == "run_finished"
    ]
    if len(starts) != 1 or len(finishes) != 1:
        raise ValueError("--since-run-id must identify exactly one complete ledger run")
    started, finished = starts[0], finishes[0]
    if started.get("payload", {}).get("job") != expected_job:
        raise ValueError("anchor run does not belong to the soak job")
    payload = finished.get("payload", {})
    if payload.get("job") != expected_job:
        raise ValueError("anchor finish does not belong to the soak job")
    if payload.get("status") != "succeeded" or payload.get("exit_code") != 0:
        raise ValueError("anchor run must have a successful exit-0 terminal event")
    if started.get("degraded") or finished.get("degraded"):
        raise ValueError("a degraded run cannot anchor a soak")
    started_at = _timestamp(started.get("ts"), "anchor run_started.ts")
    finished_at = _timestamp(finished.get("ts"), "anchor run_finished.ts")
    if finished_at < started_at:
        raise ValueError("anchor terminal timestamp precedes its start")
    if started_at > now:
        raise ValueError("anchor run starts in the future")
    return started_at


def record_contract(
    ledger: Ledger,
    name: str,
    jobs: Iterable[str],
    schedules: list[dict[str, Any]],
    *,
    minimum_seconds: int,
    reason: str,
    reset: bool = False,
    since_run_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Append a new start/reset contract after validating its evidence boundary."""
    name = _normal_name(name)
    reason = reason.strip()
    if not reason:
        raise ValueError("--reason must be non-empty")
    if minimum_seconds <= 0:
        raise ValueError("minimum duration must be positive")
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    now = now.astimezone(UTC)
    events = ledger.read_all()
    previous = active_contract(events, name)
    if reset and previous is None:
        raise ValueError(f"cannot reset unknown soak: {name}")
    if not reset and previous is not None:
        raise ValueError(f"soak already exists: {name}; use `qd soak reset`")

    snapshot = _schedule_snapshot(jobs, schedules)
    if since_run_id:
        if len(snapshot) != 1:
            raise ValueError("--since-run-id is supported only for a single-job soak")
        evidence_since = _anchor_start(events, since_run_id, snapshot[0]["job"], now)
    else:
        evidence_since = now

    payload: dict[str, Any] = {
        "schema_version": 1,
        "name": name,
        "reason": reason,
        "minimum_seconds": int(minimum_seconds),
        "evidence_since": evidence_since.isoformat(),
        "schedules": snapshot,
    }
    if since_run_id:
        payload["anchor_run_id"] = since_run_id
    if previous is not None:
        payload["replaces_event_id"] = previous["event_id"]
    kind = "soak_reset" if reset else "soak_started"
    event = ledger.append(kind, f"soak:{name}", payload, fsync=True)
    if event is None:
        raise OSError(f"could not durably append {kind}")
    return event


def _validated_contract(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("active soak contract has an unsupported schema")
    name = _normal_name(str(payload.get("name", "")))
    minimum = payload.get("minimum_seconds")
    schedules = payload.get("schedules")
    if not isinstance(minimum, int) or minimum <= 0:
        raise ValueError(f"soak {name} has an invalid minimum_seconds")
    if not isinstance(schedules, list) or not schedules:
        raise ValueError(f"soak {name} has no frozen schedules")
    snapshot = _schedule_snapshot(
        [str(schedule.get("job", "")) for schedule in schedules if isinstance(schedule, dict)],
        schedules,
    )
    if len(snapshot) != len(schedules):
        raise ValueError(f"soak {name} has duplicate or malformed schedules")
    return {
        **payload,
        "name": name,
        "minimum_seconds": minimum,
        "evidence_since": _timestamp(payload.get("evidence_since"), "evidence_since"),
        "schedules": snapshot,
    }


def contract_details(events: list[dict[str, Any]], name: str) -> dict[str, Any]:
    """Return the validated current contract for reset/UI callers."""
    event = active_contract(events, name)
    if event is None:
        raise ValueError(f"unknown soak: {_normal_name(name)}")
    return _validated_contract(event)


def _blocker(
    blockers: list[dict[str, Any]], code: str, severity: str, **detail: Any
) -> None:
    blockers.append({"code": code, "severity": severity, **detail})


def evaluate_soak(
    events: list[dict[str, Any]],
    name: str,
    now: datetime,
    current_schedules: list[dict[str, Any]],
    *,
    torn_files: Iterable[Path | str] = (),
) -> dict[str, Any]:
    """Recompute one soak verdict from ledger + current schedule state."""
    name = _normal_name(name)
    contract_event = active_contract(events, name)
    if contract_event is None:
        raise ValueError(f"unknown soak: {name}")
    contract = _validated_contract(contract_event)
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    now = now.astimezone(UTC)
    since: datetime = contract["evidence_since"]
    elapsed = (now - since).total_seconds()
    blockers: list[dict[str, Any]] = []
    if elapsed < 0:
        _blocker(blockers, "clock_before_evidence", "hard", seconds=round(-elapsed, 3))
        elapsed = 0.0

    torn = sorted(str(path) for path in torn_files)
    if torn:
        _blocker(blockers, "ledger_torn_lines", "hard", files=torn)

    current_by_job: dict[str, dict[str, Any]] = {}
    duplicate_current: set[str] = set()
    for schedule in current_schedules:
        job = schedule.get("job")
        if not isinstance(job, str):
            continue
        if job in current_by_job:
            duplicate_current.add(job)
        current_by_job[job] = schedule

    lifecycle = fold_job_lifecycle(events)
    per_job: dict[str, dict[str, Any]] = {}
    frozen_jobs = {schedule["job"] for schedule in contract["schedules"]}
    timed_event = tuple[datetime, dict[str, Any]]
    run_record = dict[str, list[timed_event]]
    run_events: dict[str, dict[str, run_record]] = {
        job: {} for job in frozen_jobs
    }

    for schedule in contract["schedules"]:
        job = schedule["job"]
        current = current_by_job.get(job)
        if job in duplicate_current:
            _blocker(blockers, "schedule_duplicate", "hard", job=job)
        elif current is None:
            _blocker(blockers, "schedule_missing", "hard", job=job)
        elif classify_schedule(current) != "active":
            _blocker(
                blockers,
                "schedule_not_active",
                "hard",
                job=job,
                state=classify_schedule(current),
            )
        else:
            current_interval = float(current["expected_interval_seconds"])
            current_grace = float(current.get("grace_seconds", 300))
            if (
                current_interval != schedule["expected_interval_seconds"]
                or current_grace != schedule["grace_seconds"]
            ):
                _blocker(blockers, "schedule_changed", "hard", job=job)

        lifecycle_state = lifecycle.get(job)
        if lifecycle_state and lifecycle_state.retired:
            _blocker(
                blockers,
                "job_resurrected" if lifecycle_state.resurrected else "job_retired",
                "hard",
                job=job,
            )

    for event in events:
        payload = event.get("payload", {})
        job = payload.get("job") if isinstance(payload, dict) else None
        if job not in frozen_jobs:
            continue
        kind = event.get("kind")
        if kind not in {"run_started", "run_finished", "tree_signal_degraded"}:
            continue
        try:
            event_time = _timestamp(event.get("ts"), f"event {event.get('event_id')} ts")
        except ValueError as exc:
            _blocker(blockers, "malformed_event_time", "hard", job=job, detail=str(exc))
            continue
        if event_time < since:
            continue
        if event_time > now:
            _blocker(
                blockers,
                "event_in_future",
                "hard",
                job=job,
                event_id=event.get("event_id"),
            )
            continue
        if event.get("degraded"):
            _blocker(
                blockers,
                "degraded_evidence",
                "hard",
                job=job,
                event_id=event.get("event_id"),
            )
        if kind == "tree_signal_degraded":
            _blocker(
                blockers,
                "tree_signal_degraded",
                "hard",
                job=job,
                event_id=event.get("event_id"),
            )
            continue
        run_id = event.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            _blocker(blockers, "malformed_run_id", "hard", job=job)
            continue
        record = run_events[str(job)].setdefault(run_id, {"starts": [], "finishes": []})
        record["starts" if kind == "run_started" else "finishes"].append((event_time, event))

    for schedule in contract["schedules"]:
        job = schedule["job"]
        threshold = schedule["expected_interval_seconds"] + schedule["grace_seconds"]
        starts: list[datetime] = []
        successes = 0
        failures = 0
        running = 0
        for run_id, record in run_events[job].items():
            if len(record["starts"]) != 1:
                _blocker(
                    blockers,
                    "duplicate_or_missing_start",
                    "hard",
                    job=job,
                    run_id=run_id,
                    count=len(record["starts"]),
                )
            else:
                starts.append(record["starts"][0][0])
            if len(record["finishes"]) > 1:
                _blocker(
                    blockers,
                    "duplicate_terminal",
                    "hard",
                    job=job,
                    run_id=run_id,
                    count=len(record["finishes"]),
                )
                failures += 1
                continue
            if not record["finishes"]:
                running += 1
                continue
            finish_time, finish = record["finishes"][0]
            if not record["starts"]:
                _blocker(blockers, "orphan_terminal", "hard", job=job, run_id=run_id)
                failures += 1
                continue
            if finish_time < record["starts"][0][0]:
                _blocker(blockers, "terminal_before_start", "hard", job=job, run_id=run_id)
                failures += 1
                continue
            finish_payload = finish.get("payload", {})
            status = finish_payload.get("status")
            exit_code = finish_payload.get("exit_code")
            if status == "succeeded" and exit_code == 0:
                successes += 1
            else:
                failures += 1
                _blocker(
                    blockers,
                    "run_not_succeeded",
                    "hard",
                    job=job,
                    run_id=run_id,
                    status=status,
                    exit_code=exit_code,
                )

        starts.sort()
        gaps: list[float] = []
        if starts:
            gaps.append((starts[0] - since).total_seconds())
            gaps.extend((right - left).total_seconds() for left, right in zip(starts, starts[1:]))
            gaps.append((now - starts[-1]).total_seconds())
        else:
            gaps.append(elapsed)
        max_gap = max(gaps, default=0.0)
        if max_gap > threshold:
            _blocker(
                blockers,
                "cadence_gap",
                "hard",
                job=job,
                max_gap_seconds=round(max_gap, 3),
                allowed_seconds=round(threshold, 3),
            )
        if successes == 0:
            _blocker(blockers, "no_successful_run", "pending", job=job)
        per_job[job] = {
            "starts": len(starts),
            "successes": successes,
            "failures": failures,
            "running": running,
            "last_started": starts[-1].isoformat() if starts else None,
            "max_gap_seconds": round(max_gap, 3),
            "allowed_gap_seconds": round(threshold, 3),
        }

    if elapsed < contract["minimum_seconds"]:
        _blocker(
            blockers,
            "minimum_duration",
            "pending",
            remaining_seconds=round(contract["minimum_seconds"] - elapsed, 3),
        )

    projection_backlog = len(pending_events(events))
    if projection_backlog:
        _blocker(
            blockers,
            "projection_backlog",
            "pending",
            pending_events=projection_backlog,
        )

    hard = any(blocker["severity"] == "hard" for blocker in blockers)
    state = "failed" if hard else "pending" if blockers else "passed"
    return {
        "schema_version": 1,
        "name": name,
        "state": state,
        "healthy": state == "passed",
        "contract_event_id": contract_event["event_id"],
        "contract_kind": contract_event["kind"],
        "evidence_since": since.isoformat(),
        "checked_at": now.isoformat(),
        "minimum_seconds": contract["minimum_seconds"],
        "elapsed_seconds": round(elapsed, 3),
        "remaining_seconds": round(max(0.0, contract["minimum_seconds"] - elapsed), 3),
        "anchor_run_id": contract.get("anchor_run_id"),
        "projection_backlog": projection_backlog,
        "jobs": per_job,
        "blockers": blockers,
    }


def evaluate_ledger_soak(
    ledger: Ledger,
    name: str,
    now: datetime,
    current_schedules: list[dict[str, Any]],
) -> dict[str, Any]:
    events = ledger.read_all()  # reading quarantines a newly discovered torn line
    torn = sorted(ledger.root.glob("*.jsonl.torn")) if ledger.root.exists() else []
    return evaluate_soak(events, name, now, current_schedules, torn_files=torn)


def record_checkpoint(
    ledger: Ledger,
    name: str,
    now: datetime,
    current_schedules: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Append a non-authoritative snapshot of the currently recomputed verdict."""
    events = ledger.read_all()
    result = evaluate_soak(
        events,
        name,
        now,
        current_schedules,
        torn_files=sorted(ledger.root.glob("*.jsonl.torn")),
    )
    payload = {
        "schema_version": 1,
        "name": result["name"],
        "contract_event_id": result["contract_event_id"],
        "checked_at": result["checked_at"],
        "state": result["state"],
        "blockers": result["blockers"],
        "ledger_tail_event_id": events[-1]["event_id"] if events else None,
    }
    event = ledger.append("soak_checkpoint", f"soak:{result['name']}", payload, fsync=True)
    if event is None:
        raise OSError("could not durably append soak_checkpoint")
    return result, event
