import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts import release_candidate as candidate


COMMIT = "a" * 40
TAG = "v0.1.0-alpha.1"
RUN_ID = 123456
RUN_ATTEMPT = 2
CANARY_RUN_ID = 987654
CANARY_RUN_ATTEMPT = 1
OBSERVATION_RUN_ID = 456789
OBSERVATION_RUN_ATTEMPT = 3
DMG_NAME = "OpsWitness-0.1.0-alpha.1-macos-arm64.dmg"
HOST_IDENTITY_SHA256 = "c" * 64


def _sha256(path: Path) -> str:
    return candidate.sha256(path)


def _macos_evidence() -> dict[str, object]:
    return {
        "architecture": "arm64",
        "minimum_macos": "14.0",
        "bundle_id": "com.opswitness.app",
        "signing": {
            "mode": "developer-id",
            "identity": "Developer ID Application: OpsWitness (TEAMID)",
            "cdhash": "b" * 40,
            "hardened_runtime": True,
            "nested_code_verified": True,
            "app_sandbox": False,
        },
        "notarization": {
            "status": "Accepted",
            "request_id": "notary-request-id",
            "stapled": True,
            "gatekeeper_assessment": "accepted",
        },
    }


def _candidate_dist(
    tmp_path: Path,
    *,
    release_ready: bool = True,
) -> tuple[Path, dict[str, object]]:
    dist = tmp_path / "candidate"
    dist.mkdir()
    contents = {
        "opswitness-0.1.0a1-py3-none-any.whl": b"wheel",
        "opswitness-0.1.0a1.tar.gz": b"sdist",
        DMG_NAME: b"signed and notarized dmg",
    }
    kinds = {
        "opswitness-0.1.0a1-py3-none-any.whl": "wheel",
        "opswitness-0.1.0a1.tar.gz": "sdist",
        DMG_NAME: "macos_dmg",
    }
    for name, body in contents.items():
        (dist / name).write_bytes(body)
    artifacts = [
        {
            "name": name,
            "kind": kinds[name],
            "sha256": _sha256(dist / name),
            "size": (dist / name).stat().st_size,
        }
        for name in sorted(contents)
    ]
    (dist / "SHA256SUMS").write_text(
        "".join(f"{item['sha256']}  {item['name']}\n" for item in artifacts),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 3,
        "product": "OpsWitness",
        "distribution": "opswitness",
        "python_version": "0.1.0a1",
        "public_version": "0.1.0-alpha.1",
        "tag": TAG,
        "git_commit": COMMIT,
        "clean_tree": True,
        "builder_python": "3.12.10",
        "created_at": "2026-07-19T00:00:00+00:00",
        "candidate": {
            "workflow_run_id": RUN_ID,
            "workflow_run_attempt": RUN_ATTEMPT,
        },
        "artifacts": artifacts,
        "platforms": {"macos": _macos_evidence()},
        "vendor_runtime_lock": {
            "schema_version": 1,
            "sha256": "c" * 64,
            "runtime_count": 5,
        },
        "release_ready": release_ready,
    }
    manifest_path = dist / "build-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    expected = {
        "expected_workflow_run_id": RUN_ID,
        "expected_workflow_run_attempt": RUN_ATTEMPT,
        "expected_commit": COMMIT,
        "expected_tag": TAG,
        "expected_dmg_sha256": _sha256(dist / DMG_NAME),
        "expected_manifest_sha256": _sha256(manifest_path),
    }
    return dist, expected


def _verify(dist: Path, expected: dict[str, object]) -> candidate.CandidateBinding:
    return candidate.verify_candidate(dist=dist, **expected)


