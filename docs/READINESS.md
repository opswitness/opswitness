# Quarterdeck Readiness

Date: 2026-07-12
Status: local P2 code is usable for controlled development; permanent installation is **NO-GO**.

This document is the current readiness snapshot. ADRs remain the source of truth for design
decisions, while `INSTALL-PAPERCLIP.md` remains a proposed runbook and must not be executed
until every gate below is closed.

## Verified Baseline

Snapshot reviewed at commit `bc52f96`:

- `62 passed` on macOS, including the process-tree test outside the restricted sandbox.
- Ruff, mypy, and full-history gitleaks checks pass.
- The working tree was clean at review time.
- No real launchd plist was adopted and no `.qd-bak` existed under `~/Library/LaunchAgents`.
- `qd wrap` records start/finish evidence without requiring Paperclip.
- Projector replay, per-job fail-stop ordering, reconciliation, and local disposable indexing
  are covered by tests; live Paperclip integration remains an installation gate.
- `qd digest` now distinguishes execution evidence from outcome evidence, includes traceable
  run IDs for problems, reports missing watchdog configuration as unavailable, and exits 1
  for an unhealthy report.

## Digest Gaps

The digest hardening is substantially complete, but two trust semantics remain:

1. Watchdog coverage is currently a boolean based on whether `schedules.yaml` exists. It must
   become a structured result covering missing, empty, malformed, unsupported, partial, and
   observed-but-unregistered jobs. A file that covers one job must not make an otherwise
   uncovered fleet green.
2. A running-only job is currently rendered with a success mark. Running is neutral, not
   successful; rendering and tests need a three-state result: healthy, running-neutral, and
   problem.

Telegram HTML delivery also needs a bounded-field or HTML-aware fallback for a single dynamic
line longer than the chunk limit.

## Bootstrap Findings

`qd init` is not ready as the default first-run path. A read-only, isolated-config run against
the actual default `~/Library/LaunchAgents` produced:

```text
41 jobs discovered, 39 added, 28 calendar (fail-closed)
```

Running watchdog immediately afterward produced 39 alerts, including third-party updaters,
application login items, and gateway services that are not part of the intended fleet. The
reported nine-job smoke used the explicit plist-copy directory under `trade/usstock`, not the
default first-run directory.

Required bootstrap v2 changes:

- Discover candidates automatically, but require one explicit selection/acceptance before
  activating monitoring. Third-party and unscheduled services stay candidates by default.
- Use the full launchd label as the canonical identity. Short-name collisions such as
  `gateway` and `wake` must fail closed rather than silently dropping one source.
- Distinguish interval, calendar, and unscheduled/service plists.
- Split generated state from user overrides, for example `schedules.generated.yaml` plus a
  user-owned `schedules.yaml`. Never rewrite the user file, its comments, or unknown fields.
- Use atomic writes and a single-init lock; report invalid YAML and source drift without
  clobbering either file.
- Add fixtures for the real 41-entry shape, collisions, empty discovery, invalid YAML,
  concurrent init, and user override preservation.

Future grace learning must use schedule-start lateness or inter-arrival residuals derived from
`run_started`, not `p95 duration * 2`. Automatic policy changes require bounded deltas, an audit
event, provenance, and rollback. Permission relaxation remains proposal-only.

## Installation Blockers

`docs/INSTALL-PAPERCLIP.md` is not approved for execution. Before permanent installation:

- Commit and validate the three claimed launchd templates; the referenced `templates/`
  directory does not currently exist.
- Define a stable Quarterdeck installation path. There is no global `qd`; only the repository
  virtualenv currently provides it.
- Install pinned Paperclip into a user-owned prefix. The current global npm prefix targets a
  root-owned module directory.
- Launch Paperclip with an absolute Node executable and absolute `dist/index.js`; its
  `#!/usr/bin/env node` entrypoint cannot rely on launchd PATH.
- Keep the PostgreSQL password out of launchd plists. Store secrets only in permission-checked
  `0600` files or another explicit secret provider.
- Enforce the config contract: consistent API-key precedence, reject insecure
  `secrets.yaml` permissions, and reject secret fields in non-secret `config.yaml`.
- Use `PAPERCLIP_HOME` or `--data-dir`, not the nonexistent `PAPERCLIP_DATA_DIR`, for an
  isolated restore rehearsal. Restore into a separate database and alternate API port.
- Add the missing encrypted-backup prerequisite (`age` is not currently installed) and prove
  a coordinated database plus instance-file restore.
- Keep fault injection inside an isolated ledger and test company. Never edit the authoritative
  append-only ledger.
- Revalidate and gracefully stop the previously observed sandbox embedded-Postgres process
  before cleanup; do not trust a stale PID without checking its command line.

## Release Gates

1. **Digest coverage-final**: structured coverage, uncovered-job reporting, neutral running
   state, and regression tests.
2. **Bootstrap v2**: candidate discovery, explicit acceptance, canonical identities,
   generated/user split, and atomic merge behavior.
3. **Install-readiness final**: stable binaries, committed plist templates, secure secrets,
   schedules, isolated backup/restore script, and `plutil -lint` coverage.
4. **Explicit operator approval**: only after gates 1-3 pass may the runbook touch the real
   HOME, PostgreSQL, or launchd configuration.
5. **Canary and soak**: one non-critical job for 24-48 hours, then feed-monitor and sox-monitor
   for seven days before calling P2 operationally ready.

## Next Task

Implement digest coverage-final only. Keep installation and real plist/config writes disabled.
After that, implement bootstrap v2 as a separate, reviewable commit.
