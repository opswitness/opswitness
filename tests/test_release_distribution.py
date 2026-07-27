import io
import importlib.util
import json
import plistlib
import re
import subprocess
import tarfile
import tomllib
import zipfile
from pathlib import Path

import pytest
import yaml


_SPEC = importlib.util.spec_from_file_location(
    "opswitness_verify_distribution",
    Path(__file__).parents[1] / "scripts" / "verify_distribution.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_VERIFY = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_VERIFY)
DistributionError = _VERIFY.DistributionError
SDIST_REQUIRED = _VERIFY.SDIST_REQUIRED
verify_sdist = _VERIFY.verify_sdist
verify_wheel = _VERIFY.verify_wheel

_MANIFEST_SPEC = importlib.util.spec_from_file_location(
    "opswitness_build_manifest",
    Path(__file__).parents[1] / "scripts" / "build_manifest.py",
)
assert _MANIFEST_SPEC is not None and _MANIFEST_SPEC.loader is not None
_MANIFEST = importlib.util.module_from_spec(_MANIFEST_SPEC)
_MANIFEST_SPEC.loader.exec_module(_MANIFEST)


def _sdist(path: Path, files: set[str], *, non_file: str | None = None) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name in sorted(files):
            payload = b"fixture\n"
            info = tarfile.TarInfo(f"opswitness-0.1.0a1/{name}")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        if non_file is not None:
            info = tarfile.TarInfo(f"opswitness-0.1.0a1/{non_file}")
            info.type = tarfile.FIFOTYPE
            archive.addfile(info)


def test_sdist_accepts_only_tracked_release_inputs(tmp_path):
    path = tmp_path / "opswitness.tar.gz"
    _sdist(path, set(SDIST_REQUIRED))

    verify_sdist(path, tracked=set(SDIST_REQUIRED))


@pytest.mark.parametrize(
    "unexpected",
    [
        ".claude/settings.local.json",
        "src/opswitness/local_private.py",
    ],
)
def test_sdist_rejects_private_or_untracked_workspace_files(tmp_path, unexpected):
    path = tmp_path / "opswitness.tar.gz"
    _sdist(path, {*SDIST_REQUIRED, unexpected})

    with pytest.raises(DistributionError):
        verify_sdist(path, tracked=set(SDIST_REQUIRED))


def test_sdist_rejects_non_file_entries(tmp_path):
    path = tmp_path / "opswitness.tar.gz"
    _sdist(path, set(SDIST_REQUIRED), non_file="src/opswitness/control.fifo")

    with pytest.raises(DistributionError, match="non-file entry"):
        verify_sdist(path, tracked=set(SDIST_REQUIRED))


def _wheel(
    path: Path,
    *,
    entries: str | None = None,
    name: str = "opswitness",
    requires_python: str = ">=3.12,<3.13",
) -> None:
    dist_info = "opswitness-0.1.0a1.dist-info"
    metadata = (
        "Metadata-Version: 2.4\n"
        f"Name: {name}\n"
        "Version: 0.1.0a1\n"
        f"Requires-Python: {requires_python}\n\n"
    )
    scripts = entries or (
        "[console_scripts]\nopswitness = opswitness.cli:app\nqd = opswitness.cli:app\n"
    )
    files = {
        "opswitness/__init__.py": "__version__ = '0.1.0a1'\n",
        "opswitness/console/static/index.html": "fixture\n",
        "opswitness/templates/quant-fleet/launchd/com.opswitness.console.plist": "fixture\n",
        f"{dist_info}/METADATA": metadata,
        f"{dist_info}/entry_points.txt": scripts,
        f"{dist_info}/licenses/LICENSE": "fixture\n",
        f"{dist_info}/licenses/NOTICE": "fixture\n",
    }
    with zipfile.ZipFile(path, "w") as archive:
        for filename, payload in files.items():
            archive.writestr(filename, payload)


def test_wheel_requires_primary_and_compatibility_clis(tmp_path):
    wheel = tmp_path / "opswitness-0.1.0a1-py3-none-any.whl"
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "opswitness"\nversion = "0.1.0a1"\n')
    _wheel(wheel)

    verify_wheel(wheel, pyproject=pyproject)


def test_wheel_accepts_normalized_requires_python_order(tmp_path):
    wheel = tmp_path / "opswitness-0.1.0a1-py3-none-any.whl"
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "opswitness"\nversion = "0.1.0a1"\n')
    _wheel(wheel, requires_python="<3.13,>=3.12")

    verify_wheel(wheel, pyproject=pyproject)


def test_wheel_rejects_different_python_range(tmp_path):
    wheel = tmp_path / "opswitness-0.1.0a1-py3-none-any.whl"
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "opswitness"\nversion = "0.1.0a1"\n')
    _wheel(wheel, requires_python=">=3.11,<3.13")

    with pytest.raises(DistributionError, match="Requires-Python"):
        verify_wheel(wheel, pyproject=pyproject)


def test_wheel_rejects_missing_compatibility_cli(tmp_path):
    wheel = tmp_path / "opswitness-0.1.0a1-py3-none-any.whl"
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "opswitness"\nversion = "0.1.0a1"\n')
    _wheel(wheel, entries="[console_scripts]\nopswitness = opswitness.cli:app\n")

    with pytest.raises(DistributionError, match="console scripts"):
        verify_wheel(wheel, pyproject=pyproject)


def test_manifest_binds_clean_commit_tag_and_asset_hashes(tmp_path):
    root = tmp_path / "repo"
    dist = root / "dist"
    dist.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", root], check=True)
    subprocess.run(["git", "-C", root, "config", "user.name", "OpsWitness Test"], check=True)
    subprocess.run(["git", "-C", root, "config", "user.email", "test@example.com"], check=True)
    (root / "pyproject.toml").write_text('[project]\nname = "opswitness"\nversion = "0.1.0a1"\n')
    (root / ".gitignore").write_text("dist/\n")
    subprocess.run(["git", "-C", root, "add", "."], check=True)
    subprocess.run(["git", "-C", root, "commit", "-qm", "fixture"], check=True)
    (dist / "opswitness-0.1.0a1-py3-none-any.whl").write_bytes(b"wheel")
    (dist / "opswitness-0.1.0a1.tar.gz").write_bytes(b"sdist")
    (dist / "sbom.spdx.json").write_text("{}\n")

    manifest = _MANIFEST.write_manifest(
        root=root,
        dist=dist,
        tag="v0.1.0-alpha.1",
    )

    assert manifest["clean_tree"] is True
    assert manifest["schema_version"] == 3
    assert manifest["tag"] == "v0.1.0-alpha.1"
    assert manifest["python_version"] == "0.1.0a1"
    assert manifest["public_version"] == "0.1.0-alpha.1"
    assert {item["name"] for item in manifest["artifacts"]} == {
        "opswitness-0.1.0a1-py3-none-any.whl",
        "opswitness-0.1.0a1.tar.gz",
        "sbom.spdx.json",
    }
    saved = json.loads((dist / "build-manifest.json").read_text())
    assert saved["git_commit"] == manifest["git_commit"]


def test_schema_3_manifest_requires_complete_signed_macos_evidence(tmp_path):
    root = tmp_path / "repo"
    dist = root / "dist"
    dist.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", root], check=True)
    subprocess.run(["git", "-C", root, "config", "user.name", "OpsWitness Test"], check=True)
    subprocess.run(["git", "-C", root, "config", "user.email", "test@example.com"], check=True)
    (root / "pyproject.toml").write_text('[project]\nname = "opswitness"\nversion = "0.1.0a1"\n')
    (root / ".gitignore").write_text("dist/\n")
    dependency_lock = root / "desktop" / "python-requirements.lock"
    dependency_lock.parent.mkdir()
    dependency_lock.write_text("fixture==1.0 --hash=sha256:" + "b" * 64 + "\n")
    dependency_review = root / "desktop" / "python-backend-license-review.json"
    dependency_review.write_text(
        json.dumps(
            {
                "schema": 1,
                "lock_sha256": _MANIFEST.sha256(dependency_lock),
                "review_status": "approved",
                "packages": [],
            }
        )
    )
    subprocess.run(["git", "-C", root, "add", "."], check=True)
    subprocess.run(["git", "-C", root, "commit", "-qm", "fixture"], check=True)

    assets = {
        "opswitness-0.1.0a1-py3-none-any.whl": b"wheel",
        "opswitness-0.1.0a1.tar.gz": b"sdist",
        "OpsWitness-0.1.0-alpha.1-macos-arm64.dmg": b"dmg",
        "OpsWitness-0.1.0-alpha.1-macos-arm64-updater.tar.gz": b"updater",
        "OpsWitness-0.1.0-alpha.1-macos-arm64-updater.tar.gz.sig": b"signature",
        "THIRD_PARTY_NOTICES.txt": b"notices",
        "updates-alpha-latest.json": b"{}",
        "python-sbom.spdx.json": json.dumps(
            {
                "spdxVersion": "SPDX-2.3",
                "packages": [
                    {
                        "name": "opswitness",
                        "versionInfo": "0.1.0a1",
                    }
                ],
            }
        ).encode(),
        "app-sbom.spdx.json": b'{"spdxVersion":"SPDX-2.3","packages":[]}',
    }
    for name, body in assets.items():
        (dist / name).write_bytes(body)
    backend_provenance = dist / "backend-build-provenance.json"
    backend_provenance.write_text(
        json.dumps(
            {
                "schema": 1,
                "build_mode": "release",
                "python": {
                    "implementation": "CPython",
                    "version": "3.12.13",
                    "architecture": "arm64",
                },
                "wheel": {
                    "distribution": "opswitness",
                    "version": "0.1.0a1",
                    "filename": "opswitness-0.1.0a1-py3-none-any.whl",
                    "sha256": _MANIFEST.sha256(dist / "opswitness-0.1.0a1-py3-none-any.whl"),
                },
                "requirements": {
                    "filename": dependency_lock.name,
                    "sha256": _MANIFEST.sha256(dependency_lock),
                    "package_count": 1,
                    "hashes_required": True,
                },
                "license_review": {
                    "filename": dependency_review.name,
                    "sha256": _MANIFEST.sha256(dependency_review),
                    "status": "approved",
                    "release_gate_enforced": True,
                },
                "source_isolation": {
                    "release_wheel_only": True,
                    "repository_source_on_import_path": False,
                },
            }
        )
    )
    metadata = dist / "macos-signing.json"
    metadata.write_text(
        json.dumps(
            {
                "architecture": "arm64",
                "minimum_macos": "14.0",
                "bundle_id": "com.opswitness.app",
                "signing": {
                    "mode": "developer-id",
                    "identity": "Developer ID Application: Example (TEAM)",
                    "cdhash": "0123456789abcdef",
                    "hardened_runtime": True,
                    "nested_code_verified": True,
                    "app_sandbox": False,
                },
                "notarization": {
                    "status": "Accepted",
                    "request_id": "example-request",
                    "stapled": True,
                    "gatekeeper_assessment": "accepted",
                },
            }
        )
    )
    lock = dist / "vendor-lock.json"
    lock.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "target": "aarch64-apple-darwin",
                "components": [
                    {
                        "id": "opswitness-backend",
                        "version": "0.1.0-alpha.1",
                        "source_url": "https://github.com/opswitness/opswitness",
                        "upstream_sha256": None,
                        "build_source_commit": "c" * 40,
                        "build_artifact_sha256": "e" * 64,
                        "license": "Apache-2.0",
                        "redistribution_review": "approved",
                        "provision": None,
                        "python_bundle": {
                            "runtime_version": "3.12.13",
                            "runtime_source_url": (
                                "https://github.com/astral-sh/python-build-standalone/"
                                "releases/download/20260510/"
                                "cpython-3.12.13%2B20260510-aarch64-apple-darwin-"
                                "install_only.tar.gz"
                            ),
                            "runtime_sha256": (
                                "5a30271f8d345a5b02b0c9e4e31e0f1e1455a8e4a04fba95cd9762472abc3b17"
                            ),
                            "runtime_license": "Python-2.0 AND MPL-2.0",
                            "runtime_notice": "fixture",
                            "runtime_redistribution_review": "approved",
                            "dependency_lock_path": "desktop/python-requirements.lock",
                            "dependency_lock_sha256": _MANIFEST.sha256(dependency_lock),
                            "dependency_license_review_path": (
                                "desktop/python-backend-license-review.json"
                            ),
                            "dependency_license_review_sha256": _MANIFEST.sha256(dependency_review),
                            "dependency_license_review": "approved",
                        },
                    },
                    {
                        "id": "runtime",
                        "version": "1",
                        "source_url": "https://example.com/runtime.tar.gz",
                        "upstream_sha256": "a" * 64,
                        "license": "MIT",
                        "redistribution_review": "approved",
                        "provision": {
                            "archive_type": "tar.gz",
                            "root_path": "runtime",
                            "output_kind": "directory",
                            "entrypoint": "bin/runtime",
                            "required_paths": ["bin/runtime"],
                        },
                    },
                ],
            }
        )
    )

    manifest = _MANIFEST.write_manifest(
        root=root,
        dist=dist,
        tag="v0.1.0-alpha.1",
        require_macos=True,
        require_release_ready=True,
        vendor_lock=lock,
        macos_metadata=metadata,
        candidate_run_id="1234",
        candidate_run_attempt="2",
    )

    assert manifest["release_ready"] is True
    assert manifest["candidate"] == {
        "workflow_run_id": 1234,
        "workflow_run_attempt": 2,
    }
    assert manifest["platforms"]["macos"]["notarization"]["status"] == "Accepted"
    kinds = {item["kind"] for item in manifest["artifacts"]}
    assert {
        "wheel",
        "sdist",
        "macos_dmg",
        "macos_updater",
        "updater_signature",
        "third_party_notices",
        "backend_build_provenance",
        "vendor_lock",
        "macos_signing_metadata",
        "updater_feed",
    } <= kinds


