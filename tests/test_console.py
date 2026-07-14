import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quarterdeck.config import Settings
from quarterdeck.console.aionui import (
    AionUiClient,
    AionUiError,
    EphemeralSession,
    _planning_prompt,
    _validate_plan_brief,
    _validate_revision_changed,
)
from quarterdeck.console.app import create_app
from quarterdeck.console.schemas import (
    ApprovalDecisionRequest,
    ConfirmRequest,
    DeletePlanRequest,
    ExecutionState,
    MailAuthorizationRequest,
    MailOAuthClientRequest,
    OrganizationRevisionRequest,
    PlanRequest,
    RevisePlanRequest,
    TaskPlan,
    TelegramConfigureRequest,
)
from quarterdeck.console.service import (
    DISPATCH_INTERRUPTED,
    DISPATCH_INTERRUPTED_DETAIL,
    EPHEMERAL_RECOVERY_UNAVAILABLE,
    EXECUTION_DISPATCH_FAILED,
    EXECUTION_DISPATCH_FAILED_DETAIL,
    EXECUTION_PLAN_INVALID,
    EXECUTION_PLAN_INVALID_DETAIL,
    EXECUTION_REMOTE_FAILED_DETAIL,
    EXECUTION_STATUS_UNAVAILABLE_DETAIL,
    MAIL_AUTHORIZATION_FAILURE,
    MAIL_OAUTH_CLIENT_REJECTED,
    MAIL_SUMMARY_FAILURE,
    PLAN_GENERATION_FAILED,
    PLAN_GENERATION_FAILED_DETAIL,
    PLANNING_INTERRUPTED,
    PLANNING_INTERRUPTED_DETAIL,
    SCHEDULE_CONFIGURATION_INVALID_DETAIL,
    TELEGRAM_CONFIGURATION_REJECTED,
    TELEGRAM_ENVIRONMENT_CONTROLLED,
    TELEGRAM_TEST_FAILED,
    ConsoleConflict,
    ConsoleService,
    ConsoleUnavailable,
    _fleet_health,
    _mail_setup_detail,
)
from quarterdeck.console.store import PlanNotFound
from quarterdeck.ledger import Ledger
from quarterdeck.paperclip import PaperclipError


