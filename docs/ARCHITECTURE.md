# Architecture

> Run long-lived AI work with approvals, evidence, and recoverable execution.

Quarterdeck is the **trust / evidence bridge** in a five-layer stack. It is not the
control plane (that's [Paperclip](https://github.com/paperclipai/paperclip), bought not
built), and not an executor (your launchd jobs and coding agents stay untouched). It also
ships a thin local operator console, but that console delegates rather than becoming a
second control plane. The bridge remains the one layer nothing else can replace: the place
where ungoverned reality gets connected to governance, with the evidence held locally.

## The stack

```mermaid
flowchart BT
    subgraph E["Execution layer (existing assets, never rewritten)"]
        E1["launchd / cron fleet"]
        E2["Claude Code (headless)"]
        E3["Codex (exec, sandbox)"]
        E4["LangGraph pipelines"]
    end
    subgraph Q["★ Quarterdeck — trust / evidence bridge (this repo)"]
        Q1["qd wrap + local ledger"]
        Q2["projector (commit order, fail-stop)"]
        Q3["watchdog + digest (fail-closed)"]
        Q4["gate (P3) + artifacts (P4)"]
        Q5["allowlisted workflow launch"]
        Q6["metadata-only mail evidence adapter"]
    end
    subgraph P["Governance layer — Paperclip (73.4k★ MIT, off the shelf)"]
        P1["issues · approvals · budgets · audit · Postgres"]
    end
    subgraph A["Replaceable internal adapters"]
        A1["AionUi planning + agent sessions"]
        A2["OpenAI / Anthropic vendor login CLIs"]
    end
    subgraph C["Operator surface"]
        C0["Quarterdeck console<br/>(workspace · tasks · approvals · evidence · connections)"]
        C1["qd CLI + Telegram fallback"]
    end
    subgraph V["Vertical case layer (P5, paid)"]
        V1["practitioner workbench (RAG lives here)"]
        V2["software delivery · research · quant (private)"]
    end
    E -->|"wrap takeover · PreToolUse interception (P3)"| Q
    Q -->|"projection: at-least-once + reconciliation"| P
    C -->|fixed local adapters| A
    C -->|governance API| P
    C -.-> V
```

Evidence flows **upward**. Nothing above the bridge is a source of truth.

## Design laws (review-hardened, each has tests)

