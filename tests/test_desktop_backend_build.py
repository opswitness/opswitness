import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "desktop" / "scripts" / "validate_backend_build_inputs.py"
SPEC = importlib.util.spec_from_file_location("validate_backend_build_inputs", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
backend_inputs = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = backend_inputs
SPEC.loader.exec_module(backend_inputs)


def _lock(path: Path) -> dict[str, backend_inputs.LockedPackage]:
    path.write_text(
        "mcp==1.28.1 \\\n"
        "    --hash=sha256:" + "1" * 64 + "\n"
        "pyinstaller==6.16.0 \\\n"
        "    --hash=sha256:" + "2" * 64 + "\n",
        encoding="utf-8",
    )
    return backend_inputs.parse_requirements_lock(path)


def _license_review(path: Path, lock: Path, *, approved: bool) -> None:
    packages = []
    if approved:
        packages = [
            {
                "name": name,
                "version": version,
                "license_expression": "Apache-2.0",
                "source_url": f"https://example.invalid/{name}",
                "redistribution_review": "approved",
                "notice": "Reviewed fixture.",
            }
            for name, version in (("mcp", "1.28.1"), ("pyinstaller", "6.16.0"))
        ]
    path.write_text(
        json.dumps(
            {
                "schema": 1,
                "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
                "review_status": "approved" if approved else "incomplete",
                "packages": packages,
                "notice": "fixture",
            }
        ),
        encoding="utf-8",
    )


def _wheel(path: Path, *, name: str = "opswitness", version: str = "0.1.0a1") -> None:
    dist_info = "opswitness-0.1.0a1.dist-info"
    metadata = f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n\n"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("opswitness/__init__.py", "")
        archive.writestr(f"{dist_info}/METADATA", metadata)


def test_checked_in_lock_is_exact_hashed_and_contains_build_and_runtime_graph():
    lock = ROOT / "desktop" / "python-requirements.lock"
    packages = backend_inputs.parse_requirements_lock(lock)

    assert len(packages) == 57
    assert packages["pyinstaller"].version == "6.16.0"
    assert packages["mcp"].version == "1.28.1"
    assert all(package.hashes for package in packages.values())
    input_pins = {
        name: version
        for line in (ROOT / "desktop" / "python-requirements.in").read_text().splitlines()
        if line and not line.startswith("#")
        for name, version in [line.split("==", maxsplit=1)]
    }
    assert input_pins == {name: package.version for name, package in packages.items()}
    status, _ = backend_inputs.validate_license_review(
        ROOT / "desktop" / "python-backend-license-review.json",
        requirements_path=lock,
        packages=packages,
        mode="adhoc",
    )
    assert status == "incomplete"


def test_requirements_lock_rejects_unhashed_or_non_exact_requirement(tmp_path):
    lock = tmp_path / "requirements.lock"
    lock.write_text("mcp>=1.0\npyinstaller==6.16.0\n", encoding="utf-8")

    with pytest.raises(backend_inputs.ValidationError, match="exact|SHA-256"):
        backend_inputs.parse_requirements_lock(lock)


def test_incomplete_license_review_allows_adhoc_but_blocks_release(tmp_path):
    lock = tmp_path / "requirements.lock"
    packages = _lock(lock)
    review = tmp_path / "license-review.json"
    _license_review(review, lock, approved=False)

    status, _ = backend_inputs.validate_license_review(
        review,
        requirements_path=lock,
        packages=packages,
        mode="adhoc",
    )
    assert status == "incomplete"
    with pytest.raises(backend_inputs.ValidationError, match="public release blocked"):
        backend_inputs.validate_license_review(
            review,
            requirements_path=lock,
            packages=packages,
            mode="release",
        )


def test_approved_license_review_requires_exact_lock_coverage(tmp_path):
    lock = tmp_path / "requirements.lock"
    packages = _lock(lock)
    review = tmp_path / "license-review.json"
    _license_review(review, lock, approved=True)
    payload = json.loads(review.read_text())
    payload["packages"].pop()
    review.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(backend_inputs.ValidationError, match="missing locked packages"):
        backend_inputs.validate_license_review(
            review,
            requirements_path=lock,
            packages=packages,
            mode="release",
        )


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("license_expression", "   ", "license expression"),
        ("license_expression", " noassertion ", "license expression"),
        ("source_url", "https://", "source must use HTTPS"),
    ],
)
def test_approved_license_review_rejects_placeholder_evidence(
    tmp_path,
    field,
    value,
    expected,
):
    lock = tmp_path / "requirements.lock"
    packages = _lock(lock)
    review = tmp_path / "license-review.json"
    _license_review(review, lock, approved=True)
    payload = json.loads(review.read_text())
    payload["packages"][0][field] = value
    review.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(backend_inputs.ValidationError, match=expected):
        backend_inputs.validate_license_review(
            review,
            requirements_path=lock,
            packages=packages,
            mode="release",
        )


def test_license_review_is_bound_to_requirements_lock_digest(tmp_path):
    lock = tmp_path / "requirements.lock"
    packages = _lock(lock)
    review = tmp_path / "license-review.json"
    _license_review(review, lock, approved=False)
    lock.write_text(lock.read_text() + "\n# changed\n", encoding="utf-8")

    with pytest.raises(backend_inputs.ValidationError, match="current requirements lock"):
        backend_inputs.validate_license_review(
            review,
            requirements_path=lock,
            packages=packages,
            mode="adhoc",
        )