def _observation_payload(
    binding: candidate.CandidateBinding,
    *,
    started_at: str = "2026-07-20T19:00:00Z",
    completed_at: str = "2026-07-21T19:00:00Z",
) -> dict[str, object]:
    checks = {
        "soak": {
            "authority": "opswitness-soak-status",
            "format": "json",
            "source_file": candidate.EXPECTED_SOURCE_FILES["soak"],
            "source_sha256": "0" * 64,
            "captured_at": completed_at,
            "status": "passed",
            "details": {
                "contract_id": "alpha-dmg-canary",
                "state": "passed",
                "minimum_duration_seconds": 24 * 60 * 60,
                "maximum_duration_seconds": 48 * 60 * 60,
                "observed_duration_seconds": 24 * 60 * 60,
                "continuous": True,
                "blocker_codes": [],
                "ledger_tail_sha256": "2" * 64,
            },
        },
        "cadence": {
            "authority": "opswitness-soak-ledger",
            "format": "json",
            "source_file": candidate.EXPECTED_SOURCE_FILES["cadence"],
            "source_sha256": "0" * 64,
            "captured_at": completed_at,
            "status": "passed",
            "details": {
                "expected_interval_seconds": 60 * 60,
                "grace_seconds": 5 * 60,
                "successful_runs": 25,
                "failed_runs": 0,
                "first_success_at": started_at,
                "last_success_at": completed_at,
                "max_gap_seconds": 60 * 60,
                "event_stream_sha256": "4" * 64,
            },
        },
        "recovery": {
            "authority": "opswitness-desktop-recovery-smoke",
            "format": "log_summary",
            "source_file": candidate.EXPECTED_SOURCE_FILES["recovery"],
            "source_sha256": "0" * 64,
            "captured_at": completed_at,
            "status": "passed",
            "details": {
                "scenario": "active-work-crash-restart-reconcile",
                "original_run_id": "first-work-run-1",
                "recovered_run_id": "first-work-run-1",
                "instance_id": "desktop-instance-1",
                "duplicate_dispatch_count": 0,
                "unknown_process_stop_count": 0,
                "ledger_reconciled": True,
                "artifact_reverified": True,
                "recovery_event_sha256": "6" * 64,
            },
        },
        "clean_install": {
            "authority": "opswitness-mounted-dmg-smoke",
            "format": "json",
            "source_file": candidate.EXPECTED_SOURCE_FILES["clean_install"],
            "source_sha256": "0" * 64,
            "captured_at": completed_at,
            "status": "passed",
            "details": {
                "os_version": "14.7.1",
                "architecture": "arm64",
                "dmg_sha256": binding.dmg_sha256,
                "manifest_sha256": binding.manifest_sha256,
                "clean_home": True,
                "preinstalled_runtimes": [],
                "gatekeeper_assessment": "accepted",
                "notary_ticket_verified": True,
                "loopback_only": True,
                "runtime_chain": [
                    "embedded-postgres",
                    "paperclip",
                    "aioncore",
                    "opswitness-backend",
                ],
            },
        },
        "first_work": {
            "authority": "opswitness-first-work-evidence",
            "format": "json",
            "source_file": candidate.EXPECTED_SOURCE_FILES["first_work"],
            "source_sha256": "0" * 64,
            "captured_at": completed_at,
            "status": "passed",
            "details": {
                "work_id": "my-first-evidence-work",
                "run_id": "first-work-run-1",
                "dmg_sha256": binding.dmg_sha256,
                "manifest_sha256": binding.manifest_sha256,
                "codex_login_completed": True,
                "workspace_was_blank": True,
                "user_files_read": False,
                "external_side_effects": False,
                "explicit_write_approvals": 2,
                "first_work_artifact_sha256": "9" * 64,
                "verification_artifact_sha256": "a" * 64,
                "verified_artifact_sha256": "9" * 64,
                "cas_reverified": True,
                "artifact_digest_match": True,
                "business_result_claimed": False,
                "ledger_tail_sha256": "b" * 64,
            },
        },
    }
    return {
        "schema_version": candidate.CANARY_OBSERVATION_SCHEMA_VERSION,
        "evidence_type": candidate.CANARY_OBSERVATION_TYPE,
        "candidate": binding.as_dict(),
        "run": {
            "id": "alpha-dmg-canary-20260720",
            "producer_workflow_run_id": OBSERVATION_RUN_ID,
            "producer_workflow_run_attempt": OBSERVATION_RUN_ATTEMPT,
            "started_at": started_at,
            "completed_at": completed_at,
            "host_identity_sha256": "c" * 64,
        },
        "checks": checks,
    }


def _source_document(
    *,
    binding: candidate.CandidateBinding,
    observation: dict[str, object],
    name: str,
) -> dict[str, object]:
    check = observation["checks"][name]
    run = observation["run"]
    if name == "soak":
        soak = check["details"]
        cadence = observation["checks"]["cadence"]["details"]
        evidence = {
            "ledger_tail_sha256": soak["ledger_tail_sha256"],
            "status": {
                "schema_version": 1,
                "name": soak["contract_id"],
                "state": "passed",
                "healthy": True,
                "contract_event_id": "01KALPHACANARYCONTRACT",
                "contract_kind": "soak_started",
                "evidence_since": run["started_at"],
                "checked_at": run["completed_at"],
                "minimum_seconds": soak["minimum_duration_seconds"],
                "elapsed_seconds": soak["observed_duration_seconds"],
                "remaining_seconds": 0,
                "anchor_run_id": None,
                "projection_backlog": 0,
                "jobs": {
                    "com.opswitness.alpha-canary": {
                        "starts": cadence["successful_runs"],
                        "successes": cadence["successful_runs"],
                        "failures": 0,
                        "running": 0,
                        "last_started": cadence["last_success_at"],
                        "max_gap_seconds": cadence["max_gap_seconds"],
                        "allowed_gap_seconds": (
                            cadence["expected_interval_seconds"]
                            + cadence["grace_seconds"]
                        ),
                    }
                },
                "blockers": [],
            },
        }
    elif name == "cadence":
        evidence = {
            "contract_id": observation["checks"]["soak"]["details"]["contract_id"],
            "ledger_tail_sha256": observation["checks"]["soak"]["details"][
                "ledger_tail_sha256"
            ],
            "details": check["details"],
        }
    else:
        evidence = {"details": check["details"]}
    return {
        "schema_version": candidate.SOURCE_SCHEMA_VERSION,
        "evidence_type": candidate.EXPECTED_SOURCE_TYPES[name],
        "candidate": binding.as_dict(),
        "observation_run_id": run["id"],
        "captured_at": check["captured_at"],
        "authority": check["authority"],
        "evidence": evidence,
    }


def _write_observation(
    tmp_path: Path,
    *,
    binding: candidate.CandidateBinding,
    payload: dict[str, object] | None = None,
) -> Path:
    observation_payload = payload or _observation_payload(binding)
    bundle = tmp_path / "observation-bundle"
    sources = bundle / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    for name, relative in candidate.EXPECTED_SOURCE_FILES.items():
        source_path = bundle / relative
        source_path.write_bytes(
            candidate.canonical_json_bytes(
                _source_document(
                    binding=binding,
                    observation=observation_payload,
                    name=name,
                )
            )
        )
        observation_payload["checks"][name]["source_sha256"] = _sha256(source_path)
    observation_path = bundle / candidate.OBSERVATION_FILE
    observation_path.write_bytes(candidate.canonical_json_bytes(observation_payload))
    return bundle