def _plan(execution_mode: str = "aion_team", workflow_id: str | None = None) -> TaskPlan:
    return TaskPlan.model_validate(
        {
            "schema_version": 1,
            "title": "每日研究摘要",
            "summary": (
                "目标：收集、复核并汇报当天研究结果。\n"
                "输入与边界：只处理任务明确提供的研究材料，不读取未授权目录。\n"
                "方法与分工：总控负责收集和组织，复核负责检查证据、矛盾和遗漏。\n"
                "检查点：候选摘要形成后必须完成证据复核，异常时停止交付。\n"
                "交付物：生成一份带来源说明、问题清单和状态结论的摘要报告。\n"
                "不包含：不自动发布、不修改原始材料，也不把进程完成当作业务结果成功。"
            ),
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


def _fortune_plan() -> TaskPlan:
    return TaskPlan.model_validate(
        {
            "schema_version": 1,
            "title": "八字命理报告演示",
            "summary": (
                "目标：创建一个八字命理报告演示任务。\n"
                "输入与边界：只使用合成客户 DEMO-001，不使用真人个人信息。\n"
                "方法与分工：lunar-python 负责确定性排盘；AI 仅基于知识库解释，由解读 Agent、"
                "引用核验 Agent 和报告编辑 Agent 协作。\n"
                "检查点：排盘依赖验证后才能起草，最终交付前必须完成人工审签。\n"
                "交付物：输出可追溯的命盘 JSON、引用清单、审核结果和 PDF 报告。\n"
                "不包含：不发送报告，不使用真人个人信息，也不承诺预测结果。"
            ),
            "execution_mode": "aion_team",
            "workflow_id": None,
            "agents": [
                {
                    "name": "解读 Agent",
                    "role": "lead",
                    "responsibility": "根据确定性命盘和知识库片段起草解释",
                    "runtime": "claude_code",
                },
                {
                    "name": "引用核验 Agent",
                    "role": "reviewer",
                    "responsibility": "核验引用、矛盾和禁忌表述",
                    "runtime": "codex_cli",
                },
                {
                    "name": "报告编辑 Agent",
                    "role": "reporter",
                    "responsibility": "整理经审核的内容与交付格式",
                    "runtime": "aion_cli",
                },
            ],
            "stages": [
                {
                    "order": 1,
                    "title": "确定性排盘",
                    "owner": "解读 Agent",
                    "outcome": "生成并验证合成客户命盘",
                    "checkpoint": True,
                },
                {
                    "order": 2,
                    "title": "解释与核验",
                    "owner": "引用核验 Agent",
                    "outcome": "形成带引用和审核结果的草稿",
                    "checkpoint": True,
                },
                {
                    "order": 3,
                    "title": "编辑与审签",
                    "owner": "报告编辑 Agent",
                    "outcome": "形成人工审签候选报告",
                    "checkpoint": True,
                },
            ],
            "cadence": {
                "kind": "once",
                "timezone": "America/Los_Angeles",
                "local_time": None,
                "update_interval": "每个案例单次运行",
            },
            "tools": ["lunar-python（执行前验证）", "签名知识库"],
            "approvals": ["最终报告人工审签"],
            "artifacts": ["命盘 JSON", "引用清单", "审核结果", "PDF 报告"],
            "risks": ["lunar-python 尚未验证可用", "知识来源可能不完整"],
            "estimated_duration_minutes": 30,
            "update_policy": "每个检查点更新一次，依赖或审签不可用时立即停止。",
        }
    )


class FakeAion:
    def __init__(self) -> None:
        self.generated = 0
        self.dispatched = 0
        self.summarized = 0
        self.previous_plan: TaskPlan | None = None
        self.revision_instruction = ""
        self.stale_sessions: list[EphemeralSession] = []
        self.recovered_sessions: list[EphemeralSession] = []

    def health(self):
        return {"platform": "darwin"}

    def list_assistants(self):
        return [
            {
                "id": "bare:8e1acf31",
                "enabled": True,
                "team_selectable": True,
            },
            {
                "id": "bare:2d23ff1c",
                "enabled": True,
                "team_selectable": True,
            },
        ]

    def stale_ephemeral_sessions(self):
        return list(self.stale_sessions)

    def recover_ephemeral_session(self, session):
        self.recovered_sessions.append(session)
        return {"team_deleted": session.team_id is not None, "workspace_removed": True}

    def generate_plan(
        self,
        plan_id,
        request,
        catalog,
        progress=None,
        *,
        assistant_id=None,
        previous_plan=None,
        revision_instruction="",
    ):
        del plan_id, request, catalog, assistant_id
        self.generated += 1
        self.previous_plan = previous_plan
        self.revision_instruction = revision_instruction
        if progress is not None:
            progress("generating_plan", 30)
            progress("validating", 78)
            progress("cleaning_up", 94)
        plan = _plan()
        if previous_plan is not None:
            plan.title = "每周研究摘要"
            plan.cadence.kind = "weekly"
            plan.cadence.update_interval = "每周五更新"
        return plan

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
        self.approvals: list[dict] = []
        self.descriptions: list[str] = []

    def list_issues(self):
        return []

    def create_issue(self, title, description):
        assert title.startswith("[qd-plan:")
        assert "outcome proof" in description
        assert "reports to " in description
        assert "Bounded collaboration loops:" in description
        self.descriptions.append(description)
        self.created += 1
        return {"id": "issue-1"}

    def list_approvals(self, status=None):
        del status
        return [row for row in self.approvals if row.get("status") == "pending"]

    def get_approval(self, approval_id):
        return next(row for row in self.approvals if row["id"] == approval_id)

    def resolve_approval(self, approval_id, decision, decision_note=None):
        row = self.get_approval(approval_id)
        row["status"] = "approved" if decision == "approve" else "rejected"
        row["decisionNote"] = decision_note
        return row


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
        provider_probe=lambda provider: {
            "provider": provider,
            "label": "ChatGPT / OpenAI" if provider == "openai" else "Claude",
            "installed": True,
            "authenticated": provider == "openai",
            "auth_mode": "chatgpt" if provider == "openai" else "none",
            "status": "online" if provider == "openai" else "setup",
            "detail": "账号已登录" if provider == "openai" else "待登录",
        },
        provider_login=lambda provider: provider == "openai",
        background=False,
    )
    yield settings, service, aion, paperclip
    service.close()


def test_plan_schema_requires_one_lead_and_exact_stage_owners():
    raw = _plan().model_dump(mode="json")
    raw["agents"][0]["role"] = "reviewer"
    with pytest.raises(ValueError, match="exactly one lead"):
        TaskPlan.model_validate(raw)


def test_plan_schema_supports_legacy_star_and_rejects_invalid_reporting_trees():
    legacy = _fortune_plan()
    assert legacy.effective_reporting_lines() == {
        "解读 Agent": None,
        "引用核验 Agent": "解读 Agent",
        "报告编辑 Agent": "解读 Agent",
    }

    explicit = legacy.model_dump(mode="json")
    explicit["agents"][1]["reports_to"] = "解读 Agent"
    explicit["agents"][2]["reports_to"] = "引用核验 Agent"
    validated = TaskPlan.model_validate(explicit)
    assert validated.effective_reporting_lines()["报告编辑 Agent"] == "引用核验 Agent"

    missing_manager = legacy.model_dump(mode="json")
    missing_manager["agents"][1]["reports_to"] = "解读 Agent"
    with pytest.raises(ValueError, match="every non-lead agent"):
        TaskPlan.model_validate(missing_manager)

    cycle = legacy.model_dump(mode="json")
    cycle["agents"][1]["reports_to"] = "报告编辑 Agent"
    cycle["agents"][2]["reports_to"] = "引用核验 Agent"
    with pytest.raises(ValueError, match="acyclic"):
        TaskPlan.model_validate(cycle)


def test_plan_schema_allows_bounded_collaboration_cycles_but_validates_contract():
    raw = _fortune_plan().model_dump(mode="json")
    raw["collaboration_loops"] = [
        {
            "source_agent": "引用核验 Agent",
            "target_agent": "报告编辑 Agent",
            "condition": "引用未通过时返回编辑；通过即停止",
            "max_iterations": 2,
        },
        {
            "source_agent": "报告编辑 Agent",
            "target_agent": "报告编辑 Agent",
            "condition": "版式未通过时自检；通过即停止",
            "max_iterations": 3,
        },
    ]
    validated = TaskPlan.model_validate(raw)
    assert validated.collaboration_loops[0].max_iterations == 2
    assert validated.collaboration_loops[1].source_agent == "报告编辑 Agent"

    unknown = json.loads(json.dumps(raw, ensure_ascii=False))
    unknown["collaboration_loops"][0]["target_agent"] = "不存在 Agent"
    with pytest.raises(ValueError, match="exact planned agents"):
        TaskPlan.model_validate(unknown)

    duplicate = json.loads(json.dumps(raw, ensure_ascii=False))
    duplicate["collaboration_loops"].append(duplicate["collaboration_loops"][0])
    with pytest.raises(ValueError, match="pairs must be unique"):
        TaskPlan.model_validate(duplicate)

    out_of_bounds = json.loads(json.dumps(raw, ensure_ascii=False))
    out_of_bounds["collaboration_loops"][0]["max_iterations"] = 11
    with pytest.raises(ValueError):
        TaskPlan.model_validate(out_of_bounds)

    workflow = _plan(execution_mode="workflow", workflow_id="daily-research").model_dump(
        mode="json"
    )
    workflow["collaboration_loops"] = [
        {
            "source_agent": "复核",
            "target_agent": "总控",
            "condition": "证据不完整时返回；通过即停止",
            "max_iterations": 2,
        }
    ]
    with pytest.raises(ValueError, match="runtime with agent loops"):
        TaskPlan.model_validate(workflow)


def test_planner_turns_terse_fortune_intent_into_a_validated_execution_brief():
    request = PlanRequest(objective="算命师")
    prompt = _planning_prompt(request, [])
    assert "AI-expanded execution brief" in prompt
    assert "DEMO-001" in prompt
    assert "lunar-python" in prompt
    assert "解读 Agent" in prompt
    assert '"reports_to":null' in prompt
    assert '"collaboration_loops"' in prompt
    assert "max_iterations from 1 through 10" in prompt
    assert "may point back to an earlier agent or to the same agent" in prompt
    assert "never send the report" in prompt

    plan = _fortune_plan()
    _validate_plan_brief(plan, request)

    invalid = plan.model_copy(deep=True)
    invalid.summary = invalid.summary.replace("人工审签", "自动通过")
    with pytest.raises(ValueError, match="required defaults"):
        _validate_plan_brief(invalid, request)

    raw = _plan().model_dump(mode="json")
    raw["stages"][0]["owner"] = "不存在"
    with pytest.raises(ValueError, match="stage owner"):
        TaskPlan.model_validate(raw)


def test_revision_prompt_carries_the_previous_plan_and_requires_a_real_change():
    previous = _plan()
    prompt = _planning_prompt(
        PlanRequest(objective="生成研究摘要"),
        [],
        previous_plan=previous,
        revision_instruction="改成每周更新，并减少不必要的步骤",
    )
    assert "versioned revision" in prompt
    assert "previous_plan" in prompt
    assert "改成每周更新" in prompt
    with pytest.raises(ValueError, match="must differ"):
        _validate_revision_changed(previous.model_copy(deep=True), previous)


def test_plan_revision_is_append_only_hash_bound_and_blocks_the_parent(console_env):
    _, service, aion, _ = console_env
    requested = service.request_plan(PlanRequest(objective="生成研究摘要"))
    parent = service.draft_plan(requested.plan_id)
    instruction = "改成每周更新并保留 SECRET-REVISION-ONLY"

    revision = service.request_plan_revision(
        parent.plan_id,
        RevisePlanRequest(instruction=instruction),
    )
    assert revision.status == "planning"
    assert revision.parent_plan_id == parent.plan_id
    assert revision.parent_plan_sha256 == parent.plan_sha256
    assert revision.revision_number == 2
    assert revision.revision_instruction == instruction
    assert revision.revision_instruction_sha256

    duplicate = service.request_plan_revision(
        parent.plan_id,
        RevisePlanRequest(instruction="另一个并发修改要求"),
    )
    assert duplicate.plan_id == revision.plan_id

    ready = service.draft_plan(revision.plan_id)
    assert ready.status == "ready"
    assert ready.plan is not None
    assert ready.plan.title == "每周研究摘要"
    assert ready.plan_sha256 != parent.plan_sha256
    assert aion.previous_plan == parent.plan
    assert aion.revision_instruction == instruction

    with pytest.raises(ConsoleConflict, match="newer revision"):
        service.confirm_plan(
            parent.plan_id,
            ConfirmRequest(plan_sha256=str(parent.plan_sha256), confirmed=True),
        )
    confirmed = service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
    )
    assert confirmed.status == "confirmed"

    events = service.ledger.read_all()
    assert [event["kind"] for event in events] == [
        "task_plan_requested",
        "task_plan_drafted",
        "task_plan_revision_requested",
        "task_plan_drafted",
        "task_plan_confirmed",
    ]
    revision_event = events[2]
    assert revision_event["payload"]["parent_plan_id"] == parent.plan_id
    assert revision_event["payload"]["revision_number"] == 2
    assert "revision_instruction_sha256" in revision_event["payload"]
    assert "SECRET-REVISION-ONLY" not in json.dumps(events, ensure_ascii=False)


def test_plan_revision_http_facade_requires_csrf(console_env, monkeypatch):
    settings, service, _, _ = console_env
    requested = service.request_plan(PlanRequest(objective="生成研究摘要"))
    parent = service.draft_plan(requested.plan_id)
    monkeypatch.setattr(service, "acquire_instance_lease", lambda: True)
    monkeypatch.setattr(service, "recover_startup", lambda: {})
    monkeypatch.setattr(service, "release_instance_lease", lambda: None)
    app = create_app(settings, service=service)
    csrf = app.state.csrf_token
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        denied = client.post(
            f"/api/v1/plans/{parent.plan_id}/revise",
            json={"instruction": "改成每周更新"},
        )
        assert denied.status_code == 403
        accepted = client.post(
            f"/api/v1/plans/{parent.plan_id}/revise",
            json={"instruction": "改成每周更新"},
            headers={"X-QD-CSRF": csrf},
        )
        assert accepted.status_code == 202
        payload = accepted.json()
        assert payload["parent_plan_id"] == parent.plan_id
        assert payload["revision_number"] == 2


