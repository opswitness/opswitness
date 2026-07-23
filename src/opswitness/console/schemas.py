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


class ApprovalMode(StrEnum):
    """Execution-time approval policy, snapshotted when a plan is confirmed."""

    AUTOMATIC = "automatic"
    AUTOMATIC_SAFE = "automatic_safe"
    MANUAL_ALL = "manual_all"


class ExecutionProfile(StrEnum):
    """A reviewed latency/quality intent; exact models remain hash-bound per agent."""

    FAST = "fast"
    BALANCED = "balanced"
    DEEP = "deep"
    CUSTOM = "custom"


class PlannedAgent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    role: AgentRole
    responsibility: str = Field(min_length=1, max_length=600)
    runtime: RuntimeName
    model: str | None = Field(default=None, min_length=1, max_length=200)
    runtime_reason: str = Field(
        default="当前方案未记录运行时推荐理由。",
        min_length=3,
        max_length=240,
    )
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


class AgentCollaborationLoop(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_agent: str = Field(min_length=1, max_length=80)
    target_agent: str = Field(min_length=1, max_length=80)
    condition: str = Field(min_length=3, max_length=300)
    max_iterations: int = Field(ge=1, le=10)


class TaskPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=1200)
    execution_profile: ExecutionProfile | None = None
    execution_mode: Literal["aion_team", "workflow"]
    workflow_id: str | None = Field(default=None, min_length=1, max_length=100)
    agents: list[PlannedAgent] = Field(min_length=1, max_length=5)
    collaboration_loops: list[AgentCollaborationLoop] = Field(
        default_factory=list,
        max_length=5,
    )
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
        exact_names = {agent.name for agent in self.agents}
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
        loop_pairs: set[tuple[str, str]] = set()
        for loop in self.collaboration_loops:
            if loop.source_agent not in exact_names or loop.target_agent not in exact_names:
                raise ValueError("collaboration loops must name exact planned agents")
            pair = (loop.source_agent, loop.target_agent)
            if pair in loop_pairs:
                raise ValueError("collaboration loop pairs must be unique")
            loop_pairs.add(pair)
        if self.execution_mode == "workflow" and not self.workflow_id:
            raise ValueError("workflow execution requires workflow_id")
        if self.execution_mode == "workflow" and self.collaboration_loops:
            raise ValueError("workflow execution cannot override its runtime with agent loops")
        if self.execution_mode == "aion_team" and self.workflow_id is not None:
            raise ValueError("aion_team execution cannot carry workflow_id")
        return self

    def effective_reporting_lines(self) -> dict[str, str | None]:
        """Return a complete tree while preserving legacy plans with no explicit hierarchy."""
        leader = next(agent for agent in self.agents if agent.role == AgentRole.LEAD)
        if not any(agent.reports_to is not None for agent in self.agents):
            return {agent.name: None if agent is leader else leader.name for agent in self.agents}
        return {agent.name: agent.reports_to for agent in self.agents}


