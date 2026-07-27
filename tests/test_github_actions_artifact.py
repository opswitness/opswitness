import argparse
import hashlib
import io
import stat
import zipfile

import pytest

from scripts import github_actions_artifact as provenance


REPOSITORY = "opswitness/opswitness"
REPOSITORY_ID = 42
RUN_ID = 123456
RUN_ATTEMPT = 2
WORKFLOW_ID = 9876
COMMIT = "a" * 40
ARTIFACT_DIGEST = "b" * 64
WORKFLOW_PATH = ".github/workflows/release.yml"
ARTIFACT_NAME = f"release-candidate-{RUN_ID}-{RUN_ATTEMPT}"


def _expectation() -> provenance.ProducerExpectation:
    return provenance.ProducerExpectation(
        repository=REPOSITORY,
        repository_id=REPOSITORY_ID,
        run_id=RUN_ID,
        run_attempt=RUN_ATTEMPT,
        head_sha=COMMIT,
        workflow_id=WORKFLOW_ID,
        workflow_path=WORKFLOW_PATH,
        event="workflow_dispatch",
        head_branch="main",
        artifact_name=ARTIFACT_NAME,
        artifact_digest=ARTIFACT_DIGEST,
    )


def _api_payloads():
    workflow = {
        "id": WORKFLOW_ID,
        "path": WORKFLOW_PATH,
        "state": "active",
    }
    run = {
        "id": RUN_ID,
        "workflow_id": WORKFLOW_ID,
        "run_attempt": RUN_ATTEMPT,
        "head_sha": COMMIT,
        "head_branch": "main",
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "path": f"{WORKFLOW_PATH}@refs/heads/main",
        "repository": {
            "id": REPOSITORY_ID,
            "full_name": REPOSITORY,
        },
        "head_repository": {
            "id": REPOSITORY_ID,
            "full_name": REPOSITORY,
        },
    }
    artifact = {
        "id": 654321,
        "name": ARTIFACT_NAME,
        "expired": False,
        "size_in_bytes": 123,
        "digest": f"sha256:{ARTIFACT_DIGEST}",
        "archive_download_url": (
            "https://api.github.com/repos/opswitness/opswitness/"
            "actions/artifacts/654321/zip"
        ),
        "workflow_run": {
            "id": RUN_ID,
            "repository_id": REPOSITORY_ID,
            "head_repository_id": REPOSITORY_ID,
            "head_sha": COMMIT,
        },
    }
    listing = {"total_count": 1, "artifacts": [artifact]}
    return workflow, run, listing


def test_verify_producer_binds_attempt_workflow_repository_and_artifact_digest():
    workflow, run, listing = _api_payloads()

    artifact = provenance.verify_producer(
        expectation=_expectation(),
        workflow=workflow,
        run=run,
        artifact_listing=listing,
    )

    assert artifact == provenance.VerifiedArtifact(
        artifact_id=654321,
        name=ARTIFACT_NAME,
        digest=ARTIFACT_DIGEST,
        size_in_bytes=123,
        archive_download_url=(
            "https://api.github.com/repos/opswitness/opswitness/"
            "actions/artifacts/654321/zip"
        ),
    )


@pytest.mark.parametrize(
    ("target", "key", "value", "message"),
    [
        ("workflow", "id", WORKFLOW_ID + 1, "workflow API ID"),
        ("workflow", "path", ".github/workflows/other.yml", "workflow API path"),
        ("workflow", "state", "disabled_manually", "not active"),
        ("run", "id", RUN_ID + 1, "run id"),
        ("run", "workflow_id", WORKFLOW_ID + 1, "different workflow ID"),
        ("run", "run_attempt", RUN_ATTEMPT + 1, "attempt"),
        ("run", "head_sha", "c" * 40, "head SHA"),
        ("run", "head_branch", "feature", "branch"),
        ("run", "event", "push", "event"),
        ("run", "status", "in_progress", "completed successfully"),
        ("run", "conclusion", "failure", "completed successfully"),
        ("run", "path", ".github/workflows/other.yml", "run path"),
        ("artifact", "name", "other", "artifact name"),
        ("artifact", "expired", True, "expired"),
        ("artifact", "digest", f"sha256:{'d' * 64}", "approved digest"),
    ],
)
def test_verify_producer_rejects_identity_mutations(
    target,
    key,
    value,
    message,
):
    workflow, run, listing = _api_payloads()
    payload = {
        "workflow": workflow,
        "run": run,
        "artifact": listing["artifacts"][0],
    }[target]
    payload[key] = value

    with pytest.raises(provenance.ProvenanceError, match=message):
        provenance.verify_producer(
            expectation=_expectation(),
            workflow=workflow,
            run=run,
            artifact_listing=listing,
        )


