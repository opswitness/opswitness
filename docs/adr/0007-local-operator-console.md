# ADR-0007: A local operator console composes AionUi and Paperclip

Status: accepted

## Context

Paperclip is the governance system of record and AionUi is the planning/conversation/agent
runtime surface. Their specialist interfaces are useful, but daily operators still need one
quiet local entry for fleet health, evidence, integrations, mail summary, and new work. New work
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

It binds only to `127.0.0.1` and delegates through narrow local adapters:

1. Read-only dashboard data comes from the local ledger/index, Paperclip health/approvals, AionUi
   health, and the metadata-only mail readiness check.
2. A new task first creates an ephemeral AionUi Team in Plan Mode. The planner receives no tools
   and must return a versioned strict JSON plan with at most five agents and exactly one lead.
3. Quarterdeck validates the plan, stores its full text only in a private local plan store, and
   appends request/plan hashes plus non-sensitive structure to the authoritative ledger.
4. The review UI displays the exact `plan_sha256`, calculated over the objective, constraints,
   workspace, preferred cadence, and validated plan. Confirmation with any other hash is rejected.
5. Quarterdeck recomputes that execution-envelope hash at confirmation and immediately before
   dispatch, then fsyncs `task_plan_confirmed` before creating external side effects. It then creates
   or reconciles a Paperclip issue and either starts a registered allowlisted workflow or creates
   an AionUi execution Team from the confirmed agent architecture.
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

Startup recovery follows the external-side-effect boundary rather than guessing. A durable
`confirmed` record is safe to enqueue again because dispatch first acquires a per-plan atomic claim;
`running` and `awaiting_approval` records are refreshed without replay. A stranded `planning` record
may own an unreconciled ephemeral Team, while a stranded `dispatching` record may already have
created a Paperclip issue, AionUi Team, or workflow run. Those two states therefore fail closed with
fixed `planning_interrupted_by_restart` or `execution_dispatch_interrupted` evidence and require a
new plan after operator inspection. No startup path blindly repeats an ambiguous external effect.

## Evidence and privacy

The ledger records `task_plan_requested`, `task_plan_drafted`, `task_plan_failed`,
`task_plan_confirmed`, `task_execution_requested`, `task_execution_dispatched`,
`task_execution_failed`, and `task_execution_finished`. Objective, constraints, full plan text,
mail metadata, and generated mail summaries are not copied into ledger events.
Planning and dispatch failures persist only fixed versioned reason codes; arbitrary AionUi,
Paperclip, workflow, parser, path, or model exception text is neither returned by the API nor
written to the ledger. Runtime failure and status-unavailable messages are fixed local guidance.

The mail button remains disabled until the existing fixed-query Gmail readonly adapter, encrypted
OAuth, and explicit model-metadata consent are all ready. A summary uses an ephemeral Plan Mode
team; only message count and summary hash enter the ledger.

## Local security boundary

- loopback-only bind and loopback-only AionUi URL;
- no CORS and no API documentation routes;
- random bootstrap CSRF token on every modifying request;
- exact local Origin checks and JSON content-type enforcement;
- CSP, frame denial, nosniff, no-referrer, and no-store headers;
- private `0700` directories and atomic `0600` plan records;
- no credentials in frontend state, plan prompts, Paperclip metadata, or ledger payloads.
- no third-party exception text in plan records, dashboard state, or ledger payloads.

Paperclip Web UI remains the sole approval-decision surface. The standalone Paperclip MCP remains
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

## Consequences

The operator gets one concise daily surface while Paperclip, AionUi, launchd, and Quarterdeck keep
their existing ownership boundaries. The frontend adds a packaging and responsive-layout test
surface, but no new orchestration authority. Vertical practitioner UI remains a separate private
product and is still blocked by the paid-design-partner gate.
