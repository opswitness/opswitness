"""Append-only Claude tool-gate state machine.

The PreToolUse hook stays deliberately local: it never calls Paperclip and never waits.
It records a request durably, then returns defer. A supervisor links the request to a
Paperclip approval and resumes the same Claude session after a board decision.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Iterator

from opswitness.ids import new_ulid
from opswitness.ledger import Ledger
from opswitness.redact import redact_text

GATE_EVENT_KINDS = {
    "tool_gate_requested",
    "tool_gate_linked",
    "tool_gate_decided",
    "tool_gate_consumed",
    "tool_gate_executed",
    "tool_gate_failed",
    "tool_gate_expired",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def request_hash(event: dict[str, Any]) -> str:
    material = {
        "session_id": event.get("session_id"),
        "tool_use_id": event.get("tool_use_id"),
        "tool_name": event.get("tool_name"),
        "tool_input": event.get("tool_input"),
    }
    return hashlib.sha256(_canonical(material)).hexdigest()


_SECRET_KEYS = ("token", "secret", "password", "passwd", "api_key", "apikey", "auth")


def _redact_value(value: object, *, depth: int = 0) -> object:
    if depth >= 6:
        return "[truncated]"
    if isinstance(value, str):
        return redact_text(value)[:1000]
    if isinstance(value, list):
        return [_redact_value(item, depth=depth + 1) for item in value[:50]]
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, child in list(value.items())[:100]:
            rendered = str(key)
            if any(part in rendered.lower() for part in _SECRET_KEYS):
                result[rendered] = "[redacted]"
            else:
                result[rendered] = _redact_value(child, depth=depth + 1)
        return result
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_text(str(value))[:1000]


def _redacted_summary(value: object) -> object:
    redacted = _redact_value(value)
    if len(_canonical(redacted)) <= 32 * 1024:
        return redacted
    return {
        "_truncated": True,
        "original_sha256": hashlib.sha256(_canonical(value)).hexdigest(),
    }


def _validate_hook(event: dict[str, Any]) -> tuple[str, str, str, dict[str, Any]]:
    session_id = event.get("session_id")
    tool_use_id = event.get("tool_use_id")
    tool_name = event.get("tool_name")
    tool_input = event.get("tool_input")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("hook event requires session_id, tool_use_id, and tool_name")
    if not isinstance(tool_use_id, str) or not tool_use_id:
        raise ValueError("hook event requires session_id, tool_use_id, and tool_name")
    if not isinstance(tool_name, str) or not tool_name:
        raise ValueError("hook event requires session_id, tool_use_id, and tool_name")
    if not isinstance(tool_input, dict):
        raise ValueError("hook event tool_input must be an object")
    return session_id, tool_use_id, tool_name, tool_input


@dataclass
class GateState:
    request_id: str
    requested: dict[str, Any]
    linked: dict[str, Any] | None = None
    decided: dict[str, Any] | None = None
    consumed: dict[str, Any] | None = None
    terminal: dict[str, Any] | None = None

    @property
    def approval_id(self) -> str | None:
        value = (self.linked or {}).get("approval_id")
        return value if isinstance(value, str) and value else None

    @property
    def decision(self) -> str | None:
        value = (self.decided or {}).get("decision")
        return value if isinstance(value, str) else None


def fold_gate_states(events: list[dict[str, Any]]) -> dict[str, GateState]:
    states: dict[str, GateState] = {}
    for event in events:
        kind = event.get("kind")
        payload = event.get("payload")
        if kind not in GATE_EVENT_KINDS or not isinstance(payload, dict):
            continue
        request_id = payload.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            continue
        if kind == "tool_gate_requested":
            states.setdefault(request_id, GateState(request_id, payload))
            continue
        state = states.get(request_id)
        if state is None:
            continue
        if kind == "tool_gate_linked":
            state.linked = payload
        elif kind == "tool_gate_decided":
            state.decided = payload
        elif kind == "tool_gate_consumed":
            state.consumed = payload
        elif kind in {"tool_gate_executed", "tool_gate_failed", "tool_gate_expired"}:
            state.terminal = payload
    return states


@contextmanager
def gate_lock(ledger: Ledger) -> Iterator[None]:
    root = ledger.root.parent
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    fd = os.open(root / "gate.lease", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _decision(value: str, reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": value,
            "permissionDecisionReason": reason,
        }
    }


def _find_state(
    states: dict[str, GateState], session_id: str, tool_use_id: str, digest: str
) -> tuple[GateState | None, GateState | None]:
    collision: GateState | None = None
    for state in reversed(list(states.values())):
        requested = state.requested
        if (
            requested.get("session_id") == session_id
            and requested.get("tool_use_id") == tool_use_id
        ):
            if requested.get("request_hash") == digest:
                return state, None
            collision = state
    return None, collision


def _is_expired(state: GateState, now: datetime) -> bool:
    raw = state.requested.get("expires_at")
    try:
        expiry = datetime.fromisoformat(str(raw))
        return expiry.tzinfo is None or now >= expiry
    except (TypeError, ValueError):
        return True


def handle_pre_tool_use(
    ledger: Ledger,
    event: dict[str, Any],
    *,
    ttl_seconds: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a fail-closed PreToolUse response and durably advance gate state."""
    now = now or _now()
    try:
        session_id, tool_use_id, tool_name, tool_input = _validate_hook(event)
    except ValueError as exc:
        return _decision("deny", f"OpsWitness gate rejected malformed hook input: {exc}")
    digest = request_hash(event)
    with gate_lock(ledger):
        states = fold_gate_states(ledger.read_all())
        state, collision = _find_state(states, session_id, tool_use_id, digest)
        if collision is not None:
            ledger.append(
                "tool_gate_failed",
                session_id,
                {
                    "schema_version": 1,
                    "request_id": collision.request_id,
                    "request_hash": digest,
                    "session_id": session_id,
                    "tool_use_id": tool_use_id,
                    "reason": "request_mismatch",
                },
                fsync=True,
                degraded=True,
            )
            return _decision("deny", "OpsWitness request identity mismatch")
        if state is None:
            request_id = new_ulid()
            created = ledger.append(
                "tool_gate_requested",
                session_id,
                {
                    "schema_version": 1,
                    "request_id": request_id,
                    "request_hash": digest,
                    "session_id": session_id,
                    "tool_use_id": tool_use_id,
                    "tool_name": tool_name,
                    "tool_input": _redacted_summary(tool_input),
                    "cwd": redact_text(str(event.get("cwd", "")))[:1000],
                    "expires_at": _iso(now + timedelta(seconds=ttl_seconds)),
                },
                fsync=True,
            )
            if created is None:
                return _decision("deny", "OpsWitness could not durably record approval request")
            return _decision("defer", f"OpsWitness approval pending: {request_id}")
        if state.terminal is not None or state.consumed is not None:
            return _decision("deny", "OpsWitness approval was already consumed or closed")
        if _is_expired(state, now):
            ledger.append(
                "tool_gate_expired",
                session_id,
                {
                    "schema_version": 1,
                    "request_id": state.request_id,
                    "request_hash": digest,
                    "session_id": session_id,
                    "tool_use_id": tool_use_id,
                    "reason": "approval_expired",
                },
                fsync=True,
            )
            return _decision("deny", "OpsWitness approval expired")
        if state.decision == "approved":
            consumed = ledger.append(
                "tool_gate_consumed",
                session_id,
                {
                    "schema_version": 1,
                    "request_id": state.request_id,
                    "request_hash": digest,
                    "session_id": session_id,
                    "tool_use_id": tool_use_id,
                    "approval_id": state.approval_id,
                },
                fsync=True,
            )
            if consumed is None:
                return _decision("deny", "OpsWitness could not durably consume approval")
            return _decision("allow", f"OpsWitness approval consumed: {state.request_id}")
        if state.decision is not None:
            return _decision("deny", f"OpsWitness approval decision: {state.decision}")
        return _decision("defer", f"OpsWitness approval pending: {state.request_id}")


