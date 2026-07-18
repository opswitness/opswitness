# M2 Production Validation

Date: 2026-07-12 America/Los_Angeles (2026-07-13 UTC)

Status: permanent install and live integration passed; register-trigger canary is
running. The 24–48 hour and subsequent seven-day elapsed-time gates are not yet met.

## Installed baseline

- Quarterdeck `0.0.1`, installed by `uv tool` with stable entry at
  `~/.local/bin/qd`.
- Paperclip `2026.707.0`, user npm prefix, absolute Node and `dist/index.js` paths.
- PostgreSQL `17.10` on 127.0.0.1:5432; dedicated `paperclip` role/database.
- age `1.3.1`; private identity outside the encrypted archive, mode 0600.
- `com.quarterdeck.paperclip`, `.projector`, and `.watchdog` installed under launchd.
- `qd doctor --json`: healthy, all checks pass, exactly one Paperclip Node runtime.

No database URL, API key, or token is present in a plist. Config directory is 0700;
config, secrets, and age identity are 0600.

## Disaster recovery

- Production age archive created, mode 0600; decrypted inventory contains PostgreSQL
  custom dump, Paperclip storage/master key, Quarterdeck ledger, and config.
- Restore imported 115 public tables into an operator-created isolated database.
- First drill exposed that `pg_restore` needs explicit `--dbname`; fixed and tested.
- Second drill exposed absolute production paths in restored Paperclip config; restore
  now rebases embedded DB, backup, log, storage, master-key, connection, and port paths.
- Final isolated copy started on 3310: health OK, UI HTTP 200, `fleet` visible. It was
  then stopped and all isolated databases/directories were destroyed.

## Live projector tests

1. Normal: `pilot-echo` projected started/finished, two body ULID markers.
2. Outage: Paperclip stopped; two runs yielded exit 1 and four pending events.
3. Replay: four events replayed, pending returned to zero; sorting Paperclip comments
   by `createdAt` exactly matched local commit order (API defaults newest-first).
4. Lost ack: isolated ledger reconciled two remote body markers with zero reposts.

Pinned Paperclip rejects structured comment metadata from agent API keys (403,
board-only). Projector now writes the human-visible `qd:event:<ULID>` body marker under
the least-privilege service-agent key and continues to read both metadata and body forms.

A full-suite run also exposed one test fixture inheriting the operator's production
`QD_CONFIG_DIR`; it created a synthetic remote `feed-monitor` issue but did not mutate the
authoritative local ledger. The fixture now always redirects `QD_CONFIG_DIR` to its isolated
temporary directory, and the complete suite passes with production services running.

## Canary

- `com.tianyuzhou.register-trigger` plist changed only in `ProgramArguments`; pristine
  `.qd-bak` retained.
- First wrapped run succeeded in 6.636 seconds and projected with zero backlog.
- Only the exact register-trigger label is enrolled. Integration fixture jobs were
  retired through append-only lifecycle events.
- Watchdog: one active schedule, healthy. Digest: full coverage, zero missed, green.

Next gate: observe for 24–48 hours before adopting feed-monitor and sox-monitor. Their
seven-day soak remains mandatory before M2 is called operationally complete.

### Observation checkpoint: 2026-07-13 00:11 PDT

- Elapsed since the first wrapped canary run: about 6.5 hours, so this is evidence only,
  not a gate pass.
- The canary has two successful runs and zero failures; the second run completed at
  `2026-07-13T06:32:24Z`.
- Production status reports six total ledger runs and zero pending projection events.
- The projector recorded the second run as `projected=2 errors=0 pending=0`, followed by
  repeated zero-error, zero-backlog drains.
- The watchdog repeatedly reports that the one active scheduled job is within
  expectations. Its stderr has not grown since the pre-enrollment bootstrap warnings.
- Paperclip scheduled database backups completed hourly from 18:29 through 23:29 PDT; the
  latest observed backup completed successfully.
- An unsandboxed `qd doctor --json` remained fully green with ports 5432/3100 open and one
  matching Paperclip process.

### Permission hardening checkpoint: 2026-07-13 00:32 PDT

