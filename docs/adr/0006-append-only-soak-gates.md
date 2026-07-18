# ADR-0006: Append-only soak gates

Status: Accepted

Date: 2026-07-13

## Context

M2 requires a 24-48 hour canary followed by a seven-day production soak. A timestamp in a
Markdown file is not an enforceable gate: it cannot prove trigger continuity, distinguish a
single successful run from sustained health, or preserve why an interrupted window restarted.
Tests and manual runs must not substitute for elapsed evidence.

## Decision

OpsWitness records soak contracts in the authoritative JSONL ledger:

- `soak_started` freezes a name, minimum duration, tracked jobs, and each job's current
  `expected_interval_seconds + grace_seconds` contract.
- `soak_reset` is a complete replacement contract with a mandatory reason and a pointer to the
  prior contract. It starts a new evidence window without deleting prior failures.
- `soak_checkpoint` records a recomputed verdict and ledger tail for audit convenience. It is
  never read as authority when calculating a later verdict.

`qd soak status` folds the latest start/reset in ledger commit order and recomputes the result
from raw events. It passes only when all of the following hold:

1. The minimum wall-clock duration has elapsed.
2. Every frozen schedule still exists, remains active, and is byte-semantically equivalent for
   interval and grace. Widening grace after a gap cannot rescue an existing soak.
3. Each job has successful, exit-0 runs and no trigger gap exceeds the frozen interval plus
   grace, including the first and current trailing boundary.
4. No tracked run failed, was killed, was malformed, or carried degraded evidence; no
   `tree_signal_degraded` or future-dated run event exists in the evidence window.
5. The ledger has no quarantined torn lines and the projector has no unacknowledged projected
   events.
6. No tracked job is retired or resurrected.

A pending elapsed-time, first successful run, or projector reconciliation exits nonzero but can
recover without reset. A cadence gap, terminal failure, schedule drift, torn ledger, lifecycle
violation, or degraded process tree permanently fails that contract; recovery requires an
explicit reasoned reset.

For a single-job canary, `--since-run-id` may anchor the evidence window to exactly one complete,
non-degraded, successful exit-0 ledger run. Arbitrary timestamps are not accepted. Multi-job
soaks begin at contract append time.

## Commands

```text
qd soak start NAME --job LABEL --minimum-hours 24 --reason REASON [--since-run-id RUN]
qd soak reset NAME --reason REASON [--since-run-id RUN]
qd soak status NAME [--json]
qd soak checkpoint NAME
```

`status` is read-only except that the existing ledger reader may quarantine a newly discovered
torn line. `checkpoint` fsyncs one snapshot event and exits zero only for a currently passing
verdict.

## Boundaries

The soak gate proves sustained execution evidence for its declared jobs. It does not replace
`qd doctor`, backup restoration, Telegram delivery, business-outcome evals, or the independent
M2 adoption checklist. The local operator owns the ledger and could edit it directly; protection
against a malicious machine owner is outside the local-first threat model.

Soak events are not included in `PROJECTED_KINDS`. Paperclip remains a projection and does not
become the authority for release readiness.

