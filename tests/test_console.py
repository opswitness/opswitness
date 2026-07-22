import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from opswitness import mcp_server
from opswitness.config import Settings
from opswitness.console.aionui import (
    AionUiClient,
    AionUiError,
    EphemeralSession,
    _planning_prompt,
    _validate_plan_brief,
    _validate_revision_changed,
)
from opswitness.console.app import create_app
from opswitness.console.schemas import (
    ApprovalDecisionRequest,
    ApprovalMode,
    ConfirmRequest,
    ContinueRunRequest,
    DeletePlanRequest,
    ExecutionApprovalModeRequest,
    ExecutionProfile,
    ExecutionProfileRevisionRequest,
    ExecutionProgress,
    ExecutionControlRequest,
    ExecutionState,
    ForkPlanRequest,
    MailAuthorizationRequest,
    MailOAuthClientRequest,
    OrganizationRevisionRequest,
    PlanRecord,
    PlanRequest,
    ProcessMemoryProposalRequest,
    ProviderConnectionRequest,
    RerunPlanRequest,
    RevisePlanRequest,
    RuntimeRevisionRequest,
    RuntimeInputAnswerRequest,
    TaskPlan,
    TaskTemplateArchiveRequest,
    TaskTemplateFromPlanRequest,
    TaskTemplateSaveRequest,
    TelegramConfigureRequest,
    TeamBlueprintArchiveRequest,
    TeamBlueprintSaveRequest,
    WorkspaceMemoryCandidateRequest,
    WorkspaceMemoryDecisionRequest,
    WorkspaceMemoryRollbackRequest,
)
from opswitness.console.service import (
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
    RuntimeArtifactNotFound,
    _fleet_health,
    _hashable_plan_payload,
    _mail_setup_detail,
    _paperclip_launchd_label,
    _profiled_plan,
)
from opswitness.console.store import PlanNotFound
from opswitness.ledger import Ledger
from opswitness.paperclip import PaperclipError


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
        self.runtime_capabilities: list[dict] = []
        self.blueprint: dict | None = None
        self.memory_snapshot: list[dict] = []
        self.stale_sessions: list[EphemeralSession] = []
        self.recovered_sessions: list[EphemeralSession] = []
        self.local_providers = {"ollama"}
        self.local_provider_models: dict[str, list[str]] = {}
        self.snapshot: dict = {"status": "completed_unverified"}
        self.confirmations_by_conversation: dict[str, list[dict[str, str]]] = {}
        self.resolved_confirmations: list[tuple[str, str, str]] = []
        self.team_messages: list[tuple[str, str]] = []
        self.pause_calls: list[tuple[str, str]] = []
        self.cancel_calls: list[tuple[str, str]] = []
        self.resume_calls: list[tuple[str, str, str, str]] = []
        self.snapshot_requests: list[dict] = []
        self.control_state: dict = {
            "status": "running",
            "active_run_id": "team-run-1",
            "active_slot_ids": ["slot-1"],
            "slot_states": [{"slot_id": "slot-1", "state": "running"}],
        }
        self.pause_result: dict = {
            "status": "paused",
            "active_run_id": "team-run-1",
            "requested_slot_ids": ["slot-1"],
        }
        self.cancel_result: dict = {
            "status": "inactive",
            "active_run_id": None,
        }

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
            {
                "id": "bare:632f31d2",
                "enabled": True,
                "team_selectable": True,
            },
        ]

    def list_managed_agents(self):
        return [
            {
                "id": "2d23ff1c",
                "available_models": {
                    "available_models": [
                        {"id": "default", "label": "Default"},
                        {"id": "claude-fable-5[1m]", "label": "Fable 5"},
                        {"id": "sonnet", "label": "Sonnet"},
                    ]
                },
                "config_options": {
                    "config_options": [
                        {
                            "category": "model",
                            "options": [
                                {
                                    "name": "Fable 5",
                                    "value": "claude-fable-5[1m]",
                                    "description": "Exact Fable 5 model",
                                },
                                {
                                    "name": "Sonnet",
                                    "value": "sonnet",
                                    "description": "Rolling Sonnet alias",
                                },
                            ],
                        }
                    ]
                },
            }
        ]

    def local_provider_registered(self, provider):
        return provider in self.local_providers

    def ensure_local_provider(self, provider, models):
        self.local_providers.add(provider)
        self.local_provider_models[provider] = list(models)
        return f"opswitness-{provider}"

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
        runtime_capabilities=None,
        blueprint=None,
        memory_snapshot=None,
    ):
        del plan_id, request, catalog, assistant_id
        self.generated += 1
        self.previous_plan = previous_plan
        self.revision_instruction = revision_instruction
        self.runtime_capabilities = list(runtime_capabilities or [])
        self.blueprint = blueprint
        self.memory_snapshot = list(memory_snapshot or [])
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
            "agent_sessions": [
                {"agent_name": agent.name, "conversation_id": f"conversation-{index}"}
                for index, agent in enumerate(kwargs["plan"].agents, start=1)
            ],
        }

    def execution_snapshot(
        self,
        team_id,
        conversation_ids,
        *,
        agent_sessions=None,
        planned_stages=None,
        existing_stage_progress=None,
        observed_after=None,
    ):
        assert team_id == "team-1"
        assert agent_sessions is not None
        assert planned_stages is not None
        assert existing_stage_progress is not None
        self.snapshot_requests.append(
            {
                "planned_stages": planned_stages,
                "existing_stage_progress": existing_stage_progress,
                "observed_after": observed_after,
            }
        )
        if observed_after is not None:
            assert isinstance(observed_after, str)
            assert conversation_ids == [session["conversation_id"] for session in agent_sessions]
            assert planned_stages
        else:
            assert conversation_ids == ["conversation-1"]
        return dict(self.snapshot)

    def run_control_state(self, team_id, expected_run_id):
        assert team_id == "team-1"
        if expected_run_id is not None:
            assert expected_run_id.startswith("team-run-")
        return dict(self.control_state)

    def pause_team_run(self, team_id, run_id):
        self.pause_calls.append((team_id, run_id))
        return dict(self.pause_result)

    def cancel_team_run(self, team_id, run_id):
        self.cancel_calls.append((team_id, run_id))
        return dict(self.cancel_result)

    def resume_team_run(self, team_id, *, marker, plan_id, plan_sha256):
        self.resume_calls.append((team_id, marker, plan_id, plan_sha256))
        return {"team_run_id": "team-run-resumed", "enqueue_status": "queued"}

    def list_confirmations(self, conversation_id):
        return [dict(row) for row in self.confirmations_by_conversation.get(conversation_id, [])]

    def resolve_confirmation(self, conversation_id, call_id, decision):
        rows = self.confirmations_by_conversation.get(conversation_id, [])
        matches = [row for row in rows if row["call_id"] == call_id]
        if len(matches) != 1:
            raise AionUiError("confirmation missing")
        self.resolved_confirmations.append((conversation_id, call_id, decision))
        self.confirmations_by_conversation[conversation_id] = [
            row for row in rows if row["call_id"] != call_id
        ]
        return {
            "conversation_id": conversation_id,
            "call_id": call_id,
            "decision": decision,
        }

    def conversation_contains_marker(self, conversation_id, marker):
        assert conversation_id.startswith("conversation-")
        return any(marker in content for _, content in self.team_messages)

    def send_team_message(self, team_id, content):
        assert team_id == "team-1"
        self.team_messages.append((team_id, content))
        return {"run": {"team_run_id": "team-run-resumed"}, "enqueue_status": "queued"}

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
        if status is None:
            return list(self.approvals)
        return [row for row in self.approvals if row.get("status") == status]

    def create_board_approval(self, payload):
        row = {
            "id": f"00000000-0000-4000-8000-{len(self.approvals) + 1:012d}",
            "status": "pending",
            "payload": payload,
            "createdAt": "2026-07-15T17:00:00+00:00",
        }
        self.approvals.append(row)
        return row

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
    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(config))
    monkeypatch.setenv("OPSWITNESS_LEDGER_DIR", str(tmp_path / "ledger"))
    monkeypatch.setenv("OPSWITNESS_CONSOLE__STATE_DIR", str(tmp_path / "console"))
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
            "label": {
                "openai": "ChatGPT / OpenAI",
                "anthropic": "Claude",
                "deepseek": "DeepSeek",
                "xai": "Grok / xAI",
                "ollama": "Ollama",
                "lmstudio": "LM Studio",
            }[provider],
            "installed": provider != "xai",
            "authenticated": provider in {"openai", "anthropic", "ollama"},
            "auth_mode": (
                "chatgpt"
                if provider == "openai"
                else "account"
                if provider == "anthropic"
                else "local"
                if provider == "ollama"
                else "none"
            ),
            "status": ("online" if provider in {"openai", "anthropic", "ollama"} else "setup"),
            "detail": (
                "本地服务已启动，发现 1 个模型"
                if provider == "ollama"
                else "账号已登录"
                if provider in {"openai", "anthropic"}
                else "待连接"
            ),
            "server_online": provider == "ollama",
            "model_count": 1 if provider == "ollama" else 0,
            "models": ["test-local-model"] if provider == "ollama" else [],
        },
        provider_login=lambda provider: provider == "openai",
        background=False,
    )
    yield settings, service, aion, paperclip
    service.close()


def _running_aion_plan(service: ConsoleService) -> PlanRecord:
    requested = service.request_plan(PlanRequest(objective="生成受管研究摘要"))
    ready = service.draft_plan(requested.plan_id)
    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
    )
    return service.dispatch_plan(ready.plan_id)


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
    assert '"model":"exact advertised model id or default"' in prompt
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
        revision_instruction="调整协作循环：引用核验未通过时，返回给解读 Agent 重新处理，最多两轮。",
    )
    assert "versioned revision" in prompt
    assert "previous_plan" in prompt
    assert "调整协作循环" in prompt
    assert "最多两轮" in prompt
    with pytest.raises(ValueError, match="must differ"):
        _validate_revision_changed(previous.model_copy(deep=True), previous)


def test_execution_profile_keeps_legacy_plan_hash_payload_unchanged():
    legacy = _plan()
    legacy_payload = _hashable_plan_payload(legacy)
    assert legacy.execution_profile is None
    assert "execution_profile" not in legacy_payload

    profiled = legacy.model_copy(update={"execution_profile": ExecutionProfile.CUSTOM})
    profiled_payload = _hashable_plan_payload(profiled)
    assert profiled_payload["execution_profile"] == "custom"
    assert profiled_payload != legacy_payload


def test_plan_revision_is_append_only_hash_bound_and_blocks_the_parent(console_env):
    _, service, aion, paperclip = console_env
    requested = service.request_plan(PlanRequest(objective="生成研究摘要"))
    parent = service.draft_plan(requested.plan_id)
    assert parent.plan is not None
    assert parent.plan.execution_profile == ExecutionProfile.BALANCED
    instruction = (
        "调整协作循环：引用核验未通过时，返回给解读 Agent 重新处理，"
        "最多两轮；其余安排保持不变。SECRET-REVISION-ONLY"
    )

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
    assert aion.dispatched == 0
    assert paperclip.created == 0

    duplicate = service.request_plan_revision(
        parent.plan_id,
        RevisePlanRequest(instruction="另一个并发修改要求"),
    )
    assert duplicate.plan_id == revision.plan_id

    ready = service.draft_plan(revision.plan_id)
    assert ready.status == "ready"
    assert ready.plan is not None
    assert ready.plan.title == "每周研究摘要"
    assert ready.plan.execution_profile == ExecutionProfile.BALANCED
    assert ready.plan_sha256 != parent.plan_sha256
    assert aion.previous_plan == parent.plan
    assert aion.revision_instruction == instruction
    assert aion.dispatched == 0
    assert paperclip.created == 0

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


def test_ended_work_can_create_an_unconfirmed_ai_revision_without_dispatch(console_env):
    _, service, aion, paperclip = console_env
    requested = service.request_plan(PlanRequest(objective="生成一份可重复经营报告"))
    ready = service.draft_plan(requested.plan_id)
    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
    )
    service.dispatch_plan(ready.plan_id)
    finished = service.refresh_execution(ready.plan_id)
    assert finished.status == "completed_unverified"
    dispatched_before = aion.dispatched
    paperclip_before = paperclip.created

    revision = service.request_plan_revision(
        finished.plan_id,
        RevisePlanRequest(
            instruction="增加一名核验 Agent，并让它向负责人汇报；其他约束保持不变。"
        ),
    )

    assert revision.status == "planning"
    assert revision.parent_plan_id == finished.plan_id
    assert revision.parent_plan_sha256 == finished.plan_sha256
    assert revision.revision_number == finished.revision_number + 1
    assert revision.execution is None
    assert aion.dispatched == dispatched_before
    assert paperclip.created == paperclip_before
    assert service.ledger.read_all()[-1]["kind"] == "task_plan_revision_requested"


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


def test_ended_work_prepares_an_idempotent_reviewed_rerun_without_dispatch(console_env):
    _, service, aion, paperclip = console_env
    service.runtime_capabilities = lambda: [  # type: ignore[method-assign]
        {
            "runtime": "claude_code",
            "available": True,
            "models": [{"id": "default"}, {"id": "sonnet"}],
        },
        {
            "runtime": "codex_cli",
            "available": True,
            "models": [{"id": "default"}, {"id": "gpt-5.4-mini"}],
        },
        {
            "runtime": "aion_cli",
            "available": False,
            "models": [{"id": "default"}],
        },
    ]
    requested = service.request_plan(PlanRequest(objective="每天生成研究摘要"))
    ready = service.draft_plan(requested.plan_id)
    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(
            plan_sha256=str(ready.plan_sha256),
            approval_mode=ApprovalMode.MANUAL_ALL,
            confirmed=True,
        ),
    )
    service.dispatch_plan(ready.plan_id)
    finished = service.refresh_execution(ready.plan_id)
    assert finished.status == "completed_unverified"
    dispatched_before = aion.dispatched
    paperclip_before = paperclip.created

    rerun = service.prepare_plan_rerun(
        finished.plan_id,
        RerunPlanRequest(confirmed=True),
    )
    repeated = service.prepare_plan_rerun(
        finished.plan_id,
        RerunPlanRequest(confirmed=True),
    )

    assert rerun.status == "ready"
    assert rerun.plan_id == repeated.plan_id
    assert rerun.parent_plan_id == finished.plan_id
    assert rerun.parent_plan_sha256 == finished.plan_sha256
    assert rerun.revision_number == finished.revision_number + 1
    assert rerun.plan is not None
    assert finished.plan is not None
    assert rerun.plan.execution_profile == ExecutionProfile.FAST
    assert rerun.plan.title == finished.plan.title
    assert rerun.plan.summary == finished.plan.summary
    assert rerun.plan.agents != finished.plan.agents
    assert [agent.name for agent in rerun.plan.agents] == [
        agent.name for agent in finished.plan.agents
    ]
    assert [agent.model for agent in rerun.plan.agents] == ["sonnet", "gpt-5.4-mini"]
    assert rerun.plan.stages == finished.plan.stages
    assert rerun.plan_sha256 != finished.plan_sha256
    assert rerun.approval_mode == ApprovalMode.AUTOMATIC
    assert rerun.execution is None
    assert aion.dispatched == dispatched_before
    assert paperclip.created == paperclip_before

    event = service.ledger.read_all()[-1]
    assert event["kind"] == "task_plan_rerun_prepared"
    assert event["run_id"] == rerun.plan_id
    assert event["payload"]["parent_plan_id"] == finished.plan_id
    assert event["payload"]["plan_sha256"] == rerun.plan_sha256
    assert event["payload"]["approval_mode"] == "automatic"
    assert event["payload"]["execution_profile"] == "fast"
    assert "每天生成研究摘要" not in json.dumps(event, ensure_ascii=False)


def test_execution_profile_uses_only_the_advertised_default_model():
    capabilities = [
        {
            "runtime": runtime,
            "available": True,
            "models": [{"id": "default"}],
        }
        for runtime in ("claude_code", "codex_cli")
    ]

    profiled = _profiled_plan(_plan(), ExecutionProfile.FAST, capabilities)

    assert [agent.model for agent in profiled.agents] == ["default", "default"]
    assert profiled.execution_profile == ExecutionProfile.FAST


