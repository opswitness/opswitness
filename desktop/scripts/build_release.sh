#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DESKTOP_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
REPO_DIR=$(CDPATH= cd -- "$DESKTOP_DIR/.." && pwd)

case "$(uname -m)" in
  arm64) ;;
  *) echo "OpsWitness desktop alpha is Apple Silicon-only" >&2; exit 2 ;;
esac

: "${APPLE_SIGNING_IDENTITY:?set APPLE_SIGNING_IDENTITY to the Developer ID Application identity}"
: "${OPSWITNESS_RELEASE_COMMIT:?set OPSWITNESS_RELEASE_COMMIT to the exact 40-hex release commit}"
command -v npm >/dev/null
command -v cargo >/dev/null
CARGO_SOURCE_ROOT=${CARGO_HOME:-"$HOME/.cargo"}
RUSTFLAGS="${RUSTFLAGS:+$RUSTFLAGS }--remap-path-prefix=$REPO_DIR=/workspace --remap-path-prefix=$CARGO_SOURCE_ROOT=/cargo"
export RUSTFLAGS

cd "$REPO_DIR/console-ui"
npm run build

OPSWITNESS_VENDOR_MODE=release "$SCRIPT_DIR/build_backend.sh"
OPSWITNESS_VENDOR_MODE=release "$SCRIPT_DIR/stage_runtime.sh"

cd "$DESKTOP_DIR/src-tauri"
cargo tauri build --config tauri.staged.conf.json --bundles app

APP_PATH="$DESKTOP_DIR/src-tauri/target/release/bundle/macos/OpsWitness.app"
test -d "$APP_PATH"

echo "Application is ready for explicit inside-out signing: $APP_PATH"
