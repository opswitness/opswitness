import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import respx
from httpx import Response
from typer.testing import CliRunner

from opswitness.cli import app
from opswitness.config import Settings
from opswitness.gate import (
    fold_gate_states,
    handle_post_tool_use,
    handle_pre_tool_use,
    record_decision,
    record_linked,
    request_hash,
)
from opswitness.gated_claude import (
    _approval_for_request,
    _claude_command,
    gate_settings_payload,
    parse_claude_version,
    recover_once,
    run_gated_claude,
    validate_claude,
    validate_user_args,
)
from opswitness.ledger import Ledger
from opswitness.paperclip import PaperclipClient
from opswitness.paperclip import PaperclipError


def _hook(**overrides):
    event = {
        "session_id": "session-1",
        "tool_use_id": "toolu-1",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "printf ok"},
        "cwd": "/tmp/project",
    }
    event.update(overrides)
    return event


def _decision(response):
    return response["hookSpecificOutput"]["permissionDecision"]


def _settings(tmp_path: Path, monkeypatch) -> Settings:
    config = tmp_path / "config"
    config.mkdir(mode=0o700)
    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(config))
    fake_qd = tmp_path / "qd"
    fake_qd.write_text("#!/bin/sh\n")
    fake_qd.chmod(0o700)
    fake_claude = tmp_path / "claude"
    fake_claude.write_text("#!/bin/sh\n")
    fake_claude.chmod(0o700)
    return Settings(
        ledger_dir=tmp_path / "ledger",
        services={"qd_bin": fake_qd},
        gate={
            "claude_bin": fake_claude,
            "state_dir": tmp_path / "gate",
            "approval_ttl_seconds": 60,
            "poll_seconds": 0.1,
        },
        paperclip={"api_key": "test", "company_id": "company-1"},
    )