@pytest.mark.parametrize(
    ("target", "field", "value", "message"),
    [
        ("repository", "id", REPOSITORY_ID + 1, "repository does not match"),
        ("repository", "full_name", "attacker/fork", "repository does not match"),
        ("head_repository", "id", REPOSITORY_ID + 1, "fork or other"),
        ("head_repository", "full_name", "attacker/fork", "fork or other"),
        ("artifact_run", "id", RUN_ID + 1, "artifact workflow run id"),
        ("artifact_run", "repository_id", REPOSITORY_ID + 1, "different repository"),
        (
            "artifact_run",
            "head_repository_id",
            REPOSITORY_ID + 1,
            "different repository",
        ),
        ("artifact_run", "head_sha", "d" * 40, "artifact workflow run head SHA"),
    ],
)
def test_verify_producer_rejects_repository_cross_binding(
    target,
    field,
    value,
    message,
):
    workflow, run, listing = _api_payloads()
    targets = {
        "repository": run["repository"],
        "head_repository": run["head_repository"],
        "artifact_run": listing["artifacts"][0]["workflow_run"],
    }
    targets[target][field] = value

    with pytest.raises(provenance.ProvenanceError, match=message):
        provenance.verify_producer(
            expectation=_expectation(),
            workflow=workflow,
            run=run,
            artifact_listing=listing,
        )


@pytest.mark.parametrize(
    "listing",
    [
        {"total_count": 0, "artifacts": []},
        {"total_count": 2, "artifacts": [{}, {}]},
        {"total_count": 1, "artifacts": []},
    ],
)
def test_verify_producer_requires_one_exact_artifact(listing):
    workflow, run, _ = _api_payloads()

    with pytest.raises(provenance.ProvenanceError, match="exactly one artifact"):
        provenance.verify_producer(
            expectation=_expectation(),
            workflow=workflow,
            run=run,
            artifact_listing=listing,
        )


def test_parse_expectation_rejects_boolean_ids_and_unapproved_digest(tmp_path):
    base = {
        "repository": REPOSITORY,
        "repository_id": str(REPOSITORY_ID),
        "run_id": str(RUN_ID),
        "run_attempt": str(RUN_ATTEMPT),
        "head_sha": COMMIT,
        "workflow_id": str(WORKFLOW_ID),
        "workflow_path": WORKFLOW_PATH,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "artifact_name": ARTIFACT_NAME,
        "artifact_digest": ARTIFACT_DIGEST,
        "destination": tmp_path / "artifact",
    }
    boolean = argparse.Namespace(**{**base, "workflow_id": True})
    uppercase = argparse.Namespace(**{**base, "artifact_digest": "B" * 64})

    with pytest.raises(provenance.ProvenanceError, match="workflow id"):
        provenance.parse_expectation(boolean)
    with pytest.raises(provenance.ProvenanceError, match="expected artifact digest"):
        provenance.parse_expectation(uppercase)


