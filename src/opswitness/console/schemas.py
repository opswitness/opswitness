"""Strict public schemas for planning, confirmation, and console state."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from opswitness.naming import validate_new_display_name, validate_optional_new_display_name


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


class ContractControl(StrEnum):
    """Per-Agent tool/effect policy. Unknown operations are always denied."""

    DENY = "deny"
    ALWAYS_ASK = "always_ask"
    INHERIT_RUN_MODE = "inherit_run_mode"


class TaskPlanV1Agent(BaseModel):
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


PlannedAgent = TaskPlanV1Agent


class TaskPlanV1Stage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=1, le=20)
    title: str = Field(min_length=1, max_length=100)
    owner: str = Field(min_length=1, max_length=80)
    outcome: str = Field(min_length=1, max_length=500)
    checkpoint: bool = False


TaskStage = TaskPlanV1Stage


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


class TaskPlanV1(BaseModel):
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
    def validate_architecture(self) -> "TaskPlanV1":
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


def _normalized_contract_relative_path(value: str) -> str:
    """Return one canonical workspace-relative POSIX path."""
    if (
        not value
        or value != value.strip()
        or "\\" in value
        or "\x00" in value
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError("contract paths must be canonical relative POSIX paths")
    path = PurePosixPath(value)
    if path.is_absolute() or value.startswith("~"):
        raise ValueError("contract paths must be relative")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("contract paths cannot traverse or contain dot segments")
    normalized = path.as_posix()
    if normalized != value:
        raise ValueError("contract paths must already be normalized")
    return normalized


def _normalized_managed_network_domain(value: str) -> str:
    if (
        not value
        or value != value.strip()
        or value != value.casefold()
        or len(value) > 253
        or value.startswith(".")
        or value.endswith(".")
        or "*" in value
        or "://" in value
        or ":" in value
    ):
        raise ValueError("managed network domains must be exact lowercase hostnames")
    labels = value.split(".")
    if any(
        not label
        or len(label) > 63
        or not label[0].isalnum()
        or not label[-1].isalnum()
        or any(
            ord(character) > 127
            or not (character.isalnum() or character == "-")
            for character in label
        )
        for label in labels
    ):
        raise ValueError("managed network domains must be exact lowercase hostnames")
    return value


class AgentContractInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    label: str = Field(min_length=1, max_length=160)
    relative_path: str | None = Field(default=None, min_length=1, max_length=512)
    source_agent_id: str | None = Field(
        default=None,
        pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$",
    )
    source_output_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$",
    )
    required: bool = True
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str | None) -> str | None:
        return None if value is None else _normalized_contract_relative_path(value)

    @model_validator(mode="after")
    def validate_source_reference(self) -> "AgentContractInput":
        if (self.source_agent_id is None) != (self.source_output_id is None):
            raise ValueError(
                "Agent input source Agent and source output must be referenced together"
            )
        return self


class AgentContractOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    label: str = Field(min_length=1, max_length=160)
    relative_path: str = Field(min_length=1, max_length=512)
    media_type: str | None = Field(default=None, min_length=1, max_length=100)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=12)
    required: bool = True

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        return _normalized_contract_relative_path(value)


class AgentToolRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1, max_length=160)
    policy: ContractControl = ContractControl.DENY

    @field_validator("tool_name")
    @classmethod
    def normalize_tool_name(cls, value: str) -> str:
        normalized = value.strip()
        if (
            not normalized
            or normalized != value
            or any(
                ord(char) > 127
                or char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.:-"
                for char in normalized
            )
        ):
            raise ValueError("tool names must be exact ASCII identifiers")
        return normalized


class AgentDataScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_relative_paths: list[str] = Field(default_factory=list, max_length=40)
    attachment_ids: list[str] = Field(default_factory=list, max_length=5)
    managed_network_domains: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("allowed_relative_paths")
    @classmethod
    def validate_paths(cls, values: list[str]) -> list[str]:
        normalized = [_normalized_contract_relative_path(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("data scope paths must be unique")
        return normalized

    @field_validator("attachment_ids")
    @classmethod
    def validate_attachment_ids(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("attachment ids must be unique")
        for value in values:
            if len(value) != 26 or any(char not in "0123456789ABCDEFGHJKMNPQRSTVWXYZ" for char in value):
                raise ValueError("attachment ids must be ULIDs")
        return values

    @field_validator("managed_network_domains")
    @classmethod
    def validate_managed_network_domains(cls, values: list[str]) -> list[str]:
        normalized = [_normalized_managed_network_domain(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("managed network domains must be unique")
        return normalized


class AgentSideEffectPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_write: ContractControl = ContractControl.DENY
    operator_input: ContractControl = ContractControl.DENY
    managed_network: ContractControl = ContractControl.DENY
    send: ContractControl = ContractControl.DENY
    publish: ContractControl = ContractControl.DENY
    delete: Literal[ContractControl.DENY, ContractControl.ALWAYS_ASK] = ContractControl.DENY


class AgentMemoryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["none", "selected"] = "none"
    version_ids: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_selection(self) -> "AgentMemoryPolicy":
        if len(self.version_ids) != len(set(self.version_ids)):
            raise ValueError("memory version ids must be unique")
        for version_id in self.version_ids:
            if len(version_id) != 26 or any(
                char not in "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
                for char in version_id
            ):
                raise ValueError("memory version ids must be ULIDs")
        if self.mode == "none" and self.version_ids:
            raise ValueError("memory mode none cannot select versions")
        if self.mode == "selected" and not self.version_ids:
            raise ValueError("selected memory mode requires at least one version")
        return self


class AgentHandoffPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_target_agent_ids: list[str] = Field(default_factory=list, max_length=5)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=12)
    require_cas_receipt: bool = True


class AgentEscalationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_agent_id: str | None = Field(
        default=None,
        pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$",
    )
    conditions: list[str] = Field(default_factory=list, max_length=12)


class AgentRetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=1, ge=1, le=5)
    retryable_errors: list[
        Literal[
            "runtime_temporarily_unavailable",
            "rate_limited",
            "network_temporarily_unavailable",
            "tool_temporarily_unavailable",
        ]
    ] = Field(default_factory=list, max_length=4)
    backoff_seconds: int = Field(default=5, ge=1, le=300)

    @model_validator(mode="after")
    def validate_retry(self) -> "AgentRetryPolicy":
        if len(self.retryable_errors) != len(set(self.retryable_errors)):
            raise ValueError("retryable error categories must be unique")
        if self.max_attempts == 1 and self.retryable_errors:
            raise ValueError("retry categories require at least two attempts")
        return self


class AgentStopPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: int = Field(default=900, ge=30, le=86400)
    stop_conditions: list[str] = Field(default_factory=list, max_length=12)
    stop_on_approval_rejection: bool = True
    stop_on_contract_violation: bool = True
    stop_on_digest_mismatch: bool = True


class AgentContractV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    instructions: str = Field(min_length=1, max_length=12000)
    prohibitions: list[str] = Field(default_factory=list, max_length=30)
    inputs: list[AgentContractInput] = Field(default_factory=list, max_length=30)
    outputs: list[AgentContractOutput] = Field(default_factory=list, max_length=30)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=30)
    default_tool_policy: ContractControl = ContractControl.DENY
    tool_rules: list[AgentToolRule] = Field(default_factory=list, max_length=30)
    data_scope: AgentDataScope = Field(default_factory=AgentDataScope)
    side_effects: AgentSideEffectPolicy = Field(default_factory=AgentSideEffectPolicy)
    memory: AgentMemoryPolicy = Field(default_factory=AgentMemoryPolicy)
    handoff: AgentHandoffPolicy = Field(default_factory=AgentHandoffPolicy)
    escalation: AgentEscalationPolicy = Field(default_factory=AgentEscalationPolicy)
    approval_checkpoints: list[str] = Field(default_factory=list, max_length=20)
    retry: AgentRetryPolicy = Field(default_factory=AgentRetryPolicy)
    stop: AgentStopPolicy = Field(default_factory=AgentStopPolicy)

    @model_validator(mode="after")
    def validate_contract(self) -> "AgentContractV1":
        input_ids = [item.input_id for item in self.inputs]
        output_ids = [item.output_id for item in self.outputs]
        tools = [item.tool_name for item in self.tool_rules]
        if len(input_ids) != len(set(input_ids)):
            raise ValueError("contract input ids must be unique")
        if len(output_ids) != len(set(output_ids)):
            raise ValueError("contract output ids must be unique")
        if len(tools) != len(set(tools)):
            raise ValueError("contract tool rules must be unique")
        if self.default_tool_policy != ContractControl.DENY:
            raise ValueError("v2 contracts must deny unknown tools")
        return self


class AgentRuntimeBinding(BaseModel):
    """Read-only adapter identity captured by the service in the reviewed plan."""

    model_config = ConfigDict(extra="forbid")

    adapter_version: str = Field(min_length=1, max_length=120)
    executable_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    status: Literal["bound", "alias", "default", "unverified"]


class TaskPlanV2Agent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    name: str = Field(min_length=1, max_length=80)
    role: AgentRole
    responsibility: str = Field(min_length=1, max_length=600)
    runtime: RuntimeName
    model: str = Field(default="default", min_length=1, max_length=200)
    model_binding: Literal["exact", "alias", "default"] = "default"
    runtime_binding: AgentRuntimeBinding = Field(
        default_factory=lambda: AgentRuntimeBinding(
            adapter_version="unavailable",
            executable_sha256=None,
            status="unverified",
        )
    )
    runtime_reason: str = Field(min_length=3, max_length=240)
    reports_to_agent_id: str | None = Field(
        default=None,
        pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$",
    )
    contract: AgentContractV1

    @model_validator(mode="after")
    def validate_model_binding(self) -> "TaskPlanV2Agent":
        if self.model_binding == "default" and self.model != "default":
            raise ValueError("default model binding must use model id default")
        if self.model_binding != "default" and self.model == "default":
            raise ValueError("alias/exact model binding requires a concrete model id")
        return self


class TaskPlanV2Stage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=1, le=20)
    title: str = Field(min_length=1, max_length=100)
    owner_agent_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    outcome: str = Field(min_length=1, max_length=500)
    checkpoint: bool = False


class AgentCollaborationLoopV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_agent_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    target_agent_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    condition: str = Field(min_length=3, max_length=300)
    max_iterations: int = Field(ge=1, le=10)


class TaskPlanV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=1200)
    execution_profile: ExecutionProfile | None = None
    execution_mode: Literal["aion_team"] = "aion_team"
    workflow_id: None = None
    runtime_mode: Literal["aion_compatible", "strict"] = "aion_compatible"
    agents: list[TaskPlanV2Agent] = Field(min_length=1, max_length=5)
    collaboration_loops: list[AgentCollaborationLoopV2] = Field(
        default_factory=list,
        max_length=5,
    )
    stages: list[TaskPlanV2Stage] = Field(min_length=1, max_length=8)
    cadence: TaskCadence
    tools: list[str] = Field(default_factory=list, max_length=12)
    approvals: list[str] = Field(default_factory=list, max_length=12)
    artifacts: list[str] = Field(default_factory=list, max_length=12)
    risks: list[str] = Field(default_factory=list, max_length=12)
    estimated_duration_minutes: int = Field(ge=1, le=10080)
    update_policy: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_architecture(self) -> "TaskPlanV2":
        leaders = [agent for agent in self.agents if agent.role == AgentRole.LEAD]
        if len(leaders) != 1:
            raise ValueError("a plan must contain exactly one lead agent")
        ids = [agent.agent_id for agent in self.agents]
        if len(ids) != len(set(ids)):
            raise ValueError("agent ids must be unique")
        names = [agent.name.casefold() for agent in self.agents]
        if len(names) != len(set(names)):
            raise ValueError("agent names must be unique")
        agent_ids = set(ids)
        leader = leaders[0]
        if leader.reports_to_agent_id is not None:
            raise ValueError("the lead agent cannot report to another agent")
        parents: dict[str, str] = {}
        for agent in self.agents:
            if agent.agent_id == leader.agent_id:
                continue
            parent = agent.reports_to_agent_id
            if parent is None or parent not in agent_ids or parent == agent.agent_id:
                raise ValueError("every non-lead agent must have one valid direct manager")
            parents[agent.agent_id] = parent
        for node_id in parents:
            seen = {node_id}
            cursor = node_id
            while cursor in parents:
                cursor = parents[cursor]
                if cursor in seen:
                    raise ValueError("agent reporting lines must be acyclic")
                seen.add(cursor)
        orders = [stage.order for stage in self.stages]
        if sorted(orders) != list(range(1, len(orders) + 1)):
            raise ValueError("stage order must be contiguous from 1")
        if any(stage.owner_agent_id not in agent_ids for stage in self.stages):
            raise ValueError("every stage owner must reference a planned agent")
        loop_pairs: set[tuple[str, str]] = set()
        for loop in self.collaboration_loops:
            pair = (loop.source_agent_id, loop.target_agent_id)
            if (
                loop.source_agent_id not in agent_ids
                or loop.target_agent_id not in agent_ids
                or pair in loop_pairs
            ):
                raise ValueError("collaboration loops must reference unique planned agents")
            loop_pairs.add(pair)
        output_owners = {
            output.output_id: agent.agent_id
            for agent in self.agents
            for output in agent.contract.outputs
        }
        output_ids = set(output_owners)
        if len(output_ids) != sum(len(agent.contract.outputs) for agent in self.agents):
            raise ValueError("output ids must be unique across the plan")
        attachment_ids = set()
        for agent in self.agents:
            contract = agent.contract
            for input_item in contract.inputs:
                if (
                    input_item.source_agent_id is not None
                    and input_item.source_agent_id not in agent_ids
                ):
                    raise ValueError("contract input source must reference a planned agent")
                if input_item.source_output_id is not None and (
                    input_item.source_output_id not in output_owners
                    or output_owners[input_item.source_output_id]
                    != input_item.source_agent_id
                ):
                    raise ValueError(
                        "contract input source output must belong to its source Agent"
                    )
            handoff_targets = contract.handoff.allowed_target_agent_ids
            if len(handoff_targets) != len(set(handoff_targets)):
                raise ValueError("handoff targets must be unique")
            if any(
                target not in agent_ids or target == agent.agent_id
                for target in handoff_targets
            ):
                raise ValueError("handoff targets must reference another planned agent")
            escalation = contract.escalation.target_agent_id
            if escalation is not None and (
                escalation not in agent_ids or escalation == agent.agent_id
            ):
                raise ValueError("escalation must reference another planned agent")
            attachment_ids.update(contract.data_scope.attachment_ids)
        if len(attachment_ids) > 5:
            raise ValueError("plan contracts reference too many attachments")
        return self

    def effective_reporting_lines(self) -> dict[str, str | None]:
        by_id = {agent.agent_id: agent.name for agent in self.agents}
        return {
            agent.name: (
                by_id[agent.reports_to_agent_id]
                if agent.reports_to_agent_id is not None
                else None
            )
            for agent in self.agents
        }


# Compatibility name for callers and fixtures that explicitly create historical v1 plans.
TaskPlan = TaskPlanV1
TaskPlanDocument = Annotated[
    TaskPlanV1 | TaskPlanV2,
    Field(discriminator="schema_version"),
]


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


class FailedPlanningRetryRequest(BaseModel):
    """An explicit edited retry of one terminal planning attempt."""

    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=3, max_length=2000)
    confirmed: Literal[True]

    @model_validator(mode="after")
    def normalize_objective(self) -> "FailedPlanningRetryRequest":
        self.objective = self.objective.strip()
        if len(self.objective) < 3:
            raise ValueError("edited objective must contain at least three characters")
        return self


class PlanningAttachment(BaseModel):
    """Immutable local material descriptor bound into a plan version hash."""

    model_config = ConfigDict(extra="forbid")

    attachment_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    storage_plan_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    name: str = Field(min_length=1, max_length=160)
    media_type: str = Field(min_length=1, max_length=100)
    size_bytes: int = Field(ge=1, le=50 * 1024 * 1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProjectLibraryMetadata(BaseModel):
    """Private operator metadata bound to one exact projected file identity."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    asset_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_kind: Literal["planning_input", "registered_output", "workspace_output"]
    plan_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    source_ref: str = Field(min_length=1, max_length=256)
    name: str = Field(min_length=1, max_length=256)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    user_tags: list[str] = Field(default_factory=list, max_length=20)
    supersedes_asset_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    updated_at: str = Field(default_factory=utc_now)