def _record_evidence(
    tmp_path: Path,
    *,
    binding: candidate.CandidateBinding,
) -> Path:
    observation = _write_observation(tmp_path, binding=binding)
    output = tmp_path / "canary-evidence.json"
    candidate.record_canary_evidence(
        binding=binding,
        canary_workflow_run_id=CANARY_RUN_ID,
        canary_workflow_run_attempt=CANARY_RUN_ATTEMPT,
        observation_bundle=observation,
        expected_observation_sha256=_sha256(
            observation / candidate.OBSERVATION_FILE
        ),
        expected_observation_workflow_run_id=OBSERVATION_RUN_ID,
        expected_observation_workflow_run_attempt=OBSERVATION_RUN_ATTEMPT,
        expected_host_identity_sha256=HOST_IDENTITY_SHA256,
        output=output,
    )
    return output


def test_verify_candidate_binds_closed_schema_3_dist(tmp_path):
    dist, expected = _candidate_dist(tmp_path)

    binding = _verify(dist, expected)

    assert binding.as_dict() == {
        "workflow_run_id": RUN_ID,
        "workflow_run_attempt": RUN_ATTEMPT,
        "git_commit": COMMIT,
        "tag": TAG,
        "dmg_sha256": expected["expected_dmg_sha256"],
        "manifest_sha256": expected["expected_manifest_sha256"],
    }


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("expected_workflow_run_id", RUN_ID + 1, "workflow run id mismatch"),
        ("expected_workflow_run_attempt", RUN_ATTEMPT + 1, "run attempt mismatch"),
        ("expected_commit", "d" * 40, "commit does not match"),
        ("expected_tag", "v0.1.0-alpha.2", "tag does not match"),
        ("expected_dmg_sha256", "e" * 64, "DMG hash"),
        ("expected_manifest_sha256", "f" * 64, "manifest.json hash"),
    ],
)
def test_verify_candidate_rejects_expected_identity_mismatch(
    tmp_path,
    field,
    value,
    message,
):
    dist, expected = _candidate_dist(tmp_path)
    expected[field] = value

    with pytest.raises(candidate.CandidateError, match=message):
        _verify(dist, expected)


def test_verify_candidate_rejects_non_release_ready_manifest(tmp_path):
    dist, expected = _candidate_dist(tmp_path, release_ready=False)

    with pytest.raises(candidate.CandidateError, match="not release_ready"):
        _verify(dist, expected)


def test_verify_candidate_rejects_future_created_at(tmp_path):
    dist, expected = _candidate_dist(tmp_path)
    manifest_path = dist / "build-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["created_at"] = "2999-01-01T00:00:00Z"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    expected["expected_manifest_sha256"] = _sha256(manifest_path)

    with pytest.raises(candidate.CandidateError, match="created_at cannot be in the future"):
        _verify(dist, expected)


@pytest.mark.parametrize("mutation", ["missing", "unexpected", "tampered"])
def test_verify_candidate_rejects_non_closed_or_tampered_dist(tmp_path, mutation):
    dist, expected = _candidate_dist(tmp_path)
    wheel = dist / "opswitness-0.1.0a1-py3-none-any.whl"
    if mutation == "missing":
        wheel.unlink()
    elif mutation == "unexpected":
        (dist / "unreviewed.txt").write_text("unexpected\n", encoding="utf-8")
    else:
        wheel.write_bytes(b"WHEEL")

    with pytest.raises(candidate.CandidateError, match="missing|unexpected|mismatch"):
        _verify(dist, expected)


def test_verify_candidate_rejects_checksum_manifest_disagreement(tmp_path):
    dist, expected = _candidate_dist(tmp_path)
    sums = dist / "SHA256SUMS"
    sums.write_text(
        sums.read_text(encoding="utf-8").replace("any.whl\n", "any.invalid\n"),
        encoding="utf-8",
    )

    with pytest.raises(candidate.CandidateError, match="SHA256SUMS does not match"):
        _verify(dist, expected)


def test_record_canary_writes_canonical_exact_candidate_evidence(tmp_path):
    dist, expected = _candidate_dist(tmp_path)
    binding = _verify(dist, expected)
    output = _record_evidence(tmp_path, binding=binding)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert output.read_bytes() == candidate.canonical_json_bytes(payload)
    assert payload["candidate"] == binding.as_dict()
    assert payload["canary"] == {
        "workflow_run_id": CANARY_RUN_ID,
        "workflow_run_attempt": CANARY_RUN_ATTEMPT,
        "observation_workflow_run_id": OBSERVATION_RUN_ID,
        "observation_workflow_run_attempt": OBSERVATION_RUN_ATTEMPT,
        "observation_sha256": _sha256(
            tmp_path / "observation-bundle" / candidate.OBSERVATION_FILE
        ),
        "run_id": "alpha-dmg-canary-20260720",
        "host_identity_sha256": "c" * 64,
        "started_at": "2026-07-20T19:00:00Z",
        "completed_at": "2026-07-21T19:00:00Z",
        "duration_seconds": 24 * 60 * 60,
    }
    assert set(payload["checks"]) == {
        "soak",
        "cadence",
        "recovery",
        "clean_install",
        "first_work",
    }
    assert payload["checks"]["soak"]["details"]["continuous"] is True
    assert payload["checks"]["recovery"]["details"]["duplicate_dispatch_count"] == 0
    assert payload["checks"]["first_work"]["details"]["cas_reverified"] is True
    assert set(payload["sources"]) == set(candidate.EXPECTED_SOURCE_FILES)
    for name, source in payload["sources"].items():
        assert (
            candidate.sha256_bytes(candidate.canonical_json_bytes(source))
            == payload["checks"][name]["source_sha256"]
        )


