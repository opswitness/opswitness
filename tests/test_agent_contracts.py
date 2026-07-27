import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from opswitness.agent_contracts import (
    build_agent_execution_envelope,
    canonical_sha256,
    contract_effective_tool_policy,
    contract_tool_policy,
    ensure_content_free_audit_payload,
    json_pointer_diff,
    normalize_v2_draft,
    project_v1_to_v2,
    validate_contract_workspace_paths,
)
from opswitness.console.schemas import (
    ContractControl,
    TaskPlanV1,
    TaskPlanV2,
)
from opswitness.strict_runtime import StrictRuntimeBroker, StrictRuntimeCoordinator


def _v1_plan() -> TaskPlanV1:
    return TaskPlanV1.model_validate(
        {
            "schema_version": 1,
            "title": "Customer reply",
            "summary": "Draft and independently verify one fictional customer reply.",
            "execution_mode": "aion_team",
            "agents": [
                {
                    "name": "Writer",
                    "role": "lead",
                    "responsibility": "Draft the bounded reply.",
                    "runtime": "codex_cli",
                },
                {
                    "name": "Verifier",
                    "role": "reviewer",
                    "responsibility": "Verify every customer-facing claim.",
                    "runtime": "claude_code",
                    "reports_to": "Writer",
                },
            ],
            "stages": [
                {
                    "order": 1,
                    "title": "Draft",
                    "owner": "Writer",
                    "outcome": "A draft exists.",
                    "checkpoint": False,
                },
                {
                    "order": 2,
                    "title": "Verify",
                    "owner": "Verifier",
                    "outcome": "The claim check exists.",
                    "checkpoint": True,
                },
            ],
            "cadence": {
                "kind": "once",
                "timezone": "America/Los_Angeles",
                "local_time": None,
                "update_interval": "Once",
            },
            "tools": ["mcp__opswitness__qd_artifacts"],
            "approvals": ["Approve the file write."],
            "artifacts": ["reply"],
            "risks": ["The fictional inquiry may be incomplete."],
            "estimated_duration_minutes": 5,
            "update_policy": "Update at each checkpoint.",
        }
    )


def _v2_plan(*, strict: bool = False) -> TaskPlanV2:
    v1 = _v1_plan()
    plan = project_v1_to_v2(
        v1,
        parent_plan_sha256=canonical_sha256(v1.model_dump(mode="json")),
    )
    if strict:
        payload = plan.model_dump(mode="json")
        payload["runtime_mode"] = "strict"
        plan = TaskPlanV2.model_validate(payload)
    return plan


def test_v1_projection_is_append_only_and_server_ids_are_stable():
    plan = _v1_plan()
    before = plan.model_dump_json()
    parent_sha = canonical_sha256(plan.model_dump(mode="json"))

    first = project_v1_to_v2(plan, parent_plan_sha256=parent_sha)
    second = project_v1_to_v2(plan, parent_plan_sha256=parent_sha)

    assert plan.model_dump_json() == before
    assert [agent.agent_id for agent in first.agents] == [
        agent.agent_id for agent in second.agents
    ]
    assert first.schema_version == 2
    assert all(
        agent.contract.default_tool_policy == ContractControl.DENY
        for agent in first.agents
    )


def test_draft_normalization_replaces_new_ids_and_rejects_dangling_references():
    parent = _v1_plan()
    parent_sha = canonical_sha256(parent.model_dump(mode="json"))
    draft = project_v1_to_v2(parent, parent_plan_sha256=parent_sha).model_dump(
        mode="json"
    )
    old_ids = [agent["agent_id"] for agent in draft["agents"]]
    replacements = {old_ids[0]: "new:writer", old_ids[1]: "new:verifier"}
    encoded = json.dumps(draft)
    for old, new in replacements.items():
        encoded = encoded.replace(old, new)
    normalized = normalize_v2_draft(
        parent_plan=parent,
        parent_plan_sha256=parent_sha,
        raw_draft=json.loads(encoded),
    )
    assert all(not agent.agent_id.startswith("new:") for agent in normalized.agents)

    broken = normalized.model_dump(mode="json")
    broken["stages"][0]["owner_agent_id"] = "0" * 26
    with pytest.raises(ValidationError, match="stage owner"):
        TaskPlanV2.model_validate(broken)

    forged = normalized.model_dump(mode="json")
    forged["agents"][0]["agent_id"] = "0" * 26
    with pytest.raises(ValueError, match="issued by the server"):
        normalize_v2_draft(
            parent_plan=parent,
            parent_plan_sha256=parent_sha,
            raw_draft=forged,
        )