def test_organization_revision_is_hash_bound_append_only_and_blocks_parent(
    console_env, monkeypatch
):
    _, service, aion, _ = console_env
    monkeypatch.setattr(aion, "generate_plan", lambda *args, **kwargs: _fortune_plan())
    requested = service.request_plan(PlanRequest(objective="生成命理演示报告"))
    parent = service.draft_plan(requested.plan_id)

    revised = service.revise_plan_organization(
        parent.plan_id,
        OrganizationRevisionRequest(
            confirmed=True,
            reporting_lines=[
                {"employee": "解读 Agent", "reports_to": None},
                {"employee": "引用核验 Agent", "reports_to": "解读 Agent"},
                {"employee": "报告编辑 Agent", "reports_to": "引用核验 Agent"},
            ],
            collaboration_loops=[
                {
                    "source_agent": "引用核验 Agent",
                    "target_agent": "报告编辑 Agent",
                    "condition": "引用未通过时返回编辑；通过即停止",
                    "max_iterations": 2,
                }
            ],
        ),
    )
    assert revised.status == "ready"
    assert revised.parent_plan_id == parent.plan_id
    assert revised.revision_number == 2
    assert revised.plan_sha256 != parent.plan_sha256
    assert revised.plan is not None
    assert revised.plan.effective_reporting_lines()["报告编辑 Agent"] == "引用核验 Agent"
    assert revised.plan.collaboration_loops[0].max_iterations == 2
    with pytest.raises(ConsoleConflict, match="newer revision"):
        service.confirm_plan(
            parent.plan_id,
            ConfirmRequest(plan_sha256=str(parent.plan_sha256), confirmed=True),
        )

    events = service.ledger.read_all()
    assert [event["kind"] for event in events] == [
        "task_plan_requested",
        "task_plan_drafted",
        "task_plan_organization_revised",
    ]
    organization_event = events[-1]["payload"]
    assert organization_event["parent_plan_id"] == parent.plan_id
    assert organization_event["plan_sha256"] == revised.plan_sha256
    assert organization_event["agent_count"] == 3
    assert organization_event["loop_count"] == 1
    assert "解读 Agent" not in json.dumps(organization_event, ensure_ascii=False)


def test_organization_revision_rejects_unchanged_incomplete_and_cyclic_trees(
    console_env, monkeypatch
):
    _, service, aion, _ = console_env
    monkeypatch.setattr(aion, "generate_plan", lambda *args, **kwargs: _fortune_plan())
    requested = service.request_plan(PlanRequest(objective="组织结构校验"))
    parent = service.draft_plan(requested.plan_id)

    with pytest.raises(ConsoleConflict, match="unchanged"):
        service.revise_plan_organization(
            parent.plan_id,
            OrganizationRevisionRequest(
                confirmed=True,
                reporting_lines=[
                    {"employee": "解读 Agent", "reports_to": None},
                    {"employee": "引用核验 Agent", "reports_to": "解读 Agent"},
                    {"employee": "报告编辑 Agent", "reports_to": "解读 Agent"},
                ],
            ),
        )
    with pytest.raises(ConsoleConflict, match="every planned agent"):
        service.revise_plan_organization(
            parent.plan_id,
            OrganizationRevisionRequest(
                confirmed=True,
                reporting_lines=[
                    {"employee": "解读 Agent", "reports_to": None},
                    {"employee": "引用核验 Agent", "reports_to": "解读 Agent"},
                ],
            ),
        )
    with pytest.raises(ConsoleConflict, match="valid team plan"):
        service.revise_plan_organization(
            parent.plan_id,
            OrganizationRevisionRequest(
                confirmed=True,
                reporting_lines=[
                    {"employee": "解读 Agent", "reports_to": None},
                    {"employee": "引用核验 Agent", "reports_to": "报告编辑 Agent"},
                    {"employee": "报告编辑 Agent", "reports_to": "引用核验 Agent"},
                ],
            ),
        )


def test_organization_revision_can_change_only_bounded_loops(console_env, monkeypatch):
    _, service, aion, paperclip = console_env
    monkeypatch.setattr(aion, "generate_plan", lambda *args, **kwargs: _fortune_plan())
    requested = service.request_plan(PlanRequest(objective="循环协作调整"))
    parent = service.draft_plan(requested.plan_id)

    revised = service.revise_plan_organization(
        parent.plan_id,
        OrganizationRevisionRequest(
            confirmed=True,
            reporting_lines=[
                {"employee": "解读 Agent", "reports_to": None},
                {"employee": "引用核验 Agent", "reports_to": "解读 Agent"},
                {"employee": "报告编辑 Agent", "reports_to": "解读 Agent"},
            ],
            collaboration_loops=[
                {
                    "source_agent": "报告编辑 Agent",
                    "target_agent": "报告编辑 Agent",
                    "condition": "版式未通过时自检；通过即停止",
                    "max_iterations": 3,
                }
            ],
        ),
    )

    assert revised.plan is not None
    assert revised.plan.effective_reporting_lines() == parent.plan.effective_reporting_lines()
    assert revised.plan.collaboration_loops[0].source_agent == "报告编辑 Agent"
    assert revised.plan_sha256 != parent.plan_sha256
    service._create_or_find_issue(revised)
    assert "报告编辑 Agent -> 报告编辑 Agent (max 3:" in paperclip.descriptions[-1]


def test_organization_revision_http_facade_requires_csrf_and_confirmation(
    console_env, monkeypatch
):
    settings, service, aion, _ = console_env
    monkeypatch.setattr(aion, "generate_plan", lambda *args, **kwargs: _fortune_plan())
    requested = service.request_plan(PlanRequest(objective="HTTP 组织结构调整"))
    parent = service.draft_plan(requested.plan_id)
    monkeypatch.setattr(service, "acquire_instance_lease", lambda: True)
    monkeypatch.setattr(service, "recover_startup", lambda: {})
    monkeypatch.setattr(service, "release_instance_lease", lambda: None)
    app = create_app(settings, service=service)
    csrf = app.state.csrf_token
    path = f"/api/v1/plans/{parent.plan_id}/organization"
    body = {
        "confirmed": True,
        "reporting_lines": [
            {"employee": "解读 Agent", "reports_to": None},
            {"employee": "引用核验 Agent", "reports_to": "解读 Agent"},
            {"employee": "报告编辑 Agent", "reports_to": "引用核验 Agent"},
        ],
        "collaboration_loops": [
            {
                "source_agent": "报告编辑 Agent",
                "target_agent": "报告编辑 Agent",
                "condition": "版式未通过时自检；通过即停止",
                "max_iterations": 3,
            }
        ],
    }
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        denied = client.post(path, json=body)
        assert denied.status_code == 403
        unconfirmed = client.post(
            path,
            json={**body, "confirmed": False},
            headers={"X-QD-CSRF": csrf},
        )
        assert unconfirmed.status_code == 422
        accepted = client.post(path, json=body, headers={"X-QD-CSRF": csrf})
        assert accepted.status_code == 201
        assert accepted.json()["parent_plan_id"] == parent.plan_id
        assert accepted.json()["plan"]["collaboration_loops"][0]["max_iterations"] == 3


def test_plan_delete_is_append_only_idempotent_and_hides_the_plan(console_env):
    _, service, _, _ = console_env
    requested = service.request_plan(PlanRequest(objective="删除任务测试"))
    ready = service.draft_plan(requested.plan_id)
    plan_path = service.store.plans_dir / f"{ready.plan_id}.json"
    original_bytes = plan_path.read_bytes()

    result = service.delete_plan(ready.plan_id, DeletePlanRequest(confirmed=True))
    assert result["plan_id"] == ready.plan_id
    assert result["deleted"] is True
    assert result["deleted_at"]
    assert result["evidence_event_id"]
    assert plan_path.read_bytes() == original_bytes
    assert service.store.get(ready.plan_id) == ready
    assert service.list_plans() == []
    with pytest.raises(PlanNotFound):
        service.get_plan(ready.plan_id)

    repeated = service.delete_plan(ready.plan_id, DeletePlanRequest(confirmed=True))
    assert repeated == result
    events = service.ledger.read_all()
    assert [event["kind"] for event in events] == [
        "task_plan_requested",
        "task_plan_drafted",
        "task_plan_deleted",
    ]
    deleted = events[-1]
    assert deleted["payload"] == {
        "schema_version": 1,
        "source": "local_console",
        "status": "ready",
        "plan_sha256": ready.plan_sha256,
        "parent_plan_id": None,
        "revision_number": 1,
    }


