# ADR-0001: Quarterdeck owns the authoritative run ledger; Paperclip gets projections

Date: 2026-07-11 · Status: accepted · **v2** (amended same day after an OpenAPI idempotency
audit; v1's blanket "idempotent replay via `externalId`" was wrong — verified against the live
v2026.707 spec, only work-products accept `externalId`).

## Context

`qd wrap` promises a run ledger for external launchd/cron jobs. Paperclip v2026.707's public
OpenAPI (362 paths) offers **no** "create external heartbeat run" endpoint — heartbeat runs are
readable but writable only by Paperclip's own execution engine. Writable surfaces available to
external systems: activity, approval, issue, comment, work-product, cost-event, agent wake.

Idempotency audit of the projection targets (verified against the live server):

| Endpoint | Idempotency support | Reconciliation handle |
|---|---|---|
| `POST /api/companies/{id}/issues` | none | deterministic marker in title/label (`qd:job:<name>`) |
| `POST /api/issues/{id}/comments` | none | **`metadata`** field (carries `qd_event_id`) |
| `POST /api/companies/{id}/activity` | none | `details` field; duplicate-tolerant by design |
| `POST /api/companies/{id}/cost-events` | none; **requires `agentId`** | **`billingCode`** field (carries event ULID) |
| `POST /api/issues/{id}/work-products` | **`externalId`** | native |
| `idempotencyKey` | only on `agents/{id}/wakeup`, `routines/{id}/run`, `issues/{id}/interactions` | not applicable to projections |

Masquerading external script runs as Paperclip heartbeat runs is impossible today and would be
dishonest even if an undocumented route existed.

## Decision

### 1. Local authoritative ledger = append-only JSONL outbox

Events under `~/.local/state/quarterdeck/ledger/YYYY-MM-DD.jsonl`:
`run_started`, `run_finished`, `artifact_registered`, `cost_recorded`, `alert_emitted`, and
**`projection_ack`** (`{event_id, remote_kind, remote_id, ts}`). Every business event carries a
ULID `event_id`. The SQLite index (WAL) is a disposable view rebuilt from the spool.

### 2. Crash-safe write protocol

- **Permissions**: ledger directory `0700`, files `0600` (argv and log tails are sensitive;
  enforced on every append, even for files predating the policy).
- **Redaction on by default**: argv is redacted (sensitive flags, provider-shaped tokens)
  before recording; log tails are redacted and capture can be disabled
  (`capture_log_tail=false`). Heuristic, not DLP: the generic secret shape excludes `/` so
  paths/URLs survive — base64-with-slash secrets are the accepted miss.
- File opened `O_APPEND`; each write holds an exclusive `flock` (multiple `qd wrap` processes
  share the ledger safely).
- One event = one JSON line = one `write()` call (events kept small; log tails truncated).
- `run_started` is written **and `fsync`ed before** the child process is exec'd — power loss
  must not produce a ran-but-unrecorded job.
- `run_finished` is written and **`fsync`ed before `qd wrap` exits**.
- Readers take a shared `flock` (an in-flight write can never be misread as torn), quarantine
  undecodable lines to `<file>.torn` **exactly once** (dedup against existing quarantine), and
  continue — a torn tail is expected after power loss, never fatal.
- On `ENOSPC`/`EACCES`/any ledger write failure: **the wrapped job still runs** (exit-code
  mirroring preserved); Quarterdeck emits an "audit evidence lost" alert through the notify
  channel and flags `degraded=true` on the next successful event.
- **Ordering**: commit order = (file date asc, line position asc) — file append order under the
  exclusive lock. ULIDs are per-process monotonic identities; they never define cross-process
  order. The projector drains in commit order.

### 3. Projection = at-least-once + reconciliation (explicitly NOT exactly-once)

A single projector (exclusive `flock` lease file) drains unacked events in **commit order**
(file date, line position — never ULID sort):

- **issue** (one per job): find-or-create by deterministic marker; ack caches the issue id.
- **comment** (run transitions): comment `metadata` is a **strict schema**
  (`version`/`sourceRunId`/`sections` only — arbitrary keys are rejected; verified on the live
  spec). The event ULID travels in a legal structure:

  ```json
  {"version": 1, "sections": [{"rows": [
    {"type": "key_value", "label": "qd_event_id", "value": "<ULID>"}]}]}
  ```

  plus a human-visible `qd:event:<ULID>` trailer in the body. Reconciliation lists recent
  comments and matches the metadata row first, body marker as fallback.
- **work-product**: `externalId = <event ULID>` — **verified on the pinned v2026.707
  source: plain index, NO unique constraint; creation is an unconditional insert.**
  `externalId` is therefore a reconciliation marker, never a server-side idempotency
  key; the list-and-reconcile path is mandatory, same as comments. `createdByRunId`
  only references Paperclip's own heartbeat runs — Quarterdeck ULIDs cannot join
  native lineage; lineage lives in `metadata` and the local ledger.
- **cost-event**: posted under a dedicated service agent (`quarterdeck`, created once per
  company — satisfies the mandatory `agentId`); `billingCode = qd:<event ULID>` is a
  **reconciliation marker, not a remote key** — the GET endpoint has zero filter params
  (verified), so reconciliation lists recent events and scans locally. Residual duplicate
  window: crash after POST, before ack — documented, bounded by reconciliation on next
  projector start.
- **activity**: best-effort audit echo, `details.qd_event_id` set, duplicate-tolerant; the
  local ledger — not Paperclip activity — is the authoritative audit for external jobs.

## Consequences

- Paperclip outage: wrap unaffected; projections replay from the outbox on reconnect.
- Duplicates are possible inside the crash window and are healed by reconciliation, not
  prevented — semantics are at-least-once. Anything requiring exactly-once must key off the
  local ledger.
- Two ledgers exist; the local one is authoritative for external jobs, Paperclip remains
  authoritative for its own agent runs. `qd status` merges both views read-only.
- Revisit triggers: upstream adds `idempotencyKey`/`externalId` to comments, cost-events, or an
  external-run API — then the reconciliation layer shrinks or disappears.
