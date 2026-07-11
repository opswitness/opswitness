# ADR-0001: Quarterdeck owns the authoritative run ledger; Paperclip gets projections

Date: 2026-07-11 · Status: accepted

## Context

`qd wrap` promises a run ledger for external launchd/cron jobs. Paperclip v2026.707's public
OpenAPI (362 paths) offers **no** "create external heartbeat run" endpoint — heartbeat runs are
readable but writable only by Paperclip's own execution engine. Writable surfaces available to
external systems: activity, approval, issue, comment, work-product, cost-event, agent wake.

Masquerading external script runs as Paperclip heartbeat runs is impossible today and would be
dishonest even if an undocumented route existed.

## Decision

1. **Quarterdeck keeps the authoritative, append-only run ledger locally.**
   - Crash-safe JSONL spool per day under `~/.local/state/quarterdeck/ledger/` written
     synchronously by `qd wrap` (works with Paperclip down — never blocks or breaks the
     wrapped job).
   - SQLite index (WAL) rebuilt/updated from the spool for queries (`qd runs`, `qd status`).
     The spool is truth; the index is disposable.
2. **Paperclip receives projections, clearly labeled as external runs:**
   - one **issue** per job (stable, carries fleet state),
   - a **comment** per run transition (started/succeeded/failed + exit code + log tail),
   - **work-products** for artifacts (sha256 in `externalId`),
   - **cost-events** where measurable,
   - **activity** entries for audit.
3. **Never write anything that presents itself as a Paperclip heartbeat run.**

## Consequences

- Quarterdeck degrades gracefully: Paperclip outage → local ledger continues, projections
  replayed from spool on reconnect (idempotency via run ULIDs in `externalId`).
- Two ledgers exist; the local one is authoritative for external jobs, Paperclip remains
  authoritative for its own agent runs. `qd status` merges both views read-only.
- If upstream later ships an external-run API or plugin surface, only the projection layer
  changes (tracked as a revisit trigger on this ADR).
