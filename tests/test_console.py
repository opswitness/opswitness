import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quarterdeck.config import Settings
from quarterdeck.console.aionui import AionUiClient, AionUiError
from quarterdeck.console.app import create_app
from quarterdeck.console.schemas import ConfirmRequest, ExecutionState, PlanRequest, TaskPlan
from quarterdeck.console.service import (
    DISPATCH_INTERRUPTED,
    DISPATCH_INTERRUPTED_DETAIL,
    EXECUTION_DISPATCH_FAILED,
    EXECUTION_DISPATCH_FAILED_DETAIL,
    EXECUTION_PLAN_INVALID,
    EXECUTION_PLAN_INVALID_DETAIL,
    EXECUTION_REMOTE_FAILED_DETAIL,
    EXECUTION_STATUS_UNAVAILABLE_DETAIL,
    MAIL_SUMMARY_FAILURE,
    PLAN_GENERATION_FAILED,
    PLAN_GENERATION_FAILED_DETAIL,
    PLANNING_INTERRUPTED,
    PLANNING_INTERRUPTED_DETAIL,
    SCHEDULE_CONFIGURATION_INVALID_DETAIL,
    ConsoleConflict,
    ConsoleService,
    ConsoleUnavailable,
    _fleet_health,
    _mail_setup_detail,
)
from quarterdeck.ledger import Ledger
from quarterdeck.paperclip import PaperclipError


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


def test_concurrent_confirmation_consumes_ready_plan_once(console_env):
    _, service, _, _ = console_env
    requested = service.request_plan(PlanRequest(objective="并发确认测试"))
    ready = service.draft_plan(requested.plan_id)
    request = ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(service.confirm_plan, ready.plan_id, request) for _ in range(2)]
    results = []
    errors = []
    for future in futures:
        try:
            results.append(future.result())
        except ConsoleConflict as exc:
            errors.append(exc)

    assert [row.status for row in results] == ["confirmed"]
    assert len(errors) == 1
    assert sum(event["kind"] == "task_plan_confirmed" for event in service.ledger.read_all()) == 1


def test_dispatch_claim_prevents_duplicate_remote_side_effects(console_env, monkeypatch):
    _, service, aion, paperclip = console_env
    requested = service.request_plan(PlanRequest(objective="并发派发测试"))
    ready = service.draft_plan(requested.plan_id)
    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
    )
    entered = threading.Event()
    release = threading.Event()

    def slow_list_issues():
        entered.set()
        assert release.wait(timeout=2)
        return []

    monkeypatch.setattr(paperclip, "list_issues", slow_list_issues)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.dispatch_plan, ready.plan_id)
        assert entered.wait(timeout=2)
        second = pool.submit(service.dispatch_plan, ready.plan_id)
        second_result = second.result(timeout=2)
        release.set()
        first_result = first.result(timeout=2)

    assert second_result.status == "dispatching"
    assert first_result.status == "running"
    assert paperclip.created == 1
    assert aion.dispatched == 1
    assert (
        sum(event["kind"] == "task_execution_requested" for event in service.ledger.read_all()) == 1
    )


