"""Agent Contract normalization, preview, diff, and execution envelopes.

This module is deliberately free of runtime/network calls. The console service
supplies reviewed memory documents and runtime descriptors, then preview and
dispatch call the same envelope builder.
"""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Literal

from opswitness.console.schemas import (
    AgentCollaborationLoopV2,
    AgentContractOutput,
    AgentContractV1,
    AgentDataScope,
    AgentEscalationPolicy,
    AgentExecutionEnvelopeView,
    AgentHandoffPolicy,
    AgentMemoryPolicy,
    AgentSideEffectPolicy,
    AgentStopPolicy,
    AgentToolRule,
    ContractControl,
    TaskPlanV1,
    TaskPlanV2,
    TaskPlanV2Agent,
    TaskPlanV2Stage,
)

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

PLATFORM_MANAGED_TOOLS = (
    "ListMcpResourcesTool",
    "ToolSearch",
    "mcp__aionui-team__team_list_assistants",
    "mcp__aionui-team__team_members",
    "mcp__aionui-team__team_send_message",
    "mcp__aionui-team__team_task_create",
    "mcp__aionui-team__team_task_list",
    "mcp__aionui-team__team_task_update",
    "mcp__opswitness__qd_artifact_verify",
    "mcp__opswitness__qd_artifacts",
    "mcp__opswitness__qd_request_input",
)

_CONTROL_RANK = {
    ContractControl.INHERIT_RUN_MODE.value: 0,
    ContractControl.ALWAYS_ASK.value: 1,
    ContractControl.DENY.value: 2,
}

_MANAGED_SIDE_EFFECT_TOOLS = {
    "mcp__opswitness__qd_request_input": "operator_input",
}

EnforcementLevel = Literal[
    "software_enforced",
    "runtime_approval",
    "execution_instruction",
    "unsupported",
]


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def stable_agent_id(parent_plan_sha256: str, reference: str) -> str:
    """Create a deterministic server-issued opaque Agent id for one parent draft."""
    digest = hashlib.sha256(
        f"opswitness-agent-v1:{parent_plan_sha256}:{reference}".encode()
    ).digest()
    value = int.from_bytes(digest[:17], "big") >> 6
    return "".join(_CROCKFORD[(value >> (5 * (25 - index))) & 31] for index in range(26))


def _artifact_path(label: str, index: int) -> str:
    safe = "".join(
        character.casefold() if character.isascii() and character.isalnum() else "-"
        for character in label
    )
    safe = "-".join(part for part in safe.split("-") if part)[:48]
    return f"artifacts/{safe or f'output-{index}'}.json"


def _is_exact_tool_identifier(value: str) -> bool:
    return bool(value) and all(
        ord(character) < 128
        and character
        in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.:-"
        for character in value
    )


