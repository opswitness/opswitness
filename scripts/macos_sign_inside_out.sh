#!/usr/bin/env bash
# Sign every nested Mach-O before signing the outer application bundle.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 APP_BUNDLE SIGNING_IDENTITY" >&2
  exit 2
fi

app_bundle=$1
identity=$2
if [[ ! -d "$app_bundle" || "$app_bundle" != *.app ]]; then
  echo "expected an existing .app bundle: $app_bundle" >&2
  exit 1
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
manifest_builder="$REPO_DIR/desktop/scripts/make_resource_manifest.py"
symlink_restorer="$REPO_DIR/desktop/scripts/restore_packaged_symlinks.py"
backend_adhoc_entitlements="$REPO_DIR/desktop/entitlements/backend-adhoc.plist"
runtime_root="$app_bundle/Contents/Resources/runtime"
runtime_payload="$runtime_root/payload"
vendor_lock="$runtime_root/vendor-lock.json"
resource_manifest="$runtime_payload/resource-manifest.json"
python_bin=${OPSWITNESS_PYTHON:-python3}

command -v "$python_bin" >/dev/null 2>&1 || {
  echo "selected signing Python does not exist: $python_bin" >&2
  exit 1
}
for required in \
  "$manifest_builder" \
  "$symlink_restorer" \
  "$backend_adhoc_entitlements" \
  "$runtime_payload" \
  "$vendor_lock" \
  "$resource_manifest"
do
  if [[ ! -e "$required" ]]; then
    echo "inside-out signing input is missing: $required" >&2
    exit 1
  fi
done

distribution_mode=$(
  "$python_bin" -I -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["distribution_mode"])' \
    "$resource_manifest"
)
if [[ "$distribution_mode" != "adhoc" && "$distribution_mode" != "release" ]]; then
  echo "runtime manifest has an invalid distribution mode" >&2
  exit 1
fi

# Prove that the copied app resources still match the staged inventory before
# any code signature is changed. The digest is embedded in the post-sign
# manifest so the signed payload remains bound to this pre-sign checkpoint.
"$python_bin" -I "$symlink_restorer" \
  --runtime "$runtime_payload" \
  --manifest "$resource_manifest"
"$python_bin" -I "$manifest_builder" \
  --runtime "$runtime_payload" \
  --vendor-lock "$vendor_lock" \
  --mode "$distribution_mode" \
  --verify-existing
pre_sign_manifest_sha256=$(
  "$python_bin" -I -c \
    'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' \
    "$resource_manifest"
)

sign_path() {
  local candidate=$1
  if [[ "$identity" == "-" ]]; then
    if [[ "$candidate" == "$runtime_payload/backend/opswitness-backend" ]]; then
      /usr/bin/codesign \
        --force \
        --sign "$identity" \
        --options runtime \
        --preserve-metadata=identifier \
        --entitlements "$backend_adhoc_entitlements" \
        "$candidate"
      return
    fi
    /usr/bin/codesign \
      --force \
      --sign "$identity" \
      --options runtime \
      --preserve-metadata=identifier,entitlements \
      "$candidate"
  else
    /usr/bin/codesign \
      --force \
      --sign "$identity" \
      --options runtime \
      --timestamp \
      --preserve-metadata=identifier,entitlements \
      "$candidate"
  fi
}

declare -a mach_o_files=()
while IFS= read -r -d '' candidate; do
  if /usr/bin/file -b "$candidate" | /usr/bin/grep -q "Mach-O"; then
    mach_o_files+=("$candidate")
  fi
done < <(/usr/bin/find "$app_bundle/Contents" -type f -print0)

# Files are leaves in the signing graph. Nested bundles are then signed from the
# greatest path depth outward, followed by the outer application. The recursive
# signing shortcut is forbidden because it hides omissions in this inventory.
if (( ${#mach_o_files[@]} > 0 )); then
  for candidate in "${mach_o_files[@]}"; do
    sign_path "$candidate"
  done
fi

declare -a nested_bundles=()
while IFS= read -r -d '' candidate; do
  nested_bundles+=("$candidate")
done < <(
  /usr/bin/find "$app_bundle/Contents" -depth -type d \
    \( -name "*.framework" -o -name "*.xpc" -o -name "*.appex" -o -name "*.app" \) \
    -print0
)

if (( ${#nested_bundles[@]} > 0 )); then
  for candidate in "${nested_bundles[@]}"; do
    sign_path "$candidate"
  done
fi

# Code signatures change Mach-O bytes. Refresh the complete payload inventory
# after every nested signature and before sealing the outer application.
"$python_bin" -I "$manifest_builder" \
  --runtime "$runtime_payload" \
  --vendor-lock "$vendor_lock" \
  --mode "$distribution_mode" \
  --post-sign \
  --pre-sign-manifest-sha256 "$pre_sign_manifest_sha256"

sign_path "$app_bundle"

/usr/bin/codesign --verify --strict --verbose=2 "$app_bundle"
echo "inside-out signing completed for $app_bundle"