@pytest.mark.parametrize(
    ("started_at", "completed_at", "failed_check", "message"),
    [
        (
            "2026-07-20T00:00:00",
            "2026-07-21T00:00:00Z",
            None,
            "timezone offset",
        ),
        (
            "2026-07-20T00:00:00Z",
            "2026-07-20T23:59:59Z",
            None,
            "between 24 and 48",
        ),
        (
            "2026-07-20T00:00:00Z",
            "2026-07-22T00:00:01Z",
            None,
            "between 24 and 48",
        ),
        (
            "2026-07-20T00:00:00Z",
            "2026-07-21T00:00:00Z",
            "recovery",
            "explicitly pass: recovery",
        ),
    ],
)
def test_record_canary_rejects_invalid_window_or_failed_check(
    tmp_path,
    started_at,
    completed_at,
    failed_check,
    message,
):
    dist, expected = _candidate_dist(tmp_path)
    binding = _verify(dist, expected)
    payload = _observation_payload(
        binding,
        started_at=started_at,
        completed_at=completed_at,
    )
    if failed_check is not None:
        payload["checks"][failed_check]["status"] = "failed"
    observation = _write_observation(tmp_path, binding=binding, payload=payload)

    with pytest.raises(candidate.CandidateError, match=message):
        candidate.record_canary_evidence(
            binding=binding,
            canary_workflow_run_id=CANARY_RUN_ID,
            canary_workflow_run_attempt=CANARY_RUN_ATTEMPT,
            observation_bundle=observation,
            expected_observation_sha256=_sha256(
                observation / candidate.OBSERVATION_FILE
            ),
            expected_observation_workflow_run_id=OBSERVATION_RUN_ID,
            expected_observation_workflow_run_attempt=OBSERVATION_RUN_ATTEMPT,
            expected_host_identity_sha256=HOST_IDENTITY_SHA256,
            output=tmp_path / "rejected.json",
        )


def test_record_canary_rejects_future_window(tmp_path):
    dist, expected = _candidate_dist(tmp_path)
    binding = _verify(dist, expected)
    payload = _observation_payload(
        binding,
        started_at="2999-01-01T00:00:00Z",
        completed_at="2999-01-02T00:00:00Z",
    )
    observation = _write_observation(tmp_path, binding=binding, payload=payload)

    with pytest.raises(candidate.CandidateError, match="cannot be in the future"):
        candidate.record_canary_evidence(
            binding=binding,
            canary_workflow_run_id=CANARY_RUN_ID,
            canary_workflow_run_attempt=CANARY_RUN_ATTEMPT,
            observation_bundle=observation,
            expected_observation_sha256=_sha256(
                observation / candidate.OBSERVATION_FILE
            ),
            expected_observation_workflow_run_id=OBSERVATION_RUN_ID,
            expected_observation_workflow_run_attempt=OBSERVATION_RUN_ATTEMPT,
            expected_host_identity_sha256=HOST_IDENTITY_SHA256,
            output=tmp_path / "future.json",
        )