def test_startup_recovery_fails_closed_and_only_schedules_safe_transitions(
    console_env, monkeypatch
):
    _, service, aion, paperclip = console_env
    planning = service.request_plan(PlanRequest(objective="中断的规划"))

    confirmed_request = service.request_plan(PlanRequest(objective="可恢复的确认"))
    confirmed_ready = service.draft_plan(confirmed_request.plan_id)
    service.confirm_plan(
        confirmed_ready.plan_id,
        ConfirmRequest(plan_sha256=str(confirmed_ready.plan_sha256), confirmed=True),
    )

    ambiguous_request = service.request_plan(PlanRequest(objective="中断的派发"))
    ambiguous_ready = service.draft_plan(ambiguous_request.plan_id)
    service.confirm_plan(
        ambiguous_ready.plan_id,
        ConfirmRequest(plan_sha256=str(ambiguous_ready.plan_sha256), confirmed=True),
    )

    def make_dispatching(current):
        current.status = "dispatching"
        current.execution = ExecutionState(kind="aion_team")
        return current

    service.store.mutate(ambiguous_ready.plan_id, make_dispatching)

    active_request = service.request_plan(PlanRequest(objective="运行中的任务"))
    active_ready = service.draft_plan(active_request.plan_id)
    service.confirm_plan(
        active_ready.plan_id,
        ConfirmRequest(plan_sha256=str(active_ready.plan_sha256), confirmed=True),
    )
    service.dispatch_plan(active_ready.plan_id)
    assert aion.dispatched == 1
    assert paperclip.created == 1
    submitted = []
    monkeypatch.setattr(
        service,
        "_submit",
        lambda fn, plan_id: submitted.append((fn.__name__, plan_id)),
    )
    result = service.recover_plans()

    assert result == {
        "planning_failed": 1,
        "dispatching_failed": 1,
        "confirmed_scheduled": 1,
        "active_refresh_scheduled": 1,
    }
    assert set(submitted) == {
        ("dispatch_plan", confirmed_ready.plan_id),
        ("refresh_execution", active_ready.plan_id),
    }
    planning_after = service.get_plan(planning.plan_id, refresh=False)
    assert planning_after.status == "failed"
    assert planning_after.error == PLANNING_INTERRUPTED_DETAIL
    ambiguous_after = service.get_plan(ambiguous_ready.plan_id, refresh=False)
    assert ambiguous_after.status == "failed"
    assert ambiguous_after.error == DISPATCH_INTERRUPTED_DETAIL
    assert ambiguous_after.execution is not None
    assert ambiguous_after.execution.status == "failed"
    reasons = {
        event["payload"].get("reason")
        for event in service.ledger.read_all()
        if event["kind"] in {"task_plan_failed", "task_execution_failed"}
    }
    assert {PLANNING_INTERRUPTED, DISPATCH_INTERRUPTED} <= reasons
    assert aion.dispatched == 1
    assert paperclip.created == 1


def test_startup_recovery_rejects_corrupt_plan_records(console_env):
    _, service, _, _ = console_env
    service.store._ensure()
    corrupt = service.store.plans_dir / "01ARZ3NDEKTSV4RRFFQ69G5FAV.json"
    corrupt.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError):
        service.recover_plans()


def test_console_instance_lease_is_exclusive_and_reusable(console_env):
    settings, service, aion, paperclip = console_env
    contender = ConsoleService(
        settings,
        aion=aion,  # type: ignore[arg-type]
        paperclip_factory=lambda: paperclip,  # type: ignore[arg-type,return-value]
        background=False,
    )
    assert service.acquire_instance_lease() is True
    assert service.acquire_instance_lease() is False
    with pytest.raises(ConsoleUnavailable, match="another console instance"):
        contender.acquire_instance_lease()
    service.release_instance_lease()
    assert contender.acquire_instance_lease() is True
    contender.close()


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
    assert failed.error == EXECUTION_PLAN_INVALID_DETAIL
    assert paperclip.created == 0
    assert aion.dispatched == 0
    assert "task_execution_requested" not in [
        event["kind"] for event in service.ledger.read_all() if event["run_id"] == second.plan_id
    ]
    failure = service.ledger.read_all()[-1]
    assert failure["kind"] == "task_execution_failed"
    assert failure["payload"]["reason"] == EXECUTION_PLAN_INVALID


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


def test_planning_failure_never_persists_or_returns_third_party_error_text(
    monkeypatch, console_env
):
    _, service, aion, _ = console_env
    hostile = "private planning echo from /Users/private/research"
    requested = service.request_plan(PlanRequest(objective="私有规划目标"))

    def planning_failed(*args, **kwargs):
        del args, kwargs
        raise AionUiError(hostile)

    monkeypatch.setattr(aion, "generate_plan", planning_failed)
    failed = service.draft_plan(requested.plan_id)
    assert failed.status == "failed"
    assert failed.error == PLAN_GENERATION_FAILED_DETAIL
    encoded = json.dumps(service.ledger.read_all(), ensure_ascii=False)
    assert hostile not in encoded
    assert f'"reason": "{PLAN_GENERATION_FAILED}"' in encoded