class ProjectLibraryItem(BaseModel):
    """One live, re-verifiable projection over retained bytes owned elsewhere."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    asset_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_kind: Literal["planning_input", "registered_output", "workspace_output"]
    source_ref: str = Field(min_length=1, max_length=256)
    plan_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    work_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    work_title: str = Field(min_length=1, max_length=120)
    revision_number: int = Field(ge=1, le=100)
    name: str = Field(min_length=1, max_length=256)
    mime: str = Field(min_length=1, max_length=100)
    file_type: str = Field(min_length=1, max_length=100)
    size: int = Field(ge=0, le=25 * 1024 * 1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_status: Literal["retained_input", "registered", "workspace_unverified"]
    preview_supported: bool
    created_at: str
    event_id: str | None = Field(default=None, max_length=128)
    system_tags: list[str] = Field(default_factory=list, max_length=55)
    user_tags: list[str] = Field(default_factory=list, max_length=20)
    supersedes_asset_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    supersedes_status: Literal["none", "available", "unavailable"] = "none"
    superseded_by_asset_ids: list[str] = Field(default_factory=list, max_length=500)
    content_url: str = Field(min_length=1, max_length=256)


class ProjectLibraryItemPreview(ProjectLibraryItem):
    model_config = ConfigDict(extra="forbid")

    preview_kind: Literal["none", "json", "text"] = "none"
    preview: Any = None


class ProjectLibraryMetadataUpdate(BaseModel):
    """Replace user-managed tags and one explicit version predecessor."""

    model_config = ConfigDict(extra="forbid")

    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    user_tags: list[str] = Field(default_factory=list, max_length=20)
    supersedes_asset_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    confirmed: Literal[True]

    @model_validator(mode="after")
    def normalize_metadata(self) -> "ProjectLibraryMetadataUpdate":
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_tag in self.user_tags:
            tag = " ".join(raw_tag.split())
            if not tag or len(tag) > 40 or any(ord(char) < 32 for char in tag):
                raise ValueError("library tags must contain 1-40 printable characters")
            folded = tag.casefold()
            if folded in seen:
                continue
            seen.add(folded)
            normalized.append(tag)
        self.user_tags = normalized
        return self


LibraryFileFormat = Literal[
    "csv",
    "docx",
    "jpeg",
    "jpg",
    "json",
    "md",
    "pdf",
    "png",
    "txt",
    "webp",
    "xlsx",
]


def _default_library_formats() -> list[LibraryFileFormat]:
    return [
        "txt",
        "md",
        "csv",
        "json",
        "pdf",
        "docx",
        "xlsx",
        "png",
        "jpg",
        "jpeg",
        "webp",
    ]


def _normalize_library_tags(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_tag in values:
        tag = " ".join(raw_tag.split())
        if not tag or len(tag) > 40 or any(ord(char) < 32 for char in tag):
            raise ValueError("library tags must contain 1-40 printable characters")
        folded = tag.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        normalized.append(tag)
    return normalized


class LibraryCollectionPolicyV1(BaseModel):
    """Immutable policy content; identity and hash live on the collection revision."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    purpose: str = Field(default="General reference material", max_length=500)
    default_tags: list[str] = Field(default_factory=list, max_length=20)
    allowed_formats: list[LibraryFileFormat] = Field(
        default_factory=_default_library_formats,
        min_length=1,
        max_length=12,
    )
    exclude_name_patterns: list[str] = Field(
        default_factory=lambda: [".DS_Store", "Thumbs.db"],
        max_length=20,
    )
    knowledge_card_language: Literal["auto", "zh-CN", "en"] = "auto"
    generation_instructions: str = Field(
        default=(
            "Summarize only supported source material. Keep claims bounded and attach an "
            "exact source citation to every key point."
        ),
        max_length=2000,
    )

    @model_validator(mode="after")
    def normalize_policy(self) -> "LibraryCollectionPolicyV1":
        self.purpose = " ".join(self.purpose.split())
        self.default_tags = _normalize_library_tags(self.default_tags)
        self.allowed_formats = list(dict.fromkeys(self.allowed_formats))
        patterns: list[str] = []
        for raw_pattern in self.exclude_name_patterns:
            pattern = raw_pattern.strip()
            if (
                not pattern
                or len(pattern) > 100
                or "/" in pattern
                or "\\" in pattern
                or any(ord(char) < 32 for char in pattern)
            ):
                raise ValueError("library exclusion patterns must be plain names")
            if pattern not in patterns:
                patterns.append(pattern)
        self.exclude_name_patterns = patterns
        self.generation_instructions = self.generation_instructions.strip()
        return self


class LibraryCollectionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    collection_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    name: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=1)
    policy_version_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy: LibraryCollectionPolicyV1
    is_inbox: bool = False
    document_count: int = Field(default=0, ge=0)
    approved_card_count: int = Field(default=0, ge=0)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class LibraryCollectionCreateV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    policy: LibraryCollectionPolicyV1 = Field(default_factory=LibraryCollectionPolicyV1)

    @model_validator(mode="after")
    def normalize_name(self) -> "LibraryCollectionCreateV1":
        self.name = " ".join(self.name.split())
        if not self.name:
            raise ValueError("library collection name must not be blank")
        return self


class LibraryCollectionRevisionRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=100)
    policy: LibraryCollectionPolicyV1
    confirmed: Literal[True]

    @model_validator(mode="after")
    def normalize_name(self) -> "LibraryCollectionRevisionRequestV1":
        self.name = " ".join(self.name.split())
        if not self.name:
            raise ValueError("library collection name must not be blank")
        return self


class LibraryImportEntryRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relative_path: str = Field(min_length=1, max_length=500)
    size_bytes: int = Field(ge=1, le=50 * 1024 * 1024)
    media_type: str = Field(default="application/octet-stream", min_length=1, max_length=100)
    source_kind: Literal["file", "hidden", "package", "symlink"] = "file"

    @model_validator(mode="after")
    def validate_relative_path(self) -> "LibraryImportEntryRequestV1":
        raw = self.relative_path.replace("\\", "/")
        path = PurePosixPath(raw)
        if (
            path.is_absolute()
            or not path.parts
            or raw != path.as_posix()
            or any(part in {"", ".", ".."} for part in path.parts)
            or any(any(ord(char) < 32 for char in part) for part in path.parts)
        ):
            raise ValueError("library import path must be a normalized relative path")
        self.relative_path = raw
        self.media_type = self.media_type.strip().casefold()
        return self


class LibraryImportCreateRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    expected_collection_revision: int = Field(ge=1)
    entries: list[LibraryImportEntryRequestV1] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_batch(self) -> "LibraryImportCreateRequestV1":
        if sum(entry.size_bytes for entry in self.entries) > 1024 * 1024 * 1024:
            raise ValueError("library import exceeds the 1 GiB batch limit")
        paths = [entry.relative_path.casefold() for entry in self.entries]
        if len(paths) != len(set(paths)):
            raise ValueError("library import paths must be unique within a batch")
        return self


class LibraryImportEntryV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    relative_path: str = Field(min_length=1, max_length=500)
    size_bytes: int = Field(ge=1, le=50 * 1024 * 1024)
    media_type: str = Field(min_length=1, max_length=100)
    file_format: str = Field(min_length=1, max_length=20)
    status: Literal[
        "pending",
        "uploaded",
        "duplicate",
        "new_version",
        "skipped",
        "error",
        "committed",
    ]
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    classification: Literal["new", "duplicate", "new_version", "skipped"] | None = None
    reason: str | None = Field(default=None, max_length=300)
    document_version_id: str | None = Field(
        default=None,
        pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$",
    )


class LibraryImportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    import_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    collection_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    collection_revision: int = Field(ge=1)
    policy_version_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["staging", "ready", "committing", "committed", "cancelled", "expired"]
    entries: list[LibraryImportEntryV1] = Field(max_length=500)
    files_total: int = Field(ge=1, le=500)
    files_uploaded: int = Field(default=0, ge=0, le=500)
    files_skipped: int = Field(default=0, ge=0, le=500)
    files_failed: int = Field(default=0, ge=0, le=500)
    bytes_total: int = Field(ge=1, le=1024 * 1024 * 1024)
    bytes_uploaded: int = Field(default=0, ge=0, le=1024 * 1024 * 1024)
    manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    expires_at: str


class LibraryImportCommitRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_collection_revision: int = Field(ge=1)
    confirmed_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed: Literal[True]


LibraryExtractionStatus = Literal[
    "included",
    "metadata_only",
    "encrypted",
    "no_text",
    "extraction_failed",
]


class LibraryDocumentVersionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    document_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    version_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    collection_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    version_number: int = Field(ge=1)
    previous_version_id: str | None = Field(
        default=None,
        pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$",
    )
    relative_path: str = Field(min_length=1, max_length=500)
    display_name: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=100)
    file_format: str = Field(min_length=1, max_length=20)
    size_bytes: int = Field(ge=1, le=50 * 1024 * 1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    blob_ref: str = Field(pattern=r"^sha256/[0-9a-f]{2}/[0-9a-f]{64}$")
    aliases: list[str] = Field(default_factory=list, max_length=50)
    tags: list[str] = Field(default_factory=list, max_length=20)
    metadata_revision: int = Field(default=1, ge=1)
    policy_version_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    extraction_status: LibraryExtractionStatus
    extraction_detail: str | None = Field(default=None, max_length=300)
    text_chunk_count: int = Field(default=0, ge=0)
    text_character_count: int = Field(default=0, ge=0)
    text_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    status: Literal["active", "tombstoned"] = "active"
    created_at: str = Field(default_factory=utc_now)
    tombstoned_at: str | None = None


class LibraryDocumentMetadataUpdateV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_metadata_revision: int = Field(ge=1)
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tags: list[str] = Field(default_factory=list, max_length=20)
    aliases: list[str] = Field(default_factory=list, max_length=50)
    confirmed: Literal[True]

    @model_validator(mode="after")
    def normalize_metadata(self) -> "LibraryDocumentMetadataUpdateV1":
        self.tags = _normalize_library_tags(self.tags)
        aliases: list[str] = []
        for raw_alias in self.aliases:
            alias = " ".join(raw_alias.split())
            if (
                not alias
                or len(alias) > 255
                or "/" in alias
                or "\\" in alias
                or any(ord(char) < 32 for char in alias)
            ):
                raise ValueError("library aliases must be plain display names")
            if alias.casefold() not in {item.casefold() for item in aliases}:
                aliases.append(alias)
        self.aliases = aliases
        return self


class LibraryCitationV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    document_version_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    locator_type: Literal["page", "sheet", "line", "chunk", "metadata"]
    locator: str = Field(min_length=1, max_length=200)
    chunk_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    excerpt: str = Field(default="", max_length=1000)
    excerpt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class KnowledgeCardPointV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1, max_length=1000)
    citations: list[LibraryCitationV1] = Field(min_length=1, max_length=4)


class KnowledgeCardVersionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    card_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    version_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    collection_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    source_document_version_ids: list[str] = Field(min_length=1, max_length=20)
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=4000)
    key_points: list[KnowledgeCardPointV1] = Field(default_factory=list, max_length=8)
    suggested_tags: list[str] = Field(default_factory=list, max_length=20)
    coverage_scope: str = Field(min_length=1, max_length=1000)
    coverage: Literal["complete", "partial", "metadata_only"]
    state: Literal["candidate", "approved", "superseded", "dismissed", "revoked"]
    card_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: Literal["openai", "anthropic"]
    model: str = Field(min_length=1, max_length=200)
    generator_version: str = Field(min_length=1, max_length=100)
    created_at: str = Field(default_factory=utc_now)
    decided_at: str | None = None


class LibraryCardJobRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    document_version_ids: list[str] = Field(min_length=1, max_length=20)
    provider: Literal["openai", "anthropic"]
    model: str = Field(min_length=1, max_length=200)
    disclosed_character_count: int = Field(ge=0)
    confirmed_source_disclosure: Literal[True]


class LibraryCardJobV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    job_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    collection_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    document_version_ids: list[str] = Field(min_length=1, max_length=20)
    provider: Literal["openai", "anthropic"]
    model: str = Field(min_length=1, max_length=200)
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    files_total: int = Field(ge=1, le=20)
    files_processed: int = Field(default=0, ge=0, le=20)
    card_version_ids: list[str] = Field(default_factory=list, max_length=20)
    error_code: str | None = Field(default=None, max_length=100)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class LibraryCardDecisionRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_card_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed: Literal[True]


class LibrarySearchRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    query: str = Field(min_length=1, max_length=500)
    mode: Literal["lexical", "semantic", "hybrid"] = "lexical"
    collection_ids: list[str] = Field(default_factory=list, max_length=20)
    states: list[str] = Field(default_factory=list, max_length=10)
    source_types: list[str] = Field(default_factory=list, max_length=10)
    evidence_statuses: list[str] = Field(default_factory=list, max_length=10)
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def normalize_query(self) -> "LibrarySearchRequestV1":
        self.query = " ".join(self.query.split())
        if not self.query:
            raise ValueError("library search query must not be blank")
        return self


class LibrarySearchHitV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hit_id: str = Field(min_length=1, max_length=160)
    source_type: Literal["document", "knowledge_card", "project_library", "workspace_memory"]
    collection_id: str | None = None
    title: str = Field(min_length=1, max_length=300)
    snippet: str = Field(default="", max_length=1200)
    source_status: str = Field(min_length=1, max_length=100)
    version_id: str = Field(min_length=1, max_length=128)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_status: str = Field(min_length=1, max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=40)
    locator: str | None = Field(default=None, max_length=200)
    relevance_score: float


LibrarySemanticStatus = Literal[
    "not_requested",
    "ready",
    "model_missing",
    "offline",
    "integrity_failed",
    "runtime_unavailable",
]


class LibrarySearchResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    query: str
    mode_requested: Literal["lexical", "semantic", "hybrid"]
    mode_used: Literal["lexical", "semantic", "hybrid"]
    semantic_status: LibrarySemanticStatus
    index_version: int = Field(ge=1)
    hits: list[LibrarySearchHitV1] = Field(max_length=100)
    next_cursor: str | None = None


class LibraryIndexStatusV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    state: Literal["idle", "building", "ready", "failed"]
    phase: str = Field(min_length=1, max_length=100)
    files_scanned: int = Field(default=0, ge=0)
    bytes_processed: int = Field(default=0, ge=0)
    succeeded: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    index_version: int = Field(default=1, ge=1)
    semantic_status: str = Field(default="model_missing", max_length=100)
    updated_at: str = Field(default_factory=utc_now)


class LibrarySemanticModelDownloadRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: Literal[True]


class LibrarySemanticModelStatusV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    model_id: Literal["intfloat/multilingual-e5-small"] = (
        "intfloat/multilingual-e5-small"
    )
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    state: Literal[
        "model_missing",
        "downloading",
        "ready",
        "offline",
        "integrity_failed",
        "runtime_unavailable",
        "failed",
    ]
    bytes_total: int = Field(ge=0)
    bytes_downloaded: int = Field(default=0, ge=0)
    current_file: str | None = Field(default=None, max_length=100)
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    error_code: str | None = Field(default=None, max_length=100)
    updated_at: str = Field(default_factory=utc_now)


class LibraryInputBindingItemV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_version_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    collection_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    name: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=100)
    size_bytes: int = Field(ge=1, le=50 * 1024 * 1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    attachment_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")


class LibraryInputBindingV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    binding_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    items: list[LibraryInputBindingItemV1] = Field(min_length=1, max_length=10)
    knowledge_card_version_ids: list[str] = Field(default_factory=list, max_length=20)
    knowledge_card_manifest_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: str = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_card_binding(self) -> "LibraryInputBindingV1":
        if bool(self.knowledge_card_version_ids) != bool(
            self.knowledge_card_manifest_sha256
        ):
            raise ValueError("library knowledge card binding is incomplete")
        return self


class LibraryPlanRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=3, max_length=2000)
    constraints: str = Field(default="", max_length=2000)
    workspace: str = Field(default="", max_length=1024)
    preferred_cadence: Literal["once", "daily", "weekdays", "weekly", "manual"] = "once"
    document_version_ids: list[str] = Field(min_length=1, max_length=10)
    knowledge_card_version_ids: list[str] = Field(default_factory=list, max_length=20)
    confirmed_context_packet: Literal[True]


class LibraryH5ExportPolicyV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    profile: Literal["safe_partner"] = "safe_partner"
    include_card_version_ids: list[str] = Field(min_length=1, max_length=500)
    include_tags: bool = True
    include_citation_excerpts: bool = True
    custom_sensitive_terms: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_sensitive_terms(self) -> "LibraryH5ExportPolicyV1":
        normalized: list[str] = []
        for raw_term in self.custom_sensitive_terms:
            term = raw_term.strip()
            if not term or len(term) > 200 or any(ord(char) < 32 for char in term):
                raise ValueError("custom sensitive terms must contain printable text")
            if term not in normalized:
                normalized.append(term)
        self.custom_sensitive_terms = normalized
        return self


class LibraryH5ExportPreviewRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    expected_collection_revision: int = Field(ge=1)
    policy: LibraryH5ExportPolicyV1


class LibraryH5ExportRequestV1(LibraryH5ExportPreviewRequestV1):
    model_config = ConfigDict(extra="forbid")

    expected_preview_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed: Literal[True]


class LibraryH5ExportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    export_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    collection_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    status: Literal["ready", "expired", "failed"]
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    card_count: int = Field(ge=1)
    created_at: str = Field(default_factory=utc_now)
    expires_at: str
    download_url: str = Field(min_length=1, max_length=300)


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


class AgentGraphStageAssignment(BaseModel):
    """Bind one existing sequential stage to one Agent in a graph revision."""

    model_config = ConfigDict(extra="forbid")

    stage_order: int = Field(ge=1, le=20)
    owner: str = Field(min_length=1, max_length=80)


class AgentGraphRevisionRequest(BaseModel):
    """Atomically replace the editable Agent projection of one reviewed Plan."""

    model_config = ConfigDict(extra="forbid")

    expected_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    agents: list[PlannedAgent] = Field(min_length=1, max_length=5)
    collaboration_loops: list[AgentCollaborationLoop] = Field(
        default_factory=list,
        max_length=5,
    )
    stage_assignments: list[AgentGraphStageAssignment] = Field(min_length=1, max_length=8)
    confirmed: Literal[True]

    @model_validator(mode="after")
    def validate_graph_request(self) -> "AgentGraphRevisionRequest":
        names = [agent.name.casefold() for agent in self.agents]
        if len(names) != len(set(names)):
            raise ValueError("agent graph names must be unique")
        orders = [assignment.stage_order for assignment in self.stage_assignments]
        if len(orders) != len(set(orders)):
            raise ValueError("agent graph stage assignments must name each stage once")
        return self