def test_plan_delete_rejects_active_work_and_preserves_revision_order(console_env):
    _, service, _, _ = console_env
    active = service.request_plan(PlanRequest(objective="规划中的任务"))
    with pytest.raises(ConsoleConflict, match="active plans"):
        service.delete_plan(active.plan_id, DeletePlanRequest(confirmed=True))

    requested = service.request_plan(PlanRequest(objective="有修改版的任务"))
    parent = service.draft_plan(requested.plan_id)
    child = service.request_plan_revision(
        parent.plan_id,
        RevisePlanRequest(instruction="生成第二版方案"),
    )
    child = service.draft_plan(child.plan_id)
    with pytest.raises(ConsoleConflict, match="newer plan revisions"):
        service.delete_plan(parent.plan_id, DeletePlanRequest(confirmed=True))

    service.delete_plan(child.plan_id, DeletePlanRequest(confirmed=True))
    next_child = service.request_plan_revision(
        parent.plan_id,
        RevisePlanRequest(instruction="删除第二版后生成新的修改版"),
    )
    assert next_child.revision_number == 3


def test_plan_delete_http_facade_requires_csrf_and_confirmation(console_env, monkeypatch):
    settings, service, _, _ = console_env
    requested = service.request_plan(PlanRequest(objective="HTTP 删除测试"))
    ready = service.draft_plan(requested.plan_id)
    monkeypatch.setattr(service, "acquire_instance_lease", lambda: True)
    monkeypatch.setattr(service, "recover_startup", lambda: {})
    monkeypatch.setattr(service, "release_instance_lease", lambda: None)
    app = create_app(settings, service=service)
    csrf = app.state.csrf_token
    path = f"/api/v1/plans/{ready.plan_id}"
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        denied = client.request("DELETE", path, json={"confirmed": True})
        assert denied.status_code == 403
        unconfirmed = client.request(
            "DELETE",
            path,
            json={"confirmed": False},
            headers={"X-QD-CSRF": csrf},
        )
        assert unconfirmed.status_code == 422
        accepted = client.request(
            "DELETE",
            path,
            json={"confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        assert accepted.status_code == 200
        assert accepted.json()["deleted"] is True
        assert client.get(path).status_code == 404


def test_planning_has_no_execution_side_effect_before_confirmation(console_env):
    _, service, aion, paperclip = console_env
    record = service.request_plan(
        PlanRequest(objective="每天生成研究摘要", preferred_cadence="daily")
    )
    assert record.status == "planning"
    assert record.planning_progress is not None
    assert record.planning_progress.phase == "queued"
    assert record.planning_progress.percent == 5
    assert record.planning_progress.expected_seconds == 150
    assert record.planning_progress.timeout_seconds == 390
    assert aion.generated == 0
    assert aion.dispatched == 0
    assert paperclip.created == 0

    ready = service.draft_plan(record.plan_id)
    assert ready.status == "ready"
    assert aion.generated == 1
    assert aion.dispatched == 0
    assert paperclip.created == 0
    assert ready.planning_progress is not None
    assert ready.planning_progress.phase == "complete"
    assert ready.planning_progress.percent == 100
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


def test_console_startup_recovery_requires_instance_lease(console_env):
    _, service, _, _ = console_env
    with pytest.raises(ConsoleUnavailable, match="instance lease is required"):
        service.recover_startup()


def test_console_startup_recovery_records_ephemeral_cleanup_evidence(
    monkeypatch, console_env
):
    settings, service, aion, _ = console_env
    session = EphemeralSession(
        purpose="planning",
        owner_id="PLAN5",
        workspace=settings.console.state_dir / "ephemeral" / "planning-PLAN5-crashed",
        team_id="team-crashed",
    )
    aion.stale_sessions = [session]

    original_recover = aion.recover_ephemeral_session

    def ordered_recovery(current):
        assert [event["kind"] for event in service.ledger.read_all()] == [
            "aion_ephemeral_recovery_started"
        ]
        return original_recover(current)

    monkeypatch.setattr(aion, "recover_ephemeral_session", ordered_recovery)
    assert service.acquire_instance_lease() is True
    try:
        result = service.recover_startup()
    finally:
        service.release_instance_lease()

    assert result["ephemeral_recovered"] == 1
    assert result["ephemeral_teams_deleted"] == 1
    assert aion.recovered_sessions == [session]
    events = service.ledger.read_all()
    assert [event["kind"] for event in events] == [
        "aion_ephemeral_recovery_started",
        "aion_ephemeral_recovery_finished",
    ]
    encoded = json.dumps(events)
    assert str(session.workspace) not in encoded
    assert events[1]["payload"]["team_deleted"] is True
    assert events[1]["payload"]["workspace_removed"] is True


def test_console_startup_recovery_failure_is_fixed_and_audited(monkeypatch, console_env):
    settings, service, aion, _ = console_env
    private_detail = f"private recovery path {settings.console.state_dir}"
    session = EphemeralSession(
        purpose="mail",
        owner_id="MAIL5",
        workspace=settings.console.state_dir / "ephemeral" / "mail-MAIL5-crashed",
    )
    aion.stale_sessions = [session]

    def recovery_failed(_session):
        raise AionUiError(private_detail)

    monkeypatch.setattr(aion, "recover_ephemeral_session", recovery_failed)
    assert service.acquire_instance_lease() is True
    try:
        with pytest.raises(ConsoleUnavailable, match=EPHEMERAL_RECOVERY_UNAVAILABLE):
            service.recover_startup()
    finally:
        service.release_instance_lease()

    events = service.ledger.read_all()
    assert [event["kind"] for event in events] == [
        "aion_ephemeral_recovery_started",
        "aion_ephemeral_recovery_failed",
    ]
    assert private_detail not in json.dumps(events)
    assert events[1]["payload"]["reason"] == "identity_or_cleanup_unconfirmed"


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


def test_pre_organization_plan_files_keep_their_original_confirmation_hash(console_env):
    _, service, _, _ = console_env
    requested = service.request_plan(PlanRequest(objective="兼容旧方案哈希"))
    ready = service.draft_plan(requested.plan_id)
    plan_path = service.store.plans_dir / f"{ready.plan_id}.json"
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    for agent in payload["plan"]["agents"]:
        agent.pop("reports_to", None)
    payload["plan"].pop("collaboration_loops", None)
    plan_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    reloaded = service.get_plan(ready.plan_id, refresh=False)
    assert reloaded.plan_sha256 == ready.plan_sha256
    confirmed = service.confirm_plan(
        reloaded.plan_id,
        ConfirmRequest(plan_sha256=str(reloaded.plan_sha256), confirmed=True),
    )
    assert confirmed.status == "confirmed"


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


def test_mail_authorization_requires_evidence_uses_fixed_consent_and_enables_only_after_verify(
    monkeypatch, console_env
):
    _, service, _, _ = console_env
    saved: list[tuple[bool, bool]] = []
    monkeypatch.setattr(
        "quarterdeck.console.service.authorize_mail",
        lambda settings: {
            "ok": True,
            "authenticated": True,
            "scope_read_only": True,
            "credential_storage": "encrypted",
        },
    )
    monkeypatch.setattr(
        "quarterdeck.console.service.save_mail_activation",
        lambda *, enabled, model_metadata_consent: saved.append(
            (enabled, model_metadata_consent)
        ),
    )

    requested = service.request_mail_authorization(
        MailAuthorizationRequest(
            gmail_readonly_acknowledged=True,
            model_metadata_acknowledged=True,
        )
    )
    assert requested.status == "running"
    ready = service.run_mail_authorization(requested.job_id)

    assert ready.status == "ready"
    assert saved == [(True, True)]
    assert service.settings.mail.enabled is True
    assert service.settings.mail.model_metadata_consent is True
    events = service.ledger.read_all()
    assert [event["kind"] for event in events] == [
        "mail_authorization_requested",
        "mail_authorization_finished",
    ]
    assert events[0]["payload"]["oauth_scope"] == "gmail.readonly"
    assert events[0]["payload"]["metadata_fields"] == [
        "from",
        "subject",
        "date",
        "message_id",
    ]


def test_mail_authorization_failure_is_fixed_and_never_activates(monkeypatch, console_env):
    _, service, _, _ = console_env
    hostile = "private@example.com /private/oauth-token"
    monkeypatch.setattr(
        "quarterdeck.console.service.authorize_mail",
        lambda settings: {"ok": False, "error": hostile},
    )
    monkeypatch.setattr(
        "quarterdeck.console.service.save_mail_activation",
        lambda **kwargs: pytest.fail("failed OAuth must not activate mail"),
    )
    requested = service.request_mail_authorization(
        MailAuthorizationRequest(
            gmail_readonly_acknowledged=True,
            model_metadata_acknowledged=True,
        )
    )
    failed = service.run_mail_authorization(requested.job_id)

    assert failed.status == "failed"
    assert failed.error == MAIL_AUTHORIZATION_FAILURE
    encoded = json.dumps(service.ledger.read_all(), ensure_ascii=False)
    assert hostile not in encoded
    assert '"reason": "oauth_or_activation_failed"' in encoded
    assert service.settings.mail.enabled is False


def test_mail_oauth_client_import_is_audited_without_secret_material(
    monkeypatch, console_env
):
    _, service, _, _ = console_env
    private_json = '{"installed":{"client_secret":"private-oauth-value"}}'
    captured: list[str] = []
    monkeypatch.setattr(
        "quarterdeck.console.service.save_oauth_client",
        lambda raw: captured.append(raw),
    )

    result = service.configure_mail_oauth_client(
        MailOAuthClientRequest(
            client_json=private_json,
            private_storage_acknowledged=True,
        )
    )

    assert result == {"configured": True}
    assert captured == [private_json]
    encoded = json.dumps(service.ledger.read_all(), ensure_ascii=False)
    assert "private-oauth-value" not in encoded
    assert [event["kind"] for event in service.ledger.read_all()] == [
        "mail_oauth_client_import_requested",
        "mail_oauth_client_import_finished",
    ]


def test_mail_oauth_client_import_returns_fixed_rejection(monkeypatch, console_env):
    _, service, _, _ = console_env
    hostile = "private-client-secret /private/path"
    monkeypatch.setattr(
        "quarterdeck.console.service.save_oauth_client",
        lambda raw: (_ for _ in ()).throw(ValueError(f"rejected {raw}")),
    )

    with pytest.raises(ConsoleConflict, match=f"^{MAIL_OAUTH_CLIENT_REJECTED}$"):
        service.configure_mail_oauth_client(
            MailOAuthClientRequest(
                client_json=hostile,
                private_storage_acknowledged=True,
            )
        )

    encoded = json.dumps(service.ledger.read_all(), ensure_ascii=False)
    assert hostile not in encoded
    assert '"reason": "client_rejected"' in encoded


def test_mail_disable_revokes_future_model_access_even_when_audit_write_fails(
    monkeypatch, console_env
):
    _, service, _, _ = console_env
    service.settings = service.settings.model_copy(
        update={
            "mail": service.settings.mail.model_copy(
                update={"enabled": True, "model_metadata_consent": True}
            )
        }
    )
    saved: list[tuple[bool, bool]] = []
    monkeypatch.setattr(
        "quarterdeck.console.service.save_mail_activation",
        lambda *, enabled, model_metadata_consent: saved.append(
            (enabled, model_metadata_consent)
        ),
    )
    monkeypatch.setattr(service.ledger, "append", lambda *args, **kwargs: None)

    assert service.disable_mail() == {"disabled": True}
    assert saved == [(False, False)]
    assert service.settings.mail.enabled is False
    assert service.settings.mail.model_metadata_consent is False


def test_telegram_console_configuration_never_persists_or_returns_credentials(
    monkeypatch, console_env
):
    _, service, _, _ = console_env
    saved = []
    monkeypatch.setattr(
        "quarterdeck.console.service.save_telegram_credentials",
        lambda token, chat_id, *, replace: saved.append((token, chat_id, replace)),
    )
    request = TelegramConfigureRequest(
        bot_token="1:private-token",
        chat_id="123456",
        storage_acknowledged=True,
        replace_existing=False,
    )

    assert service.configure_telegram(request) == {"configured": True}
    assert saved == [("1:private-token", "123456", False)]
    assert service.telegram_setup_status() == {
        "configured": True,
        "environment_controlled": False,
    }
    encoded = json.dumps(service.ledger.read_all(), ensure_ascii=False)
    assert "private-token" not in encoded
    assert "123456" not in encoded
    assert [event["kind"] for event in service.ledger.read_all()] == [
        "telegram_configuration_requested",
        "telegram_configuration_finished",
    ]


def test_telegram_console_rejects_bad_credentials_with_fixed_error(monkeypatch, console_env):
    _, service, _, _ = console_env
    hostile = "1:private-token 123456 /private/secret"

    def reject(*args, **kwargs):
        del args, kwargs
        raise ValueError(hostile)

    monkeypatch.setattr(
        "quarterdeck.console.service.save_telegram_credentials",
        reject,
    )
    request = TelegramConfigureRequest(
        bot_token="1:private-token",
        chat_id="123456",
        storage_acknowledged=True,
    )
    with pytest.raises(ConsoleConflict, match=TELEGRAM_CONFIGURATION_REJECTED):
        service.configure_telegram(request)
    encoded = json.dumps(service.ledger.read_all(), ensure_ascii=False)
    assert hostile not in encoded
    assert "private-token" not in encoded
    assert "123456" not in encoded
    assert '"reason": "credentials_rejected"' in encoded


def test_telegram_console_test_is_evidence_first_and_uses_fixed_message(
    monkeypatch, console_env
):
    _, service, _, _ = console_env
    service.settings = service.settings.model_copy(
        update={
            "telegram": service.settings.telegram.model_copy(
                update={"bot_token": "1:private-token", "chat_id": "123456"}
            )
        }
    )
    sent = []
    monkeypatch.setattr(
        "quarterdeck.console.service.send_telegram",
        lambda text, settings: sent.append((text, settings.telegram.chat_id)) or True,
    )

    assert service.test_telegram() == {"sent": True}
    assert sent == [("Quarterdeck Telegram delivery test", "123456")]
    encoded = json.dumps(service.ledger.read_all(), ensure_ascii=False)
    assert "private-token" not in encoded
    assert "123456" not in encoded
    assert [event["kind"] for event in service.ledger.read_all()] == [
        "telegram_test_requested",
        "telegram_test_finished",
    ]

    monkeypatch.setattr("quarterdeck.console.service.send_telegram", lambda *args: False)
    with pytest.raises(ConsoleUnavailable, match=TELEGRAM_TEST_FAILED):
        service.test_telegram()
    assert service.ledger.read_all()[-1]["kind"] == "telegram_test_failed"


def test_telegram_console_does_not_send_without_requested_evidence(monkeypatch, console_env):
    _, service, _, _ = console_env
    monkeypatch.setattr(service.ledger, "append", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "quarterdeck.console.service.send_telegram",
        lambda *args: pytest.fail("Telegram must not send without durable requested evidence"),
    )
    with pytest.raises(ConsoleUnavailable, match="telegram_test_requested"):
        service.test_telegram()


def test_telegram_console_disable_and_environment_override_fail_closed(
    monkeypatch, console_env
):
    _, service, _, _ = console_env
    service.settings = service.settings.model_copy(
        update={
            "telegram": service.settings.telegram.model_copy(
                update={"bot_token": "1:private-token", "chat_id": "123456"}
            )
        }
    )
    cleared = []
    monkeypatch.setattr(
        "quarterdeck.console.service.clear_telegram_credentials",
        lambda: cleared.append(True) or True,
    )
    assert service.disable_telegram() == {"disabled": True}
    assert cleared == [True]
    assert service.telegram_setup_status()["configured"] is False

    monkeypatch.setenv("QD_TELEGRAM__BOT_TOKEN", "environment-secret")
    with pytest.raises(ConsoleConflict, match=TELEGRAM_ENVIRONMENT_CONTROLLED):
        service.disable_telegram()


def test_telegram_console_serializes_configuration_mutations(monkeypatch, console_env):
    _, service, _, _ = console_env
    guard = threading.Lock()
    active = 0
    maximum = 0

    def save(*args, **kwargs):
        nonlocal active, maximum
        del args, kwargs
        with guard:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.03)
        with guard:
            active -= 1

    monkeypatch.setattr(
        "quarterdeck.console.service.save_telegram_credentials",
        save,
    )
    first = TelegramConfigureRequest(
        bot_token="1:first-token",
        chat_id="123456",
        storage_acknowledged=True,
    )
    second = TelegramConfigureRequest(
        bot_token="2:second-token",
        chat_id="654321",
        storage_acknowledged=True,
        replace_existing=True,
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(service.configure_telegram, [first, second]))

    assert results == [{"configured": True}, {"configured": True}]
    assert maximum == 1


def test_aionui_mail_summary_fails_when_ephemeral_team_cleanup_is_unconfirmed(
    monkeypatch, console_env
):
    settings, _, _, _ = console_env
    client = AionUiClient(settings.console)
    team = {
        "id": "team-private",
        "assistants": [{"role": "lead", "conversation_id": "conversation-private"}],
    }
    remote = {}

    def create_team(**kwargs):
        remote[team["id"]] = {
            "id": team["id"],
            "name": kwargs["name"],
            "workspace": str(kwargs["workspace"]),
        }
        return team

    monkeypatch.setattr(client, "create_team", create_team)
    monkeypatch.setattr(client, "list_teams", lambda: list(remote.values()))
    monkeypatch.setattr(client, "ensure_team", lambda team_id: None)
    monkeypatch.setattr(client, "set_team_mode", lambda team_id, mode: None)
    monkeypatch.setattr(client, "_run_and_wait", lambda *args, **kwargs: "摘要")

    def cleanup_failed(team_id):
        raise AionUiError("private subject leaked by upstream")

    monkeypatch.setattr(client, "delete_team", cleanup_failed)
    with pytest.raises(AionUiError, match="mail session cleanup could not be confirmed") as exc:
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


def test_aionui_dispatch_receives_the_hash_bound_reporting_hierarchy(
    monkeypatch, console_env, tmp_path
):
    settings, _, _, _ = console_env
    client = AionUiClient(settings.console)
    raw = _fortune_plan().model_dump(mode="json")
    raw["agents"][1]["reports_to"] = "解读 Agent"
    raw["agents"][2]["reports_to"] = "引用核验 Agent"
    raw["collaboration_loops"] = [
        {
            "source_agent": "引用核验 Agent",
            "target_agent": "报告编辑 Agent",
            "condition": "引用未通过时返回编辑；通过即停止",
            "max_iterations": 2,
        }
    ]
    plan = TaskPlan.model_validate(raw)
    captured: dict[str, object] = {}
    team = {
        "id": "team-org",
        "assistants": [
            {"conversation_id": f"conversation-{index}"}
            for index, _ in enumerate(plan.agents, start=1)
        ],
    }

    def create_team(**kwargs):
        captured["agents"] = kwargs["agents"]
        return team

    def send_team_message(team_id, prompt):
        assert team_id == "team-org"
        captured["prompt"] = prompt
        return {"run": {"team_run_id": "run-org"}, "enqueue_status": "queued"}

    monkeypatch.setattr(client, "create_team", create_team)
    monkeypatch.setattr(client, "ensure_team", lambda team_id: None)
    monkeypatch.setattr(client, "set_team_mode", lambda team_id, mode: None)
    monkeypatch.setattr(client, "send_team_message", send_team_message)
    result = client.dispatch_plan(
        plan_id="PLAN-ORG",
        plan=plan,
        objective="生成命理演示报告",
        constraints="仅使用合成数据",
        workspace=tmp_path,
        paperclip_issue_id="issue-org",
    )

    prompt_payload = json.loads(str(captured["prompt"]).split("\n", 1)[1])
    assert prompt_payload["organization"] == {
        "解读 Agent": None,
        "引用核验 Agent": "解读 Agent",
        "报告编辑 Agent": "引用核验 Agent",
    }
    assert prompt_payload["plan"]["collaboration_loops"] == [
        {
            "source_agent": "引用核验 Agent",
            "target_agent": "报告编辑 Agent",
            "condition": "引用未通过时返回编辑；通过即停止",
            "max_iterations": 2,
        }
    ]
    prompt_text = str(captured["prompt"]).split("\n", 1)[0]
    assert "never exceed max_iterations" in prompt_text
    assert "does not expose a verifiable hard runtime cutoff" in prompt_text
    assert [row["role"] for row in captured["agents"]] == ["lead", "teammate", "teammate"]
    assert result["team_id"] == "team-org"
    assert result["team_run_id"] == "run-org"


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
    monkeypatch.setattr(client, "ensure_team", lambda team_id: None)
    monkeypatch.setattr(client, "set_team_mode", lambda team_id, mode: None)
    monkeypatch.setattr(
        client,
        "_run_and_wait",
        lambda *args, **kwargs: _plan().model_dump_json(),
    )
    remote = {}

    def create_team(**kwargs):
        remote[team["id"]] = {
            "id": team["id"],
            "name": kwargs["name"],
            "workspace": str(kwargs["workspace"]),
        }
        return team

    monkeypatch.setattr(client, "create_team", create_team)
    monkeypatch.setattr(client, "list_teams", lambda: list(remote.values()))

    def planning_cleanup_failed(team_id):
        del team_id
        raise AionUiError("delete failed")

    monkeypatch.setattr(client, "delete_team", planning_cleanup_failed)
    with pytest.raises(AionUiError, match="planning session cleanup could not be confirmed"):
        client.generate_plan("PLAN1", PlanRequest(objective="生成摘要"), [])


def test_aionui_ephemeral_workspaces_are_unique_private_and_removed(monkeypatch, console_env):
    settings, _, _, _ = console_env
    client = AionUiClient(settings.console)
    workspaces = []
    deleted = []
    remote = {}
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

    def create_team(**kwargs):
        workspace = Path(kwargs["workspace"])
        assert workspace.exists()
        assert workspace.stat().st_mode & 0o777 == 0o700
        (workspace / "private-residue.txt").write_text("private", encoding="utf-8")
        workspaces.append(workspace)
        index = len(workspaces)
        team = {
            "id": f"team-{index}",
            "assistants": [{"role": "lead", "conversation_id": f"conversation-{index}"}],
        }
        remote[team["id"]] = {
            "id": team["id"],
            "name": kwargs["name"],
            "workspace": str(workspace),
        }
        marker = workspace / ".quarterdeck-session.json"
        assert marker.stat().st_mode & 0o777 == 0o600
        marker_payload = json.loads(marker.read_text())
        assert marker_payload == {
            "owner_id": "PLAN1" if index == 1 else "MAIL1",
            "purpose": "planning" if index == 1 else "mail",
            "schema_version": 1,
            "team_id": None,
            "workspace": str(workspace),
        }
        return team

    def ensure_team(team_id):
        workspace = workspaces[int(team_id.rsplit("-", 1)[1]) - 1]
        assert (
            json.loads((workspace / ".quarterdeck-session.json").read_text())["team_id"] == team_id
        )

    def delete_team(team_id):
        deleted.append(team_id)
        remote.pop(team_id)

    monkeypatch.setattr(client, "create_team", create_team)
    monkeypatch.setattr(client, "list_teams", lambda: list(remote.values()))
    monkeypatch.setattr(client, "ensure_team", ensure_team)
    monkeypatch.setattr(client, "set_team_mode", lambda team_id, mode: None)
    monkeypatch.setattr(
        client,
        "_run_and_wait",
        lambda team, *args, **kwargs: (
            _plan().model_dump_json() if team["id"] == "team-1" else "摘要"
        ),
    )
    monkeypatch.setattr(client, "delete_team", delete_team)

    def progress_unavailable(phase, percent):
        del phase, percent
        raise OSError("progress store unavailable")

    client.generate_plan(
        "PLAN1",
        PlanRequest(objective="生成摘要"),
        [],
        progress_unavailable,
    )
    assert client.summarize_mail("MAIL1", []) == "摘要"

    assert len(workspaces) == 2
    assert workspaces[0] != workspaces[1]
    assert workspaces[0].name.startswith("planning-PLAN1-")
    assert workspaces[1].name.startswith("mail-MAIL1-")
    assert all(not workspace.exists() for workspace in workspaces)
    assert deleted == ["team-1", "team-2"]
    assert (settings.console.state_dir / "ephemeral").stat().st_mode & 0o777 == 0o700


def test_aionui_team_creation_failure_removes_its_private_workspace(monkeypatch, console_env):
    settings, _, _, _ = console_env
    client = AionUiClient(settings.console)
    workspaces = []
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

    def creation_failed(**kwargs):
        workspace = Path(kwargs["workspace"])
        (workspace / "private-residue.txt").write_text("private", encoding="utf-8")
        workspaces.append(workspace)
        raise AionUiError("team creation failed")

    monkeypatch.setattr(client, "create_team", creation_failed)
    monkeypatch.setattr(client, "list_teams", lambda: [])
    with pytest.raises(AionUiError, match="team creation failed"):
        client.generate_plan("PLAN2", PlanRequest(objective="生成摘要"), [])
    assert len(workspaces) == 1
    assert not workspaces[0].exists()


def test_aionui_workspace_cleanup_failure_rejects_result_after_team_delete(
    monkeypatch, console_env
):
    settings, _, _, _ = console_env
    client = AionUiClient(settings.console)
    team = {
        "id": "team-mail",
        "assistants": [{"role": "lead", "conversation_id": "conversation-mail"}],
    }
    deleted = []
    remote = {}

    def create_team(**kwargs):
        remote[team["id"]] = {
            "id": team["id"],
            "name": kwargs["name"],
            "workspace": str(kwargs["workspace"]),
        }
        return team

    def delete_team(team_id):
        deleted.append(team_id)
        remote.pop(team_id)

    monkeypatch.setattr(client, "create_team", create_team)
    monkeypatch.setattr(client, "list_teams", lambda: list(remote.values()))
    monkeypatch.setattr(client, "ensure_team", lambda team_id: None)
    monkeypatch.setattr(client, "set_team_mode", lambda team_id, mode: None)
    monkeypatch.setattr(client, "_run_and_wait", lambda *args, **kwargs: "摘要")
    monkeypatch.setattr(client, "delete_team", delete_team)

    def cleanup_failed(path):
        del path
        raise OSError("private workspace path")

    monkeypatch.setattr("quarterdeck.console.aionui.shutil.rmtree", cleanup_failed)
    with pytest.raises(AionUiError, match="mail session cleanup could not be confirmed") as exc:
        client.summarize_mail("MAIL2", [])
    assert "private workspace path" not in str(exc.value)
    assert deleted == ["team-mail"]


def test_aionui_recovers_crashed_team_by_exact_private_workspace(monkeypatch, console_env):
    settings, _, _, _ = console_env
    client = AionUiClient(settings.console)
    session = client._ephemeral_workspace("planning", "PLAN3")
    remote = {
        "team-crashed": {
            "id": "team-crashed",
            "name": session.team_name,
            "workspace": str(session.workspace),
        }
    }
    deleted = []
    monkeypatch.setattr(client, "list_teams", lambda: list(remote.values()))

    def delete_team(team_id):
        deleted.append(team_id)
        remote.pop(team_id)

    monkeypatch.setattr(client, "delete_team", delete_team)
    assert client.stale_ephemeral_sessions() == [session]
    result = client.recover_ephemeral_session(session)

    assert result == {"team_deleted": True, "workspace_removed": True}
    assert deleted == ["team-crashed"]
    assert not session.workspace.exists()


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        (
            [
                {
                    "id": "team-wrong-name",
                    "name": "User team",
                    "workspace": "WORKSPACE",
                }
            ],
            "identity did not match",
        ),
        (
            [
                {"id": "team-1", "name": "TEAM_NAME", "workspace": "WORKSPACE"},
                {"id": "team-2", "name": "TEAM_NAME", "workspace": "WORKSPACE"},
            ],
            "multiple candidate teams",
        ),
    ],
)
def test_aionui_ephemeral_recovery_rejects_ambiguous_identity(
    monkeypatch, console_env, rows, message
):
    settings, _, _, _ = console_env
    client = AionUiClient(settings.console)
    session = client._ephemeral_workspace("mail", "MAIL3")
    rendered = [
        {
            **row,
            "name": session.team_name if row["name"] == "TEAM_NAME" else row["name"],
            "workspace": str(session.workspace),
        }
        for row in rows
    ]
    deleted = []
    monkeypatch.setattr(client, "list_teams", lambda: rendered)
    monkeypatch.setattr(client, "delete_team", lambda team_id: deleted.append(team_id))

    with pytest.raises(AionUiError, match=message):
        client.recover_ephemeral_session(session)
    assert deleted == []
    assert session.workspace.exists()


