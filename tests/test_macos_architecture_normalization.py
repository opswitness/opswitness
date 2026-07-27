import hashlib
import importlib.util
import stat
import sys
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1] / "desktop" / "scripts" / "normalize_macos_architecture.py"
)
SPEC = importlib.util.spec_from_file_location("normalize_macos_architecture", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
normalizer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = normalizer
SPEC.loader.exec_module(normalizer)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _install_fake_macho_tools(monkeypatch):
    def archs(path: Path) -> tuple[str, ...]:
        marker = path.read_text()
        return {
            "ARM64": ("arm64",),
            "UNIVERSAL": ("arm64", "x86_64"),
            "X86": ("x86_64",),
        }[marker]

    def thin(record):
        temporary = record.path.parent / f".{record.path.name}.test-thin"
        temporary.write_text("ARM64")
        mode = stat.S_IMODE(record.path.stat().st_mode)
        temporary.chmod(mode)
        return temporary, mode

    monkeypatch.setattr(normalizer, "is_macho", lambda _: True)
    monkeypatch.setattr(normalizer, "lipo_archs", archs)
    monkeypatch.setattr(normalizer, "_thin", thin)


@pytest.mark.parametrize("magic", sorted(normalizer.MACHO_MAGICS))
def test_macho_detection_uses_only_canonical_four_byte_magics(tmp_path, magic):
    candidate = tmp_path / "candidate"
    candidate.write_bytes(magic + b"payload")

    assert normalizer.is_macho(candidate) is True

    candidate.write_bytes(b"JSON payload")
    assert normalizer.is_macho(candidate) is False


def test_normalization_thins_only_universal_machos_and_writes_auditable_provenance(
    tmp_path, monkeypatch
):
    _install_fake_macho_tools(monkeypatch)
    runtime = tmp_path / "runtime"
    universal = runtime / "node" / "node"
    universal.parent.mkdir(parents=True)
    universal.write_text("UNIVERSAL")
    universal.chmod(0o755)
    arm64 = runtime / "backend" / "opswitness-backend"
    arm64.parent.mkdir(parents=True)
    arm64.write_text("ARM64")
    arm64.chmod(0o755)
    arm64_before = _sha256(arm64)

    payload = normalizer.normalize(runtime, runtime / "architecture-provenance.json")

    assert universal.read_text() == "ARM64"
    assert stat.S_IMODE(universal.stat().st_mode) == 0o755
    assert arm64.read_text() == "ARM64"
    assert payload == {
        "schema_version": 1,
        "target_architecture": "arm64",
        "entries": [
            {
                "path": "backend/opswitness-backend",
                "before_archs": ["arm64"],
                "after_archs": ["arm64"],
                "before_sha256": arm64_before,
                "after_sha256": arm64_before,
                "action": "preserved",
            },
            {
                "path": "node/node",
                "before_archs": ["arm64", "x86_64"],
                "after_archs": ["arm64"],
                "before_sha256": hashlib.sha256(b"UNIVERSAL").hexdigest(),
                "after_sha256": hashlib.sha256(b"ARM64").hexdigest(),
                "action": "thinned_to_arm64",
            },
        ],
    }
    assert (runtime / "architecture-provenance.json").read_text().endswith("\n")


def test_normalization_rejects_non_arm64_macho_before_modifying_any_binary(tmp_path, monkeypatch):
    _install_fake_macho_tools(monkeypatch)
    runtime = tmp_path / "runtime"
    universal = runtime / "first"
    universal.parent.mkdir(parents=True)
    universal.write_text("UNIVERSAL")
    x86_only = runtime / "second"
    x86_only.write_text("X86")

    with pytest.raises(RuntimeError, match="without an arm64 slice.*second"):
        normalizer.normalize(runtime, runtime / "architecture-provenance.json")

    assert universal.read_text() == "UNIVERSAL"
    assert not (runtime / "architecture-provenance.json").exists()


def test_normalization_excludes_only_explicit_intel_vendor_prebuild_leaf(tmp_path, monkeypatch):
    _install_fake_macho_tools(monkeypatch)
    runtime = tmp_path / "runtime"
    prebuild = (
        runtime
        / "paperclip"
        / "node_modules"
        / "native-package"
        / "prebuilds"
        / "darwin-x64"
        / "binding.node"
    )
    prebuild.parent.mkdir(parents=True)
    prebuild.write_text("X86")

    payload = normalizer.normalize(runtime, runtime / "architecture-provenance.json")

    assert not prebuild.exists()
    assert prebuild.parent.is_dir()
    assert payload["entries"] == [
        {
            "path": "paperclip/node_modules/native-package/prebuilds/darwin-x64/binding.node",
            "before_archs": ["x86_64"],
            "after_archs": [],
            "before_sha256": hashlib.sha256(b"X86").hexdigest(),
            "after_sha256": None,
            "action": "excluded_non_arm_vendor_prebuild",
        }
    ]


def test_normalization_rejects_similarly_named_non_arm_prebuild_directory(tmp_path, monkeypatch):
    _install_fake_macho_tools(monkeypatch)
    runtime = tmp_path / "runtime"
    universal = runtime / "node" / "node"
    universal.parent.mkdir(parents=True)
    universal.write_text("UNIVERSAL")
    ambiguous = runtime / "paperclip" / "prebuilds" / "darwin-x64-helper" / "binding.node"
    ambiguous.parent.mkdir(parents=True)
    ambiguous.write_text("X86")

    with pytest.raises(RuntimeError, match="darwin-x64-helper"):
        normalizer.normalize(runtime, runtime / "architecture-provenance.json")

    assert universal.read_text() == "UNIVERSAL"
    assert ambiguous.read_text() == "X86"


def test_normalization_refuses_provenance_outside_runtime(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()

    with pytest.raises(ValueError, match="inside the runtime payload"):
        normalizer.normalize(runtime, tmp_path / "architecture-provenance.json")


def test_thin_uses_the_fixed_lipo_binary_and_exact_arm64_slice(tmp_path, monkeypatch):
    binary = tmp_path / "postgres"
    binary.write_text("UNIVERSAL")
    record = normalizer.MachO(
        path=binary,
        relative_path="paperclip/node_modules/@embedded-postgres/darwin-arm64/bin/postgres",
        before_archs=("arm64", "x86_64"),
        before_sha256=_sha256(binary),
    )
    calls: list[list[str]] = []

    def fake_run(argv: list[str]) -> str:
        calls.append(argv)
        if argv[1:2] == ["-archs"]:
            return "arm64" if Path(argv[-1]).read_text() == "ARM64" else "arm64 x86_64"
        assert argv[:4] == [normalizer.LIPO, str(binary), "-thin", "arm64"]
        output = Path(argv[-1])
        output.write_text("ARM64")
        return ""

    monkeypatch.setattr(normalizer, "_run", fake_run)

    temporary, mode = normalizer._thin(record)

    try:
        assert temporary.read_text() == "ARM64"
        assert mode == stat.S_IMODE(binary.stat().st_mode)
        assert calls[0][:4] == [normalizer.LIPO, str(binary), "-thin", "arm64"]
        assert calls[0][4] == "-output"
        assert calls[1] == [normalizer.LIPO, "-archs", str(temporary)]
    finally:
        temporary.unlink(missing_ok=True)
