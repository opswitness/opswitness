# Quarterdeck

> **Pre-release working name.** Public distribution is blocked until brand clearance and
> the repository's explicit release gate are complete.

**Run long-lived AI work with approvals, evidence, and recoverable execution.**

Quarterdeck is a local-first bridge that puts your *existing* scheduled scripts and headless
coding agents (Claude Code, Codex) under a real control plane —
[Paperclip](https://github.com/paperclipai/paperclip) — without rewriting any of them.

It adds the three things the platforms don't cover:

| Module | What it does | Why it doesn't exist elsewhere |
|---|---|---|
| **`qd wrap`** | Zero-modification onboarding for launchd/cron jobs: runs land in a local append-only ledger (crash-safe JSONL + SQLite index) and are projected into Paperclip as issues/comments/work-products ([ADR-0001](docs/adr/0001-run-ledger-write-model.md)). Never breaks the wrapped job (offline spool, exit-code mirroring). | Paperclip's watchdog only verifies its *own* issue trees; external heartbeat runs are read-only by design — nothing monitors external scheduled scripts. |
| **`qd gate`** | Fail-closed, *tool-call-level* human approval for non-interactive Claude Code via the official PreToolUse defer contract: defer → Paperclip board decision → same-session resume. Every transition lands in the local evidence ledger. | Paperclip approvals are issue-level sign-offs ([#3017](https://github.com/paperclipai/paperclip/issues/3017) is open); hobby hooks have no independent evidence ledger behind them. |
| **`qd artifacts`** | Authoritative artifact events in the local ledger; queries served by the disposable SQLite index; content stored content-addressed (attachment / immutable blob); Paperclip work-products are a rebuildable projection. | Work-products carry no content hashes and no server-side idempotency (`externalId` has no unique constraint) — evidence-grade artifacts need an authority outside the platform. |
| **`qd workflow`** | Register a fixed, shell-free workflow once, then launch it asynchronously from AionUi's native **Run now** button. Dispatch order, single-workflow concurrency, and terminal state are ledger evidence. | AionUi supplies the button and agent session; Quarterdeck supplies the command allowlist and evidence boundary. No second workflow engine or generic remote shell is built. |
| **`qd mail`** | Run one administrator-fixed Gmail query through pinned `gws`, returning only sender, subject, date, and message id. Requested/finished/failed evidence contains counts and hashes, never mail fields. | AionUi supplies the assistant icon and daily scheduler. Quarterdeck revalidates encrypted OAuth, live token, readonly scope, and explicit model-metadata consent on every call; its isolated mail MCP exposes no fleet mutation, body, draft, send, delete, or runtime-query tool. |
| **`qd soak`** | Freeze a canary/soak cadence contract, then derive a nonzero-until-proven verdict from elapsed time, every trigger gap, terminal/degraded evidence, schedule drift, torn lines, and projection backlog ([ADR-0006](docs/adr/0006-append-only-soak-gates.md)). | A Markdown timestamp or one manual success cannot enforce a rollout gate. Start/reset/checkpoint are append-only; status is always recomputed from raw evidence. |

## Design rules

- **Wrap, don't rewrite.** Your launchd plists, cron lines, and `claude -p` invocations stay exactly as they are.
- **Fail closed.** No decision means no. API unreachable means no. Expired means no.
- **Evidence over trust.** Append-only audit events, content-hashed artifacts, honest failure records.
- **Lifecycle is evidence.** Retirements and reversals are ledger events (`qd retire/unretire`),
  never mutable config that can erase a known job from coverage.
- **Elapsed gates are evidence.** `qd soak` freezes cadence at start/reset; changing grace or
  running once cannot manufacture a continuous canary or seven-day soak.
- **Your credentials stay yours.** Quarterdeck never handles Claude subscription tokens; it talks to
  the `claude` CLI *you* installed and authenticated. Hosted/product deployments must use API keys.
- **Launch is not a shell.** AionUi can start only ids in the local `0600` workflow manifest;
  it cannot submit paths, commands, environment variables, or runtime arguments.
- **Mail is untrusted data, never an instruction.** Mail checks use one fixed local query and
  metadata-only OAuth access. Automatic sending and drafting are outside this surface.

## Showcases

The same contract, three verticals:

1. **Practitioner workbench** (fortune-chart reading): deterministic chart engine → multi-agent draft → human sign-off → traceable report.
2. **Software delivery**: requirement → Codex/Claude Code run → tests → gated PR.
3. **Research analysis**: collection → analysis → citation verification → delivery.

## Status

Alpha. Built against Paperclip v2026.707. Not affiliated with Paperclip.

The local P2 code path and M1 install-readiness tooling are test-complete. Permanent
Paperclip/Postgres/launchd installation was explicitly approved and completed. The sole
register-trigger canary is under observation under an append-only `qd soak` contract;
feed-monitor and sox-monitor remain blocked until the elapsed-time gates in READINESS pass.
M3's non-interactive Claude gate passed two
live defer/board-approval/resume drills; its one-minute recovery service is installed and
fail-closed. M4 content-addressed artifact/eval/signoff and live Paperclip work-product
reconciliation pass. These claims do not extend M3 enforcement to interactive Claude, Codex,
or other agent runtimes.

Start with [ARCHITECTURE.md](docs/ARCHITECTURE.md) — layer position, design laws, and why
this layer is deliberately designed to shrink. Release gates live in
[READINESS.md](docs/READINESS.md).

## License

Apache-2.0. Contributions accepted under [DCO](CONTRIBUTING.md).