class AgentContractPreviewRequest(BaseModel):
    """Preview one complete v2 draft without creating an immutable version."""

    model_config = ConfigDict(extra="forbid")

    expected_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    draft: dict[str, Any] | None = None


class AgentContractRevisionRequest(AgentContractPreviewRequest):
    """Create one reviewed immutable v2 child from the same preview draft."""

    confirmed: Literal[True]


class AgentContractDiffEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    change: Literal["added", "removed", "changed"]
    direction: Literal["tighter", "looser", "neutral"]
    before: Any = None
    after: Any = None


class AgentExecutionEnvelopeView(BaseModel):
    """User-visible exact normalized payload plus its content identity."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    agent_name: str
    delivery: Literal["exact_lead_payload", "exact_plan_packet", "strict_runtime"]
    canonical_json: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    enforcement: dict[str, Literal[
        "software_enforced",
        "runtime_approval",
        "execution_instruction",
        "unsupported",
    ]]


class AgentContractPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_plan_id: str
    parent_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_plan: TaskPlanV2
    candidate_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diff: list[AgentContractDiffEntry]
    envelopes: list[AgentExecutionEnvelopeView]
    strict_runtime_available: bool


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


class DesktopDrainRequest(BaseModel):
    """Supervisor-only transition that fences new Work dispatches."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["begin", "cancel"]


class OnboardingMigrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    choice: Literal["fresh", "import"]
    confirmed: Literal[True]


class OnboardingProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["openai", "anthropic"]
    confirmed: Literal[True]


class OnboardingFirstWorkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: Literal[True]
    replace_unstarted_legacy: bool = False
    replace_incomplete_terminal: bool = False


class ArtifactSignoffRequest(BaseModel):
    """A local review of captured evidence, not a business-outcome assertion."""

    model_config = ConfigDict(extra="forbid")

    confirmed: Literal[True]
    first_work_event_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    first_work_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verification_event_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    verification_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class OnboardingFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=100)
    detail: str = Field(min_length=1, max_length=500)
    retryable: bool


class OnboardingStatus(BaseModel):
    """Recoverable desktop first-use projection; secrets and file contents are excluded."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    state: Literal[
        "preparing",
        "self_check",
        "migration_required",
        "provider_required",
        "first_work_ready",
        "first_work_running",
        "evidence_review",
        "complete",
        "failed",
    ]
    complete: bool
    required_free_bytes: int = Field(ge=1)
    available_free_bytes: int = Field(ge=0)
    disk_ready: bool
    migration_required: bool
    legacy_sources: list[str] = Field(default_factory=list, max_length=5)
    migration_choice: Literal["fresh", "import"] | None = None
    provider_choice: Literal["openai", "anthropic"] | None = None
    runtime_ready: bool
    provider_runtime_ready: bool
    first_work_plan_id: str | None = Field(
        default=None,
        pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$",
    )
    failure: OnboardingFailure | None = None


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


class OnboardingArtifactWriteRequest(BaseModel):
    """One exact App-managed write awaiting or carrying a single-use decision."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    approval_id: str = Field(min_length=1, max_length=128)
    agent_name: Literal["Business Assistant", "Review Assistant"]
    relative_path: Literal[
        "artifacts/first-work.json",
        "artifacts/verification.json",
    ]
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    nonce: str = Field(pattern=r"^[0-9a-f]{64}$")
    requested_at: str = Field(default_factory=utc_now)
    status: Literal["pending", "committed", "rejected"] = "pending"
    decided_at: str | None = None
    artifact_event_id: str | None = None


class RecoveryModelDiagnosis(BaseModel):
    """Strict, content-free response accepted from the managed recovery model."""

    model_config = ConfigDict(extra="forbid")

    category: Literal[
        "progress_stalled",
        "runtime_unavailable",
        "remote_paused",
        "approval_wait",
        "input_wait",
        "unknown",
    ]
    summary: str = Field(min_length=3, max_length=500)
    recommended_action: Literal[
        "refresh_status",
        "resume_same_run",
        "create_repair_work",
        "request_operator",
    ]
    rationale_codes: list[
        Literal[
            "unchanged_progress",
            "runtime_unreachable",
            "remote_run_paused",
            "operator_approval_required",
            "operator_input_required",
            "identity_unverified",
            "insufficient_evidence",
        ]
    ] = Field(min_length=1, max_length=4)
    confidence: Literal["low", "medium", "high"]


class RecoveryStageBaseline(BaseModel):
    """Stable stage state used to prove monotonic forward recovery progress."""

    model_config = ConfigDict(extra="forbid")

    stage_order: int = Field(ge=1, le=20)
    status: Literal[
        "not_started",
        "pending",
        "running",
        "blocked",
        "completed",
        "failed",
        "unknown",
    ]
    task_id: str | None = Field(default=None, min_length=1, max_length=128)


class RecoveryEvidenceBaseline(BaseModel):
    """Bounded causal evidence descriptor; timestamps and member presence are excluded."""

    model_config = ConfigDict(extra="forbid")

    stages: list[RecoveryStageBaseline] = Field(default_factory=list, max_length=8)
    completed_or_observed_activity_ids: list[str] = Field(
        default_factory=list,
        max_length=100,
    )


