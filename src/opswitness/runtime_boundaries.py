"""Stable replacement seams for the desktop runtime stack.

The ledger, CAS, Work identifiers, and HTTP schemas stay authoritative on the
OpsWitness side of these protocols.  AionCore and Paperclip are the Alpha
adapters; later built-in implementations must satisfy the same contracts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Literal, Protocol, runtime_checkable

from opswitness.console.aionui import EphemeralSession
from opswitness.console.providers import LocalProviderName
from opswitness.console.schemas import (
    PlanRequest,
    RecoveryModelDiagnosis,
    TaskPlan,
    TaskPlanDocument,
)


@runtime_checkable
class AgentRuntime(Protocol):
    """Execution/runtime capabilities consumed by the console service."""

    def health(self) -> dict[str, Any]: ...

    def list_assistants(self) -> list[dict[str, Any]]: ...

    def list_managed_agents(self) -> list[dict[str, Any]]: ...

    def local_provider_registered(self, provider: LocalProviderName) -> bool: ...

    def ensure_local_provider(self, provider: LocalProviderName, models: list[str]) -> str: ...

    def list_teams(self) -> list[dict[str, Any]]: ...

    def delete_team(self, team_id: str) -> None: ...

    def run_control_state(
        self,
        team_id: str,
        expected_run_id: str | None,
    ) -> dict[str, Any]: ...

    def pause_team_run(self, team_id: str, run_id: str) -> dict[str, Any]: ...

    def cancel_team_run(self, team_id: str, run_id: str) -> dict[str, Any]: ...

    def resume_team_run(
        self,
        team_id: str,
        *,
        marker: str,
        plan_id: str,
        plan_sha256: str,
    ) -> dict[str, Any]: ...

    def conversation_contains_marker(self, conversation_id: str, marker: str) -> bool: ...

    def list_confirmations(self, conversation_id: str) -> list[dict[str, str]]: ...

    def resolve_confirmation(
        self,
        conversation_id: str,
        call_id: str,
        decision: Literal["approve", "reject"],
        *,
        expected_confirmation: dict[str, str] | None = None,
    ) -> dict[str, str]: ...

    def send_team_message(self, team_id: str, content: str) -> dict[str, Any]: ...

    def stale_ephemeral_sessions(self) -> list[EphemeralSession]: ...

    def recover_ephemeral_session(self, session: EphemeralSession) -> dict[str, bool]: ...

    def generate_plan(
        self,
        plan_id: str,
        request: PlanRequest,
        workflow_catalog: list[dict[str, Any]],
        progress: Callable[[str, int], None] | None = None,
        *,
        assistant_id: str | None = None,
        previous_plan: TaskPlan | None = None,
        revision_instruction: str = "",
        runtime_capabilities: list[dict[str, Any]] | None = None,
        blueprint: dict[str, Any] | None = None,
        memory_snapshot: list[dict[str, Any]] | None = None,
        planning_attachments: list[dict[str, Any]] | None = None,
    ) -> TaskPlan: ...

    def summarize_mail(self, job_id: str, messages: list[dict[str, str]]) -> str: ...

    def generate_knowledge_cards(
        self,
        job_id: str,
        prompt: str,
        *,
        assistant_id: str,
    ) -> str: ...

    def run_onboarding_json(
        self,
        owner_id: str,
        *,
        agent_name: str,
        assistant_id: str,
        model: str,
        prompt: str,
    ) -> dict[str, Any]: ...

    def diagnose_recovery(
        self,
        diagnosis_id: str,
        telemetry: dict[str, Any],
        *,
        assistant_id: str,
    ) -> RecoveryModelDiagnosis: ...

    def dispatch_plan(
        self,
        *,
        plan_id: str,
        plan: TaskPlanDocument,
        objective: str,
        constraints: str,
        workspace: Path,
        paperclip_issue_id: str,
        materials: list[dict[str, Any]] | None = None,
        agent_envelopes: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...

    def execution_snapshot(
        self,
        team_id: str,
        conversation_ids: list[str],
        *,
        agent_sessions: list[dict[str, str]] | None = None,
        planned_stages: list[dict[str, Any]] | None = None,
        existing_stage_progress: list[dict[str, Any]] | None = None,
        observed_after: str | None = None,
    ) -> dict[str, Any]: ...


@runtime_checkable
class GovernanceProjection(Protocol):
    """Governance view/command surface currently supplied by Paperclip."""

    def list_issues(self) -> list[dict[str, Any]]: ...

    def create_issue(self, title: str, description: str) -> dict[str, Any]: ...

    def list_approvals(self, status: str | None = None) -> list[dict[str, Any]]: ...

    def get_approval(self, approval_id: str) -> dict[str, Any]: ...

    def create_board_approval(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def resolve_approval(
        self,
        approval_id: str,
        decision: Literal["approve", "reject"],
        decision_note: str | None = None,
    ) -> dict[str, Any]: ...


GovernanceProjectionFactory = Callable[[], GovernanceProjection]
