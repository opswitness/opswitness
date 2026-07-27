from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from opswitness.artifacts import register_console_artifact
from opswitness.config import Settings
from opswitness.console.app import create_app
from opswitness.console.schemas import (
    ApprovalDecisionRequest,
    ArtifactSignoffRequest,
    ConfirmRequest,
    OnboardingFirstWorkRequest,
    OnboardingProviderRequest,
    PlanRequest,
    RerunPlanRequest,
    RuntimeName,
)
from opswitness.console.service import (
    ConsoleService,
    ConsoleUnavailable,
    _execution_plan_sha,
)


SYNTHETIC_INQUIRY = (
    "Hi, I'm Maya from Harbor Bakery. I need monthly website maintenance. "
    "My budget is $500 per month, and I'd like to start next week. What is included?"
)
SYNTHETIC_REPLY = (
    "Hi Maya,\n\n"
    "Thanks for reaching out about monthly website maintenance. I noted your $500 monthly "
    "budget and preferred start next week.\n\n"
    "Before confirming scope, price, or a start date, could you share which website platform "
    "you use, the updates you expect each month, and whether hosting or urgent support should "
    "be included?\n\n"
    "Once I have those details, I can prepare a clear scope and timeline. Nothing is booked "
    "yet.\n\n"
    "Best,\n"
    "Your business"
)
SYNTHETIC_REPLY_PAYLOAD = {
    "schema_version": 1,
    "scenario": "synthetic_website_maintenance_inquiry",
    "customer_name": "Maya",
    "inquiry": SYNTHETIC_INQUIRY,
    "reply_draft": SYNTHETIC_REPLY,
    "draft_only": True,
    "delivery_requested": False,
    "technical_demo_only": True,
}