class PlanningAttachmentUpload(BaseModel):
    """One explicitly selected planning input; bytes are never persisted in plan JSON."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    media_type: str = Field(default="application/octet-stream", min_length=1, max_length=100)
    content_base64: str = Field(min_length=1, max_length=7_000_000)

    @model_validator(mode="after")
    def validate_safe_metadata(self) -> "PlanningAttachmentUpload":
        self.name = self.name.strip()
        if (
            not self.name
            or self.name in {".", ".."}
            or "/" in self.name
            or "\\" in self.name
            or any(ord(char) < 32 for char in self.name)
        ):
            raise ValueError("attachment name must be a plain filename")
        extension = "." + self.name.rsplit(".", 1)[-1].casefold() if "." in self.name else ""
        if extension not in {
            ".csv",
            ".docx",
            ".jpeg",
            ".jpg",
            ".json",
            ".md",
            ".pdf",
            ".png",
            ".txt",
            ".webp",
            ".xlsx",
        }:
            raise ValueError("attachment file type is not supported")
        self.media_type = self.media_type.strip().casefold()
        if not self.media_type or any(ord(char) < 32 for char in self.media_type):
            raise ValueError("attachment media type is invalid")
        return self


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=3, max_length=2000)
    constraints: str = Field(default="", max_length=2000)
    workspace: str = Field(default="", max_length=1024)
    preferred_cadence: Literal["once", "daily", "weekdays", "weekly", "manual"] = "once"
    blueprint_id: str | None = Field(default=None, pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    attachments: list[PlanningAttachmentUpload] = Field(default_factory=list, max_length=5)


class PlanningAttachment(BaseModel):
    """Immutable local material descriptor bound into a plan version hash."""

    model_config = ConfigDict(extra="forbid")

    attachment_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    storage_plan_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    name: str = Field(min_length=1, max_length=160)
    media_type: str = Field(min_length=1, max_length=100)
    size_bytes: int = Field(ge=1, le=5 * 1024 * 1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


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
    collaboration_loops: list[AgentCollaborationLoop] | None = Field(
        default=None,
        max_length=5,
    )
    confirmed: Literal[True]

    @model_validator(mode="after")
    def validate_unique_employees(self) -> "OrganizationRevisionRequest":
        names = [line.employee.casefold() for line in self.reporting_lines]
        if len(names) != len(set(names)):
            raise ValueError("reporting lines must name each employee once")
        return self


class AgentRuntimeAssignment(BaseModel):
    """One explicitly chosen runtime and model for one exact reviewed agent."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(min_length=1, max_length=80)
    runtime: RuntimeName
    model: str = Field(default="default", min_length=1, max_length=200)


class RuntimeRevisionRequest(BaseModel):
    """Create a new immutable plan version; never patch a reviewed plan in place."""

    model_config = ConfigDict(extra="forbid")

    assignments: list[AgentRuntimeAssignment] = Field(min_length=1, max_length=5)
    execution_profile: Literal[ExecutionProfile.CUSTOM] = ExecutionProfile.CUSTOM
    confirmed: Literal[True]

    @model_validator(mode="after")
    def validate_unique_agents(self) -> "RuntimeRevisionRequest":
        names = [assignment.agent_name.casefold() for assignment in self.assignments]
        if len(names) != len(set(names)):
            raise ValueError("runtime assignments must name each employee once")
        return self


class DeletePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: Literal[True]


class EraseRunRequest(BaseModel):
    """Irreversibly erase the private content for one exact terminal run."""

    model_config = ConfigDict(extra="forbid")

    confirmed: Literal[True]
    expected_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RerunPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_profile: Literal[
        ExecutionProfile.FAST,
        ExecutionProfile.BALANCED,
        ExecutionProfile.DEEP,
    ] = ExecutionProfile.FAST
    confirmed: Literal[True]


class ExecutionProfileRevisionRequest(BaseModel):
    """Apply one model preset by creating a new immutable reviewed plan version."""

    model_config = ConfigDict(extra="forbid")

    execution_profile: Literal[
        ExecutionProfile.FAST,
        ExecutionProfile.BALANCED,
        ExecutionProfile.DEEP,
    ]
    confirmed: Literal[True]


class ContinueRunRequest(BaseModel):
    """Continue one proven AionUi run without persisting the follow-up body here."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    confirmed: Literal[True]

    @model_validator(mode="after")
    def normalize_message(self) -> "ContinueRunRequest":
        self.message = self.message.strip()
        if not self.message:
            raise ValueError("continuation message must not be blank")
        return self


class ForkPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: Literal[True]


class ExecutionControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["pause", "resume", "terminate"]
    confirmed: Literal[True]


class ExecutionApprovalModeRequest(BaseModel):
    """Change only the policy for future tool calls in one active execution."""

    model_config = ConfigDict(extra="forbid")

    approval_mode: ApprovalMode
    expected_current_mode: ApprovalMode
    confirmed: Literal[True]

    @model_validator(mode="after")
    def reject_legacy_target(self) -> "ExecutionApprovalModeRequest":
        if self.approval_mode == ApprovalMode.AUTOMATIC_SAFE:
            raise ValueError("automatic_safe is a read-only legacy mode")
        return self


class PairingClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=12, max_length=20)
    device_name: str = Field(min_length=1, max_length=80)


class PairingMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: Literal[True]


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_mode: ApprovalMode = ApprovalMode.AUTOMATIC
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


class ActiveMemberProgress(BaseModel):
    """Exact AionUi slot activity; never inferred from team-level running state."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(min_length=1, max_length=80)
    state: Literal["queued", "running", "blocked"]
    started_at: str | None = None
    elapsed_seconds: int | None = Field(default=None, ge=0, le=2_678_400)
    slow: bool = False


