# Quarterdeck

**Run long-lived AI work with approvals, evidence, and recoverable execution.**

Quarterdeck is a local-first bridge that puts your *existing* scheduled scripts and headless
coding agents (Claude Code, Codex) under a real control plane —
[Paperclip](https://github.com/paperclipai/paperclip) — without rewriting any of them.

It adds the three things the platforms don't cover:

| Module | What it does | Why it doesn't exist elsewhere |
|---|---|---|
| **`qd wrap`** | Zero-modification onboarding for launchd/cron jobs: runs land in a local append-only ledger (crash-safe JSONL + SQLite index) and are projected into Paperclip as issues/comments/work-products ([ADR-0001](docs/adr/0001-run-ledger-write-model.md)). Never breaks the wrapped job (offline spool, exit-code mirroring). | Paperclip's watchdog only verifies its *own* issue trees; external heartbeat runs are read-only by design — nothing monitors external scheduled scripts. |
| **`qd gate`** | Fail-closed, *tool-call-level* human approval for Claude Code via the official PreToolUse hook: block → notify (Telegram/console) → approve/deny → unblock. Every decision lands in Paperclip's audit trail. | Paperclip approvals are issue-level sign-offs ([#3017](https://github.com/paperclipai/paperclip/issues/3017) is open); hobby hooks have no ledger behind them. |
| **`qd artifacts`** | Authoritative artifact events in the local ledger; queries served by the disposable SQLite index; content stored content-addressed (attachment / immutable blob); Paperclip work-products are a rebuildable projection. | Work-products carry no content hashes and no server-side idempotency (`externalId` has no unique constraint) — evidence-grade artifacts need an authority outside the platform. |

## Design rules

- **Wrap, don't rewrite.** Your launchd plists, cron lines, and `claude -p` invocations stay exactly as they are.
- **Fail closed.** No decision means no. API unreachable means no. Expired means no.
- **Evidence over trust.** Append-only audit events, content-hashed artifacts, honest failure records.
- **Lifecycle is evidence.** Retirements and reversals are ledger events (`qd retire/unretire`),
  never mutable config that can erase a known job from coverage.
- **Your credentials stay yours.** Quarterdeck never handles Claude subscription tokens; it talks to
  the `claude` CLI *you* installed and authenticated. Hosted/product deployments must use API keys.

## Showcases

The same contract, three verticals:

1. **Practitioner workbench** (fortune-chart reading): deterministic chart engine → multi-agent draft → human sign-off → traceable report.
2. **Software delivery**: requirement → Codex/Claude Code run → tests → gated PR.
3. **Research analysis**: collection → analysis → citation verification → delivery.

## Status

Alpha. Built against Paperclip v2026.707. Not affiliated with Paperclip.

The local P2 code path is test-complete. Permanent Paperclip/launchd installation remains
NO-GO until the M1 install-readiness gates in READINESS pass.

Start with [ARCHITECTURE.md](docs/ARCHITECTURE.md) — layer position, design laws, and why
this layer is deliberately designed to shrink. Release gates live in
[READINESS.md](docs/READINESS.md).

## License

Apache-2.0. Contributions accepted under [DCO](CONTRIBUTING.md).