def project_v1_to_v2(
    plan: TaskPlanV1,
    *,
    parent_plan_sha256: str,
    memory_version_ids: Iterable[str] = (),
    attachment_ids: Iterable[str] = (),
) -> TaskPlanV2:
    """Build a conservative reviewed draft without changing the historical v1."""
    ids = {
        agent.name: stable_agent_id(
            parent_plan_sha256,
            f"legacy:{index}:{agent.name}",
        )
        for index, agent in enumerate(plan.agents)
    }
    reporting = plan.effective_reporting_lines()
    memory_ids = list(dict.fromkeys(memory_version_ids))
    attachments = list(dict.fromkeys(attachment_ids))
    delivery_agents = {
        agent.name for agent in plan.agents if agent.role.value == "reporter"
    } or {
        agent.name for agent in plan.agents if agent.role.value == "lead"
    }
    agents: list[TaskPlanV2Agent] = []
    for index, agent in enumerate(plan.agents):
        owned_stages = [stage for stage in plan.stages if stage.owner == agent.name]
        outputs = [
            AgentContractOutput(
                output_id=f"legacy_output_{index + 1}_{artifact_index}",
                label=artifact,
                relative_path=_artifact_path(artifact, artifact_index),
                acceptance_criteria=[
                    stage.outcome for stage in owned_stages if stage.checkpoint
                ],
                required=True,
            )
            for artifact_index, artifact in enumerate(plan.artifacts, start=1)
            if agent.name in delivery_agents
        ]
        output_paths = [item.relative_path for item in outputs]
        memory = (
            AgentMemoryPolicy(mode="selected", version_ids=memory_ids)
            if memory_ids and agent.role.value == "lead"
            else AgentMemoryPolicy()
        )
        contract = AgentContractV1(
            instructions=agent.responsibility,
            prohibitions=[
                "Do not expand beyond the reviewed Work objective and constraints.",
                "Do not claim a business result from process completion alone.",
            ],
            outputs=outputs,
            acceptance_criteria=[stage.outcome for stage in owned_stages],
            tool_rules=[
                AgentToolRule(
                    tool_name=tool,
                    policy=ContractControl.ALWAYS_ASK,
                )
                for tool in dict.fromkeys(
                    [
                        *PLATFORM_MANAGED_TOOLS,
                        *[
                            candidate
                            for candidate in plan.tools
                            if _is_exact_tool_identifier(candidate)
                        ],
                    ]
                )
            ],
            data_scope=AgentDataScope(
                allowed_relative_paths=output_paths,
                attachment_ids=attachments if agent.role.value == "lead" else [],
            ),
            side_effects=AgentSideEffectPolicy(),
            memory=memory,
            handoff=AgentHandoffPolicy(
                allowed_target_agent_ids=[
                    ids[candidate.name]
                    for candidate in plan.agents
                    if reporting.get(candidate.name) == agent.name
                ],
                acceptance_criteria=[],
                require_cas_receipt=True,
            ),
            escalation=AgentEscalationPolicy(
                target_agent_id=(
                    ids[parent_name]
                    if (parent_name := reporting.get(agent.name)) is not None
                    else None
                ),
                conditions=["The contract cannot be completed without expanding scope."],
            ),
            approval_checkpoints=list(plan.approvals),
            stop=AgentStopPolicy(
                timeout_seconds=max(
                    30,
                    min(86400, plan.estimated_duration_minutes * 60),
                ),
                stop_conditions=[
                    "A required approval is rejected.",
                    "A required artifact digest or acceptance check fails.",
                ],
            ),
        )
        model = agent.model or "default"
        agents.append(
            TaskPlanV2Agent(
                agent_id=ids[agent.name],
                name=agent.name,
                role=agent.role,
                responsibility=agent.responsibility,
                runtime=agent.runtime,
                model=model,
                model_binding="default" if model == "default" else "exact",
                runtime_reason=agent.runtime_reason,
                reports_to_agent_id=(
                    ids[parent_name]
                    if (parent_name := reporting.get(agent.name)) is not None
                    else None
                ),
                contract=contract,
            )
        )
    return TaskPlanV2(
        title=plan.title,
        summary=plan.summary,
        execution_profile=plan.execution_profile,
        agents=agents,
        collaboration_loops=[
            AgentCollaborationLoopV2(
                source_agent_id=ids[loop.source_agent],
                target_agent_id=ids[loop.target_agent],
                condition=loop.condition,
                max_iterations=loop.max_iterations,
            )
            for loop in plan.collaboration_loops
        ],
        stages=[
            TaskPlanV2Stage(
                order=stage.order,
                title=stage.title,
                owner_agent_id=ids[stage.owner],
                outcome=stage.outcome,
                checkpoint=stage.checkpoint,
            )
            for stage in plan.stages
        ],
        cadence=plan.cadence,
        tools=list(plan.tools),
        approvals=list(plan.approvals),
        artifacts=list(plan.artifacts),
        risks=list(plan.risks),
        estimated_duration_minutes=plan.estimated_duration_minutes,
        update_policy=plan.update_policy,
    )


def normalize_v2_draft(
    *,
    parent_plan: TaskPlanV1 | TaskPlanV2,
    parent_plan_sha256: str,
    raw_draft: dict[str, Any] | None,
    memory_version_ids: Iterable[str] = (),
    attachment_ids: Iterable[str] = (),
) -> TaskPlanV2:
    """Normalize new:* references and validate the complete v2 plan once."""
    if raw_draft is None:
        if isinstance(parent_plan, TaskPlanV2):
            return parent_plan.model_copy(deep=True)
        return project_v1_to_v2(
            parent_plan,
            parent_plan_sha256=parent_plan_sha256,
            memory_version_ids=memory_version_ids,
            attachment_ids=attachment_ids,
        )
    payload = deepcopy(raw_draft)
    if payload.get("schema_version") != 2:
        raise ValueError("Agent Contract drafts must use schema_version 2")
    raw_agents = payload.get("agents")
    if not isinstance(raw_agents, list):
        raise ValueError("Agent Contract draft agents are unavailable")
    if isinstance(parent_plan, TaskPlanV2):
        allowed_existing_ids = {agent.agent_id for agent in parent_plan.agents}
    else:
        allowed_existing_ids = {
            agent.agent_id
            for agent in project_v1_to_v2(
                parent_plan,
                parent_plan_sha256=parent_plan_sha256,
                memory_version_ids=memory_version_ids,
                attachment_ids=attachment_ids,
            ).agents
        }
    replacements: dict[str, str] = {}
    observed_new_tokens: set[str] = set()
    for index, agent in enumerate(raw_agents):
        if not isinstance(agent, dict):
            raise ValueError("Agent Contract draft agents are invalid")
        value = agent.get("agent_id")
        if value is None:
            value = f"new:{index + 1}"
        if isinstance(value, str) and value.startswith("new:"):
            if value in observed_new_tokens:
                raise ValueError("new Agent draft ids must be unique")
            observed_new_tokens.add(value)
            issued = stable_agent_id(parent_plan_sha256, f"new:{index + 1}")
            replacements[value] = issued
            agent["agent_id"] = issued
        elif isinstance(value, str) and value not in allowed_existing_ids:
            issued = stable_agent_id(parent_plan_sha256, f"new:{index + 1}")
            if value != issued:
                raise ValueError("Agent ids must be issued by the server")
    if replacements:
        def replace(value: Any) -> Any:
            if isinstance(value, str):
                return replacements.get(value, value)
            if isinstance(value, list):
                return [replace(item) for item in value]
            if isinstance(value, dict):
                return {key: replace(item) for key, item in value.items()}
            return value

        payload = replace(payload)
    normalized = TaskPlanV2.model_validate(payload)
    return normalized


