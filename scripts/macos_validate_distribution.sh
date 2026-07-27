#!/usr/bin/env bash
# Validate architecture, explicit nested signatures, Gatekeeper, and notarization.
set -euo pipefail

if [[ $# -lt 4 || $# -gt 5 ]]; then
  echo "usage: $0 APP_BUNDLE DMG MODE OUTPUT_JSON [NOTARY_JSON]" >&2
  exit 2
fi

app_bundle=$1
dmg=$2
mode=$3
output_json=$4
notary_json=${5:-}

if [[ "$mode" != "ad-hoc" && "$mode" != "developer-id" ]]; then
  echo "mode must be ad-hoc or developer-id" >&2
  exit 2
fi

build_path_prefixes=("/Users/runner/" "/home/runner/" "/builds/")
for variable_name in GITHUB_WORKSPACE RUNNER_TEMP RUNNER_TOOL_CACHE HOME; do
  value=${!variable_name:-}
  if [[ -n "$value" && "$value" != "/" ]]; then
    build_path_prefixes+=("${value%/}/")
  fi
done

while IFS= read -r -d '' candidate; do
  if /usr/bin/file -b "$candidate" | /usr/bin/grep -q "Mach-O"; then
    archs=$(/usr/bin/lipo -archs "$candidate")
    if [[ " $archs " != *" arm64 "* || " $archs " == *" x86_64 "* ]]; then
      echo "non-arm64-only Mach-O: $candidate ($archs)" >&2
      exit 1
    fi
    /usr/bin/codesign --verify --strict --verbose=2 "$candidate"
    for prefix in "${build_path_prefixes[@]}"; do
      if LC_ALL=C /usr/bin/grep -aFq "$prefix" "$candidate"; then
        echo "build-machine absolute path embedded in $candidate" >&2
        exit 1
      fi
    done
  fi
done < <(/usr/bin/find "$app_bundle/Contents" -type f -print0)

/usr/bin/codesign --verify --strict --verbose=2 "$app_bundle"

metadata_args=(
  --app "$app_bundle"
  --output "$output_json"
  --mode "$mode"
)
if [[ "$mode" == "developer-id" ]]; then
  /usr/sbin/spctl --assess --type execute --verbose=2 "$app_bundle"
  /usr/sbin/spctl --assess --type open --context context:primary-signature --verbose=2 "$dmg"
  /usr/bin/xcrun stapler validate "$dmg"
  metadata_args+=(--stapled --gatekeeper-accepted)
  if [[ -z "$notary_json" ]]; then
    echo "developer-id validation requires notarytool JSON" >&2
    exit 1
  fi
fi
if [[ -n "$notary_json" ]]; then
  metadata_args+=(--notary-json "$notary_json")
fi

/usr/bin/python3 "$(dirname "$0")/macos_write_signing_metadata.py" "${metadata_args[@]}"
echo "macOS distribution validation completed"
