#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DESKTOP_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
REPO_DIR=$(CDPATH= cd -- "$DESKTOP_DIR/.." && pwd)
PYTHON_BIN=${OPSWITNESS_PYTHON:-python3.12}

case "$(uname -m)" in
  arm64) ;;
  *) echo "OpsWitness desktop alpha is Apple Silicon-only" >&2; exit 2 ;;
esac

command -v npm >/dev/null
command -v cargo >/dev/null
cargo --version
APPLE_SIGNING_IDENTITY=${APPLE_SIGNING_IDENTITY:--}
export APPLE_SIGNING_IDENTITY
CARGO_SOURCE_ROOT=${CARGO_HOME:-"$HOME/.cargo"}
RUSTFLAGS="${RUSTFLAGS:+$RUSTFLAGS }--remap-path-prefix=$REPO_DIR=/workspace --remap-path-prefix=$CARGO_SOURCE_ROOT=/cargo"
export RUSTFLAGS

cd "$REPO_DIR/console-ui"
npm run build

"$SCRIPT_DIR/build_backend.sh"
OPSWITNESS_VENDOR_MODE=${OPSWITNESS_VENDOR_MODE:-adhoc} "$SCRIPT_DIR/stage_runtime.sh"

cd "$DESKTOP_DIR/src-tauri"
cargo tauri build --config tauri.staged.conf.json --bundles app

APP_BUNDLE="$DESKTOP_DIR/src-tauri/target/release/bundle/macos/OpsWitness.app"
DMG_DIR="$REPO_DIR/dist/macos"
DMG="$DMG_DIR/OpsWitness-0.1.0-alpha.1-macos-arm64.dmg"
test -d "$APP_BUNDLE"

OPSWITNESS_PYTHON="$PYTHON_BIN" \
  "$REPO_DIR/scripts/macos_sign_inside_out.sh" "$APP_BUNDLE" -

TEMP_PARENT=$(CDPATH= cd -- "${TMPDIR:-/tmp}" && pwd)
DMG_ROOT=$(mktemp -d "$TEMP_PARENT/opswitness-adhoc-dmg.XXXXXX")
cleanup() {
  case "$DMG_ROOT" in
    "$TEMP_PARENT"/opswitness-adhoc-dmg.*)
      rm -rf -- "$DMG_ROOT"
      ;;
  esac
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' HUP TERM

mkdir -p "$DMG_DIR"
ditto "$APP_BUNDLE" "$DMG_ROOT/OpsWitness.app"
ln -s /Applications "$DMG_ROOT/Applications"
rm -f "$DMG"
/usr/bin/hdiutil create \
  -volname OpsWitness \
  -srcfolder "$DMG_ROOT" \
  -format UDZO \
  "$DMG"
/usr/bin/codesign --force --sign - --timestamp=none "$DMG"
/usr/bin/codesign --verify --strict --verbose=2 "$DMG"

echo "Ad-hoc application: $APP_BUNDLE"
echo "Ad-hoc DMG: $DMG"
