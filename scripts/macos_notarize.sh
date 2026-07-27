#!/usr/bin/env bash
# Submit a Developer-ID-signed DMG, staple the accepted ticket, and emit JSON.
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 DMG KEYCHAIN_PROFILE OUTPUT_JSON" >&2
  exit 2
fi

dmg=$1
profile=$2
output_json=$3
if [[ ! -f "$dmg" ]]; then
  echo "DMG does not exist: $dmg" >&2
  exit 1
fi
if [[ -z "$profile" ]]; then
  echo "a notarytool keychain profile is required" >&2
  exit 1
fi

/usr/bin/xcrun notarytool submit "$dmg" \
  --keychain-profile "$profile" \
  --wait \
  --output-format json >"$output_json"

/usr/bin/python3 -c \
  'import json,sys; p=json.load(open(sys.argv[1])); assert p.get("status") == "Accepted", p' \
  "$output_json"
/usr/bin/xcrun stapler staple "$dmg"
/usr/bin/xcrun stapler validate "$dmg"
echo "notarization accepted and ticket stapled"