def test_rerun_http_facade_requires_csrf_and_explicit_confirmation(console_env, monkeypatch):
    settings, service, _, _ = console_env
    requested = service.request_plan(PlanRequest(objective="重新运行 HTTP 验收"))
    ready = service.draft_plan(requested.plan_id)
    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
    )
    service.dispatch_plan(ready.plan_id)
    finished = service.refresh_execution(ready.plan_id)
    monkeypatch.setattr(service, "acquire_instance_lease", lambda: True)
    monkeypatch.setattr(service, "recover_startup", lambda: {})
    monkeypatch.setattr(service, "release_instance_lease", lambda: None)
    app = create_app(settings, service=service)
    csrf = app.state.csrf_token

    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        denied = client.post(
            f"/api/v1/plans/{finished.plan_id}/rerun",
            json={"confirmed": True},
        )
        assert denied.status_code == 403
        unconfirmed = client.post(
            f"/api/v1/plans/{finished.plan_id}/rerun",
            json={"confirmed": False},
            headers={"X-QD-CSRF": csrf},
        )
        assert unconfirmed.status_code == 422
        accepted = client.post(
            f"/api/v1/plans/{finished.plan_id}/rerun",
            json={"confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        assert accepted.status_code == 201
        payload = accepted.json()
        assert payload["status"] == "ready"
        assert payload["parent_plan_id"] == finished.plan_id
        assert payload["plan"]["execution_profile"] == "fast"


def test_ended_aion_run_continues_same_context_as_new_audited_version(console_env):
    _, service, aion, paperclip = console_env
    running = _running_aion_plan(service)
    finished = service.refresh_execution(running.plan_id)
    assert finished.status == "completed_unverified"
    assert finished.execution is not None
    dispatched_before = aion.dispatched
    issues_before = paperclip.created
    message = "继续检查上一轮引用，并生成一份不包含真人信息的修订摘要。"

    continued = service.continue_plan_run(
        finished.plan_id,
        ContinueRunRequest(message=message, confirmed=True),
    )
    repeated = service.continue_plan_run(
        finished.plan_id,
        ContinueRunRequest(message=message, confirmed=True),
    )

    assert continued.plan_id == repeated.plan_id
    assert continued.status == "running"
    assert continued.parent_plan_id == finished.plan_id
    assert continued.continued_from_plan_id == finished.plan_id
    assert continued.continued_from_plan_sha256 == finished.plan_sha256
    assert continued.continuation_message_sha256 == hashlib.sha256(message.encode()).hexdigest()
    assert continued.revision_number == finished.revision_number + 1
    assert continued.plan == finished.plan
    assert continued.plan_sha256 != finished.plan_sha256
    assert continued.execution is not None
    assert continued.execution.aion_team_id == finished.execution.aion_team_id
    assert continued.execution.aion_agent_sessions == finished.execution.aion_agent_sessions
    assert continued.execution.aion_team_run_id == "team-run-resumed"
    assert aion.dispatched == dispatched_before
    assert paperclip.created == issues_before + 1
    assert len(aion.team_messages) == 1
    assert message in aion.team_messages[0][1]
    assert f"[qd-followup:{continued.plan_id}]" in aion.team_messages[0][1]
    assert "Create exactly one new built-in AionUi team task" in aion.team_messages[0][1]

    ledger_json = json.dumps(service.ledger.read_all(), ensure_ascii=False)
    assert message not in ledger_json
    assert ledger_json.count("task_plan_continuation_requested") == 1
    assert ledger_json.count("task_plan_continuation_delivered") == 1
    assert ledger_json.count("task_execution_dispatched") == 2
    history = {row["plan_id"]: row for row in service.dashboard()["task_runs"]}
    assert history[finished.plan_id]["continuation_available"] is True
    assert history[continued.plan_id]["continued_from_plan_id"] == finished.plan_id
    assert history[continued.plan_id]["parent_plan_id"] == finished.plan_id
    assert any(
        event["kind"] == "task_plan_continuation_delivered"
        for event in history[continued.plan_id]["events"]
    )

    with pytest.raises(ConsoleConflict, match="current work version must end"):
        service.continue_plan_run(
            finished.plan_id,
            ContinueRunRequest(message="另一条新追问", confirmed=True),
        )


def test_continuation_captures_only_this_run_artifact_delta(console_env):
    settings, service, aion, _ = console_env
    running = _running_aion_plan(service)
    source_artifacts = (
        settings.console.state_dir / "executions" / running.plan_id / "artifacts"
    )
    source_artifacts.mkdir(parents=True, mode=0o700)
    (source_artifacts / "prior.json").write_text('{"run": "prior"}')
    finished = service.refresh_execution(running.plan_id)

    continued = service.continue_plan_run(
        finished.plan_id,
        ContinueRunRequest(message="生成本轮独立报告。", confirmed=True),
    )
    report = b"follow-up report"
    (source_artifacts / "follow-up.pdf").write_bytes(report)
    completed = service.refresh_execution(continued.plan_id)

    assert completed.status == "completed_unverified"
    rows = service.list_plan_artifacts(continued.plan_id)
    assert [row["name"] for row in rows] == ["follow-up.pdf"]
    assert rows[0]["sha256"] == hashlib.sha256(report).hexdigest()
    assert rows[0]["evidence_status"] == "registered"
    assert rows[0]["cas_uri"] == f"cas+sha256://{rows[0]['sha256']}"
    assert aion.snapshot_requests[-1]["observed_after"] is not None
    assert continued.plan is not None
    assert [row["order"] for row in aion.snapshot_requests[-1]["planned_stages"]] == [
        stage.order for stage in continued.plan.stages
    ]
    registered = [
        event
        for event in service.ledger.read_all()
        if event["kind"] == "artifact_registered" and event["run_id"] == continued.plan_id
    ]
    assert [event["payload"]["logical_name"] for event in registered] == [
        "follow-up.pdf"
    ]


def test_registered_pdf_content_is_cas_verified_and_workspace_files_are_denied(
    monkeypatch, console_env
):
    settings, service, _, _ = console_env
    running = _running_aion_plan(service)
    artifact_dir = settings.console.state_dir / "executions" / running.plan_id / "artifacts"
    artifact_dir.mkdir(parents=True, mode=0o700)
    report = b"%PDF-1.7\nsynthetic OpsWitness report\n%%EOF\n"
    (artifact_dir / "report.pdf").write_bytes(report)
    finished = service.refresh_execution(running.plan_id)
    assert finished.status == "completed_unverified"

    artifact = service.get_plan_artifact_content(running.plan_id, "report.pdf")
    assert artifact == {
        "content": report,
        "mime": "application/pdf",
        "disposition": "inline",
        "name": "report.pdf",
        "sha256": hashlib.sha256(report).hexdigest(),
    }

    (artifact_dir / "late.pdf").write_bytes(b"not registered")
    with pytest.raises(RuntimeArtifactNotFound, match="registered artifact not found"):
        service.get_plan_artifact_content(running.plan_id, "late.pdf")

    monkeypatch.setattr(service, "acquire_instance_lease", lambda: True)
    monkeypatch.setattr(service, "recover_startup", lambda: {})
    monkeypatch.setattr(service, "release_instance_lease", lambda: None)
    app = create_app(settings, service=service)
    endpoint = f"/api/v1/plans/{running.plan_id}/artifacts"
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        opened = client.get(f"{endpoint}/report.pdf/content")
        assert opened.status_code == 200
        assert opened.content == report
        assert opened.headers["content-type"] == "application/pdf"
        assert opened.headers["content-disposition"] == 'inline; filename="report.pdf"'
        assert opened.headers["cache-control"] == "no-store"
        assert opened.headers["x-content-type-options"] == "nosniff"
        assert (
            opened.headers["x-opswitness-artifact-sha256"]
            == hashlib.sha256(report).hexdigest()
        )
        denied = client.get(f"{endpoint}/late.pdf/content")
        assert denied.status_code == 404
        traversal = client.get(f"{endpoint}/..%2Foutside.pdf/content")
        assert traversal.status_code == 404


def test_older_history_run_can_continue_after_latest_version_has_ended(console_env):
    _, service, aion, _ = console_env
    original = service.refresh_execution(_running_aion_plan(service).plan_id)
    first = service.continue_plan_run(
        original.plan_id,
        ContinueRunRequest(message="先核验引用来源。", confirmed=True),
    )
    first_finished = service.refresh_execution(first.plan_id)

    second = service.continue_plan_run(
        original.plan_id,
        ContinueRunRequest(message="改从原始运行继续，比较另一种解释。", confirmed=True),
    )

    assert first_finished.status == "completed_unverified"
    assert second.parent_plan_id == first_finished.plan_id
    assert second.parent_plan_sha256 == first_finished.plan_sha256
    assert second.continued_from_plan_id == original.plan_id
    assert second.continued_from_plan_sha256 == original.plan_sha256
    assert second.revision_number == first_finished.revision_number + 1
    assert second.execution is not None
    assert second.execution.aion_team_id == original.execution.aion_team_id
    assert len(aion.team_messages) == 2

    history = {row["plan_id"]: row for row in service.dashboard()["task_runs"]}
    assert history[second.plan_id]["parent_plan_id"] == first_finished.plan_id
    assert history[second.plan_id]["continued_from_plan_id"] == original.plan_id


def test_continuation_reconciles_lost_ack_without_duplicate_send(monkeypatch, console_env):
    _, service, aion, _ = console_env
    finished = service.refresh_execution(_running_aion_plan(service).plan_id)
    calls = 0

    def accepted_then_lost(team_id, content):
        nonlocal calls
        calls += 1
        aion.team_messages.append((team_id, content))
        raise AionUiError("ack lost")

    monkeypatch.setattr(aion, "send_team_message", accepted_then_lost)
    continued = service.continue_plan_run(
        finished.plan_id,
        ContinueRunRequest(message="在相同上下文中继续核验。", confirmed=True),
    )

    assert continued.status == "running"
    assert calls == 1
    delivered = next(
        event
        for event in service.ledger.read_all()
        if event["kind"] == "task_plan_continuation_delivered"
    )
    assert delivered["payload"]["reconciled_after_retry"] is True


def test_continuation_failure_is_terminal_and_never_falls_back(monkeypatch, console_env):
    _, service, aion, _ = console_env
    finished = service.refresh_execution(_running_aion_plan(service).plan_id)

    def unavailable(*args, **kwargs):
        del args, kwargs
        raise AionUiError("offline")

    monkeypatch.setattr(aion, "send_team_message", unavailable)
    with pytest.raises(ConsoleUnavailable, match="could not be continued"):
        service.continue_plan_run(
            finished.plan_id,
            ContinueRunRequest(message="继续运行", confirmed=True),
        )

    child = next(
        row for row in service.store.list_all() if row.continued_from_plan_id == finished.plan_id
    )
    assert child.status == "failed"
    assert child.execution is not None
    assert child.execution.aion_team_id == finished.execution.aion_team_id
    assert aion.dispatched == 1
    assert any(
        event["kind"] == "task_execution_failed" and event["run_id"] == child.plan_id
        for event in service.ledger.read_all()
    )


def test_continue_http_requires_csrf_and_explicit_confirmation(console_env, monkeypatch):
    settings, service, _, _ = console_env
    finished = service.refresh_execution(_running_aion_plan(service).plan_id)
    monkeypatch.setattr(service, "acquire_instance_lease", lambda: True)
    monkeypatch.setattr(service, "recover_startup", lambda: {})
    monkeypatch.setattr(service, "release_instance_lease", lambda: None)
    app = create_app(settings, service=service)
    csrf = app.state.csrf_token
    endpoint = f"/api/v1/plans/{finished.plan_id}/continue"

    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        denied = client.post(
            endpoint,
            json={"message": "继续上一轮", "confirmed": True},
        )
        assert denied.status_code == 403
        unconfirmed = client.post(
            endpoint,
            json={"message": "继续上一轮", "confirmed": False},
            headers={"X-QD-CSRF": csrf},
        )
        assert unconfirmed.status_code == 422
        accepted = client.post(
            endpoint,
            json={"message": "继续上一轮", "confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        assert accepted.status_code == 202
        payload = accepted.json()
        assert payload["status"] == "running"
        assert payload["continued_from_plan_id"] == finished.plan_id


def test_reviewed_work_fork_is_independent_and_copies_no_runtime_state(console_env):
    _, service, aion, paperclip = console_env
    requested = service.request_plan(PlanRequest(objective="创建一份可分叉的研究计划"))
    ready = service.draft_plan(requested.plan_id)
    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(
            plan_sha256=str(ready.plan_sha256),
            approval_mode=ApprovalMode.MANUAL_ALL,
            confirmed=True,
        ),
    )
    running = service.dispatch_plan(ready.plan_id)
    dispatched_before = aion.dispatched
    paperclip_before = paperclip.created

    forked = service.fork_plan(running.plan_id, ForkPlanRequest(confirmed=True))

    assert forked.status == "ready"
    assert forked.plan_id != running.plan_id
    assert forked.parent_plan_id is None
    assert forked.parent_plan_sha256 is None
    assert forked.forked_from_plan_id == running.plan_id
    assert forked.forked_from_plan_sha256 == running.plan_sha256
    assert forked.revision_number == 1
    assert forked.plan == running.plan
    assert forked.plan is not running.plan
    assert forked.plan_sha256 != running.plan_sha256
    assert forked.approval_mode == ApprovalMode.AUTOMATIC
    assert forked.confirmed_at is None
    assert forked.execution is None
    assert aion.dispatched == dispatched_before
    assert paperclip.created == paperclip_before

    event = service.ledger.read_all()[-1]
    assert event["kind"] == "task_plan_forked"
    assert event["run_id"] == forked.plan_id
    assert event["payload"]["source_plan_id"] == running.plan_id
    assert event["payload"]["source_plan_sha256"] == running.plan_sha256
    assert event["payload"]["plan_sha256"] == forked.plan_sha256
    assert "创建一份可分叉的研究计划" not in json.dumps(event, ensure_ascii=False)


def test_fork_http_facade_requires_csrf_and_explicit_confirmation(console_env, monkeypatch):
    settings, service, _, _ = console_env
    requested = service.request_plan(PlanRequest(objective="分叉 HTTP 验收"))
    ready = service.draft_plan(requested.plan_id)
    monkeypatch.setattr(service, "acquire_instance_lease", lambda: True)
    monkeypatch.setattr(service, "recover_startup", lambda: {})
    monkeypatch.setattr(service, "release_instance_lease", lambda: None)
    app = create_app(settings, service=service)
    csrf = app.state.csrf_token

    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        denied = client.post(
            f"/api/v1/plans/{ready.plan_id}/fork",
            json={"confirmed": True},
        )
        assert denied.status_code == 403
        unconfirmed = client.post(
            f"/api/v1/plans/{ready.plan_id}/fork",
            json={"confirmed": False},
            headers={"X-QD-CSRF": csrf},
        )
        assert unconfirmed.status_code == 422
        accepted = client.post(
            f"/api/v1/plans/{ready.plan_id}/fork",
            json={"confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        assert accepted.status_code == 201
        payload = accepted.json()
        assert payload["status"] == "ready"
        assert payload["parent_plan_id"] is None
        assert payload["forked_from_plan_id"] == ready.plan_id
        assert payload["forked_from_plan_sha256"] == ready.plan_sha256


def test_running_aion_task_can_pause_and_continue_with_audited_state(console_env):
    _, service, aion, _ = console_env
    running = _running_aion_plan(service)

    paused = service.control_execution(
        running.plan_id,
        ExecutionControlRequest(action="pause", confirmed=True),
    )
    assert paused.status == "paused"
    assert paused.execution is not None
    assert paused.execution.status == "paused"
    assert aion.pause_calls == [("team-1", "team-run-1")]

    resumed = service.control_execution(
        running.plan_id,
        ExecutionControlRequest(action="resume", confirmed=True),
    )
    assert resumed.status == "running"
    assert resumed.execution is not None
    assert resumed.execution.aion_team_run_id == "team-run-resumed"
    assert len(aion.resume_calls) == 1
    _, marker, resumed_plan_id, resumed_sha = aion.resume_calls[0]
    assert marker.startswith("[qd-resume:")
    assert resumed_plan_id == running.plan_id
    assert resumed_sha == running.plan_sha256

    kinds = [event["kind"] for event in service.ledger.read_all()]
    assert kinds[-4:] == [
        "task_execution_pause_requested",
        "task_execution_paused",
        "task_execution_resume_requested",
        "task_execution_resumed",
    ]
    assert "Continue only the same previously confirmed" not in json.dumps(
        service.ledger.read_all(), ensure_ascii=False
    )


def test_termination_stays_requested_until_runtime_confirms_stop(console_env):
    _, service, aion, _ = console_env
    running = _running_aion_plan(service)
    aion.cancel_result = {
        "status": "running",
        "active_run_id": "team-run-1",
    }

    requested = service.control_execution(
        running.plan_id,
        ExecutionControlRequest(action="terminate", confirmed=True),
    )
    assert requested.status == "cancel_requested"
    assert requested.execution is not None
    assert requested.execution.finished_at is None
    assert aion.cancel_calls == [("team-1", "team-run-1")]

    aion.snapshot = {"status": "completed_unverified"}
    cancelled = service.refresh_execution(running.plan_id)
    assert cancelled.status == "cancelled"
    assert cancelled.execution is not None
    assert cancelled.execution.finished_at is not None
    assert cancelled.execution.outcome_verified is False

    repeated = service.control_execution(
        running.plan_id,
        ExecutionControlRequest(action="terminate", confirmed=True),
    )
    assert repeated.status == "cancelled"
    assert aion.cancel_calls == [("team-1", "team-run-1")]
    kinds = [event["kind"] for event in service.ledger.read_all()]
    assert kinds[-3:] == [
        "task_execution_cancel_requested",
        "task_execution_cancelled",
        "task_execution_finished",
    ]


def test_unconfirmed_pause_remains_pending_and_records_degraded_evidence(
    console_env,
    monkeypatch,
):
    _, service, aion, _ = console_env
    running = _running_aion_plan(service)

    def unavailable(*args, **kwargs):
        del args, kwargs
        raise AionUiError("private runtime detail")

    monkeypatch.setattr(aion, "pause_team_run", unavailable)
    pending = service.control_execution(
        running.plan_id,
        ExecutionControlRequest(action="pause", confirmed=True),
    )
    assert pending.status == "pause_requested"
    assert pending.execution is not None
    assert pending.execution.control_error is not None
    encoded = json.dumps(service.ledger.read_all(), ensure_ascii=False)
    assert "task_execution_control_failed" in encoded
    assert "private runtime detail" not in encoded


def test_workflow_control_is_rejected_without_claiming_support(console_env):
    _, service, _, _ = console_env
    record = PlanRecord(
        plan_id="01K123456789ABCDEFGHJKMNPQ",
        status="running",
        objective="Run workflow",
        plan=_plan("workflow", "daily-market-report"),
        plan_sha256="a" * 64,
        execution=ExecutionState(
            kind="workflow",
            status="running",
            workflow_run_id="workflow-run-1",
        ),
    )
    service.store.create(record)
    with pytest.raises(ConsoleConflict, match="no controllable AionUi"):
        service.control_execution(
            record.plan_id,
            ExecutionControlRequest(action="terminate", confirmed=True),
        )


def test_control_http_requires_csrf_and_explicit_confirmation(console_env, monkeypatch):
    settings, service, _, _ = console_env
    running = _running_aion_plan(service)
    monkeypatch.setattr(service, "acquire_instance_lease", lambda: True)
    monkeypatch.setattr(service, "recover_startup", lambda: {})
    monkeypatch.setattr(service, "release_instance_lease", lambda: None)
    app = create_app(settings, service=service)
    csrf = app.state.csrf_token
    endpoint = f"/api/v1/plans/{running.plan_id}/control"
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        denied = client.post(endpoint, json={"action": "pause", "confirmed": True})
        assert denied.status_code == 403
        unconfirmed = client.post(
            endpoint,
            json={"action": "pause", "confirmed": False},
            headers={"X-QD-CSRF": csrf},
        )
        assert unconfirmed.status_code == 422
        accepted = client.post(
            endpoint,
            json={"action": "pause", "confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        assert accepted.status_code == 202
        assert accepted.json()["status"] == "paused"


def test_active_aion_execution_changes_future_approval_mode_with_audited_cas(
    console_env,
):
    _, service, _, _ = console_env
    running = _running_aion_plan(service)
    assert running.execution is not None
    assert running.execution.approval_mode == ApprovalMode.AUTOMATIC

    manual = service.change_execution_approval_mode(
        running.plan_id,
        ExecutionApprovalModeRequest(
            approval_mode=ApprovalMode.MANUAL_ALL,
            expected_current_mode=ApprovalMode.AUTOMATIC,
            confirmed=True,
        ),
    )
    assert manual.approval_mode == ApprovalMode.AUTOMATIC
    assert manual.plan_sha256 == running.plan_sha256
    assert manual.execution is not None
    assert manual.execution.approval_mode == ApprovalMode.MANUAL_ALL

    repeated = service.change_execution_approval_mode(
        running.plan_id,
        ExecutionApprovalModeRequest(
            approval_mode=ApprovalMode.MANUAL_ALL,
            expected_current_mode=ApprovalMode.AUTOMATIC,
            confirmed=True,
        ),
    )
    assert repeated.execution is not None
    assert repeated.execution.approval_mode == ApprovalMode.MANUAL_ALL
    with pytest.raises(ConsoleConflict, match="refresh before"):
        service.change_execution_approval_mode(
            running.plan_id,
            ExecutionApprovalModeRequest(
                approval_mode=ApprovalMode.AUTOMATIC,
                expected_current_mode=ApprovalMode.AUTOMATIC,
                confirmed=True,
            ),
        )

    events = service.ledger.read_all()
    assert [event["kind"] for event in events[-2:]] == [
        "task_approval_mode_change_requested",
        "task_approval_mode_changed",
    ]
    assert events[-1]["payload"] == {
        "schema_version": 1,
        "request_event_id": events[-2]["event_id"],
        "plan_sha256": running.plan_sha256,
        "from_mode": "automatic",
        "to_mode": "manual_all",
        "applies_to": "future_tool_calls",
        "existing_paused_call_preserved": False,
    }
    history = next(
        row for row in service.dashboard()["task_runs"] if row["plan_id"] == running.plan_id
    )
    assert [event["kind"] for event in history["events"]][-2:] == [
        "task_approval_mode_change_requested",
        "task_approval_mode_changed",
    ]


def test_enabling_auto_preserves_existing_manual_approval_and_applies_to_next_call(
    console_env,
):
    _, service, aion, paperclip = console_env
    running = _running_aion_plan(service)
    service.change_execution_approval_mode(
        running.plan_id,
        ExecutionApprovalModeRequest(
            approval_mode=ApprovalMode.MANUAL_ALL,
            expected_current_mode=ApprovalMode.AUTOMATIC,
            confirmed=True,
        ),
    )
    aion.snapshot = {"status": "awaiting_approval", "pending_approvals": 1}
    first = {
        "message_id": "message-before-auto",
        "call_id": "call-before-auto",
        "title": "First tool call",
        "description": "This call was observed while manual mode was active.",
        "command_type": "execute",
        "allow_value": "allow",
        "reject_value": "reject",
    }
    aion.confirmations_by_conversation["conversation-1"] = [first]
    waiting = service.refresh_execution(running.plan_id)
    assert waiting.status == "awaiting_approval"
    assert paperclip.approvals[0]["status"] == "pending"
    assert paperclip.approvals[0]["payload"]["qdApprovalModeAtRequest"] == "manual_all"
    assert paperclip.approvals[0]["payload"]["qdAutomaticReason"] == ""

    automatic = service.change_execution_approval_mode(
        running.plan_id,
        ExecutionApprovalModeRequest(
            approval_mode=ApprovalMode.AUTOMATIC,
            expected_current_mode=ApprovalMode.MANUAL_ALL,
            confirmed=True,
        ),
    )
    assert automatic.execution is not None
    assert automatic.execution.approval_mode == ApprovalMode.AUTOMATIC

    second = {
        "message_id": "message-after-auto",
        "call_id": "call-after-auto",
        "title": "Second tool call",
        "description": "This call was observed after Auto mode was enabled.",
        "command_type": "execute",
        "allow_value": "allow",
        "reject_value": "reject",
    }
    aion.confirmations_by_conversation["conversation-1"] = [first, second]
    service.refresh_execution(running.plan_id)

    assert paperclip.approvals[0]["status"] == "pending"
    assert paperclip.approvals[1]["status"] == "approved"
    assert paperclip.approvals[1]["payload"]["qdApprovalModeAtRequest"] == "automatic"
    assert aion.resolved_confirmations == [("conversation-1", "call-after-auto", "approve")]
    assert service.list_pending_approvals()[0]["approval_id"] == paperclip.approvals[0]["id"]


def test_incomplete_auto_enable_recovers_to_manual_mode(console_env):
    _, service, _, _ = console_env
    running = _running_aion_plan(service)
    service.change_execution_approval_mode(
        running.plan_id,
        ExecutionApprovalModeRequest(
            approval_mode=ApprovalMode.MANUAL_ALL,
            expected_current_mode=ApprovalMode.AUTOMATIC,
            confirmed=True,
        ),
    )
    request = service._append(
        "task_approval_mode_change_requested",
        running.plan_id,
        {
            "schema_version": 1,
            "plan_sha256": running.plan_sha256,
            "from_mode": "manual_all",
            "to_mode": "automatic",
            "execution_mode": "aion_team",
            "team_run_id": "team-run-1",
            "existing_paused_call_preserved": False,
        },
    )

    def interrupted(current):
        assert current.execution is not None
        current.execution.approval_mode = ApprovalMode.AUTOMATIC
        return current

    service.store.mutate(running.plan_id, interrupted)
    assert service._recover_incomplete_approval_mode_changes() == 1
    recovered = service.store.get(running.plan_id)
    assert recovered.execution is not None
    assert recovered.execution.approval_mode == ApprovalMode.MANUAL_ALL
    event = service.ledger.read_all()[-1]
    assert event["kind"] == "task_approval_mode_change_recovered"
    assert event["payload"]["request_event_id"] == request["event_id"]
    assert event["payload"]["effective_mode"] == "manual_all"


def test_approval_mode_http_requires_csrf_confirmation_and_current_mode(
    console_env,
    monkeypatch,
):
    settings, service, _, _ = console_env
    running = _running_aion_plan(service)
    monkeypatch.setattr(service, "acquire_instance_lease", lambda: True)
    monkeypatch.setattr(service, "recover_startup", lambda: {})
    monkeypatch.setattr(service, "release_instance_lease", lambda: None)
    app = create_app(settings, service=service)
    csrf = app.state.csrf_token
    endpoint = f"/api/v1/plans/{running.plan_id}/approval-mode"
    body = {
        "approval_mode": "manual_all",
        "expected_current_mode": "automatic",
        "confirmed": True,
    }
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        denied = client.post(endpoint, json=body)
        assert denied.status_code == 403
        unconfirmed = client.post(
            endpoint,
            json={**body, "confirmed": False},
            headers={"X-QD-CSRF": csrf},
        )
        assert unconfirmed.status_code == 422
        legacy_target = client.post(
            endpoint,
            json={**body, "approval_mode": "automatic_safe"},
            headers={"X-QD-CSRF": csrf},
        )
        assert legacy_target.status_code == 422
        accepted = client.post(endpoint, json=body, headers={"X-QD-CSRF": csrf})
        assert accepted.status_code == 200
        assert accepted.json()["execution"]["approval_mode"] == "manual_all"
        stale = client.post(
            endpoint,
            json={
                **body,
                "approval_mode": "automatic",
                "expected_current_mode": "automatic",
            },
            headers={"X-QD-CSRF": csrf},
        )
        assert stale.status_code == 409


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


def test_organization_revision_http_facade_requires_csrf_and_confirmation(console_env, monkeypatch):
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


def test_console_startup_recovery_records_ephemeral_cleanup_evidence(monkeypatch, console_env):
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


def test_aion_tool_confirmation_becomes_one_actionable_governance_approval(console_env):
    _, service, aion, paperclip = console_env
    aion.snapshot = {"status": "awaiting_approval", "pending_approvals": 1}
    aion.confirmations_by_conversation["conversation-1"] = [
        {
            "message_id": "message-1",
            "call_id": "tool-call-1",
            "title": "Check whether lunar-python is installed",
            "description": "A read-only dependency check needs confirmation.",
            "command_type": "execute",
            "allow_value": "allow",
            "reject_value": "reject",
        }
    ]
    requested = service.request_plan(PlanRequest(objective="生成受管演示报告"))
    ready = service.draft_plan(requested.plan_id)
    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(
            plan_sha256=str(ready.plan_sha256),
            approval_mode=ApprovalMode.MANUAL_ALL,
            confirmed=True,
        ),
    )
    service.dispatch_plan(ready.plan_id)

    waiting = service.refresh_execution(ready.plan_id)
    repeated = service.refresh_execution(ready.plan_id)

    assert waiting.status == repeated.status == "awaiting_approval"
    assert len(paperclip.approvals) == 1
    approval = paperclip.approvals[0]
    assert approval["payload"]["qdApprovalSource"] == "aionui_tool_confirmation"
    assert approval["payload"]["toolInput"] == "Check whether lunar-python is installed"
    cards = service.list_pending_approvals()
    assert cards == [
        {
            "approval_id": approval["id"],
            "plan_id": ready.plan_id,
            "status": "pending",
            "kind": "tool_call",
            "title": "Approve 总控: A read-only dependency check needs confirmation.",
            "summary": "The confirmed runtime paused this tool call before execution.",
            "recommended_action": ("Review the bounded request, then allow it once or reject it."),
            "tool_name": "execute",
            "tool_input": "Check whether lunar-python is installed",
            "risks": [
                "Approval is single-use and bound to this exact paused tool call.",
                "Reject the request if its purpose or scope is unclear.",
            ],
            "expires_at": None,
            "requested_at": "2026-07-15T17:00:00+00:00",
            "can_decide": True,
        }
    ]
    task_action = next(
        action
        for action in service.dashboard()["home"]["action_queue"]
        if action["action_id"] == f"approval-task:{ready.plan_id}"
    )
    assert task_action["target"] == "tasks"
    approval["payload"]["requestDescription"] = "{}"
    placeholder_card = service.list_pending_approvals()[0]
    assert placeholder_card["title"] == ("Approve 总控: Check whether lunar-python is installed")
    approval["payload"]["planId"] = "01AAAAAAAAAAAAAAAAAAAAAAAA"
    assert service.list_pending_approvals()[0]["plan_id"] is None
    approval["payload"]["planId"] = ready.plan_id
    kinds = [event["kind"] for event in service.ledger.read_all()]
    assert kinds.count("aion_tool_gate_requested") == 1
    assert kinds.count("aion_tool_gate_linked") == 1

    decided = service.decide_approval(
        approval["id"],
        ApprovalDecisionRequest(decision="approve", confirmed=True),
    )
    assert decided["status"] == "approved"
    assert aion.resolved_confirmations == [("conversation-1", "tool-call-1", "approve")]
    repeated = service.decide_approval(
        approval["id"],
        ApprovalDecisionRequest(decision="approve", confirmed=True),
    )
    assert repeated["reconciled"] is True
    assert aion.resolved_confirmations == [("conversation-1", "tool-call-1", "approve")]
    kinds = [event["kind"] for event in service.ledger.read_all()]
    assert kinds[-2:] == [
        "aion_tool_gate_delivery_requested",
        "aion_tool_gate_delivery_finished",
    ]


def test_default_automatic_mode_approves_generic_execution_tools(console_env):
    _, service, aion, paperclip = console_env
    aion.snapshot = {"status": "awaiting_approval", "pending_approvals": 1}
    aion.confirmations_by_conversation["conversation-1"] = [
        {
            "message_id": "message-auto",
            "call_id": "tool-call-auto",
            "title": "Run the confirmed task step",
            "description": "Execute the tool required by the confirmed plan.",
            "command_type": "execute",
            "allow_value": "allow",
            "reject_value": "reject",
        }
    ]
    ready = service.draft_plan(
        service.request_plan(PlanRequest(objective="测试默认自动模式")).plan_id
    )
    confirmed = service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
    )
    assert confirmed.approval_mode == ApprovalMode.AUTOMATIC
    service.dispatch_plan(ready.plan_id)

    service.refresh_execution(ready.plan_id)

    assert paperclip.approvals[0]["status"] == "approved"
    assert aion.resolved_confirmations == [("conversation-1", "tool-call-auto", "approve")]
    assert service.list_pending_approvals() == []
    events = service.ledger.read_all()
    automatic = next(event for event in events if event["kind"] == "aion_tool_gate_auto_approved")
    assert automatic["payload"] == {
        "schema_version": 1,
        "approval_id": paperclip.approvals[0]["id"],
        "policy_version": 2,
        "policy_reason": "confirmed-plan automatic mode",
        "approval_mode": "automatic",
    }
    requested = next(event for event in events if event["kind"] == "approval_decision_requested")
    assert requested["payload"]["source"] == "automatic_policy"
    assert "Run the confirmed task step" not in json.dumps(events, ensure_ascii=False)


def test_legacy_automatic_safe_mode_approves_exact_read_only_tools(console_env):
    _, service, aion, paperclip = console_env
    aion.snapshot = {"status": "awaiting_approval", "pending_approvals": 1}
    aion.confirmations_by_conversation["conversation-1"] = [
        {
            "message_id": "message-safe",
            "call_id": "tool-call-safe",
            "title": "Check package metadata",
            "description": "Read installed package metadata without importing it.",
            "command_type": "mcp__opswitness__qd_python_package_status",
            "allow_value": "allow",
            "reject_value": "reject",
        }
    ]
    ready = service.draft_plan(
        service.request_plan(PlanRequest(objective="测试安全自动审批")).plan_id
    )
    confirmed = service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(
            plan_sha256=str(ready.plan_sha256),
            approval_mode=ApprovalMode.AUTOMATIC_SAFE,
            confirmed=True,
        ),
    )
    assert confirmed.approval_mode == ApprovalMode.AUTOMATIC_SAFE
    service.dispatch_plan(ready.plan_id)

    service.refresh_execution(ready.plan_id)

    assert paperclip.approvals[0]["status"] == "approved"
    assert aion.resolved_confirmations == [("conversation-1", "tool-call-safe", "approve")]
    assert service.list_pending_approvals() == []
    events = service.ledger.read_all()
    automatic = next(event for event in events if event["kind"] == "aion_tool_gate_auto_approved")
    assert automatic["payload"] == {
        "schema_version": 1,
        "approval_id": paperclip.approvals[0]["id"],
        "policy_version": 2,
        "policy_reason": "exact read-only tool allowlist",
        "approval_mode": "automatic_safe",
    }
    requested = next(event for event in events if event["kind"] == "approval_decision_requested")
    assert requested["payload"]["source"] == "automatic_safe_policy"
    assert "Check package metadata" not in json.dumps(events, ensure_ascii=False)


def test_legacy_automatic_safe_mode_keeps_generic_execute_waiting(console_env):
    _, service, aion, paperclip = console_env
    aion.snapshot = {"status": "awaiting_approval", "pending_approvals": 1}
    aion.confirmations_by_conversation["conversation-1"] = [
        {
            "message_id": "message-legacy-safe",
            "call_id": "tool-call-legacy-safe",
            "title": "Run a command",
            "description": "Generic command execution is outside the legacy safe allowlist.",
            "command_type": "execute",
            "allow_value": "allow",
            "reject_value": "reject",
        }
    ]
    ready = service.draft_plan(
        service.request_plan(PlanRequest(objective="测试旧安全自动模式")).plan_id
    )
    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(
            plan_sha256=str(ready.plan_sha256),
            approval_mode=ApprovalMode.AUTOMATIC_SAFE,
            confirmed=True,
        ),
    )
    service.dispatch_plan(ready.plan_id)

    waiting = service.refresh_execution(ready.plan_id)

    assert waiting.status == "awaiting_approval"
    assert paperclip.approvals[0]["status"] == "pending"
    assert aion.resolved_confirmations == []


def test_manual_all_mode_keeps_read_only_tool_waiting(console_env):
    _, service, aion, paperclip = console_env
    aion.snapshot = {"status": "awaiting_approval", "pending_approvals": 1}
    aion.confirmations_by_conversation["conversation-1"] = [
        {
            "message_id": "message-manual",
            "call_id": "tool-call-manual",
            "title": "Check package metadata",
            "description": "Read installed package metadata without importing it.",
            "command_type": "mcp__opswitness__qd_python_package_status",
            "allow_value": "allow",
            "reject_value": "reject",
        }
    ]
    ready = service.draft_plan(
        service.request_plan(PlanRequest(objective="测试全部手动审批")).plan_id
    )
    confirmed = service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(
            plan_sha256=str(ready.plan_sha256),
            approval_mode=ApprovalMode.MANUAL_ALL,
            confirmed=True,
        ),
    )
    assert confirmed.approval_mode == ApprovalMode.MANUAL_ALL
    service.dispatch_plan(ready.plan_id)

    waiting = service.refresh_execution(ready.plan_id)

    assert waiting.status == "awaiting_approval"
    assert paperclip.approvals[0]["status"] == "pending"
    assert aion.resolved_confirmations == []
    assert not any(
        event["kind"] == "aion_tool_gate_auto_approved" for event in service.ledger.read_all()
    )


def test_runtime_question_survives_stale_snapshot_and_resumes_same_team(monkeypatch, console_env):
    _, service, aion, _ = console_env
    ready = service.draft_plan(
        service.request_plan(PlanRequest(objective="测试运行中补充信息")).plan_id
    )
    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
    )
    running = service.dispatch_plan(ready.plan_id)
    assert running.plan is not None
    assert running.execution is not None
    agent_name = running.plan.agents[0].name
    question = "请选择本次演示报告使用的合成日期范围。"

    def stale_snapshot(*args, **kwargs):
        del args, kwargs
        result = mcp_server.request_runtime_input(
            running.plan_id,
            agent_name,
            question,
            ["最近 30 天", "最近 90 天"],
        )
        assert result["accepted"] is True
        return {"status": "awaiting_approval", "pending_approvals": 0}

    monkeypatch.setattr(aion, "execution_snapshot", stale_snapshot)
    waiting = service.refresh_execution(running.plan_id)

    assert waiting.status == "awaiting_input"
    assert waiting.execution is not None
    pending = [item for item in waiting.execution.input_requests if item.status == "pending"]
    assert len(pending) == 1
    assert pending[0].question == question
    action = next(
        row
        for row in service.dashboard()["home"]["action_queue"]
        if row["kind"] == "input_required"
    )
    assert action["plan_id"] == running.plan_id
    assert action["summary"] == question
    ledger_before = json.dumps(service.ledger.read_all(), ensure_ascii=False)
    assert question not in ledger_before

    answer = "最近 30 天；继续使用合成数据，不包含真人信息。"
    resumed = service.answer_runtime_input(
        running.plan_id,
        pending[0].request_id,
        RuntimeInputAnswerRequest(answer=answer, confirmed=True),
    )

    assert resumed.status == "running"
    assert resumed.execution is not None
    assert resumed.execution.aion_team_id == running.execution.aion_team_id
    assert resumed.execution.input_requests[0].status == "answered"
    assert len(aion.team_messages) == 1
    assert question in aion.team_messages[0][1]
    assert answer in aion.team_messages[0][1]
    ledger_after = json.dumps(service.ledger.read_all(), ensure_ascii=False)
    assert question not in ledger_after
    assert answer not in ledger_after
    assert ledger_after.count("task_input_answered") == 1
    assert ledger_after.count("task_input_delivered") == 1

    reconciled = service.answer_runtime_input(
        running.plan_id,
        pending[0].request_id,
        RuntimeInputAnswerRequest(answer=answer, confirmed=True),
    )
    assert reconciled.status == "running"
    assert len(aion.team_messages) == 1
    with pytest.raises(ConsoleConflict, match="already answered differently"):
        service.answer_runtime_input(
            running.plan_id,
            pending[0].request_id,
            RuntimeInputAnswerRequest(answer="另一个答案", confirmed=True),
        )


def test_runtime_input_answer_http_requires_csrf_and_confirmation(monkeypatch, console_env):
    settings, service, aion, _ = console_env
    ready = service.draft_plan(service.request_plan(PlanRequest(objective="测试回答接口")).plan_id)
    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
    )
    running = service.dispatch_plan(ready.plan_id)
    assert running.plan is not None
    requested = mcp_server.request_runtime_input(
        running.plan_id,
        running.plan.agents[0].name,
        "请选择合成演示范围。",
        ["小范围", "完整范围"],
    )
    assert requested["accepted"] is True
    request_id = str(requested["request_id"])

    monkeypatch.setattr(service, "acquire_instance_lease", lambda: True)
    monkeypatch.setattr(service, "recover_startup", lambda: {})
    monkeypatch.setattr(service, "release_instance_lease", lambda: None)
    app = create_app(settings, service=service)
    csrf = app.state.csrf_token
    endpoint = f"/api/v1/plans/{running.plan_id}/input-requests/{request_id}/answer"
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        denied = client.post(
            endpoint,
            json={"answer": "小范围", "confirmed": True},
        )
        assert denied.status_code == 403
        invalid = client.post(
            endpoint,
            json={"answer": "小范围", "confirmed": False},
            headers={"X-QD-CSRF": csrf},
        )
        assert invalid.status_code == 422
        accepted = client.post(
            endpoint,
            json={"answer": "小范围", "confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        assert accepted.status_code == 200
        assert accepted.json()["status"] == "running"
    assert len(aion.team_messages) == 1


def test_runtime_input_artifact_preview_is_request_bound_and_hides_paths(
    monkeypatch, console_env
):
    settings, service, _, _ = console_env
    ready = service.draft_plan(
        service.request_plan(PlanRequest(objective="测试候选知识库预览")).plan_id
    )
    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
    )
    running = service.dispatch_plan(ready.plan_id)
    assert running.plan is not None
    artifact_dir = settings.console.state_dir / "executions" / running.plan_id / "artifacts"
    artifact_dir.mkdir(parents=True, mode=0o700)
    knowledge = {
        "artifact_type": "candidate_knowledge_base",
        "status": "candidate_pending_signoff",
        "scope": "只覆盖合成演示数据。",
        "excerpts": [
            {
                "id": "KB-01",
                "category": "定义",
                "title": "测试规则",
                "statement": "仅用于测试。",
                "source": "测试来源",
            }
        ],
    }
    encoded = json.dumps(knowledge, ensure_ascii=False).encode()
    (artifact_dir / "candidate-knowledge-base.json").write_bytes(encoded)
    (artifact_dir / "not-mentioned.json").write_text('{"private": true}')
    outside = settings.console.state_dir / "outside.json"
    outside.write_text('{"outside": true}')
    (artifact_dir / "linked.json").symlink_to(outside)

    requested = mcp_server.request_runtime_input(
        running.plan_id,
        running.plan.agents[0].name,
        (
            "请先查看 artifacts/candidate-knowledge-base.json 后审定；"
            "artifacts/linked.json 不应越过附件边界。"
        ),
        ["批准", "修改"],
    )
    assert requested["accepted"] is True
    request_id = str(requested["request_id"])

    rows = service.list_runtime_input_artifacts(running.plan_id, request_id)
    assert rows[0] == {
        "name": "candidate-knowledge-base.json",
        "relative_path": "artifacts/candidate-knowledge-base.json",
        "available": True,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "size": len(encoded),
        "mime": "application/json",
        "preview_supported": True,
        "artifact_type": "candidate_knowledge_base",
        "status": "candidate_pending_signoff",
        "item_count": 1,
    }
    assert rows[1]["name"] == "linked.json"
    assert rows[1]["available"] is False
    preview = service.get_runtime_input_artifact(
        running.plan_id,
        request_id,
        "candidate-knowledge-base.json",
    )
    assert preview["content"] == knowledge
    assert str(settings.console.state_dir) not in json.dumps(preview)
    with pytest.raises(RuntimeArtifactNotFound):
        service.get_runtime_input_artifact(
            running.plan_id,
            request_id,
            "not-mentioned.json",
        )
    with pytest.raises(RuntimeArtifactNotFound):
        service.get_runtime_input_artifact(running.plan_id, request_id, "../outside.json")

    monkeypatch.setattr(service, "acquire_instance_lease", lambda: True)
    monkeypatch.setattr(service, "recover_startup", lambda: {})
    monkeypatch.setattr(service, "release_instance_lease", lambda: None)
    app = create_app(settings, service=service)
    endpoint = f"/api/v1/plans/{running.plan_id}/input-requests/{request_id}/artifacts"
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        listed = client.get(endpoint)
        assert listed.status_code == 200
        viewed = client.get(f"{endpoint}/candidate-knowledge-base.json")
        assert viewed.status_code == 200
        assert viewed.json()["content"]["excerpts"][0]["id"] == "KB-01"
        denied = client.get(f"{endpoint}/not-mentioned.json")
        assert denied.status_code == 404


def test_plan_artifacts_list_real_files_and_keep_workspace_results_unverified(
    monkeypatch, console_env
):
    settings, service, _, _ = console_env
    ready = service.draft_plan(
        service.request_plan(PlanRequest(objective="测试运行结果查看")).plan_id
    )
    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
    )
    running = service.dispatch_plan(ready.plan_id)
    artifact_dir = settings.console.state_dir / "executions" / running.plan_id / "artifacts"
    artifact_dir.mkdir(parents=True, mode=0o700)
    chart = {"artifact_type": "chart", "status": "generated", "value": 7}
    chart_bytes = json.dumps(chart).encode()
    (artifact_dir / "chart.json").write_bytes(chart_bytes)
    (artifact_dir / "notes.json").write_text("not-json")
    (artifact_dir / "nested").mkdir()
    (artifact_dir / "nested" / "hidden.json").write_text('{"hidden": true}')
    outside = settings.console.state_dir / "outside-plan-artifact.json"
    outside.write_text('{"outside": true}')
    (artifact_dir / "linked.json").symlink_to(outside)

    rows = service.list_plan_artifacts(running.plan_id)
    assert [row["name"] for row in rows] == ["chart.json", "notes.json"]
    chart_row = rows[0]
    assert chart_row == {
        "name": "chart.json",
        "relative_path": "artifacts/chart.json",
        "available": True,
        "sha256": hashlib.sha256(chart_bytes).hexdigest(),
        "size": len(chart_bytes),
        "mime": "application/json",
        "preview_supported": True,
        "artifact_type": "chart",
        "status": "generated",
        "item_count": None,
        "evidence_status": "workspace_unverified",
    }
    assert rows[1]["preview_supported"] is False
    assert str(settings.console.state_dir) not in json.dumps(rows)

    preview = service.get_plan_artifact(running.plan_id, "chart.json")
    assert preview["content"] == chart
    assert preview["evidence_status"] == "workspace_unverified"
    with pytest.raises(RuntimeArtifactNotFound):
        service.get_plan_artifact(running.plan_id, "../outside-plan-artifact.json")
    with pytest.raises(RuntimeArtifactNotFound):
        service.get_plan_artifact(running.plan_id, "linked.json")

    other = service.request_plan(PlanRequest(objective="另一个隔离任务"))
    assert service.list_plan_artifacts(other.plan_id) == []
    with pytest.raises(RuntimeArtifactNotFound):
        service.get_plan_artifact(other.plan_id, "chart.json")

    monkeypatch.setattr(service, "acquire_instance_lease", lambda: True)
    monkeypatch.setattr(service, "recover_startup", lambda: {})
    monkeypatch.setattr(service, "release_instance_lease", lambda: None)
    app = create_app(settings, service=service)
    endpoint = f"/api/v1/plans/{running.plan_id}/artifacts"
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        listed = client.get(endpoint)
        assert listed.status_code == 200
        assert [row["name"] for row in listed.json()] == ["chart.json", "notes.json"]
        viewed = client.get(f"{endpoint}/chart.json")
        assert viewed.status_code == 200
        assert viewed.json()["content"] == chart
        denied = client.get(f"{endpoint}/linked.json")
        assert denied.status_code == 404


