import base64
import json
import os
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opswitness.artifacts import register_console_artifact
from opswitness.config import Settings
from opswitness.console.app import create_app
from opswitness.console.schemas import (
    DeletePlanRequest,
    EraseRunRequest,
    PlanningAttachmentUpload,
    PlanRequest,
    ProjectLibraryMetadata,
    ProjectLibraryMetadataUpdate,
)
from opswitness.console.service import (
    ConsoleConflict,
    ConsoleService,
    ConsoleUnavailable,
    RuntimeArtifactNotFound,
)
from opswitness.ids import new_ulid


@pytest.fixture(autouse=True)
def isolated_install_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "config"
    config.mkdir(mode=0o700)
    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(config))
    monkeypatch.setenv("OPSWITNESS_LEDGER_DIR", str(tmp_path / "ledger"))
    monkeypatch.setenv("OPSWITNESS_CONSOLE__STATE_DIR", str(tmp_path / "console"))
    monkeypatch.setenv("OPSWITNESS_SERVICES__LOG_DIR", str(tmp_path / "logs"))


def _service(tmp_path: Path) -> tuple[Settings, ConsoleService]:
    settings = Settings(
        ledger_dir=tmp_path / "ledger",
        console={"state_dir": tmp_path / "console", "port": 8765},
        paperclip={"api_key": "test", "company_id": "company-1"},
    )
    service = ConsoleService(
        settings,
        aion=object(),  # type: ignore[arg-type]
        paperclip_factory=lambda: object(),  # type: ignore[arg-type,return-value]
        background=False,
    )
    return settings, service


def _seed_library(
    tmp_path: Path,
) -> tuple[Settings, ConsoleService, str, bytes, bytes]:
    settings, service = _service(tmp_path)
    input_bytes = b"account=fictional\\nstatus=reviewed\\n"
    record = service.request_plan(
        PlanRequest(
            objective="整理项目资料并保留可验证产物",
            attachments=[
                PlanningAttachmentUpload(
                    name="customer-brief.txt",
                    media_type="text/plain",
                    content_base64=base64.b64encode(input_bytes).decode("ascii"),
                )
            ],
        )
    )
    workspace = settings.console.state_dir / "executions" / record.plan_id
    artifact_dir = workspace / "artifacts"
    artifact_dir.mkdir(parents=True, mode=0o700)
    workspace_bytes = json.dumps({"status": "draft", "version": 2}).encode()
    (artifact_dir / "reply-v2.json").write_bytes(workspace_bytes)
    source = tmp_path / "reply-v1.json"
    source.write_text('{"status":"reviewed","version":1}', encoding="utf-8")
    register_console_artifact(
        service.ledger,
        source,
        plan_id=record.plan_id,
        logical_name="reply-v1.json",
        labels=["customer-reply"],
    )
    return settings, service, record.plan_id, input_bytes, workspace_bytes


def test_project_library_projects_searches_and_reverifies_content(tmp_path: Path):
    settings, service, plan_id, input_bytes, workspace_bytes = _seed_library(tmp_path)
    rows = service.list_project_library()

    assert {row["source_kind"] for row in rows} == {
        "planning_input",
        "registered_output",
        "workspace_output",
    }
    assert {row["name"] for row in rows} == {
        "customer-brief.txt",
        "reply-v1.json",
        "reply-v2.json",
    }
    assert service.list_project_library(query="fictional") == []
    assert [row["name"] for row in service.list_project_library(query="customer-reply")] == [
        "reply-v1.json"
    ]
    assert [row["name"] for row in service.list_project_library(file_type="txt")] == [
        "customer-brief.txt"
    ]
    assert len(service.list_project_library(work_id=plan_id)) == 3

    input_item = next(row for row in rows if row["source_kind"] == "planning_input")
    workspace_item = next(row for row in rows if row["source_kind"] == "workspace_output")
    assert service.get_project_library_content(input_item["asset_id"])["content"] == input_bytes
    assert (
        service.get_project_library_content(workspace_item["asset_id"])["content"]
        == workspace_bytes
    )
    assert service.get_project_library_item(workspace_item["asset_id"])["preview"] == {
        "status": "draft",
        "version": 2,
    }
    assert str(settings.console.state_dir) not in json.dumps(rows)

    workspace_path = (
        settings.console.state_dir
        / "executions"
        / plan_id
        / "artifacts"
        / "reply-v2.json"
    )
    workspace_path.write_text('{"status":"changed"}', encoding="utf-8")
    try:
        service.get_project_library_content(workspace_item["asset_id"])
    except RuntimeArtifactNotFound:
        pass
    else:
        raise AssertionError("a changed workspace file must receive a new identity")