def test_record_canary_rejects_window_before_candidate(tmp_path):
    dist, expected = _candidate_dist(tmp_path)
    binding = _verify(dist, expected)
    payload = _observation_payload(
        binding,
        started_at="2026-07-17T00:00:00Z",
        completed_at="2026-07-18T00:00:00Z",
    )
    observation = _write_observation(tmp_path, binding=binding, payload=payload)

    with pytest.raises(candidate.CandidateError, match="predates"):
        candidate.record_canary_evidence(
            binding=binding,
            canary_workflow_run_id=CANARY_RUN_ID,
            canary_workflow_run_attempt=CANARY_RUN_ATTEMPT,
            observation_bundle=observation,
            expected_observation_sha256=_sha256(
                observation / candidate.OBSERVATION_FILE
            ),
            expected_observation_workflow_run_id=OBSERVATION_RUN_ID,
            expected_observation_workflow_run_attempt=OBSERVATION_RUN_ATTEMPT,
            expected_host_identity_sha256=HOST_IDENTITY_SHA256,
            output=tmp_path / "predates.json",
        )


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (
            ("candidate", "dmg_sha256"),
            "f" * 64,
            "different candidate",
        ),
        (
            ("checks", "soak", "details", "continuous"),
            False,
            "continuous must be true",
        ),
        (
            ("checks", "soak", "details", "blocker_codes"),
            ["cadence_gap"],
            "blocker_codes must be empty",
        ),
        (
            ("checks", "cadence", "details", "failed_runs"),
            1,
            "failed_runs must be zero",
        ),
        (
            ("checks", "cadence", "details", "max_gap_seconds"),
            3901,
            "max gap exceeds",
        ),
        (
            ("checks", "recovery", "details", "recovered_run_id"),
            "duplicate-run-2",
            "original run ID",
        ),
        (
            ("checks", "recovery", "details", "duplicate_dispatch_count"),
            1,
            "duplicate_dispatch_count must be zero",
        ),
        (
            ("checks", "recovery", "details", "unknown_process_stop_count"),
            1,
            "unknown_process_stop_count must be zero",
        ),
        (
            ("checks", "clean_install", "details", "dmg_sha256"),
            "e" * 64,
            "clean install DMG hash mismatch",
        ),
        (
            ("checks", "clean_install", "details", "preinstalled_runtimes"),
            ["node"],
            "no preinstalled runtimes",
        ),
        (
            ("checks", "first_work", "details", "cas_reverified"),
            False,
            "cas_reverified must be true",
        ),
        (
            ("checks", "first_work", "details", "verified_artifact_sha256"),
            "d" * 64,
            "verifier digest does not match",
        ),
        (
            ("checks", "first_work", "details", "business_result_claimed"),
            True,
            "business_result_claimed must be false",
        ),
    ],
)
def test_record_canary_rejects_incomplete_or_inconsistent_observation_metrics(
    tmp_path,
    path,
    value,
    message,
):
    dist, expected = _candidate_dist(tmp_path)
    binding = _verify(dist, expected)
    payload = _observation_payload(binding)
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    observation = _write_observation(tmp_path, binding=binding, payload=payload)

    with pytest.raises(candidate.CandidateError, match=message):
        candidate.record_canary_evidence(
            binding=binding,
            canary_workflow_run_id=CANARY_RUN_ID,
            canary_workflow_run_attempt=CANARY_RUN_ATTEMPT,
            observation_bundle=observation,
            expected_observation_sha256=_sha256(
                observation / candidate.OBSERVATION_FILE
            ),
            expected_observation_workflow_run_id=OBSERVATION_RUN_ID,
            expected_observation_workflow_run_attempt=OBSERVATION_RUN_ATTEMPT,
            expected_host_identity_sha256=HOST_IDENTITY_SHA256,
            output=tmp_path / "rejected-metrics.json",
        )


@pytest.mark.parametrize(
    ("observation_sha256", "observation_run_id", "observation_run_attempt", "message"),
    [
        ("f" * 64, OBSERVATION_RUN_ID, OBSERVATION_RUN_ATTEMPT, "hash mismatch"),
        (
            None,
            OBSERVATION_RUN_ID + 1,
            OBSERVATION_RUN_ATTEMPT,
            "workflow run id mismatch",
        ),
        (
            None,
            OBSERVATION_RUN_ID,
            OBSERVATION_RUN_ATTEMPT + 1,
            "run attempt mismatch",
        ),
    ],
)
def test_record_canary_binds_observation_artifact_identity(
    tmp_path,
    observation_sha256,
    observation_run_id,
    observation_run_attempt,
    message,
):
    dist, expected = _candidate_dist(tmp_path)
    binding = _verify(dist, expected)
    observation = _write_observation(tmp_path, binding=binding)

    with pytest.raises(candidate.CandidateError, match=message):
        candidate.record_canary_evidence(
            binding=binding,
            canary_workflow_run_id=CANARY_RUN_ID,
            canary_workflow_run_attempt=CANARY_RUN_ATTEMPT,
            observation_bundle=observation,
            expected_observation_sha256=observation_sha256
            or _sha256(observation / candidate.OBSERVATION_FILE),
            expected_observation_workflow_run_id=observation_run_id,
            expected_observation_workflow_run_attempt=observation_run_attempt,
            expected_host_identity_sha256=HOST_IDENTITY_SHA256,
            output=tmp_path / "rejected-identity.json",
        )


def test_record_canary_rejects_unapproved_host_identity(tmp_path):
    dist, expected = _candidate_dist(tmp_path)
    binding = _verify(dist, expected)
    observation = _write_observation(tmp_path, binding=binding)

    with pytest.raises(candidate.CandidateError, match="host identity mismatch"):
        candidate.record_canary_evidence(
            binding=binding,
            canary_workflow_run_id=CANARY_RUN_ID,
            canary_workflow_run_attempt=CANARY_RUN_ATTEMPT,
            observation_bundle=observation,
            expected_observation_sha256=_sha256(
                observation / candidate.OBSERVATION_FILE
            ),
            expected_observation_workflow_run_id=OBSERVATION_RUN_ID,
            expected_observation_workflow_run_attempt=OBSERVATION_RUN_ATTEMPT,
            expected_host_identity_sha256="d" * 64,
            output=tmp_path / "rejected-host.json",
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing", "missing sources/recovery-summary.json"),
        ("unexpected", "unexpected sources/operator-note.txt"),
        ("tampered", "source hash mismatch"),
    ],
)
def test_record_canary_rejects_open_or_tampered_source_bundle(
    tmp_path,
    mutation,
    message,
):
    dist, expected = _candidate_dist(tmp_path)
    binding = _verify(dist, expected)
    observation = _write_observation(tmp_path, binding=binding)
    recovery = observation / candidate.EXPECTED_SOURCE_FILES["recovery"]
    if mutation == "missing":
        recovery.unlink()
    elif mutation == "unexpected":
        (observation / "sources" / "operator-note.txt").write_text("passed\n")
    else:
        recovery.write_bytes(recovery.read_bytes() + b"\n")

    with pytest.raises(candidate.CandidateError, match=message):
        candidate.record_canary_evidence(
            binding=binding,
            canary_workflow_run_id=CANARY_RUN_ID,
            canary_workflow_run_attempt=CANARY_RUN_ATTEMPT,
            observation_bundle=observation,
            expected_observation_sha256=_sha256(
                observation / candidate.OBSERVATION_FILE
            ),
            expected_observation_workflow_run_id=OBSERVATION_RUN_ID,
            expected_observation_workflow_run_attempt=OBSERVATION_RUN_ATTEMPT,
            expected_host_identity_sha256=HOST_IDENTITY_SHA256,
            output=tmp_path / "rejected-source-bundle.json",
        )


