"""Fail-closed strict Agent Runtime state and filesystem primitives."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from opswitness.artifacts import publish_blob, verify_blob
from opswitness.console.schemas import ContractControl, TaskPlanV2

StrictStageStatus = Literal[
    "not_started",
    "preparing",
    "running",
    "awaiting_approval",
    "awaiting_input",
    "stop_requested",
    "stopped",
    "completed",
    "failed",
]

_TERMINAL = {"stopped", "completed", "failed"}
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "not_started": frozenset({"preparing", "stop_requested"}),
    "preparing": frozenset({"running", "failed", "stop_requested"}),
    "running": frozenset(
        {
            "awaiting_approval",
            "awaiting_input",
            "completed",
            "failed",
            "stop_requested",
        }
    ),
    "awaiting_approval": frozenset({"running", "failed", "stop_requested"}),
    "awaiting_input": frozenset({"running", "failed", "stop_requested"}),
    "stop_requested": frozenset({"stopped", "failed"}),
    "stopped": frozenset(),
    "completed": frozenset(),
    "failed": frozenset(),
}


@dataclass(frozen=True)
class StrictStageRecord:
    stage_order: int
    agent_id: str
    status: StrictStageStatus = "not_started"
    attempt: int = 1
    loop_iteration: int = 0


@dataclass(frozen=True)
class HandoffReceipt:
    source_agent_id: str
    target_agent_id: str
    output_id: str
    sha256: str
    size: int
    cas_path: str


@dataclass(frozen=True)
class BrokerDecision:
    stage_order: int
    agent_id: str
    operation: str
    allowed: bool
    approval_required: bool
    scope: str


@runtime_checkable
class StrictStageAdapter(Protocol):
    """Required adapter seam; identity comes from OpsWitness, never the model."""

    def strict_runtime_descriptor(self) -> dict[str, Any]: ...

    def launch_strict_stage(
        self,
        *,
        plan_id: str,
        plan_sha256: str,
        agent_id: str,
        stage_order: int,
        workspace: Path,
        envelope_json: str,
        envelope_sha256: str,
    ) -> dict[str, Any]: ...

    def revoke_stage_authorization(self, stage_handle: str) -> bool: ...

    def request_stage_stop(self, stage_handle: str) -> bool: ...


def strict_runtime_available(adapter: object) -> bool:
    return isinstance(adapter, StrictStageAdapter)


class StrictRuntimeCoordinator:
    """Hard state transitions, isolation, bounded retries, handoffs, and stop."""

    def __init__(
        self,
        *,
        plan: TaskPlanV2,
        execution_root: Path,
        cas_root: Path,
    ) -> None:
        if plan.runtime_mode != "strict":
            raise ValueError("strict coordinator requires a strict plan")
        self.plan = plan
        self.execution_root = execution_root.expanduser()
        self.cas_root = cas_root.expanduser()
        self.records = {
            stage.order: StrictStageRecord(
                stage_order=stage.order,
                agent_id=stage.owner_agent_id,
            )
            for stage in plan.stages
        }

    def transition(
        self,
        stage_order: int,
        status: StrictStageStatus,
    ) -> StrictStageRecord:
        record = self.records[stage_order]
        if status not in _ALLOWED_TRANSITIONS[record.status]:
            raise ValueError(
                f"invalid strict stage transition: {record.status} -> {status}"
            )
        if status == "preparing":
            if any(
                row.status != "completed"
                for order, row in self.records.items()
                if order < stage_order
            ):
                raise ValueError("strict stages must start in reviewed plan order")
            if any(
                row.status not in _TERMINAL | {"not_started"}
                for order, row in self.records.items()
                if order != stage_order
            ):
                raise ValueError("only one strict Agent stage may be active")
        updated = StrictStageRecord(
            stage_order=record.stage_order,
            agent_id=record.agent_id,
            status=status,
            attempt=record.attempt,
            loop_iteration=record.loop_iteration,
        )
        self.records[stage_order] = updated
        return updated

    def record_retry(
        self,
        stage_order: int,
        error_category: str,
        *,
        side_effect_started: bool,
    ) -> StrictStageRecord:
        record = self.records[stage_order]
        agent = next(
            row for row in self.plan.agents if row.agent_id == record.agent_id
        )
        retry = agent.contract.retry
        if record.status not in {"preparing", "running"}:
            raise ValueError("strict retry requires an active stage")
        if side_effect_started:
            raise ValueError("non-idempotent side effects are never automatically retried")
        if error_category not in retry.retryable_errors:
            raise ValueError("error category is not retryable")
        if record.attempt >= retry.max_attempts:
            raise ValueError("strict retry attempt limit reached")
        updated = StrictStageRecord(
            stage_order=record.stage_order,
            agent_id=record.agent_id,
            status="preparing",
            attempt=record.attempt + 1,
            loop_iteration=record.loop_iteration,
        )
        self.records[stage_order] = updated
        return updated

    def retry_delay_seconds(self, stage_order: int) -> int:
        record = self.records[stage_order]
        agent = next(
            row for row in self.plan.agents if row.agent_id == record.agent_id
        )
        return min(
            300,
            agent.contract.retry.backoff_seconds
            * (2 ** max(0, record.attempt - 2)),
        )

    def record_loop_iteration(
        self,
        stage_order: int,
        *,
        target_agent_id: str,
    ) -> StrictStageRecord:
        record = self.records[stage_order]
        loops = [
            loop
            for loop in self.plan.collaboration_loops
            if loop.source_agent_id == record.agent_id
            and loop.target_agent_id == target_agent_id
        ]
        if len(loops) != 1:
            raise ValueError("strict loop is not present in the reviewed contract")
        if record.loop_iteration >= loops[0].max_iterations:
            raise ValueError("strict collaboration loop limit reached")
        updated = StrictStageRecord(
            stage_order=record.stage_order,
            agent_id=record.agent_id,
            status=record.status,
            attempt=record.attempt,
            loop_iteration=record.loop_iteration + 1,
        )
        self.records[stage_order] = updated
        return updated

    def stage_timeout_seconds(self, stage_order: int) -> int:
        record = self.records[stage_order]
        agent = next(
            row for row in self.plan.agents if row.agent_id == record.agent_id
        )
        return agent.contract.stop.timeout_seconds

    def stage_timed_out(
        self,
        stage_order: int,
        *,
        elapsed_seconds: float,
    ) -> bool:
        if elapsed_seconds < 0:
            raise ValueError("strict stage elapsed time cannot be negative")
        return elapsed_seconds >= self.stage_timeout_seconds(stage_order)

    def request_stop(self, stage_order: int) -> StrictStageRecord:
        return self.transition(stage_order, "stop_requested")

    def confirm_stopped(
        self,
        stage_order: int,
        *,
        authorization_revoked: bool,
        runtime_confirmed: bool,
    ) -> StrictStageRecord:
        if not authorization_revoked or not runtime_confirmed:
            return self.records[stage_order]
        return self.transition(stage_order, "stopped")

    def private_workspace(self, stage_order: int) -> Path:
        record = self.records[stage_order]
        if self.execution_root.is_symlink():
            raise ValueError("strict workspace cannot be a symlink")
        self.execution_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root = self.execution_root.resolve(strict=True)
        path = root
        for segment in ("agents", record.agent_id, f"stage-{stage_order}"):
            path /= segment
            if path.is_symlink():
                raise ValueError("strict workspace cannot contain a symlink")
            path.mkdir(exist_ok=True, mode=0o700)
            if path.resolve(strict=True) != path:
                raise ValueError("strict workspace identity changed")
        os.chmod(path, 0o700)
        return path

    def copy_approved_input(
        self,
        *,
        source: Path,
        stage_order: int,
        relative_target: str,
        expected_sha256: str,
    ) -> Path:
        workspace = self.private_workspace(stage_order)
        source_fd = os.open(
            source,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            before = os.fstat(source_fd)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("strict input must be a regular file")
            digest = hashlib.sha256()
            data = bytearray()
            while chunk := os.read(source_fd, 1024 * 1024):
                digest.update(chunk)
                data.extend(chunk)
            after = os.fstat(source_fd)
        finally:
            os.close(source_fd)
        if (
            before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or digest.hexdigest() != expected_sha256
        ):
            raise ValueError("strict input digest or identity changed")
        target = workspace / relative_target
        root = workspace.resolve(strict=True)
        resolved = target.resolve(strict=False)
        if resolved != root and root not in resolved.parents:
            raise ValueError("strict input target escapes the private workspace")
        if target.is_symlink():
            raise ValueError("strict input target cannot be a symlink")
        cursor = workspace
        for segment in Path(relative_target).parent.parts:
            cursor /= segment
            if cursor.is_symlink():
                raise ValueError("strict input target cannot contain a symlink")
            cursor.mkdir(exist_ok=True, mode=0o700)
        temporary = target.with_name(f".{target.name}.copy")
        if temporary.exists() or temporary.is_symlink():
            raise ValueError("strict input temporary target already exists")
        target_fd = os.open(
            temporary,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            view = memoryview(data)
            while view:
                written = os.write(target_fd, view)
                view = view[written:]
            os.fsync(target_fd)
            os.replace(temporary, target)
        finally:
            os.close(target_fd)
            if temporary.exists():
                temporary.unlink()
        return target

    def capture_handoff(
        self,
        *,
        source_agent_id: str,
        target_agent_id: str,
        output_id: str,
        source: Path,
    ) -> HandoffReceipt:
        source_agent = next(
            agent for agent in self.plan.agents if agent.agent_id == source_agent_id
        )
        if target_agent_id not in source_agent.contract.handoff.allowed_target_agent_ids:
            raise ValueError("strict handoff target is not allowed by the contract")
        outputs = [
            output
            for output in source_agent.contract.outputs
            if output.output_id == output_id
        ]
        if len(outputs) != 1:
            raise ValueError("strict handoff output is not owned by the source Agent")
        if source.is_symlink() or not source.is_file():
            raise ValueError("strict handoff source must be a regular non-symlink file")
        expected_sources = {
            (
                self.private_workspace(stage.order)
                / outputs[0].relative_path
            ).resolve(strict=False)
            for stage in self.plan.stages
            if stage.owner_agent_id == source_agent_id
        }
        if source.resolve(strict=True) not in expected_sources:
            raise ValueError(
                "strict handoff source is outside the source Agent output contract"
            )
        digest, size, stored = publish_blob(source, self.cas_root)
        if verify_blob(self.cas_root, digest, size).get("ok") is not True:
            raise ValueError("strict handoff CAS verification failed")
        return HandoffReceipt(
            source_agent_id=source_agent_id,
            target_agent_id=target_agent_id,
            output_id=output_id,
            sha256=digest,
            size=size,
            cas_path=str(stored),
        )


class StrictRuntimeBroker:
    """Fail-closed broker decisions for strict-mode managed side effects."""

    def __init__(
        self,
        *,
        coordinator: StrictRuntimeCoordinator,
        run_approval_mode: Literal["automatic", "automatic_safe", "manual_all"],
    ) -> None:
        self.coordinator = coordinator
        self.run_approval_mode = run_approval_mode

    def _agent_for_stage(self, stage_order: int) -> Any:
        record = self.coordinator.records[stage_order]
        return next(
            agent
            for agent in self.coordinator.plan.agents
            if agent.agent_id == record.agent_id
        )

    def _decision(
        self,
        *,
        stage_order: int,
        operation: str,
        policy: ContractControl,
        scope: str,
        approval_granted: bool,
    ) -> BrokerDecision:
        agent = self._agent_for_stage(stage_order)
        approval_required = (
            policy == ContractControl.ALWAYS_ASK
            or (
                policy == ContractControl.INHERIT_RUN_MODE
                and self.run_approval_mode != "automatic"
            )
        )
        if policy == ContractControl.DENY:
            raise PermissionError(f"strict Agent Contract denies {operation}")
        if approval_required and not approval_granted:
            raise PermissionError(
                f"strict Agent Contract requires one approval for {operation}"
            )
        return BrokerDecision(
            stage_order=stage_order,
            agent_id=agent.agent_id,
            operation=operation,
            allowed=True,
            approval_required=approval_required,
            scope=scope,
        )

    def authorize_file_write(
        self,
        *,
        stage_order: int,
        relative_path: str,
        approval_granted: bool = False,
    ) -> BrokerDecision:
        agent = self._agent_for_stage(stage_order)
        if relative_path not in agent.contract.data_scope.allowed_relative_paths:
            raise PermissionError("strict file path is outside the Agent data scope")
        workspace = self.coordinator.private_workspace(stage_order)
        target = workspace / relative_path
        root = workspace.resolve(strict=True)
        resolved = target.resolve(strict=False)
        if resolved != root and root not in resolved.parents:
            raise PermissionError("strict file path escapes the private workspace")
        cursor = workspace
        for segment in Path(relative_path).parts:
            cursor /= segment
            if cursor.is_symlink():
                raise PermissionError("strict file path contains a symlink")
            if not cursor.exists():
                break
        return self._decision(
            stage_order=stage_order,
            operation="file_write",
            policy=agent.contract.side_effects.file_write,
            scope=relative_path,
            approval_granted=approval_granted,
        )

    def authorize_managed_network(
        self,
        *,
        stage_order: int,
        domain: str,
        approval_granted: bool = False,
    ) -> BrokerDecision:
        agent = self._agent_for_stage(stage_order)
        if domain not in agent.contract.data_scope.managed_network_domains:
            raise PermissionError("strict network domain is outside the exact allowlist")
        return self._decision(
            stage_order=stage_order,
            operation="managed_network",
            policy=agent.contract.side_effects.managed_network,
            scope=domain,
            approval_granted=approval_granted,
        )

    def authorize_operator_input(
        self,
        *,
        stage_order: int,
        approval_granted: bool = False,
    ) -> BrokerDecision:
        agent = self._agent_for_stage(stage_order)
        return self._decision(
            stage_order=stage_order,
            operation="operator_input",
            policy=agent.contract.side_effects.operator_input,
            scope="single_bounded_question",
            approval_granted=approval_granted,
        )

    def authorize_external_side_effect(
        self,
        *,
        stage_order: int,
        operation: Literal["send", "publish", "delete"],
        approval_granted: bool = False,
    ) -> BrokerDecision:
        agent = self._agent_for_stage(stage_order)
        policy = getattr(agent.contract.side_effects, operation)
        return self._decision(
            stage_order=stage_order,
            operation=operation,
            policy=policy,
            scope="reviewed_managed_tool",
            approval_granted=approval_granted,
        )

    @staticmethod
    def authorize_shell_network() -> None:
        raise PermissionError(
            "arbitrary Shell networking is unsupported without a reliable process sandbox"
        )