def test_project_library_metadata_is_private_bound_and_cycle_safe(tmp_path: Path):
    settings, service, _, _, _ = _seed_library(tmp_path)
    rows = service.list_project_library()
    older = next(row for row in rows if row["name"] == "reply-v1.json")
    newer = next(row for row in rows if row["name"] == "reply-v2.json")

    updated = service.update_project_library_metadata(
        newer["asset_id"],
        ProjectLibraryMetadataUpdate(
            expected_sha256=newer["sha256"],
            user_tags=["客户", "  待复核  ", "客户"],
            supersedes_asset_id=older["asset_id"],
            confirmed=True,
        ),
    )
    assert updated["user_tags"] == ["客户", "待复核"]
    assert updated["supersedes_asset_id"] == older["asset_id"]
    metadata_root = settings.console.state_dir / "project-library"
    metadata_path = metadata_root / f"{newer['asset_id']}.json"
    assert stat.S_IMODE(metadata_root.stat().st_mode) == 0o700
    assert stat.S_IMODE(metadata_path.stat().st_mode) == 0o600
    assert "客户" in service.list_project_library(tag="客户")[0]["user_tags"]

    try:
        service.update_project_library_metadata(
            older["asset_id"],
            ProjectLibraryMetadataUpdate(
                expected_sha256=older["sha256"],
                supersedes_asset_id=newer["asset_id"],
                confirmed=True,
            ),
        )
    except ValueError as exc:
        assert "cycle" in str(exc)
    else:
        raise AssertionError("a version cycle must be rejected")

    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["sha256"] = "0" * 64
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        service.list_project_library()
    except ConsoleConflict as exc:
        assert "binding is invalid" in str(exc)
    else:
        raise AssertionError("metadata with a different hash binding must fail closed")


def test_project_library_http_is_read_only_except_explicit_metadata(tmp_path: Path):
    settings, service, _, input_bytes, _ = _seed_library(tmp_path)
    service.acquire_instance_lease = lambda: True  # type: ignore[method-assign]
    service.recover_startup = lambda: {}  # type: ignore[method-assign]
    service.release_instance_lease = lambda: None  # type: ignore[method-assign]
    app = create_app(settings, service=service)
    csrf = app.state.csrf_token

    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        listed = client.get("/api/v1/project-library")
        assert listed.status_code == 200
        input_item = next(
            row for row in listed.json() if row["source_kind"] == "planning_input"
        )
        opened = client.get(f"/api/v1/project-library/{input_item['asset_id']}/content")
        assert opened.status_code == 200
        assert opened.content == input_bytes
        assert opened.headers["x-opswitness-artifact-sha256"] == input_item["sha256"]

        denied = client.patch(
            f"/api/v1/project-library/{input_item['asset_id']}",
            json={
                "expected_sha256": input_item["sha256"],
                "user_tags": ["source"],
                "supersedes_asset_id": None,
                "confirmed": True,
            },
        )
        assert denied.status_code == 403
        accepted = client.patch(
            f"/api/v1/project-library/{input_item['asset_id']}",
            headers={"X-QD-CSRF": csrf},
            json={
                "expected_sha256": input_item["sha256"],
                "user_tags": ["source"],
                "supersedes_asset_id": None,
                "confirmed": True,
            },
        )
        assert accepted.status_code == 200
        assert accepted.json()["user_tags"] == ["source"]