def handle_post_tool_use(ledger: Ledger, event: dict[str, Any], *, succeeded: bool) -> None:
    """Record outcome evidence; a post event without consumption is a security failure."""
    try:
        session_id, tool_use_id, tool_name, _tool_input = _validate_hook(event)
    except ValueError as exc:
        raise ValueError(f"cannot audit malformed post-tool event: {exc}") from exc
    digest = request_hash(event)
    with gate_lock(ledger):
        state, _collision = _find_state(
            fold_gate_states(ledger.read_all()), session_id, tool_use_id, digest
        )
        if state is None:
            ledger.append(
                "tool_gate_failed",
                session_id,
                {
                    "schema_version": 1,
                    "request_id": new_ulid(),
                    "request_hash": digest,
                    "session_id": session_id,
                    "tool_use_id": tool_use_id,
                    "tool_name": tool_name,
                    "reason": "execution_without_request",
                },
                fsync=True,
                degraded=True,
            )
            return
        if state.terminal is not None:
            return
        kind = "tool_gate_executed" if succeeded and state.consumed else "tool_gate_failed"
        payload: dict[str, Any] = {
            "schema_version": 1,
            "request_id": state.request_id,
            "request_hash": digest,
            "session_id": session_id,
            "tool_use_id": tool_use_id,
            "tool_name": tool_name,
        }
        degraded = False
        if not state.consumed:
            payload["reason"] = "execution_without_consumption"
            degraded = True
        elif not succeeded:
            payload["reason"] = "tool_execution_failed"
            error = event.get("error") or event.get("tool_response")
            if error is not None:
                payload["error"] = _redact_value(error)
        ledger.append(kind, session_id, payload, fsync=True, degraded=degraded)


