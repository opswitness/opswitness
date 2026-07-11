# P0 Validation Report — Paperclip as the base platform

Date: 2026-07-11 · Target: Paperclip v2026.707.0 · Verdict: **GO**

Sandbox: isolated `HOME` under a session scratchpad (`pp-sandbox/home`), embedded PostgreSQL
on :54329, server on :3100 (`local_trusted`, loopback). Smoke company `bosun-smoke`
(id `1366e98e-98cd-4b46-b048-e7f478e5a2cb`).

## What was validated

### API surface
- `GET /api/openapi.json` → 362 paths / 445 operations (~504 KB).
- Smoke round-trip 7/7 green: create company → issue → approval (create → approve →
  terminal state `approved`) → work-product (sha256 carried in `externalId`) → agent →
  cost-event (`billingType=subscription_included` native; requires `costCents` + `occurredAt`;
  aggregation and by-provider queries immediately consistent).
- CLI exposes the full approval lifecycle (`approval create/approve/reject/request-revision/
  resubmit/comment`) and run inspection (`run list/live/get/events/log`).
- MCP server built in: 35 task-management tools; **no approval tools** (gap Quarterdeck fills).

### Crash recovery (issue #8023 assessment)
Two independent observations, one deliberate experiment:

1. **Natural experiment**: parent `npx paperclipai onboard` was killed mid-session leaving an
   orphaned embedded Postgres and one in-flight heartbeat run. Next startup logged
   `WARN: reaped orphaned heartbeat runs {"reapedCount":1}` and served HTTP 200. No crash-loop.
2. **Deliberate kill**: process adapter running `sleep 300` (in-flight run) → `kill -9` of the
   main process → restart healthy in ~8 s; interrupted run honestly recorded as
   `failed: "Process lost -- server may have restarted"` with a complete 3-event chain;
   approvals/issues/cost events all survived.
3. **New finding (upstream contribution candidate)**: the interrupted run's *child process*
   (`sleep`, pid 74039) was **not reaped** after recovery — a real agent child would leak
   sessions/tokens. Adjacent to but distinct from #8023.

Conclusion: #8023 did not reproduce on v2026.707 in either scenario. Risk downgraded from
"blocker" to "watch + contribute fix upstream".

### Known constraints discovered
- **No public "create external heartbeat run" endpoint.** External heartbeat runs are
  read-only; writes available to external systems: activity, approval, issue, comment,
  work-product, cost-event, wake/invoke of Paperclip-managed agents. → See
  [ADR-0001](adr/0001-run-ledger-write-model.md) for the wrap write model.
- Approval `type` is a closed enum; tool-gate approvals use `request_board_approval` + payload.
- Paperclip watchdog verifies its own issue trees only — external script monitoring is
  genuinely absent (Quarterdeck `wrap`'s reason to exist).
- Work-products carry no content hashes natively; `externalId` accepts our sha256.
- Issue [#3017](https://github.com/paperclipai/paperclip/issues/3017) (action-class guards)
  remains open, unassigned, zero linked PRs; none of its three sketched options use
  vendor-native PreToolUse hooks — Quarterdeck `gate` targets it as reference implementation.

## Operational notes
- Only ever run **one** server instance per embedded Postgres; a second `paperclipai run`
  happily binds :3101 against the same DB (observed) — scheduler duplication risk.
- Production deployments should set `DATABASE_URL` to an external Postgres.
- `telemetry.enabled` defaults to `true` — disable for privacy-sensitive installs.