def test_public_manifest_rejects_incomplete_vendor_lock(tmp_path):
    lock = tmp_path / "vendor-lock.json"
    lock.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "runtimes": [
                    {
                        "name": "paperclipai",
                        "version": "2026.707.0",
                        "source_url": "https://example.com/paperclip.tgz",
                        "sha256": None,
                        "architecture": "arm64",
                        "license": "MIT",
                    }
                ],
            }
        )
    )

    with pytest.raises(ValueError, match="paperclipai is incomplete: sha256"):
        _MANIFEST.assert_vendor_lock(lock, require_complete=True)
    payload = _MANIFEST.assert_vendor_lock(lock, require_complete=False)
    assert payload["runtimes"][0]["sha256"] is None


def test_release_gate_defers_only_first_party_backend_digest_to_build(tmp_path):
    dependency_lock = tmp_path / "desktop" / "python-requirements.lock"
    dependency_lock.parent.mkdir()
    dependency_lock.write_text("fixture==1.0 --hash=sha256:" + "b" * 64 + "\n")
    dependency_review = tmp_path / "desktop" / "python-backend-license-review.json"
    dependency_review.write_text(
        json.dumps(
            {
                "schema": 1,
                "lock_sha256": _MANIFEST.sha256(dependency_lock),
                "review_status": "approved",
                "packages": [],
            }
        )
    )
    lock = tmp_path / "vendor-lock.json"
    lock.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "target": "aarch64-apple-darwin",
                "components": [
                    {
                        "id": "opswitness-backend",
                        "version": "0.1.0-alpha.1",
                        "source_url": "https://github.com/opswitness/opswitness",
                        "upstream_sha256": None,
                        "license": "Apache-2.0",
                        "redistribution_review": "blocked",
                        "provision": None,
                        "python_bundle": {
                            "runtime_version": "3.12.13",
                            "runtime_source_url": (
                                "https://github.com/astral-sh/python-build-standalone/"
                                "releases/download/20260510/"
                                "cpython-3.12.13%2B20260510-aarch64-apple-darwin-"
                                "install_only.tar.gz"
                            ),
                            "runtime_sha256": (
                                "5a30271f8d345a5b02b0c9e4e31e0f1e1455a8e4a04fba95cd9762472abc3b17"
                            ),
                            "runtime_license": "Python-2.0 AND MPL-2.0",
                            "runtime_notice": "fixture",
                            "runtime_redistribution_review": "approved",
                            "dependency_lock_path": "desktop/python-requirements.lock",
                            "dependency_lock_sha256": _MANIFEST.sha256(dependency_lock),
                            "dependency_license_review_path": (
                                "desktop/python-backend-license-review.json"
                            ),
                            "dependency_license_review_sha256": _MANIFEST.sha256(dependency_review),
                            "dependency_license_review": "approved",
                        },
                    },
                    {
                        "id": "runtime",
                        "version": "1",
                        "source_url": "https://example.com/runtime.tar.gz",
                        "upstream_sha256": "a" * 64,
                        "license": "MIT",
                        "redistribution_review": "approved",
                        "provision": {
                            "archive_type": "tar.gz",
                            "root_path": "runtime",
                            "output_kind": "directory",
                            "entrypoint": "bin/runtime",
                            "required_paths": ["bin/runtime"],
                        },
                    },
                ],
            }
        )
    )
    _MANIFEST.assert_vendor_lock(
        lock,
        require_complete=True,
        allow_first_party_unresolved=True,
        root=tmp_path,
    )
    with pytest.raises(ValueError, match="opswitness-backend is incomplete"):
        _MANIFEST.assert_vendor_lock(lock, require_complete=True)