- A leaf-mode audit found the Paperclip backup directory at 0755 and its `.sql.gz` files at
  0644. The enclosing `~/.local/share/paperclip` directory was already 0700, so other local
  users had no traversable path, but the leaf permissions violated the portable backup
  invariant.
- Existing backup and log directories/files were tightened to 0700/0600. Exact pre-change
  launchd plists were preserved as `.pre-umask-20260713` rollback copies.
- All four committed service templates now carry launchd `Umask=077`; `qd service exec`
  independently calls `umask(077)` before `execve` as defense in depth.
- The installed Paperclip/projector/watchdog plists were atomically replaced after a diff
  proved the only change was `Umask=077`, and all three passed `plutil -lint`.
- Paperclip restarted cleanly on one new PID; health returned `ok`. `launchctl print`
  reported `umask = 77` for all three services. After reload, projector ran five times and
  watchdog twice with exit code 0; status and digest remained green with zero backlog.
- `qd doctor` now checks actual installed plists, service-log permissions, backup-directory
  and backup-file permissions, in addition to templates. The production result is fully
  green across those new checks.

The creation-mode evidence was then closed without waiting for the hourly timer: the pinned
Paperclip `db:backup` command was exposed through `qd service exec paperclip
--paperclip-mode backup`, which injects `DATABASE_URL` only in-process and inherits the same
077 umask. It created `paperclip-20260713-004017.sql.gz` as mode 0600. A following production
doctor run remained fully green and counted seven secure backup files.

Current verification after permission hardening: 135 tests pass; ruff, mypy, and
full-history gitleaks pass. No secret values were printed or committed.

### Feed/SOX adoption preflight: 2026-07-13 00:52 PDT

The next two soak jobs were prepared without changing either production plist or the
user-owned schedule configuration:

- `com.tianyuzhou.feed-monitor` remains an elapsed-time `StartInterval=1500` job. Its
  source plist SHA-256 is
  `5ae4e5b4a342a25525ec1b3f85e5446f3785bea15108368aff554034b4e77a69`; the dry-run
  changes only the execution entry from `Program=feed_monitor_run.sh` to the stable
  `~/.local/bin/qd wrap --job com.tianyuzhou.feed-monitor -- feed_monitor_run.sh`.
- `com.tianyuzhou.sox-monitor` remains an elapsed-time `StartInterval=21600` job. Its
  source plist SHA-256 is
  `9e41a23df92f141eb5303ec1f507e22d3819d431cf31235cc06f59aaa32c1be6`; the dry-run
  prepends the same stable wrapper to its existing Python `ProgramArguments`.
- Both production plists pass `plutil -lint`; every referenced executable exists, and
  neither job currently has a `.qd-bak`, as expected before first adoption.
- A read-only query of the real GUI launchd domain found both labels loaded with last exit
  status 0. SOX was idle; feed was in a normal scheduled invocation started at 00:52:37 PDT.
  This proves adoption must never boot out or rewrite a target while its PID is active.
- Copies under an isolated `/tmp` directory completed the full
  `--apply -> plutil -lint -> --rollback` sequence. Each rollback reproduced the original
  SHA-256 exactly. No production plist, launchd job, ledger, or schedule file was changed.

After the 24-48 hour canary gate passes, adoption must remain fail-closed and ordered:

1. Confirm each target has no active PID, waiting for a scheduled invocation to finish
   naturally. Then recompute both source hashes, stop on drift, and rerun the dry-run diffs.
2. Apply one plist at a time, lint it, and verify that its pristine `.qd-bak` matches the
   pre-apply hash before reloading the corresponding launchd job.
3. Add only the two exact full labels to the user-owned `schedules.yaml`; do not enroll a
   namespace glob. Run watchdog, status, digest, and projector checks after each job.
4. Any wrapper, coverage, projection, or process-tree anomaly triggers immediate
   `qd adopt launchd LABEL --rollback`, launchd reload, and removal of that label from the
   enrollment list. The seven-day soak clock starts only after both jobs are healthy.

After both exact labels are wrapped, enrolled, idle/healthy, and the independent checks pass,
append the multi-job contract with no historical anchor:

```bash
qd soak start m2-production \
  --job com.tianyuzhou.feed-monitor \
  --job com.tianyuzhou.sox-monitor \
  --minimum-hours 168 \
  --reason "post-canary production adoption"
```

Multi-job evidence begins at the `soak_started` commit. The initial nonzero result must report
pending first-run and duration evidence; it must not be checkpointed as passed. After seven days,
`qd soak status m2-production --json` and all independent M2 checks must pass before
`qd soak checkpoint m2-production` is appended.

### Upgrade maintenance checkpoint: 2026-07-13 12:07 PDT

- Before maintenance, the canary had four successful wrapped runs and zero projection
  backlog. It was idle when inspected.
- Projector, watchdog, gate-recovery, and the sole adopted canary were booted out; a process
  scan found no remaining `qd wrap`, periodic-service, or gated-Claude process before the uv
  environment was replaced.
- The final wheel was installed with the MCP extra. Each original plist was then bootstrapped;
  periodic services were kicked once to establish an explicit runtime baseline.
- Runtime-aware production doctor reported Paperclip running and projector, watchdog, and
  gate-recovery at last exit 0. The canary's `RunAtLoad` invocation became its fifth successful
  ledger run; total indexed runs became nine and projection backlog returned to zero.

The maintenance-triggered fifth run proves upgrade recovery only. It does not replace elapsed
time and does not move the earliest 24-hour canary gate from approximately 17:32 PDT.

### Mail-schema recovery checkpoint: 2026-07-13 15:23 PDT

- At 15:01 PDT, production `config.yaml` gained the default-disabled `mail` block before the
  installed uv tool understood that schema. The old binary failed closed: `qd doctor` was red,
  while projector, watchdog, and gate-recovery each exited 2. Paperclip remained running and
  the ledger stayed intact. Mail was disabled, OAuth was absent, and no mailbox was accessed.
- A threat review then hardened the adapter before installation: every call revalidates the
  pinned gws version, encrypted credentials, live token, and least-privilege Gmail scope;
  model calls require an explicit consent bit; full gws output is bounded; and the normal
  current 13-tool MCP is structurally separate from the 2-tool mail profile.
- The same maintenance discipline was repeated. There was no active `qd wrap` or
  `qd gated-claude`; projector, watchdog, gate-recovery, and register-trigger were booted out;
  the committed wheel at `ee2499a` was installed with the MCP extra; then all four original
  plists were bootstrapped and the three periodic services were kicked once.
- Installed MCP enumeration returned exactly 11 ops tools and exactly 2 mail tools. Production
  doctor returned healthy; all four launchd jobs reported last exit 0; canary run 6 succeeded at
  15:23:39 PDT; indexed runs became 12; projection backlog returned to zero; watchdog reported
  all active jobs within expectations; and the 24-hour digest was healthy.
- A secret-safe Paperclip database backup and an age-encrypted full-instance backup were created
  after recovery. Both output files are mode `0600`.

The 15:01-15:23 observability interruption invalidates continuous-soak evidence even though no
ledger event was lost. The 24-hour canary clock therefore restarts at 2026-07-13 15:23 PDT; the
earliest admissible gate is 2026-07-14 15:23 PDT. Tests and earlier successful runs cannot replace
that elapsed time.

### Machine-enforced canary contract: 2026-07-13 15:53 PDT

- Commit `5ddcc5f` adds ADR-0006 and `qd soak start/reset/status/checkpoint`. The verdict freezes
  each job's interval/grace and recomputes elapsed time, every cadence boundary, terminal and
  degraded evidence, schedule drift, torn lines, lifecycle state, and projection backlog from the
  authoritative ledger. A checkpoint is only an audit snapshot; it cannot make a gate pass.
- Production event `01KXETZM2A7BXN7D4Z54MF7RH0` (`soak_started`) defines `m2-canary` for
  `com.tianyuzhou.register-trigger`, minimum 86400 seconds, frozen interval 21600 seconds plus
  4320 seconds grace. It is anchored to verified successful run
  `01KXES8445NZP2KAVFY6BD859S`, whose `run_started` timestamp is
  `2026-07-13T22:23:32.485475+00:00` (15:23:32 PDT).