def test_aion_tool_confirmation_delivery_failure_stays_blocked_and_retries(
    monkeypatch, console_env
):
    _, service, aion, paperclip = console_env
    aion.snapshot = {"status": "awaiting_approval", "pending_approvals": 1}
    aion.confirmations_by_conversation["conversation-1"] = [
        {
            "message_id": "message-2",
            "call_id": "tool-call-2",
            "title": "Write a bounded output",
            "description": "The runtime is paused.",
            "command_type": "execute",
            "allow_value": "allow",
            "reject_value": "reject",
        }
    ]
    requested = service.request_plan(PlanRequest(objective="测试审批重放"))
    ready = service.draft_plan(requested.plan_id)
    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(
            plan_sha256=str(ready.plan_sha256),
            approval_mode=ApprovalMode.MANUAL_ALL,
            confirmed=True,
        ),
    )
    service.dispatch_plan(ready.plan_id)
    service.refresh_execution(ready.plan_id)
    approval = paperclip.approvals[0]
    original = aion.resolve_confirmation

    def unavailable(*args, **kwargs):
        del args, kwargs
        raise AionUiError("private runtime detail")

    monkeypatch.setattr(aion, "resolve_confirmation", unavailable)
    with pytest.raises(ConsoleUnavailable, match="runtime is still blocked"):
        service.decide_approval(
            approval["id"],
            ApprovalDecisionRequest(decision="reject", confirmed=True),
        )
    assert approval["status"] == "rejected"
    assert aion.confirmations_by_conversation["conversation-1"]
    failed = service.ledger.read_all()[-1]
    assert failed["kind"] == "aion_tool_gate_delivery_failed"
    assert failed["degraded"] is True
    assert "private runtime detail" not in json.dumps(failed)

    monkeypatch.setattr(aion, "resolve_confirmation", original)
    service.refresh_execution(ready.plan_id)
    assert aion.resolved_confirmations == [("conversation-1", "tool-call-2", "reject")]


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
        lambda *args, **kwargs: {"status": "failed", "error": hostile},
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

    def status_failed(*args, **kwargs):
        del args, kwargs
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
        "opswitness.console.service.check_mail",
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
        "opswitness.console.service.check_mail",
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
        "opswitness.console.service.authorize_mail",
        lambda settings: {
            "ok": True,
            "authenticated": True,
            "scope_read_only": True,
            "credential_storage": "encrypted",
        },
    )
    monkeypatch.setattr(
        "opswitness.console.service.save_mail_activation",
        lambda *, enabled, model_metadata_consent: saved.append((enabled, model_metadata_consent)),
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
        "opswitness.console.service.authorize_mail",
        lambda settings: {"ok": False, "error": hostile},
    )
    monkeypatch.setattr(
        "opswitness.console.service.save_mail_activation",
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


def test_mail_oauth_client_import_is_audited_without_secret_material(monkeypatch, console_env):
    _, service, _, _ = console_env
    private_json = '{"installed":{"client_secret":"private-oauth-value"}}'
    captured: list[str] = []
    monkeypatch.setattr(
        "opswitness.console.service.save_oauth_client",
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
        "opswitness.console.service.save_oauth_client",
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
        "opswitness.console.service.save_mail_activation",
        lambda *, enabled, model_metadata_consent: saved.append((enabled, model_metadata_consent)),
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
        "opswitness.console.service.save_telegram_credentials",
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
        "opswitness.console.service.save_telegram_credentials",
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


def test_telegram_console_test_is_evidence_first_and_uses_fixed_message(monkeypatch, console_env):
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
        "opswitness.console.service.send_telegram",
        lambda text, settings: sent.append((text, settings.telegram.chat_id)) or True,
    )

    assert service.test_telegram() == {"sent": True}
    assert sent == [("OpsWitness Telegram delivery test", "123456")]
    encoded = json.dumps(service.ledger.read_all(), ensure_ascii=False)
    assert "private-token" not in encoded
    assert "123456" not in encoded
    assert [event["kind"] for event in service.ledger.read_all()] == [
        "telegram_test_requested",
        "telegram_test_finished",
    ]

    monkeypatch.setattr("opswitness.console.service.send_telegram", lambda *args: False)
    with pytest.raises(ConsoleUnavailable, match=TELEGRAM_TEST_FAILED):
        service.test_telegram()
    assert service.ledger.read_all()[-1]["kind"] == "telegram_test_failed"


def test_telegram_console_does_not_send_without_requested_evidence(monkeypatch, console_env):
    _, service, _, _ = console_env
    monkeypatch.setattr(service.ledger, "append", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "opswitness.console.service.send_telegram",
        lambda *args: pytest.fail("Telegram must not send without durable requested evidence"),
    )
    with pytest.raises(ConsoleUnavailable, match="telegram_test_requested"):
        service.test_telegram()


def test_telegram_console_disable_and_environment_override_fail_closed(monkeypatch, console_env):
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
        "opswitness.console.service.clear_telegram_credentials",
        lambda: cleared.append(True) or True,
    )
    assert service.disable_telegram() == {"disabled": True}
    assert cleared == [True]
    assert service.telegram_setup_status()["configured"] is False

    monkeypatch.setenv("OPSWITNESS_TELEGRAM__BOT_TOKEN", "environment-secret")
    with pytest.raises(ConsoleConflict, match=TELEGRAM_ENVIRONMENT_CONTROLLED):
        service.disable_telegram()

    monkeypatch.delenv("OPSWITNESS_TELEGRAM__BOT_TOKEN")
    monkeypatch.setenv("QD_TELEGRAM__CHAT_ID", "legacy-environment-secret")
    assert service.telegram_setup_status()["environment_controlled"] is True
    with pytest.raises(ConsoleConflict, match=TELEGRAM_ENVIRONMENT_CONTROLLED):
        service.disable_telegram()