def test_aionui_ephemeral_recovery_rejects_insecure_marker(console_env):
    settings, _, _, _ = console_env
    client = AionUiClient(settings.console)
    session = client._ephemeral_workspace("planning", "PLAN4")
    marker = session.workspace / ".quarterdeck-session.json"
    marker.chmod(0o644)

    with pytest.raises(ValueError, match="marker permissions are insecure"):
        client.stale_ephemeral_sessions()


def test_aionui_ephemeral_recovery_rejects_workspace_outside_private_root(tmp_path, console_env):
    settings, _, _, _ = console_env
    client = AionUiClient(settings.console)
    workspace = tmp_path / "outside"
    workspace.mkdir(mode=0o700)
    session = EphemeralSession(purpose="mail", owner_id="MAIL4", workspace=workspace)
    client._write_ephemeral_session(session)

    with pytest.raises(ValueError, match="not a private directory"):
        client.recover_ephemeral_session(session)


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


def test_console_dashboard_folds_task_runs_from_ledger_and_keeps_deleted_history(console_env):
    _, service, _, _ = console_env
    requested = service.request_plan(PlanRequest(objective="生成可追溯运行历史"))
    ready = service.draft_plan(requested.plan_id)
    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
    )
    service.dispatch_plan(ready.plan_id)
    finished = service.refresh_execution(ready.plan_id)
    assert finished.status == "completed_unverified"

    result = service.dashboard()
    assert len(result["task_runs"]) == 1
    history = result["task_runs"][0]
    assert history["run_id"] == ready.plan_id
    assert history["title"] == "每日研究摘要"
    assert history["status"] == "completed_unverified"
    assert history["agent_count"] == 2
    assert history["outcome_verified"] is False
    assert history["evidence_gap"] is False
    assert history["deleted"] is False
    assert history["duration_s"] >= 0
    assert [event["kind"] for event in history["events"]] == [
        "task_plan_confirmed",
        "task_execution_requested",
        "task_execution_dispatched",
        "task_execution_finished",
    ]

    service.delete_plan(ready.plan_id, DeletePlanRequest(confirmed=True))
    after_delete = service.dashboard()
    assert after_delete["plans"] == []
    assert after_delete["task_runs"][0]["run_id"] == ready.plan_id
    assert after_delete["task_runs"][0]["deleted"] is True


