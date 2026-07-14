import io
import importlib.util
import re
import tarfile
from pathlib import Path

import pytest
import yaml


_SPEC = importlib.util.spec_from_file_location(
    "quarterdeck_verify_distribution",
    Path(__file__).parents[1] / "scripts" / "verify_distribution.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_VERIFY = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_VERIFY)
DistributionError = _VERIFY.DistributionError
SDIST_REQUIRED = _VERIFY.SDIST_REQUIRED
verify_sdist = _VERIFY.verify_sdist


def _sdist(path: Path, files: set[str], *, non_file: str | None = None) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name in sorted(files):
            payload = b"fixture\n"
            info = tarfile.TarInfo(f"quarterdeck-0.0.1/{name}")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        if non_file is not None:
            info = tarfile.TarInfo(f"quarterdeck-0.0.1/{non_file}")
            info.type = tarfile.FIFOTYPE
            archive.addfile(info)


def test_sdist_accepts_only_tracked_release_inputs(tmp_path):
    path = tmp_path / "quarterdeck.tar.gz"
    _sdist(path, set(SDIST_REQUIRED))

    verify_sdist(path, tracked=set(SDIST_REQUIRED))


@pytest.mark.parametrize(
    "unexpected",
    [
        ".claude/settings.local.json",
        "src/quarterdeck/local_private.py",
    ],
)
def test_sdist_rejects_private_or_untracked_workspace_files(tmp_path, unexpected):
    path = tmp_path / "quarterdeck.tar.gz"
    _sdist(path, {*SDIST_REQUIRED, unexpected})

    with pytest.raises(DistributionError):
        verify_sdist(path, tracked=set(SDIST_REQUIRED))


def test_sdist_rejects_non_file_entries(tmp_path):
    path = tmp_path / "quarterdeck.tar.gz"
    _sdist(path, set(SDIST_REQUIRED), non_file="src/quarterdeck/control.fifo")

    with pytest.raises(DistributionError, match="non-file entry"):
        verify_sdist(path, tracked=set(SDIST_REQUIRED))


def test_release_tag_gate_precedes_build_and_attestation():
    workflow = yaml.load(
        (Path(__file__).parents[1] / ".github" / "workflows" / "release.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    jobs = workflow["jobs"]
    preflight = jobs["preflight"]
    build = jobs["build"]

    assert build["needs"] == "preflight"
    gate = preflight["steps"][0]
    assert gate["name"] == "Reject unapproved public tag"
    assert "PUBLIC_RELEASE_APPROVED" in gate["if"]
    assert preflight["permissions"] == {}
    attest = next(
        step for step in build["steps"] if step.get("uses", "").startswith("actions/attest@")
    )
    assert "refs/tags/" in attest["if"]
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
