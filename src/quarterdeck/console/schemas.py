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
        if self.execution_mode == "workflow" and not self.workflow_id:
            raise ValueError("workflow execution requires workflow_id")
        if self.execution_mode == "aion_team" and self.workflow_id is not None:
            raise ValueError("aion_team execution cannot carry workflow_id")
        return self


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=3, max_length=2000)
    constraints: str = Field(default="", max_length=2000)
    workspace: str = Field(default="", max_length=1024)
    preferred_cadence: Literal["once", "daily", "weekdays", "weekly", "manual"] = "once"


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed: Literal[True]


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
    plan: TaskPlan | None = None
    plan_sha256: str | None = None
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
