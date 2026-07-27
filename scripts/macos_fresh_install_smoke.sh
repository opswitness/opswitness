#!/usr/bin/env bash
# Mount the final DMG and start the complete packaged runtime in an isolated clean home.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 DMG" >&2
  exit 2
fi

dmg=$1
mount_root=$(/usr/bin/mktemp -d "${RUNNER_TEMP:-/tmp}/opswitness-dmg.XXXXXX")
cleanup() {
  if /usr/bin/hdiutil detach "$mount_root" -quiet; then
    /bin/rm -rf "$mount_root"
  else
    echo "DMG remains mounted for diagnosis: $mount_root" >&2
  fi
}
trap cleanup EXIT

/usr/bin/hdiutil attach "$dmg" -nobrowse -readonly -mountpoint "$mount_root"
app="$mount_root/OpsWitness.app"
if [[ ! -d "$app" ]]; then
  echo "DMG does not contain OpsWitness.app" >&2
  exit 1
fi

executable=$(/usr/libexec/PlistBuddy -c "Print :CFBundleExecutable" "$app/Contents/Info.plist")
smoke_output=$("$app/Contents/MacOS/$executable" --distribution-smoke-test)
printf '%s\n' "$smoke_output"
SMOKE_OUTPUT="$smoke_output" python3 -c '
import json
import os

payload = json.loads(os.environ["SMOKE_OUTPUT"])
assert payload["healthy"] is True
assert payload["resource_inventory"] == "verified"
assert payload["services_started"] is True
assert payload["clean_home"] is True
assert payload["runtime_chain"] == [
    "embedded-postgres",
    "paperclip",
    "aioncore",
    "opswitness-backend",
]
'
echo "mounted-DMG clean-home runtime smoke passed"