def test_run_erasure_fails_closed_then_recovers_and_removes_private_metadata(
    tmp_path: Path,
):
    settings, service, plan_id, _, _ = _seed_library(tmp_path)
    workspace_item = next(
        row for row in service.list_project_library() if row["source_kind"] == "workspace_output"
    )
    service.update_project_library_metadata(
        workspace_item["asset_id"],
        ProjectLibraryMetadataUpdate(
            expected_sha256=workspace_item["sha256"],
            user_tags=["private"],
            confirmed=True,
        ),
    )
    metadata_path = (
        settings.console.state_dir
        / "project-library"
        / f"{workspace_item['asset_id']}.json"
    )
    metadata_lock_path = metadata_path.with_name(f".{workspace_item['asset_id']}.lock")
    valid_metadata = metadata_path.read_bytes()
    rebound_metadata = json.loads(valid_metadata)
    rebound_metadata["plan_id"] = new_ulid()
    metadata_path.write_text(json.dumps(rebound_metadata), encoding="utf-8")

    terminal = service.store.mutate(
        plan_id,
        lambda current: current.model_copy(
            update={
                "status": "failed",
                "plan_sha256": "f" * 64,
                "planning_progress": None,
            },
            deep=True,
        ),
    )
    request = EraseRunRequest(
        confirmed=True,
        expected_plan_sha256=str(terminal.plan_sha256),
    )
    run_root = settings.console.state_dir / "executions" / plan_id
    with pytest.raises(ConsoleUnavailable, match="could not be verified"):
        service.erase_run_data(plan_id, request)
    assert run_root.is_dir()
    assert service.store.get(plan_id).erased_at is None
    assert metadata_path.is_file()

    metadata_path.write_bytes(valid_metadata)
    result = service.erase_run_data(plan_id, request)
    assert result["erased"] is True
    assert not metadata_path.exists()
    assert not metadata_lock_path.exists()
    assert service.project_library.list_all() == {}

    service.project_library.put(
        ProjectLibraryMetadata(
            asset_id=workspace_item["asset_id"],
            source_kind=workspace_item["source_kind"],
            plan_id=workspace_item["plan_id"],
            source_ref=workspace_item["source_ref"],
            name=workspace_item["name"],
            sha256=workspace_item["sha256"],
            user_tags=["stale"],
        )
    )
    assert metadata_path.is_file()
    assert service.erase_run_data(plan_id, request) == result
    assert not metadata_path.exists()
    assert not metadata_lock_path.exists()


def test_deleted_cross_work_predecessor_is_an_explicit_unavailable_link(tmp_path: Path):
    _, service = _service(tmp_path)
    older_record = service.request_plan(
        PlanRequest(
            objective="保留旧版客户材料",
            attachments=[
                PlanningAttachmentUpload(
                    name="customer-note.txt",
                    media_type="text/plain",
                    content_base64=base64.b64encode(b"older").decode("ascii"),
                )
            ],
        )
    )
    newer_record = service.request_plan(
        PlanRequest(
            objective="保留新版客户材料",
            attachments=[
                PlanningAttachmentUpload(
                    name="customer-note.txt",
                    media_type="text/plain",
                    content_base64=base64.b64encode(b"newer").decode("ascii"),
                )
            ],
        )
    )
    rows = service.list_project_library()
    older = next(row for row in rows if row["plan_id"] == older_record.plan_id)
    newer = next(row for row in rows if row["plan_id"] == newer_record.plan_id)
    service.update_project_library_metadata(
        newer["asset_id"],
        ProjectLibraryMetadataUpdate(
            expected_sha256=newer["sha256"],
            supersedes_asset_id=older["asset_id"],
            confirmed=True,
        ),
    )
    service.store.mutate(
        older_record.plan_id,
        lambda current: current.model_copy(
            update={"status": "ready", "planning_progress": None},
            deep=True,
        ),
    )
    service.delete_plan(older_record.plan_id, DeletePlanRequest(confirmed=True))

    retained = service.list_project_library()
    assert {row["plan_id"] for row in retained} == {newer_record.plan_id}
    linked = retained[0]
    assert linked["supersedes_asset_id"] == older["asset_id"]
    assert linked["supersedes_status"] == "unavailable"
    assert linked["superseded_by_asset_ids"] == []

    preserved = service.update_project_library_metadata(
        linked["asset_id"],
        ProjectLibraryMetadataUpdate(
            expected_sha256=linked["sha256"],
            user_tags=["仍需复核"],
            supersedes_asset_id=older["asset_id"],
            confirmed=True,
        ),
    )
    assert preserved["supersedes_status"] == "unavailable"
    cleared = service.update_project_library_metadata(
        linked["asset_id"],
        ProjectLibraryMetadataUpdate(
            expected_sha256=linked["sha256"],
            user_tags=["仍需复核"],
            supersedes_asset_id=None,
            confirmed=True,
        ),
    )
    assert cleared["supersedes_asset_id"] is None
    assert cleared["supersedes_status"] == "none"


