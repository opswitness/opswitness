"""Fail-closed supervisor for non-interactive Claude Code tool approvals."""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import subprocess
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterator

from quarterdeck.config import Settings, resolve_api_key
from quarterdeck.console.provider_credentials import managed_anthropic_api_key_helper
from quarterdeck.fsutil import atomic_write
from quarterdeck.gate import (
    GateState,
    fold_gate_states,
    open_gate_states,
    record_decision,
    record_expired,
    record_failure,
    record_linked,
    request_hash,
    unsettled_gate_states,
)
from quarterdeck.ledger import Ledger
from quarterdeck.paperclip import PaperclipClient, PaperclipError

MIN_CLAUDE_VERSION = (2, 1, 89)
SAFE_TOOLS = ("Read", "Glob", "Grep")
GOVERNED_MATCHER = "Bash|Edit|Write|NotebookEdit|mcp__.*"

_ALLOWED_FLAGS = {
    "--add-dir",
    "--append-system-prompt",
    "--append-system-prompt-file",
    "--debug",
    "--debug-file",
    "--disable-slash-commands",
    "--effort",
    "--exclude-dynamic-system-prompt-sections",
    "--fallback-model",
    "--json-schema",
    "--max-budget-usd",
    "--model",
    "--name",
    "--system-prompt",
    "--system-prompt-file",
    "--verbose",
    "-d",
    "-n",
}

_FORBIDDEN_FLAGS = {
    "--allow-dangerously-skip-permissions",
    "--allowed-tools",
    "--allowedTools",
    "--bare",
    "--continue",
    "--dangerously-skip-permissions",
    "--disallowed-tools",
    "--disallowedTools",
    "--input-format",
    "--mcp-config",
    "--no-session-persistence",
    "--output-format",
    "--permission-mode",
    "--plugin-dir",
    "--plugin-url",
    "--resume",
    "--session-id",
    "--setting-sources",
    "--settings",
    "--strict-mcp-config",
    "--tools",
    "-c",
    "-r",
}


