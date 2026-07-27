# Community Alpha Quickstart

OpsWitness `v0.1.0-alpha.1` is a local-first, single-operator release candidate. Use synthetic or
non-critical work first. Stable durability and an SLA are not included.

## Install the Mac app

The supported first-user path is the signed and notarized Apple Silicon application:

1. Download `OpsWitness-0.1.0-alpha.1-macos-arm64.dmg` from the inspected GitHub prerelease.
2. Compare its SHA-256 with `SHA256SUMS`, then open the DMG.
3. Drag **OpsWitness** into **Applications** and open it.
4. Complete the local checks, then choose either Codex or Anthropic when prompted. Codex uses the
   official ChatGPT sign-in flow; Anthropic requires your own API Key.
5. Review and run **Reply to Your First Customer**.

The App contains its compatible Python, Node, Paperclip/PostgreSQL, AionCore, Codex CLI, and Claude
Agent runtime components. A first-time user does not install those dependencies separately. An
Anthropic API Key is validated and stored in this Mac's Keychain; its API usage is billed separately
from Claude Pro/Max, whose subscription login is not routed by OpsWitness. The App needs macOS 14 or
newer, Apple Silicon, at least 5 GB of free space during setup, and internet access for provider
authentication.

The first Work uses a fixed, fictional website-maintenance inquiry and an App-managed empty
workspace. A Business Assistant creates a careful local reply draft in `first-work.json`; a Review
Assistant checks unsupported price and start-date commitments and records the draft digest in
`verification.json`. The workflow has no delivery step. The App asks for one single-use approval
for each local save (normally two approvals); reject any other request. It then verifies both
artifacts from the content-addressed store. Passing this demonstration means only:

> Synthetic customer-reply demonstration passed; no real customer or business outcome was
> evaluated.

## Existing OpsWitness or Quarterdeck data

Do not copy or rename data manually. If the App detects an existing installation, choose either
**Import a copy** or **Start fresh**. Import first writes a manifest and backup, leaves the old
directory untouched, and never silently merges old and new services.

The App stores new data under `~/Library/Application Support/OpsWitness/` and logs under
`~/Library/Logs/OpsWitness/`. App-managed services do not install launchd jobs and must not share
their instance IDs or ports with an older installation.

## Command-line distribution

Wheel and source archives remain available for developers and existing CLI users. They are not the
new-user Mac installation path. PyPI is intentionally disabled for this Alpha.

```bash
uv tool install --with mcp \
  https://github.com/opswitness/opswitness/releases/download/v0.1.0-alpha.1/opswitness-0.1.0a1-py3-none-any.whl
opswitness version
qd version
```

Both version commands must report `0.1.0a1`. CLI installations keep the documented Python 3.12 and
external-runtime boundaries; they do not silently borrow sidecars from the Mac App.

## Before real work

Read [Support matrix](SUPPORT-MATRIX.md), [Known limitations](KNOWN-LIMITATIONS.md),
[Vendored runtimes](VENDORED-RUNTIMES.md), and [Readiness](READINESS.md). Keep integrations disabled
until their explicit consent and secret setup are complete. Back up important work and retain an
independent recovery path.