def test_paperclip_launchd_label_supports_legacy_and_rejects_dual_install(tmp_path):
    launchagents = tmp_path / "LaunchAgents"
    launchagents.mkdir()
    legacy = launchagents / "com.quarterdeck.paperclip.plist"
    legacy.write_text("legacy\n")

    assert _paperclip_launchd_label(launchagents) == "com.quarterdeck.paperclip"

    (launchagents / "com.opswitness.paperclip.plist").write_text("canonical\n")
    with pytest.raises(ConsoleUnavailable, match="new and legacy"):
        _paperclip_launchd_label(launchagents)


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
        "opswitness.console.service.save_telegram_credentials",
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
    raw["agents"][0]["model"] = "claude-fable-5[1m]"
    raw["agents"][1]["model"] = "sonnet"
    raw["agents"][2]["model"] = "default"
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
            {"name": agent.name, "conversation_id": f"conversation-{index}"}
            for index, agent in enumerate(plan.agents, start=1)
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
    assert [row["model"] for row in captured["agents"]] == [
        "claude-fable-5[1m]",
        "sonnet",
        "default",
    ]
    assert result["team_id"] == "team-org"
    assert result["team_run_id"] == "run-org"
    assert result["agent_sessions"] == [
        {"agent_name": agent.name, "conversation_id": f"conversation-{index}"}
        for index, agent in enumerate(plan.agents, start=1)
    ]


