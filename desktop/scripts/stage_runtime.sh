#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DESKTOP_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
RUNTIME_DIR="$DESKTOP_DIR/.stage/runtime"
VENDOR_MODE=${OPSWITNESS_VENDOR_MODE:-adhoc}
PYTHON_BIN=${OPSWITNESS_PYTHON:-python3.12}

: "${OPSWITNESS_BACKEND_DIR:=$DESKTOP_DIR/dist/pyinstaller/opswitness-backend}"
: "${OPSWITNESS_NODE_BIN:?set OPSWITNESS_NODE_BIN to the pinned arm64 Node executable}"
: "${OPSWITNESS_PAPERCLIP_DIR:?set OPSWITNESS_PAPERCLIP_DIR to the pinned Paperclip package}"
: "${OPSWITNESS_AIONCORE_DIR:?set OPSWITNESS_AIONCORE_DIR to the verified AionCore bundle}"
: "${OPSWITNESS_CODEX_BIN:?set OPSWITNESS_CODEX_BIN to the pinned arm64 Codex executable}"

"$PYTHON_BIN" -c \
  'import platform, sys; sys.exit(0 if sys.platform == "darwin" and platform.machine() == "arm64" else 1)' \
  || {
    echo "runtime staging requires an explicit native macOS arm64 OPSWITNESS_PYTHON" >&2
    exit 1
  }

test -x "$OPSWITNESS_BACKEND_DIR/opswitness-backend"
test -x "$OPSWITNESS_NODE_BIN"
test -f "$OPSWITNESS_PAPERCLIP_DIR/dist/index.js"
test -x "$OPSWITNESS_AIONCORE_DIR/aioncore"
test -x "$OPSWITNESS_CODEX_BIN"

mkdir -p "$RUNTIME_DIR"
find "$RUNTIME_DIR" -mindepth 1 -maxdepth 1 ! -name .gitkeep -exec rm -rf -- {} +
mkdir -p \
  "$RUNTIME_DIR/backend" \
  "$RUNTIME_DIR/node" \
  "$RUNTIME_DIR/paperclip" \
  "$RUNTIME_DIR/aioncore" \
  "$RUNTIME_DIR/codex"

ditto "$OPSWITNESS_BACKEND_DIR" "$RUNTIME_DIR/backend"
ditto "$OPSWITNESS_NODE_BIN" "$RUNTIME_DIR/node/node"
ditto "$OPSWITNESS_PAPERCLIP_DIR" "$RUNTIME_DIR/paperclip"
ditto "$OPSWITNESS_AIONCORE_DIR" "$RUNTIME_DIR/aioncore"
ditto "$OPSWITNESS_CODEX_BIN" "$RUNTIME_DIR/codex/codex"

"$PYTHON_BIN" "$SCRIPT_DIR/stage_codex_only_aioncore.py" \
  --runtime "$RUNTIME_DIR" \
  --vendor-lock "$DESKTOP_DIR/vendor-lock.json" \
  --receipt "$RUNTIME_DIR/staging-exclusions.json"

"$PYTHON_BIN" "$SCRIPT_DIR/stage_codex_only_paperclip.py" \
  --runtime "$RUNTIME_DIR" \
  --vendor-lock "$DESKTOP_DIR/vendor-lock.json" \
  --receipt "$RUNTIME_DIR/paperclip-staging-exclusions.json"

chmod 0755 \
  "$RUNTIME_DIR/backend/opswitness-backend" \
  "$RUNTIME_DIR/node/node" \
  "$RUNTIME_DIR/aioncore/aioncore" \
  "$RUNTIME_DIR/codex/codex"

"$PYTHON_BIN" "$SCRIPT_DIR/normalize_macos_architecture.py" \
  --runtime "$RUNTIME_DIR" \
  --provenance "architecture-provenance.json"

if [ "$VENDOR_MODE" = release ]; then
  : "${OPSWITNESS_RELEASE_COMMIT:?release staging requires OPSWITNESS_RELEASE_COMMIT}"
  "$PYTHON_BIN" "$SCRIPT_DIR/resolve_vendor_lock.py" \
    --source "$DESKTOP_DIR/vendor-lock.json" \
    --destination "$DESKTOP_DIR/.stage/vendor-lock.resolved.json" \
    --backend "$RUNTIME_DIR/backend/opswitness-backend" \
    --mode release \
    --commit "$OPSWITNESS_RELEASE_COMMIT"
else
  "$PYTHON_BIN" "$SCRIPT_DIR/resolve_vendor_lock.py" \
    --source "$DESKTOP_DIR/vendor-lock.json" \
    --destination "$DESKTOP_DIR/.stage/vendor-lock.resolved.json" \
    --backend "$RUNTIME_DIR/backend/opswitness-backend" \
    --mode adhoc
fi

"$PYTHON_BIN" "$SCRIPT_DIR/make_resource_manifest.py" \
  --runtime "$RUNTIME_DIR" \
  --vendor-lock "$DESKTOP_DIR/.stage/vendor-lock.resolved.json" \
  --mode "$VENDOR_MODE"

echo "Staged and integrity-locked runtime at $RUNTIME_DIR"
