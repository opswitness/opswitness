"""Deterministic, content-free signals for the governed Work Recovery Agent."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from opswitness.console.schemas import (
    PlanRecord,
    RecoveryEvidenceBaseline,
    RecoveryStageBaseline,
)


RECOVERY_STALL_SECONDS = 180
RECOVERY_MAX_ATTEMPTS = 2
RECOVERY_COOLDOWN_SECONDS = 300
RECOVERY_VERIFY_SECONDS = 120


def normalize_runtime_control_status(value: object) -> str:
    if not isinstance(value, str) or len(value) > 32:
        return "unknown"
    normalized = value.strip().casefold()
    if normalized in {"running", "paused", "unavailable", "unknown"}:
        return normalized
    if normalized in {
        "inactive",
        "cancelled",
        "canceled",
        "completed",
        "completed_unverified",
        "failed",
    }:
        return "not_running"
    return "unknown"


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def progress_fingerprint(record: PlanRecord) -> str:
    """Hash only bounded runtime state; never read prompts, logs, or artifact bodies."""

    execution = record.execution
    if execution is None:
        payload: dict[str, Any] = {"status": record.status, "execution": None}
    else:
        progress = execution.progress
        payload = {
            "status": record.status,
            "kind": execution.kind,
            "team_id": execution.aion_team_id,
            "team_run_id": execution.aion_team_run_id,
            "workflow_run_id": execution.workflow_run_id,
            "pending_input_ids": sorted(
                item.request_id for item in execution.input_requests if item.status == "pending"
            ),
            "progress": (
                None
                if progress is None
                else {
                    "available": progress.available,
                    "active_members": sorted(
                        (
                            member.agent_name,
                            member.state,
                            member.started_at,
                        )
                        for member in progress.active_members
                    ),
                    "recent_activity": sorted(
                        (
                            activity.activity_id,
                            activity.agent_name,
                            activity.kind,
                            activity.status,
                            activity.tool_name,
                            activity.observed_at,
                            activity.count,
                        )
                        for activity in progress.recent_activity
                    ),
                    "stages": sorted(
                        (
                            stage.stage_order,
                            stage.agent_name,
                            stage.status,
                            stage.source,
                            stage.task_id,
                            tuple(stage.blocked_by),
                            stage.started_at,
                            stage.updated_at,
                            stage.completed_at,
                        )
                        for stage in progress.stages
                    ),
                }
            ),
        }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def progress_evidence_fingerprint(record: PlanRecord) -> str:
    """Hash the bounded monotonic baseline, excluding timestamps and member presence."""

    payload = recovery_evidence_baseline(record).model_dump(mode="json")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def recovery_evidence_baseline(record: PlanRecord) -> RecoveryEvidenceBaseline:
    execution = record.execution
    progress = execution.progress if execution is not None else None
    if progress is None:
        return RecoveryEvidenceBaseline()
    activity_ids = {
        activity.activity_id
        for activity in progress.recent_activity
        if activity.status in {"completed", "observed"}
    }
    for stage in progress.stages:
        activity_ids.update(
            activity.activity_id
            for activity in stage.recent_activity
            if activity.status in {"completed", "observed"}
        )
    return RecoveryEvidenceBaseline(
        stages=[
            RecoveryStageBaseline(
                stage_order=stage.stage_order,
                status=stage.status,
                task_id=stage.task_id,
            )
            for stage in sorted(progress.stages, key=lambda item: item.stage_order)
        ],
        completed_or_observed_activity_ids=sorted(activity_ids)[:100],
    )


def has_monotonic_forward_progress(
    baseline: RecoveryEvidenceBaseline,
    record: PlanRecord,
) -> bool:
    """Accept only causal forward transitions; disappearance/failure never counts."""

    current = recovery_evidence_baseline(record)
    if set(current.completed_or_observed_activity_ids) - set(
        baseline.completed_or_observed_activity_ids
    ):
        return True
    baseline_stages = {stage.stage_order: stage for stage in baseline.stages}
    current_stages = {stage.stage_order: stage for stage in current.stages}
    if any(
        stage.status == "completed" and order not in baseline_stages
        for order, stage in current_stages.items()
    ):
        return True
    valid_transitions = {
        "pending": {"running", "completed"},
        "running": {"completed"},
    }
    for order, previous in baseline_stages.items():
        observed = current_stages.get(order)
        if observed is None:
            continue
        if (
            previous.task_id is not None
            and observed.task_id is not None
            and previous.task_id != observed.task_id
        ):
            continue
        if observed.status in valid_transitions.get(previous.status, set()):
            return True
        if (
            previous.status in {"not_started", "pending", "running"}
            and observed.status == "completed"
        ):
            return True
    return False


def latest_progress_time(record: PlanRecord, *, fallback: datetime) -> datetime:
    """Find the newest verifiable activity timestamp, bounded to ``fallback``."""

    execution = record.execution
    candidates: list[str] = []
    if execution is not None:
        if execution.dispatched_at:
            candidates.append(execution.dispatched_at)
        progress = execution.progress
        if progress is not None:
            for activity in progress.recent_activity:
                candidates.append(activity.observed_at)
            for stage in progress.stages:
                candidates.extend(
                    value
                    for value in (
                        stage.started_at,
                        stage.updated_at,
                        stage.completed_at,
                    )
                    if value
                )
    parsed: list[datetime] = []
    for value in candidates:
        try:
            candidate = parse_utc(value)
        except ValueError:
            continue
        if candidate <= fallback:
            parsed.append(candidate)
    return max(parsed, default=fallback)


def bounded_recovery_telemetry(
    record: PlanRecord,
    *,
    unchanged_seconds: int,
    runtime_control_status: str,
) -> dict[str, Any]:
    """Return model-safe facts without objectives, prompts, paths, logs, or file content."""

    execution = record.execution
    progress = execution.progress if execution is not None else None
    stages = progress.stages if progress is not None else []
    members = progress.active_members if progress is not None else []
    return {
        "schema_version": 1,
        "work_status": record.status,
        "execution_kind": execution.kind if execution is not None else None,
        "progress_available": progress.available if progress is not None else False,
        "unchanged_seconds": max(0, unchanged_seconds),
        "runtime_control_status": runtime_control_status,
        "stage_counts": {
            status: sum(stage.status == status for stage in stages)
            for status in (
                "not_started",
                "pending",
                "running",
                "blocked",
                "completed",
                "failed",
                "unknown",
            )
        },
        "member_state_counts": {
            state: sum(member.state == state for member in members)
            for state in ("queued", "running", "blocked")
        },
        "pending_operator_input": bool(
            execution
            and any(item.status == "pending" for item in execution.input_requests)
        ),
        "has_team_identity": bool(
            execution
            and execution.aion_team_id
            and execution.aion_team_run_id
        ),
    }