def test_erased_parent_shell_keeps_child_revision_in_project_library(tmp_path: Path):
    _, service = _service(tmp_path)
    parent = service.request_plan(
        PlanRequest(
            objective="父版本客户材料",
            attachments=[
                PlanningAttachmentUpload(
                    name="brief.txt",
                    media_type="text/plain",
                    content_base64=base64.b64encode(b"retained by child").decode("ascii"),
                )
            ],
        )
    )
    terminal_parent = service.store.mutate(
        parent.plan_id,
        lambda current: current.model_copy(
            update={
                "status": "failed",
                "plan_sha256": "a" * 64,
                "planning_progress": None,
            },
            deep=True,
        ),
    )
    child_id = new_ulid()
    child = terminal_parent.model_copy(
        update={
            "plan_id": child_id,
            "status": "planning",
            "objective": "子版本客户材料",
            "plan_sha256": None,
            "parent_plan_id": parent.plan_id,
            "parent_plan_sha256": terminal_parent.plan_sha256,
            "revision_number": 2,
            "erased_at": None,
            "erasure_event_id": None,
        },
        deep=True,
    )
    service.store.create(child)

    service.erase_run_data(
        parent.plan_id,
        EraseRunRequest(
            confirmed=True,
            expected_plan_sha256=str(terminal_parent.plan_sha256),
        ),
    )
    rows = service.list_project_library()
    assert len(rows) == 1
    assert rows[0]["plan_id"] == child_id
    assert rows[0]["work_id"] == parent.plan_id
    assert rows[0]["revision_number"] == 2
    assert rows[0]["name"] == "brief.txt"


def test_persisted_project_library_version_cycle_fails_closed(tmp_path: Path):
    _, service, _, _, _ = _seed_library(tmp_path)
    rows = service.list_project_library()
    older = next(row for row in rows if row["name"] == "reply-v1.json")
    newer = next(row for row in rows if row["name"] == "reply-v2.json")
    service.update_project_library_metadata(
        newer["asset_id"],
        ProjectLibraryMetadataUpdate(
            expected_sha256=newer["sha256"],
            supersedes_asset_id=older["asset_id"],
            confirmed=True,
        ),
    )
    service.project_library.put(
        ProjectLibraryMetadata(
            asset_id=older["asset_id"],
            source_kind=older["source_kind"],
            plan_id=older["plan_id"],
            source_ref=older["source_ref"],
            name=older["name"],
            sha256=older["sha256"],
            supersedes_asset_id=newer["asset_id"],
        )
    )

    with pytest.raises(ConsoleConflict, match="persisted cycle"):
        service.list_project_library()


def test_workspace_output_read_stays_bound_to_open_artifact_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    settings, service, plan_id, _, workspace_bytes = _seed_library(tmp_path)
    workspace_item = next(
        row for row in service.list_project_library() if row["source_kind"] == "workspace_output"
    )
    artifact_dir = settings.console.state_dir / "executions" / plan_id / "artifacts"
    displaced_dir = artifact_dir.with_name("artifacts-original")
    original_open = os.open
    swapped = False

    def racing_open(
        path: os.PathLike[str] | str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if (
            not swapped
            and Path(os.fspath(path)).name == workspace_item["name"]
            and not flags & getattr(os, "O_DIRECTORY", 0)
        ):
            swapped = True
            artifact_dir.rename(displaced_dir)
            artifact_dir.mkdir(mode=0o700)
            (artifact_dir / workspace_item["name"]).write_bytes(b"x" * len(workspace_bytes))
        if dir_fd is None:
            return original_open(path, flags, mode)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", racing_open)
    opened = service._read_project_library_content(workspace_item)
    assert swapped is True
    assert opened["content"] == workspace_bytes