- The first `qd soak status m2-canary --json` returned exit 1, `state=pending`, one success,
  zero failures, zero projection backlog, and exactly one blocker: `minimum_duration`. This is the
  required non-green result before elapsed time completes.
- The contract was appended with the repository venv. The production uv tool and all launchd
  jobs were left running and unchanged: no install, bootout, bootstrap, or kickstart occurred.
  A post-append production doctor remained healthy; Paperclip remained a single instance; ledger
  run count remained 12 and projection backlog remained zero.

The machine gate cannot pass before 2026-07-14 15:23:32 PDT. At that time it is still only the
elapsed canary gate: doctor, digest, watchdog, projector, backup, and the remaining M2 acceptance
checks must pass independently before adopting feed-monitor or sox-monitor.

### Post-canary upgrade rehearsal: 2026-07-13 20:59 PDT

- Current commit `428deef` was built and installed into isolated uv tool/bin directories under
  `/private/tmp`; the production uv tool, launchd services, canary, configuration, and ledger were
  unchanged. The isolated binary exposes both `qd soak` and `qd console` and completed
  `qd wrap --job current-wheel-first-run -- /usr/bin/true` with exit 0, no degraded event, and a
  0.123-second ledger run.
- A deliberately shared console state directory was rejected by the single-instance lease. With
  an isolated `QD_CONSOLE__STATE_DIR`, the wheel served `127.0.0.1:18765`; `/api/health` returned
  `status=ok, exposure=loopback`, and the packaged JS/CSS assets both returned HTTP 200. The
  isolated server was then shut down cleanly.
- Real-user-domain `qd doctor --json` has exactly one failing check:
  `qd_command_surface`, because the intentionally stale production uv tool lacks `soak` and
  `console`. All dependencies, permissions, templates, installed services, runtime states, ports,
  credential boundaries, backup target, and Paperclip single-instance checks pass.
- Feed/SOX source hashes still exactly match the locked preflight values above, both plists pass
  `plutil -lint`, and both current dry-run diffs remain limited to prepending the stable wrapper.
  SOX was idle with last exit 0. Feed was in a normal interval invocation with last exit 0, proving
  again that the real adoption must wait for an idle-PID window rather than interrupting it.
- Independent pre-gate checks also pass: status reports 13 ledger runs and zero pending
  projections; watchdog reports its one active canary within expectations; the 24-hour digest is
  healthy with eight runs, zero problems, and zero missed runs; a projector drain is empty; and
  the encrypted-backup dry-run finds Paperclip state, the ledger, CAS, and configuration inputs.
  These checks reduce checkpoint risk but do not satisfy the remaining wall-clock duration.
- An isolated `QD_CONFIG_DIR` bootstrap against the real LaunchAgents also exposed a stale but
  non-authoritative production `schedules.generated.yaml` last written on July 12. The current
  parser correctly recognizes register-trigger as wrapped with the current plist hash and also
  discovers gate-recovery plus two newer candidate jobs. The user-owned enrollment file remains
  exact-label-only and unchanged, so no task was silently enrolled and the canary's frozen
  interval/grace semantics are unchanged. Evaluate the canary first; then, inside the quiesced
  post-canary maintenance window, run current-HEAD `qd init` once to regenerate the machine-owned
  file and rerun watchdog/status/digest. Do not use this derived-file refresh to reset or backdate
  soak evidence.

### Natural cadence checkpoint: 2026-07-13 21:24 PDT

Launchd performed the second post-contract register-trigger invocation without a manual kick.
`launchctl` reports `runs=2`, idle state, and last exit 0. Ledger run
`01KXFDVGNHMYG3Z2P9HZ097M0R` completed `succeeded`, exit 0, in 7.407 seconds. The recomputed soak
verdict has two starts, two successes, zero failures/running runs, zero projection backlog, and a
21,606.956-second maximum gap against the frozen 25,920-second limit. Its only blocker remains
`minimum_duration` (64,756.646 seconds at the checkpoint); no checkpoint event was appended.