class RuntimeActivity(BaseModel):
    """Bounded runtime metadata without message text, arguments, or tool output."""

    model_config = ConfigDict(extra="forbid")

    activity_id: str = Field(min_length=1, max_length=160)
    agent_name: str = Field(min_length=1, max_length=80)
    kind: Literal["tool_call", "response"]
    status: Literal["running", "completed", "failed", "observed"]
    tool_name: str | None = Field(default=None, max_length=120)
    observed_at: str
    count: int = Field(default=1, ge=1, le=100)


class StageProgress(BaseModel):
    """Plan-bound AionUi task state plus bounded, content-free runtime activity."""

    model_config = ConfigDict(extra="forbid")

    stage_order: int = Field(ge=1, le=20)
    agent_name: str = Field(min_length=1, max_length=80)
    status: Literal[
        "not_started",
        "pending",
        "running",
        "blocked",
        "completed",
        "failed",
        "unknown",
    ] = "not_started"
    source: Literal["aion_team_task", "unobserved"] = "unobserved"
    task_id: str | None = Field(default=None, min_length=1, max_length=128)
    blocked_by: list[int] = Field(default_factory=list, max_length=8)
    started_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    recent_activity: list[RuntimeActivity] = Field(default_factory=list, max_length=8)


class ExecutionProgress(BaseModel):
    """Advisory evidence snapshot for the live Work view."""

    model_config = ConfigDict(extra="forbid")

    available: bool = True
    observed_at: str = Field(default_factory=utc_now)
    stage_history_recovered: bool = False
    stage_mapping_version: int = Field(default=0, ge=0, le=1)
    active_members: list[ActiveMemberProgress] = Field(default_factory=list, max_length=5)
    recent_activity: list[RuntimeActivity] = Field(default_factory=list, max_length=20)
    stages: list[StageProgress] = Field(default_factory=list, max_length=8)


class RuntimeInputRequest(BaseModel):
    """One bounded operator question; answers remain private and are only hash-audited."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    agent_name: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=3, max_length=1200)
    choices: list[str] = Field(default_factory=list, max_length=8)
    question_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    requested_at: str = Field(default_factory=utc_now)
    status: Literal["pending", "answered"] = "pending"
    answered_at: str | None = None
    answer_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_choices(self) -> "RuntimeInputRequest":
        normalized = [choice.strip() for choice in self.choices]
        if any(not choice or len(choice) > 160 for choice in normalized):
            raise ValueError("input choices must contain 1-160 characters")
        if len({choice.casefold() for choice in normalized}) != len(normalized):
            raise ValueError("input choices must be unique")
        self.choices = normalized
        return self


class RuntimeInputAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=4000)
    confirmed: Literal[True]

    @model_validator(mode="after")
    def normalize_answer(self) -> "RuntimeInputAnswerRequest":
        self.answer = self.answer.strip()
        if not self.answer:
            raise ValueError("runtime input answer must not be blank")
        return self


class ExecutionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["aion_team", "workflow"]
    status: Literal[
        "dispatching",
        "queued",
        "running",
        "awaiting_approval",
        "awaiting_input",
        "pause_requested",
        "paused",
        "resuming",
        "cancel_requested",
        "cancelled",
        "completed_unverified",
        "failed",
    ] = "dispatching"
    approval_mode: ApprovalMode = ApprovalMode.MANUAL_ALL
    paperclip_issue_id: str | None = None
    aion_team_id: str | None = None
    aion_team_run_id: str | None = None
    aion_conversation_ids: list[str] = Field(default_factory=list)
    aion_agent_sessions: list["AgentSession"] = Field(default_factory=list)
    member_observations: list["AgentObservation"] = Field(default_factory=list)
    progress: ExecutionProgress | None = None
    input_requests: list[RuntimeInputRequest] = Field(default_factory=list, max_length=20)
    workflow_run_id: str | None = None
    error: str | None = Field(default=None, max_length=500)
    control_error: str | None = Field(default=None, max_length=500)
    control_marker: str | None = Field(default=None, max_length=100)
    control_requested_at: str | None = None
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
        "awaiting_input",
        "pause_requested",
        "paused",
        "resuming",
        "cancel_requested",
        "cancelled",
        "completed_unverified",
        "failed",
    ]
    objective: str
    constraints: str = ""
    workspace: str = ""
    preferred_cadence: Literal["once", "daily", "weekdays", "weekly", "manual"] = "once"
    attachments: list[PlanningAttachment] = Field(default_factory=list, max_length=5)
    source_blueprint_id: str | None = Field(default=None, pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    source_blueprint_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    memory_snapshot_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    memory_version_ids: list[str] = Field(default_factory=list, max_length=20)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    confirmed_at: str | None = None
    approval_mode: ApprovalMode | None = None
    planning_progress: PlanningProgress | None = None
    plan: TaskPlan | None = None
    plan_sha256: str | None = None
    parent_plan_id: str | None = None
    parent_plan_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    forked_from_plan_id: str | None = Field(
        default=None,
        pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$",
    )
    forked_from_plan_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    continued_from_plan_id: str | None = Field(
        default=None,
        pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$",
    )
    continued_from_plan_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    continuation_message_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    revision_number: int = Field(default=1, ge=1, le=100)
    revision_instruction: str = Field(default="", max_length=2000)
    revision_instruction_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    error: str | None = Field(default=None, max_length=500)
    execution: ExecutionState | None = None
    erased_at: str | None = None
    erasure_event_id: str | None = Field(
        default=None,
        pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$",
    )


class AgentSession(BaseModel):
    """Private durable mapping from a planned name to an opaque adapter conversation."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(min_length=1, max_length=80)
    conversation_id: str = Field(min_length=1, max_length=160)


