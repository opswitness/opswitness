# OpsWitness macOS desktop shell

This directory contains the Apple Silicon Tauri 2 shell and the deterministic
runtime staging tools for the OpsWitness alpha. Large third-party runtimes are
never checked into Git. They are supplied to `scripts/stage_runtime.sh` from
locally verified inputs or by the release workflow.

The application starts only after every staged resource matches
`resource-manifest.json`. The supervisor binds each service to a dynamically
selected loopback port, launches it with a fixed argument vector, and waits for
its health endpoint before exposing the main window.

## Local ad-hoc build

Prerequisites:

- macOS 14 or newer on Apple Silicon
- native arm64 CPython 3.12.13
- a current Rust toolchain compatible with Tauri 2
- the exact OpsWitness release wheel
- the pinned runtime inputs described by `vendor-lock.json`

Set these paths without placing their contents in the repository:

```sh
export OPSWITNESS_RELEASE_WHEEL=/absolute/path/to/opswitness-0.1.0a1-py3-none-any.whl
# Optional additional binding when the expected digest is already known:
export OPSWITNESS_RELEASE_WHEEL_SHA256=<64-hex-sha256>
export OPSWITNESS_NODE_BIN=/absolute/path/to/node
export OPSWITNESS_PAPERCLIP_DIR=/absolute/path/to/paperclip-package
export OPSWITNESS_AIONCORE_DIR=/absolute/path/to/aioncore-bundle
export OPSWITNESS_CODEX_BIN=/absolute/path/to/codex-aarch64-apple-darwin
desktop/scripts/build_adhoc.sh
```

The backend build creates a temporary isolated virtual environment, installs
build and runtime packages from `python-requirements.lock` with
mandatory hashes, and then installs only the wheel named by
`OPSWITNESS_RELEASE_WHEEL`. The PyInstaller `--onedir` analysis runs from a
temporary staging directory with no repository source path. Its input
provenance is written to `dist/backend-build-provenance.json`.

The remaining steps stage the pinned sidecars, normalize every staged Mach-O to
the supported arm64 slice, write deterministic `architecture-provenance.json`,
then write a complete SHA-256 resource manifest and ask Tauri for an ad-hoc
signed app. The explicit inside-out signer verifies that staged manifest,
signs each nested Mach-O, refreshes the payload hashes, and only then seals the
outer app. A simple DMG with an Applications link is created from that final
app and ad-hoc signed. The provenance and the pre-sign manifest digest are
themselves integrity-locked in the final manifest.
An arm64-only Mach-O is retained byte-for-byte; a universal Mach-O is thinned
with `lipo` to its existing arm64 slice; any Mach-O without arm64 fails the
build, except an Intel-only leaf under an explicit vendor
`prebuilds/<Apple-platform>-<x64-target>/` directory. That narrow alternative
platform prebuild is recorded and excluded while its package directory remains;
an arbitrary x86 Mach-O still fails. This is architecture normalization, not
dependency pruning: no dependency directory or managed arm64 resource is
silently removed. These steps never install launch agents, start the product
services, publish a release, or modify user data.

`OPSWITNESS_VENDOR_MODE=release` is reserved for CI. In that mode every vendor
entry must have an approved redistribution review and an upstream SHA-256. The
backend build additionally requires
`python-backend-license-review.json` to approve every package at the exact
version in the hash lock. The checked-in review is intentionally incomplete,
so public redistribution remains fail-closed until that review and the notices
are completed.
