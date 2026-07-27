#!/usr/bin/env python3
"""Download an Actions artifact only from an exact trusted workflow run."""

from __future__ import annotations

import argparse
import hashlib
from http.client import HTTPMessage
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import IO, Any, BinaryIO, Mapping, Sequence


API_VERSION = "2026-03-10"
EXPECTED_REPOSITORY = "opswitness/opswitness"
MAX_ARCHIVE_ENTRIES = 200_000
MAX_UNCOMPRESSED_BYTES = 25 * 1024 * 1024 * 1024
REPOSITORY_RE = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})/"
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})"
)
WORKFLOW_PATH_RE = re.compile(r"\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml")
ARTIFACT_NAME_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,254})")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")


class ProvenanceError(RuntimeError):
    """Raised when producer identity or artifact integrity is not exact."""


@dataclass(frozen=True)
class ProducerExpectation:
    repository: str
    repository_id: int
    run_id: int
    run_attempt: int
    head_sha: str
    workflow_id: int
    workflow_path: str
    event: str
    head_branch: str
    artifact_name: str
    artifact_digest: str


@dataclass(frozen=True)
class VerifiedArtifact:
    artifact_id: int
    name: str
    digest: str
    size_in_bytes: int
    archive_download_url: str


def _positive_integer(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ProvenanceError(f"{label} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ProvenanceError(f"{label} must be a positive integer") from exc
    if parsed <= 0 or str(parsed) != str(value):
        raise ProvenanceError(f"{label} must be a positive integer")
    return parsed


def _required_string(payload: Mapping[str, Any], key: str, *, label: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ProvenanceError(f"{label} {key} must be a non-empty string")
    return value


def _required_mapping(
    payload: Mapping[str, Any], key: str, *, label: str
) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ProvenanceError(f"{label} {key} must be an object")
    return value


def parse_expectation(args: argparse.Namespace) -> ProducerExpectation:
    if not REPOSITORY_RE.fullmatch(args.repository):
        raise ProvenanceError("repository must be an exact owner/name identifier")
    if args.repository != EXPECTED_REPOSITORY:
        raise ProvenanceError(
            f"repository must be the trusted {EXPECTED_REPOSITORY} repository"
        )
    repository_id = _positive_integer(args.repository_id, label="repository id")
    run_id = _positive_integer(args.run_id, label="run id")
    run_attempt = _positive_integer(args.run_attempt, label="run attempt")
    if not COMMIT_RE.fullmatch(args.head_sha):
        raise ProvenanceError("head SHA must be exactly 40 lowercase hex characters")
    if not WORKFLOW_PATH_RE.fullmatch(args.workflow_path):
        raise ProvenanceError("workflow path must be an exact .github/workflows YAML path")
    workflow_id = _positive_integer(args.workflow_id, label="workflow id")
    if args.event not in {"workflow_dispatch", "push"}:
        raise ProvenanceError("producer event must be workflow_dispatch or push")
    if args.head_branch != "main":
        raise ProvenanceError("producer branch must be main")
    if not ARTIFACT_NAME_RE.fullmatch(args.artifact_name):
        raise ProvenanceError("artifact name contains unsafe characters")
    if not SHA256_RE.fullmatch(args.artifact_digest):
        raise ProvenanceError(
            "expected artifact digest must be exactly 64 lowercase hex characters"
        )
    return ProducerExpectation(
        repository=args.repository,
        repository_id=repository_id,
        run_id=run_id,
        run_attempt=run_attempt,
        head_sha=args.head_sha,
        workflow_id=workflow_id,
        workflow_path=args.workflow_path,
        event=args.event,
        head_branch=args.head_branch,
        artifact_name=args.artifact_name,
        artifact_digest=args.artifact_digest,
    )


def verify_producer(
    *,
    expectation: ProducerExpectation,
    workflow: object,
    run: object,
    artifact_listing: object,
) -> VerifiedArtifact:
    if not isinstance(workflow, Mapping):
        raise ProvenanceError("workflow API response must be an object")
    workflow_id = _positive_integer(workflow.get("id"), label="workflow id")
    if workflow_id != expectation.workflow_id:
        raise ProvenanceError("workflow API ID does not match the trusted producer")
    if workflow.get("path") != expectation.workflow_path:
        raise ProvenanceError("workflow API path does not match the trusted producer")
    if workflow.get("state") != "active":
        raise ProvenanceError("trusted producer workflow is not active")

    if not isinstance(run, Mapping):
        raise ProvenanceError("workflow run API response must be an object")
    if _positive_integer(run.get("id"), label="workflow run id") != expectation.run_id:
        raise ProvenanceError("workflow run id does not match")
    if (
        _positive_integer(run.get("workflow_id"), label="run workflow id")
        != workflow_id
    ):
        raise ProvenanceError("workflow run was produced by a different workflow ID")
    run_path = run.get("path")
    if not isinstance(run_path, str) or run_path.split("@", 1)[0] != expectation.workflow_path:
        raise ProvenanceError("workflow run path does not match the trusted producer")
    if (
        _positive_integer(run.get("run_attempt"), label="workflow run attempt")
        != expectation.run_attempt
    ):
        raise ProvenanceError("workflow run attempt does not match")
    if run.get("head_sha") != expectation.head_sha:
        raise ProvenanceError("workflow run head SHA does not match")
    if run.get("head_branch") != expectation.head_branch:
        raise ProvenanceError("workflow run branch does not match")
    if run.get("event") != expectation.event:
        raise ProvenanceError("workflow run event does not match")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        raise ProvenanceError("workflow run must be completed successfully")

    repository = _required_mapping(run, "repository", label="workflow run")
    head_repository = _required_mapping(run, "head_repository", label="workflow run")
    repository_id = _positive_integer(repository.get("id"), label="repository id")
    head_repository_id = _positive_integer(
        head_repository.get("id"), label="head repository id"
    )
    if (
        repository.get("full_name") != expectation.repository
        or repository_id != expectation.repository_id
    ):
        raise ProvenanceError("workflow run repository does not match")
    if (
        head_repository.get("full_name") != expectation.repository
        or head_repository_id != expectation.repository_id
    ):
        raise ProvenanceError("workflow run originated from a fork or other repository")

    if not isinstance(artifact_listing, Mapping):
        raise ProvenanceError("artifact API response must be an object")
    artifacts = artifact_listing.get("artifacts")
    if (
        artifact_listing.get("total_count") != 1
        or not isinstance(artifacts, list)
        or len(artifacts) != 1
    ):
        raise ProvenanceError("expected exactly one artifact with the trusted name")
    artifact = artifacts[0]
    if not isinstance(artifact, Mapping):
        raise ProvenanceError("artifact API item must be an object")
    artifact_id = _positive_integer(artifact.get("id"), label="artifact id")
    if artifact.get("name") != expectation.artifact_name:
        raise ProvenanceError("artifact name does not match")
    if artifact.get("expired") is not False:
        raise ProvenanceError("artifact is expired or has no explicit expiry state")
    size_in_bytes = _positive_integer(
        artifact.get("size_in_bytes"), label="artifact size"
    )
    digest = _required_string(artifact, "digest", label="artifact")
    if not digest.startswith("sha256:") or not SHA256_RE.fullmatch(digest[7:]):
        raise ProvenanceError("artifact API digest must be a SHA-256 digest")
    if digest[7:] != expectation.artifact_digest:
        raise ProvenanceError("artifact API digest does not match the approved digest")

    artifact_run = _required_mapping(artifact, "workflow_run", label="artifact")
    if _positive_integer(artifact_run.get("id"), label="artifact run id") != expectation.run_id:
        raise ProvenanceError("artifact workflow run id does not match")
    if artifact_run.get("head_sha") != expectation.head_sha:
        raise ProvenanceError("artifact workflow run head SHA does not match")
    if (
        _positive_integer(
            artifact_run.get("repository_id"), label="artifact repository id"
        )
        != expectation.repository_id
        or _positive_integer(
            artifact_run.get("head_repository_id"),
            label="artifact head repository id",
        )
        != expectation.repository_id
    ):
        raise ProvenanceError("artifact originated from a different repository")

    archive_download_url = _required_string(
        artifact, "archive_download_url", label="artifact"
    )
    return VerifiedArtifact(
        artifact_id=artifact_id,
        name=expectation.artifact_name,
        digest=digest[7:],
        size_in_bytes=size_in_bytes,
        archive_download_url=archive_download_url,
    )


class GitHubApi:
    def __init__(self, *, base_url: str, token: str) -> None:
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
            raise ProvenanceError("GitHub API URL must be an absolute HTTPS origin")
        if not token:
            raise ProvenanceError("GITHUB_TOKEN is required")
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _request(self, url: str) -> urllib.request.Request:
        return urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "User-Agent": "opswitness-release-provenance",
                "X-GitHub-Api-Version": API_VERSION,
            },
        )

    def get_json(self, path: str, *, query: Mapping[str, object] | None = None) -> object:
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        try:
            with urllib.request.urlopen(self._request(url), timeout=30) as response:
                return json.load(response)
        except (OSError, ValueError, urllib.error.HTTPError) as exc:
            raise ProvenanceError(f"GitHub API request failed for {path}") from exc

    def get_workflow(self, repository: str, workflow_id: int) -> object:
        return self.get_json(
            f"/repos/{repository}/actions/workflows/{workflow_id}"
        )

    def get_run_attempt(self, repository: str, run_id: int, run_attempt: int) -> object:
        return self.get_json(
            f"/repos/{repository}/actions/runs/{run_id}/attempts/{run_attempt}"
        )

    def list_run_artifacts(
        self, repository: str, run_id: int, artifact_name: str
    ) -> object:
        return self.get_json(
            f"/repos/{repository}/actions/runs/{run_id}/artifacts",
            query={"name": artifact_name, "per_page": 100},
        )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        return None


def _authenticated_archive_response(
    api: GitHubApi, archive_url: str
) -> BinaryIO | str:
    expected_origin = urllib.parse.urlsplit(api.base_url)
    parsed = urllib.parse.urlsplit(archive_url)
    if (
        parsed.scheme != expected_origin.scheme
        or parsed.netloc != expected_origin.netloc
        or not parsed.path.startswith("/repos/")
        or not parsed.path.endswith("/zip")
        or parsed.query
        or parsed.fragment
    ):
        raise ProvenanceError("artifact archive URL is outside the GitHub API origin")
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        response = opener.open(api._request(archive_url), timeout=30)
    except urllib.error.HTTPError as exc:
        if exc.code not in {301, 302, 303, 307, 308}:
            raise ProvenanceError("artifact archive request failed") from exc
        location = exc.headers.get("Location")
        if not location:
            raise ProvenanceError("artifact archive redirect has no location") from exc
        redirect = urllib.parse.urlsplit(location)
        if redirect.scheme != "https" or not redirect.netloc:
            raise ProvenanceError("artifact archive redirect is not HTTPS") from exc
        return location
    except OSError as exc:
        raise ProvenanceError("artifact archive request failed") from exc
    if getattr(response, "status", None) != 200:
        response.close()
        raise ProvenanceError("artifact archive request returned an unexpected status")
    return response


def _copy_and_hash(response: BinaryIO, output: BinaryIO) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while True:
        chunk = response.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
        size += len(chunk)
        output.write(chunk)
    return digest.hexdigest(), size


def download_archive(
    *,
    api: GitHubApi,
    artifact: VerifiedArtifact,
    archive_path: Path,
) -> None:
    first = _authenticated_archive_response(api, artifact.archive_download_url)
    try:
        if isinstance(first, str):
            try:
                response = urllib.request.urlopen(
                    urllib.request.Request(
                        first,
                        headers={"User-Agent": "opswitness-release-provenance"},
                    ),
                    timeout=120,
                )
            except (OSError, urllib.error.HTTPError) as exc:
                raise ProvenanceError("artifact archive download failed") from exc
        else:
            response = first
        try:
            with archive_path.open("wb") as output:
                actual_digest, actual_size = _copy_and_hash(response, output)
        finally:
            response.close()
    finally:
        if not isinstance(first, str):
            first.close()

    if actual_digest != artifact.digest:
        raise ProvenanceError("downloaded artifact does not match the API SHA-256 digest")
    if actual_size != artifact.size_in_bytes:
        raise ProvenanceError("downloaded artifact does not match the API size")


def _safe_archive_member(
    info: zipfile.ZipInfo,
    *,
    seen: set[str],
) -> PurePosixPath:
    name = info.filename
    if not name or "\x00" in name or "\\" in name or name.startswith("/"):
        raise ProvenanceError("artifact archive contains an unsafe path")
    relative = PurePosixPath(name.rstrip("/"))
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ProvenanceError("artifact archive contains path traversal")
    normalized = "/".join(
        unicodedata.normalize("NFC", part).casefold() for part in relative.parts
    )
    if normalized in seen:
        raise ProvenanceError("artifact archive contains a duplicate or colliding path")
    seen.add(normalized)
    if info.flag_bits & 0x1:
        raise ProvenanceError("artifact archive contains an encrypted member")
    mode = info.external_attr >> 16
    kind = stat.S_IFMT(mode)
    if kind not in {0, stat.S_IFREG, stat.S_IFDIR}:
        raise ProvenanceError("artifact archive contains a link or special file")
    return relative


def extract_archive(archive_path: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise ProvenanceError("artifact destination must not already exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=".opswitness-artifact-", dir=destination.parent)
    )
    try:
        seen: set[str] = set()
        total_size = 0
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            if not members or len(members) > MAX_ARCHIVE_ENTRIES:
                raise ProvenanceError("artifact archive has an invalid entry count")
            for info in members:
                relative = _safe_archive_member(info, seen=seen)
                total_size += info.file_size
                if total_size > MAX_UNCOMPRESSED_BYTES:
                    raise ProvenanceError("artifact archive exceeds the extraction limit")
                target = temporary.joinpath(*relative.parts)
                if info.is_dir() or info.filename.endswith("/"):
                    target.mkdir(parents=True, exist_ok=False)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                target.chmod(0o600)
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def download_verified_artifact(
    *,
    api: GitHubApi,
    expectation: ProducerExpectation,
    destination: Path,
) -> VerifiedArtifact:
    workflow = api.get_workflow(expectation.repository, expectation.workflow_id)
    run = api.get_run_attempt(
        expectation.repository,
        expectation.run_id,
        expectation.run_attempt,
    )
    artifact_listing = api.list_run_artifacts(
        expectation.repository,
        expectation.run_id,
        expectation.artifact_name,
    )
    artifact = verify_producer(
        expectation=expectation,
        workflow=workflow,
        run=run,
        artifact_listing=artifact_listing,
    )
    destination_parent = destination.parent.resolve()
    destination_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=".opswitness-artifact-",
        suffix=".zip",
        dir=destination_parent,
        delete=False,
    ) as temporary:
        archive_path = Path(temporary.name)
    try:
        download_archive(api=api, artifact=artifact, archive_path=archive_path)
        extract_archive(archive_path, destination)
    finally:
        archive_path.unlink(missing_ok=True)
    return artifact


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a fixed GitHub Actions producer and download its exact "
            "API-digest-bound artifact."
        )
    )
    parser.add_argument("--repository", required=True)
    parser.add_argument("--repository-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--workflow-path", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--head-branch", default="main")
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--artifact-digest", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        expectation = parse_expectation(args)
        api = GitHubApi(
            base_url=os.environ.get("GITHUB_API_URL", "https://api.github.com"),
            token=os.environ.get("GITHUB_TOKEN", ""),
        )
        artifact = download_verified_artifact(
            api=api,
            expectation=expectation,
            destination=args.destination,
        )
    except ProvenanceError as exc:
        print(f"GitHub Actions provenance verification failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "artifact_digest": f"sha256:{artifact.digest}",
                "artifact_id": artifact.artifact_id,
                "artifact_name": artifact.name,
                "head_sha": expectation.head_sha,
                "repository": expectation.repository,
                "repository_id": expectation.repository_id,
                "run_attempt": expectation.run_attempt,
                "run_id": expectation.run_id,
                "workflow_id": expectation.workflow_id,
                "workflow_path": expectation.workflow_path,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