def test_console_dashboard_keeps_each_confirmed_run_in_commit_order(console_env):
    _, service, _, _ = console_env
    confirmed_ids = []
    for objective in ["第一次受管执行", "第二次受管执行"]:
        requested = service.request_plan(PlanRequest(objective=objective))
        ready = service.draft_plan(requested.plan_id)
        service.confirm_plan(
            ready.plan_id,
            ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
        )
        confirmed_ids.append(ready.plan_id)

    history = service.dashboard()["task_runs"]
    assert [row["run_id"] for row in history] == list(reversed(confirmed_ids))
    assert all(row["status"] == "confirmed" for row in history)
    assert all([event["kind"] for event in row["events"]] == ["task_plan_confirmed"] for row in history)


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


def test_console_exposes_user_facing_provider_readiness_without_internal_ids(console_env):
    _, service, _, _ = console_env
    providers = service.provider_statuses()
    assert providers["openai"]["runtime_ready"] is True
    assert providers["openai"]["status"] == "online"
    assert providers["openai"]["detail"] == "已通过 ChatGPT 登录，可用于任务"
    assert providers["anthropic"]["status"] == "setup"
    encoded = json.dumps(providers, ensure_ascii=False)
    assert "bare:" not in encoded
    assert "AionUi" not in encoded


