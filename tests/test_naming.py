from __future__ import annotations

import pytest
from pydantic import ValidationError

from opswitness.console.schemas import (
    ProcessMemoryProposalRequest,
    TaskTemplate,
    TaskTemplateFromPlanRequest,
    TaskTemplateSaveRequest,
    TeamBlueprint,
    TeamBlueprintSaveRequest,
    WorkspaceMemoryCandidateRequest,
    WorkspaceMemoryVersion,
)
from opswitness.naming import (
    LEGACY_CLI_ALIAS,
    PACKAGE_AND_CLI_NAME,
    PRODUCT_DISPLAY_NAME,
    validate_new_display_name,
    validate_optional_new_display_name,
)


def test_canonical_product_names_are_explicit() -> None:
    assert PRODUCT_DISPLAY_NAME == "OpsWitness"
    assert PACKAGE_AND_CLI_NAME == "opswitness"
    assert LEGACY_CLI_ALIAS == "qd"


@pytest.mark.parametrize(
    "value",
    [
        "Weekly customer follow-up",
        "客户回复复核",
        "Evidence review — July",
    ],
)
def test_new_display_names_preserve_valid_authored_text(value: str) -> None:
    assert validate_new_display_name(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        " leading",
        "trailing ",
        "two  spaces",
        "path/name",
        r"path\name",
        ".",
        "..",
        "line\nbreak",
        "zero\u200bwidth",
        "right\u202eto-left",
        "e\u0301vidence",
    ],
)
def test_new_display_names_fail_closed_without_normalizing(value: str) -> None:
    with pytest.raises(ValueError):
        validate_new_display_name(value)


def test_optional_new_display_name_preserves_absence() -> None:
    assert validate_optional_new_display_name(None) is None


@pytest.mark.parametrize(
    ("request_type", "payload"),
    [
        (
            TeamBlueprintSaveRequest,
            {
                "source_plan_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
                "name": "unsafe/name",
                "confirmed": True,
            },
        ),
        (
            TaskTemplateSaveRequest,
            {
                "name": " unsafe",
                "objective": "Prepare a weekly customer update",
                "confirmed": True,
            },
        ),
        (
            TaskTemplateFromPlanRequest,
            {"name": "unsafe\nname", "confirmed": True},
        ),
        (
            WorkspaceMemoryCandidateRequest,
            {
                "kind": "process",
                "title": "unsafe  name",
                "content": "Review every exact artifact.",
                "confirmed": True,
            },
        ),
        (
            ProcessMemoryProposalRequest,
            {"title": "unsafe/name", "confirmed": True},
        ),
    ],
)
def test_new_display_name_mutations_use_the_canonical_validator(
    request_type: type,
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="display name"):
        request_type.model_validate(payload)


def test_historical_read_models_do_not_revalidate_recorded_display_names() -> None:
    historical = TaskTemplate.model_validate(
        {
            "schema_version": 1,
            "template_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "name": " Quarterdeck/legacy name ",
            "objective": "Retain this exact historical task template.",
            "created_at": "2026-07-01T00:00:00+00:00",
            "archived_at": None,
            "source_plan_id": None,
            "source_plan_sha256": None,
            "template_sha256": "a" * 64,
        }
    )
    assert historical.name == " Quarterdeck/legacy name "

    blueprint = TeamBlueprint.model_validate(
        {
            "schema_version": 1,
            "blueprint_id": "01ARZ3NDEKTSV4RRFFQ69G5FAW",
            "name": " Legacy/blueprint ",
            "created_at": "2026-07-01T00:00:00+00:00",
            "archived_at": None,
            "source_plan_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "source_plan_sha256": "b" * 64,
            "verification_status": "unverified",
            "agents": [
                {
                    "key": "agent_1",
                    "role": "lead",
                    "reports_to_key": None,
                    "runtime": "codex_cli",
                }
            ],
            "collaboration_loops": [],
            "blueprint_sha256": "c" * 64,
        }
    )
    assert blueprint.name == " Legacy/blueprint "

    memory = WorkspaceMemoryVersion.model_validate(
        {
            "schema_version": 1,
            "memory_id": "01ARZ3NDEKTSV4RRFFQ69G5FAX",
            "version_id": "01ARZ3NDEKTSV4RRFFQ69G5FAY",
            "version_number": 1,
            "kind": "process",
            "title": " Legacy/memory ",
            "tags": [],
            "workspace": "",
            "source_plan_id": None,
            "source_plan_sha256": None,
            "parent_version_id": None,
            "created_at": "2026-07-01T00:00:00+00:00",
            "content_sha256": "d" * 64,
            "document_sha256": "e" * 64,
            "relative_path": "process/legacy.md",
        }
    )
    assert memory.title == " Legacy/memory "
