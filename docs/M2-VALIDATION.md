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

Open evidence: inspect the first automatic database backup created after this restart and
prove it is born as mode 0600. Existing files were corrected, so they cannot prove process
creation semantics by themselves.

Current verification after permission hardening: 134 tests pass; ruff, mypy, and
full-history gitleaks pass. No secret values were printed or committed.