1. **The local ledger is the sole source of truth.** Append-only JSONL outbox,
   crash-safe write protocol (O_APPEND + flock, one event one write, started fsync'd
   before exec, finished fsync'd before exit, torn-tail heal + quarantine). Paperclip
   receives *projections* — at-least-once with reconciliation, never claimed as
   exactly-once. If Paperclip dies, the evidence chain is intact. See
   [ADR-0001](adr/0001-run-ledger-write-model.md).
2. **Fail closed, everywhere.** No approval decision means no. Unreachable API means no.
   Unsupported schedule renders red, never silently green. Absence of coverage is
   reported as absence — "no schedules" is never "0 missed"; coverage counts only
   *active* monitoring, over *every* job the ledger has ever seen. Retirement and
   reversal are append-only `job_retired` / `job_unretired` events; any later run
   resurfaces as `resurrected` until an explicit unretire.
3. **Execution evidence ≠ outcome evidence.** Exit codes prove the process ran; they do
   not prove the data was right. The digest says so explicitly; outcome evidence
   (artifact hashes, evals, approvals) arrives with P4 and is labeled separately.
4. **Discovery generates candidates; monitoring requires one human enrollment.**
   Auto-tighten may run unattended (bounded, audited, rollbackable); auto-loosen is
   propose-only, always. Never break the wrapped job: ledger failure degrades to an
   alert, exit codes are mirrored faithfully (including death-by-signal).
5. **Canonical ID = the full launchd label.** Short names are display sugar; an ID that
   could drift when a neighbor appears would sever ledger history. User config is
   strict-schema (scalar enroll rejected, identity fields not overridable).
6. **The platform layer has no LLM, no embeddings, no RAG — deliberately.** Evidence
   does not tolerate "approximately relevant". Structured queries beat vectors here;
   at scale, lexical FTS is the upgrade path. Knowledge retrieval (RAG) belongs to the
   vertical case layer, where the curated rules corpus is itself the paid content —
   shape defined in [ADR-0002](adr/0002-knowledge-layer.md): deterministic-first split,
   markdown vault as source, structured-first retrieval, verifiable citations.
7. **A workflow button is an allowlisted launch, never a remote shell.** Quarterdeck owns the
   visible task action; AionUi may execute it as a hidden adapter. Quarterdeck accepts only an exact id from a local `0600`
   manifest, then enforces fixed argv, no runtime parameters, single-workflow concurrency,
   a detached supervisor, and fsync-before-exec dispatch order. See
   [ADR-0004](adr/0004-allowlisted-workflow-launch.md).
8. **Mailbox content is untrusted external data.** The hidden planning adapter can invoke only one fixed,
   administrator-owned metadata query. Quarterdeck persists `mail_check_requested` before
   access and `mail_check_finished` before returning sender/subject/date/message-id fields;
   neither event stores those fields. No body, draft, send, delete, label mutation, or runtime
   query exists in the CLI or MCP surface. The normal 11-tool MCP excludes mail entirely;
   `qd mcp --profile mail` exposes only status/check, and model transmission additionally
   requires an explicit local consent bit. Before login, the loopback console requires a valid
   Google Desktop OAuth client at gws's fixed location with `0700` directory and `0600` file
   permissions. Import is explicit, schema-validated, canonicalized, and atomically published;
   no client field enters the API response or ledger. The console can obtain the consent bit only
   after two literal-true acknowledgements and an exact readonly Gmail OAuth flow; activation
   lives in a private managed file so user configuration is never rewritten. See
   [ADR-0005](adr/0005-metadata-only-mail-monitor.md).
9. **Elapsed rollout gates are ledger contracts, not prose timestamps.** `qd soak` freezes
   each tracked job's interval/grace and recomputes first/intermediate/trailing cadence gaps,
   terminal/degraded evidence, schedule drift, torn lines, and projection backlog. A hard
   failure remains failed until a reasoned append-only reset; checkpoints never become a
   second truth source. See [ADR-0006](adr/0006-append-only-soak-gates.md).
10. **Planning and execution are separate state transitions.** New general work is drafted
    by an ephemeral AionUi team in Plan Mode, without tools. Quarterdeck validates the strict
    plan schema and records only request/plan hashes in the ledger. A Paperclip issue and an
    AionUi execution team or allowlisted workflow can be created only after a human confirms
    the exact plan hash. Completion remains `completed_unverified` until outcome evidence
    exists. See [ADR-0007](adr/0007-local-operator-console.md).
11. **Notification setup is narrow, local, and evidence-first.** The console is not a generic
    secret editor. It accepts only Telegram token/chat ID into password fields, writes through the
    existing `0600` secret boundary, serializes configuration changes, and exposes only a fixed
    test message behind a separate confirmation. Credentials never enter ledger events or API
    responses; environment-managed values cannot be replaced from the UI.
12. **Quarterdeck is the only ordinary product door.** Provider login, task planning, approval
    decisions, and evidence review stay in the loopback console. AionUi and Paperclip are named
    only in advanced diagnostics and remain replaceable adapters. Vendor credentials stay with
    vendor-owned CLI login flows; Quarterdeck receives only sanitized status.

## Necessity and shrinkability

Quarterdeck exists because of three verified gaps, no more:

| Gap | Verified how |
|---|---|
| Nothing monitors *external* scheduled scripts | Paperclip's watchdog verifies only its own issue trees (official docs) |
| No tool-call-level, fail-closed approval gate | paperclip#3017 open, unassigned, zero PRs; hobby hooks have no ledger |
| No content-hashed artifacts; platform records are self-reported | work-products carry no hashes; audit-chain bug open upstream |

It is designed to **shrink**: ADR-0001 carries revisit triggers — if upstream ships an
external-run API, tool gates, or content hashes, the corresponding module retires.
A thin layer that refuses to thin itself becomes the thing it replaced.

**The wheel test** — every proposed module must first answer: does Paperclip, Claude
Code, or launchd already do this? Applied consequences: the gate (P3) builds no policy
engine and no in-hook waiting (Claude Code's native permission pipeline handles static
allow/deny/ask; its `permissionDecision: "defer"` handles the pending-decision
lifecycle — we add only the defer→Paperclip-approval→resume bridge and the ledger
record); artifacts (P4) build no database (authority = one ledger event kind; the
projection rides Paperclip work-products with reconciliation, since `externalId` has
no unique constraint upstream); vertical-case agents (P5) run natively as Paperclip
agents/routines. Scheduling stays with launchd (launchd intervals are elapsed-time,
cron is calendar-aligned — they are not translatable); the approval **workflow state** stays with
Paperclip while the visible decision UI and **authoritative approval evidence**
(request hash, tool_use_id, expiry, approval id, decision, decider, resume/consume
outcome) stay in Quarterdeck and the local ledger — law 1 admits no exception: if Paperclip loses its
database, pending calls stay denied and every past decision remains locally auditable;
sessions stay with the agent CLIs. Version 1 records the local single-user actor as
`local_console`; it does not claim multi-user or remote identity assurance.

AionUi's native Manual Scheduled Task remains an advanced adapter test surface, not an operator
requirement. Quarterdeck builds no DAG editor or workflow runtime. Its local console is the one
composition surface for daily operations, approvals, connections, and new-task plan review; confirmed execution is
delegated to AionUi teams or to fixed asynchronous MCP launches whose requested/dispatched/run
events share one run id. Internal workflow orchestration stays with the registered command (for
example LangGraph).

The standalone Paperclip MCP is deliberately not mounted in AionUi. Its pinned
v2026.707.0 surface includes approval decisions, other mutations, and a general `/api`
escape hatch, with no documented read-only mode or scoped read-only token. Prompt-level
instructions are not an authorization boundary. Quarterdeck therefore exposes only a fixed
approve/reject facade over the Paperclip API and keeps the general Paperclip MCP unavailable to
the model. AionUi receives Quarterdeck's evidence-oriented MCP surface.

## Entry doctrine: Quarterdeck is the door

Two kinds of doors, two opposite rules:

**Platform layer (open source): spine plus one thin local door.** `qd` and the ledger remain the
operational spine. The local console is the ordinary user entry for AI connection, planning,
confirmation, approval, evidence, and integrations. It owns no scheduler, agent runtime, or DAG;
each dependency stays replaceable because the console calls versioned local adapters instead of
absorbing their state machines. The CLI and Telegram remain fallbacks, not competing setup paths.

**Commercial layer (paid verticals): the door IS the product.** Entry equals
relationship ownership — whoever's surface opens every morning owns the brand memory,
the pricing conversation, and the renewal. Paid users enter through a **purpose-built
thin workbench** (for the practitioner case: client list → chart → draft → sign-off
queue → delivery), never through a generic issue board, and never via "install three
tools and wire up MCP". Not a rebranded Paperclip fork — that buys the UI maintenance
debt of a 73k★ project and still ships the wrong UX; the workbench calls the lower
layers' APIs and Paperclip stays as invisible as Postgres. It stays thin (weeks, not
months) precisely because every piece of logic lives below: the deterministic engine,
Paperclip-native agents, the gate, the corpus MCP.

