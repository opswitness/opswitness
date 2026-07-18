import io
import importlib.util
import json
import re
import subprocess
import tarfile
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


def _wheel(path: Path, *, entries: str | None = None, name: str = "opswitness") -> None:
    dist_info = "opswitness-0.1.0a1.dist-info"
    metadata = (
        "Metadata-Version: 2.4\n"
        f"Name: {name}\n"
        "Version: 0.1.0a1\n"
        "Requires-Python: >=3.12,<3.13\n\n"
    )
    scripts = entries or (
        "[console_scripts]\n"
        "opswitness = opswitness.cli:app\n"
        "qd = opswitness.cli:app\n"
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
    (root / "pyproject.toml").write_text(
        '[project]\nname = "opswitness"\nversion = "0.1.0a1"\n'
    )
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
    (root / "pyproject.toml").write_text(
        '[project]\nname = "opswitness"\nversion = "0.1.0a1"\n'
    )
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


def test_release_tag_gate_precedes_build_and_attestation():
    workflow = yaml.load(
        (Path(__file__).parents[1] / ".github" / "workflows" / "release.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    jobs = workflow["jobs"]
    preflight = jobs["preflight"]
    build = jobs["build"]
    publish = jobs["publish"]

    assert build["needs"] == ["preflight", "quality", "dco", "gitleaks"]
    gate = preflight["steps"][0]
    assert gate["name"] == "Reject unapproved public tag"
    assert "PUBLIC_RELEASE_APPROVED" in gate["if"]
    assert preflight["permissions"] == {}
    assert set(jobs["quality"]["strategy"]["matrix"]["os"]) == {
        "ubuntu-latest",
        "macos-14",
    }
    quality_runs = [step.get("run", "") for step in jobs["quality"]["steps"]]
    assert "npm test" in quality_runs
    assert "pytest -q" in quality_runs
    assert any("check_release_identity.py" in run for run in quality_runs)
    assert any("check_dco.py" in step.get("run", "") for step in jobs["dco"]["steps"])
    assert any("gitleaks-action" in step.get("uses", "") for step in jobs["gitleaks"]["steps"])
    assert build["permissions"] == {"contents": "read"}
    assert not any(
        step.get("uses", "").startswith("actions/attest@") for step in build["steps"]
    )
    assert "refs/tags/" in publish["if"]
    assert "PUBLIC_RELEASE_APPROVED" in publish["if"]
    assert publish["needs"] == "build"
    assert publish["permissions"] == {
        "contents": "write",
        "id-token": "write",
        "attestations": "write",
        "artifact-metadata": "write",
    }
    assert any(
        step.get("uses", "").startswith("actions/download-artifact@")
        for step in publish["steps"]
    )
    assert any(
        step.get("uses", "").startswith("actions/attest@")
        for step in publish["steps"]
    )
    assert not any("public-release gate" in step.get("name", "").casefold() for step in build["steps"])


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
