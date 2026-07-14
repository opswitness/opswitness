"""Strict public schemas for planning, confirmation, and console state."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class RuntimeName(StrEnum):
    CLAUDE_CODE = "claude_code"
    CODEX_CLI = "codex_cli"
    AION_CLI = "aion_cli"


class AgentRole(StrEnum):
    LEAD = "lead"
    RESEARCHER = "researcher"
    OPERATOR = "operator"
    REVIEWER = "reviewer"
    REPORTER = "reporter"
    SPECIALIST = "specialist"


class PlannedAgent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    role: AgentRole
    responsibility: str = Field(min_length=1, max_length=600)
    runtime: RuntimeName
    reports_to: str | None = Field(default=None, min_length=1, max_length=80)


class TaskStage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=1, le=20)
    title: str = Field(min_length=1, max_length=100)
    owner: str = Field(min_length=1, max_length=80)
    outcome: str = Field(min_length=1, max_length=500)
    checkpoint: bool = False


class TaskCadence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["once", "daily", "weekdays", "weekly", "manual"]
    timezone: str = Field(default="America/Los_Angeles", min_length=1, max_length=80)
    local_time: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    update_interval: str = Field(min_length=1, max_length=160)


class TaskPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=1200)
    execution_mode: Literal["aion_team", "workflow"]
    workflow_id: str | None = Field(default=None, min_length=1, max_length=100)
    agents: list[PlannedAgent] = Field(min_length=1, max_length=5)
    stages: list[TaskStage] = Field(min_length=1, max_length=8)
    cadence: TaskCadence
    tools: list[str] = Field(default_factory=list, max_length=12)
    approvals: list[str] = Field(default_factory=list, max_length=12)
    artifacts: list[str] = Field(default_factory=list, max_length=12)
    risks: list[str] = Field(default_factory=list, max_length=12)
    estimated_duration_minutes: int = Field(ge=1, le=10080)
    update_policy: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_architecture(self) -> "TaskPlan":
        leaders = [agent for agent in self.agents if agent.role == AgentRole.LEAD]
        if len(leaders) != 1:
            raise ValueError("a plan must contain exactly one lead agent")
        names = [agent.name.casefold() for agent in self.agents]
        if len(names) != len(set(names)):
            raise ValueError("agent names must be unique")
        owners = {agent.name.casefold() for agent in self.agents}
        if any(stage.owner.casefold() not in owners for stage in self.stages):
            raise ValueError("every stage owner must name a planned agent")
        orders = [stage.order for stage in self.stages]
        if sorted(orders) != list(range(1, len(orders) + 1)):
            raise ValueError("stage order must be contiguous from 1")
        explicit_reporting = any(agent.reports_to is not None for agent in self.agents)
        if explicit_reporting:
            leader = leaders[0]
            if leader.reports_to is not None:
                raise ValueError("the lead agent cannot report to another agent")
            exact_names = {agent.name for agent in self.agents}
            parents: dict[str, str] = {}
            for agent in self.agents:
                if agent is leader:
                    continue
                if agent.reports_to is None:
                    raise ValueError("every non-lead agent must have a direct manager")
                if agent.reports_to not in exact_names:
                    raise ValueError("every direct manager must name an exact planned agent")
                if agent.reports_to == agent.name:
                    raise ValueError("an agent cannot report to itself")
                parents[agent.name] = agent.reports_to
            for node_name in parents:
                seen = {node_name}
                cursor = node_name
                while cursor in parents:
                    cursor = parents[cursor]
                    if cursor in seen:
                        raise ValueError("agent reporting lines must be acyclic")
                    seen.add(cursor)
        if self.execution_mode == "workflow" and not self.workflow_id:
            raise ValueError("workflow execution requires workflow_id")
        if self.execution_mode == "aion_team" and self.workflow_id is not None:
            raise ValueError("aion_team execution cannot carry workflow_id")
        return self

    def effective_reporting_lines(self) -> dict[str, str | None]:
        """Return a complete tree while preserving legacy plans with no explicit hierarchy."""
        leader = next(agent for agent in self.agents if agent.role == AgentRole.LEAD)
        if not any(agent.reports_to is not None for agent in self.agents):
            return {
                agent.name: None if agent is leader else leader.name
                for agent in self.agents
            }
        return {agent.name: agent.reports_to for agent in self.agents}


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=3, max_length=2000)
    constraints: str = Field(default="", max_length=2000)
    workspace: str = Field(default="", max_length=1024)
    preferred_cadence: Literal["once", "daily", "weekdays", "weekly", "manual"] = "once"


class RevisePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(min_length=3, max_length=2000)

    @model_validator(mode="after")
    def normalize_instruction(self) -> RevisePlanRequest:
        self.instruction = self.instruction.strip()
        if len(self.instruction) < 3:
            raise ValueError("revision instruction must contain at least three characters")
        return self


class AgentReportingLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee: str = Field(min_length=1, max_length=80)
    reports_to: str | None = Field(default=None, min_length=1, max_length=80)


class OrganizationRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reporting_lines: list[AgentReportingLine] = Field(min_length=1, max_length=5)
    confirmed: Literal[True]

    @model_validator(mode="after")
    def validate_unique_employees(self) -> "OrganizationRevisionRequest":
        names = [line.employee.casefold() for line in self.reporting_lines]
        if len(names) != len(set(names)):
            raise ValueError("reporting lines must name each employee once")
        return self


class DeletePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: Literal[True]


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed: Literal[True]


class PlanningProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    phase: Literal[
        "queued",
        "preparing",
        "generating_plan",
        "validating",
        "repairing",
        "cleaning_up",
        "complete",
        "failed",
    ] = "queued"
    percent: int = Field(default=5, ge=0, le=100)
    started_at: str = Field(default_factory=utc_now)
    expected_seconds: int = Field(default=150, ge=1, le=600)
    timeout_seconds: int = Field(default=390, ge=1, le=1300)


class ExecutionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["aion_team", "workflow"]
    status: Literal[
        "dispatching",
        "queued",
        "running",
        "awaiting_approval",
        "completed_unverified",
        "failed",
    ] = "dispatching"
    paperclip_issue_id: str | None = None
    aion_team_id: str | None = None
    aion_team_run_id: str | None = None
    aion_conversation_ids: list[str] = Field(default_factory=list)
    workflow_run_id: str | None = None
    error: str | None = Field(default=None, max_length=500)
    dispatched_at: str | None = None
    finished_at: str | None = None
    outcome_verified: bool = False
    finish_event_recorded: bool = False


class PlanRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    plan_id: str
    status: Literal[
        "planning",
        "ready",
        "confirmed",
        "dispatching",
        "running",
        "awaiting_approval",
        "completed_unverified",
        "failed",
    ]
    objective: str
    constraints: str = ""
    workspace: str = ""
    preferred_cadence: Literal["once", "daily", "weekdays", "weekly", "manual"] = "once"
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    confirmed_at: str | None = None
    planning_progress: PlanningProgress | None = None
    plan: TaskPlan | None = None
    plan_sha256: str | None = None
    parent_plan_id: str | None = None
    parent_plan_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    revision_number: int = Field(default=1, ge=1, le=100)
    revision_instruction: str = Field(default="", max_length=2000)
    revision_instruction_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    error: str | None = Field(default=None, max_length=500)
    execution: ExecutionState | None = None


class MailSummaryJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: Literal["running", "ready", "failed"] = "running"
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    summary: str | None = Field(default=None, max_length=12000)
    message_count: int = 0
    error: str | None = Field(default=None, max_length=500)


class MailAuthorizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gmail_readonly_acknowledged: Literal[True]
    model_metadata_acknowledged: Literal[True]


class MailOAuthClientRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_json: SecretStr = Field(min_length=2, max_length=65_536)
    private_storage_acknowledged: Literal[True]


class MailDisableRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: Literal[True]


class MailAuthorizationJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: Literal["running", "ready", "failed"] = "running"
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    error: str | None = Field(default=None, max_length=500)


class ProviderConnectionJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    provider: Literal["openai", "anthropic"]
    status: Literal["running", "ready", "failed"] = "running"
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    error: str | None = Field(default=None, max_length=500)


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]
    decision_note: str = Field(default="", max_length=500)
    confirmed: Literal[True]


class TelegramConfigureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bot_token: SecretStr = Field(min_length=3, max_length=512)
    chat_id: SecretStr = Field(min_length=1, max_length=64)
    storage_acknowledged: Literal[True]
    replace_existing: bool = False


class TelegramActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: Literal[True]


JsonObject = dict[str, Any]
