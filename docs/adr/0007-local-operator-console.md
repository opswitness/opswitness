# ADR-0007: Quarterdeck is the sole local operator surface

Status: accepted

## Context

Paperclip is the governance system of record and AionUi is a replaceable planning/agent adapter.
They remain internal implementation components. Daily operators need one quiet Quarterdeck entry
for fleet health, evidence, approvals, AI connections, mail summary, and new work. New work
must not jump directly from a sentence into execution: the operator needs to review the objective,
agent architecture, stages, cadence, checkpoints, artifacts, and risks first.

Building another control plane, DAG engine, scheduler, or agent runtime would violate the wheel
test. Giving either AionUi or Paperclip unrestricted cross-system credentials would also collapse
the existing trust boundaries.

## Decision

Quarterdeck ships a thin FastAPI + React operator console, started with:

```bash
qd console serve --open
```

This console is the sole ordinary product door. Users connect ChatGPT/OpenAI or Claude, plan and
run tasks, review approvals, and inspect evidence without opening AionUi or Paperclip. Those names
appear only inside a closed advanced-diagnostics disclosure. Quarterdeck still delegates to their
versioned local APIs and does not absorb their planner, agent runtime, governance state machine, or
database.

Provider connection is real, local, and credential-minimizing. Quarterdeck probes the installed
vendor CLIs with fixed argv (`codex login status`, `claude auth status --json`) and exposes only a
sanitized readiness result. Connect actions launch the vendors' own fixed login flows (`codex
login`, `claude auth login --console`) in the background. Quarterdeck never asks for, receives,
stores, logs, or echoes an OpenAI/Anthropic password, browser cookie, OAuth token, or API key.

The default left-navigation destination is **Workspace**, a deliberately small chat-first entry.
The operator describes one outcome in plain language; the same existing planning contract renders
an AI-expanded six-section execution brief plus the proposed Agent architecture, stages, cadence,
checkpoints, artifacts, and risks inline. The brief must state the goal, inputs and boundaries,
method and roles, checkpoints, deliverables, and exclusions. The
operator can replan or confirm the hash-bound proposal without moving through a separate task
drawer. This is a presentation layer over the existing plan state machine, not a direct chat-to-run
path and not a second conversation or orchestration backend.

Terse, well-known intents may select a versioned planning profile. The initial `算命师`/Bazi demo
profile is deliberately synthetic: `DEMO-001`, deterministic `lunar-python` chart construction,
knowledge-grounded interpretation only, three named review roles, mandatory human signoff,
traceable JSON/citation/eval/PDF artifacts, no real personal data, and no report sending. The
profile constrains and validates the AI-generated plan; it does not install the dependency or create
a practitioner data-entry product. A missing term, agent, approval, tool, or artifact triggers one
repair attempt and then fails closed.

It binds only to `127.0.0.1` and delegates through narrow local adapters:

1. Read-only dashboard data comes from the local ledger/index, provider readiness, governance
   approvals, internal adapter health, and the metadata-only mail readiness check.
2. A new task first creates an ephemeral AionUi Team in Plan Mode inside a unique per-request
   `0700` workspace. The planner receives no tools and must return a versioned strict JSON plan
   with at most five agents and exactly one lead. Returning a result requires confirmed deletion
   of both the temporary Team and its local workspace.
3. Quarterdeck validates the plan, stores its full text only in a private local plan store, and
   appends request/plan hashes plus non-sensitive structure to the authoritative ledger.
4. The review UI displays the exact `plan_sha256`, calculated over the objective, constraints,
   workspace, preferred cadence, and validated plan. Confirmation with any other hash is rejected.
5. Quarterdeck recomputes that execution-envelope hash at confirmation and immediately before
   dispatch, then fsyncs `task_plan_confirmed` before creating external side effects. It then creates
   or reconciles a Paperclip issue and either starts a registered allowlisted workflow or creates
   an AionUi execution Team from the confirmed agent architecture. These are hidden adapter calls;
   the operator remains in Quarterdeck.
6. Runtime completion is `completed_unverified`. Artifact, eval, or human sign-off is required to
   prove a business outcome.

The plan's cadence is the proposed update/reporting cadence. Version 1 confirmation launches one
managed run only; it never silently installs a recurring schedule. A recurring AionUi task,
Paperclip routine, or launchd definition requires a separate explicit registration and approval.

The state transition is:

```text
planning -> ready -> confirmed -> dispatching -> running
                                      |             |
                                      v             v
                                    failed   awaiting_approval
                                                    |
                                                    v
                                         completed_unverified
