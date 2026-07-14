"""Console application service: evidence-first planning, confirmation, and dispatch."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import httpx

from quarterdeck.bootstrap import load_effective_schedules
from quarterdeck.config import (
    Settings,
    clear_telegram_credentials,
    config_dir,
    resolve_api_key,
    save_mail_activation,
    save_telegram_credentials,
)
from quarterdeck.console.aionui import AionUiClient, AionUiError
from quarterdeck.console.schemas import (
    ConfirmRequest,
    ExecutionState,
    MailAuthorizationJob,
    MailAuthorizationRequest,
    MailSummaryJob,
    PlanRecord,
    PlanRequest,
    TaskPlan,
    TelegramConfigureRequest,
    utc_now,
)
from quarterdeck.console.store import PlanNotFound, PlanStore
from quarterdeck.digest import build_digest
from quarterdeck.ids import new_ulid
from quarterdeck.index import job_summary, query_runs, rebuild
from quarterdeck.ledger import Ledger
from quarterdeck.mail import authorize_mail, check_mail, mail_status
from quarterdeck.notify import alert
from quarterdeck.notify.telegram import send_telegram
from quarterdeck.paperclip import PaperclipClient, PaperclipError
from quarterdeck.workflows import start_workflow, workflow_catalog, workflow_status
from quarterdeck.watchdog import check as watchdog_check


class ConsoleConflict(ValueError):
    pass


class ConsoleUnavailable(RuntimeError):
    pass


PaperclipFactory = Callable[[], PaperclipClient]
MAIL_SUMMARY_FAILURE = "mail summary failed; run qd mail status locally"
MAIL_AUTHORIZATION_FAILURE = (
    "Gmail readonly authorization failed; inspect qd mail status locally."
)
TELEGRAM_CONFIGURATION_REJECTED = "Telegram credentials were rejected or already configured."
TELEGRAM_ENVIRONMENT_CONTROLLED = "Telegram credentials are controlled outside the console."
TELEGRAM_TEST_FAILED = "Telegram test delivery failed; inspect local diagnostics."
PLAN_GENERATION_FAILED = "plan_generation_failed"
PLAN_GENERATION_FAILED_DETAIL = "Planning failed; inspect AionUi locally and create a new plan."
EXECUTION_PLAN_INVALID = "execution_plan_invalid"
EXECUTION_PLAN_INVALID_DETAIL = "Confirmed plan integrity failed; replan before dispatch."
EXECUTION_DISPATCH_FAILED = "execution_dispatch_failed"
EXECUTION_DISPATCH_FAILED_DETAIL = (
    "Execution dispatch failed; inspect Paperclip and AionUi before replanning."
)
EXECUTION_REMOTE_FAILED_DETAIL = "Execution reported failure; inspect AionUi or workflow evidence."
EXECUTION_STATUS_UNAVAILABLE_DETAIL = (
    "Execution status is temporarily unavailable; retry from the console."
)
EXECUTION_IDENTIFIERS_MISSING_DETAIL = (
    "Execution identifiers are incomplete; inspect local evidence before replanning."
)
SCHEDULE_CONFIGURATION_INVALID_DETAIL = (
    "schedule configuration is invalid; run qd init or qd watchdog locally"
)
PLANNING_INTERRUPTED = "planning_interrupted_by_restart"
DISPATCH_INTERRUPTED = "execution_dispatch_interrupted"
PLANNING_INTERRUPTED_DETAIL = "Planning was interrupted by a console restart; create a new plan."
DISPATCH_INTERRUPTED_DETAIL = (
    "Execution dispatch was interrupted; inspect Paperclip and AionUi before replanning."
)
EPHEMERAL_RECOVERY_UNAVAILABLE = (
    "AionUi ephemeral recovery is unavailable; inspect the local console state before restarting."
)


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _mail_setup_detail(status: dict[str, Any]) -> str:
    if status.get("mcp_ready"):
        return "已就绪"
    error = str(status.get("error") or "").lower()
    if "disabled" in error:
        return "未启用"
    if "consent" in error or "授权" in error:
        return "待授权"
    return "待配置"


def _fleet_health(
    events: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    *,
    now: datetime,
    pending_projection: int,
    coverage_error: str | None = None,
) -> dict[str, Any]:
    """Derive the console health badge from the same fail-closed fleet contract as digest."""
    missed = watchdog_check(schedules, events, now) if schedules else []
    digest = build_digest(
        events,
        now,
        hours=24,
        missed=missed,
        schedules=schedules,
        coverage_error=coverage_error,
    )
    coverage = digest["coverage"]
    active = set(coverage["active_covered"])
    attention = {str(item.get("job")) for item in [*digest["problems"], *missed] if item.get("job")}
    for key in (
        "observed_unregistered",
        "observed_disabled",
        "observed_unsupported",
        "resurrected",
    ):
        attention.update(str(job) for job in coverage[key])
    for item in digest["outcomes"]["items"]:
        if item in digest["outcomes"]["problems"] or item["pending_signoff"]:
            attention.add(str(item.get("job") or f"artifact:{item['event_id']}"))
    return {
        "monitored_jobs": len(active),
        "healthy_jobs": len(active - attention),
        "problem_jobs": len(attention),
        "missed_jobs": len(missed),
        "coverage_status": coverage["status"],
        "coverage_error": coverage_error,
        "fleet_healthy": bool(digest["healthy"] and pending_projection == 0),
    }


def _execution_plan_sha(record: PlanRecord, plan: TaskPlan | None = None) -> str:
    selected_plan = plan if plan is not None else record.plan
    if selected_plan is None:
        raise ConsoleConflict("plan content is unavailable")
    return _canonical_sha256(
        {
            "objective": record.objective,
            "constraints": record.constraints,
            "workspace": record.workspace,
            "preferred_cadence": record.preferred_cadence,
            "plan": selected_plan.model_dump(mode="json"),
        }
    )


class ConsoleService:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        aion: AionUiClient | None = None,
        paperclip_factory: PaperclipFactory | None = None,
        background: bool = True,
    ) -> None:
        self.settings = settings or Settings()
        self.ledger = Ledger(self.settings.ledger_dir)
        self.store = PlanStore(self.settings.console.state_dir)
        self.aion = aion or AionUiClient(self.settings.console)
        self._paperclip_factory = paperclip_factory or self._paperclip
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="qd-console")
        self._background = background
        self._mail_jobs: dict[str, MailSummaryJob] = {}
        self._mail_lock = threading.Lock()
        self._mail_auth_jobs: dict[str, MailAuthorizationJob] = {}
        self._mail_auth_lock = threading.Lock()
        self._telegram_lock = threading.Lock()
        self._lease_guard = threading.Lock()
        self._lease_fd: int | None = None

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)
        self.release_instance_lease()

    def acquire_instance_lease(self) -> bool:
        """Hold the exclusive console lease before recovery or remote side effects."""
        with self._lease_guard:
            if self._lease_fd is not None:
                return False
            root = self.settings.console.state_dir.expanduser()
            if root.is_symlink():
                raise ConsoleUnavailable("console state directory is unavailable")
            fd: int | None = None
            try:
                root.mkdir(parents=True, exist_ok=True, mode=0o700)
                os.chmod(root, 0o700)
                fd = os.open(
                    root / "console.lease",
                    os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
                os.fchmod(fd, 0o600)
            except OSError as exc:
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                raise ConsoleUnavailable("console instance lease is unavailable") from exc
            if fd is None:
                raise ConsoleUnavailable("console instance lease is unavailable")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                os.close(fd)
                raise ConsoleUnavailable("another console instance is already active") from None
            self._lease_fd = fd
            return True

    def release_instance_lease(self) -> None:
        with self._lease_guard:
            fd = self._lease_fd
            self._lease_fd = None
            if fd is None:
                return
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                os.close(fd)
            except OSError:
                pass

    def _submit(self, fn: Callable[..., Any], *args: Any) -> None:
        if self._background:
            self._executor.submit(fn, *args)

    def _paperclip(self) -> PaperclipClient:
        api_key = resolve_api_key(self.settings)
        company_id = self.settings.paperclip.company_id
        if not api_key or not company_id:
            raise ConsoleUnavailable("Paperclip API key and company id are not configured")
        return PaperclipClient(self.settings.paperclip.api_base, api_key, company_id)

    def _append(self, kind: str, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.append(kind, run_id, payload, fsync=True)
        if event is None:
            raise ConsoleUnavailable(f"audit evidence unavailable for {kind}")
        return event

    def request_plan(self, request: PlanRequest) -> PlanRecord:
        workspace = self._normalise_requested_workspace(request.workspace)
        request = request.model_copy(update={"workspace": workspace})
        plan_id = new_ulid()
        request_hash = _canonical_sha256(request.model_dump(mode="json"))
        self._append(
            "task_plan_requested",
            plan_id,
            {
                "schema_version": 1,
                "request_sha256": request_hash,
                "preferred_cadence": request.preferred_cadence,
                "has_constraints": bool(request.constraints),
                "has_workspace": bool(request.workspace),
            },
        )
        record = PlanRecord(
            plan_id=plan_id,
            status="planning",
            objective=request.objective,
            constraints=request.constraints,
            workspace=request.workspace,
            preferred_cadence=request.preferred_cadence,
        )
        self.store.create(record)
        self._submit(self.draft_plan, plan_id)
        return record

    @staticmethod
    def _normalise_requested_workspace(value: str) -> str:
        if not value.strip():
            return ""
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError("workspace must be an absolute directory")
        try:
            if path.is_symlink():
                raise ValueError("workspace must not be a symlink")
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise ValueError("workspace is unavailable") from exc
        if not resolved.is_dir():
            raise ValueError("workspace must be an existing directory")
        return str(resolved)

    def draft_plan(self, plan_id: str) -> PlanRecord:
        record = self.store.get(plan_id)
        if record.status != "planning":
            return record
        try:
            try:
                catalog = workflow_catalog()
            except (OSError, ValueError):
                catalog = []
            request = PlanRequest(
                objective=record.objective,
                constraints=record.constraints,
                workspace=record.workspace,
                preferred_cadence=record.preferred_cadence,
            )
            plan = self.aion.generate_plan(plan_id, request, catalog)
            plan_sha = _execution_plan_sha(record, plan)
            self._append(
                "task_plan_drafted",
                plan_id,
                {
                    "schema_version": 1,
                    "plan_sha256": plan_sha,
                    "agent_count": len(plan.agents),
                    "execution_mode": plan.execution_mode,
                    "workflow_id": plan.workflow_id,
                    "cadence": plan.cadence.kind,
                },
            )

            def ready(current: PlanRecord) -> PlanRecord:
                if current.status != "planning":
                    return current
                current.status = "ready"
                current.plan = plan
                current.plan_sha256 = plan_sha
                current.error = None
                return current

            return self.store.mutate(plan_id, ready)
        except Exception:
            try:
                self._append(
                    "task_plan_failed",
                    plan_id,
                    {"schema_version": 1, "reason": PLAN_GENERATION_FAILED},
                )
            except ConsoleUnavailable:
                alert(f"audit evidence lost after task planning failure plan={plan_id}")

            def failed(current: PlanRecord) -> PlanRecord:
                current.status = "failed"
                current.error = PLAN_GENERATION_FAILED_DETAIL
                return current

            return self.store.mutate(plan_id, failed)

    def confirm_plan(self, plan_id: str, request: ConfirmRequest) -> PlanRecord:
        def confirm(current: PlanRecord) -> PlanRecord:
            if current.status != "ready" or current.plan is None or not current.plan_sha256:
                raise ConsoleConflict("only a ready plan can be confirmed")
            if current.plan_sha256 != _execution_plan_sha(current):
                raise ConsoleConflict("stored plan inputs changed; replan before confirming")
            if request.plan_sha256 != current.plan_sha256:
                raise ConsoleConflict("plan hash changed; refresh before confirming")
            self._append(
                "task_plan_confirmed",
                plan_id,
                {
                    "schema_version": 1,
                    "plan_sha256": current.plan_sha256,
                    "execution_mode": current.plan.execution_mode,
                },
            )
            current.status = "confirmed"
            current.confirmed_at = utc_now()
            return current

        record = self.store.mutate(plan_id, confirm)
        self._submit(self.dispatch_plan, plan_id)
        return record

    def dispatch_plan(self, plan_id: str) -> PlanRecord:
        try:
            claimed = False

            def claim_dispatch(current: PlanRecord) -> PlanRecord:
                nonlocal claimed
                if current.status != "confirmed":
                    return current
                if current.plan is None or not current.plan_sha256:
                    raise ConsoleConflict("confirmed plan content is unavailable")
                if current.plan_sha256 != _execution_plan_sha(current):
                    raise ConsoleConflict("confirmed plan inputs changed before dispatch")
                self._append(
                    "task_execution_requested",
                    plan_id,
                    {
                        "schema_version": 1,
                        "plan_sha256": current.plan_sha256,
                        "execution_mode": current.plan.execution_mode,
                    },
                )
                current.status = "dispatching"
                current.execution = ExecutionState(kind=current.plan.execution_mode)  # type: ignore[union-attr]
                claimed = True
                return current

            record = self.store.mutate(plan_id, claim_dispatch)
            if not claimed:
                return record
            plan = record.plan
            if plan is None:
                raise ConsoleConflict("plan content disappeared before dispatch")
            issue = self._create_or_find_issue(record)
            issue_id = str(issue.get("id", ""))
            if not issue_id:
                raise ConsoleUnavailable("Paperclip issue response has no id")

            if plan.execution_mode == "workflow":
                launched = start_workflow(
                    str(plan.workflow_id), source="console", settings=self.settings
                )
                if launched.get("accepted") is not True:
                    raise ConsoleUnavailable(str(launched.get("error") or "workflow was rejected"))
                execution = ExecutionState(
                    kind="workflow",
                    status="running",
                    paperclip_issue_id=issue_id,
                    workflow_run_id=str(launched["run_id"]),
                    dispatched_at=utc_now(),
                )
                remote: dict[str, Any] = {"workflow_run_id": execution.workflow_run_id}
            else:
                workspace = self._execution_workspace(record)
                launched = self.aion.dispatch_plan(
                    plan_id=record.plan_id,
                    plan=plan,
                    objective=record.objective,
                    constraints=record.constraints,
                    workspace=workspace,
                    paperclip_issue_id=issue_id,
                )
                execution = ExecutionState(
                    kind="aion_team",
                    status="running",
                    paperclip_issue_id=issue_id,
                    aion_team_id=str(launched["team_id"]),
                    aion_team_run_id=str(launched.get("team_run_id") or ""),
                    aion_conversation_ids=list(launched.get("conversation_ids") or []),
                    dispatched_at=utc_now(),
                )
                remote = {
                    "aion_team_id": execution.aion_team_id,
                    "aion_team_run_id": execution.aion_team_run_id,
                }

            event = self.ledger.append(
                "task_execution_dispatched",
                plan_id,
                {
                    "schema_version": 1,
                    "plan_sha256": record.plan_sha256,
                    "paperclip_issue_id": issue_id,
                    "execution_mode": plan.execution_mode,
                    **remote,
                },
                fsync=True,
            )
            if event is None:
                alert(f"execution dispatched but audit evidence was lost plan={plan_id}")
                raise ConsoleUnavailable(
                    "execution started but dispatch evidence was not persisted"
                )

            def running(current: PlanRecord) -> PlanRecord:
                current.status = "running"
                current.execution = execution
                current.error = None
                return current

            return self.store.mutate(plan_id, running)
        except Exception as exc:
            if isinstance(exc, ConsoleConflict):
                reason = EXECUTION_PLAN_INVALID
                detail = EXECUTION_PLAN_INVALID_DETAIL
            else:
                reason = EXECUTION_DISPATCH_FAILED
                detail = EXECUTION_DISPATCH_FAILED_DETAIL
            try:
                self._append(
                    "task_execution_failed",
                    plan_id,
                    {"schema_version": 1, "reason": reason},
                )
            except ConsoleUnavailable:
                alert(f"audit evidence lost after task execution failure plan={plan_id}")

            def failed(current: PlanRecord) -> PlanRecord:
                current.status = "failed"
                current.error = detail
                if current.execution is None and current.plan is not None:
                    current.execution = ExecutionState(kind=current.plan.execution_mode)
                if current.execution is not None:
                    current.execution.status = "failed"
                    current.execution.error = detail
                return current

            return self.store.mutate(plan_id, failed)

    def recover_plans(self) -> dict[str, int]:
        """Recover only transitions whose side-effect boundary is unambiguous."""
        recovered = {
            "planning_failed": 0,
            "dispatching_failed": 0,
            "confirmed_scheduled": 0,
            "active_refresh_scheduled": 0,
        }
        for snapshot in self.store.list_all():
            if snapshot.status == "planning":
                if self._fail_interrupted_plan(
                    snapshot.plan_id,
                    expected="planning",
                    event_kind="task_plan_failed",
                    reason=PLANNING_INTERRUPTED,
                    detail=PLANNING_INTERRUPTED_DETAIL,
                ):
                    recovered["planning_failed"] += 1
            elif snapshot.status == "dispatching":
                if self._fail_interrupted_plan(
                    snapshot.plan_id,
                    expected="dispatching",
                    event_kind="task_execution_failed",
                    reason=DISPATCH_INTERRUPTED,
                    detail=DISPATCH_INTERRUPTED_DETAIL,
                ):
                    recovered["dispatching_failed"] += 1
            elif snapshot.status == "confirmed":
                self._submit(self.dispatch_plan, snapshot.plan_id)
                recovered["confirmed_scheduled"] += 1
            elif snapshot.status in {"running", "awaiting_approval"}:
                self._submit(self.refresh_execution, snapshot.plan_id)
                recovered["active_refresh_scheduled"] += 1
        return recovered

    def recover_startup(self) -> dict[str, int]:
        """Reconcile private AionUi residue under the instance lease, then recover plans."""
        if self._lease_fd is None:
            raise ConsoleUnavailable("console instance lease is required before recovery")
        try:
            sessions = self.aion.stale_ephemeral_sessions()
        except (AionUiError, OSError, ValueError) as exc:
            raise ConsoleUnavailable(EPHEMERAL_RECOVERY_UNAVAILABLE) from exc
        stats = {
            "ephemeral_recovered": 0,
            "ephemeral_teams_deleted": 0,
        }
        for session in sessions:
            workspace_sha256 = hashlib.sha256(str(session.workspace).encode()).hexdigest()
            evidence = {
                "schema_version": 1,
                "purpose": session.purpose,
                "workspace_sha256": workspace_sha256,
                "team_id_present": session.team_id is not None,
            }
            self._append("aion_ephemeral_recovery_started", session.owner_id, evidence)
            try:
                result = self.aion.recover_ephemeral_session(session)
            except (AionUiError, OSError, ValueError) as exc:
                try:
                    self._append(
                        "aion_ephemeral_recovery_failed",
                        session.owner_id,
                        {**evidence, "reason": "identity_or_cleanup_unconfirmed"},
                    )
                except ConsoleUnavailable:
                    alert("audit evidence lost during AionUi ephemeral recovery failure")
                raise ConsoleUnavailable(EPHEMERAL_RECOVERY_UNAVAILABLE) from exc
            self._append(
                "aion_ephemeral_recovery_finished",
                session.owner_id,
                {
                    **evidence,
                    "team_deleted": result["team_deleted"],
                    "workspace_removed": result["workspace_removed"],
                },
            )
            stats["ephemeral_recovered"] += 1
            stats["ephemeral_teams_deleted"] += int(result["team_deleted"])
        stats.update(self.recover_plans())
        return stats

    def _fail_interrupted_plan(
        self,
        plan_id: str,
        *,
        expected: str,
        event_kind: str,
        reason: str,
        detail: str,
    ) -> bool:
        changed = False

        def fail(current: PlanRecord) -> PlanRecord:
            nonlocal changed
            if current.status != expected:
                return current
            self._append(
                event_kind,
                plan_id,
                {"schema_version": 1, "reason": reason, "recovery": True},
            )
            current.status = "failed"
            current.error = detail
            if expected == "dispatching":
                if current.execution is None and current.plan is not None:
                    current.execution = ExecutionState(kind=current.plan.execution_mode)
                if current.execution is not None:
                    current.execution.status = "failed"
                    current.execution.error = detail
            changed = True
            return current

        self.store.mutate(plan_id, fail)
        return changed

    def _create_or_find_issue(self, record: PlanRecord) -> dict[str, Any]:
        if record.plan is None or not record.plan_sha256:
            raise ConsoleConflict("plan content is unavailable")
        client = self._paperclip_factory()
        title = f"[qd-plan:{record.plan_id[-8:]}] {record.plan.title}"
        for issue in client.list_issues():
            if issue.get("title") == title:
                return issue
        architecture = ", ".join(f"{agent.name} ({agent.runtime})" for agent in record.plan.agents)
        description = (
            f"Confirmed Quarterdeck plan `{record.plan_id}`.\n\n"
            f"{record.plan.summary}\n\n"
            f"Team: {architecture}\n"
            f"Cadence: {record.plan.cadence.kind} / {record.plan.cadence.update_interval}\n"
            f"Plan sha256: `{record.plan_sha256}`\n\n"
            "Execution completion is not business outcome proof; inspect artifacts, evals, and signoff."
        )
        return client.create_issue(title, description)

    def _execution_workspace(self, record: PlanRecord) -> Path:
        if record.workspace:
            return Path(record.workspace)
        root = self.settings.console.state_dir.expanduser() / "executions" / record.plan_id
        if root.is_symlink():
            raise ValueError("execution workspace must not be a symlink")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(root, 0o700)
        return root

    def get_plan(self, plan_id: str, *, refresh: bool = True) -> PlanRecord:
        record = self.store.get(plan_id)
        if refresh and record.status in {"running", "awaiting_approval"}:
            return self.refresh_execution(plan_id)
        return record

    def list_plans(self, limit: int = 30) -> list[PlanRecord]:
        return self.store.list(limit)

    def refresh_execution(self, plan_id: str) -> PlanRecord:
        record = self.store.get(plan_id)
        execution = record.execution
        if execution is None or record.status not in {"running", "awaiting_approval"}:
            return record
        try:
            if execution.kind == "workflow" and execution.workflow_run_id:
                rows = workflow_status(execution.workflow_run_id, settings=self.settings, limit=1)
                external = rows[0]["status"] if rows else "queued"
                if external in {"requested", "dispatched", "running"}:
                    next_status = "running"
                elif external == "succeeded":
                    next_status = "completed_unverified"
                else:
                    next_status = "failed"
            elif execution.kind == "aion_team" and execution.aion_team_id:
                snapshot = self.aion.execution_snapshot(
                    execution.aion_team_id, execution.aion_conversation_ids
                )
                next_status = str(snapshot.get("status", "running"))
                if next_status == "failed":
                    execution.error = EXECUTION_REMOTE_FAILED_DETAIL
            else:
                next_status = "failed"
                execution.error = EXECUTION_IDENTIFIERS_MISSING_DETAIL
            if next_status == "failed" and execution.error is None:
                execution.error = EXECUTION_REMOTE_FAILED_DETAIL
        except (AionUiError, PaperclipError, OSError, ValueError):
            execution.error = EXECUTION_STATUS_UNAVAILABLE_DETAIL
            return record

        def update(current: PlanRecord) -> PlanRecord:
            if current.execution is None:
                return current
            current.execution.status = next_status  # type: ignore[assignment]
            current.status = next_status  # type: ignore[assignment]
            current.execution.error = execution.error
            if next_status in {"completed_unverified", "failed"}:
                current.execution.finished_at = current.execution.finished_at or utc_now()
            return current

        updated = self.store.mutate(plan_id, update)
        if (
            next_status in {"completed_unverified", "failed"}
            and updated.execution is not None
            and not updated.execution.finish_event_recorded
        ):
            event = self.ledger.append(
                "task_execution_finished",
                plan_id,
                {
                    "schema_version": 1,
                    "status": next_status,
                    "outcome_verified": False,
                    "paperclip_issue_id": updated.execution.paperclip_issue_id,
                },
                fsync=True,
                degraded=next_status == "failed",
            )
            if event is not None:

                def mark(current: PlanRecord) -> PlanRecord:
                    if current.execution is not None:
                        current.execution.finish_event_recorded = True
                    return current

                updated = self.store.mutate(plan_id, mark)
            else:
                alert(f"execution finished but final evidence was lost plan={plan_id}")
        return updated

    def request_mail_summary(self) -> MailSummaryJob:
        with self._mail_lock:
            running = next(
                (job for job in self._mail_jobs.values() if job.status == "running"), None
            )
            if running is not None:
                return running
            job = MailSummaryJob(job_id=new_ulid())
            self._append(
                "mail_summary_requested",
                job.job_id,
                {"schema_version": 1, "privacy": "metadata_only", "source": "console"},
            )
            self._mail_jobs[job.job_id] = job
        self._submit(self.run_mail_summary, job.job_id)
        return job

    def run_mail_summary(self, job_id: str) -> MailSummaryJob:
        try:
            result = check_mail(source="console", settings=self.settings)
            if result.get("ok") is not True:
                raise ConsoleUnavailable(str(result.get("error") or "mail check failed"))
            messages = result.get("messages")
            if not isinstance(messages, list):
                raise ConsoleUnavailable("mail adapter returned invalid metadata")
            summary = self.aion.summarize_mail(job_id, messages)
            summary_hash = hashlib.sha256(summary.encode()).hexdigest()
            self._append(
                "mail_summary_finished",
                job_id,
                {
                    "schema_version": 1,
                    "message_count": len(messages),
                    "summary_sha256": summary_hash,
                    "privacy": "metadata_only",
                },
            )
            updated = MailSummaryJob(
                job_id=job_id,
                status="ready",
                created_at=self._mail_jobs[job_id].created_at,
                updated_at=utc_now(),
                summary=summary,
                message_count=len(messages),
            )
        except Exception:
            try:
                self._append(
                    "mail_summary_failed",
                    job_id,
                    {
                        "schema_version": 1,
                        "reason": "mail_summary_failed",
                        "privacy": "metadata_only",
                    },
                )
            except ConsoleUnavailable:
                alert(f"audit evidence lost after mail summary failure job={job_id}")
            updated = MailSummaryJob(
                job_id=job_id,
                status="failed",
                created_at=self._mail_jobs[job_id].created_at,
                updated_at=utc_now(),
                error=MAIL_SUMMARY_FAILURE,
            )
        with self._mail_lock:
            self._mail_jobs[job_id] = updated
        return updated

    def get_mail_summary(self, job_id: str) -> MailSummaryJob:
        with self._mail_lock:
            try:
                return self._mail_jobs[job_id]
            except KeyError as exc:
                raise PlanNotFound(f"unknown mail summary: {job_id}") from exc

    def mail_setup_status(self) -> dict[str, Any]:
        status = mail_status(self.settings)
        return {
            "enabled": status.get("enabled") is True,
            "available": status.get("available") is True,
            "authenticated": status.get("authenticated") is True,
            "model_metadata_consent": status.get("model_metadata_consent") is True,
            "ready": status.get("mcp_ready") is True,
            "oauth_scope": "gmail.readonly",
            "metadata_fields": ["from", "subject", "date", "message_id"],
            "privacy": "metadata_only",
        }

    def request_mail_authorization(
        self, request: MailAuthorizationRequest
    ) -> MailAuthorizationJob:
        del request  # Literal[True] fields are validated at the HTTP boundary.
        with self._mail_auth_lock:
            running = next(
                (job for job in self._mail_auth_jobs.values() if job.status == "running"),
                None,
            )
            if running is not None:
                return running
            job = MailAuthorizationJob(job_id=new_ulid())
            self._append(
                "mail_authorization_requested",
                job.job_id,
                {
                    "schema_version": 1,
                    "oauth_scope": "gmail.readonly",
                    "metadata_fields": ["from", "subject", "date", "message_id"],
                    "model_metadata_consent": True,
                    "source": "console",
                },
            )
            self._mail_auth_jobs[job.job_id] = job
        self._submit(self.run_mail_authorization, job.job_id)
        return job

    def run_mail_authorization(self, job_id: str) -> MailAuthorizationJob:
        activation_saved = False
        try:
            result = authorize_mail(self.settings)
            if result.get("ok") is not True:
                raise ConsoleUnavailable("mail OAuth verification failed")
            save_mail_activation(enabled=True, model_metadata_consent=True)
            activation_saved = True
            enabled_mail = self.settings.mail.model_copy(
                update={"enabled": True, "model_metadata_consent": True}
            )
            self.settings = self.settings.model_copy(update={"mail": enabled_mail})
            self._append(
                "mail_authorization_finished",
                job_id,
                {
                    "schema_version": 1,
                    "oauth_scope": "gmail.readonly",
                    "credential_storage": "encrypted",
                    "model_metadata_consent": True,
                    "source": "console",
                },
            )
            updated = MailAuthorizationJob(
                job_id=job_id,
                status="ready",
                created_at=self._mail_auth_jobs[job_id].created_at,
                updated_at=utc_now(),
            )
        except Exception:
            if activation_saved:
                try:
                    save_mail_activation(enabled=False, model_metadata_consent=False)
                    disabled_mail = self.settings.mail.model_copy(
                        update={"enabled": False, "model_metadata_consent": False}
                    )
                    self.settings = self.settings.model_copy(update={"mail": disabled_mail})
                except (OSError, ValueError):
                    alert("mail activation rollback failed after authorization evidence loss")
            try:
                self._append(
                    "mail_authorization_failed",
                    job_id,
                    {
                        "schema_version": 1,
                        "reason": "oauth_or_activation_failed",
                        "source": "console",
                    },
                )
            except ConsoleUnavailable:
                alert(f"audit evidence lost after mail authorization failure job={job_id}")
            updated = MailAuthorizationJob(
                job_id=job_id,
                status="failed",
                created_at=self._mail_auth_jobs[job_id].created_at,
                updated_at=utc_now(),
                error=MAIL_AUTHORIZATION_FAILURE,
            )
        with self._mail_auth_lock:
            self._mail_auth_jobs[job_id] = updated
        return updated

    def get_mail_authorization(self, job_id: str) -> MailAuthorizationJob:
        with self._mail_auth_lock:
            try:
                return self._mail_auth_jobs[job_id]
            except KeyError as exc:
                raise PlanNotFound(f"unknown mail authorization: {job_id}") from exc

    def disable_mail(self) -> dict[str, bool]:
        try:
            save_mail_activation(enabled=False, model_metadata_consent=False)
        except (OSError, ValueError) as exc:
            raise ConsoleUnavailable("mail consent could not be revoked safely") from exc
        disabled_mail = self.settings.mail.model_copy(
            update={"enabled": False, "model_metadata_consent": False}
        )
        self.settings = self.settings.model_copy(update={"mail": disabled_mail})
        event = self.ledger.append(
            "mail_consent_revoked",
            new_ulid(),
            {
                "schema_version": 1,
                "model_metadata_consent": False,
                "source": "console",
            },
            fsync=True,
        )
        if event is None:
            alert("mail consent was revoked but audit evidence was unavailable")
        return {"disabled": True}

    @staticmethod
    def _telegram_environment_controlled() -> bool:
        return any(
            name in os.environ
            for name in ("QD_TELEGRAM__BOT_TOKEN", "QD_TELEGRAM__CHAT_ID")
        )

    def telegram_setup_status(self) -> dict[str, bool]:
        configured = bool(
            self.settings.telegram.bot_token and self.settings.telegram.chat_id
        )
        return {
            "configured": configured,
            "environment_controlled": self._telegram_environment_controlled(),
        }

    def configure_telegram(self, request: TelegramConfigureRequest) -> dict[str, bool]:
        with self._telegram_lock:
            return self._configure_telegram_locked(request)

    def _configure_telegram_locked(
        self, request: TelegramConfigureRequest
    ) -> dict[str, bool]:
        if self._telegram_environment_controlled():
            raise ConsoleConflict(TELEGRAM_ENVIRONMENT_CONTROLLED)
        run_id = new_ulid()
        self._append(
            "telegram_configuration_requested",
            run_id,
            {
                "schema_version": 1,
                "replace_existing": request.replace_existing,
                "private_storage_acknowledged": True,
                "source": "console",
            },
        )
        token = request.bot_token.get_secret_value()
        chat_id = request.chat_id.get_secret_value()
        try:
            save_telegram_credentials(
                token,
                chat_id,
                replace=request.replace_existing,
            )
        except (OSError, ValueError) as exc:
            try:
                self._append(
                    "telegram_configuration_failed",
                    run_id,
                    {
                        "schema_version": 1,
                        "reason": "credentials_rejected",
                        "source": "console",
                    },
                )
            except ConsoleUnavailable:
                alert("audit evidence lost after Telegram configuration failure")
            raise ConsoleConflict(TELEGRAM_CONFIGURATION_REJECTED) from exc
        telegram = self.settings.telegram.model_copy(
            update={"bot_token": token, "chat_id": chat_id}
        )
        self.settings = self.settings.model_copy(update={"telegram": telegram})
        self._append(
            "telegram_configuration_finished",
            run_id,
            {"schema_version": 1, "source": "console"},
        )
        return {"configured": True}

    def test_telegram(self) -> dict[str, bool]:
        with self._telegram_lock:
            return self._test_telegram_locked()

    def _test_telegram_locked(self) -> dict[str, bool]:
        run_id = new_ulid()
        self._append(
            "telegram_test_requested",
            run_id,
            {"schema_version": 1, "source": "console"},
        )
        if not send_telegram("Quarterdeck Telegram delivery test", self.settings):
            self._append(
                "telegram_test_failed",
                run_id,
                {
                    "schema_version": 1,
                    "reason": "delivery_failed",
                    "source": "console",
                },
            )
            raise ConsoleUnavailable(TELEGRAM_TEST_FAILED)
        self._append(
            "telegram_test_finished",
            run_id,
            {"schema_version": 1, "source": "console"},
        )
        return {"sent": True}

    def disable_telegram(self) -> dict[str, bool]:
        with self._telegram_lock:
            return self._disable_telegram_locked()

    def _disable_telegram_locked(self) -> dict[str, bool]:
        if self._telegram_environment_controlled():
            raise ConsoleConflict(TELEGRAM_ENVIRONMENT_CONTROLLED)
        try:
            clear_telegram_credentials()
        except (OSError, ValueError) as exc:
            raise ConsoleUnavailable("Telegram credentials could not be removed safely") from exc
        telegram = self.settings.telegram.model_copy(
            update={"bot_token": "", "chat_id": ""}
        )
        self.settings = self.settings.model_copy(update={"telegram": telegram})
        event = self.ledger.append(
            "telegram_disabled",
            new_ulid(),
            {"schema_version": 1, "source": "console"},
            fsync=True,
        )
        if event is None:
            alert("Telegram credentials were removed but audit evidence was unavailable")
        return {"disabled": True}

    def dashboard(self) -> dict[str, Any]:
        index_db = self.settings.ledger_dir.parent / "index.db"
        events = self.ledger.read_all()
        info = rebuild(index_db, self.ledger, events=events)
        jobs = job_summary(index_db)
        recent_runs = query_runs(index_db, limit=8)
        schedules: list[dict[str, Any]] = []
        coverage_error: str | None = None
        try:
            schedules = load_effective_schedules(config_dir())["schedules"]
        except ValueError:
            coverage_error = SCHEDULE_CONFIGURATION_INVALID_DETAIL
        health = _fleet_health(
            events,
            schedules,
            now=datetime.now(UTC),
            pending_projection=int(info["pending_projection"]),
            coverage_error=coverage_error,
        )
        integrations: dict[str, Any] = {}
        try:
            self.aion.health()
            integrations["aionui"] = {
                "status": "online",
                "label": "AionUi",
                "url": self.settings.console.aionui_base,
            }
        except (AionUiError, ValueError):
            integrations["aionui"] = {
                "status": "offline",
                "label": "AionUi",
                "detail": "本地服务不可用",
            }
        try:
            response = httpx.get(
                f"{self.settings.paperclip.api_base.rstrip('/')}/api/health", timeout=3.0
            )
            response.raise_for_status()
            integrations["paperclip"] = {
                "status": "online",
                "label": "Paperclip",
                "url": self.settings.paperclip.api_base,
            }
        except httpx.HTTPError:
            integrations["paperclip"] = {
                "status": "offline",
                "label": "Paperclip",
                "detail": "治理服务不可用",
            }
        mail = (
            mail_status(self.settings)
            if self.settings.mail.enabled
            else {
                "mcp_ready": False,
                "error": "mail integration is disabled",
            }
        )
        integrations["mail"] = {
            "status": "online" if mail.get("mcp_ready") else "setup",
            "label": "邮箱",
            "detail": _mail_setup_detail(mail),
            "privacy": "metadata_only",
        }
        telegram = self.telegram_setup_status()
        integrations["telegram"] = {
            "status": "online" if telegram["configured"] else "setup",
            "label": "Telegram",
            "detail": (
                "外部环境管理"
                if telegram["environment_controlled"]
                else "已配置" if telegram["configured"] else "待配置"
            ),
        }
        integrations["ledger"] = {
            "status": "online" if info["pending_projection"] == 0 else "attention",
            "label": "证据账本",
            "detail": f"待投影 {info['pending_projection']}",
        }
        pending_approvals: int | None = None
        approvals_available = False
        try:
            pending_approvals = len(self._paperclip_factory().list_approvals("pending"))
            approvals_available = True
        except (ConsoleUnavailable, PaperclipError):
            if integrations["paperclip"]["status"] == "online":
                integrations["paperclip"] = {
                    **integrations["paperclip"],
                    "status": "attention",
                    "detail": "审批状态不可用",
                }
        try:
            workflows = workflow_catalog()
        except (OSError, ValueError):
            workflows = []
        return {
            "generated_at": utc_now(),
            "integrations": integrations,
            "fleet": {
                **info,
                "jobs": len(jobs),
                **health,
            },
            "pending_approvals": pending_approvals,
            "approvals_available": approvals_available,
            "workflows": workflows,
            "plans": [row.model_dump(mode="json") for row in self.list_plans(12)],
            "recent_runs": recent_runs,
            "mail_ready": bool(mail.get("mcp_ready")),
        }