def _pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def json_pointer_diff(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    """Return deterministic, field-level changes with policy direction labels."""
    if isinstance(before, dict) and isinstance(after, dict):
        rows: list[dict[str, Any]] = []
        for key in sorted(set(before) | set(after)):
            child = f"{path}/{_pointer_token(str(key))}"
            if key not in before:
                rows.append(_diff_row(child, "added", None, after[key]))
            elif key not in after:
                rows.append(_diff_row(child, "removed", before[key], None))
            else:
                rows.extend(json_pointer_diff(before[key], after[key], child))
        return rows
    if isinstance(before, list) and isinstance(after, list):
        rows = []
        for index in range(max(len(before), len(after))):
            child = f"{path}/{index}"
            if index >= len(before):
                rows.append(_diff_row(child, "added", None, after[index]))
            elif index >= len(after):
                rows.append(_diff_row(child, "removed", before[index], None))
            else:
                rows.extend(json_pointer_diff(before[index], after[index], child))
        return rows
    return [] if before == after else [_diff_row(path or "/", "changed", before, after)]


def _diff_row(
    path: str,
    change: Literal["added", "removed", "changed"],
    before: Any,
    after: Any,
) -> dict[str, Any]:
    direction: Literal["tighter", "looser", "neutral"] = "neutral"
    if isinstance(before, str) and isinstance(after, str):
        if before in _CONTROL_RANK and after in _CONTROL_RANK:
            if _CONTROL_RANK[after] > _CONTROL_RANK[before]:
                direction = "tighter"
            elif _CONTROL_RANK[after] < _CONTROL_RANK[before]:
                direction = "looser"
    elif change == "added" and (
        "/prohibitions/" in path
        or "/approval_checkpoints/" in path
        or "/stop_conditions/" in path
    ):
        direction = "tighter"
    elif change == "removed" and (
        "/prohibitions/" in path
        or "/approval_checkpoints/" in path
        or "/stop_conditions/" in path
    ):
        direction = "looser"
    return {
        "path": path,
        "change": change,
        "direction": direction,
        "before": before,
        "after": after,
    }


def enforcement_map(plan: TaskPlanV2) -> dict[str, EnforcementLevel]:
    strict = plan.runtime_mode == "strict"
    return {
        "instructions": "execution_instruction",
        "tool_policy": "software_enforced" if strict else "runtime_approval",
        "operator_input_policy": "software_enforced" if strict else "runtime_approval",
        "file_write_policy": "software_enforced" if strict else "execution_instruction",
        "managed_network_policy": "software_enforced" if strict else "unsupported",
        "send_publish_delete_policy": (
            "software_enforced" if strict else "execution_instruction"
        ),
        "memory_selection": "software_enforced",
        "required_artifacts": "software_enforced",
        "data_scope": "software_enforced" if strict else "execution_instruction",
        "handoff": "software_enforced" if strict else "execution_instruction",
        "loop_limit": "software_enforced" if strict else "execution_instruction",
        "retry_limit": "software_enforced" if strict else "execution_instruction",
        "stop_policy": "software_enforced" if strict else "execution_instruction",
        "arbitrary_shell_network": "unsupported",
    }


def build_agent_execution_envelope(
    *,
    plan_sha256: str,
    objective: str,
    constraints: str,
    plan: TaskPlanV2,
    agent: TaskPlanV2Agent,
    memory_documents: list[dict[str, Any]],
    material_descriptors: list[dict[str, Any]],
    runtime_descriptor: dict[str, Any],
) -> AgentExecutionEnvelopeView:
    """Build the one canonical payload shared by preview and actual dispatch."""
    owned_stages = [
        stage.model_dump(mode="json")
        for stage in plan.stages
        if stage.owner_agent_id == agent.agent_id
    ]
    payload = {
        "schema_version": 1,
        "plan_sha256": plan_sha256,
        "agent": agent.model_dump(mode="json"),
        "objective": objective,
        "constraints": constraints,
        "owned_stages": owned_stages,
        "collaboration_loops": [
            loop.model_dump(mode="json")
            for loop in plan.collaboration_loops
            if agent.agent_id in {loop.source_agent_id, loop.target_agent_id}
        ],
        "selected_memory": memory_documents,
        "materials": material_descriptors,
        "runtime": runtime_descriptor,
        "platform_safety": {
            "hidden_provider_instructions_visible": False,
            "business_result_requires_human_signoff": True,
            "unknown_agent_or_tool": "deny",
            "credentials_must_not_enter_logs_or_artifacts": True,
        },
    }
    encoded = canonical_json(payload)
    delivery: Literal[
        "exact_lead_payload",
        "exact_plan_packet",
        "strict_runtime",
    ]
    if plan.runtime_mode == "strict":
        delivery = "strict_runtime"
    elif agent.role.value == "lead":
        delivery = "exact_lead_payload"
    else:
        delivery = "exact_plan_packet"
    return AgentExecutionEnvelopeView(
        agent_id=agent.agent_id,
        agent_name=agent.name,
        delivery=delivery,
        canonical_json=encoded,
        sha256=hashlib.sha256(encoded.encode()).hexdigest(),
        enforcement=enforcement_map(plan),
    )


def validate_contract_workspace_paths(
    plan: TaskPlanV2,
    workspace: Path,
    *,
    create_workspace: bool = False,
) -> None:
    """Reject traversal and any existing symlink component below the workspace."""
    workspace = workspace.expanduser()
    if workspace.is_symlink():
        raise ValueError("execution workspace must not be a symlink")
    if not workspace.exists():
        if not create_workspace:
            return
        workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    root = workspace.resolve(strict=True)
    paths = {
        path
        for agent in plan.agents
        for path in [
            *agent.contract.data_scope.allowed_relative_paths,
            *[
                item.relative_path
                for item in agent.contract.inputs
                if item.relative_path is not None
            ],
            *[item.relative_path for item in agent.contract.outputs],
        ]
    }
    for relative in paths:
        candidate = workspace / relative
        cursor = workspace
        for part in Path(relative).parts:
            cursor /= part
            if cursor.is_symlink():
                raise ValueError("Agent Contract path contains a symlink")
            if not cursor.exists():
                break
        resolved = candidate.resolve(strict=False)
        if resolved != root and root not in resolved.parents:
            raise ValueError("Agent Contract path escapes the execution workspace")


def contract_tool_policy(agent: TaskPlanV2Agent, tool_name: str) -> ContractControl:
    for rule in agent.contract.tool_rules:
        if rule.tool_name == tool_name:
            return rule.policy
    return agent.contract.default_tool_policy


def contract_effective_tool_policy(
    agent: TaskPlanV2Agent,
    tool_name: str,
) -> tuple[ContractControl, str | None]:
    """Combine an exact tool rule with any software-known side-effect category."""
    tool_policy = contract_tool_policy(agent, tool_name)
    category = _MANAGED_SIDE_EFFECT_TOOLS.get(tool_name)
    if category is None:
        return tool_policy, None
    side_effect_policy = getattr(agent.contract.side_effects, category)
    return (
        max(
            (tool_policy, side_effect_policy),
            key=lambda policy: _CONTROL_RANK[str(policy)],
        ),
        category,
    )


def contract_sha256(plan: TaskPlanV2) -> str:
    return canonical_sha256(
        {
            agent.agent_id: agent.contract.model_dump(mode="json")
            for agent in sorted(plan.agents, key=lambda row: row.agent_id)
        }
    )


def ensure_content_free_audit_payload(payload: dict[str, Any]) -> None:
    """Defence in depth for Agent Contract ledger projections."""
    forbidden = {
        "instructions",
        "prohibitions",
        "memory",
        "canonical_json",
        "before",
        "after",
        "relative_path",
    }
    if forbidden.intersection(payload):
        raise ValueError("Agent Contract audit payload contains private contract content")
    encoded = canonical_json(payload)
    if any(os.sep + segment in encoded for segment in ("Users", "home", "private")):
        raise ValueError("Agent Contract audit payload contains a filesystem path")