Sequencing: the generic local operator console may evolve with the open platform. The
purpose-built practitioner workbench remains blocked until a paying pilot exists.
Paperclip's per-company `branding:update` can carry practitioner branding without a fork;
paid users ultimately see the vertical workbench, not the generic operations surface.

## Module map

| Module | Path | Status |
|---|---|---|
| ledger (outbox + write protocol) | `src/quarterdeck/ledger.py`, `fsutil.py` | ✅ P2 |
| wrap runner (tee, bounded process-tree signals, mirroring) | `src/quarterdeck/wrap/runner.py`, `process_tree.py` | ✅ P2 |
| projector (issues/comments, reconciliation) | `src/quarterdeck/projector.py`, `paperclip.py` | ✅ P2 |
| index (disposable SQLite) | `src/quarterdeck/index.py` | ✅ P2 |
| watchdog / digest / coverage | `src/quarterdeck/watchdog.py`, `digest.py`, `schedules.py` | ✅ P2 |
| job lifecycle | `src/quarterdeck/lifecycle.py` | ✅ P2 |
| canary / soak evidence gate | `src/quarterdeck/soak.py` | ✅ append-only contract + CLI |
| bootstrap (candidates, two-file model) | `src/quarterdeck/bootstrap.py` | ✅ P2 |
| adopt (dry-run plist wrapping) | `src/quarterdeck/adopt.py` | ✅ P2 (`--apply` gated on install) |
| MCP console surface | `src/quarterdeck/mcp_server.py` | ✅ 11-tool ops + isolated 2-tool mail profile |
| allowlisted workflow launcher | `src/quarterdeck/workflows.py`, `workflow_worker.py` | ✅ code + tests + live AionUi one-click acceptance |
| metadata-only mail monitor | `src/quarterdeck/mail.py`, `console/`, `console-ui/` | ✅ adapter + setup/revoke UI; live OAuth and AionUi schedule pending |
| local operator console | `src/quarterdeck/console/`, `console-ui/` | ✅ sole operator surface + provider login/status + plan/confirm/dispatch + approval facade + Gmail/Telegram + responsive UI; production install pending canary |
| install doctor / secure services / disaster recovery | `src/quarterdeck/doctor.py`, `service.py`, `backup.py` | ✅ five secret-free templates + installed-command drift check; soak pending |
| gate (PreToolUse `defer` → Paperclip approval → resume) | `gate.py`, `gated_claude.py` | ✅ M3 code + two live approval/resume drills |
| artifacts (ledger events + content-addressed projection) | `artifacts.py`, `index.py` | ✅ M4 code + live projection |
| vertical case packs | separate private repo | P5 |

Status tracks code + tests in this repo. [READINESS.md](READINESS.md) is the single
current release-gate snapshot; ADRs remain the design authority.

Related: [P0 validation](P0-VALIDATION.md) · [readiness gates](READINESS.md) ·
[approved install runbook](INSTALL-PAPERCLIP.md) ·
[AionUi console setup](aionui.md)
