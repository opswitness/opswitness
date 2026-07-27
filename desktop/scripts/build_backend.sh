#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DESKTOP_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
REPO_DIR=$(CDPATH= cd -- "$DESKTOP_DIR/.." && pwd)
PYTHON_BIN=${OPSWITNESS_PYTHON:-python3.12}
BUILD_MODE=${OPSWITNESS_VENDOR_MODE:-adhoc}
SOURCE_REQUIREMENTS_LOCK="$DESKTOP_DIR/python-requirements.lock"
SOURCE_LICENSE_REVIEW="$DESKTOP_DIR/python-backend-license-review.json"
SOURCE_VALIDATOR="$SCRIPT_DIR/validate_backend_build_inputs.py"
SOURCE_TAURI_CONFIG="$DESKTOP_DIR/src-tauri/tauri.conf.json"
SOURCE_PYINSTALLER_SPEC="$DESKTOP_DIR/pyinstaller/opswitness.spec"
PROVENANCE="$DESKTOP_DIR/dist/backend-build-provenance.json"
DIST_DIR="$DESKTOP_DIR/dist/pyinstaller"
WORK_DIR="$DESKTOP_DIR/dist/pyinstaller-work"

: "${OPSWITNESS_RELEASE_WHEEL:?set OPSWITNESS_RELEASE_WHEEL to the exact release wheel}"

case "$BUILD_MODE" in
  adhoc|release) ;;
  *) echo "OPSWITNESS_VENDOR_MODE must be adhoc or release" >&2; exit 2 ;;
esac

command -v "$PYTHON_BIN" >/dev/null 2>&1 || {
  echo "selected Python interpreter does not exist: $PYTHON_BIN" >&2
  exit 2
}

mkdir -p "$DESKTOP_DIR/dist"
rm -f "$PROVENANCE"

TEMP_PARENT=$(CDPATH= cd -- "${TMPDIR:-/tmp}" && pwd)
BUILD_ROOT=$(mktemp -d "$TEMP_PARENT/opswitness-backend.XXXXXX")
cleanup() {
  case "$BUILD_ROOT" in
    "$TEMP_PARENT"/opswitness-backend.*)
      rm -rf -- "$BUILD_ROOT"
      ;;
  esac
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' HUP TERM

INPUT_DIR="$BUILD_ROOT/inputs"
mkdir -p "$INPUT_DIR"
WHEEL_FILENAME=${OPSWITNESS_RELEASE_WHEEL##*/}
case "$WHEEL_FILENAME" in
  ""|"."|"..") echo "OPSWITNESS_RELEASE_WHEEL has an invalid filename" >&2; exit 2 ;;
esac
RELEASE_WHEEL="$INPUT_DIR/$WHEEL_FILENAME"
REQUIREMENTS_LOCK="$INPUT_DIR/python-requirements.lock"
LICENSE_REVIEW="$INPUT_DIR/python-backend-license-review.json"
VALIDATOR="$INPUT_DIR/validate_backend_build_inputs.py"
TAURI_CONFIG="$INPUT_DIR/tauri.conf.json"
PYINSTALLER_SPEC="$INPUT_DIR/opswitness.spec"

cp -P "$OPSWITNESS_RELEASE_WHEEL" "$RELEASE_WHEEL"
cp -P "$SOURCE_REQUIREMENTS_LOCK" "$REQUIREMENTS_LOCK"
cp -P "$SOURCE_LICENSE_REVIEW" "$LICENSE_REVIEW"
cp -P "$SOURCE_VALIDATOR" "$VALIDATOR"
cp -P "$SOURCE_TAURI_CONFIG" "$TAURI_CONFIG"
cp -P "$SOURCE_PYINSTALLER_SPEC" "$PYINSTALLER_SPEC"

INPUT_PROVENANCE="$BUILD_ROOT/backend-build-inputs.json"
"$PYTHON_BIN" -I "$VALIDATOR" inputs \
  --wheel "$RELEASE_WHEEL" \
  --wheel-sha256 "${OPSWITNESS_RELEASE_WHEEL_SHA256:-}" \
  --requirements "$REQUIREMENTS_LOCK" \
  --license-review "$LICENSE_REVIEW" \
  --tauri-config "$TAURI_CONFIG" \
  --mode "$BUILD_MODE" \
  --provenance "$INPUT_PROVENANCE"

"$PYTHON_BIN" -I -m venv "$BUILD_ROOT/venv"
VENV_PYTHON="$BUILD_ROOT/venv/bin/python"

env -u PYTHONHOME -u PYTHONPATH \
  PYTHONNOUSERSITE=1 PYTHONSAFEPATH=1 \
  "$VENV_PYTHON" -I -m pip install \
  --disable-pip-version-check \
  --no-cache-dir \
  --require-hashes \
  --only-binary=:all: \
  -r "$REQUIREMENTS_LOCK"

env -u PYTHONHOME -u PYTHONPATH \
  PYTHONNOUSERSITE=1 PYTHONSAFEPATH=1 \
  "$VENV_PYTHON" -I -m pip install \
  --disable-pip-version-check \
  --no-cache-dir \
  --no-deps \
  --no-index \
  "$RELEASE_WHEEL"

env -u PYTHONHOME -u PYTHONPATH \
  PYTHONNOUSERSITE=1 PYTHONSAFEPATH=1 \
  "$VENV_PYTHON" -I -m pip check

env -u PYTHONHOME -u PYTHONPATH \
  PYTHONNOUSERSITE=1 PYTHONSAFEPATH=1 \
  "$VENV_PYTHON" -I "$VALIDATOR" installed \
  --repository "$REPO_DIR" \
  --requirements "$REQUIREMENTS_LOCK" \
  --tauri-config "$TAURI_CONFIG"

FROZEN_ENTRYPOINT="$BUILD_ROOT/venv/bin/opswitness"
test -x "$FROZEN_ENTRYPOINT"

mkdir -p "$BUILD_ROOT/spec"
cp -P "$PYINSTALLER_SPEC" "$BUILD_ROOT/spec/opswitness.spec"

cd "$BUILD_ROOT/spec"
env -u PYTHONHOME -u PYTHONPATH \
  PYTHONNOUSERSITE=1 PYTHONSAFEPATH=1 PYTHONHASHSEED=0 \
  "$VENV_PYTHON" -I -m PyInstaller \
  --noconfirm \
  --clean \
  --distpath "$DIST_DIR" \
  --workpath "$WORK_DIR" \
  "$BUILD_ROOT/spec/opswitness.spec"

test -x "$DIST_DIR/opswitness-backend/opswitness-backend"
"$PYTHON_BIN" -I "$VALIDATOR" finalize \
  --input-provenance "$INPUT_PROVENANCE" \
  --backend "$DIST_DIR/opswitness-backend/opswitness-backend" \
  --output "$PROVENANCE"