@pytest.mark.parametrize(
    "installed",
    [
        {"mcp": "1.28.1"},
        {"mcp": "1.28.1", "pyinstaller": "6.16.0", "unexpected": "1"},
        {"mcp": "1.28.1", "pyinstaller": "6.15.0"},
    ],
)
def test_installed_environment_must_exactly_match_lock(tmp_path, installed):
    lock = tmp_path / "requirements.lock"
    packages = _lock(lock)

    with pytest.raises(backend_inputs.ValidationError, match="exactly match"):
        backend_inputs.validate_installed_package_set(installed, packages)

    backend_inputs.validate_installed_package_set(
        {"mcp": "1.28.1", "pyinstaller": "6.16.0"},
        packages,
    )


def test_provenance_is_published_only_after_frozen_backend_exists(tmp_path):
    inputs = tmp_path / "inputs.json"
    inputs.write_text(
        json.dumps(
            {
                "schema": 1,
                "source_isolation": {
                    "release_wheel_only": True,
                    "repository_source_on_import_path": False,
                },
            }
        ),
        encoding="utf-8",
    )
    backend = tmp_path / "opswitness-backend"
    backend.write_bytes(b"frozen")
    backend.chmod(0o755)
    output = tmp_path / "backend-build-provenance.json"

    backend_inputs.finalize_provenance(
        input_path=inputs,
        backend=backend,
        output=output,
    )

    payload = json.loads(output.read_text())
    assert payload["frozen_backend"] == {
        "build_completed": True,
        "filename": "opswitness-backend",
        "format": "pyinstaller-onedir",
        "sha256": hashlib.sha256(b"frozen").hexdigest(),
        "size": 6,
    }


def test_wheel_identity_and_optional_digest_are_verified(tmp_path):
    wheel = tmp_path / "opswitness-0.1.0a1-py3-none-any.whl"
    _wheel(wheel)
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()

    identity = backend_inputs.validate_wheel(
        wheel,
        expected_version="0.1.0a1",
        expected_sha256=digest,
    )

    assert identity.distribution == "opswitness"
    assert identity.version == "0.1.0a1"
    assert identity.sha256 == digest
    with pytest.raises(backend_inputs.ValidationError, match="SHA-256 mismatch"):
        backend_inputs.validate_wheel(
            wheel,
            expected_version="0.1.0a1",
            expected_sha256="0" * 64,
        )


@pytest.mark.parametrize(
    "startup_hook",
    [
        "opswitness-path.pth",
        "sitecustomize/__init__.py",
        "opswitness-0.1.0a1.data/purelib/usercustomize.pyc",
    ],
)
def test_wheel_rejects_import_path_startup_hooks(tmp_path, startup_hook):
    wheel = tmp_path / "opswitness-0.1.0a1-py3-none-any.whl"
    _wheel(wheel)
    with zipfile.ZipFile(wheel, "a") as archive:
        archive.writestr(startup_hook, "/tmp/untrusted\n")

    with pytest.raises(backend_inputs.ValidationError, match="startup hook"):
        backend_inputs.validate_wheel(
            wheel,
            expected_version="0.1.0a1",
            expected_sha256=None,
        )


def test_wheel_must_match_distribution_and_tauri_version(tmp_path):
    wheel = tmp_path / "opswitness-0.1.0a1-py3-none-any.whl"
    _wheel(wheel, name="other", version="0.1.0a2")

    with pytest.raises(backend_inputs.ValidationError, match="distribution must be opswitness"):
        backend_inputs.validate_wheel(
            wheel,
            expected_version="0.1.0a1",
            expected_sha256=None,
        )

    assert (
        backend_inputs._expected_wheel_version(ROOT / "desktop" / "src-tauri" / "tauri.conf.json")
        == "0.1.0a2"
    )


def test_backend_build_uses_isolated_wheel_only_pyinstaller_analysis():
    build_script = (ROOT / "desktop" / "scripts" / "build_backend.sh").read_text()
    release_script = (ROOT / "desktop" / "scripts" / "build_release.sh").read_text()
    pyinstaller_spec = (ROOT / "desktop" / "pyinstaller" / "opswitness.spec").read_text()

    assert "OPSWITNESS_RELEASE_WHEEL:?" in build_script
    assert "-I -m venv" in build_script
    assert "--require-hashes" in build_script
    assert "--only-binary=:all:" in build_script
    assert "--no-index" in build_script
    assert "-I -m pip check" in build_script
    assert 'INPUT_DIR="$BUILD_ROOT/inputs"' in build_script
    assert 'cp -P "$OPSWITNESS_RELEASE_WHEEL" "$RELEASE_WHEEL"' in build_script
    assert '--wheel "$RELEASE_WHEEL"' in build_script
    assert 'PROVENANCE="$DESKTOP_DIR/dist/backend-build-provenance.json"' in build_script
    assert 'rm -f "$PROVENANCE"' in build_script
    assert 'FROZEN_ENTRYPOINT="$BUILD_ROOT/venv/bin/opswitness"' in build_script
    assert '--requirements "$REQUIREMENTS_LOCK"' in build_script
    assert "backend_entry.py" not in build_script
    assert build_script.index("-m PyInstaller") < build_script.index('"$VALIDATOR" finalize')
    assert "EXPECTED_PYTHON = (3, 12, 13)" in SCRIPT.read_text()
    assert 'OPSWITNESS_VENDOR_MODE=release "$SCRIPT_DIR/build_backend.sh"' in release_script
    assert "pathex=[]" in pyinstaller_spec
    assert 'ROOT / "src"' not in pyinstaller_spec
    assert 'Path(sys.prefix) / "bin" / "opswitness"' in pyinstaller_spec
    assert "ENTRYPOINT.is_relative_to(PREFIX)" in pyinstaller_spec
    assert 'collect_all("opswitness")' in pyinstaller_spec
