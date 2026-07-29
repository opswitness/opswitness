#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DESKTOP_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
REPO_DIR=$(CDPATH= cd -- "$DESKTOP_DIR/.." && pwd)
PYTHON_BIN=${OPSWITNESS_PYTHON:-python3.12}
PUBLIC_VERSION=0.1.0-alpha.2
DMG_NAME="OpsWitness-$PUBLIC_VERSION-macos-arm64.dmg"

fail() {
  echo "ERROR: $*" >&2
  exit 2
}

case "$(uname -m)" in
  arm64) ;;
  *) fail "OpsWitness desktop alpha is Apple Silicon-only" ;;
esac

command -v npm >/dev/null || fail "npm is unavailable"
command -v rustc >/dev/null || fail "rustc is unavailable"
command -v cargo >/dev/null || fail "cargo is unavailable"
RUST_RELEASE=$(rustc -vV | /usr/bin/awk '/^release: / {print $2}')
RUST_HOST=$(rustc -vV | /usr/bin/awk '/^host: / {print $2}')
CARGO_RELEASE=$(cargo --version | /usr/bin/awk '{print $2}')
test "$RUST_RELEASE" = "1.88.0" ||
  fail "Rust 1.88.0 is required; found ${RUST_RELEASE:-unknown}"
test "$CARGO_RELEASE" = "1.88.0" ||
  fail "Cargo 1.88.0 is required; found ${CARGO_RELEASE:-unknown}"
test "$RUST_HOST" = "aarch64-apple-darwin" ||
  fail "the Rust host must be aarch64-apple-darwin; found ${RUST_HOST:-unknown}"
rustc --version
cargo --version
APPLE_SIGNING_IDENTITY=${APPLE_SIGNING_IDENTITY:--}
export APPLE_SIGNING_IDENTITY
CARGO_SOURCE_ROOT=${CARGO_HOME:-"$HOME/.cargo"}
RUSTFLAGS="${RUSTFLAGS:+$RUSTFLAGS }--remap-path-prefix=$REPO_DIR=/workspace --remap-path-prefix=$CARGO_SOURCE_ROOT=/cargo"
export RUSTFLAGS

DMG_DIR="$REPO_DIR/dist/releases/v$PUBLIC_VERSION"
DMG="$DMG_DIR/$DMG_NAME"
mkdir -p "$DMG_DIR"
test -d "$DMG_DIR" && test ! -L "$DMG_DIR" ||
  fail "release output must be a real directory: $DMG_DIR"
test ! -e "$DMG" && test ! -L "$DMG" ||
  fail "refusing to overwrite existing Alpha candidate: $DMG"

cd "$REPO_DIR/console-ui"
npm run build

"$SCRIPT_DIR/build_backend.sh"
OPSWITNESS_VENDOR_MODE=${OPSWITNESS_VENDOR_MODE:-adhoc} "$SCRIPT_DIR/stage_runtime.sh"

cd "$DESKTOP_DIR/src-tauri"
cargo tauri build --config tauri.staged.conf.json --bundles app -- --locked

APP_BUNDLE="$DESKTOP_DIR/src-tauri/target/release/bundle/macos/OpsWitness.app"
test -d "$APP_BUNDLE"

OPSWITNESS_PYTHON="$PYTHON_BIN" \
  "$REPO_DIR/scripts/macos_sign_inside_out.sh" "$APP_BUNDLE" -

TEMP_PARENT=$(CDPATH= cd -- "${TMPDIR:-/tmp}" && pwd)
DMG_ROOT=""
OUTPUT_TEMP_DIR=""
cleanup() {
  case "$DMG_ROOT" in
    "$TEMP_PARENT"/opswitness-adhoc-dmg.*)
      rm -rf -- "$DMG_ROOT"
      ;;
  esac
  case "$OUTPUT_TEMP_DIR" in
    "$DMG_DIR"/.opswitness-adhoc-output.*)
      rm -rf -- "$OUTPUT_TEMP_DIR"
      ;;
  esac
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' HUP TERM
DMG_ROOT=$(mktemp -d "$TEMP_PARENT/opswitness-adhoc-dmg.XXXXXX")
OUTPUT_TEMP_DIR=$(mktemp -d "$DMG_DIR/.opswitness-adhoc-output.XXXXXX")
TEMP_DMG="$OUTPUT_TEMP_DIR/$DMG_NAME"

ditto "$APP_BUNDLE" "$DMG_ROOT/OpsWitness.app"
ln -s /Applications "$DMG_ROOT/Applications"
/usr/bin/hdiutil create \
  -volname OpsWitness \
  -srcfolder "$DMG_ROOT" \
  -format UDZO \
  "$TEMP_DMG"
/usr/bin/hdiutil verify "$TEMP_DMG"
/usr/bin/codesign --force --sign - --timestamp=none "$TEMP_DMG"
/usr/bin/codesign --verify --strict --verbose=2 "$TEMP_DMG"

# Hard-link publication is atomic on this filesystem and fails if the final name exists.
/bin/ln "$TEMP_DMG" "$DMG" ||
  fail "refusing to overwrite concurrently created Alpha candidate: $DMG"
/usr/bin/hdiutil verify "$DMG"
/usr/bin/codesign --verify --strict --verbose=2 "$DMG"

echo "Ad-hoc application: $APP_BUNDLE"
echo "Ad-hoc DMG: $DMG"
