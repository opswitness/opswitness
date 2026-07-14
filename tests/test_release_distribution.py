import io
import importlib.util
import tarfile
from pathlib import Path

import pytest


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
