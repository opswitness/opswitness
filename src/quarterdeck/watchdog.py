"""Missed-run detection over the ledger. Pure check function + thin CLI glue.

Interval jobs only for now (StartInterval-style). Calendar/cron expressions are a
known gap (croniter) — tracked for the fleet's calendar jobs before full rollout.
"""

from datetime import datetime
from typing import Any


def last_seen_by_job(events: list[dict[str, Any]]) -> dict[str, datetime]:
    seen: dict[str, datetime] = {}
    for e in events:
        if e.get("kind") not in ("run_started", "run_finished"):
            continue
        job = e.get("payload", {}).get("job")
        if not job:
            continue
        try:
            ts = datetime.fromisoformat(e["ts"])
        except (KeyError, ValueError):
            continue
        if job not in seen or ts > seen[job]:
            seen[job] = ts
    return seen


def check(
    schedules: list[dict[str, Any]],
    events: list[dict[str, Any]],
    now: datetime,
) -> list[dict[str, Any]]:
    """Return one entry per missed job: {job, reason, overdue_seconds?}."""
    seen = last_seen_by_job(events)
    missed: list[dict[str, Any]] = []
    for sched in schedules:
        if not sched.get("enabled", True):
            continue
        job = sched["job"]
        interval = sched.get("expected_interval_seconds")
        if interval is None:
            continue  # calendar jobs: not yet supported
        grace = sched.get("grace_seconds", 300)
        last = seen.get(job)
        if last is None:
            missed.append({"job": job, "reason": "never-run"})
            continue
        overdue = (now - last).total_seconds() - interval - grace
        if overdue > 0:
            missed.append(
                {"job": job, "reason": "overdue", "overdue_seconds": round(overdue)}
            )
    return missed
