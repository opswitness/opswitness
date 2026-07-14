import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quarterdeck.config import Settings
from quarterdeck.console.aionui import AionUiClient
from quarterdeck.console.app import create_app
from quarterdeck.console.schemas import ConfirmRequest, PlanRequest, TaskPlan
from quarterdeck.console.service import (
    ConsoleConflict,
    ConsoleService,
    ConsoleUnavailable,
    _fleet_health,
    _mail_setup_detail,
)
from quarterdeck.ledger import Ledger


def _plan(execution_mode: str = "aion_team", workflow_id: str | None = None) -> TaskPlan:
    return TaskPlan.model_validate(
        {
            "schema_version": 1,
            "title": "每日研究摘要",
            "summary": "收集、复核并汇报当天研究结果。",
            "execution_mode": execution_mode,
            "workflow_id": workflow_id,
            "agents": [
                {
                    "name": "总控",
                    "role": "lead",
                    "responsibility": "分配任务并汇总结果",
                    "runtime": "claude_code",
                },
                {
                    "name": "复核",
                    "role": "reviewer",
                    "responsibility": "检查证据与错误",
                    "runtime": "codex_cli",
                },
            ],
            "stages": [
                {
                    "order": 1,
                    "title": "收集",
                    "owner": "总控",
                    "outcome": "形成候选摘要",
                    "checkpoint": False,
                },
                {
                    "order": 2,
                    "title": "复核",
                    "owner": "复核",
                    "outcome": "形成可交付摘要",
                    "checkpoint": True,
                },
            ],
            "cadence": {
                "kind": "daily",
                "timezone": "America/Los_Angeles",
                "local_time": "09:00",
                "update_interval": "每天 09:00",
            },
            "tools": ["mail metadata"],
            "approvals": ["发布前人工确认"],
            "artifacts": ["摘要报告"],
            "risks": ["输入数据可能不完整"],
            "estimated_duration_minutes": 20,
            "update_policy": "完成后更新一次，异常立即更新。",
        }
    )


class FakeAion:
    def __init__(self) -> None:
        self.generated = 0
        self.dispatched = 0
        self.summarized = 0

    def health(self):
        return {"platform": "darwin"}

    def generate_plan(self, plan_id, request, catalog):
        del plan_id, request, catalog
        self.generated += 1
        return _plan()

    def dispatch_plan(self, **kwargs):
        assert kwargs["paperclip_issue_id"] == "issue-1"
        self.dispatched += 1
        return {
            "team_id": "team-1",
            "team_run_id": "team-run-1",
            "conversation_ids": ["conversation-1"],
        }

    def execution_snapshot(self, team_id, conversation_ids):
        assert team_id == "team-1"
        assert conversation_ids == ["conversation-1"]
        return {"status": "completed_unverified"}

    def summarize_mail(self, job_id, messages):
        del job_id
        self.summarized += 1
        assert messages[0]["subject"] == "private subject"
        return "今日有一封需要回复的邮件。"


class FakePaperclip:
    def __init__(self) -> None:
        self.created = 0

    def list_issues(self):
        return []

    def create_issue(self, title, description):
        assert title.startswith("[qd-plan:")
        assert "outcome proof" in description
        self.created += 1
        return {"id": "issue-1"}

    def list_approvals(self, status=None):
        del status
        return []


@pytest.fixture
def console_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = tmp_path / "config"
    config.mkdir(mode=0o700)
    monkeypatch.setenv("QD_CONFIG_DIR", str(config))
    settings = Settings(
        ledger_dir=tmp_path / "ledger",
        console={"state_dir": tmp_path / "console", "port": 8765},
        paperclip={"api_key": "test", "company_id": "company-1"},
    )
    aion = FakeAion()
    paperclip = FakePaperclip()
    service = ConsoleService(
        settings,
        aion=aion,  # type: ignore[arg-type]
        paperclip_factory=lambda: paperclip,  # type: ignore[arg-type,return-value]
        background=False,
    )
    yield settings, service, aion, paperclip
    service.close()