@pytest.mark.parametrize(
    "path",
    [
        "../secret",
        "/Users/operator/secret",
        "artifacts/../secret",
        "artifacts//reply.json",
        "~/secret",
        "artifacts\\reply.json",
    ],
)
def test_contract_paths_reject_traversal_and_noncanonical_forms(path: str):
    payload = _v2_plan().model_dump(mode="json")
    payload["agents"][0]["contract"]["outputs"][0]["relative_path"] = path
    with pytest.raises(ValidationError, match="path"):
        TaskPlanV2.model_validate(payload)


@pytest.mark.parametrize(
    "domain",
    ["https://api.example.com", "*.example.com", "API.example.com", "example.com:443"],
)
def test_managed_network_domains_require_exact_lowercase_hosts(domain: str):
    payload = _v2_plan().model_dump(mode="json")
    payload["agents"][0]["contract"]["data_scope"]["managed_network_domains"] = [
        domain
    ]
    with pytest.raises(ValidationError, match="network domain"):
        TaskPlanV2.model_validate(payload)


def test_contract_inputs_reject_dangling_or_mismatched_output_references():
    payload = _v2_plan().model_dump(mode="json")
    lead, verifier = payload["agents"]
    output_id = lead["contract"]["outputs"][0]["output_id"]
    verifier["contract"]["inputs"] = [
        {
            "input_id": "writer_result",
            "label": "Writer result",
            "relative_path": "artifacts/reply.json",
            "source_agent_id": verifier["agent_id"],
            "source_output_id": output_id,
            "required": True,
            "sha256": None,
        }
    ]
    with pytest.raises(ValidationError, match="source output"):
        TaskPlanV2.model_validate(payload)

    verifier["contract"]["inputs"][0]["source_agent_id"] = lead["agent_id"]
    assert TaskPlanV2.model_validate(payload).agents[1].contract.inputs[
        0
    ].source_output_id == output_id


def test_preview_and_dispatch_share_identical_canonical_envelope_bytes():
    plan = _v2_plan()
    agent = plan.agents[0]
    kwargs = {
        "plan_sha256": canonical_sha256(plan.model_dump(mode="json")),
        "objective": "Answer a fictional customer inquiry.",
        "constraints": "Do not send or publish.",
        "plan": plan,
        "agent": agent,
        "memory_documents": [],
        "material_descriptors": [],
        "runtime_descriptor": {
            "adapter_version": "test-adapter",
            "executable_sha256": "a" * 64,
            "status": "bound",
        },
    }
    preview = build_agent_execution_envelope(**kwargs)
    dispatch = build_agent_execution_envelope(**kwargs)

    assert preview.canonical_json == dispatch.canonical_json
    assert preview.sha256 == dispatch.sha256
    assert hashlib.sha256(preview.canonical_json.encode()).hexdigest() == preview.sha256
    assert preview.delivery == "exact_lead_payload"
    assert build_agent_execution_envelope(
        **{**kwargs, "agent": plan.agents[1]}
    ).delivery == "exact_plan_packet"


def test_contract_diff_marks_permission_direction_and_audit_stays_content_free():
    rows = json_pointer_diff(
        {"agents": [{"contract": {"side_effects": {"send": "deny"}}}]},
        {"agents": [{"contract": {"side_effects": {"send": "always_ask"}}}]},
    )
    assert rows == [
        {
            "path": "/agents/0/contract/side_effects/send",
            "change": "changed",
            "direction": "looser",
            "before": "deny",
            "after": "always_ask",
        }
    ]
    ensure_content_free_audit_payload(
        {
            "contract_sha256": "a" * 64,
            "changed_path_sha256": ["b" * 64],
            "change_count": 1,
        }
    )
    with pytest.raises(ValueError, match="private contract content"):
        ensure_content_free_audit_payload({"instructions": "private"})


def test_unknown_tools_fail_closed_and_workspace_symlinks_are_rejected(tmp_path: Path):
    plan = _v2_plan()
    assert (
        contract_tool_policy(plan.agents[0], "unknown_tool")
        == ContractControl.DENY
    )
    policy, category = contract_effective_tool_policy(
        plan.agents[0],
        "mcp__opswitness__qd_request_input",
    )
    assert (policy, category) == (ContractControl.DENY, "operator_input")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "artifacts").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="symlink"):
        validate_contract_workspace_paths(plan, workspace)


def test_strict_runtime_is_sequential_bounded_and_stop_is_confirmed(tmp_path: Path):
    plan = _v2_plan(strict=True)
    coordinator = StrictRuntimeCoordinator(
        plan=plan,
        execution_root=tmp_path / "execution",
        cas_root=tmp_path / "cas",
    )

    assert coordinator.transition(1, "preparing").status == "preparing"
    assert coordinator.transition(1, "running").status == "running"
    with pytest.raises(ValueError, match="plan order"):
        coordinator.transition(2, "preparing")
    stopped = coordinator.request_stop(1)
    assert stopped.status == "stop_requested"
    assert (
        coordinator.confirm_stopped(
            1,
            authorization_revoked=True,
            runtime_confirmed=False,
        ).status
        == "stop_requested"
    )
    assert (
        coordinator.confirm_stopped(
            1,
            authorization_revoked=True,
            runtime_confirmed=True,
        ).status
        == "stopped"
    )


