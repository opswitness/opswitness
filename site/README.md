# OpsWitness public site

This directory is the static source for `opswitness.com`.

The site is intentionally a product, download, installation, support-boundary, and feedback
surface. It does not host the OpsWitness console, accept customer work, or impersonate an online
SaaS. The full console continues to run on the operator's own Mac.

Deployment remains disabled until the repository is public, the signed/notarized DMG and its
supporting checksum/SBOM/manifest assets exist in the inspected Alpha Prerelease, the exact App
candidate passes its canary, the private vulnerability-reporting channel is enabled, and
`PUBLIC_SITE_APPROVED=true` is set for the approved deployment workflow. The source can contain the
direct DMG link because no Pages deployment is allowed before that gate.

The signed updater feed under `/updates/alpha/latest.json` is injected only by the gated Pages
workflow after it verifies the exact prerelease, schema-3 manifest, checksums, and updater signature.
There is intentionally no unsigned placeholder in this source directory.
