from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
RELEASE_TAG = "v0.1.0-alpha.2"


def _workflow(name: str) -> dict:
    return yaml.load(
        (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


def test_adhoc_build_creates_the_alpha2_dmg() -> None:
    script = (ROOT / "desktop" / "scripts" / "build_adhoc.sh").read_text(
        encoding="utf-8"
    )

    assert 'PUBLIC_VERSION=0.1.0-alpha.2' in script
    assert 'DMG_DIR="$REPO_DIR/dist/releases/v$PUBLIC_VERSION"' in script
    assert 'DMG="$DMG_DIR/$DMG_NAME"' in script
    assert 'test "$RUST_RELEASE" = "1.88.0"' in script
    assert 'test "$CARGO_RELEASE" = "1.88.0"' in script
    assert 'test "$RUST_HOST" = "aarch64-apple-darwin"' in script
    assert "cargo tauri build --config tauri.staged.conf.json --bundles app -- --locked" in script
    assert 'test -d "$DMG_DIR" && test ! -L "$DMG_DIR"' in script
    assert 'test ! -e "$DMG" && test ! -L "$DMG"' in script
    assert 'rm -f "$DMG"' not in script
    assert '"$TEMP_DMG"' in script
    assert '/bin/ln "$TEMP_DMG" "$DMG"' in script
    assert "OpsWitness-0.1.0-alpha.1-macos-arm64.dmg" not in script


def test_ci_checks_the_alpha2_release_identity() -> None:
    workflow = _workflow("ci.yml")
    commands = [
        step["run"]
        for step in workflow["jobs"]["test"]["steps"]
        if "run" in step
    ]

    assert f"python scripts/check_release_identity.py --tag {RELEASE_TAG}" in commands
    assert not any("check_release_identity.py --tag v0.1.0-alpha.1" in command for command in commands)