def record_linked(
    ledger: Ledger,
    state: GateState,
    approval_id: str,
    *,
    resume_args: list[str] | None = None,
) -> bool:
    if state.linked is not None:
        return state.approval_id == approval_id
    event = ledger.append(
        "tool_gate_linked",
        str(state.requested["session_id"]),
        {
            "schema_version": 1,
            "request_id": state.request_id,
            "request_hash": state.requested["request_hash"],
            "session_id": state.requested["session_id"],
            "tool_use_id": state.requested["tool_use_id"],
            "approval_id": approval_id,
            "resume_args": resume_args or [],
        },
        fsync=True,
    )
    return event is not None


def record_decision(ledger: Ledger, state: GateState, approval: dict[str, Any]) -> bool:
    status = str(approval.get("status", "")).lower()
    if status not in {"approved", "rejected"}:
        return False
    if state.approval_id and approval.get("id") != state.approval_id:
        return False
    if state.decided is not None:
        return state.decision == status
    event = ledger.append(
        "tool_gate_decided",
        str(state.requested["session_id"]),
        {
            "schema_version": 1,
            "request_id": state.request_id,
            "request_hash": state.requested["request_hash"],
            "session_id": state.requested["session_id"],
            "tool_use_id": state.requested["tool_use_id"],
            "approval_id": state.approval_id or approval.get("id"),
            "decision": status,
            "decided_by": approval.get("decidedByUserId"),
            "decided_at": approval.get("decidedAt"),
            "decision_note": _redact_value(approval.get("decisionNote")),
        },
        fsync=True,
    )
    return event is not None


def record_failure(ledger: Ledger, state: GateState, reason: str) -> bool:
    event = ledger.append(
        "tool_gate_failed",
        str(state.requested["session_id"]),
        {
            "schema_version": 1,
            "request_id": state.request_id,
            "request_hash": state.requested["request_hash"],
            "session_id": state.requested["session_id"],
            "tool_use_id": state.requested["tool_use_id"],
            "reason": reason,
        },
        fsync=True,
        degraded=True,
    )
    return event is not None


def record_expired(ledger: Ledger, state: GateState, reason: str) -> bool:
    event = ledger.append(
        "tool_gate_expired",
        str(state.requested["session_id"]),
        {
            "schema_version": 1,
            "request_id": state.request_id,
            "request_hash": state.requested["request_hash"],
            "session_id": state.requested["session_id"],
            "tool_use_id": state.requested["tool_use_id"],
            "reason": reason,
        },
        fsync=True,
    )
    return event is not None


def open_gate_states(ledger: Ledger) -> list[GateState]:
    return [
        state
        for state in fold_gate_states(ledger.read_all()).values()
        if state.terminal is None and state.consumed is None
    ]


def unsettled_gate_states(ledger: Ledger) -> list[GateState]:
    """Requests with no terminal outcome, including consumed calls that must not rerun."""
    return [
        state
        for state in fold_gate_states(ledger.read_all()).values()
        if state.terminal is None
    ]