def test_console_does_not_mislabel_claude_account_auth_as_console_billing(console_env):
    _, service, _, _ = console_env

    def account_probe(provider):
        return {
            "provider": provider,
            "label": "ChatGPT / OpenAI" if provider == "openai" else "Claude",
            "installed": True,
            "authenticated": provider == "anthropic",
            "auth_mode": "account" if provider == "anthropic" else "none",
            "status": "online" if provider == "anthropic" else "setup",
            "detail": "账号已登录" if provider == "anthropic" else "待登录",
        }

    service._provider_probe = account_probe
    providers = service.provider_statuses()
    assert providers["anthropic"]["runtime_ready"] is True
    assert providers["anthropic"]["detail"] == "Claude 账号已登录，可用于本机任务"
    assert "Console" not in str(providers["anthropic"]["detail"])


def test_provider_connection_is_vendor_owned_and_audited_without_credentials(console_env):
    _, service, _, _ = console_env
    requested = service.request_provider_connection("openai")
    assert requested.status == "running"
    ready = service.run_provider_connection(requested.job_id)
    assert ready.status == "ready"
    events = service.ledger.read_all()
    assert [event["kind"] for event in events] == [
        "provider_connection_requested",
        "provider_connection_finished",
    ]
    encoded = json.dumps(events, ensure_ascii=False)
    assert "token" not in encoded.casefold()
    assert "password" not in encoded.casefold()