def test_strict_runtime_copies_digest_bound_input_and_cas_handoff(tmp_path: Path):
    plan = _v2_plan(strict=True)
    coordinator = StrictRuntimeCoordinator(
        plan=plan,
        execution_root=tmp_path / "execution",
        cas_root=tmp_path / "cas",
    )
    source = tmp_path / "approved.txt"
    source.write_text("approved input", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    copied = coordinator.copy_approved_input(
        source=source,
        stage_order=1,
        relative_target="inputs/approved.txt",
        expected_sha256=digest,
    )
    assert copied.read_bytes() == source.read_bytes()
    with pytest.raises(ValueError, match="escapes"):
        coordinator.copy_approved_input(
            source=source,
            stage_order=1,
            relative_target="../escape.txt",
            expected_sha256=digest,
        )

    lead, verifier = plan.agents
    output = lead.contract.outputs[0]
    handoff_source = (
        coordinator.private_workspace(1) / output.relative_path
    )
    handoff_source.parent.mkdir(parents=True)
    handoff_source.write_bytes(source.read_bytes())
    receipt = coordinator.capture_handoff(
        source_agent_id=lead.agent_id,
        target_agent_id=verifier.agent_id,
        output_id=output.output_id,
        source=handoff_source,
    )
    assert receipt.sha256 == digest
    assert Path(receipt.cas_path).is_file()


def test_strict_runtime_hard_limits_retry_loop_timeout_and_broker_scope(tmp_path: Path):
    payload = _v2_plan(strict=True).model_dump(mode="json")
    lead = payload["agents"][0]
    verifier = payload["agents"][1]
    lead["contract"]["retry"] = {
        "max_attempts": 2,
        "retryable_errors": ["rate_limited"],
        "backoff_seconds": 7,
    }
    lead["contract"]["data_scope"]["managed_network_domains"] = ["api.example.com"]
    lead["contract"]["side_effects"].update(
        {
            "file_write": "always_ask",
            "managed_network": "inherit_run_mode",
            "delete": "always_ask",
        }
    )
    payload["collaboration_loops"] = [
        {
            "source_agent_id": lead["agent_id"],
            "target_agent_id": verifier["agent_id"],
            "condition": "Return once when verification fails.",
            "max_iterations": 1,
        }
    ]
    plan = TaskPlanV2.model_validate(payload)
    coordinator = StrictRuntimeCoordinator(
        plan=plan,
        execution_root=tmp_path / "execution",
        cas_root=tmp_path / "cas",
    )
    coordinator.transition(1, "preparing")
    coordinator.transition(1, "running")
    assert coordinator.stage_timeout_seconds(1) == lead["contract"]["stop"]["timeout_seconds"]
    assert coordinator.stage_timed_out(1, elapsed_seconds=10**6) is True
    assert coordinator.record_loop_iteration(
        1,
        target_agent_id=verifier["agent_id"],
    ).loop_iteration == 1
    with pytest.raises(ValueError, match="loop limit"):
        coordinator.record_loop_iteration(
            1,
            target_agent_id=verifier["agent_id"],
        )
    assert coordinator.record_retry(
        1,
        "rate_limited",
        side_effect_started=False,
    ).attempt == 2
    assert coordinator.retry_delay_seconds(1) == 7
    with pytest.raises(ValueError, match="attempt limit"):
        coordinator.record_retry(
            1,
            "rate_limited",
            side_effect_started=False,
        )

    broker = StrictRuntimeBroker(
        coordinator=coordinator,
        run_approval_mode="automatic",
    )
    output_path = lead["contract"]["outputs"][0]["relative_path"]
    with pytest.raises(PermissionError, match="requires one approval"):
        broker.authorize_file_write(stage_order=1, relative_path=output_path)
    assert broker.authorize_file_write(
        stage_order=1,
        relative_path=output_path,
        approval_granted=True,
    ).approval_required is True
    assert broker.authorize_managed_network(
        stage_order=1,
        domain="api.example.com",
    ).allowed is True
    with pytest.raises(PermissionError, match="outside the exact allowlist"):
        broker.authorize_managed_network(
            stage_order=1,
            domain="evil.example",
        )
    with pytest.raises(PermissionError, match="denies operator_input"):
        broker.authorize_operator_input(stage_order=1)
    with pytest.raises(PermissionError, match="unsupported"):
        broker.authorize_shell_network()