def test_record_canary_rejects_rebound_source_summary_disagreement(tmp_path):
    dist, expected = _candidate_dist(tmp_path)
    binding = _verify(dist, expected)
    observation = _write_observation(tmp_path, binding=binding)
    recovery_path = observation / candidate.EXPECTED_SOURCE_FILES["recovery"]
    recovery = json.loads(recovery_path.read_text())
    recovery["evidence"]["details"]["instance_id"] = "different-instance"
    recovery_path.write_bytes(candidate.canonical_json_bytes(recovery))
    observation_path = observation / candidate.OBSERVATION_FILE
    payload = json.loads(observation_path.read_text())
    payload["checks"]["recovery"]["source_sha256"] = _sha256(recovery_path)
    observation_path.write_bytes(candidate.canonical_json_bytes(payload))

    with pytest.raises(candidate.CandidateError, match="source details mismatch"):
        candidate.record_canary_evidence(
            binding=binding,
            canary_workflow_run_id=CANARY_RUN_ID,
            canary_workflow_run_attempt=CANARY_RUN_ATTEMPT,
            observation_bundle=observation,
            expected_observation_sha256=_sha256(observation_path),
            expected_observation_workflow_run_id=OBSERVATION_RUN_ID,
            expected_observation_workflow_run_attempt=OBSERVATION_RUN_ATTEMPT,
            expected_host_identity_sha256=HOST_IDENTITY_SHA256,
            output=tmp_path / "rejected-source-disagreement.json",
        )


def test_record_canary_rejects_rebound_noncanonical_source(tmp_path):
    dist, expected = _candidate_dist(tmp_path)
    binding = _verify(dist, expected)
    observation = _write_observation(tmp_path, binding=binding)
    cadence_path = observation / candidate.EXPECTED_SOURCE_FILES["cadence"]
    cadence = json.loads(cadence_path.read_text())
    cadence_path.write_text(json.dumps(cadence, indent=2, sort_keys=True) + "\n")
    observation_path = observation / candidate.OBSERVATION_FILE
    payload = json.loads(observation_path.read_text())
    payload["checks"]["cadence"]["source_sha256"] = _sha256(cadence_path)
    observation_path.write_bytes(candidate.canonical_json_bytes(payload))

    with pytest.raises(candidate.CandidateError, match="source JSON is not canonical"):
        candidate.record_canary_evidence(
            binding=binding,
            canary_workflow_run_id=CANARY_RUN_ID,
            canary_workflow_run_attempt=CANARY_RUN_ATTEMPT,
            observation_bundle=observation,
            expected_observation_sha256=_sha256(observation_path),
            expected_observation_workflow_run_id=OBSERVATION_RUN_ID,
            expected_observation_workflow_run_attempt=OBSERVATION_RUN_ATTEMPT,
            expected_host_identity_sha256=HOST_IDENTITY_SHA256,
            output=tmp_path / "rejected-source-canonical.json",
        )


def test_record_canary_rejects_noncanonical_or_open_observation(tmp_path):
    dist, expected = _candidate_dist(tmp_path)
    binding = _verify(dist, expected)
    payload = _observation_payload(binding)
    payload["operator_note"] = "manual pass"
    observation = _write_observation(tmp_path, binding=binding, payload=payload)
    observation_file = observation / candidate.OBSERVATION_FILE
    observation_file.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(candidate.CandidateError, match="not canonical"):
        candidate.record_canary_evidence(
            binding=binding,
            canary_workflow_run_id=CANARY_RUN_ID,
            canary_workflow_run_attempt=CANARY_RUN_ATTEMPT,
            observation_bundle=observation,
            expected_observation_sha256=_sha256(observation_file),
            expected_observation_workflow_run_id=OBSERVATION_RUN_ID,
            expected_observation_workflow_run_attempt=OBSERVATION_RUN_ATTEMPT,
            expected_host_identity_sha256=HOST_IDENTITY_SHA256,
            output=tmp_path / "noncanonical.json",
        )

    observation_file.write_bytes(candidate.canonical_json_bytes(payload))
    with pytest.raises(candidate.CandidateError, match="unexpected operator_note"):
        candidate.record_canary_evidence(
            binding=binding,
            canary_workflow_run_id=CANARY_RUN_ID,
            canary_workflow_run_attempt=CANARY_RUN_ATTEMPT,
            observation_bundle=observation,
            expected_observation_sha256=_sha256(observation_file),
            expected_observation_workflow_run_id=OBSERVATION_RUN_ID,
            expected_observation_workflow_run_attempt=OBSERVATION_RUN_ATTEMPT,
            expected_host_identity_sha256=HOST_IDENTITY_SHA256,
            output=tmp_path / "open-schema.json",
        )