def test_plan_schema_requires_one_lead_and_exact_stage_owners():
    raw = _plan().model_dump(mode="json")
    raw["agents"][0]["role"] = "reviewer"
    with pytest.raises(ValueError, match="exactly one lead"):
        TaskPlan.model_validate(raw)

    raw = _plan().model_dump(mode="json")
    raw["stages"][0]["owner"] = "不存在"
    with pytest.raises(ValueError, match="stage owner"):
        TaskPlan.model_validate(raw)


def test_planning_has_no_execution_side_effect_before_confirmation(console_env):
    _, service, aion, paperclip = console_env
    record = service.request_plan(
        PlanRequest(objective="每天生成研究摘要", preferred_cadence="daily")
    )
    assert record.status == "planning"
    assert aion.generated == 0
    assert aion.dispatched == 0
    assert paperclip.created == 0

    ready = service.draft_plan(record.plan_id)
    assert ready.status == "ready"
    assert aion.generated == 1
    assert aion.dispatched == 0
    assert paperclip.created == 0
    assert [event["kind"] for event in service.ledger.read_all()] == [
        "task_plan_requested",
        "task_plan_drafted",
    ]


def test_confirmation_hash_is_mandatory_and_dispatch_is_ordered(console_env):
    _, service, aion, paperclip = console_env
    requested = service.request_plan(PlanRequest(objective="每天生成研究摘要"))
    ready = service.draft_plan(requested.plan_id)
    with pytest.raises(ConsoleConflict, match="hash changed"):
        service.confirm_plan(
            ready.plan_id,
            ConfirmRequest(plan_sha256="0" * 64, confirmed=True),
        )
    assert paperclip.created == 0
    assert aion.dispatched == 0

    confirmed = service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
    )
    assert confirmed.status == "confirmed"
    assert paperclip.created == 0
    running = service.dispatch_plan(ready.plan_id)
    assert running.status == "running"
    assert paperclip.created == 1
    assert aion.dispatched == 1
    kinds = [event["kind"] for event in service.ledger.read_all()]
    assert kinds == [
        "task_plan_requested",
        "task_plan_drafted",
        "task_plan_confirmed",
        "task_execution_requested",
        "task_execution_dispatched",
    ]


def test_plan_hash_binds_objective_constraints_workspace_and_dispatch(console_env):
    _, service, aion, paperclip = console_env
    requested = service.request_plan(PlanRequest(objective="生成严格绑定的摘要"))
    ready = service.draft_plan(requested.plan_id)

    def alter_objective(current):
        current.objective = "被替换的目标"
        return current

    service.store.mutate(ready.plan_id, alter_objective)
    with pytest.raises(ConsoleConflict, match="inputs changed"):
        service.confirm_plan(
            ready.plan_id,
            ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
        )
    assert paperclip.created == 0
    assert aion.dispatched == 0

    second = service.request_plan(
        PlanRequest(objective="生成第二份摘要", constraints="只读", workspace="")
    )
    second_ready = service.draft_plan(second.plan_id)
    service.confirm_plan(
        second_ready.plan_id,
        ConfirmRequest(plan_sha256=str(second_ready.plan_sha256), confirmed=True),
    )

    def alter_constraints(current):
        current.constraints = "允许写入"
        return current

    service.store.mutate(second_ready.plan_id, alter_constraints)
    failed = service.dispatch_plan(second_ready.plan_id)
    assert failed.status == "failed"
    assert failed.error == "confirmed plan inputs changed before dispatch"
    assert paperclip.created == 0
    assert aion.dispatched == 0
    assert "task_execution_requested" not in [
        event["kind"] for event in service.ledger.read_all() if event["run_id"] == second.plan_id
    ]


