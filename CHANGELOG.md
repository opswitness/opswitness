# Changelog

All notable public changes are documented here. Versions follow Semantic Versioning for tags and
PEP 440 for Python package metadata.

## [0.1.0-alpha.1] - Unreleased

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
