"""One monitorability classifier shared by bootstrap, watchdog, and digest."""

from typing import Any, Literal

ScheduleState = Literal["active", "disabled", "unsupported"]


def classify_schedule(schedule: dict[str, Any]) -> ScheduleState:
    """Classify whether a schedule provides active watchdog coverage."""
    if schedule.get("enabled", True) is False:
        return "disabled"
    interval = schedule.get("expected_interval_seconds")
    if not isinstance(interval, (int, float)) or interval <= 0:
        return "unsupported"
    return "active"


def schedules_by_state(schedules: list[dict[str, Any]]) -> dict[ScheduleState, list[str]]:
    grouped: dict[ScheduleState, list[str]] = {
        "active": [],
        "disabled": [],
        "unsupported": [],
    }
    for schedule in schedules:
        job = schedule.get("job")
        if job:
            grouped[classify_schedule(schedule)].append(str(job))
    for jobs in grouped.values():
        jobs.sort()
    return grouped
