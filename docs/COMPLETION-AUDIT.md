# Quarterdeck Completion Audit

Snapshot: 2026-07-13 18:13 PDT. This document maps the approved M0-M6 plan to evidence and
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
| Local total console | Dashboard, Plan Mode architecture drafting, hash-bound confirmation, dispatch adapters, responsive UI and packaged assets | Complete in source; stable install/KeepAlive service waits for canary maintenance window |

## Live evidence at this snapshot

- Current-HEAD `qd soak status m2-canary --json`: `pending`; only blocker is
  `minimum_duration`, with 76,218 seconds remaining at 18:13 PDT. The tracked job has one start,
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

## Safe remaining sequence

1. Do not touch the stable uv tool or canary before 2026-07-14 15:23:32 PDT.
2. At the checkpoint, recompute soak, doctor, status, watchdog, digest, projector backlog, backup,
   and canary evidence. Append a checkpoint only if the derived verdict passes.
3. Enter one quiesced maintenance window: ensure no active `qd wrap`/`qd gated-claude`; boot out
   qd periodic services and canary; install the current wheel; verify stable `qd soak` and
   `qd console`; render/lint/install the console plist; bootstrap all services; require current
   doctor, runtime state, watchdog, digest, and backlog to pass.
4. Adopt feed-monitor and sox-monitor only from their hash-locked idle-PID preflight, then start
   the seven-day append-only soak.
5. Configure Telegram only through local hidden input. Enable mail only after explicit metadata
   transmission consent and Gmail readonly OAuth.
6. Obtain the brand decision before creating a Git remote or public release. Begin M6 product code
   only after a written paid commitment or deposit.

Project completion requires every row above to be complete. A green repository test suite, one
manual run, or a source-only console does not substitute for elapsed production, public release,
or paid-Pilot evidence.