def test_dispatch_failure_never_persists_or_returns_third_party_error_text(
    monkeypatch, console_env
):
    _, service, _, paperclip = console_env
    hostile = "private dispatch echo from /Users/private/workspace"
    requested = service.request_plan(PlanRequest(objective="私有派发目标"))
    ready = service.draft_plan(requested.plan_id)
    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
    )

    def dispatch_failed():
        raise PaperclipError(hostile)

    monkeypatch.setattr(paperclip, "list_issues", dispatch_failed)
    failed = service.dispatch_plan(ready.plan_id)
    assert failed.status == "failed"
    assert failed.error == EXECUTION_DISPATCH_FAILED_DETAIL
    assert failed.execution is not None
    assert failed.execution.error == EXECUTION_DISPATCH_FAILED_DETAIL
    encoded = json.dumps(service.ledger.read_all(), ensure_ascii=False)
    assert hostile not in encoded
    assert f'"reason": "{EXECUTION_DISPATCH_FAILED}"' in encoded


def test_execution_refresh_contains_remote_failure_and_status_errors(monkeypatch, console_env):
    _, service, aion, _ = console_env
    hostile = "private runtime echo from /Users/private/output"
    requested = service.request_plan(PlanRequest(objective="私有运行目标"))
    ready = service.draft_plan(requested.plan_id)
    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
    )
    service.dispatch_plan(ready.plan_id)
    monkeypatch.setattr(
        aion,
        "execution_snapshot",
        lambda *args: {"status": "failed", "error": hostile},
    )
    failed = service.refresh_execution(ready.plan_id)
    assert failed.status == "failed"
    assert failed.execution is not None
    assert failed.execution.error == EXECUTION_REMOTE_FAILED_DETAIL
    assert hostile not in json.dumps(failed.model_dump(mode="json"), ensure_ascii=False)
    assert hostile not in json.dumps(service.ledger.read_all(), ensure_ascii=False)

    second = service.request_plan(PlanRequest(objective="第二个私有运行目标"))
    second_ready = service.draft_plan(second.plan_id)
    service.confirm_plan(
        second_ready.plan_id,
        ConfirmRequest(plan_sha256=str(second_ready.plan_sha256), confirmed=True),
    )
    service.dispatch_plan(second_ready.plan_id)

    def status_failed(*args):
        del args
        raise AionUiError(hostile)

    monkeypatch.setattr(aion, "execution_snapshot", status_failed)
    unavailable = service.refresh_execution(second_ready.plan_id)
    assert unavailable.status == "running"
    assert unavailable.execution is not None
    assert unavailable.execution.error == EXECUTION_STATUS_UNAVAILABLE_DETAIL
    assert hostile not in json.dumps(unavailable.model_dump(mode="json"), ensure_ascii=False)


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


def test_mail_summary_failure_never_persists_or_returns_third_party_error_text(
    monkeypatch, console_env
):
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

    def hostile_failure(job_id, messages):
        del job_id, messages
        raise RuntimeError("private subject private@example.com")

    monkeypatch.setattr(aion, "summarize_mail", hostile_failure)
    job = service.request_mail_summary()
    failed = service.run_mail_summary(job.job_id)
    assert failed.status == "failed"
    assert failed.error == MAIL_SUMMARY_FAILURE
    encoded = json.dumps(service.ledger.read_all(), ensure_ascii=False)
    assert "private subject" not in encoded
    assert "private@example.com" not in encoded
    assert '"reason": "mail_summary_failed"' in encoded


def test_aionui_mail_summary_fails_when_ephemeral_team_cleanup_is_unconfirmed(
    monkeypatch, console_env
):
    settings, _, _, _ = console_env
    client = AionUiClient(settings.console)
    team = {
        "id": "team-private",
        "assistants": [{"role": "lead", "conversation_id": "conversation-private"}],
    }
    monkeypatch.setattr(client, "create_team", lambda **kwargs: team)
    monkeypatch.setattr(client, "ensure_team", lambda team_id: None)
    monkeypatch.setattr(client, "set_team_mode", lambda team_id, mode: None)
    monkeypatch.setattr(client, "_run_and_wait", lambda *args, **kwargs: "摘要")

    def cleanup_failed(team_id):
        raise AionUiError("private subject leaked by upstream")

    monkeypatch.setattr(client, "delete_team", cleanup_failed)
    with pytest.raises(AionUiError, match="cleanup could not be confirmed") as exc:
        client.summarize_mail(
            "MAIL1",
            [
                {
                    "message_id": "private-id",
                    "from": "private@example.com",
                    "subject": "private subject",
                    "date": "today",
                }
            ],
        )
    assert "private subject" not in str(exc.value)