def test_aionui_run_controls_use_exact_public_team_routes(console_env):
    settings, _, _, _ = console_env
    phase = {"value": "running"}
    requests: list[tuple[str, str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        requests.append((request.method, request.url.path, body))
        if request.method == "GET":
            if phase["value"] == "inactive":
                data = {"active_run": None}
            else:
                data = {
                    "active_run": {
                        "team_run_id": "team-run-1",
                        "status": phase["value"],
                        "slot_work": [
                            {
                                "slot_id": "slot-1",
                                "state": "paused" if phase["value"] == "paused" else "running",
                            }
                        ],
                    }
                }
            return httpx.Response(200, json={"success": True, "data": data})
        if request.url.path.endswith("/agents/slot-1/pause"):
            phase["value"] = "paused"
        elif request.url.path.endswith("/cancel"):
            phase["value"] = "inactive"
        return httpx.Response(200, json={"success": True, "data": {}})

    with httpx.Client(
        base_url=settings.console.aionui_base,
        transport=httpx.MockTransport(handler),
    ) as http_client:
        client = AionUiClient(settings.console, client=http_client)
        paused = client.pause_team_run("team-1", "team-run-1")
        assert paused["status"] == "paused"
        phase["value"] = "running"
        cancelled = client.cancel_team_run("team-1", "team-run-1")
        assert cancelled["status"] == "inactive"

    assert (
        "POST",
        "/api/teams/team-1/runs/team-run-1/agents/slot-1/pause",
        {"reason": "opswitness_user_pause"},
    ) in requests
    assert (
        "POST",
        "/api/teams/team-1/runs/team-run-1/cancel",
        {"reason": "opswitness_user_terminate"},
    ) in requests


def test_aionui_member_telemetry_returns_only_state_and_timestamp(monkeypatch, console_env):
    settings, _, _, _ = console_env
    client = AionUiClient(settings.console)
    monkeypatch.setattr(
        client,
        "team",
        lambda team_id: {
            "id": team_id,
            "assistants": [
                {"conversation_id": "c-1", "pending_confirmations": 1},
                {"conversation_id": "c-2", "pending_confirmations": 0},
            ],
        },
    )
    monkeypatch.setattr(client, "team_run_state", lambda team_id: {})
    monkeypatch.setattr(
        client,
        "messages",
        lambda conversation_id: (
            [
                {
                    "position": "left",
                    "status": "finish",
                    "content": "private tool output must never leave the adapter",
                    "created_at": "2026-07-14T08:00:00+00:00",
                }
            ]
            if conversation_id == "c-2"
            else []
        ),
    )
    snapshot = client.execution_snapshot(
        "team-telemetry",
        ["c-1", "c-2"],
        agent_sessions=[
            {"agent_name": "运行 Agent", "conversation_id": "c-1"},
            {"agent_name": "复核 Agent", "conversation_id": "c-2"},
        ],
    )
    assert snapshot["status"] == "awaiting_approval"
    assert snapshot["member_observations"] == [
        {
            "agent_name": "运行 Agent",
            "state": "activity_observed",
            "observed_at": snapshot["member_observations"][0]["observed_at"],
            "source": "adapter",
        },
        {
            "agent_name": "复核 Agent",
            "state": "response_observed",
            "observed_at": "2026-07-14T08:00:00+00:00",
            "source": "adapter",
        },
    ]
    assert "private tool output" not in json.dumps(snapshot, ensure_ascii=False)


def test_aionui_execution_progress_exposes_bounded_activity_without_private_content(
    monkeypatch, console_env
):
    settings, _, _, _ = console_env
    client = AionUiClient(settings.console)
    monkeypatch.setattr(
        client,
        "team",
        lambda team_id: {
            "id": team_id,
            "assistants": [
                {
                    "name": "运行 Agent",
                    "conversation_id": "c-1",
                    "slot_id": "slot-1",
                    "pending_confirmations": 0,
                },
                {
                    "name": "复核 Agent",
                    "conversation_id": "c-2",
                    "slot_id": "slot-2",
                    "pending_confirmations": 0,
                },
            ],
        },
    )
    monkeypatch.setattr(
        client,
        "team_run_state",
        lambda team_id: {
            "active_run": {
                "status": "running",
                "slot_work": [
                    {
                        "slot_id": "slot-1",
                        "state": "running",
                        "active_turn_started_at_ms": 1_783_500_000_000,
                        "active_turn_elapsed_ms": 92_000,
                        "active_turn_slow": True,
                    }
                ],
            }
        },
    )

    def messages(conversation_id):
        if conversation_id != "c-1":
            return []
        return [
            {
                "id": "message-tool-1",
                "type": "acp_tool_call",
                "position": "left",
                "status": "finish",
                "created_at": "2026-07-15T22:00:00+00:00",
                "content": {
                    "update": {
                        "title": "mcp__aionui-team__team_task_update",
                        "status": "completed",
                        "raw_input": {"api_key": "must-not-leak"},
                        "raw_output": "private tool output",
                    }
                },
            },
            {
                "id": "message-text-1",
                "type": "text",
                "position": "left",
                "status": "finish",
                "created_at": "2026-07-15T22:01:00+00:00",
                "content": "private response body must not leave the adapter",
            },
        ]

    monkeypatch.setattr(client, "messages", messages)
    snapshot = client.execution_snapshot(
        "team-progress",
        ["c-1", "c-2"],
        agent_sessions=[
            {"agent_name": "运行 Agent", "conversation_id": "c-1"},
            {"agent_name": "复核 Agent", "conversation_id": "c-2"},
        ],
    )

    assert snapshot["status"] == "running"
    assert snapshot["progress"]["active_members"] == [
        {
            "agent_name": "运行 Agent",
            "state": "running",
            "started_at": "2026-07-08T08:40:00+00:00",
            "elapsed_seconds": 92,
            "slow": True,
        }
    ]
    assert snapshot["progress"]["recent_activity"] == [
        {
            "activity_id": "message-text-1",
            "agent_name": "运行 Agent",
            "kind": "response",
            "status": "observed",
            "observed_at": "2026-07-15T22:01:00+00:00",
            "count": 1,
        },
        {
            "activity_id": "message-tool-1",
            "agent_name": "运行 Agent",
            "kind": "tool_call",
            "status": "completed",
            "tool_name": "mcp__aionui-team__team_task_update",
            "observed_at": "2026-07-15T22:00:00+00:00",
            "count": 1,
        },
    ]
    rendered = json.dumps(snapshot, ensure_ascii=False)
    assert "must-not-leak" not in rendered
    assert "private tool output" not in rendered
    assert "private response body" not in rendered
    assert "percent" not in rendered

    bounded = client.execution_snapshot(
        "team-progress",
        ["c-1", "c-2"],
        agent_sessions=[
            {"agent_name": "运行 Agent", "conversation_id": "c-1"},
            {"agent_name": "复核 Agent", "conversation_id": "c-2"},
        ],
        observed_after="2026-07-15T22:00:30+00:00",
    )
    assert bounded["progress"]["recent_activity"] == [
        {
            "activity_id": "message-text-1",
            "agent_name": "运行 Agent",
            "kind": "response",
            "status": "observed",
            "observed_at": "2026-07-15T22:01:00+00:00",
            "count": 1,
        }
    ]


def test_aionui_execution_progress_binds_safe_activity_to_plan_stages(monkeypatch, console_env):
    settings, _, _, _ = console_env
    client = AionUiClient(settings.console)
    monkeypatch.setattr(
        client,
        "team",
        lambda team_id: {
            "id": team_id,
            "assistants": [
                {
                    "name": "解读 Agent",
                    "conversation_id": "c-1",
                    "slot_id": "slot-1",
                    "pending_confirmations": 0,
                },
                {
                    "name": "引用核验 Agent",
                    "conversation_id": "c-2",
                    "slot_id": "slot-2",
                    "pending_confirmations": 0,
                },
            ],
        },
    )
    monkeypatch.setattr(
        client,
        "team_run_state",
        lambda team_id: {"active_run": {"status": "running", "slot_work": []}},
    )

    def team_task_create(message_id, at, task_id, subject, owner, blocked_by=None):
        task = {
            "task_id": task_id,
            "owner": owner,
            "status": "pending",
            "subject": subject,
            "blocked_by": blocked_by or [],
            "description": "private stage description must not leave the adapter",
        }
        return {
            "id": message_id,
            "type": "acp_tool_call",
            "position": "left",
            "status": "finish",
            "created_at": at,
            "content": {
                "update": {
                    "title": "mcp__aionui-team__team_task_create",
                    "status": "completed",
                    "raw_input": {
                        "subject": subject,
                        "description": "secret stage input",
                    },
                    "raw_output": [{"text": json.dumps({"status": "ok", "task": task})}],
                }
            },
        }

    def team_task_update(message_id, at, task_id, status):
        return {
            "id": message_id,
            "type": "acp_tool_call",
            "position": "left",
            "status": "finish",
            "created_at": at,
            "content": {
                "update": {
                    "title": "mcp__aionui-team__team_task_update",
                    "status": "completed",
                    "raw_input": {"task_id": task_id, "status": status},
                    "raw_output": [{"text": "private update output"}],
                }
            },
        }

    first_messages = {
        "c-1": [
            team_task_create(
                "create-stage-1",
                "2026-07-16T07:00:00+00:00",
                "task-stage-1",
                "依赖校验与确定性命盘构建",
                "slot-1",
            ),
            team_task_update(
                "start-stage-1",
                "2026-07-16T07:01:00+00:00",
                "task-stage-1",
                "in_progress",
            ),
            {
                "id": "safe-tool-stage-1",
                "type": "acp_tool_call",
                "position": "left",
                "status": "finish",
                "created_at": "2026-07-16T07:02:00+00:00",
                "content": {
                    "update": {
                        "title": "mcp__opswitness__qd_python_package_status",
                        "status": "completed",
                        "raw_input": {"api_key": "never-render-this"},
                        "raw_output": "private package result",
                    }
                },
            },
            team_task_update(
                "complete-stage-1",
                "2026-07-16T07:03:00+00:00",
                "task-stage-1",
                "completed",
            ),
            team_task_create(
                "create-stage-2",
                "2026-07-16T07:04:00+00:00",
                "task-stage-2",
                "旧版主题：解读命盘特征",
                "slot-1",
                ["task-stage-1"],
            ),
            team_task_update(
                "start-stage-2",
                "2026-07-16T07:05:00+00:00",
                "task-stage-2",
                "in_progress",
            ),
            {
                "id": "response-stage-2",
                "type": "text",
                "position": "left",
                "status": "finish",
                "created_at": "2026-07-16T07:06:00+00:00",
                "content": "private response body",
            },
        ],
        "c-2": [
            team_task_create(
                "create-stage-3",
                "2026-07-16T07:05:30+00:00",
                "task-stage-3",
                "引用核验",
                "slot-2",
                ["task-stage-2"],
            )
        ],
    }
    monkeypatch.setattr(client, "messages", lambda conversation_id: first_messages[conversation_id])
    planned_stages = [
        {"order": 1, "title": "依赖校验与确定性命盘构建", "owner": "解读 Agent"},
        {"order": 2, "title": "确定性特征的 AI 解读", "owner": "解读 Agent"},
        {"order": 3, "title": "引用核验", "owner": "引用核验 Agent"},
    ]
    sessions = [
        {"agent_name": "解读 Agent", "conversation_id": "c-1"},
        {"agent_name": "引用核验 Agent", "conversation_id": "c-2"},
    ]

    snapshot = client.execution_snapshot(
        "team-stage-progress",
        ["c-1", "c-2"],
        agent_sessions=sessions,
        planned_stages=planned_stages,
    )
    stages = snapshot["progress"]["stages"]
    assert [(row["stage_order"], row["status"]) for row in stages] == [
        (1, "completed"),
        (2, "running"),
        (3, "blocked"),
    ]
    assert stages[0]["task_id"] == "task-stage-1"
    assert stages[0]["recent_activity"][0]["tool_name"] == (
        "mcp__opswitness__qd_python_package_status"
    )
    assert stages[1]["recent_activity"][0]["kind"] == "response"
    assert stages[2]["blocked_by"] == [2]
    rendered = json.dumps(snapshot, ensure_ascii=False)
    assert "never-render-this" not in rendered
    assert "private package result" not in rendered
    assert "private response body" not in rendered
    assert "secret stage input" not in rendered
    assert "private stage description" not in rendered

    second_messages = {
        "c-1": [
            team_task_update(
                "complete-stage-2",
                "2026-07-16T07:07:00+00:00",
                "task-stage-2",
                "completed",
            )
        ],
        "c-2": [
            team_task_update(
                "start-stage-3",
                "2026-07-16T07:08:00+00:00",
                "task-stage-3",
                "in_progress",
            )
        ],
    }
    monkeypatch.setattr(
        client, "messages", lambda conversation_id: second_messages[conversation_id]
    )
    refreshed = client.execution_snapshot(
        "team-stage-progress",
        ["c-1", "c-2"],
        agent_sessions=sessions,
        planned_stages=planned_stages,
        existing_stage_progress=stages,
    )
    assert [(row["stage_order"], row["status"]) for row in refreshed["progress"]["stages"]] == [
        (1, "completed"),
        (2, "completed"),
        (3, "running"),
    ]

    monkeypatch.setattr(
        client,
        "team_run_state",
        lambda team_id: {"active_run": {"status": "completed", "slot_work": []}},
    )
    terminal = client.execution_snapshot(
        "team-stage-progress",
        ["c-1", "c-2"],
        agent_sessions=sessions,
        planned_stages=planned_stages,
        existing_stage_progress=refreshed["progress"]["stages"],
    )
    assert terminal["status"] == "failed"
    assert terminal["terminal_reason"] == "unfinished_stages"
    assert terminal["unfinished_stage_orders"] == [3]


def test_aionui_confirmation_adapter_allows_once_and_never_persists_permission(
    monkeypatch, console_env
):
    settings, _, _, _ = console_env
    client = AionUiClient(settings.console)
    calls = []

    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if method == "GET":
            return [
                {
                    "id": "message-1",
                    "call_id": "toolu-1",
                    "title": "Inspect a dependency",
                    "description": "Read-only environment check",
                    "command_type": "execute",
                    "options": [
                        {"value": "allow_always"},
                        {"value": "allow"},
                        {"value": "reject"},
                    ],
                }
            ]
        return {"ok": True}

    monkeypatch.setattr(client, "_request", request)
    confirmations = client.list_confirmations("conversation-1")
    assert confirmations[0]["allow_value"] == "allow"
    assert confirmations[0]["reject_value"] == "reject"
    resolved = client.resolve_confirmation("conversation-1", "toolu-1", "approve")
    assert resolved["value"] == "allow"
    assert calls[-1] == (
        "POST",
        "/api/conversations/conversation-1/confirmations/toolu-1/confirm",
        {
            "timeout": 10.0,
            "json": {
                "msg_id": "message-1",
                "data": "allow",
                "always_allow": False,
            },
        },
    )


def test_aionui_confirmation_adapter_rejects_unknown_or_ambiguous_options(monkeypatch, console_env):
    settings, _, _, _ = console_env
    client = AionUiClient(settings.console)
    monkeypatch.setattr(
        client,
        "_request",
        lambda *args, **kwargs: [
            {
                "id": "message-1",
                "call_id": "toolu-1",
                "options": [
                    {"value": "approve"},
                    {"value": "allow"},
                    {"value": "reject"},
                ],
            }
        ],
    )
    with pytest.raises(AionUiError, match="allow-once and reject"):
        client.list_confirmations("conversation-1")


def test_aionui_active_team_does_not_imply_each_member_activity(monkeypatch, console_env):
    settings, _, _, _ = console_env
    client = AionUiClient(settings.console)
    monkeypatch.setattr(
        client,
        "team",
        lambda team_id: {
            "id": team_id,
            "assistants": [
                {"conversation_id": "c-1", "pending_confirmations": 0},
                {"conversation_id": "c-2", "pending_confirmations": 0},
            ],
        },
    )
    monkeypatch.setattr(client, "team_run_state", lambda _: {"active_run": {"status": "running"}})
    monkeypatch.setattr(client, "messages", lambda _: [])

    snapshot = client.execution_snapshot(
        "team-telemetry",
        ["c-1", "c-2"],
        agent_sessions=[
            {"agent_name": "运行 Agent", "conversation_id": "c-1"},
            {"agent_name": "复核 Agent", "conversation_id": "c-2"},
        ],
    )

    assert snapshot["status"] == "running"
    assert [item["state"] for item in snapshot["member_observations"]] == [
        "unobserved",
        "unobserved",
    ]


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
        marker = workspace / ".opswitness-session.json"
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
            json.loads((workspace / ".opswitness-session.json").read_text())["team_id"] == team_id
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

    monkeypatch.setattr("opswitness.console.aionui.shutil.rmtree", cleanup_failed)
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
    marker = session.workspace / ".opswitness-session.json"
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
        "opswitness.console.service.httpx.get", lambda *args, **kwargs: HealthyResponse()
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
    assert all(
        [event["kind"] for event in row["events"]] == ["task_plan_confirmed"] for row in history
    )


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
        "opswitness.console.service.httpx.get", lambda *args, **kwargs: HealthyResponse()
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
    assert providers["anthropic"]["runtime_ready"] is True
    assert providers["anthropic"]["status"] == "online"
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


def test_console_labels_managed_anthropic_api_key_and_keychain_boundary(console_env):
    _, service, _, _ = console_env

    def api_key_probe(provider):
        return {
            "provider": provider,
            "label": "ChatGPT / OpenAI" if provider == "openai" else "Claude",
            "installed": True,
            "authenticated": provider == "anthropic",
            "auth_mode": "api_key" if provider == "anthropic" else "none",
            "status": "online" if provider == "anthropic" else "setup",
            "detail": "账号已登录" if provider == "anthropic" else "待登录",
        }

    service._provider_probe = api_key_probe
    providers = service.provider_statuses()
    assert providers["anthropic"]["detail"] == "Anthropic API Key 已连接，可用于任务"
    assert "macOS Keychain" in str(providers["anthropic"]["privacy"])


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


def test_openai_api_key_connection_is_transient_and_audited_without_key(console_env):
    _, service, _, _ = console_env
    secret = "sk-local-sentinel-value"
    received: dict[str, str | None] = {}

    def api_login(provider: str, api_key: str | None) -> bool:
        received["provider"] = provider
        received["api_key"] = api_key
        return provider == "openai" and api_key == secret

    service._provider_api_login = api_login
    requested = service.request_provider_connection(
        "openai",
        ProviderConnectionRequest(method="api", api_key=secret),
    )
    assert requested.method == "api"
    ready = service.run_provider_connection(requested.job_id, secret)
    assert ready.status == "ready"
    assert received == {"provider": "openai", "api_key": secret}
    events = service.ledger.read_all()
    encoded = json.dumps([event["payload"] for event in events], ensure_ascii=False)
    assert secret not in encoded
    assert events[0]["payload"] == {
        "schema_version": 2,
        "provider": "openai",
        "method": "api",
        "flow": "vendor_cli",
    }
    assert events[1]["payload"] == {
        "schema_version": 2,
        "provider": "openai",
        "method": "api",
        "authenticated": True,
    }


def test_provider_api_key_connection_rejects_missing_or_unsupported_key(console_env):
    _, service, _, _ = console_env
    with pytest.raises(ConsoleConflict, match="OpenAI API key is required"):
        service.request_provider_connection(
            "openai",
            ProviderConnectionRequest(method="api"),
        )
    with pytest.raises(ConsoleConflict, match="API key connection method"):
        service.request_provider_connection(
            "anthropic",
            ProviderConnectionRequest(method="api", api_key="sk-local-sentinel-value"),
        )
    with pytest.raises(ValueError, match="explicit confirmation"):
        ProviderConnectionRequest(
            method="api_key",
            api_key="sk-ant-local-sentinel-value",
        )


def test_anthropic_api_key_connection_is_keychained_and_audited_without_key(console_env):
    _, service, _, _ = console_env
    secret = "sk-ant-local-sentinel-value"
    received: dict[str, str | None] = {}

    def key_login(provider: str, api_key: str | None) -> bool:
        received["provider"] = provider
        received["api_key"] = api_key
        return provider == "anthropic" and api_key == secret

    service._provider_key_login = key_login
    requested = service.request_provider_connection(
        "anthropic",
        ProviderConnectionRequest(method="api_key", api_key=secret, confirmed=True),
    )
    assert requested.method == "api_key"
    ready = service.run_provider_connection(requested.job_id, secret)
    assert ready.status == "ready"
    assert received == {"provider": "anthropic", "api_key": secret}
    events = service.ledger.read_all()
    encoded = json.dumps(events, ensure_ascii=False)
    assert secret not in encoded
    assert events[0]["payload"] == {
        "schema_version": 2,
        "provider": "anthropic",
        "method": "api_key",
        "flow": "keychain_api_key_helper",
    }
    assert events[1]["payload"] == {
        "schema_version": 2,
        "provider": "anthropic",
        "method": "api_key",
        "authenticated": True,
    }


@pytest.mark.parametrize("provider", ["deepseek", "xai"])
def test_external_provider_api_key_is_keychained_without_runtime_overclaim(
    console_env,
    provider,
):
    _, service, _, _ = console_env
    secret = f"{provider}-local-sentinel-value"
    received = []
    connected: set[str] = set()

    def key_login(selected: str, api_key: str | None) -> bool:
        received.append((selected, api_key))
        if selected == provider and api_key == secret:
            connected.add(selected)
            return True
        return False

    def probe(selected: str) -> dict[str, object]:
        authenticated = selected in connected
        return {
            "provider": selected,
            "label": "DeepSeek" if selected == "deepseek" else "Grok / xAI",
            "installed": selected == "deepseek",
            "authenticated": authenticated,
            "auth_mode": "api_key" if authenticated else "none",
            "status": "online" if authenticated else "setup",
            "detail": "API Key 已连接" if authenticated else "待连接",
        }

    service._provider_key_login = key_login
    service._provider_probe = probe
    requested = service.request_provider_connection(
        provider,
        ProviderConnectionRequest(method="api_key", api_key=secret, confirmed=True),
    )
    ready = service.run_provider_connection(requested.job_id, secret)

    assert ready.status == "ready"
    assert received == [(provider, secret)]
    status = service.provider_statuses()[provider]
    assert status["authenticated"] is True
    assert status["runtime_ready"] is False
    assert status["status"] == "attention"
    assert "尚未启用" in str(status["detail"])
    events = service.ledger.read_all()
    assert secret not in json.dumps(events, ensure_ascii=False)
    assert events[0]["payload"] == {
        "schema_version": 2,
        "provider": provider,
        "method": "api_key",
        "flow": "keychain_api_key_helper",
    }


def test_provider_connection_method_matrix_rejects_unsupported_flows(console_env):
    _, service, _, _ = console_env
    with pytest.raises(ConsoleConflict, match="deepseek does not support"):
        service.request_provider_connection("deepseek", ProviderConnectionRequest())
    with pytest.raises(ConsoleConflict, match="xai does not support"):
        service.request_provider_connection(
            "xai",
            ProviderConnectionRequest(method="api"),
        )
    with pytest.raises(ConsoleConflict, match="API key connection method"):
        service.request_provider_connection(
            "anthropic",
            ProviderConnectionRequest(method="api", api_key="sk-ant-local-sentinel"),
        )


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
                "summary": "OpsWitness deferred a tool call.",
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


def test_provider_and_approval_http_facade_requires_local_csrf(console_env, monkeypatch):
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


def test_provider_api_key_http_handoff_is_csrf_protected_and_nonpersistent(
    console_env, monkeypatch
):
    settings, service, _, _ = console_env
    secret = "sk-local-http-sentinel"
    received: dict[str, str | None] = {}

    def api_login(provider: str, api_key: str | None) -> bool:
        received["provider"] = provider
        received["api_key"] = api_key
        return provider == "openai" and api_key == secret

    service._provider_api_login = api_login
    monkeypatch.setattr(service, "acquire_instance_lease", lambda: True)
    monkeypatch.setattr(service, "recover_startup", lambda: {})
    monkeypatch.setattr(service, "release_instance_lease", lambda: None)
    app = create_app(settings, service=service)
    csrf = app.state.csrf_token
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        denied = client.post(
            "/api/v1/providers/openai/connect",
            json={"method": "api", "api_key": secret},
        )
        assert denied.status_code == 403
        missing = client.post(
            "/api/v1/providers/openai/connect",
            json={"method": "api"},
            headers={"X-QD-CSRF": csrf},
        )
        assert missing.status_code == 409
        malformed = client.post(
            "/api/v1/providers/openai/connect",
            json={"method": "api", "api_key": f"{secret} invalid"},
            headers={"X-QD-CSRF": csrf},
        )
        assert malformed.status_code == 409
        assert secret not in malformed.text
        accepted = client.post(
            "/api/v1/providers/openai/connect",
            json={"method": "api", "api_key": secret},
            headers={"X-QD-CSRF": csrf},
        )
        assert accepted.status_code == 202
        assert accepted.json()["method"] == "api"
        assert secret not in accepted.text
        ready = service.run_provider_connection(accepted.json()["job_id"], secret)
        assert ready.status == "ready"
    assert received == {"provider": "openai", "api_key": secret}
    assert secret not in json.dumps(service.ledger.read_all(), ensure_ascii=False)


def test_anthropic_api_key_http_setup_requires_confirmation_and_never_echoes_key(
    console_env,
    monkeypatch,
):
    settings, service, _, _ = console_env
    secret = "sk-ant-local-http-sentinel"
    received: dict[str, str | None] = {}

    def key_login(provider: str, api_key: str | None) -> bool:
        received["provider"] = provider
        received["api_key"] = api_key
        return provider == "anthropic" and api_key == secret

    service._provider_key_login = key_login
    monkeypatch.setattr(service, "acquire_instance_lease", lambda: True)
    monkeypatch.setattr(service, "recover_startup", lambda: {})
    monkeypatch.setattr(service, "release_instance_lease", lambda: None)
    app = create_app(settings, service=service)
    csrf = app.state.csrf_token
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        unconfirmed = client.post(
            "/api/v1/providers/anthropic/connect",
            json={"method": "api_key", "api_key": secret},
            headers={"X-QD-CSRF": csrf},
        )
        assert unconfirmed.status_code == 409
        assert secret not in unconfirmed.text
        accepted = client.post(
            "/api/v1/providers/anthropic/connect",
            json={"method": "api_key", "api_key": secret, "confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        assert accepted.status_code == 202
        assert accepted.json()["method"] == "api_key"
        assert secret not in accepted.text
        ready = service.run_provider_connection(accepted.json()["job_id"], secret)
        assert ready.status == "ready"
    assert received == {"provider": "anthropic", "api_key": secret}
    assert secret not in json.dumps(service.ledger.read_all(), ensure_ascii=False)


def test_console_dashboard_contains_schedule_parser_errors(monkeypatch, console_env):
    _, service, _, _ = console_env
    hostile = "private schedule parser echo from /Users/private/config.yaml"

    def invalid_schedules(*args, **kwargs):
        del args, kwargs
        raise ValueError(hostile)

    monkeypatch.setattr(
        "opswitness.console.service.load_effective_schedules",
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
        assert "OpsWitness" in page.text
        assert page.headers["x-frame-options"] == "DENY"
    assert lifecycle == ["lease", "recovery", "release"]


def test_mail_authorization_http_requires_both_explicit_acknowledgements(console_env, monkeypatch):
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


def test_telegram_http_redacts_credentials_and_requires_explicit_actions(console_env, monkeypatch):
    settings, service, _, _ = console_env
    monkeypatch.setattr(
        "opswitness.console.service.save_telegram_credentials",
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
    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(config))
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


def test_home_uses_chat_for_first_or_unconfirmed_work_then_today_after_confirmation(console_env):
    _, service, _, _ = console_env
    assert service.dashboard()["home"]["default_view"] == "workspace"

    requested = service.request_plan(PlanRequest(objective="规划首页路由测试"))
    ready = service.draft_plan(requested.plan_id)
    assert ready.status == "ready"
    assert service.dashboard()["home"]["has_unconfirmed_plan"] is True
    assert service.dashboard()["home"]["default_view"] == "workspace"

    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
    )
    home = service.dashboard()["home"]
    assert home["first_use"] is False
    assert home["default_view"] == "today"
    assert home["active_teams"][0]["plan_id"] == ready.plan_id
    assert all(member["state"] == "unobserved" for member in home["active_teams"][0]["members"])


def test_home_action_queue_uses_fixed_priority_order(console_env):
    _, service, _, paperclip = console_env
    requested = service.request_plan(PlanRequest(objective="首页行动排序测试"))
    ready = service.draft_plan(requested.plan_id)

    def fail(current):
        current.status = "failed"
        current.error = "任务需要处理"
        return current

    service.store.mutate(ready.plan_id, fail)
    paperclip.approvals.append(
        {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "status": "pending",
            "kind": "tool_call",
            "title": "需要批准",
            "summary": "审批测试",
            "recommendedAction": "review",
        }
    )
    actions = service.dashboard()["home"]["action_queue"]
    priorities = [action["priority"] for action in actions]
    assert priorities == sorted(priorities)
    assert actions[0]["kind"] == "approval"
    assert next(action for action in actions if action["kind"] == "task_blocked")["priority"] == 2
    assert next(action for action in actions if action["kind"] == "operational")["priority"] == 3


def test_home_bounds_historical_questions_errors_and_titles(console_env, monkeypatch):
    settings, service, _, _ = console_env
    question = "请补充完整的历史运行输入与约束。" * 60
    waiting = service.draft_plan(
        service.request_plan(PlanRequest(objective="等待输入的历史任务")).plan_id
    )

    def await_input(current):
        current.status = "awaiting_input"
        current.execution = ExecutionState.model_validate(
            {
                "kind": "aion_team",
                "status": "awaiting_input",
                "input_requests": [
                    {
                        "request_id": current.plan_id,
                        "agent_name": "总控",
                        "question": question,
                        "question_sha256": hashlib.sha256(question.encode()).hexdigest(),
                    }
                ],
            }
        )
        return current

    service.store.mutate(waiting.plan_id, await_input)

    long_objective = "旧任务包含很长的目标说明。" * 100
    failed = service.request_plan(PlanRequest(objective=long_objective))

    def fail(current):
        current.status = "failed"
        current.error = "历史失败详情。" * 70
        return current

    service.store.mutate(failed.plan_id, fail)

    monkeypatch.setattr(service, "acquire_instance_lease", lambda: True)
    monkeypatch.setattr(service, "recover_startup", lambda: {})
    monkeypatch.setattr(service, "release_instance_lease", lambda: None)
    app = create_app(settings, service=service)
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        response = client.get("/api/v1/bootstrap")

    assert response.status_code == 200
    actions = response.json()["home"]["action_queue"]
    input_action = next(action for action in actions if action["action_id"] == f"input:{waiting.plan_id}")
    failed_action = next(
        action for action in actions if action["action_id"] == f"blocked:{failed.plan_id}"
    )
    assert len(input_action["summary"]) == 320
    assert len(failed_action["summary"]) == 320
    assert len(failed_action["title"]) <= 160
    assert len(failed_action["title"]) < len(f"需要处理：{long_objective}")


def test_team_blueprint_keeps_only_topology_and_is_ledgered(console_env):
    _, service, _, _ = console_env
    requested = service.request_plan(PlanRequest(objective="保存团队蓝图"))
    ready = service.draft_plan(requested.plan_id)
    blueprint = service.save_team_blueprint(
        TeamBlueprintSaveRequest(
            source_plan_id=ready.plan_id,
            name="研究与复核团队",
            confirmed=True,
        )
    )
    assert blueprint.verification_status == "unverified"
    assert blueprint.source_plan_sha256 == ready.plan_sha256
    assert [agent.key for agent in blueprint.agents] == ["agent_1", "agent_2"]
    encoded = json.dumps(blueprint.model_dump(mode="json"), ensure_ascii=False)
    assert "每日研究摘要" not in encoded
    assert "分配任务并汇总结果" not in encoded
    assert "总控" not in encoded
    saved = [
        event for event in service.ledger.read_all() if event["kind"] == "team_blueprint_saved"
    ]
    assert saved[-1]["payload"]["blueprint_sha256"] == blueprint.blueprint_sha256

    archived = service.archive_team_blueprint(
        blueprint.blueprint_id,
        TeamBlueprintArchiveRequest(confirmed=True),
    )
    assert archived.archived_at is not None
    assert service.list_team_blueprints() == []
    assert (
        service.list_team_blueprints(include_archived=True)[0].blueprint_id
        == blueprint.blueprint_id
    )
    assert service.ledger.read_all()[-1]["kind"] == "team_blueprint_archived"


def test_task_template_is_private_hash_ledgered_and_has_no_execution_side_effects(console_env):
    settings, service, aion, paperclip = console_env
    objective = "每个工作日整理支持工单，但不要发送回复，必须由人工确认后执行。"
    template = service.save_task_template(
        TaskTemplateSaveRequest(
            name="支持工单晨报",
            objective=objective,
            confirmed=True,
        )
    )
    assert template.objective == objective
    assert service.list_task_templates()[0].template_id == template.template_id
    assert service.dashboard()["task_templates"][0]["template_id"] == template.template_id
    template_path = settings.console.state_dir / "task-templates" / f"{template.template_id}.json"
    assert template_path.stat().st_mode & 0o777 == 0o600
    ledger_text = json.dumps(service.ledger.read_all(), ensure_ascii=False)
    assert objective not in ledger_text
    assert "支持工单晨报" not in ledger_text
    saved = [event for event in service.ledger.read_all() if event["kind"] == "task_template_saved"]
    assert saved[-1]["payload"]["template_sha256"] == template.template_sha256
    assert aion.dispatched == 0
    assert paperclip.created == 0

    archived = service.archive_task_template(
        template.template_id,
        TaskTemplateArchiveRequest(confirmed=True),
    )
    assert archived.archived_at is not None
    assert service.list_task_templates() == []
    assert service.list_task_templates(include_archived=True)[0].template_id == template.template_id
    assert service.ledger.read_all()[-1]["kind"] == "task_template_archived"


def test_workspace_conversation_history_restores_latest_revision_and_binds_template_source(
    console_env,
):
    _, service, aion, paperclip = console_env
    requested = service.request_plan(PlanRequest(objective="每周整理客户项目并提出下一步"))
    parent = service.draft_plan(requested.plan_id)
    revision = service.request_plan_revision(
        parent.plan_id,
        RevisePlanRequest(instruction="增加证据复核步骤，但不要启动执行。"),
    )
    current = service.draft_plan(revision.plan_id)
    dispatched_before = aion.dispatched
    issues_before = paperclip.created

    conversations = service.list_workspace_conversations()
    conversation = next(row for row in conversations if row.conversation_id == parent.plan_id)
    assert conversation.current_plan_id == current.plan_id
    assert conversation.current_plan_sha256 == current.plan_sha256
    assert conversation.version_count == 2
    assert conversation.template_source_available is True
    assert service.dashboard()["workspace_conversations"][0]["current_plan_id"] == current.plan_id

    template = service.save_task_template_from_plan(
        current.plan_id,
        TaskTemplateFromPlanRequest(name="客户项目周报", confirmed=True),
    )
    assert template.objective == current.objective
    assert template.source_plan_id == current.plan_id
    assert template.source_plan_sha256 == current.plan_sha256
    assert aion.dispatched == dispatched_before
    assert paperclip.created == issues_before
    event = service.ledger.read_all()[-1]
    assert event["kind"] == "task_template_saved"
    assert event["payload"]["source_plan_id"] == current.plan_id
    assert event["payload"]["source_plan_sha256"] == current.plan_sha256


def test_workspace_conversation_http_routes_require_confirmed_csrf_write(
    console_env,
    monkeypatch,
):
    settings, service, _, _ = console_env
    ready = service.draft_plan(
        service.request_plan(PlanRequest(objective="保存历史规划模板")).plan_id
    )
    monkeypatch.setattr(service, "acquire_instance_lease", lambda: True)
    monkeypatch.setattr(service, "recover_startup", lambda: {})
    monkeypatch.setattr(service, "release_instance_lease", lambda: None)
    app = create_app(settings, service=service)
    csrf = app.state.csrf_token

    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        history = client.get("/api/v1/workspace-conversations")
        denied = client.post(
            f"/api/v1/plans/{ready.plan_id}/task-template",
            json={"name": "历史模板", "confirmed": True},
        )
        accepted = client.post(
            f"/api/v1/plans/{ready.plan_id}/task-template",
            json={"name": "历史模板", "confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )

    assert history.status_code == 200
    assert history.json()[0]["current_plan_id"] == ready.plan_id
    assert denied.status_code == 403
    assert accepted.status_code == 201
    assert accepted.json()["source_plan_id"] == ready.plan_id
    assert accepted.json()["source_plan_sha256"] == ready.plan_sha256


def test_ended_work_is_a_repeatable_blueprint_and_preparing_it_has_no_execution_side_effects(
    console_env,
):
    _, service, aion, paperclip = console_env
    running = _running_aion_plan(service)
    ended = service.refresh_execution(running.plan_id)
    dispatched_before = aion.dispatched
    issues_before = paperclip.created

    works = service.list_repeatable_works()
    selected = next(row for row in works if row.source_plan_id == ended.plan_id)
    assert selected.work_id == ended.plan_id
    assert selected.source_plan_sha256 == ended.plan_sha256
    assert selected.agent_count == 2
    assert selected.last_status == "completed_unverified"
    assert service.dashboard()["repeatable_works"][0]["source_plan_id"] == ended.plan_id

    prepared = service.prepare_plan_rerun(
        selected.source_plan_id,
        RerunPlanRequest(confirmed=True),
    )
    assert prepared.status == "ready"
    assert prepared.parent_plan_id == ended.plan_id
    assert prepared.execution is None
    assert aion.dispatched == dispatched_before
    assert paperclip.created == issues_before


def test_workspace_memory_is_private_immutable_and_only_approved_versions_reach_planning(
    console_env,
):
    settings, service, aion, _ = console_env
    content = "## Proven process\nAlways verify citations before publishing."
    candidate = service.create_workspace_memory_candidate(
        WorkspaceMemoryCandidateRequest(
            kind="process",
            title="Citation review",
            content=content,
            tags=["review", "evidence"],
            confirmed=True,
        )
    )

    assert candidate.state == "candidate"
    assert candidate.active is False
    document = settings.console.state_dir / "workspace-memory" / candidate.relative_path
    metadata = (
        settings.console.state_dir
        / "workspace-memory"
        / ".opswitness"
        / "versions"
        / f"{candidate.version_id}.json"
    )
    assert document.stat().st_mode & 0o777 == 0o600
    assert metadata.stat().st_mode & 0o777 == 0o600
    assert "opswitness_schema: 1" in document.read_text()
    assert content in document.read_text()
    assert content not in json.dumps(service.ledger.read_all(), ensure_ascii=False)

    without_memory = service.request_plan(PlanRequest(objective="候选记忆不能进入规划"))
    assert without_memory.memory_version_ids == []
    service.draft_plan(without_memory.plan_id)
    assert aion.memory_snapshot == []

    approved = service.approve_workspace_memory(
        candidate.version_id,
        WorkspaceMemoryDecisionRequest(reason="Reviewed by operator", confirmed=True),
    )
    assert approved.state == "approved"
    assert approved.active is True
    requested = service.request_plan(PlanRequest(objective="使用已批准流程记忆"))
    assert requested.memory_version_ids == [candidate.version_id]
    assert requested.memory_snapshot_sha256 is not None
    ready = service.draft_plan(requested.plan_id)
    assert aion.memory_snapshot[0]["version_id"] == candidate.version_id
    assert aion.memory_snapshot[0]["content"] == content
    assert ready.plan_sha256 is not None

    service.revoke_workspace_memory(
        candidate.version_id,
        WorkspaceMemoryDecisionRequest(reason="No longer applicable", confirmed=True),
    )
    with pytest.raises(ConsoleConflict, match="memory changed"):
        service.confirm_plan(
            ready.plan_id,
            ConfirmRequest(plan_sha256=ready.plan_sha256, confirmed=True),
        )


def test_workspace_memory_revision_supersedes_and_rollback_restores_an_exact_version(console_env):
    _, service, _, _ = console_env
    first = service.create_workspace_memory_candidate(
        WorkspaceMemoryCandidateRequest(
            kind="knowledge",
            title="Research standard",
            content="Use primary sources and keep citations.",
            confirmed=True,
        )
    )
    service.approve_workspace_memory(
        first.version_id,
        WorkspaceMemoryDecisionRequest(confirmed=True),
    )
    second = service.create_workspace_memory_candidate(
        WorkspaceMemoryCandidateRequest(
            kind="knowledge",
            title="Research standard",
            content="Use primary sources, record dates, and keep citations.",
            supersedes_version_id=first.version_id,
            confirmed=True,
        )
    )
    assert second.memory_id == first.memory_id
    assert second.version_number == 2
    service.approve_workspace_memory(
        second.version_id,
        WorkspaceMemoryDecisionRequest(reason="Expanded review rule", confirmed=True),
    )
    assert service.get_workspace_memory(first.version_id).state == "superseded"
    assert service.get_workspace_memory(second.version_id).active is True

    restored = service.rollback_workspace_memory(
        first.version_id,
        WorkspaceMemoryRollbackRequest(reason="Restore the simpler verified rule", confirmed=True),
    )
    assert restored.state == "approved"
    assert restored.active is True
    assert service.get_workspace_memory(second.version_id).state == "superseded"


def test_process_memory_proposal_is_deterministic_and_stays_candidate(console_env):
    _, service, aion, _ = console_env
    running = _running_aion_plan(service)
    ended = service.refresh_execution(running.plan_id)
    generated_before = aion.generated
    proposed = service.propose_process_memory(
        ended.plan_id,
        ProcessMemoryProposalRequest(title="Weekly research process", confirmed=True),
    )

    assert proposed.kind == "process"
    assert proposed.state == "candidate"
    assert proposed.source_plan_id == ended.plan_id
    assert ended.plan_sha256 in proposed.content
    assert "## Team structure" in proposed.content
    assert "## Repeatable stages" in proposed.content
    assert aion.generated == generated_before


def test_blueprint_is_safe_planning_input_and_hash_bound(console_env):
    _, service, aion, _ = console_env
    source = service.draft_plan(service.request_plan(PlanRequest(objective="蓝图来源")).plan_id)
    blueprint = service.save_team_blueprint(
        TeamBlueprintSaveRequest(
            source_plan_id=source.plan_id,
            name="可复用研究团队",
            confirmed=True,
        )
    )
    planned = service.request_plan(
        PlanRequest(objective="用蓝图规划新任务", blueprint_id=blueprint.blueprint_id)
    )
    ready = service.draft_plan(planned.plan_id)
    assert ready.source_blueprint_id == blueprint.blueprint_id
    assert ready.source_blueprint_sha256 == blueprint.blueprint_sha256
    assert aion.blueprint is not None
    assert aion.blueprint["blueprint_sha256"] == blueprint.blueprint_sha256
    assert "responsibility" not in json.dumps(aion.blueprint, ensure_ascii=False)

    def alter_provenance(current):
        current.source_blueprint_sha256 = "0" * 64
        return current

    service.store.mutate(ready.plan_id, alter_provenance)
    with pytest.raises(ConsoleConflict, match="inputs changed"):
        service.confirm_plan(
            ready.plan_id,
            ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
        )


def test_runtime_revision_is_immutable_validated_and_has_no_dispatch_side_effect(console_env):
    _, service, aion, paperclip = console_env
    service.runtime_capabilities = lambda: [  # type: ignore[method-assign]
        {
            "runtime": "codex_cli",
            "available": True,
            "models": [
                {"id": "default"},
                {"id": "gpt-test-pinned"},
            ],
        },
        {
            "runtime": "claude_code",
            "available": True,
            "models": [{"id": "default"}],
        },
        {
            "runtime": "aion_cli",
            "available": False,
            "models": [{"id": "default"}],
        },
    ]
    parent = service.draft_plan(service.request_plan(PlanRequest(objective="调整运行时")).plan_id)
    assert parent.plan is not None
    child = service.revise_plan_runtimes(
        parent.plan_id,
        RuntimeRevisionRequest(
            assignments=[
                {
                    "agent_name": "总控",
                    "runtime": "codex_cli",
                    "model": "gpt-test-pinned",
                },
                {"agent_name": "复核", "runtime": "codex_cli", "model": "default"},
            ],
            confirmed=True,
        ),
    )
    assert child.parent_plan_id == parent.plan_id
    assert child.plan_sha256 != parent.plan_sha256
    assert parent.plan.agents[0].runtime == "claude_code"
    assert child.plan is not None and child.plan.agents[0].runtime == "codex_cli"
    assert child.plan.agents[0].model == "gpt-test-pinned"
    assert child.plan.agents[1].model == "default"
    assert child.plan.agents[0].runtime_reason.startswith("由操作员")
    assert aion.dispatched == 0
    assert paperclip.created == 0
    assert service.ledger.read_all()[-1]["kind"] == "task_plan_runtime_revised"

    second = service.draft_plan(
        service.request_plan(PlanRequest(objective="拒绝不可用运行时")).plan_id
    )
    service.runtime_capabilities = lambda: [  # type: ignore[method-assign]
        {"runtime": "codex_cli", "available": True, "models": [{"id": "default"}]},
        {"runtime": "claude_code", "available": False, "models": [{"id": "default"}]},
        {"runtime": "aion_cli", "available": False, "models": [{"id": "default"}]},
    ]
    with pytest.raises(ConsoleConflict, match="unavailable"):
        service.revise_plan_runtimes(
            second.plan_id,
            RuntimeRevisionRequest(
                assignments=[
                    {"agent_name": "总控", "runtime": "claude_code"},
                    {"agent_name": "复核", "runtime": "codex_cli"},
                ],
                confirmed=True,
            ),
        )

    service.runtime_capabilities = lambda: [  # type: ignore[method-assign]
        {"runtime": "codex_cli", "available": True, "models": [{"id": "default"}]},
        {"runtime": "claude_code", "available": True, "models": [{"id": "default"}]},
        {"runtime": "aion_cli", "available": False, "models": [{"id": "default"}]},
    ]
    third = service.draft_plan(
        service.request_plan(PlanRequest(objective="拒绝未公布模型")).plan_id
    )
    with pytest.raises(ConsoleConflict, match="model is unavailable"):
        service.revise_plan_runtimes(
            third.plan_id,
            RuntimeRevisionRequest(
                assignments=[
                    {
                        "agent_name": "总控",
                        "runtime": "codex_cli",
                        "model": "invented-model",
                    },
                    {"agent_name": "复核", "runtime": "codex_cli", "model": "default"},
                ],
                confirmed=True,
            ),
        )
    assert aion.dispatched == 0
    assert paperclip.created == 0


def test_execution_profile_revision_pins_exact_models_in_an_immutable_child(console_env):
    _, service, aion, paperclip = console_env
    capabilities = [
        {
            "runtime": "claude_code",
            "available": True,
            "models": [
                {"id": "default"},
                {"id": "claude-haiku-test"},
                {"id": "claude-sonnet-test"},
                {"id": "claude-opus-test"},
            ],
        },
        {
            "runtime": "codex_cli",
            "available": True,
            "models": [
                {"id": "default"},
                {"id": "gpt-mini-test"},
                {"id": "gpt-codex-test"},
                {"id": "gpt-pro-test"},
            ],
        },
        {
            "runtime": "aion_cli",
            "available": False,
            "models": [{"id": "default"}],
        },
    ]
    service.runtime_capabilities = lambda: capabilities  # type: ignore[method-assign]
    parent = service.draft_plan(
        service.request_plan(PlanRequest(objective="档位模型选择")).plan_id
    )
    assert parent.plan is not None
    assert parent.plan.execution_profile == ExecutionProfile.BALANCED
    assert [agent.model for agent in parent.plan.agents] == [
        "claude-sonnet-test",
        "gpt-codex-test",
    ]

    child = service.revise_plan_execution_profile(
        parent.plan_id,
        ExecutionProfileRevisionRequest(
            execution_profile=ExecutionProfile.FAST,
            confirmed=True,
        ),
    )
    assert child.status == "ready"
    assert child.parent_plan_id == parent.plan_id
    assert child.parent_plan_sha256 == parent.plan_sha256
    assert child.plan_sha256 != parent.plan_sha256
    assert child.plan is not None
    assert child.plan.execution_profile == ExecutionProfile.FAST
    assert [agent.model for agent in child.plan.agents] == [
        "claude-haiku-test",
        "gpt-mini-test",
    ]
    assert parent.plan.execution_profile == ExecutionProfile.BALANCED
    assert [agent.model for agent in parent.plan.agents] == [
        "claude-sonnet-test",
        "gpt-codex-test",
    ]
    assert all("所选模型已按本机能力表写入方案" in agent.runtime_reason for agent in child.plan.agents)
    assert aion.dispatched == 0
    assert paperclip.created == 0
    event = service.ledger.read_all()[-1]
    assert event["kind"] == "task_plan_execution_profile_revised"
    assert event["payload"]["execution_profile"] == "fast"
    assert event["payload"]["plan_sha256"] == child.plan_sha256

    unavailable = service.draft_plan(
        service.request_plan(PlanRequest(objective="档位拒绝不可用运行时")).plan_id
    )
    service.runtime_capabilities = lambda: [  # type: ignore[method-assign]
        {**capabilities[0], "available": False},
        capabilities[1],
        capabilities[2],
    ]
    with pytest.raises(ConsoleConflict, match="runtime is unavailable"):
        service.revise_plan_execution_profile(
            unavailable.plan_id,
            ExecutionProfileRevisionRequest(
                execution_profile=ExecutionProfile.DEEP,
                confirmed=True,
            ),
        )
    assert aion.dispatched == 0
    assert paperclip.created == 0


def test_execution_profile_http_facade_requires_csrf_and_confirmation(
    console_env, monkeypatch
):
    settings, service, aion, paperclip = console_env
    parent = service.draft_plan(
        service.request_plan(PlanRequest(objective="HTTP 执行档位")).plan_id
    )
    monkeypatch.setattr(service, "acquire_instance_lease", lambda: True)
    monkeypatch.setattr(service, "recover_startup", lambda: {})
    monkeypatch.setattr(service, "release_instance_lease", lambda: None)
    app = create_app(settings, service=service)
    csrf = app.state.csrf_token
    path = f"/api/v1/plans/{parent.plan_id}/execution-profile"
    body = {"execution_profile": "deep", "confirmed": True}

    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        assert client.post(path, json=body).status_code == 403
        assert (
            client.post(
                path,
                json={**body, "confirmed": False},
                headers={"X-QD-CSRF": csrf},
            ).status_code
            == 422
        )
        accepted = client.post(path, json=body, headers={"X-QD-CSRF": csrf})
        assert accepted.status_code == 201
        payload = accepted.json()
        assert payload["parent_plan_id"] == parent.plan_id
        assert payload["plan"]["execution_profile"] == "deep"
        assert all(agent["model"] for agent in payload["plan"]["agents"])

    assert aion.dispatched == 0
    assert paperclip.created == 0


def test_runtime_and_team_blueprint_http_facades_require_csrf_and_confirmation(
    console_env, monkeypatch
):
    settings, service, _, _ = console_env
    parent = service.draft_plan(service.request_plan(PlanRequest(objective="HTTP 新接口")).plan_id)
    monkeypatch.setattr(service, "acquire_instance_lease", lambda: True)
    monkeypatch.setattr(service, "recover_startup", lambda: {})
    monkeypatch.setattr(service, "release_instance_lease", lambda: None)
    app = create_app(settings, service=service)
    csrf = app.state.csrf_token
    runtimes_path = f"/api/v1/plans/{parent.plan_id}/runtimes"
    runtime_body = {
        "confirmed": True,
        "assignments": [
            {"agent_name": "总控", "runtime": "codex_cli", "model": "default"},
            {"agent_name": "复核", "runtime": "codex_cli", "model": "default"},
        ],
    }
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        assert client.post(runtimes_path, json=runtime_body).status_code == 403
        assert (
            client.post(
                runtimes_path,
                json={**runtime_body, "confirmed": False},
                headers={"X-QD-CSRF": csrf},
            ).status_code
            == 422
        )
        child = client.post(
            runtimes_path,
            json=runtime_body,
            headers={"X-QD-CSRF": csrf},
        )
        assert child.status_code == 201
        assert child.json()["parent_plan_id"] == parent.plan_id

        blueprint_body = {
            "source_plan_id": child.json()["plan_id"],
            "name": "HTTP 研究团队",
            "confirmed": True,
        }
        assert client.post("/api/v1/team-blueprints", json=blueprint_body).status_code == 403
        saved = client.post(
            "/api/v1/team-blueprints",
            json=blueprint_body,
            headers={"X-QD-CSRF": csrf},
        )
        assert saved.status_code == 201
        blueprint_id = saved.json()["blueprint_id"]
        archive_path = f"/api/v1/team-blueprints/{blueprint_id}/archive"
        assert client.post(archive_path, json={"confirmed": True}).status_code == 403
        assert (
            client.post(
                archive_path,
                json={"confirmed": False},
                headers={"X-QD-CSRF": csrf},
            ).status_code
            == 422
        )
        archived = client.post(
            archive_path,
            json={"confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        assert archived.status_code == 200
        assert archived.json()["archived_at"] is not None


def test_task_template_http_facade_requires_csrf_and_confirmation(console_env, monkeypatch):
    settings, service, aion, paperclip = console_env
    monkeypatch.setattr(service, "acquire_instance_lease", lambda: True)
    monkeypatch.setattr(service, "recover_startup", lambda: {})
    monkeypatch.setattr(service, "release_instance_lease", lambda: None)
    app = create_app(settings, service=service)
    csrf = app.state.csrf_token
    body = {
        "name": "每周项目复盘",
        "objective": "整理每周项目进展、风险、负责人和下一步，不要自动发送。",
        "confirmed": True,
    }
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        assert client.post("/api/v1/task-templates", json=body).status_code == 403
        assert (
            client.post(
                "/api/v1/task-templates",
                json={**body, "confirmed": False},
                headers={"X-QD-CSRF": csrf},
            ).status_code
            == 422
        )
        saved = client.post(
            "/api/v1/task-templates",
            json=body,
            headers={"X-QD-CSRF": csrf},
        )
        assert saved.status_code == 201
        template_id = saved.json()["template_id"]
        rows = client.get("/api/v1/task-templates")
        assert rows.status_code == 200
        assert rows.json()[0]["template_id"] == template_id
        archive_path = f"/api/v1/task-templates/{template_id}/archive"
        assert client.post(archive_path, json={"confirmed": True}).status_code == 403
        assert (
            client.post(
                archive_path,
                json={"confirmed": False},
                headers={"X-QD-CSRF": csrf},
            ).status_code
            == 422
        )
        archived = client.post(
            archive_path,
            json={"confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        assert archived.status_code == 200
        assert archived.json()["archived_at"] is not None
    assert aion.dispatched == 0
    assert paperclip.created == 0


def test_workspace_memory_http_facade_requires_csrf_confirmation_and_keeps_body_on_demand(
    console_env,
    monkeypatch,
):
    settings, service, _, _ = console_env
    monkeypatch.setattr(service, "acquire_instance_lease", lambda: True)
    monkeypatch.setattr(service, "recover_startup", lambda: {})
    monkeypatch.setattr(service, "release_instance_lease", lambda: None)
    app = create_app(settings, service=service)
    csrf = app.state.csrf_token
    body = {
        "kind": "process",
        "title": "Weekly review",
        "content": "Review evidence, unresolved risks, and next actions.",
        "tags": ["weekly"],
        "confirmed": True,
    }
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        assert client.post("/api/v1/workspace-memory/candidates", json=body).status_code == 403
        assert (
            client.post(
                "/api/v1/workspace-memory/candidates",
                json={**body, "confirmed": False},
                headers={"X-QD-CSRF": csrf},
            ).status_code
            == 422
        )
        created = client.post(
            "/api/v1/workspace-memory/candidates",
            json=body,
            headers={"X-QD-CSRF": csrf},
        )
        assert created.status_code == 201
        version_id = created.json()["version_id"]
        approved = client.post(
            f"/api/v1/workspace-memory/{version_id}/approve",
            json={"reason": "Operator reviewed", "confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        assert approved.status_code == 200
        assert approved.json()["active"] is True
        listed = client.get("/api/v1/workspace-memory", params={"query": "unresolved"})
        assert listed.status_code == 200
        assert listed.json()[0]["version_id"] == version_id
        detail = client.get(f"/api/v1/workspace-memory/{version_id}")
        assert detail.status_code == 200
        assert detail.json()["content"] == body["content"]


def test_member_observations_are_safe_signals_not_outcome_evidence(console_env, monkeypatch):
    _, service, aion, _ = console_env
    ready = service.draft_plan(service.request_plan(PlanRequest(objective="成员观察状态")).plan_id)
    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
    )
    running = service.dispatch_plan(ready.plan_id)
    assert running.execution is not None
    monkeypatch.setattr(
        aion,
        "execution_snapshot",
        lambda *args, **kwargs: {
            "status": "running",
            "progress": {
                "available": True,
                "observed_at": "2026-07-14T08:01:00+00:00",
                "active_members": [
                    {
                        "agent_name": "总控",
                        "state": "running",
                        "started_at": "2026-07-14T08:00:00+00:00",
                        "elapsed_seconds": 60,
                        "slow": False,
                    }
                ],
                "recent_activity": [
                    {
                        "activity_id": "tool-1",
                        "agent_name": "总控",
                        "kind": "tool_call",
                        "status": "completed",
                        "tool_name": "mcp__opswitness__qd_fleet_status",
                        "observed_at": "2026-07-14T08:00:30+00:00",
                        "count": 1,
                    }
                ],
            },
            "member_observations": [
                {
                    "agent_name": "总控",
                    "state": "response_observed",
                    "observed_at": "2026-07-14T08:00:00+00:00",
                    "source": "adapter",
                },
                {"agent_name": "复核", "state": "unavailable", "source": "unavailable"},
            ],
        },
    )
    refreshed = service.refresh_execution(ready.plan_id)
    assert refreshed.status == "running"
    assert refreshed.execution is not None
    assert [item.state for item in refreshed.execution.member_observations] == [
        "response_observed",
        "unavailable",
    ]
    assert refreshed.execution.outcome_verified is False
    assert refreshed.execution.progress is not None
    assert refreshed.execution.progress.active_members[0].agent_name == "总控"
    rendered = json.dumps(refreshed.execution.progress.model_dump(mode="json"), ensure_ascii=False)
    assert "message" not in rendered
    assert "raw_input" not in rendered
    assert "raw_output" not in rendered
    assert "percent" not in rendered


def test_completed_execution_backfills_progress_without_rewriting_terminal_state(console_env):
    _, service, aion, _ = console_env
    ready = service.draft_plan(service.request_plan(PlanRequest(objective="终态进度回填")).plan_id)
    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
    )
    service.dispatch_plan(ready.plan_id)

    def mark_completed(current):
        current.status = "completed_unverified"
        assert current.execution is not None
        current.execution.status = "completed_unverified"
        current.execution.progress = None
        return current

    service.store.mutate(ready.plan_id, mark_completed)
    aion.snapshot = {
        "status": "queued",
        "progress": {
            "available": True,
            "observed_at": "2026-07-15T22:01:00+00:00",
            "stage_history_recovered": True,
            "stage_mapping_version": 1,
            "active_members": [],
            "recent_activity": [
                {
                    "activity_id": "response-1",
                    "agent_name": "总控",
                    "kind": "response",
                    "status": "observed",
                    "observed_at": "2026-07-15T22:00:00+00:00",
                    "count": 1,
                }
            ],
        },
        "member_observations": [
            {
                "agent_name": "总控",
                "state": "response_observed",
                "observed_at": "2026-07-15T22:00:00+00:00",
                "source": "adapter",
            }
        ],
    }
    event_count = len(service.ledger.read_all())

    backfilled = service.get_plan(ready.plan_id)

    assert backfilled.status == "completed_unverified"
    assert backfilled.execution is not None
    assert backfilled.execution.status == "completed_unverified"
    assert backfilled.execution.progress is not None
    assert backfilled.execution.progress.recent_activity[0].activity_id == "response-1"
    assert backfilled.execution.progress.stage_history_recovered is True
    assert backfilled.execution.progress.stage_mapping_version == 1
    assert len(service.ledger.read_all()) == event_count


def test_completed_aion_execution_with_unfinished_stages_is_reconciled_locally(
    console_env, monkeypatch
):
    _, service, aion, _ = console_env
    ready = service.draft_plan(service.request_plan(PlanRequest(objective="终态阶段核对")).plan_id)
    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
    )
    service.dispatch_plan(ready.plan_id)

    def mark_completed(current):
        assert current.execution is not None
        current.status = "completed_unverified"
        current.execution.status = "completed_unverified"
        current.execution.finish_event_recorded = True
        current.execution.finished_at = "2026-07-16T08:38:52+00:00"
        current.execution.progress = ExecutionProgress.model_validate(
            {
                "available": True,
                "stage_mapping_version": 1,
                "stages": [
                    {
                        "stage_order": 1,
                        "agent_name": "总控",
                        "status": "completed",
                        "source": "aion_team_task",
                        "task_id": "task-stage-1",
                    },
                    {
                        "stage_order": 2,
                        "agent_name": "复核",
                        "status": "blocked",
                        "source": "aion_team_task",
                        "task_id": "task-stage-2",
                        "blocked_by": [1],
                    },
                ],
            }
        )
        return current

    service.store.mutate(ready.plan_id, mark_completed)

    def remote_must_not_be_called(*args, **kwargs):
        del args, kwargs
        pytest.fail("local terminal stage reconciliation must not query AionUi")

    monkeypatch.setattr(aion, "execution_snapshot", remote_must_not_be_called)

    reconciled = service.get_plan(ready.plan_id)

    assert reconciled.status == "failed"
    assert reconciled.execution is not None
    assert reconciled.execution.status == "failed"
    assert reconciled.execution.error == (
        "Execution ended before completing plan stage 2. "
        "Continue this Work to finish the remaining stages."
    )
    correction = service.ledger.read_all()[-1]
    assert correction["kind"] == "task_execution_failed"
    assert correction["payload"]["reason"] == "aion_terminal_with_unfinished_stages"
    assert correction["payload"]["unfinished_stage_orders"] == [2]


def test_dashboard_reconciles_terminal_aion_false_completion(console_env, monkeypatch):
    _, service, aion, _ = console_env
    ready = service.draft_plan(service.request_plan(PlanRequest(objective="列表终态阶段核对")).plan_id)
    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
    )
    service.dispatch_plan(ready.plan_id)

    def mark_completed(current):
        assert current.execution is not None
        current.status = "completed_unverified"
        current.execution.status = "completed_unverified"
        current.execution.finish_event_recorded = True
        current.execution.finished_at = "2026-07-16T08:38:52+00:00"
        current.execution.progress = ExecutionProgress.model_validate(
            {
                "available": True,
                "stage_mapping_version": 1,
                "stages": [
                    {
                        "stage_order": 1,
                        "agent_name": "总控",
                        "status": "completed",
                        "source": "aion_team_task",
                        "task_id": "task-stage-1",
                    },
                    {
                        "stage_order": 2,
                        "agent_name": "复核",
                        "status": "pending",
                        "source": "aion_team_task",
                        "task_id": "task-stage-2",
                        "blocked_by": [1],
                    },
                ],
            }
        )
        return current

    service.store.mutate(ready.plan_id, mark_completed)

    def remote_must_not_be_called(*args, **kwargs):
        del args, kwargs
        pytest.fail("dashboard reconciliation must not query AionUi")

    monkeypatch.setattr(aion, "execution_snapshot", remote_must_not_be_called)

    dashboard = service.dashboard()
    reconciled = next(row for row in dashboard["plans"] if row["plan_id"] == ready.plan_id)

    assert reconciled["status"] == "failed"
    assert reconciled["execution"]["status"] == "failed"
    assert reconciled["execution"]["error"] == (
        "Execution ended before completing plan stage 2. "
        "Continue this Work to finish the remaining stages."
    )
    assert service.ledger.read_all()[-1]["payload"]["unfinished_stage_orders"] == [2]
    run = next(row for row in dashboard["task_runs"] if row["plan_id"] == ready.plan_id)
    assert run["finished_at"] == "2026-07-16T08:38:52+00:00"


def test_aion_terminal_snapshot_with_unfinished_stages_has_stable_failure_detail(console_env):
    _, service, aion, _ = console_env
    ready = service.draft_plan(service.request_plan(PlanRequest(objective="远端阶段核对")).plan_id)
    service.confirm_plan(
        ready.plan_id,
        ConfirmRequest(plan_sha256=str(ready.plan_sha256), confirmed=True),
    )
    service.dispatch_plan(ready.plan_id)
    aion.snapshot = {"status": "failed", "unfinished_stage_orders": [2]}

    failed = service.refresh_execution(ready.plan_id)

    assert failed.status == "failed"
    assert failed.execution is not None
    assert failed.execution.error == (
        "Execution ended before completing plan stage 2. "
        "Continue this Work to finish the remaining stages."
    )


def test_aionui_local_provider_registration_uses_fixed_loopback_and_placeholder(monkeypatch):
    client = AionUiClient(Settings().console)
    calls = []

    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if method == "GET":
            return []
        return {"id": "opswitness-ollama"}

    monkeypatch.setattr(client, "_request", request)
    provider_id = client.ensure_local_provider("ollama", ["qwen3:8b"])

    assert provider_id == "opswitness-ollama"
    assert calls[0][:2] == ("GET", "/api/providers")
    method, path, kwargs = calls[1]
    assert (method, path) == ("POST", "/api/providers")
    assert kwargs["json"] == {
        "id": "opswitness-ollama",
        "platform": "custom",
        "name": "Ollama (OpsWitness)",
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key": "ollama",
        "models": ["qwen3:8b"],
        "enabled": True,
        "model_protocols": {"qwen3:8b": "openai"},
    }
    assert "https://" not in json.dumps(kwargs)


def test_local_provider_connection_is_confirmed_audited_and_runtime_gated(console_env):
    _, service, aion, _ = console_env
    with pytest.raises(ValueError, match="explicit confirmation"):
        ProviderConnectionRequest(method="local")

    connected = []
    service._provider_local_connect = lambda provider: connected.append(provider) or True
    requested = service.request_provider_connection(
        "ollama",
        ProviderConnectionRequest(method="local", confirmed=True),
    )
    ready = service.run_provider_connection(requested.job_id)

    assert ready.status == "ready"
    assert connected == ["ollama"]
    events = service.ledger.read_all()
    assert events[0]["payload"] == {
        "schema_version": 2,
        "provider": "ollama",
        "method": "local",
        "flow": "loopback_local_provider",
    }
    assert "api_key" not in json.dumps(events)
    assert service.provider_statuses()["ollama"]["runtime_ready"] is True
    assert (
        next(item for item in service.runtime_capabilities() if item["runtime"] == "aion_cli")[
            "available"
        ]
        is True
    )

    aion.local_providers.clear()
    assert service.provider_statuses()["ollama"]["runtime_ready"] is False


def test_runtime_capabilities_publish_only_validated_model_metadata(console_env, monkeypatch):
    _, service, _, _ = console_env
    monkeypatch.setattr(
        service,
        "_codex_model_options",
        lambda: [
            {
                "id": "gpt-test-exact",
                "label": "GPT Test Exact",
                "description": "Local Codex metadata cache",
                "pinning": "exact",
            }
        ],
    )
    capabilities = {row["runtime"]: row for row in service.runtime_capabilities()}

    assert capabilities["claude_code"]["models"] == [
        {
            "id": "default",
            "label": "运行时默认（不固定版本）",
            "description": "由运行时在会话启动时选择，可能随账号或适配器更新而变化。",
            "pinning": "default",
        },
        {
            "id": "claude-fable-5[1m]",
            "label": "Fable 5",
            "description": "Exact Fable 5 model",
            "pinning": "exact",
        },
        {
            "id": "sonnet",
            "label": "Sonnet",
            "description": "Rolling Sonnet alias",
            "pinning": "alias",
        },
    ]
    assert capabilities["codex_cli"]["models"][1]["id"] == "gpt-test-exact"
    assert capabilities["aion_cli"]["models"][1] == {
        "id": "test-local-model",
        "label": "test-local-model",
        "description": "由 Ollama 本机服务公布",
        "pinning": "exact",
    }
    serialized = json.dumps(capabilities, ensure_ascii=False)
    assert "api_key" not in serialized
    assert "env_override" not in serialized
