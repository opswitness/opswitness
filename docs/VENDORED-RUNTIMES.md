# Vendored macOS runtimes

The macOS application is an offline-capable distribution channel. It bundles only the pinned
runtime versions recorded in [`desktop/vendor-lock.json`](../desktop/vendor-lock.json); the Python
wheel and source distribution remain independent and do not contain these runtimes.

## Release rule

Every downloaded runtime entry must have an immutable HTTPS artifact URL, a lowercase SHA-256, a
license identifier, a notice, and an approved redistribution review. The lock target fixes the
architecture to `aarch64-apple-darwin`. Its `provision` object also fixes the archive type,
extraction root, output kind, entrypoint, and paths that must exist after extraction. Release CI
downloads those archives into a new runner directory, checks the raw hashes, safely extracts them,
and exports only the resulting paths. Repository variables cannot substitute local runtime paths.

The App SPDX 2.3 SBOM must inventory the extracted runtime tree, including native Node modules,
PostgreSQL executables, dynamic libraries, Python packages, and managed AionCore resources.

The lock intentionally leaves unresolved artifacts with a `null` hash, `provision: null`, or a
`blocked` review. This keeps local/ad-hoc development possible while making a signed public
candidate fail closed. Replace each placeholder only with evidence for the exact artifact. Do not
replace a release URL with a project page or a mutable `latest` URL.

## Frozen Python backend

The PyInstaller backend is first-party, but it contains third-party CPython and package code. Its
release inputs are therefore separately bound:

- CPython is exactly `3.12.13` arm64 from the immutable
  `python-build-standalone` `20260510` release. Candidate CI downloads the locked install-only
  archive, verifies its raw SHA-256, extracts it into a private ephemeral directory, and confirms
  the executable and every packaged native object are arm64 before it can build the backend.
- `desktop/python-requirements.lock` contains exact `name==version` pins and wheel hashes for the
  complete build, OpsWitness runtime, and MCP graph.
- `desktop/python-backend-license-review.json` must cover every locked package at the exact version.
- `OPSWITNESS_RELEASE_WHEEL` must be the one wheel built earlier in the same candidate run. The
  backend builder installs it with `--no-index --no-deps` in an isolated environment and keeps the
  repository source tree off the PyInstaller import path.
- `backend-build-provenance.json` records the interpreter, wheel digest, dependency-lock digest,
  license-review digest, and source-isolation result and becomes a release asset.

The checked-in Python runtime and package redistribution reviews remain blocked. A reviewer must
complete the notices and license file before changing those statuses to `approved`; merely having a
complete SPDX inventory is not approval.

The pinned AionCore `0.1.45` payload from AionUi Web `2.1.33` currently embeds an absolute
`/Users/runner/.cargo/...` build-machine path. It therefore cannot pass the distribution
no-build-machine-path validator even though its archive digest matches the lock. Public candidate
creation remains blocked until the vendor supplies a clean payload or an explicit product decision
changes both the artifact and its reviewed evidence; the validator must not waive this finding.

Alpha.2 has exactly two redistribution-driven, vendor-locked staging exceptions:

- AionCore's exact Claude Agent ACP `0.58.1` managed-resource subtree is removed and replaced by
  the recorded first-party fail-closed compatibility shim required for AionCore startup.
- Paperclip's exact Claude Agent ACP `0.52.0` subtree, its nested proprietary Claude Agent SDK
  `0.3.191`, the separate native arm64 SDK package, and the companion `.bin` symlink are removed.
  Paperclip's MIT adapter packages and MIT `@anthropic-ai/sdk` remain because the server imports or
  declares them in its production tree. The App disables Paperclip's heartbeat scheduler, creates
  and reconciles only its exact inert `process` service Agent, and does not expose Claude. Payload
  removal is still not described as a global sandbox against arbitrary external clients, imported
  Paperclip data, or a host-installed provider runtime.

Both transforms run only after the complete pinned source payload is copied, reject any version,
tree, marker, link, or native-binary digest drift, and write separate receipts that the final
resource manifest integrity-locks. No other production dependency or managed resource may be
trimmed without its own vendor-lock policy, clean-machine Work, and license/SBOM comparison.
Redistribution review therefore remains blocked.

## arm64 architecture normalization

After the runtime payload is copied and before `resource-manifest.json` is generated, staging
scans every regular Mach-O without following symlinks. An arm64-only object is retained as-is; a
universal object containing arm64 is thinned with `lipo` to exactly its existing arm64 slice. A
Mach-O without arm64 stops the build, with one narrow, auditable exception: an Intel-only leaf
inside a literal `prebuilds/darwin-x64`, `prebuilds/ios-x64-simulator`, or another exact Apple
`prebuilds/<platform>-<x64-or-32-bit-Intel-target>` directory may be excluded. The parent package
and dependency directories remain; a similarly named or arbitrary x86 Mach-O is never excluded.
Staging writes deterministic `architecture-provenance.json` in the payload with the relative path,
pre/post architectures, pre/post SHA-256, and explicit exclusion action for every Mach-O. The final
resource manifest integrity-locks that provenance file, records its digest explicitly, and rejects
a provenance exclusion that still exists in the payload.

Architecture normalization is separate from the two earlier Codex-only staging filters. After
those filters have produced their integrity-bound receipts, normalization preserves all remaining
package/dependency directories, arm64/universal resources, and AionCore managed resources. Only
the explicit non-arm vendor-prebuild Mach-O leaf exception above is removed at this stage, with
provenance; it does not use `codesign --deep` as a substitute for the explicit signing inventory.

## Update discipline

A runtime update is a release change. Update the lock, third-party notices, complete App SBOM,
mounted-DMG smoke test, and 24–48 hour executable canary together. A newer locally installed
Paperclip, AionUi, Node, PostgreSQL, or Codex CLI must never override the bundled version.

The signed candidate workflow writes its workflow run ID and attempt into the schema-3 manifest.
Canary evidence binds that identity, the commit, DMG hash, and manifest hash. The tag promotion
workflow downloads those exact artifacts and evidence by run ID and never rebuilds them.