class AgentObservation(BaseModel):
    """Read-side adapter telemetry, deliberately not business-outcome evidence."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(min_length=1, max_length=80)
    state: Literal[
        "activity_observed",
        "response_observed",
        "unobserved",
        "unavailable",
    ]
    observed_at: str | None = None
    source: Literal["adapter", "unavailable"] = "adapter"


class TeamBlueprintAgent(BaseModel):
    """A task-independent role slot: no agent name or task responsibility is retained."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=r"^agent_[1-5]$")
    role: AgentRole
    reports_to_key: str | None = Field(default=None, pattern=r"^agent_[1-5]$")
    runtime: RuntimeName


class TeamBlueprintLoop(BaseModel):
    """Topology-only loop; task-specific stop conditions remain in each new plan."""

    model_config = ConfigDict(extra="forbid")

    source_key: str = Field(pattern=r"^agent_[1-5]$")
    target_key: str = Field(pattern=r"^agent_[1-5]$")
    max_iterations: int = Field(ge=1, le=10)


class TeamBlueprint(BaseModel):
    """Private, versioned reusable team topology rather than a global employee directory."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    blueprint_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    name: str = Field(min_length=1, max_length=100)
    created_at: str = Field(default_factory=utc_now)
    archived_at: str | None = None
    source_plan_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    source_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verification_status: Literal["unverified", "verified"]
    agents: list[TeamBlueprintAgent] = Field(min_length=1, max_length=5)
    collaboration_loops: list[TeamBlueprintLoop] = Field(default_factory=list, max_length=5)
    blueprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_topology(self) -> "TeamBlueprint":
        keys = [agent.key for agent in self.agents]
        if len(keys) != len(set(keys)):
            raise ValueError("blueprint agent keys must be unique")
        leaders = [agent for agent in self.agents if agent.role == AgentRole.LEAD]
        if len(leaders) != 1:
            raise ValueError("a blueprint must contain exactly one lead role")
        exact_keys = set(keys)
        leader = leaders[0]
        if leader.reports_to_key is not None:
            raise ValueError("the blueprint lead cannot report to another role")
        parents: dict[str, str] = {}
        for agent in self.agents:
            if agent is leader:
                continue
            if agent.reports_to_key not in exact_keys or agent.reports_to_key == agent.key:
                raise ValueError("every non-lead blueprint role needs an exact manager")
            parents[agent.key] = agent.reports_to_key
        for key in parents:
            seen = {key}
            cursor = key
            while cursor in parents:
                cursor = parents[cursor]
                if cursor in seen:
                    raise ValueError("blueprint reporting lines must be acyclic")
                seen.add(cursor)
        pairs: set[tuple[str, str]] = set()
        for loop in self.collaboration_loops:
            if loop.source_key not in exact_keys or loop.target_key not in exact_keys:
                raise ValueError("blueprint loops must use exact role keys")
            pair = (loop.source_key, loop.target_key)
            if pair in pairs:
                raise ValueError("blueprint loop pairs must be unique")
            pairs.add(pair)
        return self


class TeamBlueprintSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_plan_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    name: str = Field(min_length=1, max_length=100)
    confirmed: Literal[True]


class TeamBlueprintArchiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: Literal[True]


class WorkspaceConversation(BaseModel):
    """Read-only projection of one immutable plan revision chain."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    conversation_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    current_plan_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    current_plan_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    title: str = Field(min_length=1, max_length=120)
    objective: str = Field(min_length=3, max_length=2000)
    status: Literal[
        "planning",
        "ready",
        "confirmed",
        "dispatching",
        "running",
        "awaiting_approval",
        "awaiting_input",
        "pause_requested",
        "paused",
        "resuming",
        "cancel_requested",
        "cancelled",
        "completed_unverified",
        "failed",
    ]
    version_count: int = Field(ge=1, le=100)
    created_at: str
    updated_at: str
    template_source_available: bool