def test_gate_defer_approve_consume_execute_once(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    now = datetime(2026, 7, 12, tzinfo=UTC)
    event = _hook()
    first = handle_pre_tool_use(ledger, event, ttl_seconds=60, now=now)
    assert _decision(first) == "defer"
    state = next(iter(fold_gate_states(ledger.read_all()).values()))
    assert record_linked(ledger, state, "approval-1")
    state = next(iter(fold_gate_states(ledger.read_all()).values()))
    assert record_decision(
        ledger,
        state,
        {
            "id": "approval-1",
            "status": "approved",
            "decidedByUserId": "board-user",
            "decidedAt": now.isoformat(),
        },
    )

    allowed = handle_pre_tool_use(
        ledger, event, ttl_seconds=60, now=now + timedelta(seconds=1)
    )
    assert _decision(allowed) == "allow"
    duplicate = handle_pre_tool_use(
        ledger, event, ttl_seconds=60, now=now + timedelta(seconds=2)
    )
    assert _decision(duplicate) == "deny"
    handle_post_tool_use(ledger, event, succeeded=True)
    kinds = [item["kind"] for item in ledger.read_all()]
    assert kinds == [
        "tool_gate_requested",
        "tool_gate_linked",
        "tool_gate_decided",
        "tool_gate_consumed",
        "tool_gate_executed",
    ]


def test_gate_expires_and_request_identity_mismatch_fail_closed(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    now = datetime(2026, 7, 12, tzinfo=UTC)
    event = _hook()
    assert _decision(handle_pre_tool_use(ledger, event, ttl_seconds=1, now=now)) == "defer"
    expired = handle_pre_tool_use(
        ledger, event, ttl_seconds=1, now=now + timedelta(seconds=2)
    )
    assert _decision(expired) == "deny"
    assert ledger.read_all()[-1]["kind"] == "tool_gate_expired"

    other = Ledger(tmp_path / "other")
    assert _decision(handle_pre_tool_use(other, event, ttl_seconds=60, now=now)) == "defer"
    changed = _hook(tool_input={"command": "printf changed"})
    assert _decision(handle_pre_tool_use(other, changed, ttl_seconds=60, now=now)) == "deny"
    assert other.read_all()[-1]["payload"]["reason"] == "request_mismatch"


def test_gate_redacts_input_and_detects_execution_without_consumption(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    event = _hook(tool_input={"command": "deploy", "api_key": "secret-value"})
    handle_pre_tool_use(ledger, event, ttl_seconds=60)
    requested = ledger.read_all()[0]
    assert requested["payload"]["tool_input"]["api_key"] == "[redacted]"
    handle_post_tool_use(ledger, event, succeeded=True)
    failure = ledger.read_all()[-1]
    assert failure["kind"] == "tool_gate_failed"
    assert failure["payload"]["reason"] == "execution_without_consumption"
    assert failure["degraded"] is True

    no_request = Ledger(tmp_path / "no-request")
    handle_post_tool_use(no_request, _hook(), succeeded=True)
    missing = no_request.read_all()[0]
    assert missing["kind"] == "tool_gate_failed"
    assert missing["payload"]["reason"] == "execution_without_request"


def test_gate_redacts_short_secret_embedded_in_bash_command(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    event = _hook(tool_input={"command": "API_TOKEN=short-value deploy"})

    handle_pre_tool_use(ledger, event, ttl_seconds=60)

    requested = ledger.read_all()[0]["payload"]
    assert requested["tool_input"]["command"] == "API_TOKEN=«redacted» deploy"
    assert requested["request_hash"] == request_hash(event)


def test_gate_bounds_large_redacted_input(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    huge = {f"field_{i}": "word " * 250 for i in range(100)}
    handle_pre_tool_use(ledger, _hook(tool_input=huge), ttl_seconds=60)
    summary = ledger.read_all()[0]["payload"]["tool_input"]
    assert summary["_truncated"] is True
    assert len(summary["original_sha256"]) == 64


def test_gate_settings_have_no_allow_rule_for_governed_tools(tmp_path):
    helper = tmp_path / "anthropic-api-key-helper"
    payload = gate_settings_payload(tmp_path / "qd", api_key_helper=helper)
    assert payload["permissions"]["defaultMode"] == "dontAsk"
    assert payload["disableBypassPermissionsMode"] == "disable"
    assert payload["permissions"]["allow"] == ["Read", "Glob", "Grep"]
    matcher = payload["hooks"]["PreToolUse"][0]["matcher"]
    assert "Bash" in matcher and "mcp__.*" in matcher
    assert payload["apiKeyHelper"] == str(helper)


def test_version_and_forbidden_argument_gates(tmp_path, monkeypatch):
    assert parse_claude_version("2.1.146 (Claude Code)") == (2, 1, 146)
    settings = _settings(tmp_path, monkeypatch)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(a[0], 0, "2.1.88\n", ""),
    )
    with pytest.raises(ValueError, match=">= 2.1.89"):
        validate_claude(settings)
    for args in (
        ["--dangerously-skip-permissions", "x"],
        ["--permission-mode=bypassPermissions", "x"],
        ["--allowedTools", "Bash", "x"],
        ["--settings", "other.json", "x"],
        ["--mcp-config", "server.json", "x"],
    ):
        with pytest.raises(ValueError, match="owns security/session flag"):
            validate_user_args(args)


def test_claude_command_owns_settings_permissions_and_session(tmp_path):
    command = _claude_command(
        tmp_path / "claude",
        tmp_path / "settings.json",
        [],
        session_id="session-1",
    )
    assert command[:4] == [str(tmp_path / "claude"), "-p", "--resume", "session-1"]
    assert command[command.index("--permission-mode") + 1] == "dontAsk"
    assert command[command.index("--setting-sources") + 1] == ""
    assert "bypassPermissions" not in command
    assert "--tools" not in command


class _ApprovalClient:
    def __init__(self, status="approved"):
        self.status = status

    def list_approvals(self):
        return []

    def create_board_approval(self, payload):
        assert payload["qdRequestId"]
        return {"id": "approval-1", "status": "pending", "payload": payload}

    def get_approval(self, approval_id):
        assert approval_id == "approval-1"
        return {
            "id": approval_id,
            "status": self.status,
            "decidedByUserId": "board-user",
            "decidedAt": "2026-07-12T00:00:00+00:00",
        }


def test_duplicate_remote_approval_markers_fail_closed(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    handle_pre_tool_use(ledger, _hook(), ttl_seconds=60)
    state = next(iter(fold_gate_states(ledger.read_all()).values()))

    class Duplicates(_ApprovalClient):
        def list_approvals(self):
            marker = {"qdRequestId": state.request_id}
            return [
                {"id": "approval-1", "payload": marker},
                {"id": "approval-2", "payload": marker},
            ]

    with pytest.raises(PaperclipError, match="multiple approvals"):
        _approval_for_request(Duplicates(), state)


def test_supervisor_defer_link_decide_resume_and_execute(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    ledger = Ledger(settings.ledger_dir)
    hook = _hook(cwd=str(tmp_path))
    deferred = {
        "type": "result",
        "stop_reason": "tool_deferred",
        "session_id": hook["session_id"],
        "deferred_tool_use": {
            "id": hook["tool_use_id"],
            "name": hook["tool_name"],
            "input": hook["tool_input"],
        },
    }
    calls = 0

    def fake_run(command, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            assert _decision(handle_pre_tool_use(ledger, hook, ttl_seconds=60)) == "defer"
            result = deferred
        else:
            assert "--resume" in command
            assert _decision(handle_pre_tool_use(ledger, hook, ttl_seconds=60)) == "allow"
            handle_post_tool_use(ledger, hook, succeeded=True)
            result = {"type": "result", "stop_reason": "end_turn", "result": "done"}
        return subprocess.CompletedProcess(command, 0, json.dumps(result), "")

    import opswitness.gated_claude as supervisor

    monkeypatch.setattr(supervisor, "validate_claude", lambda _settings: settings.gate.claude_bin)
    monkeypatch.setattr(supervisor, "_client", lambda _settings: _ApprovalClient())
    notices = []
    result, code = run_gated_claude(
        settings, ["perform the task"], cwd=tmp_path, run=fake_run, notify=notices.append
    )
    assert code == 0 and result["result"] == "done"
    assert notices[0]["approval_id"] == "approval-1"
    assert [e["kind"] for e in ledger.read_all()] == [
        "tool_gate_requested",
        "tool_gate_linked",
        "tool_gate_decided",
        "tool_gate_consumed",
        "tool_gate_executed",
    ]


def test_recovery_marks_resume_without_hook_consumption_failed(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    ledger = Ledger(settings.ledger_dir)
    hook = _hook(cwd=str(tmp_path))
    handle_pre_tool_use(ledger, hook, ttl_seconds=60)
    state = next(iter(fold_gate_states(ledger.read_all()).values()))
    record_linked(ledger, state, "approval-1")
    state = next(iter(fold_gate_states(ledger.read_all()).values()))
    record_decision(
        ledger,
        state,
        {"id": "approval-1", "status": "approved", "decidedByUserId": "board-user"},
    )

    def fake_run(command, **kwargs):
        result = {"type": "result", "is_error": True, "result": "MCP tool unavailable"}
        return subprocess.CompletedProcess(command, 0, json.dumps(result), "")

    import opswitness.gated_claude as supervisor

    monkeypatch.setattr(supervisor, "validate_claude", lambda _settings: settings.gate.claude_bin)
    monkeypatch.setattr(supervisor, "_client", lambda _settings: _ApprovalClient())
    stats = recover_once(settings, run=fake_run)
    assert stats["errors"] == 1 and stats["resumed"] == 0
    final = ledger.read_all()[-1]
    assert final["kind"] == "tool_gate_failed"
    assert final["payload"]["reason"] == "resume_did_not_consume"


def test_recovery_expires_without_creating_or_resuming_approval(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    ledger = Ledger(settings.ledger_dir)
    old = datetime.now(UTC) - timedelta(minutes=2)
    handle_pre_tool_use(ledger, _hook(cwd=str(tmp_path)), ttl_seconds=1, now=old)

    import opswitness.gated_claude as supervisor

    monkeypatch.setattr(supervisor, "validate_claude", lambda _settings: settings.gate.claude_bin)
    monkeypatch.setattr(supervisor, "_client", lambda _settings: _ApprovalClient())
    stats = recover_once(settings, run=lambda *a, **kw: pytest.fail("must not resume"))
    assert stats["pending"] == 1 and stats["resumed"] == 0
    assert ledger.read_all()[-1]["kind"] == "tool_gate_expired"


def test_recovery_never_replays_consumed_call_without_outcome(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    ledger = Ledger(settings.ledger_dir)
    old = datetime.now(UTC) - timedelta(minutes=2)
    hook = _hook(cwd=str(tmp_path))
    handle_pre_tool_use(ledger, hook, ttl_seconds=30, now=old)
    state = next(iter(fold_gate_states(ledger.read_all()).values()))
    record_linked(ledger, state, "approval-1")
    state = next(iter(fold_gate_states(ledger.read_all()).values()))
    record_decision(ledger, state, {"id": "approval-1", "status": "approved"})
    assert _decision(
        handle_pre_tool_use(
            ledger, hook, ttl_seconds=30, now=old + timedelta(seconds=1)
        )
    ) == "allow"

    import opswitness.gated_claude as supervisor

    monkeypatch.setattr(supervisor, "validate_claude", lambda _settings: settings.gate.claude_bin)
    monkeypatch.setattr(supervisor, "_client", lambda _settings: _ApprovalClient())
    stats = recover_once(settings, run=lambda *a, **kw: pytest.fail("must not replay"))
    assert stats["errors"] == 1 and stats["resumed"] == 0
    assert ledger.read_all()[-1]["payload"]["reason"] == "consumed_without_outcome"


def test_parallel_defer_not_returned_is_closed_without_approval(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    ledger = Ledger(settings.ledger_dir)

    def fake_run(command, **kwargs):
        handle_pre_tool_use(ledger, _hook(tool_use_id="toolu-a"), ttl_seconds=60)
        handle_pre_tool_use(ledger, _hook(tool_use_id="toolu-b"), ttl_seconds=60)
        result = {
            "type": "result",
            "stop_reason": "end_turn",
            "session_id": "session-1",
            "permission_denials": ["toolu-a", "toolu-b"],
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(result), "")

    import opswitness.gated_claude as supervisor

    monkeypatch.setattr(supervisor, "validate_claude", lambda _settings: settings.gate.claude_bin)
    monkeypatch.setattr(supervisor, "_client", lambda _settings: _ApprovalClient())
    result, code = run_gated_claude(settings, ["parallel task"], cwd=tmp_path, run=fake_run)
    assert code == 0 and result["stop_reason"] == "end_turn"
    failures = [e for e in ledger.read_all() if e["kind"] == "tool_gate_failed"]
    assert len(failures) == 2
    assert {e["payload"]["reason"] for e in failures} == {
        "defer_not_returned_by_claude"
    }


def test_parallel_cleanup_never_closes_another_claude_session(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    ledger = Ledger(settings.ledger_dir)

    def fake_run(command, **kwargs):
        handle_pre_tool_use(ledger, _hook(tool_use_id="toolu-a"), ttl_seconds=60)
        handle_pre_tool_use(
            ledger,
            _hook(session_id="session-other", tool_use_id="toolu-b"),
            ttl_seconds=60,
        )
        result = {"type": "result", "stop_reason": "end_turn", "session_id": "session-1"}
        return subprocess.CompletedProcess(command, 0, json.dumps(result), "")

    import opswitness.gated_claude as supervisor

    monkeypatch.setattr(supervisor, "validate_claude", lambda _settings: settings.gate.claude_bin)
    monkeypatch.setattr(supervisor, "_client", lambda _settings: _ApprovalClient())
    run_gated_claude(settings, ["parallel task"], cwd=tmp_path, run=fake_run)
    states = list(fold_gate_states(ledger.read_all()).values())
    by_session = {state.requested["session_id"]: state for state in states}
    assert by_session["session-1"].terminal is not None
    assert by_session["session-other"].terminal is None


def test_gate_hook_cli_returns_structured_defer_and_malformed_deny(tmp_path, monkeypatch):
    _settings(tmp_path, monkeypatch)
    monkeypatch.setenv("OPSWITNESS_LEDGER_DIR", str(tmp_path / "cli-ledger"))
    result = CliRunner().invoke(app, ["gate", "hook"], input=json.dumps(_hook()))
    assert result.exit_code == 0
    assert _decision(json.loads(result.output)) == "defer"
    malformed = CliRunner().invoke(app, ["gate", "hook"], input="not-json")
    assert malformed.exit_code == 0
    assert _decision(json.loads(malformed.output)) == "deny"


@respx.mock
def test_paperclip_approval_api_shapes():
    base = "http://paperclip.test"
    client = PaperclipClient(base, "test-key", "company-1")
    listed = respx.get(f"{base}/api/companies/company-1/approvals").mock(
        return_value=Response(200, json=[{"id": "approval-1"}])
    )
    created = respx.post(f"{base}/api/companies/company-1/approvals").mock(
        return_value=Response(200, json={"id": "approval-2", "status": "pending"})
    )
    fetched = respx.get(f"{base}/api/approvals/approval-2").mock(
        return_value=Response(200, json={"id": "approval-2", "status": "approved"})
    )
    assert client.list_approvals()[0]["id"] == "approval-1"
    assert client.create_board_approval({"qdRequestId": "req-1"})["id"] == "approval-2"
    assert client.get_approval("approval-2")["status"] == "approved"
    assert listed.called and created.called and fetched.called
    payload = json.loads(created.calls[0].request.content)
    assert payload == {
        "type": "request_board_approval",
        "payload": {"qdRequestId": "req-1"},
    }


@respx.mock
def test_paperclip_local_trusted_approval_resolution_uses_implicit_board():
    base = "http://127.0.0.1:3100"
    approval_id = "22222222-2222-4222-8222-222222222222"
    client = PaperclipClient(base, "service-agent-key", "company-1")
    health = respx.get(f"{base}/api/health").mock(
        return_value=Response(
            200,
            json={"status": "ok", "deploymentMode": "local_trusted"},
        )
    )
    resolved = respx.post(f"{base}/api/approvals/{approval_id}/approve").mock(
        return_value=Response(200, json={"id": approval_id, "status": "approved"})
    )

    result = client.resolve_approval(approval_id, "approve")

    assert result["status"] == "approved"
    assert "authorization" not in health.calls[0].request.headers
    assert "authorization" not in resolved.calls[0].request.headers


@respx.mock
def test_paperclip_local_board_resolution_rejects_authenticated_deployment():
    base = "http://127.0.0.1:3100"
    approval_id = "22222222-2222-4222-8222-222222222222"
    client = PaperclipClient(base, "service-agent-key", "company-1")
    respx.get(f"{base}/api/health").mock(
        return_value=Response(
            200,
            json={"status": "ok", "deploymentMode": "authenticated"},
        )
    )
    resolved = respx.post(f"{base}/api/approvals/{approval_id}/approve").mock(
        return_value=Response(200, json={"id": approval_id, "status": "approved"})
    )

    with pytest.raises(PaperclipError, match="local_trusted"):
        client.resolve_approval(approval_id, "approve")

    assert not resolved.called


def test_paperclip_local_board_resolution_rejects_non_loopback_api_base():
    client = PaperclipClient("https://paperclip.example", "service-agent-key", "company-1")

    with pytest.raises(PaperclipError, match="loopback"):
        client.resolve_approval("22222222-2222-4222-8222-222222222222", "approve")


@respx.mock
def test_paperclip_local_board_resolution_rejects_invalid_health_json():
    base = "http://127.0.0.1:3100"
    client = PaperclipClient(base, "service-agent-key", "company-1")
    respx.get(f"{base}/api/health").mock(return_value=Response(200, text="not-json"))

    with pytest.raises(PaperclipError, match="invalid JSON"):
        client.resolve_approval("22222222-2222-4222-8222-222222222222", "approve")
