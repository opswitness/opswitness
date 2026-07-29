#!/bin/bash
set -euo pipefail

cat >&2 <<'EOF'
ERROR: this one-off alpha.1 publisher is retired.

v0.1.0-alpha.1 and its release assets are immutable. Do not upload with
--clobber, reuse the old temporary App, or replace the public DMG in place.

Prepare v0.1.0-alpha.2 from a clean exact commit through the gated release
workflow after the vendor redistribution lock, clean installation, first Work,
recovery, and executable canary have passed. Switch the website only after the
new prerelease asset and SHA-256 have been independently verified.
EOF

exit 2