class TaskTemplate(BaseModel):
    """A private reusable task objective; selecting one never starts planning."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    template_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    name: str = Field(min_length=1, max_length=100)
    objective: str = Field(min_length=3, max_length=2000)
    created_at: str = Field(default_factory=utc_now)
    archived_at: str | None = None
    source_plan_id: str | None = Field(default=None, pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    source_plan_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    template_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_source(self) -> "TaskTemplate":
        if (self.source_plan_id is None) != (self.source_plan_sha256 is None):
            raise ValueError("task template source id and hash must be provided together")
        return self


class TaskTemplateSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    objective: str = Field(min_length=3, max_length=2000)
    confirmed: Literal[True]


class TaskTemplateFromPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    confirmed: Literal[True]


class TaskTemplateArchiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: Literal[True]


class RepeatableWork(BaseModel):
    """A read-only Work Blueprint projection backed by an immutable reviewed plan."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    work_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    source_plan_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    source_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    title: str = Field(min_length=1, max_length=120)
    objective: str = Field(min_length=3, max_length=2000)
    revision_number: int = Field(ge=1, le=100)
    agent_count: int = Field(ge=1, le=5)
    cadence: Literal["once", "daily", "weekdays", "weekly", "manual"]
    last_status: Literal["failed", "cancelled", "completed_unverified"]
    updated_at: str
    outcome_verified: bool = False


