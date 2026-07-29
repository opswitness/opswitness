# Changelog

All notable public changes are documented here. Versions follow Semantic Versioning for tags and
PEP 440 for Python package metadata.

## [0.1.0-alpha.2] - Unreleased

### Added

- planning failures remain in the same Workspace conversation: the failed attempt stays immutable,
  the prior objective returns to the composer for editing, and an approved retry creates a child
  request instead of a new root task;
- retained planning attempts render above the current turn, with scroll position preserved while
  the App refreshes in the background;
- retry provenance binds the root conversation, parent request, prior Plan, request hash and
  attachment manifest without rewriting the failed attempt or silently adding new files.

### Release boundary

- this behavior is verified in source tests but is not present in the public alpha.1 DMG;
- alpha.2 remains unreleased until an exact rebuilt App passes the vendored-runtime redistribution
  gate, clean installation, first-Work acceptance, recovery checks and a new executable canary.

## [0.1.0-alpha.1] - 2026-07-27

### Added

- local-first Workspace planning and hash-bound confirmation;
- task-scoped Agent teams with hierarchy, collaboration contracts, runtime/model selection, rerun,
  independent Work fork, and immutable History;
- AionUi execution with bounded stage/activity observation, inline operator input, approvals, and
  evidence-confirmed pause/continue/stop controls;
- Paperclip governance projection, append-only JSONL ledger, rebuildable SQLite views, CAS artifacts,
  eval and sign-off evidence;
- `opswitness` primary CLI and `qd` compatibility CLI;
- canonical `OPSWITNESS_*` configuration with fail-closed `QD_*` compatibility;
- clean-checkout distribution verification, checksums, build manifest, SPDX SBOM, DCO, gitleaks, and
  GitHub attestation workflow.

### Compatibility

- existing Quarterdeck-only configuration, state, launchd labels, and known Keychain services remain
  usable in place;
- historical ledger events, plan hashes, artifact hashes, and protocol markers are not rewritten;
- the old `quarterdeck` Python import package is not retained because it was never publicly released.

### Not included

- OpenClaw, Work-as-worker/team-of-teams, auditable long-term memory, DeepSeek/Grok execution
  adapters, SaaS, multi-user identity, promoted mobile access, and PyPI publishing. Private HTTPS,
  device pairing, and PWA support remain unadvertised Beta capabilities.