def test_aionui_planning_fails_when_ephemeral_team_cleanup_is_unconfirmed(monkeypatch, console_env):
    settings, _, _, _ = console_env
    client = AionUiClient(settings.console)
    team = {
        "id": "team-plan",
        "assistants": [{"role": "lead", "conversation_id": "conversation-plan"}],
    }
    monkeypatch.setattr(
        client,
        "list_assistants",
        lambda: [
            {
                "id": settings.console.planner_assistant_id,
                "enabled": True,
                "team_selectable": True,
            }
        ],
    )
    monkeypatch.setattr(client, "create_team", lambda **kwargs: team)
    monkeypatch.setattr(client, "ensure_team", lambda team_id: None)
    monkeypatch.setattr(client, "set_team_mode", lambda team_id, mode: None)
    monkeypatch.setattr(
        client,
        "_run_and_wait",
        lambda *args, **kwargs: _plan().model_dump_json(),
    )

    def planning_cleanup_failed(team_id):
        del team_id
        raise AionUiError("delete failed")

    monkeypatch.setattr(client, "delete_team", planning_cleanup_failed)
    with pytest.raises(AionUiError, match="planning team cleanup could not be confirmed"):
        client.generate_plan("PLAN1", PlanRequest(objective="生成摘要"), [])


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
        "coverage_error": None,
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
    result = service.dashboard()
    assert reads == 1
    assert result["approvals_available"] is True
    assert result["pending_approvals"] == 0


def test_console_dashboard_never_reports_zero_when_approvals_are_unavailable(
    monkeypatch, console_env
):
    _, service, _, _ = console_env

    class HealthyResponse:
        def raise_for_status(self):
            return None

    class FailingApprovals:
        def list_approvals(self, status=None):
            del status
            raise PaperclipError("approval API unavailable")

    monkeypatch.setattr(
        "quarterdeck.console.service.httpx.get", lambda *args, **kwargs: HealthyResponse()
    )
    monkeypatch.setattr(service, "_paperclip_factory", lambda: FailingApprovals())
    result = service.dashboard()
    assert result["pending_approvals"] is None
    assert result["approvals_available"] is False
    assert result["integrations"]["paperclip"]["status"] == "attention"
    assert result["integrations"]["paperclip"]["detail"] == "审批状态不可用"


def test_console_dashboard_contains_schedule_parser_errors(monkeypatch, console_env):
    _, service, _, _ = console_env
    hostile = "private schedule parser echo from /Users/private/config.yaml"

    def invalid_schedules(*args, **kwargs):
        del args, kwargs
        raise ValueError(hostile)

    monkeypatch.setattr(
        "quarterdeck.console.service.load_effective_schedules",
        invalid_schedules,
    )
    result = service.dashboard()
    assert result["fleet"]["coverage_status"] == "none"
    assert result["fleet"]["fleet_healthy"] is False
    encoded = json.dumps(result, ensure_ascii=False)
    assert hostile not in encoded
    assert SCHEDULE_CONFIGURATION_INVALID_DETAIL in encoded


def test_console_requires_csrf_and_serves_built_frontend(console_env, monkeypatch):
    settings, service, _, _ = console_env
    lifecycle = []
    monkeypatch.setattr(
        service,
        "acquire_instance_lease",
        lambda: lifecycle.append("lease") or True,
    )
    monkeypatch.setattr(
        service,
        "recover_plans",
        lambda: lifecycle.append("recovery") or {},
    )
    monkeypatch.setattr(
        service,
        "release_instance_lease",
        lambda: lifecycle.append("release"),
    )
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
            "approvals_available": True,
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
    assert lifecycle == ["lease", "recovery", "release"]


def test_console_lifespan_releases_lease_when_recovery_fails(console_env, monkeypatch):
    settings, service, _, _ = console_env
    lifecycle = []
    monkeypatch.setattr(
        service,
        "acquire_instance_lease",
        lambda: lifecycle.append("lease") or True,
    )

    def recovery_failed():
        lifecycle.append("recovery")
        raise ConsoleUnavailable("recovery failed closed")

    monkeypatch.setattr(service, "recover_plans", recovery_failed)
    monkeypatch.setattr(
        service,
        "release_instance_lease",
        lambda: lifecycle.append("release"),
    )
    with pytest.raises(ConsoleUnavailable, match="recovery failed closed"):
        with TestClient(
            create_app(settings, service=service),
            base_url="http://127.0.0.1:8765",
        ):
            pass
    assert lifecycle == ["lease", "recovery", "release"]


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