class WorkspaceMemoryVersion(BaseModel):
    """Immutable Obsidian-compatible memory document metadata."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    memory_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    version_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    version_number: int = Field(ge=1, le=1000)
    kind: Literal["process", "knowledge"]
    title: str = Field(min_length=1, max_length=120)
    tags: list[str] = Field(default_factory=list, max_length=20)
    workspace: str = Field(default="", max_length=1024)
    source_plan_id: str | None = Field(default=None, pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    source_plan_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    parent_version_id: str | None = Field(
        default=None,
        pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$",
    )
    created_at: str = Field(default_factory=utc_now)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relative_path: str = Field(min_length=1, max_length=512)


class WorkspaceMemoryView(WorkspaceMemoryVersion):
    """Operator view: immutable content plus ledger-derived lifecycle state."""

    state: Literal["candidate", "approved", "superseded", "revoked"]
    active: bool = False
    content: str = Field(min_length=1, max_length=24_000)
    decided_at: str | None = None


class WorkspaceMemoryCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["process", "knowledge"]
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=3, max_length=24_000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    workspace: str = Field(default="", max_length=1024)
    source_plan_id: str | None = Field(default=None, pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    supersedes_version_id: str | None = Field(
        default=None,
        pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$",
    )
    confirmed: Literal[True]


class ProcessMemoryProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=120)
    confirmed: Literal[True]


class WorkspaceMemoryDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=500)
    confirmed: Literal[True]


class WorkspaceMemoryRollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=500)
    confirmed: Literal[True]


class HomeAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(min_length=1, max_length=160)
    kind: Literal[
        "approval",
        "input_required",
        "task_blocked",
        "operational",
        "running",
        "info",
    ]
    priority: int = Field(ge=1, le=5)
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=320)
    target: Literal["approvals", "tasks", "team", "history", "connections", "workspace"]
    plan_id: str | None = None


class HomeActiveTeam(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    title: str = Field(min_length=1, max_length=120)
    status: Literal[
        "confirmed",
        "dispatching",
        "running",
        "awaiting_approval",
        "awaiting_input",
        "pause_requested",
        "paused",
        "resuming",
        "cancel_requested",
    ]
    updated_at: str
    members: list[AgentObservation] = Field(default_factory=list)


class HomeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_use: bool
    has_unconfirmed_plan: bool
    default_view: Literal["workspace", "today"]
    action_queue: list[HomeAction] = Field(default_factory=list)
    active_teams: list[HomeActiveTeam] = Field(default_factory=list)
    health: dict[str, Any] = Field(default_factory=dict)


class TaskRunEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    kind: Literal[
        "task_plan_continuation_requested",
        "task_plan_confirmed",
        "task_execution_requested",
        "task_execution_dispatched",
        "task_plan_continuation_delivered",
        "task_execution_failed",
        "task_execution_finished",
        "task_input_requested",
        "task_input_answered",
        "task_input_delivered",
        "task_execution_pause_requested",
        "task_execution_paused",
        "task_execution_resume_requested",
        "task_execution_resumed",
        "task_execution_cancel_requested",
        "task_execution_cancelled",
        "task_execution_control_failed",
        "task_approval_mode_change_requested",
        "task_approval_mode_changed",
        "task_approval_mode_change_aborted",
        "task_approval_mode_change_recovered",
        "task_run_erased",
    ]
    ts: str


class TaskRunHistory(BaseModel):
    """Evidence-backed summary for one confirmed console execution."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    run_id: str
    plan_id: str
    title: str = Field(min_length=1, max_length=120)
    status: Literal[
        "confirmed",
        "dispatching",
        "running",
        "awaiting_approval",
        "awaiting_input",
        "pause_requested",
        "paused",
        "resuming",
        "cancel_requested",
        "cancelled",
        "completed_unverified",
        "failed",
    ]
    execution_mode: Literal["aion_team", "workflow"] | None = None
    agent_count: int = Field(default=0, ge=0, le=5)
    revision_number: int = Field(default=1, ge=1, le=100)
    parent_plan_id: str | None = None
    continued_from_plan_id: str | None = None
    continuation_available: bool = False
    started_at: str
    updated_at: str
    finished_at: str | None = None
    duration_s: float | None = Field(default=None, ge=0)
    outcome_verified: bool = False
    evidence_gap: bool = False
    deleted: bool = False
    events: list[TaskRunEvidence] = Field(default_factory=list)


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


class ProviderConnectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["account", "api", "api_key", "local"] = "account"
    api_key: SecretStr | None = Field(default=None, min_length=8, max_length=512)
    confirmed: Literal[True] | None = None

    @model_validator(mode="after")
    def api_key_is_only_for_api_login(self) -> "ProviderConnectionRequest":
        if self.api_key is not None and self.method not in {"api", "api_key"}:
            raise ValueError("api_key is only valid for API login")
        if self.api_key is not None and any(
            character.isspace() for character in self.api_key.get_secret_value()
        ):
            raise ValueError("api_key must not contain whitespace")
        if self.method in {"api_key", "local"} and self.confirmed is not True:
            raise ValueError("persistent or local setup requires explicit confirmation")
        if self.method not in {"api_key", "local"} and self.confirmed is not None:
            raise ValueError("confirmed is only valid for persistent or local setup")
        return self


class ProviderConnectionJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    provider: Literal["openai", "anthropic", "deepseek", "xai", "ollama", "lmstudio"]
    method: Literal["account", "api", "api_key", "local"] = "account"
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