def test_execution_completion_is_explicitly_unverified(console_env):
    _, service, _, _ = console_env
    requested = service.request_plan(PlanRequest(objective="每天生成研究摘要"))
    ready = service.draft_plan(requested.plan_id)
    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
    )
    service.dispatch_plan(ready.plan_id)
    finished = service.refresh_execution(ready.plan_id)
    assert finished.status == "completed_unverified"
    assert finished.execution is not None
    assert finished.execution.outcome_verified is False
    assert finished.execution.finish_event_recorded is True
    final = service.ledger.read_all()[-1]
    assert final["kind"] == "task_execution_finished"
    assert final["payload"]["outcome_verified"] is False


def test_audit_failure_prevents_planning(monkeypatch, console_env):
    _, service, aion, _ = console_env
    monkeypatch.setattr(Ledger, "append", lambda *args, **kwargs: None)
    with pytest.raises(ConsoleUnavailable, match="audit evidence unavailable"):
        service.request_plan(PlanRequest(objective="不应访问模型"))
    assert aion.generated == 0


def test_mail_summary_keeps_metadata_and_summary_out_of_ledger(monkeypatch, console_env):
    _, service, aion, _ = console_env
    monkeypatch.setattr(
        "quarterdeck.console.service.check_mail",
        lambda **kwargs: {
            "ok": True,
            "messages": [
                {
                    "message_id": "private-id",
                    "from": "private@example.com",
                    "subject": "private subject",
                    "date": "today",
                }
            ],
        },
    )
    job = service.request_mail_summary()
    ready = service.run_mail_summary(job.job_id)
    assert ready.status == "ready"
    assert aion.summarized == 1
    encoded = json.dumps(service.ledger.read_all(), ensure_ascii=False)
    assert "private subject" not in encoded
    assert "private@example.com" not in encoded
    assert "今日有一封" not in encoded
    assert "summary_sha256" in encoded


def _successful_run(job: str, run_id: str, started: datetime) -> list[dict]:
    return [
        {
            "event_id": f"{run_id}-start",
            "kind": "run_started",
            "run_id": run_id,
            "ts": started.isoformat(),
            "payload": {"job": job},
        },
        {
            "event_id": f"{run_id}-finish",
            "kind": "run_finished",
            "run_id": run_id,
            "ts": (started + timedelta(seconds=1)).isoformat(),
            "payload": {
                "job": job,
                "status": "succeeded",
                "exit_code": 0,
                "duration_s": 1.0,
            },
        },
    ]


def test_console_fleet_health_cannot_treat_success_as_watchdog_coverage():
    now = datetime(2026, 7, 13, 18, tzinfo=UTC)
    events = [
        *_successful_run("managed", "RUN1", now - timedelta(minutes=10)),
        *_successful_run("stray", "RUN2", now - timedelta(minutes=5)),
    ]
    result = _fleet_health(
        events,
        [{"job": "managed", "expected_interval_seconds": 3600, "grace_seconds": 60}],
        now=now,
        pending_projection=0,
    )
    assert result == {
        "monitored_jobs": 1,
        "healthy_jobs": 1,
        "problem_jobs": 1,
        "missed_jobs": 0,
        "coverage_status": "partial",
        "fleet_healthy": False,
    }


def test_console_fleet_health_fails_closed_without_active_schedules():
    now = datetime(2026, 7, 13, 18, tzinfo=UTC)
    result = _fleet_health(
        _successful_run("stray", "RUN1", now - timedelta(minutes=5)),
        [],
        now=now,
        pending_projection=0,
    )
    assert result["coverage_status"] == "none"
    assert result["monitored_jobs"] == 0
    assert result["healthy_jobs"] == 0
    assert result["problem_jobs"] == 1
    assert result["fleet_healthy"] is False