def test_verify_promotion_revalidates_exact_candidate_and_canary(tmp_path):
    dist, expected = _candidate_dist(tmp_path)
    binding = _verify(dist, expected)
    evidence = _record_evidence(tmp_path, binding=binding)

    promoted = candidate.verify_promotion(
        dist=dist,
        **expected,
        evidence_path=evidence,
        expected_canary_workflow_run_id=CANARY_RUN_ID,
        expected_canary_workflow_run_attempt=CANARY_RUN_ATTEMPT,
        expected_host_identity_sha256=HOST_IDENTITY_SHA256,
        expected_evidence_sha256=_sha256(evidence),
    )

    assert promoted == binding


@pytest.mark.parametrize(
    ("canary_run_id", "canary_run_attempt", "evidence_sha", "message"),
    [
        (CANARY_RUN_ID + 1, CANARY_RUN_ATTEMPT, None, "workflow run id mismatch"),
        (CANARY_RUN_ID, CANARY_RUN_ATTEMPT + 1, None, "run attempt mismatch"),
        (CANARY_RUN_ID, CANARY_RUN_ATTEMPT, "f" * 64, "evidence hash mismatch"),
    ],
)
def test_verify_promotion_rejects_canary_identity_or_hash_mismatch(
    tmp_path,
    canary_run_id,
    canary_run_attempt,
    evidence_sha,
    message,
):
    dist, expected = _candidate_dist(tmp_path)
    binding = _verify(dist, expected)
    evidence = _record_evidence(tmp_path, binding=binding)

    with pytest.raises(candidate.CandidateError, match=message):
        candidate.verify_promotion(
            dist=dist,
            **expected,
            evidence_path=evidence,
            expected_canary_workflow_run_id=canary_run_id,
            expected_canary_workflow_run_attempt=canary_run_attempt,
            expected_host_identity_sha256=HOST_IDENTITY_SHA256,
            expected_evidence_sha256=evidence_sha or _sha256(evidence),
        )


def test_verify_promotion_rejects_unapproved_host_identity(tmp_path):
    dist, expected = _candidate_dist(tmp_path)
    binding = _verify(dist, expected)
    evidence = _record_evidence(tmp_path, binding=binding)

    with pytest.raises(candidate.CandidateError, match="host identity mismatch"):
        candidate.verify_promotion(
            dist=dist,
            **expected,
            evidence_path=evidence,
            expected_canary_workflow_run_id=CANARY_RUN_ID,
            expected_canary_workflow_run_attempt=CANARY_RUN_ATTEMPT,
            expected_host_identity_sha256="d" * 64,
            expected_evidence_sha256=_sha256(evidence),
        )


def test_verify_promotion_rejects_rewritten_candidate_or_check(tmp_path):
    dist, expected = _candidate_dist(tmp_path)
    binding = _verify(dist, expected)
    evidence = _record_evidence(tmp_path, binding=binding)
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    payload["candidate"]["git_commit"] = "e" * 40
    evidence.write_bytes(candidate.canonical_json_bytes(payload))

    with pytest.raises(candidate.CandidateError, match="different candidate"):
        candidate.verify_promotion(
            dist=dist,
            **expected,
            evidence_path=evidence,
            expected_canary_workflow_run_id=CANARY_RUN_ID,
            expected_canary_workflow_run_attempt=CANARY_RUN_ATTEMPT,
            expected_host_identity_sha256=HOST_IDENTITY_SHA256,
            expected_evidence_sha256=_sha256(evidence),
        )

    payload["candidate"] = binding.as_dict()
    payload["checks"]["first_work"]["status"] = "failed"
    evidence.write_bytes(candidate.canonical_json_bytes(payload))
    with pytest.raises(candidate.CandidateError, match="explicitly pass: first_work"):
        candidate.verify_promotion(
            dist=dist,
            **expected,
            evidence_path=evidence,
            expected_canary_workflow_run_id=CANARY_RUN_ID,
            expected_canary_workflow_run_attempt=CANARY_RUN_ATTEMPT,
            expected_host_identity_sha256=HOST_IDENTITY_SHA256,
            expected_evidence_sha256=_sha256(evidence),
        )


def test_verify_promotion_recomputes_embedded_source_hashes(tmp_path):
    dist, expected = _candidate_dist(tmp_path)
    binding = _verify(dist, expected)
    evidence = _record_evidence(tmp_path, binding=binding)
    payload = json.loads(evidence.read_text())
    payload["sources"]["first_work"]["evidence"]["details"][
        "verification_artifact_sha256"
    ] = "f" * 64
    evidence.write_bytes(candidate.canonical_json_bytes(payload))

    with pytest.raises(candidate.CandidateError, match="source first_work hash mismatch"):
        candidate.verify_promotion(
            dist=dist,
            **expected,
            evidence_path=evidence,
            expected_canary_workflow_run_id=CANARY_RUN_ID,
            expected_canary_workflow_run_attempt=CANARY_RUN_ATTEMPT,
            expected_host_identity_sha256=HOST_IDENTITY_SHA256,
            expected_evidence_sha256=_sha256(evidence),
        )