class RecoveryState(BaseModel):
    """Durable, bounded state for one governed Work recovery attempt."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    state: Literal[
        "idle",
        "observing",
        "diagnosing",
        "proposal_ready",
        "auto_recovering",
        "verifying",
        "recovered",
        "failed",
        "escalated",
    ] = "idle"
    progress_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    progress_changed_at: str | None = None
    observation_baseline: RecoveryEvidenceBaseline | None = None
    last_observed_at: str | None = None
    stalled_since: str | None = None
    attempt_count: int = Field(default=0, ge=0, le=2)
    diagnosis_id: str | None = Field(
        default=None,
        pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$",
    )
    diagnosis_claimed_at: str | None = None
    diagnosis_category: str | None = Field(default=None, max_length=80)
    diagnosis_summary: str | None = Field(default=None, max_length=500)
    recommended_action: Literal[
        "refresh_status",
        "resume_same_run",
        "create_repair_work",
        "request_operator",
    ] | None = None
    rationale_codes: list[str] = Field(default_factory=list, max_length=4)
    proposal_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    diagnosed_at: str | None = None
    bound_plan_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    bound_team_id: str | None = Field(default=None, min_length=1, max_length=128)
    previous_team_run_id: str | None = Field(default=None, min_length=1, max_length=128)
    resulting_team_run_id: str | None = Field(default=None, min_length=1, max_length=128)
    action_started_at: str | None = None
    action_completed_at: str | None = None
    verification_evidence_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    verification_baseline: RecoveryEvidenceBaseline | None = None
    verification_deadline: str | None = None
    repair_work_id: str | None = Field(
        default=None,
        pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$",
    )
    cooldown_until: str | None = None
    last_error_code: Literal[
        "model_unavailable",
        "identity_changed",
        "action_not_auto_allowed",
        "action_unconfirmed",
        "attempt_limit_reached",
    ] | None = None


class RecoveryCheckRequest(BaseModel):
    """Explicit retry of the same bounded recovery check; it grants no new capability."""

    model_config = ConfigDict(extra="forbid")

    confirmed: Literal[True]


class RecoveryDecisionRequest(BaseModel):
    """Explicitly approve creation of a separate, still-unconfirmed Repair Work."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["create_repair_work"]
    expected_proposal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed: Literal[True]


class ExecutionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["aion_team", "workflow", "onboarding_managed"]
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
    recovery: RecoveryState = Field(default_factory=RecoveryState)
    input_requests: list[RuntimeInputRequest] = Field(default_factory=list, max_length=20)
    onboarding_artifact_writes: list[OnboardingArtifactWriteRequest] = Field(
        default_factory=list,
        max_length=2,
    )
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
    attachments: list[PlanningAttachment] = Field(default_factory=list, max_length=10)
    library_input_binding: LibraryInputBindingV1 | None = None
    source_blueprint_id: str | None = Field(default=None, pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    source_blueprint_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    memory_snapshot_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    memory_version_ids: list[str] = Field(default_factory=list, max_length=20)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    confirmed_at: str | None = None
    approval_mode: ApprovalMode | None = None
    planning_progress: PlanningProgress | None = None
    plan: TaskPlanDocument | None = None
    plan_sha256: str | None = None
    request_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    parent_plan_id: str | None = None
    parent_plan_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    planning_retry_source_plan_id: str | None = Field(
        default=None,
        pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$",
    )
    planning_retry_source_request_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
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
    recovery_source_plan_id: str | None = Field(
        default=None,
        pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$",
    )
    recovery_source_plan_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    recovery_proposal_sha256: str | None = Field(
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

    @model_validator(mode="after")
    def validate_planning_retry_provenance(self) -> "PlanRecord":
        retry = (
            self.planning_retry_source_plan_id,
            self.planning_retry_source_request_sha256,
        )
        if any(value is not None for value in retry):
            if any(value is None for value in retry):
                raise ValueError("planning retry provenance is incomplete")
            if self.planning_retry_source_plan_id == self.plan_id:
                raise ValueError("planning retry cannot reference itself")
            conflicting_provenance = (
                self.parent_plan_id,
                self.parent_plan_sha256,
                self.forked_from_plan_id,
                self.forked_from_plan_sha256,
                self.continued_from_plan_id,
                self.continued_from_plan_sha256,
                self.continuation_message_sha256,
                self.recovery_source_plan_id,
                self.recovery_source_plan_sha256,
                self.recovery_proposal_sha256,
                self.revision_instruction_sha256,
            )
            if (
                any(value is not None for value in conflicting_provenance)
                or self.revision_instruction
                or self.library_input_binding is not None
            ):
                raise ValueError(
                    "planning retry cannot also carry revision, fork, continuation, "
                    "recovery, or library provenance"
                )
            if self.request_sha256 is None:
                raise ValueError("planning retry request hash is required")
            if self.revision_number < 2:
                raise ValueError("planning retry revision number must be at least two")
        return self


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

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return validate_new_display_name(value)


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

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return validate_new_display_name(value)


class TaskTemplateFromPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    confirmed: Literal[True]

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return validate_new_display_name(value)


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
    origin: Literal["operator", "automatic_experience"] = "operator"
    generation_key: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_terminal_event_id: str | None = Field(
        default=None,
        pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$",
    )
    source_terminal_event_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    created_at: str = Field(default_factory=utc_now)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relative_path: str = Field(min_length=1, max_length=512)


class WorkspaceMemoryView(WorkspaceMemoryVersion):
    """Operator view: immutable content plus ledger-derived lifecycle state."""

    state: Literal["candidate", "approved", "superseded", "revoked", "dismissed"]
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

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return validate_new_display_name(value)


class ProcessMemoryProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=120)
    confirmed: Literal[True]

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        return validate_optional_new_display_name(value)


class WorkspaceMemoryDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=500)
    expected_content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    expected_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
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
        "task_recovery_stall_detected",
        "task_recovery_diagnosed",
        "task_recovery_diagnosis_failed",
        "task_recovery_action_started",
        "task_recovery_action_finished",
        "task_recovery_reconciliation_failed",
        "task_recovery_escalated",
        "task_recovery_repair_work_requested",
        "task_recovery_repair_work_created",
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