def test_console_fleet_health_requires_zero_projection_backlog():
    now = datetime(2026, 7, 13, 18, tzinfo=UTC)
    result = _fleet_health(
        _successful_run("managed", "RUN1", now - timedelta(minutes=5)),
        [{"job": "managed", "expected_interval_seconds": 3600, "grace_seconds": 60}],
        now=now,
        pending_projection=2,
    )
    assert result["coverage_status"] == "full"
    assert result["healthy_jobs"] == 1
    assert result["problem_jobs"] == 0
    assert result["fleet_healthy"] is False


def test_console_dashboard_uses_one_authoritative_ledger_snapshot(monkeypatch, console_env):
    _, service, _, _ = console_env
    original_read = service.ledger.read_all
    reads = 0

    def counted_read():
        nonlocal reads
        reads += 1
        return original_read()

    class HealthyResponse:
        def raise_for_status(self):
            return None

    monkeypatch.setattr(service.ledger, "read_all", counted_read)
    monkeypatch.setattr(
        "quarterdeck.console.service.httpx.get", lambda *args, **kwargs: HealthyResponse()
    )
    service.dashboard()
    assert reads == 1


def test_console_requires_csrf_and_serves_built_frontend(console_env, monkeypatch):
    settings, service, _, _ = console_env
    monkeypatch.setattr(
        service,
        "dashboard",
        lambda: {
            "generated_at": "now",
            "integrations": {},
            "fleet": {
                "runs": 0,
                "artifacts": 0,
                "pending_projection": 0,
                "jobs": 0,
                "monitored_jobs": 0,
                "healthy_jobs": 0,
                "problem_jobs": 0,
                "missed_jobs": 0,
                "coverage_status": "none",
                "fleet_healthy": False,
            },
            "pending_approvals": 0,
            "workflows": [],
            "plans": [],
            "recent_runs": [],
            "mail_ready": False,
        },
    )
    with TestClient(
        create_app(settings, service=service),
        base_url="http://127.0.0.1:8765",
    ) as client:
        denied_host = client.get(
            "/api/v1/bootstrap",
            headers={"Host": "rebound.example"},
        )
        assert denied_host.status_code == 400
        boot = client.get("/api/v1/bootstrap")
        assert boot.status_code == 200
        csrf = boot.json()["csrf_token"]
        denied = client.post("/api/v1/plans", json={"objective": "plan this"})
        assert denied.status_code == 403
        bad_origin = client.post(
            "/api/v1/plans",
            json={"objective": "plan this"},
            headers={"X-QD-CSRF": csrf, "Origin": "https://evil.example"},
        )
        assert bad_origin.status_code == 403
        accepted = client.post(
            "/api/v1/plans",
            json={"objective": "plan this"},
            headers={"X-QD-CSRF": csrf, "Origin": "http://127.0.0.1:8765"},
        )
        assert accepted.status_code == 202
        page = client.get("/")
        assert page.status_code == 200
        assert "Quarterdeck" in page.text
        assert page.headers["x-frame-options"] == "DENY"


def test_aionui_base_is_loopback_only(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir(mode=0o700)
    monkeypatch.setenv("QD_CONFIG_DIR", str(config))
    with pytest.raises(ValueError, match="loopback"):
        Settings(console={"aionui_base": "https://remote.example"})
    with pytest.raises(ValueError, match="loopback"):
        Settings(console={"aionui_base": "http://127.0.0.1:63021/unexpected"})
    settings = Settings(console={"aionui_base": "http://127.0.0.1:63021"})
    assert AionUiClient(settings.console).base == "http://127.0.0.1:63021"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ({"mcp_ready": True}, "已就绪"),
        ({"mcp_ready": False, "error": "mail integration is disabled"}, "未启用"),
        ({"mcp_ready": False, "error": "metadata consent is required"}, "待授权"),
        ({"mcp_ready": False, "error": "/private/config/path missing"}, "待配置"),
    ],
)
def test_mail_setup_detail_is_localized_and_does_not_leak_errors(status, expected):
    assert _mail_setup_detail(status) == expected