class _OnboardingAion:
    def health(self):
        return {"platform": "darwin"}

    def list_assistants(self):
        return [
            {
                "id": "bare:8e1acf31",
                "enabled": True,
                "team_selectable": True,
            }
        ]

    def list_managed_agents(self):
        return []

    def local_provider_registered(self, provider):
        del provider
        return False

    def run_onboarding_json(
        self,
        owner_id,
        *,
        agent_name,
        assistant_id,
        model,
        prompt,
    ):
        del owner_id, assistant_id, model
        assert "Do not use tools" in prompt
        if agent_name == "Business Assistant":
            return dict(SYNTHETIC_REPLY_PAYLOAD)
        first_bytes = (
            json.dumps(
                SYNTHETIC_REPLY_PAYLOAD,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
        return {
            "schema_version": 1,
            "artifact": "first-work.json",
            "sha256": hashlib.sha256(first_bytes).hexdigest(),
            "checks": {
                "follow_up_questions_present": True,
                "no_price_commitment": True,
                "no_start_date_commitment": True,
                "delivery_requested": False,
            },
            "approved_as_draft": True,
            "fictional_scenario": True,
            "technical_demo_only": True,
        }


class _ClaudeOnlyOnboardingAion(_OnboardingAion):
    def list_assistants(self):
        return [
            {
                "id": "bare:2d23ff1c",
                "enabled": True,
                "team_selectable": True,
            }
        ]


class _BothProvidersOnboardingAion(_OnboardingAion):
    def list_assistants(self):
        return [
            {
                "id": assistant_id,
                "enabled": True,
                "team_selectable": True,
            }
            for assistant_id in ("bare:8e1acf31", "bare:2d23ff1c")
        ]


class _OnboardingPaperclip:
    def __init__(self):
        self.approvals = []

    def list_issues(self):
        return []

    def create_issue(self, title, description):
        del title, description
        return {"id": "onboarding-issue"}

    def list_approvals(self, status=None):
        if status is None:
            return list(self.approvals)
        return [row for row in self.approvals if row["status"] == status]

    def create_board_approval(self, payload):
        row = {
            "id": f"00000000-0000-4000-8000-{len(self.approvals) + 1:012d}",
            "status": "pending",
            "payload": payload,
            "createdAt": "2026-07-25T18:00:00+00:00",
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
def onboarding_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "home"
    config = tmp_path / "config"
    app_support = tmp_path / "Application Support" / "OpsWitness"
    home.mkdir(mode=0o700)
    config.mkdir(mode=0o700)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(config))
    monkeypatch.setenv("OPSWITNESS_LEDGER_DIR", str(tmp_path / "ledger"))
    monkeypatch.setenv("OPSWITNESS_CONSOLE__STATE_DIR", str(app_support / "state" / "console"))
    monkeypatch.setenv("OPSWITNESS_APP_SUPPORT_DIR", str(app_support))
    settings = Settings(
        ledger_dir=tmp_path / "ledger",
        console={"state_dir": app_support / "state" / "console", "port": 8765},
        paperclip={"api_key": "test", "company_id": "company-1"},
    )
    paperclip = _OnboardingPaperclip()
    service = ConsoleService(
        settings,
        aion=_OnboardingAion(),  # type: ignore[arg-type]
        paperclip_factory=lambda: paperclip,  # type: ignore[return-value]
        provider_probe=lambda provider: {
            "provider": provider,
            "label": provider,
            "installed": provider == "openai",
            "authenticated": provider == "openai",
            "auth_mode": "chatgpt" if provider == "openai" else "none",
            "status": "online" if provider == "openai" else "setup",
            "detail": "ready" if provider == "openai" else "not configured",
            "server_online": False,
            "model_count": 0,
            "models": [],
        },
        background=False,
    )
    service.onboarding._disk_usage = lambda path: SimpleNamespace(  # type: ignore[method-assign]
        total=20 * 1024**3,
        used=2 * 1024**3,
        free=18 * 1024**3,
    )
    yield settings, service, home
    service.close()


def _client(settings: Settings, service: ConsoleService) -> TestClient:
    service.acquire_instance_lease = lambda: True  # type: ignore[method-assign]
    service.recover_startup = lambda: {}  # type: ignore[method-assign]
    service.release_instance_lease = lambda: None  # type: ignore[method-assign]
    return TestClient(
        create_app(settings, service=service),
        base_url="http://127.0.0.1:8765",
    )


def _select_provider(service: ConsoleService, provider: str = "openai") -> None:
    service.select_onboarding_provider(
        OnboardingProviderRequest.model_validate(
            {"provider": provider, "confirmed": True}
        )
    )


def _provider_probe_for(*ready_providers: str):
    ready = set(ready_providers)

    def probe(provider: str) -> dict[str, object]:
        authenticated = provider in ready
        return {
            "provider": provider,
            "label": provider,
            "installed": authenticated,
            "authenticated": authenticated,
            "auth_mode": (
                "chatgpt"
                if provider == "openai" and authenticated
                else "api_key"
                if provider == "anthropic" and authenticated
                else "none"
            ),
            "status": "online" if authenticated else "setup",
            "detail": "ready" if authenticated else "not configured",
            "server_online": False,
            "model_count": 0,
            "models": [],
        }

    return probe


def test_new_user_onboarding_exposes_readiness_without_mutating_state(onboarding_env):
    settings, service, _ = onboarding_env
    assert not service.onboarding.state_path.exists()

    with _client(settings, service) as client:
        response = client.get("/api/v1/onboarding")

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "provider_required"
    assert payload["complete"] is False
    assert payload["disk_ready"] is True
    assert payload["required_free_bytes"] == 5 * 1024**3
    assert payload["migration_required"] is False
    assert payload["legacy_sources"] == []
    assert payload["runtime_ready"] is True
    assert payload["provider_choice"] is None
    assert payload["provider_runtime_ready"] is False
    assert not service.onboarding.state_path.exists()


def test_provider_selection_is_explicit_validated_and_idempotent(onboarding_env):
    settings, service, _ = onboarding_env

    with _client(settings, service) as client:
        csrf = client.app.state.csrf_token
        unselected = client.post(
            "/api/v1/onboarding/first-work",
            json={"confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        denied = client.post(
            "/api/v1/onboarding/provider",
            json={"provider": "openai", "confirmed": True},
        )
        unavailable = client.post(
            "/api/v1/onboarding/provider",
            json={"provider": "anthropic", "confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        selected = client.post(
            "/api/v1/onboarding/provider",
            json={"provider": "openai", "confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        repeated = client.post(
            "/api/v1/onboarding/provider",
            json={"provider": "openai", "confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )

    assert unselected.status_code == 409
    assert "choose OpenAI or Anthropic" in unselected.json()["detail"]
    assert denied.status_code == 403
    assert unavailable.status_code == 409
    assert selected.status_code == 200, selected.json()
    assert selected.json()["provider_choice"] == "openai"
    assert selected.json()["provider_runtime_ready"] is True
    assert selected.json()["state"] == "first_work_ready"
    assert repeated.status_code == 200
    assert repeated.json()["provider_choice"] == "openai"
    persisted = json.loads(service.onboarding.state_path.read_text(encoding="utf-8"))
    assert persisted["schema_version"] == 2
    assert persisted["provider_choice"] == "openai"


def test_claude_only_provider_creates_claude_first_work(onboarding_env):
    settings, service, _ = onboarding_env
    service.aion = _ClaudeOnlyOnboardingAion()  # type: ignore[assignment]
    service._provider_probe = _provider_probe_for("anthropic")

    with _client(settings, service) as client:
        csrf = client.app.state.csrf_token
        selected = client.post(
            "/api/v1/onboarding/provider",
            json={"provider": "anthropic", "confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        created = client.post(
            "/api/v1/onboarding/first-work",
            json={"confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )

    assert selected.status_code == 200, selected.json()
    assert selected.json()["provider_choice"] == "anthropic"
    assert selected.json()["provider_runtime_ready"] is True
    assert created.status_code == 201
    plan = created.json()["plan"]
    assert all(
        agent["runtime"] == "claude_code" for agent in plan["plan"]["agents"]
    )
    event = next(
        event
        for event in service.ledger.read_all()
        if event["kind"] == "onboarding_first_work_created"
    )
    assert event["payload"]["provider"] == "anthropic"
    assert event["payload"]["runtime"] == "claude_code"


def test_planner_uses_the_explicitly_selected_claude_provider(onboarding_env):
    _, service, _ = onboarding_env
    service.aion = _BothProvidersOnboardingAion()  # type: ignore[assignment]
    service._provider_probe = _provider_probe_for("openai", "anthropic")
    _select_provider(service, "anthropic")

    assert service._planner_assistant_id() == "bare:2d23ff1c"


def test_planner_does_not_fall_back_when_selected_claude_becomes_unavailable(
    onboarding_env,
):
    _, service, _ = onboarding_env
    service.aion = _BothProvidersOnboardingAion()  # type: ignore[assignment]
    service._provider_probe = _provider_probe_for("openai", "anthropic")
    _select_provider(service, "anthropic")
    service._provider_probe = _provider_probe_for("openai")

    with pytest.raises(ConsoleUnavailable, match="will not switch providers"):
        service._planner_assistant_id()


def test_provider_cannot_switch_after_first_work_exists(onboarding_env):
    settings, service, _ = onboarding_env
    _select_provider(service)
    _, first = service.create_first_onboarding_work(
        OnboardingFirstWorkRequest(confirmed=True)
    )
    service.aion = _BothProvidersOnboardingAion()  # type: ignore[assignment]
    service._provider_probe = _provider_probe_for("openai", "anthropic")

    with _client(settings, service) as client:
        csrf = client.app.state.csrf_token
        rejected = client.post(
            "/api/v1/onboarding/provider",
            json={"provider": "anthropic", "confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        repeated = client.post(
            "/api/v1/onboarding/provider",
            json={"provider": "openai", "confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )

    assert rejected.status_code == 409
    assert "cannot change" in rejected.json()["detail"]
    assert repeated.status_code == 200
    assert repeated.json()["provider_choice"] == "openai"
    assert service.onboarding.read()["first_work_plan_id"] == first.plan_id
    assert service.onboarding.read()["provider_choice"] == "openai"


def test_v1_first_work_provider_is_inferred_and_persisted(onboarding_env):
    settings, service, _ = onboarding_env
    _select_provider(service)
    _, first = service.create_first_onboarding_work(
        OnboardingFirstWorkRequest(confirmed=True)
    )
    legacy_state = service.onboarding.read()
    legacy_state["schema_version"] = 1
    legacy_state.pop("provider_choice")
    service.onboarding.state_path.write_text(
        json.dumps(legacy_state, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    service.onboarding.state_path.chmod(0o600)

    with _client(settings, service) as client:
        response = client.get("/api/v1/onboarding")

    assert response.status_code == 200
    assert response.json()["provider_choice"] == "openai"
    assert response.json()["first_work_plan_id"] == first.plan_id
    upgraded = json.loads(service.onboarding.state_path.read_text(encoding="utf-8"))
    assert upgraded["schema_version"] == 2
    assert upgraded["provider_choice"] == "openai"


def test_v1_mixed_runtime_first_work_fails_closed(onboarding_env):
    settings, service, _ = onboarding_env
    _select_provider(service)
    _, first = service.create_first_onboarding_work(
        OnboardingFirstWorkRequest(confirmed=True)
    )

    def make_mixed(record):
        assert record.plan is not None
        record.plan.agents[1].runtime = RuntimeName.CLAUDE_CODE
        return record

    service.store.mutate(first.plan_id, make_mixed)
    legacy_state = service.onboarding.read()
    legacy_state["schema_version"] = 1
    legacy_state.pop("provider_choice")
    service.onboarding.state_path.write_text(
        json.dumps(legacy_state, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    service.onboarding.state_path.chmod(0o600)

    with _client(settings, service) as client:
        response = client.get("/api/v1/onboarding")

    assert response.status_code == 200
    assert response.json()["state"] == "failed"
    assert response.json()["provider_choice"] is None
    assert response.json()["failure"]["code"] == "onboarding_provider_unresolved"
    unchanged = json.loads(service.onboarding.state_path.read_text(encoding="utf-8"))
    assert unchanged["schema_version"] == 1
    assert "provider_choice" not in unchanged


def test_existing_cli_install_is_not_forced_through_desktop_onboarding(onboarding_env):
    settings, service, _ = onboarding_env
    existing = service.request_plan(PlanRequest(objective="Existing reviewed workflow"))
    assert existing.status == "planning"
    assert not service.onboarding.state_path.exists()

    with _client(settings, service) as client:
        response = client.get("/api/v1/onboarding")

    assert response.status_code == 200
    assert response.json()["state"] == "complete"
    assert response.json()["complete"] is True
    assert response.json()["first_work_plan_id"] is None
    assert not service.onboarding.state_path.exists()


def test_legacy_import_is_csrf_protected_idempotent_and_source_preserving(onboarding_env):
    settings, service, home = onboarding_env
    legacy = home / ".config" / "quarterdeck"
    legacy.mkdir(parents=True, mode=0o700)
    source = legacy / "config.yaml"
    source.write_text("console:\n  port: 8765\n", encoding="utf-8")
    source.chmod(0o600)
    original = source.read_bytes()
    original_digest = hashlib.sha256(original).hexdigest()

    with _client(settings, service) as client:
        status = client.get("/api/v1/onboarding").json()
        assert status["state"] == "migration_required"
        assert status["migration_required"] is True
        denied = client.post(
            "/api/v1/onboarding/migration",
            json={"choice": "import", "confirmed": True},
        )
        assert denied.status_code == 403
        csrf = client.app.state.csrf_token
        imported = client.post(
            "/api/v1/onboarding/migration",
            json={"choice": "import", "confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        assert imported.status_code == 200
        assert imported.json()["migration_choice"] == "import"
        repeated = client.post(
            "/api/v1/onboarding/migration",
            json={"choice": "import", "confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        assert repeated.status_code == 200

    assert source.read_bytes() == original
    state = service.onboarding.read()
    import_id = state["import_id"]
    imports = [
        path
        for path in (service.onboarding.root / "legacy-imports").iterdir()
        if not path.name.startswith(".")
    ]
    assert imports == [service.onboarding.root / "legacy-imports" / import_id]
    manifest = json.loads((imports[0] / "manifest.json").read_text())
    assert manifest["source_untouched"] is True
    assert manifest["total_files"] == 1
    assert manifest["sources"][0]["files"][0]["sha256"] == original_digest
    assert (imports[0] / "config" / "config.yaml").read_bytes() == original


def test_fresh_choice_leaves_detected_legacy_tree_untouched(onboarding_env):
    settings, service, home = onboarding_env
    legacy = home / ".local" / "state" / "quarterdeck"
    legacy.mkdir(parents=True, mode=0o700)
    marker = legacy / "ledger.jsonl"
    marker.write_text('{"immutable":true}\n', encoding="utf-8")

    with _client(settings, service) as client:
        csrf = client.app.state.csrf_token
        selected = client.post(
            "/api/v1/onboarding/migration",
            json={"choice": "fresh", "confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )

    assert selected.status_code == 200
    assert selected.json()["migration_choice"] == "fresh"
    assert selected.json()["migration_required"] is False
    assert marker.read_text(encoding="utf-8") == '{"immutable":true}\n'
    assert not (service.onboarding.root / "legacy-imports").exists()


def test_canonical_pre_desktop_opswitness_state_is_offered_as_a_copy(
    onboarding_env,
):
    settings, service, home = onboarding_env
    legacy = home / ".local" / "state" / "opswitness"
    legacy.mkdir(parents=True, mode=0o700)
    marker = legacy / "ledger.jsonl"
    marker.write_text('{"source":"legacy-opswitness"}\n', encoding="utf-8")
    original = marker.read_bytes()

    with _client(settings, service) as client:
        status = client.get("/api/v1/onboarding").json()
        assert str(legacy) in status["legacy_sources"]
        csrf = client.app.state.csrf_token
        imported = client.post(
            "/api/v1/onboarding/migration",
            json={"choice": "import", "confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )

    assert imported.status_code == 200
    assert marker.read_bytes() == original
    import_id = service.onboarding.read()["import_id"]
    copied = (
        service.onboarding.root / "legacy-imports" / import_id / "opswitness-state" / "ledger.jsonl"
    )
    assert copied.read_bytes() == original


def test_import_fails_closed_on_legacy_symlink_without_copying(onboarding_env):
    settings, service, home = onboarding_env
    external = home / "external"
    external.mkdir(mode=0o700)
    (external / "secret.txt").write_text("must not be copied", encoding="utf-8")
    legacy_parent = home / ".config"
    legacy_parent.mkdir(mode=0o700)
    (legacy_parent / "quarterdeck").symlink_to(external, target_is_directory=True)

    with _client(settings, service) as client:
        csrf = client.app.state.csrf_token
        rejected = client.post(
            "/api/v1/onboarding/migration",
            json={"choice": "import", "confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )

    assert rejected.status_code == 409
    assert "manual review" in rejected.json()["detail"]
    assert (external / "secret.txt").read_text(encoding="utf-8") == "must not be copied"
    assert not (service.onboarding.root / "legacy-imports").exists()
    assert service.onboarding.read()["migration_choice"] is None


def test_all_detected_legacy_sources_fit_the_onboarding_projection(onboarding_env):
    settings, service, home = onboarding_env
    sources = [
        home / ".config" / "opswitness",
        home / ".local" / "state" / "opswitness",
        home / ".config" / "quarterdeck",
        home / ".local" / "state" / "quarterdeck",
        home / "Library" / "Logs" / "Quarterdeck",
    ]
    for index, source in enumerate(sources):
        source.mkdir(parents=True, mode=0o700)
        marker = source / f"marker-{index}.json"
        marker.write_text('{"legacy":true}\n', encoding="utf-8")
        marker.chmod(0o600)

    with _client(settings, service) as client:
        response = client.get("/api/v1/onboarding")

    assert response.status_code == 200
    assert response.json()["state"] == "migration_required"
    assert set(response.json()["legacy_sources"]) == {str(source) for source in sources}


def test_retryable_import_failure_keeps_migration_choice_recoverable(onboarding_env):
    settings, service, home = onboarding_env
    external = home / "external"
    external.mkdir(mode=0o700)
    legacy_parent = home / ".config"
    legacy_parent.mkdir(mode=0o700)
    (legacy_parent / "quarterdeck").symlink_to(external, target_is_directory=True)

    with _client(settings, service) as client:
        csrf = client.app.state.csrf_token
        rejected = client.post(
            "/api/v1/onboarding/migration",
            json={"choice": "import", "confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        status = client.get("/api/v1/onboarding")
        recovered = client.post(
            "/api/v1/onboarding/migration",
            json={"choice": "fresh", "confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )

    assert rejected.status_code == 409
    assert status.status_code == 200
    assert status.json()["state"] == "migration_required"
    assert status.json()["migration_choice"] is None
    assert status.json()["failure"]["retryable"] is True
    assert recovered.status_code == 200
    assert recovered.json()["migration_choice"] == "fresh"
    assert recovered.json()["failure"] is None


def test_first_work_is_fixed_reviewable_manual_and_idempotent(onboarding_env):
    settings, service, _ = onboarding_env
    _select_provider(service)

    with _client(settings, service) as client:
        csrf = client.app.state.csrf_token
        first = client.post(
            "/api/v1/onboarding/first-work",
            json={"confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        repeated = client.post(
            "/api/v1/onboarding/first-work",
            json={"confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )

    assert first.status_code == 201
    assert repeated.status_code == 201
    first_plan = first.json()["plan"]
    assert repeated.json()["plan"]["plan_id"] == first_plan["plan_id"]
    assert first_plan["status"] == "ready"
    assert first_plan["approval_mode"] == "automatic_safe"
    assert first_plan["plan"]["title"] == "Reply to Your First Customer"
    assert [agent["name"] for agent in first_plan["plan"]["agents"]] == [
        "Business Assistant",
        "Review Assistant",
    ]
    assert all(agent["runtime"] == "codex_cli" for agent in first_plan["plan"]["agents"])
    assert first_plan["plan"]["approvals"] == [
        "Require one explicit single-use human approval for each workspace-local "
        "file write. Two approvals are expected; any additional governed runtime "
        "operation must surface its own approval instead of inheriting a batch grant. "
        "The Agent must initiate each exact write tool call once; a prose request does "
        "not count as an approval."
    ]
    assert first_plan["plan"]["artifacts"] == ["first-work.json", "verification.json"]
    assert "no delivery step" in first_plan["plan"]["summary"]
    assert any("reject any unexpected send request" in risk for risk in first_plan["plan"]["risks"])
    assert Path(first_plan["workspace"]).is_dir()
    assert list(Path(first_plan["workspace"]).iterdir()) == []
    assert len(service.store.list_all()) == 1
    created_events = [
        event
        for event in service.ledger.read_all()
        if event["kind"] == "onboarding_first_work_created"
    ]
    assert len(created_events) == 1


def test_first_work_cannot_relax_its_prepared_approval_mode(onboarding_env):
    _, service, _ = onboarding_env
    _select_provider(service)
    _, first = service.create_first_onboarding_work(
        OnboardingFirstWorkRequest(confirmed=True)
    )

    with pytest.raises(ValueError, match="cannot be less restrictive"):
        service.confirm_plan(
            first.plan_id,
            ConfirmRequest(
                plan_sha256=str(first.plan_sha256),
                approval_mode="automatic",
                confirmed=True,
            ),
        )

    confirmed = service.confirm_plan(
        first.plan_id,
        ConfirmRequest(
            plan_sha256=str(first.plan_sha256),
            approval_mode="automatic_safe",
            confirmed=True,
        ),
    )
    assert str(confirmed.approval_mode) == "automatic_safe"


def test_managed_first_work_writes_only_after_two_exact_approvals(onboarding_env):
    _, service, _ = onboarding_env
    _select_provider(service)
    _, first = service.create_first_onboarding_work(
        OnboardingFirstWorkRequest(confirmed=True)
    )
    service.confirm_plan(
        first.plan_id,
        ConfirmRequest(
            plan_sha256=str(first.plan_sha256),
            approval_mode="automatic_safe",
            confirmed=True,
        ),
    )
    running = service.dispatch_plan(first.plan_id)
    workspace = Path(running.workspace)
    assert running.execution is not None
    assert running.execution.kind == "onboarding_managed"
    assert list(workspace.iterdir()) == []

    service._prepare_managed_onboarding_stage(first.plan_id, 1)
    awaiting_first = service.get_plan(first.plan_id, refresh=False)
    assert awaiting_first.status == "awaiting_approval"
    assert awaiting_first.execution is not None
    assert not (workspace / "artifacts" / "first-work.json").exists()
    first_request = awaiting_first.execution.onboarding_artifact_writes[0]
    first_card = next(
        card
        for card in service.list_pending_approvals()
        if card["approval_id"] == first_request.approval_id
    )
    assert first_card["plan_id"] == first.plan_id
    assert "artifacts/first-work.json" in first_card["title"]

    service.decide_approval(
        first_request.approval_id,
        ApprovalDecisionRequest(
            decision="approve",
            decision_note="Approve the exact first local demo artifact.",
            confirmed=True,
        ),
    )
    after_first = service.get_plan(first.plan_id, refresh=False)
    assert after_first.status == "running"
    assert (workspace / "artifacts" / "first-work.json").is_file()
    assert not (workspace / "artifacts" / "verification.json").exists()

    service._prepare_managed_onboarding_stage(first.plan_id, 2)
    awaiting_second = service.get_plan(first.plan_id, refresh=False)
    assert awaiting_second.status == "awaiting_approval"
    assert awaiting_second.execution is not None
    second_request = awaiting_second.execution.onboarding_artifact_writes[1]
    assert second_request.approval_id != first_request.approval_id
    assert not (workspace / "artifacts" / "verification.json").exists()

    service.decide_approval(
        second_request.approval_id,
        ApprovalDecisionRequest(
            decision="approve",
            decision_note="Approve the exact local verification artifact.",
            confirmed=True,
        ),
    )
    completed = service.get_plan(first.plan_id, refresh=False)
    assert completed.status == "completed_unverified"
    assert completed.execution is not None
    assert completed.execution.outcome_verified is False
    writes = completed.execution.onboarding_artifact_writes
    assert [item.status for item in writes] == ["committed", "committed"]
    assert (workspace / "artifacts" / "verification.json").is_file()
    registrations = [
        event
        for event in service.ledger.read_all()
        if event["kind"] == "artifact_registered"
        and event["run_id"] == first.plan_id
    ]
    assert {event["payload"]["logical_name"] for event in registrations} == {
        "first-work.json",
        "verification.json",
    }
    assert len(
        [
            event
            for event in service.ledger.read_all()
            if event["kind"] == "onboarding_artifact_write_committed"
            and event["run_id"] == first.plan_id
        ]
    ) == 2


def test_managed_first_work_recovery_schedules_initial_stage_once(
    onboarding_env,
    monkeypatch,
):
    _, service, _ = onboarding_env
    _select_provider(service)
    _, first = service.create_first_onboarding_work(
        OnboardingFirstWorkRequest(confirmed=True)
    )
    service.confirm_plan(
        first.plan_id,
        ConfirmRequest(
            plan_sha256=str(first.plan_sha256),
            approval_mode="automatic_safe",
            confirmed=True,
        ),
    )
    running = service.dispatch_plan(first.plan_id)
    assert running.execution is not None
    assert running.execution.onboarding_artifact_writes == []

    submitted = []

    class CaptureExecutor:
        def submit(self, fn, *args):
            submitted.append((fn, args))

        def shutdown(self, **kwargs):
            del kwargs

    monkeypatch.setattr(service, "_executor", CaptureExecutor())
    service._background = True
    service.refresh_execution(first.plan_id)
    service.refresh_execution(first.plan_id)

    assert len(submitted) == 1
    assert submitted[0][1] == (first.plan_id, 1)


def test_managed_first_work_recovery_schedules_second_stage_once(
    onboarding_env,
    monkeypatch,
):
    _, service, _ = onboarding_env
    _select_provider(service)
    _, first = service.create_first_onboarding_work(
        OnboardingFirstWorkRequest(confirmed=True)
    )
    service.confirm_plan(
        first.plan_id,
        ConfirmRequest(
            plan_sha256=str(first.plan_sha256),
            approval_mode="automatic_safe",
            confirmed=True,
        ),
    )
    service.dispatch_plan(first.plan_id)
    service._prepare_managed_onboarding_stage(first.plan_id, 1)
    awaiting = service.get_plan(first.plan_id, refresh=False)
    assert awaiting.execution is not None
    first_request = awaiting.execution.onboarding_artifact_writes[0]
    service.decide_approval(
        first_request.approval_id,
        ApprovalDecisionRequest(
            decision="approve",
            decision_note="Approve the exact first local demo artifact.",
            confirmed=True,
        ),
    )
    after_first = service.get_plan(first.plan_id, refresh=False)
    assert after_first.status == "running"
    assert after_first.execution is not None
    assert [item.status for item in after_first.execution.onboarding_artifact_writes] == [
        "committed"
    ]

    submitted = []

    class CaptureExecutor:
        def submit(self, fn, *args):
            submitted.append((fn, args))

        def shutdown(self, **kwargs):
            del kwargs

    monkeypatch.setattr(service, "_executor", CaptureExecutor())
    service._background = True
    service.refresh_execution(first.plan_id)
    service.refresh_execution(first.plan_id)

    assert len(submitted) == 1
    assert submitted[0][1] == (first.plan_id, 2)


def test_managed_first_work_recovery_backfills_terminal_once(
    onboarding_env,
    monkeypatch,
):
    _, service, _ = onboarding_env
    _select_provider(service)
    _, first = service.create_first_onboarding_work(
        OnboardingFirstWorkRequest(confirmed=True)
    )
    service.confirm_plan(
        first.plan_id,
        ConfirmRequest(
            plan_sha256=str(first.plan_sha256),
            approval_mode="automatic_safe",
            confirmed=True,
        ),
    )
    service.dispatch_plan(first.plan_id)
    service._prepare_managed_onboarding_stage(first.plan_id, 1)
    awaiting_first = service.get_plan(first.plan_id, refresh=False)
    assert awaiting_first.execution is not None
    service.decide_approval(
        awaiting_first.execution.onboarding_artifact_writes[0].approval_id,
        ApprovalDecisionRequest(
            decision="approve",
            decision_note="Approve the exact first local demo artifact.",
            confirmed=True,
        ),
    )
    service._prepare_managed_onboarding_stage(first.plan_id, 2)
    awaiting_second = service.get_plan(first.plan_id, refresh=False)
    assert awaiting_second.execution is not None
    second_request = awaiting_second.execution.onboarding_artifact_writes[1]
    with monkeypatch.context() as patch:
        patch.setattr(
            service,
            "_ensure_managed_onboarding_terminal",
            lambda record: record,
        )
        service.decide_approval(
            second_request.approval_id,
            ApprovalDecisionRequest(
                decision="approve",
                decision_note="Approve the exact local verification artifact.",
                confirmed=True,
            ),
        )

    interrupted = service.get_plan(first.plan_id, refresh=False)
    assert interrupted.status == "completed_unverified"
    assert interrupted.execution is not None
    assert interrupted.execution.finish_event_recorded is False
    assert not any(
        event["kind"] == "task_execution_finished"
        and event["run_id"] == first.plan_id
        for event in service.ledger.read_all()
    )

    recovered = service.refresh_execution(first.plan_id)
    service.refresh_execution(first.plan_id)
    assert recovered.execution is not None
    assert recovered.execution.finish_event_recorded is True
    assert (
        len(
            [
                event
                for event in service.ledger.read_all()
                if event["kind"] == "task_execution_finished"
                and event["run_id"] == first.plan_id
            ]
        )
        == 1
    )


def test_failed_first_work_retry_creates_one_new_immutable_plan(onboarding_env):
    settings, service, _ = onboarding_env
    _select_provider(service)
    _, failed = service.create_first_onboarding_work(OnboardingFirstWorkRequest(confirmed=True))
    service.store.mutate(
        failed.plan_id,
        lambda current: current.model_copy(update={"status": "failed"}),
    )

    with _client(settings, service) as client:
        csrf = client.app.state.csrf_token
        retried = client.post(
            "/api/v1/onboarding/first-work",
            json={"confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        repeated = client.post(
            "/api/v1/onboarding/first-work",
            json={"confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )

    assert retried.status_code == 201
    retry_plan = retried.json()["plan"]
    assert retry_plan["plan_id"] != failed.plan_id
    assert retry_plan["status"] == "ready"
    assert repeated.json()["plan"]["plan_id"] == retry_plan["plan_id"]
    assert service.onboarding.read()["first_work_plan_id"] == retry_plan["plan_id"]
    created_events = [
        event
        for event in service.ledger.read_all()
        if event["kind"] == "onboarding_first_work_created"
    ]
    assert len(created_events) == 2
    assert created_events[-1]["payload"]["replaces_terminal_plan_id"] == failed.plan_id


def test_repeatable_first_work_uses_a_fresh_plan_bound_workspace(onboarding_env):
    _, service, _ = onboarding_env
    _select_provider(service)
    _, source = service.create_first_onboarding_work(
        OnboardingFirstWorkRequest(confirmed=True)
    )
    source_workspace = Path(source.workspace)
    artifact_dir = source_workspace / "artifacts"
    artifact_dir.mkdir(mode=0o700)
    (artifact_dir / "first-work.json").write_text("stale", encoding="utf-8")
    (artifact_dir / "verification.json").write_text("stale", encoding="utf-8")
    service.store.mutate(
        source.plan_id,
        lambda current: current.model_copy(update={"status": "failed"}),
    )

    rerun = service.prepare_plan_rerun(
        source.plan_id,
        RerunPlanRequest(confirmed=True),
    )
    repeated = service.prepare_plan_rerun(
        source.plan_id,
        RerunPlanRequest(confirmed=True),
    )

    rerun_workspace = Path(rerun.workspace)
    assert rerun.plan_id == repeated.plan_id
    assert rerun.approval_mode == "automatic_safe"
    assert rerun_workspace != source_workspace
    assert rerun_workspace.name.endswith(rerun.plan_id)
    assert rerun_workspace.is_dir()
    assert list(rerun_workspace.iterdir()) == []
    assert {item.name for item in artifact_dir.iterdir()} == {
        "first-work.json",
        "verification.json",
    }
    event = service.ledger.read_all()[-1]
    assert event["kind"] == "task_plan_rerun_prepared"
    assert event["payload"]["workspace_strategy"] == "fresh_plan_bound"

    service.store.mutate(
        rerun.plan_id,
        lambda current: current.model_copy(update={"status": "failed"}),
    )
    retry_after_failure = service.prepare_plan_rerun(
        source.plan_id,
        RerunPlanRequest(confirmed=True),
    )

    assert retry_after_failure.plan_id != rerun.plan_id
    assert retry_after_failure.revision_number == rerun.revision_number + 1
    assert retry_after_failure.approval_mode == "automatic_safe"
    retry_workspace = Path(retry_after_failure.workspace)
    assert retry_workspace != rerun_workspace
    assert retry_workspace.name.endswith(retry_after_failure.plan_id)
    assert list(retry_workspace.iterdir()) == []


def test_incomplete_completed_first_work_can_be_explicitly_replaced(onboarding_env):
    settings, service, _ = onboarding_env
    _select_provider(service)
    _, incomplete = service.create_first_onboarding_work(OnboardingFirstWorkRequest(confirmed=True))
    service.store.mutate(
        incomplete.plan_id,
        lambda current: current.model_copy(update={"status": "completed_unverified"}),
    )

    with _client(settings, service) as client:
        csrf = client.app.state.csrf_token
        unchanged = client.post(
            "/api/v1/onboarding/first-work",
            json={"confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        replaced = client.post(
            "/api/v1/onboarding/first-work",
            json={"confirmed": True, "replace_incomplete_terminal": True},
            headers={"X-QD-CSRF": csrf},
        )
        repeated = client.post(
            "/api/v1/onboarding/first-work",
            json={"confirmed": True, "replace_incomplete_terminal": True},
            headers={"X-QD-CSRF": csrf},
        )

    assert unchanged.json()["plan"]["plan_id"] == incomplete.plan_id
    replacement = replaced.json()["plan"]
    assert replacement["plan_id"] != incomplete.plan_id
    assert replacement["plan"]["title"] == "Reply to Your First Customer"
    assert repeated.json()["plan"]["plan_id"] == replacement["plan_id"]
    assert service.get_plan(incomplete.plan_id, refresh=False).status == "completed_unverified"
    assert service.onboarding.read()["first_work_plan_id"] == replacement["plan_id"]
    created = [
        event
        for event in service.ledger.read_all()
        if event["kind"] == "onboarding_first_work_created"
    ]
    assert created[-1]["payload"]["replaces_terminal_plan_id"] == incomplete.plan_id
    assert created[-1]["payload"]["replaces_incomplete_terminal_plan_id"] == incomplete.plan_id


def test_unstarted_legacy_first_work_requires_explicit_audited_replacement(onboarding_env):
    settings, service, _ = onboarding_env
    _select_provider(service)
    _, legacy = service.create_first_onboarding_work(OnboardingFirstWorkRequest(confirmed=True))

    def make_legacy(current):
        assert current.plan is not None
        updated = current.model_copy(
            update={
                "plan": current.plan.model_copy(update={"title": "My First Evidence Work"}),
            }
        )
        updated.plan_sha256 = _execution_plan_sha(updated)
        return updated

    service.store.mutate(legacy.plan_id, make_legacy)

    with _client(settings, service) as client:
        csrf = client.app.state.csrf_token
        unchanged = client.post(
            "/api/v1/onboarding/first-work",
            json={"confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )
        replaced = client.post(
            "/api/v1/onboarding/first-work",
            json={"confirmed": True, "replace_unstarted_legacy": True},
            headers={"X-QD-CSRF": csrf},
        )
        repeated = client.post(
            "/api/v1/onboarding/first-work",
            json={"confirmed": True, "replace_unstarted_legacy": True},
            headers={"X-QD-CSRF": csrf},
        )

    assert unchanged.json()["plan"]["plan_id"] == legacy.plan_id
    replacement = replaced.json()["plan"]
    assert replacement["plan_id"] != legacy.plan_id
    assert replacement["plan"]["title"] == "Reply to Your First Customer"
    assert repeated.json()["plan"]["plan_id"] == replacement["plan_id"]
    assert service.get_plan(legacy.plan_id, refresh=False).status == "ready"
    assert service.onboarding.read()["first_work_plan_id"] == replacement["plan_id"]
    created = [
        event
        for event in service.ledger.read_all()
        if event["kind"] == "onboarding_first_work_created"
    ]
    assert created[-1]["payload"]["template"] == "first-customer-reply-v2"
    assert created[-1]["payload"]["replaces_unstarted_legacy_plan_id"] == legacy.plan_id


def test_active_legacy_first_work_cannot_be_replaced(onboarding_env):
    settings, service, _ = onboarding_env
    _select_provider(service)
    _, legacy = service.create_first_onboarding_work(OnboardingFirstWorkRequest(confirmed=True))

    def make_active_legacy(current):
        assert current.plan is not None
        updated = current.model_copy(
            update={
                "status": "confirmed",
                "plan": current.plan.model_copy(update={"title": "My First Evidence Work"}),
            }
        )
        updated.plan_sha256 = _execution_plan_sha(updated)
        return updated

    service.store.mutate(legacy.plan_id, make_active_legacy)

    with _client(settings, service) as client:
        response = client.post(
            "/api/v1/onboarding/first-work",
            json={"confirmed": True, "replace_unstarted_legacy": True},
            headers={"X-QD-CSRF": client.app.state.csrf_token},
        )

    assert response.status_code == 409
    assert "unstarted legacy" in response.json()["detail"]
    assert service.onboarding.read()["first_work_plan_id"] == legacy.plan_id
    assert len(service.store.list_all()) == 1


def test_completed_legacy_first_work_remains_signoff_compatible(
    onboarding_env,
    tmp_path: Path,
):
    _, service, _ = onboarding_env
    _select_provider(service)
    _, legacy = service.create_first_onboarding_work(OnboardingFirstWorkRequest(confirmed=True))

    def make_completed_legacy(current):
        assert current.plan is not None
        updated = current.model_copy(
            update={
                "status": "completed_unverified",
                "plan": current.plan.model_copy(update={"title": "My First Evidence Work"}),
            }
        )
        updated.plan_sha256 = _execution_plan_sha(updated)
        return updated

    service.store.mutate(legacy.plan_id, make_completed_legacy)
    first_source = tmp_path / "legacy-first-work.json"
    first_source.write_text(
        '{"schema_version":1,"message":"Hello from OpsWitness","technical_demo_only":true}',
        encoding="utf-8",
    )
    first_event = register_console_artifact(
        service.ledger,
        first_source,
        plan_id=legacy.plan_id,
        logical_name="first-work.json",
        labels=["console-output", "requires-signoff"],
    )
    verification_source = tmp_path / "legacy-verification.json"
    verification_source.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact": "first-work.json",
                "sha256": first_event["payload"]["sha256"],
                "verified": True,
                "technical_demo_only": True,
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    verification_event = register_console_artifact(
        service.ledger,
        verification_source,
        plan_id=legacy.plan_id,
        logical_name="verification.json",
        labels=["console-output", "requires-signoff"],
    )

    snapshot = service.signoff_onboarding_artifacts(
        legacy.plan_id,
        ArtifactSignoffRequest(
            confirmed=True,
            first_work_event_id=first_event["event_id"],
            first_work_sha256=first_event["payload"]["sha256"],
            verification_event_id=verification_event["event_id"],
            verification_sha256=verification_event["payload"]["sha256"],
        ),
    )

    assert snapshot.complete is True
    signoff = service._onboarding_artifact_signoff(legacy.plan_id)
    assert signoff is not None
    assert signoff["payload"]["note"] == (
        "Technical demo artifacts reviewed; no real business outcome was evaluated."
    )


def test_artifact_signoff_validates_cas_and_records_review_without_business_success(
    onboarding_env,
    tmp_path: Path,
):
    settings, service, _ = onboarding_env
    _select_provider(service)
    _, record = service.create_first_onboarding_work(OnboardingFirstWorkRequest(confirmed=True))
    service.store.mutate(
        record.plan_id,
        lambda current: current.model_copy(update={"status": "completed_unverified"}),
    )
    first_payload = SYNTHETIC_REPLY_PAYLOAD
    first_source = tmp_path / "first-work.json"
    first_source.write_text(
        json.dumps(first_payload, separators=(",", ":")),
        encoding="utf-8",
    )
    first_event = register_console_artifact(
        service.ledger,
        first_source,
        plan_id=record.plan_id,
        logical_name="first-work.json",
        labels=["console-output", "requires-signoff"],
    )
    verification_source = tmp_path / "verification.json"
    verification_source.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact": "first-work.json",
                "sha256": first_event["payload"]["sha256"],
                "checks": {
                    "follow_up_questions_present": True,
                    "no_price_commitment": True,
                    "no_start_date_commitment": True,
                    "delivery_requested": False,
                },
                "approved_as_draft": True,
                "fictional_scenario": True,
                "technical_demo_only": True,
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    verification_event = register_console_artifact(
        service.ledger,
        verification_source,
        plan_id=record.plan_id,
        logical_name="verification.json",
        labels=["console-output", "requires-signoff"],
    )
    review = {
        "confirmed": True,
        "first_work_event_id": first_event["event_id"],
        "first_work_sha256": first_event["payload"]["sha256"],
        "verification_event_id": verification_event["event_id"],
        "verification_sha256": verification_event["payload"]["sha256"],
    }

    with _client(settings, service) as client:
        csrf = client.app.state.csrf_token
        signed = client.post(
            f"/api/v1/works/{record.plan_id}/artifact-signoff",
            json=review,
            headers={"X-QD-CSRF": csrf},
        )
        repeated = client.post(
            f"/api/v1/works/{record.plan_id}/artifact-signoff",
            json=review,
            headers={"X-QD-CSRF": csrf},
        )
        verification_source.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "artifact": "first-work.json",
                    "sha256": first_event["payload"]["sha256"],
                    "checks": {
                        "follow_up_questions_present": True,
                        "no_price_commitment": True,
                        "no_start_date_commitment": True,
                        "delivery_requested": False,
                    },
                    "approved_as_draft": True,
                    "fictional_scenario": True,
                    "technical_demo_only": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        register_console_artifact(
            service.ledger,
            verification_source,
            plan_id=record.plan_id,
            logical_name="verification.json",
            labels=["console-output", "requires-signoff"],
        )
        stale_review = client.post(
            f"/api/v1/works/{record.plan_id}/artifact-signoff",
            json=review,
            headers={"X-QD-CSRF": csrf},
        )
        unexpected_source = tmp_path / "unexpected.json"
        unexpected_source.write_text('{"unexpected":true}', encoding="utf-8")
        register_console_artifact(
            service.ledger,
            unexpected_source,
            plan_id=record.plan_id,
            logical_name="unexpected.json",
            labels=["console-output"],
        )
        unexpected_review = client.post(
            f"/api/v1/works/{record.plan_id}/artifact-signoff",
            json=review,
            headers={"X-QD-CSRF": csrf},
        )

    assert signed.status_code == 200
    assert signed.json()["complete"] is True
    assert signed.json()["state"] == "complete"
    assert repeated.status_code == 200
    assert stale_review.status_code == 409
    assert "evidence changed" in stale_review.json()["detail"]
    assert unexpected_review.status_code == 409
    assert "exactly the two" in unexpected_review.json()["detail"]
    signoffs = [event for event in service.ledger.read_all() if event["kind"] == "artifact_signoff"]
    assert len(signoffs) == 1
    assert signoffs[0]["payload"]["note"] == (
        "Synthetic customer-reply draft and review artifacts inspected; delivery was outside "
        "the reviewed workflow and no real business outcome was evaluated."
    )
    unchanged = service.get_plan(record.plan_id, refresh=False)
    assert unchanged.status == "completed_unverified"
    assert unchanged.execution is None


def test_insufficient_disk_blocks_first_work_with_recoverable_status(onboarding_env):
    settings, service, _ = onboarding_env
    _select_provider(service)
    service.onboarding._disk_usage = lambda path: SimpleNamespace(  # type: ignore[method-assign]
        total=4 * 1024**3,
        used=3 * 1024**3,
        free=1 * 1024**3,
    )

    with _client(settings, service) as client:
        status = client.get("/api/v1/onboarding")
        csrf = client.app.state.csrf_token
        blocked = client.post(
            "/api/v1/onboarding/first-work",
            json={"confirmed": True},
            headers={"X-QD-CSRF": csrf},
        )

    assert status.status_code == 200
    assert status.json()["state"] == "self_check"
    assert status.json()["failure"]["code"] == "insufficient_disk_space"
    assert status.json()["failure"]["retryable"] is True
    assert blocked.status_code == 409
    assert service.store.list_all() == []
