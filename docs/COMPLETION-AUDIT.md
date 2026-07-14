# Quarterdeck Completion Audit

Snapshot: 2026-07-13 20:25 PDT. This document maps the approved M0-M6 plan to evidence and
remaining gates. [READINESS.md](READINESS.md) remains the single operational snapshot.

## Requirement matrix

| Milestone | Current evidence | Verdict |
|---|---|---|
| M0 trusted baseline | Process-tree supervisor, shared schedule classification, append-only lifecycle, full tests | Complete |
| M1 install and recovery tooling | Doctor, secure service exec, encrypted backup/isolated restore, five secret-free launchd templates | Complete in source |
| M2 permanent install and soak | Postgres/Paperclip/services installed; live matrix, recovery, doctor checks and canary ledger contract exist | In progress: elapsed canary, stable-tool upgrade, then seven-day soak |
| M3 Claude gate | Two live defer/approval/resume/consume drills and 60-second recovery service | Complete for non-interactive `qd gated-claude` only |
| M4 artifact/eval/signoff | Atomic CAS, ledger authority, live projection/reconciliation and restore evidence | Complete |
| M5 open-source v0.1 | CI/release/SBOM/provenance code, tracked-only distribution verification, showcase, wheel and first-run evidence exist | Blocked by brand decision and real Git remote/Actions |
| M6 paid practitioner Pilot | Offer, privacy contract, technical boundary and success criteria exist | Blocked by written paid commitment/deposit; product code intentionally absent |
| Local total console | Dashboard, Plan Mode architecture drafting, hash-bound confirmation, atomic dispatch/recovery, fixed-error privacy boundary, single-instance lease, per-request private AionUi workspaces, responsive UI and packaged assets | Complete in source; stable install/KeepAlive service waits for canary maintenance window |

## Live evidence at this snapshot

- Current-HEAD `qd soak status m2-canary --json`: `pending`; only blocker is
  `minimum_duration`, with 68,289 seconds remaining at 20:25 PDT. The tracked job has one start,
  one success, zero failures, and zero projection backlog since the reset contract.
- Current-HEAD `qd status`: 13 total runs and zero pending projections. The third independently
  clicked AionUi one-click workflow run (`01KXF2VC2NGNK7NFKEXWEBWZEY`) exited 0 without degraded
  evidence.
- Current-HEAD watchdog: all one active scheduled jobs within expectations.
- Current-HEAD digest: green, complete coverage, zero missed runs; execution and outcome evidence
  remain separated.
- Real launchd: Paperclip is running as one instance; projector, watchdog, gate-recovery, and
  register-trigger all have latest exit code 0.
- Current-HEAD doctor correctly returns non-green for one reason only: the stable installed qd
  lacks `soak` and `console`. The older installed doctor cannot detect its own drift.
- Real-browser total-console acceptance passed at desktop and 390x844 mobile widths. The mobile
  document had no horizontal overflow, the current four-agent plan exposed every planning field,
  and its dispatch button remained fail-closed unless the separate confirmation checkbox was
  actively selected. No plan was dispatched during this acceptance.
- Total-console health now uses the same fail-closed coverage/watchdog/outcome rules as the digest
  over one ledger snapshot. The live metric is `1/1 完整覆盖`; successful historical or on-demand
  runs no longer inflate the number of actively monitored jobs.
- Approval counts are also fail-closed: only a successful Paperclip query may display zero.
  Unavailable approval state is rendered separately as unknown/attention rather than “no pending
  approvals.”
- Plan startup recovery resumes only safe `confirmed` work through one atomic dispatch claim,
  refreshes active work without replay, and fails ambiguous `planning`/`dispatching` states closed.
  Concurrent confirmation/dispatch and corrupt-record tests pass within the 252-test suite.
- Commit `93c8bbb` gives every AionUi planning or mail request a unique `0700` workspace and makes
  confirmed Team plus workspace cleanup part of successful return. The source console restarted
  cleanly on port 8765; its only plan remained `ready` with the same timestamp, the confirmation
  checkbox was false, the run button was disabled, and the browser logged no warnings or errors.
  No planning request, mail access, or execution was triggered during this acceptance.
- Crash recovery now fsyncs a private marker before Team creation and reconciles only an exact
  AionUi workspace/name/optional-ID match under the console lease, with append-only started/failed/
  finished evidence. A real isolated probe deliberately left its Team ID unbound to simulate the
  POST-response crash window; startup recovery deleted exactly one matching Team and its workspace,
  confirmed zero remote Teams, and recorded `started -> finished`. Missing/corrupt/insecure markers,
  ambiguous candidates, identity drift, API failure, cleanup failure, or evidence failure stop
  startup. A pre-marker crash can leave only an unmarked local directory and requires inspection.
- Post-commit acceptance restarted source commit `d645441` on loopback port 8765. Startup recovery
  completed with no residue, health stayed green, the sole plan remained `ready` with its original
  timestamp, the dashboard remained `1/1` covered with zero projection backlog, and the browser
  emitted no warnings or errors. No plan, mailbox, or production fleet action was triggered.
- The local mail setup path now has a complete two-consent UI and fixed backend OAuth boundary.
  Only `gws auth login --readonly --services gmail` is possible; activation follows a second
  encrypted-token/readonly-scope verification and uses an atomic `0600` managed file without
  rewriting user configuration. Revocation fails closed for future access. Focused tests, three
  consecutive 261-test full runs, frontend typecheck, ruff, mypy, desktop acceptance, and 390x844
  no-overflow acceptance pass. One checkbox leaves OAuth disabled; both enable the button, but the
  button was not clicked, no authorization ledger event exists, and no mailbox was accessed.
- Arbitrary planning, Paperclip, workflow, runtime, and schedule-parser errors no longer cross into
  plan API responses or ledger records. Hostile private-path echoes are covered by regressions.
- A real primary console on port 8765 held the `0700` state directory's `0600` lease. A second
  source-tree start on port 8766 exited 2 before recovery; primary health and the existing `ready`
  plan were unchanged.
- Current-HEAD real doctor has exactly one failing check: the deliberately stale stable qd lacks
  `soak` and `console`. Every dependency, credential boundary, template, installed service,
  runtime, port, permission, backup target, and Paperclip single-instance check passes.

## Safe remaining sequence

1. Do not touch the stable uv tool or canary before 2026-07-14 15:23:32 PDT.
2. At the checkpoint, recompute soak, doctor, status, watchdog, digest, projector backlog, backup,
   and canary evidence. Append a checkpoint only if the derived verdict passes.
3. Enter one quiesced maintenance window: ensure no active `qd wrap`/`qd gated-claude`; boot out
   qd periodic services and canary; gracefully stop the manual source console without deleting its
   persistent lease file; install the current wheel; verify stable `qd soak` and `qd console`;
   render/lint/install the console plist; bootstrap all services; require current doctor, runtime
   state, watchdog, digest, and backlog to pass.
4. Adopt feed-monitor and sox-monitor only from their hash-locked idle-PID preflight, then start
   the seven-day append-only soak.
5. Configure Telegram only through local hidden input. Enable mail only after explicit metadata
   transmission consent and Gmail readonly OAuth.
6. Obtain the brand decision before creating a Git remote or public release. Begin M6 product code
   only after a written paid commitment or deposit.

Project completion requires every row above to be complete. A green repository test suite, one
manual run, or a source-only console does not substitute for elapsed production, public release,
or paid-Pilot evidence.