def test_local_console_can_resolve_pending_approval_with_append_only_evidence(console_env):
    _, service, _, paperclip = console_env
    approval_id = "11111111-1111-4111-8111-111111111111"
    paperclip.approvals.append(
        {
            "id": approval_id,
            "status": "pending",
            "createdAt": "2026-07-14T12:00:00+00:00",
            "payload": {
                "title": "Approve Claude tool: Bash",
                "summary": "Quarterdeck deferred a tool call.",
                "recommendedAction": "Inspect and decide.",
                "risks": ["May modify files"],
            },
        }
    )
    service.ledger.append(
        "tool_gate_requested",
        "session-1",
        {
            "schema_version": 1,
            "request_id": "request-1",
            "request_hash": "a" * 64,
            "session_id": "session-1",
            "tool_use_id": "tool-1",
            "tool_name": "Bash",
            "tool_input": {"command": "echo safe"},
            "cwd": "/tmp/demo",
            "expires_at": "2026-07-14T13:00:00+00:00",
        },
        fsync=True,
    )
    service.ledger.append(
        "tool_gate_linked",
        "session-1",
        {
            "schema_version": 1,
            "request_id": "request-1",
            "request_hash": "a" * 64,
            "session_id": "session-1",
            "tool_use_id": "tool-1",
            "approval_id": approval_id,
            "resume_args": [],
        },
        fsync=True,
    )
    cards = service.list_pending_approvals()
    assert cards[0]["tool_name"] == "Bash"
    assert cards[0]["tool_input"] == '{"command":"echo safe"}'

    result = service.decide_approval(
        approval_id,
        ApprovalDecisionRequest(
            decision="approve",
            decision_note="I reviewed this exact request",
            confirmed=True,
        ),
    )
    assert result == {"approval_id": approval_id, "status": "approved", "reconciled": False}
    assert paperclip.approvals[0]["status"] == "approved"
    events = service.ledger.read_all()
    assert [event["kind"] for event in events[-2:]] == [
        "approval_decision_requested",
        "approval_decision_finished",
    ]
    encoded = json.dumps(events, ensure_ascii=False)
    assert "I reviewed this exact request" not in encoded

    reconciled = service.decide_approval(
        approval_id,
        ApprovalDecisionRequest(decision="approve", confirmed=True),
    )
    assert reconciled["reconciled"] is True


def test_provider_and_approval_http_facade_requires_local_csrf(
    console_env, monkeypatch
):
    settings, service, _, paperclip = console_env
    approval_id = "22222222-2222-4222-8222-222222222222"
    paperclip.approvals.append(
        {
            "id": approval_id,
            "status": "pending",
            "payload": {"title": "Approve a governed operation"},
        }
    )
    monkeypatch.setattr(service, "acquire_instance_lease", lambda: True)
    monkeypatch.setattr(service, "recover_startup", lambda: {})
    monkeypatch.setattr(service, "release_instance_lease", lambda: None)
    app = create_app(settings, service=service)
    csrf = app.state.csrf_token
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        denied = client.post("/api/v1/providers/openai/connect", json={})
        assert denied.status_code == 403
        connected = client.post(
            "/api/v1/providers/openai/connect",
            json={},
            headers={"X-QD-CSRF": csrf},
        )
        assert connected.status_code == 202
        job_id = connected.json()["job_id"]
        assert client.get(f"/api/v1/provider-connections/{job_id}").status_code == 200
        approvals = client.get("/api/v1/approvals")
        assert approvals.status_code == 200
        assert approvals.json()[0]["approval_id"] == approval_id
        decided = client.post(
            f"/api/v1/approvals/{approval_id}/decision",
            json={"decision": "reject", "decision_note": "not intended", "confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        assert decided.status_code == 200
        assert decided.json()["status"] == "rejected"


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
        "recover_startup",
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
            "task_runs": [],
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


def test_mail_authorization_http_requires_both_explicit_acknowledgements(
    console_env, monkeypatch
):
    settings, service, _, _ = console_env
    monkeypatch.setattr(
        service,
        "mail_setup_status",
        lambda: {
            "enabled": False,
            "available": True,
            "authenticated": False,
            "oauth_client_ready": False,
            "oauth_client_issue": "missing",
            "model_metadata_consent": False,
            "ready": False,
            "oauth_scope": "gmail.readonly",
            "metadata_fields": ["from", "subject", "date", "message_id"],
            "privacy": "metadata_only",
        },
    )
    monkeypatch.setattr(
        service,
        "configure_mail_oauth_client",
        lambda request: {"configured": True},
    )
    with TestClient(
        create_app(settings, service=service),
        base_url="http://127.0.0.1:8765",
    ) as client:
        csrf = client.get("/api/v1/bootstrap").json()["csrf_token"]
        headers = {"X-QD-CSRF": csrf, "Origin": "http://127.0.0.1:8765"}
        status_response = client.get("/api/v1/mail-authorization/status")
        assert status_response.status_code == 200
        assert status_response.json()["metadata_fields"] == [
            "from",
            "subject",
            "date",
            "message_id",
        ]
        assert status_response.json()["oauth_client_issue"] == "missing"

        private_client = '{"installed":{"client_secret":"private-http-value"}}'
        client_denied = client.post(
            "/api/v1/mail-authorization/client",
            json={
                "client_json": private_client,
                "private_storage_acknowledged": False,
            },
            headers=headers,
        )
        assert client_denied.status_code == 422
        assert "private-http-value" not in client_denied.text
        client_accepted = client.post(
            "/api/v1/mail-authorization/client",
            json={
                "client_json": private_client,
                "private_storage_acknowledged": True,
            },
            headers=headers,
        )
        assert client_accepted.json() == {"configured": True}
        assert "private-http-value" not in client_accepted.text

        denied = client.post(
            "/api/v1/mail-authorization",
            json={
                "gmail_readonly_acknowledged": True,
                "model_metadata_acknowledged": False,
            },
            headers=headers,
        )
        assert denied.status_code == 422

        accepted = client.post(
            "/api/v1/mail-authorization",
            json={
                "gmail_readonly_acknowledged": True,
                "model_metadata_acknowledged": True,
            },
            headers=headers,
        )
        assert accepted.status_code == 202
        job = accepted.json()
        assert job["status"] == "running"
        fetched = client.get(f"/api/v1/mail-authorization/{job['job_id']}")
        assert fetched.json() == job

        without_csrf = client.post(
            "/api/v1/mail-authorization/disable",
            json={"confirmed": True},
        )
        assert without_csrf.status_code == 403


def test_telegram_http_redacts_credentials_and_requires_explicit_actions(
    console_env, monkeypatch
):
    settings, service, _, _ = console_env
    monkeypatch.setattr(
        "quarterdeck.console.service.save_telegram_credentials",
        lambda *args, **kwargs: None,
    )
    with TestClient(
        create_app(settings, service=service),
        base_url="http://127.0.0.1:8765",
    ) as client:
        csrf = client.get("/api/v1/bootstrap").json()["csrf_token"]
        headers = {"X-QD-CSRF": csrf, "Origin": "http://127.0.0.1:8765"}
        payload = {
            "bot_token": "1:private-token",
            "chat_id": "123456",
            "storage_acknowledged": False,
            "replace_existing": False,
        }
        denied = client.post(
            "/api/v1/telegram/configure",
            json=payload,
            headers=headers,
        )
        assert denied.status_code == 422
        assert "private-token" not in denied.text
        assert "123456" not in denied.text

        payload["storage_acknowledged"] = True
        accepted = client.post(
            "/api/v1/telegram/configure",
            json=payload,
            headers=headers,
        )
        assert accepted.status_code == 200
        assert accepted.json() == {"configured": True}
        assert "private-token" not in accepted.text
        assert "123456" not in accepted.text

        denied_test = client.post(
            "/api/v1/telegram/test",
            json={"confirmed": False},
            headers=headers,
        )
        assert denied_test.status_code == 422


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

    monkeypatch.setattr(service, "recover_startup", recovery_failed)
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