def test_repository_vendor_lock_blocks_python_redistribution_until_review():
    root = Path(__file__).parents[1]

    with pytest.raises(ValueError, match="runtime_redistribution_review=approved"):
        _MANIFEST.assert_vendor_lock(
            root / "desktop" / "vendor-lock.json",
            require_complete=True,
            allow_first_party_unresolved=True,
            root=root,
        )


def test_macos_signing_is_explicit_and_never_uses_deep():
    root = Path(__file__).parents[1]
    signing = (root / "scripts" / "macos_sign_inside_out.sh").read_text()
    assert "Mach-O" in signing
    assert "--options runtime" in signing
    assert "--preserve-metadata=identifier,entitlements" in signing
    assert "backend-adhoc.plist" in signing
    assert "--verify-existing" in signing
    assert "--post-sign" in signing
    assert "--pre-sign-manifest-sha256" in signing
    assert signing.index("--verify-existing") < signing.index("for candidate in")
    assert signing.index("--post-sign") < signing.rindex('sign_path "$app_bundle"')
    assert "codesign --deep" not in signing
    assert "/usr/bin/codesign --verify --strict" in signing
    backend_entitlements = plistlib.loads(
        (root / "desktop" / "entitlements" / "backend-adhoc.plist").read_bytes()
    )
    assert backend_entitlements == {"com.apple.security.cs.disable-library-validation": True}