def test_verify_promotion_rejects_boolean_run_attempt_type_confusion(tmp_path):
    dist, expected = _candidate_dist(tmp_path)
    binding = _verify(dist, expected)
    evidence = _record_evidence(tmp_path, binding=binding)
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["candidate"]["workflow_run_attempt"] == 2
    payload["canary"]["workflow_run_attempt"] = True
    evidence.write_bytes(candidate.canonical_json_bytes(payload))

    with pytest.raises(candidate.CandidateError, match="positive integer"):
        candidate.verify_promotion(
            dist=dist,
            **expected,
            evidence_path=evidence,
            expected_canary_workflow_run_id=CANARY_RUN_ID,
            expected_canary_workflow_run_attempt=CANARY_RUN_ATTEMPT,
            expected_host_identity_sha256=HOST_IDENTITY_SHA256,
            expected_evidence_sha256=_sha256(evidence),
        )


def test_verify_promotion_rejects_noncanonical_evidence(tmp_path):
    dist, expected = _candidate_dist(tmp_path)
    binding = _verify(dist, expected)
    evidence = _record_evidence(tmp_path, binding=binding)
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    evidence.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(candidate.CandidateError, match="not canonical"):
        candidate.verify_promotion(
            dist=dist,
            **expected,
            evidence_path=evidence,
            expected_canary_workflow_run_id=CANARY_RUN_ID,
            expected_canary_workflow_run_attempt=CANARY_RUN_ATTEMPT,
            expected_host_identity_sha256=HOST_IDENTITY_SHA256,
            expected_evidence_sha256=_sha256(evidence),
        )


def test_verify_promotion_rejects_future_canary_evidence(tmp_path):
    dist, expected = _candidate_dist(tmp_path)
    binding = _verify(dist, expected)
    evidence = _record_evidence(tmp_path, binding=binding)
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    payload["canary"]["started_at"] = "2999-01-01T00:00:00Z"
    payload["canary"]["completed_at"] = "2999-01-02T00:00:00Z"
    evidence.write_bytes(candidate.canonical_json_bytes(payload))

    with pytest.raises(candidate.CandidateError, match="cannot be in the future"):
        candidate.verify_promotion(
            dist=dist,
            **expected,
            evidence_path=evidence,
            expected_canary_workflow_run_id=CANARY_RUN_ID,
            expected_canary_workflow_run_attempt=CANARY_RUN_ATTEMPT,
            expected_host_identity_sha256=HOST_IDENTITY_SHA256,
            expected_evidence_sha256=_sha256(evidence),
        )


def test_cli_records_canary_from_verified_candidate(tmp_path, capsys):
    dist, expected = _candidate_dist(tmp_path)
    binding = _verify(dist, expected)
    observation = _write_observation(tmp_path, binding=binding)
    output = tmp_path / "cli-evidence.json"

    result = candidate.main(
        [
            "record-canary",
            "--dist",
            str(dist),
            "--candidate-run-id",
            str(expected["expected_workflow_run_id"]),
            "--candidate-run-attempt",
            str(expected["expected_workflow_run_attempt"]),
            "--commit",
            str(expected["expected_commit"]),
            "--tag",
            str(expected["expected_tag"]),
            "--dmg-sha256",
            str(expected["expected_dmg_sha256"]),
            "--manifest-sha256",
            str(expected["expected_manifest_sha256"]),
            "--canary-run-id",
            str(CANARY_RUN_ID),
            "--canary-run-attempt",
            str(CANARY_RUN_ATTEMPT),
            "--observation-bundle",
            str(observation),
            "--observation-sha256",
            _sha256(observation / candidate.OBSERVATION_FILE),
            "--observation-run-id",
            str(OBSERVATION_RUN_ID),
            "--observation-run-attempt",
            str(OBSERVATION_RUN_ATTEMPT),
            "--host-identity-sha256",
            HOST_IDENTITY_SHA256,
            "--output",
            str(output),
        ]
    )

    assert result == 0
    assert output.is_file()
    assert "canary evidence written" in capsys.readouterr().out


def test_canary_duration_bounds_are_inclusive(tmp_path):
    dist, expected = _candidate_dist(tmp_path)
    binding = _verify(dist, expected)
    start = datetime(2026, 7, 20, tzinfo=timezone.utc)

    for hours in (24, 48):
        started_at = start.isoformat().replace("+00:00", "Z")
        completed_at = (start + timedelta(hours=hours)).isoformat().replace(
            "+00:00",
            "Z",
        )
        payload = _observation_payload(
            binding,
            started_at=started_at,
            completed_at=completed_at,
        )
        payload["checks"]["soak"]["details"]["observed_duration_seconds"] = (
            hours * 60 * 60
        )
        payload["checks"]["cadence"]["details"]["successful_runs"] = hours + 1
        observation = _write_observation(
            tmp_path,
            binding=binding,
            payload=payload,
        )
        output = tmp_path / f"evidence-{hours}.json"
        candidate.record_canary_evidence(
            binding=binding,
            canary_workflow_run_id=CANARY_RUN_ID,
            canary_workflow_run_attempt=CANARY_RUN_ATTEMPT,
            observation_bundle=observation,
            expected_observation_sha256=_sha256(
                observation / candidate.OBSERVATION_FILE
            ),
            expected_observation_workflow_run_id=OBSERVATION_RUN_ID,
            expected_observation_workflow_run_attempt=OBSERVATION_RUN_ATTEMPT,
            expected_host_identity_sha256=HOST_IDENTITY_SHA256,
            output=output,
        )
        assert output.is_file()
