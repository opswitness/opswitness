# Community Alpha Quickstart

OpsWitness `v0.1.0-alpha.1` is a local-first, single-operator release candidate. Use synthetic or
non-critical work first. The seven-day durability soak required for Stable has not completed.

## Requirements

- macOS 14 or newer;
- Python 3.12 exactly;
- `uv` installed;
- a loopback browser for the default console;
- AionUi and Paperclip only when you want the full team-execution and governance path.

Linux runs the tested core in CI but is not a supported launchd or desktop-console target in Alpha.

## Install from GitHub Release

PyPI is intentionally disabled for this release.

```bash
uv tool install --with mcp \
  https://github.com/opswitness/opswitness/releases/download/v0.1.0-alpha.1/opswitness-0.1.0a1-py3-none-any.whl
opswitness version
qd version
```

Both version commands must report `0.1.0a1`. `qd` is the compatibility CLI and invokes the same
entry point.

## First local evidence run

```bash
opswitness init
opswitness wrap --job hello -- sh -c 'printf "hello from OpsWitness\\n"'
opswitness runs
opswitness status
```

This path needs no Paperclip service. The wrapped command's exit status is mirrored and its execution
evidence is appended locally. Do not put secrets in command arguments.

## Open the Workforce console

```bash
opswitness console serve --open
```

The default listener is `http://127.0.0.1:8765`. Describe a goal in Workspace, review the proposed
team and immutable plan hash, then confirm. Full AionUi execution and Paperclip governance require
their separately documented local setup; planning must fail closed rather than silently use another
runtime.

## Existing Quarterdeck installation

Do not copy or rename data manually. If only the old configuration/state roots exist, OpsWitness
continues using them in place. If both old and new roots exist, startup fails until the operator
resolves the ambiguity. Canonical `OPSWITNESS_*` variables and compatibility `QD_*` variables may not
carry conflicting values.

New services use `com.opswitness.*`. Existing `com.quarterdeck.*` services remain supported, but the
same old and new service must not run together. Run `opswitness doctor` before changing services.

## Before real work

Read [Support matrix](SUPPORT-MATRIX.md), [Known limitations](KNOWN-LIMITATIONS.md), and
[Readiness](READINESS.md). Keep Gmail and Telegram disabled until their explicit consent and secret
setup are complete. Use the backup/restore drill before adopting important jobs.