def test_alpha_update_feed_is_https_and_signature_bound(tmp_path, monkeypatch):
    signature = tmp_path / "updater.sig"
    signature.write_text("fixture-signature\n")
    output = tmp_path / "latest.json"
    script = Path(__file__).parents[1] / "scripts" / "macos_build_update_feed.py"
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    subprocess.run(
        [
            "python",
            script,
            "--version",
            "0.1.0-alpha.1",
            "--archive-url",
            "https://example.com/OpsWitness-updater.tar.gz",
            "--signature",
            signature,
            "--output",
            output,
        ],
        check=True,
    )
    payload = json.loads(output.read_text())
    platform = payload["platforms"]["darwin-aarch64"]
    assert payload["version"] == "0.1.0-alpha.1"
    assert platform["signature"] == "fixture-signature"
    assert platform["url"].startswith("https://")


def test_manifest_rejects_dirty_tree(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", root], check=True)
    subprocess.run(["git", "-C", root, "config", "user.name", "OpsWitness Test"], check=True)
    subprocess.run(["git", "-C", root, "config", "user.email", "test@example.com"], check=True)
    (root / "tracked.txt").write_text("clean\n")
    subprocess.run(["git", "-C", root, "add", "."], check=True)
    subprocess.run(["git", "-C", root, "commit", "-qm", "fixture"], check=True)
    (root / "tracked.txt").write_text("dirty\n")

    with pytest.raises(ValueError, match="clean Git tree"):
        _MANIFEST.assert_clean_tree(root)


def test_manifest_can_require_spdx_sbom(tmp_path):
    root = tmp_path / "repo"
    dist = root / "dist"
    dist.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", root], check=True)
    subprocess.run(["git", "-C", root, "config", "user.name", "OpsWitness Test"], check=True)
    subprocess.run(["git", "-C", root, "config", "user.email", "test@example.com"], check=True)
    (root / "pyproject.toml").write_text('[project]\nname = "opswitness"\nversion = "0.1.0a1"\n')
    (root / ".gitignore").write_text("dist/\n")
    subprocess.run(["git", "-C", root, "add", "."], check=True)
    subprocess.run(["git", "-C", root, "commit", "-qm", "fixture"], check=True)
    (dist / "opswitness-0.1.0a1-py3-none-any.whl").write_bytes(b"wheel")
    (dist / "opswitness-0.1.0a1.tar.gz").write_bytes(b"sdist")

    with pytest.raises(ValueError, match="SPDX SBOM"):
        _MANIFEST.write_manifest(
            root=root,
            dist=dist,
            tag="v0.1.0-alpha.1",
            require_sbom=True,
        )

    (dist / "sbom.spdx.json").write_text(
        json.dumps(
            {
                "spdxVersion": "SPDX-2.3",
                "packages": [
                    {
                        "name": "dist",
                        "versionInfo": "0.1.0a1",
                        "SPDXID": "SPDXRef-dist",
                    }
                ],
            }
        )
    )
    with pytest.raises(
        ValueError,
        match="does not identify the opswitness 0.1.0a1 distribution",
    ):
        _MANIFEST.write_manifest(
            root=root,
            dist=dist,
            tag="v0.1.0-alpha.1",
            require_sbom=True,
        )

    (dist / "sbom.spdx.json").write_text(
        json.dumps(
            {
                "spdxVersion": "SPDX-2.3",
                "packages": [
                    {
                        "name": "opswitness",
                        "versionInfo": "0.1.0a0",
                        "SPDXID": "SPDXRef-opswitness",
                    }
                ],
            }
        )
    )
    with pytest.raises(
        ValueError,
        match="does not identify the opswitness 0.1.0a1 distribution",
    ):
        _MANIFEST.write_manifest(
            root=root,
            dist=dist,
            tag="v0.1.0-alpha.1",
            require_sbom=True,
        )

    (dist / "sbom.spdx.json").write_text(
        json.dumps(
            {
                "spdxVersion": "SPDX-2.3",
                "packages": [
                    {
                        "name": "opswitness",
                        "versionInfo": "0.1.0a1",
                        "SPDXID": "SPDXRef-opswitness",
                    }
                ],
            }
        )
    )
    manifest = _MANIFEST.write_manifest(
        root=root,
        dist=dist,
        tag="v0.1.0-alpha.1",
        require_sbom=True,
    )
    assert any(item["name"] == "sbom.spdx.json" for item in manifest["artifacts"])


def test_release_candidate_is_immutable_and_never_publishes_or_builds_from_tag():
    root = Path(__file__).parents[1]
    workflow = yaml.load(
        (root / ".github" / "workflows" / "release.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    jobs = workflow["jobs"]
    preflight = jobs["preflight"]
    build = jobs["build"]
    macos = jobs["macos"]

    assert "push" not in workflow["on"]
    assert set(jobs) == {"preflight", "quality", "dco", "gitleaks", "build", "macos"}
    assert build["needs"] == ["preflight", "quality", "dco", "gitleaks"]
    assert preflight["permissions"] == {}
    preflight_runs = "\n".join(step.get("run", "") for step in preflight["steps"])
    assert 'test "$GITHUB_REF" = "refs/heads/main"' in preflight_runs
    assert set(jobs["quality"]["strategy"]["matrix"]["os"]) == {
        "ubuntu-latest",
        "macos-14",
    }
    quality_runs = [step.get("run", "") for step in jobs["quality"]["steps"]]
    assert "npm test" in quality_runs
    assert "python -m pytest -q" in quality_runs
    assert any("check_release_identity.py" in run for run in quality_runs)
    assert any("check_dco.py" in step.get("run", "") for step in jobs["dco"]["steps"])
    gitleaks_steps = jobs["gitleaks"]["steps"]
    install_gitleaks = next(
        step for step in gitleaks_steps if step.get("name") == "Install gitleaks"
    )
    setup_go = next(
        step for step in gitleaks_steps if step.get("uses", "").startswith("actions/setup-go@")
    )
    assert setup_go["uses"].endswith("@924ae3a1cded613372ab5595356fb5720e22ba16")
    assert setup_go["with"] == {"go-version": "1.24.11", "cache": "false"}
    assert install_gitleaks["env"]["GITLEAKS_VERSION"] == "v8.30.1"
    assert "github.com/zricethezav/gitleaks/v8@${GITLEAKS_VERSION}" in install_gitleaks["run"]
    scan_history = next(
        step for step in gitleaks_steps if step.get("name") == "Scan full git history"
    )
    assert 'gitleaks" git --redact --no-banner --verbose .' in scan_history["run"]
    assert "GITLEAKS_LICENSE" not in str(jobs["gitleaks"])
    assert build["permissions"] == {"contents": "read"}
    assert not any(step.get("uses", "").startswith("actions/attest@") for step in build["steps"])
    extract_wheel = next(
        step
        for step in build["steps"]
        if step.get("name") == "Extract the release wheel for SBOM generation"
    )
    assert "python -m zipfile -e" in extract_wheel["run"]
    generate_sbom = next(
        step for step in build["steps"] if step.get("name") == "Generate Python SPDX SBOM"
    )
    assert "file" not in generate_sbom["with"]
    assert generate_sbom["with"]["path"].endswith("/opswitness-release-wheel")
    assert generate_sbom["with"]["upload-artifact"] == "false"
    assert macos["runs-on"] == "macos-14"
    assert macos["permissions"] == {"contents": "read"}
    assert not any(
        step.get("uses", "").startswith("actions/setup-python@") for step in macos["steps"]
    )
    install_python = next(
        step
        for step in macos["steps"]
        if step.get("name") == "Install CPython from the exact verified arm64 archive"
    )
    vendor_lock = json.loads((root / "desktop" / "vendor-lock.json").read_text())
    python_bundle = next(
        component["python_bundle"]
        for component in vendor_lock["components"]
        if component["id"] == "opswitness-backend"
    )
    assert install_python["env"]["PYTHON_RUNTIME_URL"] == python_bundle["runtime_source_url"]
    assert install_python["env"]["PYTHON_RUNTIME_SHA256"] == python_bundle["runtime_sha256"]
    assert "shasum -a 256 --check" in install_python["run"]
    assert "/usr/sbin/installer" not in install_python["run"]
    assert 'runtime_root="$RUNNER_TEMP/opswitness-python-runtime"' in install_python["run"]
    assert "python/bin/python3.12" in install_python["run"]
    assert "OPSWITNESS_PYTHON=" in install_python["run"]
    macos_runs = "\n".join(step.get("run", "") for step in macos["steps"])
    assert "macos_sign_inside_out.sh" in macos_runs
    assert "macos_notarize.sh" in macos_runs
    assert "macos_validate_distribution.sh" in macos_runs
    assert "macos_fresh_install_smoke.sh" in macos_runs
    assert "--require-release-ready" in macos_runs
    assert "codesign --deep" not in macos_runs
    assert "PUBLIC_RELEASE_APPROVED" not in macos_runs
    gate_step = next(
        step
        for step in macos["steps"]
        if step.get("name") == "Enforce the signed-candidate release gate"
    )
    assert "OPSWITNESS_UPDATER_PUBLIC_KEY" in gate_step["env"]
    assert "provision_macos_vendor.py" in gate_step["run"]
    provision = next(
        step
        for step in macos["steps"]
        if step.get("name") == "Provision exact vendor archives on the empty runner"
    )
    assert "--github-env" in provision["run"]
    assert "vars.OPSWITNESS_NODE_BIN" not in str(macos)
    bind_wheel = next(
        step
        for step in macos["steps"]
        if step.get("name") == "Bind the exact release wheel to the backend build"
    )
    assert "OPSWITNESS_RELEASE_WHEEL_SHA256" in bind_wheel["run"]
    build_app = next(
        step for step in macos["steps"] if step.get("name") == "Build pinned application resources"
    )
    assert "OPSWITNESS_UPDATER_PUBLIC_KEY" in build_app["env"]
    assemble = next(
        step
        for step in macos["steps"]
        if step.get("name") == "Assemble and verify immutable signed candidate"
    )
    assert "--candidate-run-id" in assemble["run"]
    assert "verify-candidate" in assemble["run"]
    candidate_upload = next(
        step
        for step in macos["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
    )
    assert candidate_upload["id"] == "candidate-artifact"
    assert "github.run_id" in candidate_upload["with"]["name"]
    candidate_transport = next(
        step
        for step in macos["steps"]
        if step.get("name") == "Record the immutable candidate artifact transport identity"
    )
    assert "outputs.artifact-id" in candidate_transport["run"]
    assert "outputs.artifact-digest" in candidate_transport["run"]
    assert not any(step.get("uses", "").startswith("actions/attest@") for step in macos["steps"])
    assert "gh release create" not in str(workflow)


def test_macos_candidate_pins_rust_and_fails_closed_on_disk_capacity():
    root = Path(__file__).parents[1]
    workflow = yaml.load(
        (root / ".github" / "workflows" / "release.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    macos = workflow["jobs"]["macos"]
    cargo_manifest = tomllib.loads((root / "desktop" / "src-tauri" / "Cargo.toml").read_text())

    assert cargo_manifest["package"]["rust-version"] == "1.88"
    assert macos["env"] == {
        "RUST_VERSION": "1.88.0",
        "RUST_TOOLCHAIN": "1.88.0-aarch64-apple-darwin",
        "MACOS_INITIAL_FREE_GIB": "24",
        "MACOS_BUILD_FREE_GIB": "18",
        "MACOS_POST_BUILD_FREE_GIB": "8",
        "MACOS_FALLBACK_RUNNER_FREE_GIB": "30",
    }

    prepare = next(
        step
        for step in macos["steps"]
        if step.get("name") == "Prepare an arm64 runner with deterministic disk headroom"
    )["run"]
    assert '[[ "$(uname -m)" != arm64 ]]' in prepare
    assert "active_developer=$(xcode-select -p)" in prepare
    assert '[[ "$candidate" -ef "$active_xcode" ]]' in prepare
    assert "candidate_name" in prepare
    assert "Xcode(_[0-9]+" in prepare
    assert 'sudo rm -rf -- "$candidate"' in prepare
    assert "MACOS_INITIAL_FREE_GIB * 1024 * 1024" in prepare
    assert "MACOS_FALLBACK_RUNNER_FREE_GIB" in prepare

    install_toolchains = next(
        step for step in macos["steps"] if step.get("name") == "Install pinned build toolchains"
    )["run"]
    assert 'rustup toolchain install "$RUST_TOOLCHAIN" --profile minimal --no-self-update' in (
        install_toolchains
    )
    assert 'rustup override set "$RUST_TOOLCHAIN"' in install_toolchains
    assert "aarch64-apple-darwin" in install_toolchains
    assert "cargo install tauri-cli --version 2.8.4 --locked" in install_toolchains
    assert "1.84" not in install_toolchains

    validate = next(
        step
        for step in macos["steps"]
        if step.get("name") == "Validate desktop project and release scripts"
    )["run"]
    assert "cargo check --locked --manifest-path desktop/src-tauri/Cargo.toml" in validate

    provision = next(
        step
        for step in macos["steps"]
        if step.get("name") == "Provision exact vendor archives on the empty runner"
    )["run"]
    assert "for component in node paperclip aioncore codex" in provision
    assert 'find "$component_root" -mindepth 1 -maxdepth 1 -type f -print0' in provision
    assert 'rm -f -- "$archive"' in provision

    build_app = next(
        step for step in macos["steps"] if step.get("name") == "Build pinned application resources"
    )["run"]
    assert "desktop/scripts/build_release.sh" not in build_app
    assert "desktop/scripts/build_backend.sh" in build_app
    assert "desktop/scripts/stage_runtime.sh" in build_app
    assert 'rm -rf -- "$RUNNER_TEMP/opswitness-vendor"' in build_app
    assert "MACOS_BUILD_FREE_GIB * 1024 * 1024" in build_app
    assert "MACOS_FALLBACK_RUNNER_FREE_GIB" in build_app
    assert "--remap-path-prefix=$GITHUB_WORKSPACE=/workspace" in build_app
    assert "--remap-path-prefix=$cargo_source_root=/cargo" in build_app
    assert re.search(r"cargo tauri build[\s\S]+--locked", build_app)

    reclaim = next(
        step
        for step in macos["steps"]
        if step.get("name") == "Preserve the exact App and reclaim build-only space"
    )["run"]
    assert 'mv "$app" "$hold/OpsWitness.app"' in reclaim
    assert 'rm -rf -- "$target_root"' in reclaim
    assert "desktop/.stage/runtime/aioncore" in reclaim
    assert "desktop/.stage/runtime/resource-manifest.json" in reclaim
    assert "test -f desktop/.stage/runtime/.gitkeep" in reclaim
    assert "MACOS_POST_BUILD_FREE_GIB * 1024 * 1024" in reclaim
    assert "MACOS_FALLBACK_RUNNER_FREE_GIB" in reclaim

    package = next(
        step
        for step in macos["steps"]
        if step.get("name") == "Sign inside-out and create DMG and updater archive"
    )["run"]
    assert 'tar -C "$(dirname "$app")" -czf "$updater" "$(basename "$app")"' in package
    assert "updater_root" not in package
    assert 'rm -rf -- "$dmg_root"' in package

    release_docs = (root / "docs" / "WEBSITE-RELEASE.md").read_text()
    assert "at least 24 GiB free" in release_docs
    assert "18 GiB" in release_docs
    assert "8 GiB" in release_docs
    assert "at least 30 GiB free workspace" in release_docs
    assert "partial candidate" in release_docs


def test_tag_promotion_downloads_exact_canaried_candidate_without_rebuilding():
    root = Path(__file__).parents[1]
    promotion = yaml.load(
        (root / ".github" / "workflows" / "release-promote.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    canary = yaml.load(
        (root / ".github" / "workflows" / "release-canary.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    observation = yaml.load(
        (root / ".github" / "workflows" / "release-canary-observation.yml").read_text(),
        Loader=yaml.BaseLoader,
    )

    assert promotion["on"]["push"]["tags"] == ["v0.1.0-alpha.1"]
    assert set(promotion["jobs"]) == {"promote"}
    promote = promotion["jobs"]["promote"]
    assert promote["environment"] == "alpha-release"
    assert promote["permissions"] == {
        "actions": "read",
        "contents": "write",
        "id-token": "write",
        "attestations": "write",
        "artifact-metadata": "write",
    }
    promotion_text = str(promotion)
    for variable in (
        "PUBLIC_RELEASE_APPROVED",
        "ALPHA_CANDIDATE_RUN_ID",
        "ALPHA_CANDIDATE_RUN_ATTEMPT",
        "ALPHA_CANDIDATE_COMMIT",
        "ALPHA_CANDIDATE_DMG_SHA256",
        "ALPHA_CANDIDATE_MANIFEST_SHA256",
        "ALPHA_CANDIDATE_ARTIFACT_SHA256",
        "ALPHA_CANDIDATE_WORKFLOW_ID",
        "ALPHA_CANARY_RUN_ID",
        "ALPHA_CANARY_RUN_ATTEMPT",
        "ALPHA_CANARY_EVIDENCE_SHA256",
        "ALPHA_CANARY_ARTIFACT_SHA256",
        "ALPHA_CANARY_WORKFLOW_ID",
        "ALPHA_CANARY_HOST_IDENTITY_SHA256",
    ):
        assert variable in promotion_text
    promotion_runs = "\n".join(step.get("run", "") for step in promote["steps"])
    assert "verify-promotion" in promotion_runs
    assert "--host-identity-sha256" in promotion_runs
    assert "gh release create" in promotion_runs
    assert "--prerelease" in promotion_runs
    assert "cargo " not in promotion_runs
    assert "python -m build" not in promotion_runs
    assert not any(
        step.get("uses", "").startswith("actions/download-artifact@") for step in promote["steps"]
    )
    provenance_downloads = [
        step for step in promote["steps"] if "github_actions_artifact.py" in step.get("run", "")
    ]
    assert len(provenance_downloads) == 2
    assert ".github/workflows/release.yml" in provenance_downloads[0]["run"]
    assert ".github/workflows/release-canary.yml" in provenance_downloads[1]["run"]
    for step in provenance_downloads:
        assert "--repository-id" in step["run"]
        assert "--workflow-id" in step["run"]
        assert "--artifact-digest" in step["run"]
        assert step.get("continue-on-error") is None
        assert step.get("if") is None
    assert any(step.get("uses", "").startswith("actions/attest@") for step in promote["steps"])

    record = canary["jobs"]["record"]
    assert record["environment"] == "alpha-canary"
    canary_runs = "\n".join(step.get("run", "") for step in record["steps"])
    assert "record-canary" in canary_runs
    assert "--candidate-run-id" in canary_runs
    assert "--canary-run-id" in canary_runs
    assert "--observation-bundle" in canary_runs
    assert "--observation-sha256" in canary_runs
    assert "--observation-run-id" in canary_runs
    assert "--observation-run-attempt" in canary_runs
    assert "--host-identity-sha256" in canary_runs
    assert "--started-at" not in canary_runs and "--completed-at" not in canary_runs
    for source in (
        "sources/soak-status.json",
        "sources/cadence-summary.json",
        "sources/recovery-summary.json",
        "sources/clean-install-summary.json",
        "sources/first-work-summary.json",
    ):
        assert source in canary_runs
    assert "find observation -type f | wc -l" in canary_runs
    assert '= "6"' in canary_runs
    inputs = canary["on"]["workflow_dispatch"]["inputs"]
    assert {
        "started_at",
        "completed_at",
        "cadence",
        "recovery",
        "clean_install",
        "first_work",
    }.isdisjoint(inputs)
    assert {
        "observation_run_id",
        "observation_run_attempt",
        "observation_sha256",
        "candidate_artifact_sha256",
        "observation_artifact_sha256",
    }.issubset(inputs)
    assert {
        "candidate_workflow_id",
        "observation_workflow_id",
    }.isdisjoint(inputs)
    canary_provenance_downloads = [
        step for step in record["steps"] if "github_actions_artifact.py" in step.get("run", "")
    ]
    assert len(canary_provenance_downloads) == 2
    assert ".github/workflows/release.yml" in canary_provenance_downloads[0]["run"]
    assert (
        ".github/workflows/release-canary-observation.yml" in canary_provenance_downloads[1]["run"]
    )
    for step in canary_provenance_downloads:
        assert "--repository-id" in step["run"]
        assert "--workflow-id" in step["run"]
        assert "--artifact-digest" in step["run"]
        assert step.get("continue-on-error") is None
        assert step.get("if") is None
    canary_upload = next(
        step
        for step in record["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
    )
    assert canary_upload["id"] == "canary-artifact"

    observe = observation["jobs"]["ingest"]
    assert observe["environment"] == "alpha-canary-observation"
    assert observe["runs-on"] == {
        "group": "opswitness-alpha-canary",
        "labels": [
            "self-hosted",
            "macOS",
            "ARM64",
            "opswitness-alpha-canary",
        ],
    }
    assert observation["permissions"] == {"contents": "read", "actions": "read"}
    observation_inputs = observation["on"]["workflow_dispatch"]["inputs"]
    assert {
        "observation_path",
        "observation_run_id",
        "observation_run_attempt",
        "observation_status",
    }.isdisjoint(observation_inputs)
    observation_runs = "\n".join(step.get("run", "") for step in observe["steps"])
    assert "/Users/Shared/OpsWitnessAlphaCanary" in str(observe)
    assert "github_actions_artifact.py" in observation_runs
    assert "macos_canary_handoff.py" in observation_runs
    assert "record-canary" in observation_runs
    assert "--host-identity-sha256" in observation_runs
    assert "ALPHA_CANARY_HOST_IDENTITY_SHA256" in str(observe)
    assert 'test "$GITHUB_REF" = "refs/heads/main"' in observation_runs
    observation_upload = next(
        step
        for step in observe["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
    )
    assert observation_upload["id"] == "observation-artifact"
    upload_paths = observation_upload["with"]["path"]
    assert "observation/alpha-canary-observation.json" in upload_paths
    for source in (
        "soak-status.json",
        "cadence-summary.json",
        "recovery-summary.json",
        "clean-install-summary.json",
        "first-work-summary.json",
    ):
        assert source in upload_paths


def test_alpha_canary_observation_schema_is_closed_and_documents_all_checks():
    root = Path(__file__).parents[1]
    schema = json.loads((root / "docs" / "alpha-canary-observation.schema.json").read_text())
    source_schema = json.loads((root / "docs" / "alpha-canary-source.schema.json").read_text())

    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == 1
    assert schema["properties"]["evidence_type"]["const"] == "opswitness-alpha-canary-observation"
    checks = schema["properties"]["checks"]
    assert checks["additionalProperties"] is False
    assert set(checks["required"]) == {
        "soak",
        "cadence",
        "recovery",
        "clean_install",
        "first_work",
    }
    for definition in ("soak", "cadence", "recovery", "cleanInstall", "firstWork"):
        assert schema["$defs"][definition]["additionalProperties"] is False
        assert schema["$defs"][definition]["properties"]["details"]["additionalProperties"] is False
        assert "source_file" in schema["$defs"][definition]["required"]
    assert source_schema["additionalProperties"] is False
    assert source_schema["properties"]["schema_version"]["const"] == 1
    assert set(source_schema["$defs"]) == {
        "cadenceEvidence",
        "cleanInstallEvidence",
        "firstWorkEvidence",
        "recoveryEvidence",
        "soakEvidence",
        "soakJob",
        "soakStatus",
    }
    for definition in (
        "cadenceEvidence",
        "cleanInstallEvidence",
        "firstWorkEvidence",
        "recoveryEvidence",
        "soakEvidence",
        "soakJob",
        "soakStatus",
    ):
        assert source_schema["$defs"][definition]["additionalProperties"] is False


def test_every_external_action_is_pinned_and_dependabot_covers_dependencies():
    root = Path(__file__).parents[1]
    for path in sorted((root / ".github" / "workflows").glob("*.yml")):
        workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
        for job in workflow["jobs"].values():
            for step in job.get("steps", []):
                uses = step.get("uses")
                if uses and not uses.startswith("./"):
                    assert re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", uses), (path, uses)

    config = yaml.load(
        (root / ".github" / "dependabot.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    ecosystems = {item["package-ecosystem"]: item["directory"] for item in config["updates"]}
    assert ecosystems == {"github-actions": "/", "uv": "/", "npm": "/console-ui"}
