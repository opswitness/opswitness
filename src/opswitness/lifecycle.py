"""Fold append-only job lifecycle events into the current retirement verdict."""

from dataclasses import dataclass
from typing import Any


@dataclass
class JobLifecycle:
    retired: bool = False
    resurrected: bool = False
    reason: str | None = None
    event_id: str | None = None


def fold_job_lifecycle(events: list[dict[str, Any]]) -> dict[str, JobLifecycle]:
    """Fold in ledger commit order; only an explicit unretire clears resurrection."""
    states: dict[str, JobLifecycle] = {}
    for event in events:
        kind = event.get("kind")
        payload = event.get("payload", {})
        job = payload.get("job")
        if not job:
            continue
        job = str(job)
        if kind == "job_retired":
            states[job] = JobLifecycle(
                retired=True,
                resurrected=False,
                reason=payload.get("reason"),
                event_id=event.get("event_id"),
            )
        elif kind == "job_unretired":
            states[job] = JobLifecycle(
                retired=False,
                resurrected=False,
                reason=payload.get("reason"),
                event_id=event.get("event_id"),
            )
        elif kind == "run_started":
            state = states.get(job)
            if state and state.retired:
                state.resurrected = True
    return states


def lifecycle_sets(events: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    states = fold_job_lifecycle(events)
    retired = {job for job, state in states.items() if state.retired and not state.resurrected}
    resurrected = {job for job, state in states.items() if state.retired and state.resurrected}
    return retired, resurrected