```

There is no auto-confirm path. Replanning creates a new request and hash.

Planning progress is durable presentation state, not model reasoning. The backend reports only
observable phases: queued/preparing, generating the brief and architecture, validating or repairing,
and cleaning the ephemeral session. The UI combines those phases with elapsed time, a conservative
typical range, and a worst-case budget covering the first model call, one repair call, and cleanup.
Progress persistence is advisory and can never block ephemeral-Team cleanup. No chain-of-thought,
partial model text, prompt, or hidden tool trace is streamed to the browser.

The Workspace composer may infer only the plan's proposed cadence from explicit phrases such as
"daily" or "weekly". That deterministic hint never installs a schedule and never bypasses plan
validation, exact-hash confirmation, or external-side-effect recovery. Starting a new conversation
clears only the local presentation state; it does not cancel, mutate, or hide an existing run.

Startup recovery follows the external-side-effect boundary rather than guessing. A durable
`confirmed` record is safe to enqueue again because dispatch first acquires a per-plan atomic claim;
`running` and `awaiting_approval` records are refreshed without replay. A stranded `planning` record
may own an unreconciled ephemeral Team, while a stranded `dispatching` record may already have
created a Paperclip issue, AionUi Team, or workflow run. Those two states therefore fail closed with
fixed `planning_interrupted_by_restart` or `execution_dispatch_interrupted` evidence and require a
new plan after operator inspection. No startup path blindly repeats an ambiguous external effect.
Before recovery starts, the process holds a non-blocking exclusive `console.lease` for the private
state directory. A second port or process therefore cannot inspect or mutate the same plan state;
graceful shutdown waits for background work before releasing the lease.

Before the Team POST, Quarterdeck fsyncs a `0600` marker containing only the request owner,
purpose, exact workspace, and optional Team ID. Team creation is then bound atomically to that
marker. On startup, while holding the exclusive console lease, Quarterdeck records recovery intent,
lists AionUi Teams, requires one exact workspace + expected-name + optional-ID match, deletes only
that Team, lists again to prove absence, removes the local workspace, and records completion. A
missing or malformed marker, insecure permissions, multiple matches, identity drift, unavailable
AionUi, unconfirmed deletion, or unavailable audit ledger refuses startup. There is no prefix-based
or bulk Team deletion.

A machine crash before the initial marker is published can leave an unmarked local directory, but
cannot follow the later Team POST in Quarterdeck's program order. That directory is not deleted by
guesswork: startup stops for operator inspection. Interrupted planning remains failed separately;
cleanup recovery does not replay planning or execution.

## Evidence and privacy

The ledger records `task_plan_requested`, `task_plan_drafted`, `task_plan_failed`,
`task_plan_confirmed`, `task_execution_requested`, `task_execution_dispatched`,
`task_execution_failed`, `task_execution_finished`, `aion_ephemeral_recovery_started`,
`aion_ephemeral_recovery_failed`, `aion_ephemeral_recovery_finished`,
`mail_authorization_requested`, `mail_authorization_finished`, `mail_authorization_failed`, and
`mail_consent_revoked`; Telegram setup records fixed `telegram_configuration_requested/finished/
failed`, `telegram_test_requested/finished/failed`, and `telegram_disabled` transitions. Provider
setup records `provider_connection_requested/finished/failed`; local approval actions record
`approval_decision_requested/finished/failed`. Objective,
constraints, full plan text, workspace path, mail metadata, account identity, OAuth output,
Telegram token/chat ID, and generated mail summaries are not copied into ledger events; recovery
stores only purpose, path hash, ID-presence booleans, fixed outcomes, and a fixed failure reason.
Planning and dispatch failures persist only fixed versioned reason codes; arbitrary AionUi,
Paperclip, workflow, parser, path, or model exception text is neither returned by the API nor
written to the ledger. Runtime failure and status-unavailable messages are fixed local guidance.

When mail is not ready, the mail button opens a local setup dialog rather than becoming a dead
control. If the fixed gws Desktop OAuth client is absent, invalid, or permission-unsafe, the dialog
shows an explicit first step and does not render an actionable Gmail login button. A selected
Desktop client JSON is accepted only with a private-storage acknowledgement, then validated and
atomically published without exposing its values. Two separate checkboxes then bind Gmail readonly
OAuth and the exact metadata fields sent to the currently selected AI provider; the OAuth action remains
disabled until both are checked. The backend accepts only literal true acknowledgements and the
fixed readonly Gmail login command.
Successful re-verification atomically activates the adapter without rewriting user `config.yaml`;
the same dialog can revoke future access. A summary uses an ephemeral Plan Mode team and a unique
private workspace; only message count and summary hash enter the ledger. Team or workspace cleanup
failure rejects the summary instead of releasing potentially residue-backed output.

Telegram setup is also local and explicit. Token and chat ID use password inputs and are cleared
from frontend state after successful storage or whenever the dialog closes. The backend accepts them only with a literal-true
private-storage acknowledgement, delegates validation and atomic merge to the existing `0600`
`secrets.yaml` boundary, serializes configure/test/disable operations, and never returns either
value. Sending a fixed test message requires a separate literal-true action acknowledgement and
durable `telegram_test_requested` evidence before network access. Removing credentials is local
and safety-first: future sends are disabled even if the final audit append is unavailable. Values
provided by environment variables are reported as externally managed and cannot be overwritten or
deleted by the console.

## Local security boundary

- loopback-only bind and loopback-only AionUi URL;
- no CORS and no API documentation routes;
- random bootstrap CSRF token on every modifying request;
- exact local Origin checks and JSON content-type enforcement;
- CSP, frame denial, nosniff, no-referrer, and no-store headers;
- private `0700` directories and atomic `0600` plan records;
- unique `0700` AionUi workspaces per planning or mail request, removed together with the Team;
- no credentials in frontend state, plan prompts, Paperclip metadata, or ledger payloads.
- no third-party exception text in plan records, dashboard state, or ledger payloads.
- fixed vendor login argv only; provider subprocess output is discarded and never becomes API data;
- approval mutation requires loopback Origin, CSRF, JSON, an explicit review acknowledgement, and
  an exact pending UUID.

Quarterdeck is the approval-decision surface. Before calling Paperclip's fixed approve/reject API,
it fsyncs `approval_decision_requested`; afterward it records a fixed outcome. The optional note is
sent to the governance record but only its SHA-256 is written to the local ledger. The authoritative
local actor in version 1 is `local_console`: this is a single-user loopback boundary, not a claim of
multi-user identity or Paperclip-authenticated human identity. The standalone Paperclip MCP remains
unmounted in AionUi. Existing Quarterdeck gate and allowlist rules remain authoritative.

## Rejected alternatives

- **A second general control plane or DAG editor:** duplicates Paperclip/LangGraph and expands the
  security surface.
- **Direct execution from the task prompt:** removes the review contract and permits plan swapping.
- **AionUi side-question API:** the pinned build exposes only a placeholder; normal ephemeral Team
  sessions provide a testable versioned API.
- **A long-lived universal planner team:** retains unnecessary conversation state and increases
  cross-task data leakage.
- **Treating agent completion as outcome success:** contradicts the execution/outcome evidence law.
- **Embedding AionUi or Paperclip as user-facing pages:** leaks implementation topology and turns
  replaceable adapters into product navigation.
- **A generic API-key editor:** expands secret custody and confuses consumer login with API billing;
  vendor-owned login flows preserve the intended authentication boundary.

## Consequences

The operator gets one concise Quarterdeck surface while Paperclip, AionUi, launchd, and provider
CLIs keep their existing ownership boundaries behind it. The default Workspace reduces task creation to one clear
description-and-confirm flow while the dashboard, task, evidence, and integration views remain
separate; approvals are available in the same shell. The frontend adds a packaging and
responsive-layout test surface, but no new orchestration authority. Vertical practitioner UI
remains a separate private product and is still blocked by the paid-design-partner gate.
