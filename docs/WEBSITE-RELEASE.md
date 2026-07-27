# Public website release boundary

`opswitness.com` is the public product, download, installation, support-boundary, and feedback
surface for OpsWitness. It does not host the full console, accept customer work, or represent the
local application as a multi-user SaaS. A future browser demo may use synthetic data only.

## Source and hosting

- Static source: `site/`
- Custom domain: `opswitness.com`
- Deployment: GitHub Pages from the pinned `public site` workflow
- Deployment gate: repository variable `PUBLIC_SITE_APPROVED=true`

The deployment job is intentionally skipped while the repository remains private or the final
Alpha Release is unavailable. Do not set the approval variable until all of the following are true:

1. the professional confusing-similarity review is complete;
2. the repository is public and Private Vulnerability Reporting is enabled;
3. `v0.1.0-alpha.1` exists as an inspected GitHub prerelease containing the signed and notarized
   `OpsWitness-0.1.0-alpha.1-macos-arm64.dmg`;
4. the exact mounted DMG passes the final clean-machine first-Work smoke;
5. the DNS records for the Pages host are configured and verified.

## Candidate, canary, and promotion

The `release-candidate` workflow runs only by manual dispatch from `main`. It builds the Python
wheel/sdist and then uses that exact wheel for the isolated PyInstaller backend. On an empty
`macos-14` arm64 runner it downloads every sidecar from the immutable URL in the vendor lock,
verifies its raw hash, embeds the updater public key, signs nested code from the inside out,
notarizes and staples the DMG, runs the mounted-DMG clean-home runtime smoke, and uploads an
immutable artifact named with the workflow run ID and attempt. It does not create a tag or release.
The upload step also reports the immutable GitHub artifact ID and SHA-256 transport digest; retain
that digest with the candidate handoff.

The macOS candidate job has an explicit runner contract. It must be native arm64, uses the pinned
`1.88.0-aarch64-apple-darwin` Rust toolchain, declares `rust-version = "1.88"` in the desktop
package, and runs every project Cargo check and build with `--locked`. This is the minimum Rust
line required by the exact dependency lock; the runner's preinstalled default toolchain is never
trusted.

Disk capacity is also a fail-closed release input. Before downloading build inputs, the ephemeral
runner preserves the active Xcode and removes only recognized inactive Xcode bundles plus
rebuildable user caches, then requires at least 24 GiB free in the workspace. It requires 18 GiB
again immediately before Cargo and 8 GiB after compilation for signing, DMG creation, and SBOM
generation. Verified archives are removed after extraction; provisioned vendor trees and
PyInstaller intermediates are removed after the integrity-locked runtime is staged; and all Cargo
outputs except the exact App are removed before signing. The updater is archived directly from
that App, so a second App tree is not created. If any threshold remains unmet, the workflow stops
with an explicit requirement for an arm64 runner with at least 30 GiB free workspace; it never
builds a partial candidate or silently weakens a gate.

After that exact DMG has completed a 24–48 hour cadence and recovery canary plus the clean-install
and first-Work checks, dispatch the fixed `release-canary-observation` workflow on the candidate
commit. Its protected Apple Silicon validation runner requests the closed
observation-plus-five-sources bundle through the fixed restricted-host handoff and uploads
`alpha-canary-observation-<producer-run-id>-<producer-run-attempt>`. It accepts no caller-selected
path or verdict. The bundle must contain the authoritative soak/cadence JSON or secret-free log
summaries, recovery reconciliation, clean-install identity, and first-Work artifact/CAS evidence
defined in [ALPHA-CANARY-EVIDENCE.md](ALPHA-CANARY-EVIDENCE.md).

The producer uses the dedicated `opswitness-alpha-canary` runner group, which must be restricted
to that fixed workflow. It fails closed unless the root-owned host marker matches
`ALPHA_CANARY_HOST_IDENTITY_SHA256` and the `/Users/Shared` handoff is a runner-owned `0700` tree
without ACL grants. A labels-only runner match or an observation's self-reported host digest is
not sufficient.