def parse_claude_version(output: str) -> tuple[int, int, int]:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", output)
    if not match:
        raise ValueError(f"cannot parse Claude Code version: {output[:120]}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def validate_claude(settings: Settings) -> Path:
    candidate = settings.gate.claude_bin.expanduser()
    if not candidate.is_absolute():
        resolved = shutil.which(str(candidate))
        if not resolved:
            raise ValueError(f"Claude executable not found: {candidate}")
        candidate = Path(resolved)
    candidate = candidate.resolve()
    if not candidate.is_file() or not os.access(candidate, os.X_OK):
        raise ValueError(f"Claude executable is not an executable file: {candidate}")
    result = subprocess.run(
        [str(candidate), "--version"], capture_output=True, text=True, timeout=10, check=False
    )
    if result.returncode != 0:
        raise ValueError(f"Claude version check failed: {result.stderr[:200]}")
    version = parse_claude_version(result.stdout or result.stderr)
    if version < MIN_CLAUDE_VERSION:
        required = ".".join(str(v) for v in MIN_CLAUDE_VERSION)
        found = ".".join(str(v) for v in version)
        raise ValueError(f"Claude Code >= {required} required, found {found}")
    return candidate


def validate_user_args(argv: list[str]) -> list[str]:
    cleaned = [arg for arg in argv if arg not in {"-p", "--print", "--"}]
    for arg in cleaned:
        flag = arg.split("=", 1)[0]
        if flag in _FORBIDDEN_FLAGS:
            raise ValueError(f"gated-claude owns security/session flag: {flag}")
        if flag.startswith("-") and flag not in _ALLOWED_FLAGS:
            raise ValueError(f"gated-claude v1 does not allow CLI flag: {flag}")
    if not cleaned:
        raise ValueError("gated-claude requires a Claude prompt or supported arguments")
    return cleaned


def gate_settings_payload(
    qd_bin: Path,
    *,
    api_key_helper: Path | None = None,
) -> dict[str, Any]:
    hook = {"type": "command", "command": str(qd_bin), "args": ["gate", "hook"]}
    post_ok = {
        "type": "command",
        "command": str(qd_bin),
        "args": ["gate", "hook", "--post", "success"],
    }
    post_failed = {
        "type": "command",
        "command": str(qd_bin),
        "args": ["gate", "hook", "--post", "failure"],
    }
    payload: dict[str, Any] = {
        "disableBypassPermissionsMode": "disable",
        "permissions": {
            "defaultMode": "dontAsk",
            "allow": list(SAFE_TOOLS),
            "ask": [],
            "deny": [],
        },
        "hooks": {
            "PreToolUse": [{"matcher": GOVERNED_MATCHER, "hooks": [hook]}],
            "PostToolUse": [{"matcher": GOVERNED_MATCHER, "hooks": [post_ok]}],
            "PostToolUseFailure": [
                {"matcher": GOVERNED_MATCHER, "hooks": [post_failed]}
            ],
        },
    }
    if api_key_helper is not None:
        payload["apiKeyHelper"] = str(api_key_helper)
    return payload


def install_gate_settings(settings: Settings) -> Path:
    qd_bin = settings.services.qd_bin.expanduser().resolve()
    if not qd_bin.is_file() or not os.access(qd_bin, os.X_OK):
        raise ValueError(f"configured qd executable is invalid: {qd_bin}")
    root = settings.gate.state_dir.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    target = root / "claude-settings.json"
    api_key_helper = managed_anthropic_api_key_helper(settings)
    atomic_write(
        target,
        (
            json.dumps(
                gate_settings_payload(qd_bin, api_key_helper=api_key_helper),
                indent=2,
            )
            + "\n"
        ).encode(),
        mode=0o600,
    )
    return target


def _client(settings: Settings) -> PaperclipClient:
    key = resolve_api_key(settings)
    company_id = settings.paperclip.company_id
    if not key or not company_id:
        raise ValueError("Paperclip API key and company_id are required for gated Claude")
    return PaperclipClient(settings.paperclip.api_base, key, company_id)


def _approval_for_request(client: PaperclipClient, state: GateState) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for approval in client.list_approvals():
        payload = approval.get("payload")
        if isinstance(payload, dict) and payload.get("qdRequestId") == state.request_id:
            matches.append(approval)
    if len(matches) > 1:
        raise PaperclipError(f"multiple approvals carry qdRequestId {state.request_id}")
    if matches:
        return matches[0]
    requested = state.requested
    return client.create_board_approval(
        {
            "title": f"Approve Claude tool: {requested['tool_name']}",
            "summary": "Quarterdeck deferred a non-interactive Claude Code tool call.",
            "recommendedAction": "Inspect the redacted input and approve only if intended.",
            "risks": [
                "Approval is single-use and bound to the exact session, tool call, and input hash.",
                "Reject or let it expire if the requested side effect is unclear.",
            ],
            "qdRequestId": state.request_id,
            "requestHash": requested["request_hash"],
            "sessionId": requested["session_id"],
            "toolUseId": requested["tool_use_id"],
            "toolName": requested["tool_name"],
            "toolInput": requested["tool_input"],
            "expiresAt": requested["expires_at"],
        }
    )


def _result_from_output(stdout: str) -> dict[str, Any]:
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Claude did not return JSON: {stdout[:200]}") from exc
    if not isinstance(result, dict):
        raise ValueError("Claude JSON result must be an object")
    return result


def _claude_command(
    claude_bin: Path,
    settings_file: Path,
    argv: list[str],
    *,
    session_id: str | None = None,
) -> list[str]:
    command = [str(claude_bin), "-p"]
    if session_id:
        command.extend(["--resume", session_id])
    else:
        command.extend(argv)
    command.extend(
        [
            "--output-format",
            "json",
            "--permission-mode",
            "dontAsk",
            "--setting-sources",
            "",
            "--settings",
            str(settings_file),
        ]
    )
    return command


Run = Callable[..., subprocess.CompletedProcess[str]]
Notice = Callable[[dict[str, Any]], None]


def invoke_claude(
    claude_bin: Path,
    settings_file: Path,
    argv: list[str],
    *,
    cwd: Path,
    session_id: str | None = None,
    run: Run = subprocess.run,
) -> tuple[dict[str, Any], int]:
    env = os.environ.copy()
    env.pop("CLAUDE_CODE_SIMPLE", None)  # --bare semantics skip hooks entirely
    completed = run(
        _claude_command(claude_bin, settings_file, argv, session_id=session_id),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    result = _result_from_output(completed.stdout)
    return result, completed.returncode


def _deferred_state(ledger: Ledger, result: dict[str, Any]) -> GateState:
    if result.get("stop_reason") != "tool_deferred":
        raise ValueError("Claude result is not deferred")
    session_id = result.get("session_id")
    tool = result.get("deferred_tool_use")
    if not isinstance(session_id, str) or not isinstance(tool, dict):
        raise ValueError("deferred result lacks session_id or deferred_tool_use")
    hook_shape = {
        "session_id": session_id,
        "tool_use_id": tool.get("id"),
        "tool_name": tool.get("name"),
        "tool_input": tool.get("input"),
    }
    digest = request_hash(hook_shape)
    for state in reversed(list(fold_gate_states(ledger.read_all()).values())):
        requested = state.requested
        if (
            requested.get("session_id") == session_id
            and requested.get("tool_use_id") == tool.get("id")
            and requested.get("request_hash") == digest
        ):
            return state
    raise ValueError("deferred Claude result has no matching durable gate request")


@contextmanager
def request_lease(state_dir: Path, request_id: str) -> Iterator[bool]:
    state_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(state_dir, 0o700)
    fd = os.open(state_dir / f"{request_id}.lease", os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError:
            pass
        yield acquired
    finally:
        if acquired:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _expires_at(state: GateState) -> datetime:
    try:
        value = datetime.fromisoformat(str(state.requested["expires_at"]))
        if value.tzinfo is None:
            raise ValueError("expiry has no timezone")
        return value
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"gate request {state.request_id} has invalid expiry") from exc


def _refresh_state(ledger: Ledger, request_id: str) -> GateState:
    state = fold_gate_states(ledger.read_all()).get(request_id)
    if state is None:
        raise ValueError(f"gate request disappeared: {request_id}")
    return state


def _request_ids(ledger: Ledger) -> set[str]:
    return set(fold_gate_states(ledger.read_all()))


def _close_unreturned_requests(
    ledger: Ledger, before: set[str], session_id: object
) -> int:
    if not isinstance(session_id, str) or not session_id:
        return 0
    closed = 0
    for state in open_gate_states(ledger):
        if (
            state.request_id not in before
            and state.linked is None
            and state.requested.get("session_id") == session_id
        ):
            if record_failure(ledger, state, "defer_not_returned_by_claude"):
                closed += 1
    return closed


def _link(ledger: Ledger, client: PaperclipClient, state: GateState) -> GateState:
    approval = _approval_for_request(client, state)
    approval_id = approval.get("id")
    if not isinstance(approval_id, str) or not approval_id:
        raise PaperclipError("approval response has no id")
    if not record_linked(ledger, state, approval_id):
        raise ValueError("could not durably link Paperclip approval")
    state = _refresh_state(ledger, state.request_id)
    status = str(approval.get("status", "")).lower()
    if status in {"approved", "rejected"}:
        record_decision(ledger, state, approval)
        state = _refresh_state(ledger, state.request_id)
    return state


def _await_decision(
    ledger: Ledger,
    client: PaperclipClient,
    state: GateState,
    *,
    poll_seconds: float,
) -> GateState:
    while datetime.now(UTC) < _expires_at(state):
        approval = client.get_approval(str(state.approval_id))
        status = str(approval.get("status", "")).lower()
        if status in {"approved", "rejected"}:
            if not record_decision(ledger, state, approval):
                raise ValueError("could not durably record approval decision")
            return _refresh_state(ledger, state.request_id)
        if status not in {"pending", "revision_requested"}:
            record_failure(ledger, state, f"unsupported_approval_status:{status}")
            return _refresh_state(ledger, state.request_id)
        time.sleep(poll_seconds)
    record_expired(ledger, state, "approval_expired_without_resume")
    return _refresh_state(ledger, state.request_id)


def run_gated_claude(
    settings: Settings,
    argv: list[str],
    *,
    cwd: Path,
    wait: bool = True,
    run: Run = subprocess.run,
    notify: Notice | None = None,
) -> tuple[dict[str, Any], int]:
    """Run until completion or return a durable pending approval when wait is false."""
    claude_bin = validate_claude(settings)
    cleaned = validate_user_args(argv)
    settings_file = install_gate_settings(settings)
    ledger = Ledger(settings.ledger_dir)
    client = _client(settings)
    before = _request_ids(ledger)
    result, code = invoke_claude(
        claude_bin, settings_file, cleaned, cwd=cwd, run=run
    )
    if result.get("stop_reason") != "tool_deferred":
        _close_unreturned_requests(ledger, before, result.get("session_id"))
    while result.get("stop_reason") == "tool_deferred":
        state = _deferred_state(ledger, result)
        with request_lease(settings.gate.state_dir, state.request_id) as acquired:
            if not acquired:
                return {"status": "approval_owned_elsewhere", "request_id": state.request_id}, 75
            state = _link(ledger, client, state)
            if notify:
                notify(
                    {
                        "status": "approval_pending",
                        "request_id": state.request_id,
                        "approval_id": state.approval_id,
                        "paperclip": settings.paperclip.api_base,
                    }
                )
            if not wait:
                return {
                    "status": "approval_pending",
                    "request_id": state.request_id,
                    "approval_id": state.approval_id,
                    "session_id": state.requested["session_id"],
                }, 75
            if state.decision is None:
                state = _await_decision(
                    ledger,
                    client,
                    state,
                    poll_seconds=settings.gate.poll_seconds,
                )
            if state.decision == "rejected":
                record_failure(ledger, state, "approval_rejected")
                return {"status": "approval_rejected", "request_id": state.request_id}, 1
            if state.decision != "approved":
                return {"status": "approval_closed", "request_id": state.request_id}, 1
            before = _request_ids(ledger)
            result, code = invoke_claude(
                claude_bin,
                settings_file,
                [],
                cwd=Path(str(state.requested.get("cwd") or cwd)),
                session_id=str(state.requested["session_id"]),
                run=run,
            )
            if result.get("stop_reason") != "tool_deferred":
                _close_unreturned_requests(ledger, before, result.get("session_id"))
            refreshed = _refresh_state(ledger, state.request_id)
            if result.get("stop_reason") != "tool_deferred" and refreshed.consumed is None:
                record_failure(ledger, refreshed, "resume_did_not_consume")
                return {"status": "resume_failed_closed", "request_id": state.request_id}, 1
    if result.get("is_error"):
        code = code or 1
    return result, code


def recover_once(settings: Settings, *, run: Run = subprocess.run) -> dict[str, int]:
    ledger = Ledger(settings.ledger_dir)
    client = _client(settings)
    claude_bin = validate_claude(settings)
    settings_file = install_gate_settings(settings)
    stats = {"pending": 0, "linked": 0, "decided": 0, "resumed": 0, "errors": 0}
    for original in unsettled_gate_states(ledger):
        stats["pending"] += 1
        with request_lease(settings.gate.state_dir, original.request_id) as acquired:
            if not acquired:
                continue
            try:
                state = original
                if state.consumed is not None:
                    if datetime.now(UTC) >= _expires_at(state):
                        record_failure(ledger, state, "consumed_without_outcome")
                        stats["errors"] += 1
                    continue
                if datetime.now(UTC) >= _expires_at(state):
                    record_expired(ledger, state, "approval_expired_before_recovery")
                    continue
                if state.linked is None:
                    state = _link(ledger, client, state)
                    stats["linked"] += 1
                if state.decision is None:
                    approval = client.get_approval(str(state.approval_id))
                    if str(approval.get("status", "")).lower() not in {"approved", "rejected"}:
                        continue
                    record_decision(ledger, state, approval)
                    state = _refresh_state(ledger, state.request_id)
                    stats["decided"] += 1
                if state.decision == "rejected":
                    record_failure(ledger, state, "approval_rejected")
                    continue
                before = _request_ids(ledger)
                result, _code = invoke_claude(
                    claude_bin,
                    settings_file,
                    [],
                    cwd=Path(str(state.requested.get("cwd") or Path.home())),
                    session_id=str(state.requested["session_id"]),
                    run=run,
                )
                if result.get("stop_reason") != "tool_deferred":
                    _close_unreturned_requests(ledger, before, result.get("session_id"))
                if result.get("stop_reason") == "tool_deferred":
                    _deferred_state(ledger, result)
                elif _refresh_state(ledger, state.request_id).consumed is None:
                    record_failure(ledger, state, "resume_did_not_consume")
                    stats["errors"] += 1
                    continue
                stats["resumed"] += 1
            except (OSError, ValueError, PaperclipError, subprocess.SubprocessError):
                stats["errors"] += 1
    return stats
