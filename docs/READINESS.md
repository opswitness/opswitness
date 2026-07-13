# Quarterdeck Readiness

Snapshot date: 2026-07-12 · This file is a SINGLE current snapshot; all earlier review
text is preserved verbatim under History. ADRs remain the source of design truth;
`INSTALL-PAPERCLIP.md` records the approved M2 procedure. Remaining rollout steps stay
blocked by the current open gates below.

## Current baseline

- M0-M2 are committed through `dede83f`; M2 permanent install and live integration
  executed successfully. The current worktree is the M3 implementation.
- Full suite: 130 tests pass; ruff, mypy, and full-history gitleaks are clean.
- Process-tree signalling no longer executes `pgrep`, recursion, sleeps, or subprocesses
  in a signal handler. The handler writes a self-pipe; the supervisor snapshots
  `(pid, create_time)`, verifies descendants, escalates after 750ms, and emits
  `tree_signal_degraded` when cleanup cannot be proven.
- Watchdog, digest, and bootstrap share one `classify_schedule()` definition.
- Mutable `retired:` config has been removed. `qd retire/unretire --reason` records
  lifecycle events; a post-retirement run becomes `resurrected` and breaks health.
- M1 install readiness is implemented without touching production: structured
  `qd doctor --json`; strict config/secrets permissions; secure `qd service exec`;
  three M2 launchd templates; encrypted backup and isolated restore dry-runs.
- `uv build` succeeds; the wheel was installed into an isolated `/tmp` tool root,
  `qd version` ran, and a packaged watchdog plist rendered and passed `plutil -lint`.
- Permanent Paperclip/Postgres/launchd are installed. `qd doctor` is fully green;
  encrypted backup + isolated restore and the projector four-test matrix pass.
- `com.tianyuzhou.register-trigger` is the sole canary; its pristine `.qd-bak` exists,
  first run succeeded, watchdog/digest are green, and projection backlog is zero.
  Evidence: [M2-VALIDATION.md](M2-VALIDATION.md).
- M3 repository implementation now includes the append-only gate state machine,
  `gated-claude`, Paperclip approval reconciliation, one-shot recovery, and a fourth
  secret-free launchd template. Deterministic spike coverage passes; live Claude auth is
  not available yet. Evidence: [M3-VALIDATION.md](M3-VALIDATION.md).
- M4 repository implementation now includes atomic CAS, artifact lineage/eval/signoff,
  rebuildable indexes, work-product reconciliation, outcome digest, and backup/restore
  coverage. Evidence: [M4-VALIDATION.md](M4-VALIDATION.md) and
  [ADR-0002](adr/0002-artifact-authority.md).

## Open gates (blocking, in order)

1. **Canary elapsed time** — register-trigger must remain healthy for 24–48 hours.
2. **Seven-day soak** — only after the canary passes may feed-monitor and sox-monitor
   be adopted; M2 remains incomplete until seven days pass.
3. **Telegram digest** — not configured in Quarterdeck secrets yet; must be exercised
   during soak without exposing or copying tokens into repo/plists.
4. **M3 live defer** — the machine's Claude Code 2.1.146 is not logged in. A harmless
   real defer -> Paperclip board approval -> resume -> consume -> execute-once drill must
   pass before installing gate recovery.
5. **M4 live projection** — one non-sensitive canary artifact must create exactly one
   reconciled Paperclip work-product and survive a zero-repost second drain.
6. **No git remote** — GitHub Actions CI has never actually run.
7. **Brand gate** before any publish (org name collision, trademark, domain).

## P3 defer contract (implemented; live acceptance pending)

- Non-interactive `claude -p` only; minimum version **v2.1.89** (machine: 2.1.146).
- Hook returns `permissionDecision: "defer"` → run exits with
  `stop_reason=tool_deferred`, carrying `session_id` + `deferred_tool_use`.
- Resume via `claude -p --resume <session-id>`; the same tool call re-fires the hook.
- **Parallel tool calls in one turn: defer is IGNORED** and the call falls into the
  normal permission flow ⇒ the gate always runs `--permission-mode dontAsk`, safe
  tools explicitly allowed, governed tools neither allowed nor asked — an ignored
  defer therefore still denies.
- No long-poll fallback: absence of defer support ⇒ deny. `bypassPermissions` is
  forbidden under the gate.
- Deterministic matrix passes: single defer/resume · parallel two-tool · approval timeout ·
  duplicate resume · one-shot consumption · MCP/hook missing on resume · old Claude
  version · bypassPermissions rejection. Real model execution is blocked by local login.

## Truth split for approvals (P3)

- **Paperclip owns**: approval UI, human identity, workflow state machine.
- **Quarterdeck ledger owns**: the authoritative evidence — request hash,
  tool_use_id, expiry, approval id, decision, decider, resume/consume outcome.
- Paperclip database loss ⇒ pending calls stay denied; every past decision remains
  auditable from the local ledger.

## Next task

Keep register-trigger under observation for 24–48 hours. After the user completes normal
Claude login, run the harmless M3 live acceptance drill. Do not adopt feed-monitor/sox-monitor
or bootstrap gate recovery before their respective gates pass.

---

## History (superseded reviews, retained verbatim for audit)

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

---

## Update 2026-07-12 (through f32ac92)

Landed since the `bc52f96` baseline above (each commit reviewed in-loop):

- `9dba684` projector per-job fail-stop ordering; faithful signal exit semantics
- `6297d6e` adopt dry-run doctrine + watchdog missed-run detection
- `36829d6` fail-closed watchdog for unsupported schedules; atomic plist writes; qd-path/collision gates
- `affe16a` crash-safe backup publish; real config layering (env > secrets > config > defaults)
- `ce8fb89`→`0e3f0f9`→`592f2b6` bootstrap v1→v2→v2.1: candidates-only discovery, full-label
  canonical IDs (immutable under later collisions), strict user-config schema, fsutil gaps
- `bc52f96`→`c42a6f2`→`716c062` digest hardening → coverage-final → coverage v3:
  structured coverage (active-only, full-ledger universe, retired excuse path),
  three-state job marks, unified legacy-schedules validation
- `84a90a4` MCP console surface (6 tools, stdio handshake smoke)
- `1c5b0e6` evidence-based digest + Telegram HTML renderer
- Suite at 79 tests; ruff/mypy/gitleaks green at every commit above.

### Open (unchanged verdicts)

1. **Signal fallback (`9f62656`) is live on the main path** while its deterministic
   rework is tracked: pgrep returncode unchecked (restricted envs return 3), per-level
   5s blocking in a signal handler, PID-reuse race. Not a digest gate; own workstream.
2. **P3 design pivoted to `defer`** (native `permissionDecision: "defer"` confirmed in
   the hooks reference; detailed save/resume semantics + minimum Claude Code version to
   be pinned by the P3 spike; long-poll hook demoted to fallback design).
3. **P4 idempotency corrected**: `externalId` has no unique constraint upstream
   (verified against pinned v2026.707 source) — projection is list-and-reconcile;
   artifact content must be content-addressed (attachment/immutable blob), never a
   mutable local path reference alone.
4. **INSTALL remains NO-GO**: launchd service templates, stable Node/qd absolute paths,
   npm prefix handling, secrets handling, isolated restore drill — unchanged.