def test_parse_expectation_rejects_a_fork_repository(tmp_path):
    args = argparse.Namespace(
        repository="attacker/opswitness",
        repository_id=str(REPOSITORY_ID),
        run_id=str(RUN_ID),
        run_attempt=str(RUN_ATTEMPT),
        head_sha=COMMIT,
        workflow_id=str(WORKFLOW_ID),
        workflow_path=WORKFLOW_PATH,
        event="workflow_dispatch",
        head_branch="main",
        artifact_name=ARTIFACT_NAME,
        artifact_digest=ARTIFACT_DIGEST,
        destination=tmp_path / "artifact",
    )

    with pytest.raises(provenance.ProvenanceError, match="trusted opswitness/opswitness"):
        provenance.parse_expectation(args)


def test_github_api_uses_attempt_specific_run_and_fixed_workflow_id(monkeypatch):
    api = object.__new__(provenance.GitHubApi)
    requests = []

    def fake_get_json(path, *, query=None):
        requests.append((path, query))
        return {}

    monkeypatch.setattr(api, "get_json", fake_get_json)

    api.get_workflow(REPOSITORY, WORKFLOW_ID)
    api.get_run_attempt(REPOSITORY, RUN_ID, RUN_ATTEMPT)
    api.list_run_artifacts(REPOSITORY, RUN_ID, ARTIFACT_NAME)

    assert requests == [
        (
            f"/repos/{REPOSITORY}/actions/workflows/{WORKFLOW_ID}",
            None,
        ),
        (
            f"/repos/{REPOSITORY}/actions/runs/{RUN_ID}/attempts/{RUN_ATTEMPT}",
            None,
        ),
        (
            f"/repos/{REPOSITORY}/actions/runs/{RUN_ID}/artifacts",
            {"name": ARTIFACT_NAME, "per_page": 100},
        ),
    ]


def test_download_archive_recomputes_the_approved_api_digest(tmp_path, monkeypatch):
    archive_bytes = b"immutable actions artifact archive"
    artifact = provenance.VerifiedArtifact(
        artifact_id=1,
        name=ARTIFACT_NAME,
        digest=hashlib.sha256(archive_bytes).hexdigest(),
        size_in_bytes=len(archive_bytes),
        archive_download_url="https://api.github.com/repos/o/r/actions/artifacts/1/zip",
    )
    api = object()
    monkeypatch.setattr(
        provenance,
        "_authenticated_archive_response",
        lambda _api, _url: io.BytesIO(archive_bytes),
    )
    output = tmp_path / "artifact.zip"

    provenance.download_archive(api=api, artifact=artifact, archive_path=output)

    assert output.read_bytes() == archive_bytes


def test_download_archive_fails_closed_on_digest_mismatch(tmp_path, monkeypatch):
    artifact = provenance.VerifiedArtifact(
        artifact_id=1,
        name=ARTIFACT_NAME,
        digest="0" * 64,
        size_in_bytes=3,
        archive_download_url="https://api.github.com/repos/o/r/actions/artifacts/1/zip",
    )
    monkeypatch.setattr(
        provenance,
        "_authenticated_archive_response",
        lambda _api, _url: io.BytesIO(b"zip"),
    )

    with pytest.raises(provenance.ProvenanceError, match="API SHA-256"):
        provenance.download_archive(
            api=object(),
            artifact=artifact,
            archive_path=tmp_path / "artifact.zip",
        )


def test_extract_archive_rejects_traversal_and_symlinks(tmp_path):
    traversal = tmp_path / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr("../escape", b"no")
    with pytest.raises(provenance.ProvenanceError, match="path traversal"):
        provenance.extract_archive(traversal, tmp_path / "traversal")

    symlink = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(symlink, "w") as archive:
        archive.writestr(info, "target")
    with pytest.raises(provenance.ProvenanceError, match="link or special"):
        provenance.extract_archive(symlink, tmp_path / "symlink")


def test_extract_archive_writes_only_regular_members(tmp_path):
    source = tmp_path / "artifact.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("alpha-canary-observation.json", b"{}")
        archive.writestr("sources/soak-status.json", b"{}")

    destination = tmp_path / "artifact"
    provenance.extract_archive(source, destination)

    assert (destination / "alpha-canary-observation.json").read_bytes() == b"{}"
    assert (destination / "sources" / "soak-status.json").read_bytes() == b"{}"