An `alpha-canary` environment reviewer may then run `release-canary-evidence` with that producer
run identity, exact observation SHA-256, and observation artifact SHA-256. Before either
cross-workflow artifact is extracted, the workflow queries the attempt-specific GitHub API and
requires the protected numeric workflow ID, fixed path, same repository and candidate commit on
`main`, successful conclusion, exact artifact name, and approved API digest. The downloaded ZIP is
hashed again and safely extracted. The workflow has no manual verdict inputs. Its schema-2 sealed
evidence binds the candidate, observation and canary run identities, exact DMG/manifest hashes,
measured checks, embedded sources, and protected host digest. Artifact transport identities remain
an external workflow/API envelope: both sealing and promotion validate them, but schema-2 does not
claim to embed them.

Only then set `PUBLIC_RELEASE_APPROVED=true` and these repository variables to the inspected values:

- `ALPHA_CANDIDATE_RUN_ID`, `ALPHA_CANDIDATE_RUN_ATTEMPT`, and `ALPHA_CANDIDATE_COMMIT`;
- `ALPHA_CANDIDATE_DMG_SHA256` and `ALPHA_CANDIDATE_MANIFEST_SHA256`;
- `ALPHA_CANDIDATE_ARTIFACT_SHA256`;
- `ALPHA_CANARY_RUN_ID`, `ALPHA_CANARY_RUN_ATTEMPT`, and
  `ALPHA_CANARY_EVIDENCE_SHA256`;
- `ALPHA_CANARY_ARTIFACT_SHA256`;
- the protected numeric `ALPHA_CANDIDATE_WORKFLOW_ID`, `ALPHA_OBSERVATION_WORKFLOW_ID`, and
  `ALPHA_CANARY_WORKFLOW_ID` values for the three fixed producer paths;
- the protected `ALPHA_CANARY_HOST_IDENTITY_SHA256` value provisioned on the restricted canary
  host.

Pushing `v0.1.0-alpha.1` invokes the `alpha-release` environment gate. Promotion requires the tag,
`main`, and candidate commit to be identical, downloads the two exact artifacts by run ID,
re-verifies their attempt-specific workflow identities and API/archive digests, re-verifies all
content hashes and verdicts, attests the candidate assets, and creates the prerelease without
rebuilding. A rerun is a distinct candidate because its workflow attempt and artifact digest are
part of the identity.

## Public links

The website exposes only these public actions:

- download the exact Apple Silicon DMG with a **Download Alpha** action;
- open the GitHub prerelease, checksums, SBOM, manifest, attestation, and Quickstart;
- serve the signed Tauri Alpha feed at `/updates/alpha/latest.json`;
- read the support matrix, known limitations, and security policy;
- submit Alpha experience, feature, and bug reports as GitHub issues;
- open GitHub Private Vulnerability Reporting for security reports.

Do not add API-key collection, hosted planning, login, analytics containing customer content, or a
remote console proxy to this site. The ordinary product continues to bind to the operator's own Mac.

## Verification

Before deployment:

```bash
python -m http.server 8088 --directory site
```

Verify desktop and 390px mobile layouts, keyboard access, local assets, HTTPS-only external links,
the exact DMG download, and all feedback routes. The repository tests also validate identity,
the **Download Alpha** wording, local asset presence, image alt text, and HTTPS external links.

The direct DMG URL may exist in `site/` because the Pages deployment itself is fail-closed on
`PUBLIC_SITE_APPROVED=true`. Never set that variable merely because a workflow or ad-hoc build is
green; the inspected GitHub asset, its canary, and every external gate must already be complete.

The update feed is not committed with a placeholder signature. During the gated Pages job, the
workflow downloads `updates-alpha-latest.json`, its updater signature, `SHA256SUMS`, and the
schema-3 manifest from the exact `v0.1.0-alpha.1` prerelease. It verifies their hashes, Developer ID
and notarization evidence, exact archive URL, and signature equality before staging the file at
`site/updates/alpha/latest.json`. Missing or inconsistent release evidence stops deployment.
