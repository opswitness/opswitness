# ADR-0007: OpsWitness is the sole local operator surface

Status: accepted

## Context

Paperclip is the governance system of record and AionUi is a replaceable planning/agent adapter.
They remain internal implementation components. Daily operators need one quiet OpsWitness entry
for fleet health, evidence, approvals, AI connections, mail summary, and new work. New work
must not jump directly from a sentence into execution: the operator needs to review the objective,
agent architecture, stages, cadence, checkpoints, artifacts, and risks first.

Building another control plane, DAG engine, scheduler, or agent runtime would violate the wheel
test. Giving either AionUi or Paperclip unrestricted cross-system credentials would also collapse
the existing trust boundaries.

## Decision

OpsWitness ships a thin FastAPI + React operator console, started with:

```bash
qd console serve --open
```

This console is the sole ordinary product door. Users connect ChatGPT/OpenAI, Claude, DeepSeek,
Grok/xAI, Ollama, or LM Studio, plan and run tasks, review approvals, and inspect evidence without opening AionUi or Paperclip. Those names
appear only inside a closed advanced-diagnostics disclosure. OpsWitness still delegates to their
versioned local APIs and does not absorb their planner, agent runtime, governance state machine, or
database.

English is the first-run interface default. The ordinary **Settings** view exposes an English/中文
segmented control whose value is stored under a versioned browser-local key. Language selection is
presentation state only: it is not sent to FastAPI, written to the ledger, included in a plan hash,
or used to translate user-authored objectives, generated plans, evidence, or provider errors. Fixed
product navigation, controls, statuses, and consent/safety copy follow the selected language. An
absent, inaccessible, or unknown preference fails to English.

Provider connection is real, local, and credential-minimizing. OpsWitness probes the installed
vendor CLIs with fixed argv (`codex login status`, `claude auth status --json`) and exposes only a
sanitized readiness result. ChatGPT login, local single-user Claude subscription login, and
Anthropic Console API login use their vendors' fixed flows (`codex login`, `claude auth login
--claudeai`, `claude auth login --console`). OpenAI also has one narrow API-key path: a
loopback, CSRF-protected request accepts the key only for the current connection attempt, passes it
through stdin to the fixed `codex login --with-api-key` command, then discards it. OpsWitness never
logs, echoes, places in argv, or writes to evidence an OpenAI/Anthropic password, browser cookie,
OAuth token, or API key. Anthropic has a separate persistent API-key path because Claude Code has no
equivalent stdin login command: the operator must explicitly confirm storage and usage billing; the
key is validated against the read-only Models API, passed through stdin to macOS Keychain, and
made available through a fixed executable `apiKeyHelper`. The helper path, provider, method, and
outcome may be evidence; the key may not. Existing non-OpsWitness `apiKeyHelper` configuration is
never overwritten. Claude subscription login is limited to the operator's own local session;
hosted or multi-user product execution must use Anthropic API billing.

DeepSeek and xAI use separate persistent API-key paths. Each key is validated only against the
provider's fixed Models endpoint, passed to macOS Keychain through stdin, and represented by a
OpsWitness-owned non-secret helper. It is never submitted to AionUi: the pinned AionUi provider
endpoint returns submitted credentials in its response and therefore cannot satisfy this boundary.
Grok account login is allowed only through the official Grok Build `grok login` browser flow; no
browser cookie, consumer token, or password crosses OpsWitness. The xAI account may be shared by
Grok and the developer console, but API usage has separate billing. Provider authentication and
Agent runtime readiness remain distinct. Until reviewed DeepSeek and Grok execution adapters pass
acceptance, these connections are visible as credential-ready but absent from runtime choices.

Local model connection is a separate, credential-free contract. Ollama and LM Studio are the only
version-1 local providers. OpsWitness probes compile-time fixed loopback endpoints, requires an
explicit confirmation before starting either vendor service, and accepts neither a custom URL nor a
local API key. It extracts only bounded model names and registers them in AionUi as OpenAI-compatible
Custom providers at fixed `/v1` URLs. AionUi receives the literal non-secret placeholders `ollama`
or `lm-studio`, never a user credential. Registration is reconciled by fixed provider id or exact
loopback URL. A local runtime is ready only when the server responds, at least one model is present,
the provider is registered and enabled, and the configured `aion_cli` Assistant is enabled and
team-selectable. Installation, process presence, or provider registration alone can never turn the
runtime green.

The entry route is deterministic: **Workspace** remains the default route and a permanent top-level
navigation item for every user. It is a deliberately small chat-first entry. The operator describes one outcome in plain
language; the same existing planning contract renders an AI-expanded six-section execution brief plus
the proposed Agent architecture, runtime recommendation, stages, cadence, checkpoints, artifacts,
and risks inline. The brief must state the goal, inputs and boundaries, method and roles,
checkpoints, deliverables, and exclusions. Confirmation stays in the chatbox. **Today** remains an
optional action-first model but is temporarily hidden from top-level navigation; legacy Today
targets resolve to Workspace. When restored, it presents approval decisions, failed or
blocked work, coverage or projection concerns, observable active teams, mail summary, and a compact
new-task entry come before technical service details. The operator can replan or confirm the
hash-bound proposal without moving through a separate task drawer. This is a presentation layer over
the existing plan state machine, not a direct chat-to-run path and not a second conversation or
orchestration backend.

The panel currently labelled **Task teams** inside Today is a read-only active-work summary, not a
second task or team object. It folds the same immutable plan ids used by Work and includes only
`confirmed`, `dispatching`, `running`, `awaiting_approval`, and `awaiting_input` records. Its member badges are bounded
adapter observations and never grant edit authority or imply outcome success. All hierarchy,
collaboration-loop, runtime/model, activity, output, blueprint, and deletion operations remain under
the selected Work item.

An active Work overview refreshes its execution detail every 2.5 seconds and renders only bounded,
verifiable runtime progress: an exactly mapped active Agent slot, observed duration, slow/blocked
state, and a recent activity timeline containing Agent name, strict tool identifier, tool status,
timestamp, and collapsed count. Text responses contribute only a `response_observed` marker. The
pinned AionUi runtime also exposes structured team work-item create/update records. OpsWitness binds
those task IDs to the immutable plan stages, folds pending/running/blocked/completed/failed state, and
attaches only the same content-free runtime activity observed between each stage's start and finish.
New dispatch prompts require exact `[QD-STAGE:<order>] <title>` subjects; existing runs use a strict,
unambiguous title match. Missing or ambiguous mappings remain `unobserved` or `unknown` and fail
closed. Tool arguments, outputs, task descriptions, message bodies, arbitrary titles,
chain-of-thought, and inferred percentages never cross the adapter boundary. Agent-reported stage
completion is execution telemetry and never implies business outcome success. A legacy
`completed_unverified` record with no progress snapshot may perform one
read-only adapter backfill; that operation cannot rewrite terminal status, append a second finish
event, or rerun the task. Failed records are never backfilled this way.

`Run again` is a review action, not an execution shortcut. It is available only for failed or
`completed_unverified` work with an intact reviewed plan. The action creates an idempotent ready
child version containing the same plan, the default `automatic` approval mode, parent hash, a new
version number, and a new confirmation hash. It appends `task_plan_rerun_prepared` without task
plaintext and makes no AionUi or Paperclip dispatch call. The operator may opt into manual approval,
then must review and confirm the new hash before a new execution can start.

`Fork work` is a separate identity operation available for any intact reviewed plan, including an
active source. It creates a version-1 top-level Work rather than a `parent_plan_id` child, so Work
selection never collapses it into the source. The copied plan, team, and settings are unchanged, but
`forked_from_plan_id` and `forked_from_plan_sha256` are added to the execution envelope and therefore
produce a distinct confirmation hash. The append-only `task_plan_forked` event stores only ids,
hashes, schema, and approval mode. Execution state, approvals, operator questions/answers, artifacts,
and outcome evidence are deliberately absent. The new Work defaults to `automatic`, opens in
Workspace review, and cannot dispatch until the operator confirms its own hash.

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
3. OpsWitness validates the plan, stores its full text only in a private local plan store, and
   appends request/plan hashes plus non-sensitive structure to the authoritative ledger.
4. The review UI displays the exact `plan_sha256`, calculated over the objective, constraints,
   workspace, preferred cadence, and validated plan. Confirmation with any other hash is rejected.
5. OpsWitness recomputes that execution-envelope hash at confirmation and immediately before
   dispatch, then fsyncs `task_plan_confirmed` before creating external side effects. It then creates
   or reconciles a Paperclip issue and either starts a registered allowlisted workflow or creates
   an AionUi execution Team from the confirmed agent architecture. These are hidden adapter calls;
   the operator remains in OpsWitness.
6. Runtime completion is `completed_unverified`. Artifact, eval, or human sign-off is required to
   prove a business outcome.

The plan's cadence is the proposed update/reporting cadence. Version 1 confirmation launches one
managed run only; it never silently installs a recurring schedule. A recurring AionUi task,
Paperclip routine, or launchd definition requires a separate explicit registration and approval.

The planner receives a sanitized local runtime capability table and recommends one available runtime
and advertised model id per Agent with a short reason. Claude options come from AionUi's managed
adapter metadata, Codex options from its public local model metadata cache, and local options from
the currently ready Ollama or LM Studio provider; credentials and raw adapter rows never cross the
console API. Before confirmation, the operator can replace every runtime and model assignment. This
is a structured plan revision, not an in-place edit: it creates a child plan bound to the parent
hash, stores the complete assignment set, recomputes the execution envelope, and requires fresh
confirmation. Exact model ids, rolling aliases, and the unpinned runtime default are distinct
states. An unavailable runtime, unadvertised model, incomplete assignment set, or unknown Agent is
rejected. Dispatch passes the hash-bound model id and does not auto-fallback.

Task changes are chat-first. The operator describes a desired change, such as returning a failed
citation check to a named Agent for at most two iterations, and OpsWitness uses the same immutable
revision contract to draft a complete replacement plan. It cannot mutate or dispatch the reviewed
plan. The hierarchy/loop graph remains an explicitly labelled advanced manual editor for cases where
the operator needs to set an exact relationship or iteration limit directly.

The empty **Workspace** exposes a static, searchable bilingual catalog of 27
common task presets grouped into
operations, research and decision support, growth, customer operations, and specialist workflows.
A preset is only an authored objective with conservative approval and side-effect constraints.
Category and full-text filtering operate entirely over the in-browser static catalog and send no
query to the backend. Choosing one sets the browser-local composer text and closes the catalog; it
does not call the planning API, create a private plan record, select a runtime, or dispatch work.
The operator can edit the text and must still request a complete AI plan, review it, adjust runtime
assignments if needed, and confirm its exact hash. Presets contain no credentials or user data, are
not TeamBlueprints, and cannot instantiate persistent employees. The Bazi demonstration preset is fixed to synthetic `DEMO-001`,
deterministic `lunar-python` charting, knowledge-bound AI interpretation, human sign-off, and no
delivery or real-person data.

Workspace also exposes **My task templates** next to the static catalog. A TaskTemplate is
separate from a TeamBlueprint: it stores an operator-authored display name and task objective, not
Agent topology. Records live only under the private console state directory as mode-`0600` JSON;
save and archive transitions require CSRF plus explicit confirmation and append hash-only ledger
events. The ledger never receives the template name or objective. Search is browser-local, deletion
is a recoverable archive transition, and selecting a template only fills the composer. Neither save
nor selection may invoke planning, confirmation, Paperclip, AionUi, or an Agent runtime.

The top-level **Work** view deliberately combines the former Tasks and Team navigation because both
were lists of the same plan-scoped object. It does not combine their storage models. A work item is
the operator's goal and current plan version; its Team tab is the plan-scoped hierarchy and
collaboration graph; Activity is evidence-only execution telemetry; Outputs separates expected
artifacts from verified outcome evidence; Settings owns blueprint saving and visibility deletion.
Each run remains independently identified.

History is not a separate top-level product object. A selected Work item's **Activity** tab owns the
bounded signals for its current execution; its **History** tab owns the immutable run chain and each
run's ledger timeline. Wrapped system automation that cannot be assigned to one Work item remains
visible only in the collapsed **Settings → Advanced diagnostics** section. This is a navigation
merge, not evidence deletion: append-only events, tombstones, run IDs, and retention semantics
remain unchanged.

An ended Aion run may expose **Continue this run** only when OpsWitness can prove the exact team and
one conversation mapping for every planned Agent and the current Work leaf is also terminal. The
operator's follow-up creates a new immutable child version rather than reopening or mutating the
selected run. Its parent is the current leaf; `continued_from_plan_id`, source hash, follow-up hash,
and new plan hash preserve source intent even when an older run is selected. Plaintext goes only to
the same local Aion team and is absent from the ledger and API history. A marker reconciles an
accepted-but-unacknowledged send; absence of either the marker or a confirmed run identity makes the
new child fail. There is no new-team dispatch, workflow continuation, runtime fallback, or implicit
branch. Shared-conversation telemetry is cut at the new run's dispatch timestamp and old stage
bindings are not reused, so continuation cannot inherit an earlier run's apparent progress.

Workspace adds a third **Team blueprints** entry while keeping TeamBlueprints separate from both work items and task templates. A
**TeamBlueprint** is a private, versioned reusable planning
input containing only Agent role keys, reporting edges, collaboration-edge limits, runtime
preferences, source plan identity/hash, creation time, and a verification label. It contains no
credentials, plan body, outside data, conversation transcript, or persistent employee identity. The
operator can manually save it only from a non-active task; a completed task has `verified` status
only where outcome evidence exists, otherwise it is explicitly unverified. OpsWitness never
auto-saves, overwrites, enables, or instantiates a blueprint. Reusing one still generates and reviews
a full new plan and requires a new hash confirmation.

Member telemetry is advisory evidence only. The local adapter may return a timestamp and one of
`activity_observed`, `response_observed`, `unobserved`, or `unavailable`, with no message body,
tool content, chain-of-thought, percentage complete, or outcome claim. Missing telemetry renders as
unobserved; unavailable telemetry renders as unavailable. Execution and outcome evidence retain
their existing independent meanings.

The state transition is:

```text
planning -> ready -> confirmed -> dispatching -> running
                                      |          |  |  |  |
                                      v          |  |  |  +-> completed_unverified
                                    failed       |  |  +----> awaiting_approval -> running
                                                 |  +------> awaiting_input ----> running
                                                 +---------> pause_requested -> paused -> resuming -> running
                                                 +---------> cancel_requested -> cancelled
```

Pause, resume, and cancel are evidence-first Aion team transitions. OpsWitness appends and fsyncs
the request before invoking the public adapter endpoint. A pause is complete only when all active
Agent slots report paused. Continue sends a fixed request marker into the same Team and binds the
new run id to the unchanged confirmed plan hash. Cancel remains `cancel_requested` until the exact
run is observed inactive or terminal; an accepted cancel request is not sufficient proof. Runtime
errors leave the requested state visible with a sanitized control warning. Pause is cooperative and
does not claim OS-level process suspension. Workflow adapters do not expose controls without an
equivalent confirmable contract.

Work renders those controls as a stable three-position group: Start/Continue, Pause, and End.
Running work disables Start and enables Pause; runtime-confirmed paused work enables Continue and
disables Pause; approval/input waits disable both while retaining End. Pending start, pause, and end
states stay visibly pending. The Start/Continue position never confirms a new plan: initial execution
still requires the ordinary reviewed plan hash and explicit Workspace confirmation.

There is no auto-confirm path. Approval mode applies only after the operator confirms the exact plan
hash. New plans and reviewed reruns default to `automatic`, which supplies a single-use decision
for each AionUi tool confirmation without another operator click. The Paperclip approval object,
local policy decision, and runtime delivery evidence are still created before execution continues.
A review switch selects `manual_all`; each execution tool then pauses for a human decision.
Existing `automatic_safe` records preserve their fixed versioned exact-name read-only/internal
allowlist, and a legacy plan without a stored mode remains manual. The side-effect-free
`qd_request_input` notification remains available in every mode so requesting operator data cannot
deadlock behind a second approval.

That confirmed value remains the immutable initial-policy snapshot. During an active Aion team run,
the Work overview may change only `ExecutionState.approval_mode`. The write API requires the
expected current mode and `confirmed=true`; switching to `manual_all` tightens immediately, while
switching to `automatic` requires a dedicated UI confirmation and applies only to future tool
requests. Every approval payload captures `qdApprovalModeAtRequest` and its bounded automatic
reason. Consequently, enabling Auto cannot consume a call that was already paused under manual
policy. A mode change writes `task_approval_mode_change_requested` before state mutation and
`task_approval_mode_changed` after it; the plan content and hash are unchanged. If a crash leaves
the request without terminal evidence, startup recovery selects the more restrictive of the old
and requested modes and appends `task_approval_mode_change_recovered`.

Manual attention is task-local. OpsWitness exposes an Aion approval inside Work only when its
OpsWitness source marker is exact, its `planId` resolves to an existing private plan, and that id
matches the displayed Work item. The redacted request, risks, approve/reject choice, optional note,
and explicit review acknowledgement are completed inline. The global Approval view remains an
aggregate queue and recovery surface; it is not the ordinary continuation path for one task.

An active AionUi execution may hold one pending `RuntimeInputRequest`, bound to the confirmed
`plan_id` and an exact planned Agent name. The question and optional choices live only in the
private plan store. The Agent stops after requesting input; Work and Today render
`awaiting_input`. The operator answer is delivered to the same AionUi team with a stable request
marker, so a lost acknowledgement can reconcile without blind resend. The answer does not revise
the plan or hash. Questions and answers are explicitly untrusted task data and must not contain
secrets. If manual governance pauses `qd_request_input` itself, the inline approval occupies the
same attention slot first; after allow-once delivery, the resulting question and suggested answers
replace it without a page transition.

A pending input may refer to a reviewable runtime attachment only by an exact, single-level
`artifacts/<filename>` token in that request's stored question. The console lists only those bound
names and offers an inline read-only preview for regular UTF-8 JSON files no larger than the fixed
preview limit. It opens the artifacts directory and file without following symlinks, recomputes the
content SHA-256, and returns a relative display name rather than a host path. An unmentioned name,
path traversal, symlink, oversized file, invalid JSON, or changed-while-reading file fails closed.
The UI labels candidate state and source boundaries; viewing never records approval or signoff and
does not promote the execution workspace file into authoritative CAS outcome evidence.

A ready plan offers two distinct actions. **Modify plan** accepts a
bounded change instruction and creates a new child `plan_id`; the previous plan, its hash, and its
private record remain unchanged. The child stores `parent_plan_id`, the exact parent hash, a
monotonic revision number, and the private instruction, while the ledger receives only the
instruction SHA-256. The planner receives the complete previous plan plus the requested delta,
must return a complete replacement plan rather than a patch, and may not return an identical plan.
The UI shows the changed structural sections before confirmation. While a non-failed child exists,
the parent cannot be confirmed. The child receives a new execution-envelope hash and requires a
fresh checkbox confirmation. **Start over** alone clears the current presentation and creates an
unrelated root plan from a blank composer.
Forking is neither action: it preserves explicit source provenance while starting an independent
Work identity. Later modifications of that fork use the ordinary parent/child revision contract
within the new Work.

The **Team tab inside Work** renders the selected task team as a responsive organization chart. A legacy plan
with no explicit reporting fields is interpreted as one lead with every teammate reporting directly
to that lead, without rewriting the private plan file or changing its historical hash. A ready plan
may assign each non-lead employee one exact direct manager. The graph must have one lead root, cover
every agent exactly once, and remain acyclic. The current plan contract permits one to five Agents,
so a valid chain may render up to five reporting levels. The advanced editor only reassigns existing
Agents; adding or removing roles goes through a full chat-first plan revision and fresh confirmation.

Iterative collaboration is a separate graph. A ready plan may define up to five directed loops using
exact agent names, including a self-loop for bounded self-review or cycles between multiple agents.
Every loop carries a user-editable return/stop condition and an integer `max_iterations` from 1 to
10. Workflow plans cannot override their runtime with these loops. Saving never patches the reviewed
plan: OpsWitness creates an immediately reviewable child version, binds the complete reporting tree
and loop contracts into its new execution-envelope hash, and records only `organization_sha256`,
counts, and non-sensitive version metadata in `task_plan_organization_revised`. Confirmed or active
organizations are read-only. The effective tree and bounded loops are included in the Paperclip issue
and AionUi execution contract. The pinned AionUi Team API does not expose a verifiable round-limit
parameter, so version 1 labels the cap as plan-level constraint, not deterministic runtime cutoff.
AionUi remains the executor and Paperclip remains the governance plane, so the console does not
become an employee database or agent runtime.

**Delete task** is a visibility tombstone, not record destruction. It is allowed only for `ready`,
`failed`, `cancelled`, or `completed_unverified` plans. Planning, confirmed, dispatching, running,
approval-waiting, and input-waiting work must first reach a terminal state; a parent with any visible child revision
must be deleted child-first. OpsWitness fsyncs one idempotent `task_plan_deleted` event containing
only non-sensitive identity/hash metadata. The private plan file, execution evidence, artifacts,
and governance records remain unchanged, while ordinary list/get/recovery paths fold the event and
hide the plan. This makes a crash after deletion unambiguous and prevents the UI from becoming an
evidence eraser.

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
`running`, `awaiting_approval`, and `awaiting_input` records are refreshed without replay. A stranded `planning` record
may own an unreconciled ephemeral Team, while a stranded `dispatching` record may already have
created a Paperclip issue, AionUi Team, or workflow run. Those two states therefore fail closed with
fixed `planning_interrupted_by_restart` or `execution_dispatch_interrupted` evidence and require a
new plan after operator inspection. No startup path blindly repeats an ambiguous external effect.
Before recovery starts, the process holds a non-blocking exclusive `console.lease` for the private
state directory. A second port or process therefore cannot inspect or mutate the same plan state;
graceful shutdown waits for background work before releasing the lease.

Before the Team POST, OpsWitness fsyncs a `0600` marker containing only the request owner,
purpose, exact workspace, and optional Team ID. Team creation is then bound atomically to that
marker. On startup, while holding the exclusive console lease, OpsWitness records recovery intent,
lists AionUi Teams, requires one exact workspace + expected-name + optional-ID match, deletes only
that Team, lists again to prove absence, removes the local workspace, and records completion. A
missing or malformed marker, insecure permissions, multiple matches, identity drift, unavailable
AionUi, unconfirmed deletion, or unavailable audit ledger refuses startup. There is no prefix-based
or bulk Team deletion.

A machine crash before the initial marker is published can leave an unmarked local directory, but
cannot follow the later Team POST in OpsWitness's program order. That directory is not deleted by
guesswork: startup stops for operator inspection. Interrupted planning remains failed separately;
cleanup recovery does not replay planning or execution.

## Evidence and privacy

The ledger records `task_plan_requested`, `task_plan_revision_requested`,
`task_plan_organization_revised`, `task_plan_runtime_revised`, `task_plan_drafted`, `task_plan_failed`,
`task_plan_confirmed`, `task_plan_deleted`, `task_execution_requested`, `task_execution_dispatched`,
`task_input_requested`, `task_input_answered`, `task_input_delivered`,
`task_execution_failed`, `task_execution_finished`, `aion_ephemeral_recovery_started`,
`aion_ephemeral_recovery_failed`, `aion_ephemeral_recovery_finished`,
`mail_authorization_requested`, `mail_authorization_finished`, `mail_authorization_failed`, and
`mail_consent_revoked`; Telegram setup records fixed `telegram_configuration_requested/finished/
failed`, `telegram_test_requested/finished/failed`, and `telegram_disabled` transitions. Provider
setup records `provider_connection_requested/finished/failed`; local approval actions record
`approval_decision_requested/finished/failed`. AionUi tool confirmations additionally record
`aion_tool_gate_requested/linked/delivery_requested/delivery_finished` and, for exact safe-query
matches, `aion_tool_gate_auto_approved` with the policy version and fixed reason; failed delivery is written
as degraded `aion_tool_gate_delivery_failed` evidence and remains blocked for reconciliation. Question
and answer plaintext, objective,
constraints, full plan text, workspace path, mail metadata, account identity, OAuth output,
Telegram token/chat ID, and generated mail summaries are not copied into ledger events; recovery
stores only purpose, path hash, ID-presence booleans, fixed outcomes, and a fixed failure reason.
Planning and dispatch failures persist only fixed versioned reason codes; arbitrary AionUi,
Paperclip, workflow, parser, path, or model exception text is neither returned by the API nor
written to the ledger. Runtime failure and status-unavailable messages are fixed local guidance.
Blueprint actions append `team_blueprint_saved` and `team_blueprint_archived` with opaque local
identity, source hash, verification label, and topology counts only. Member-observation data remains
ephemeral dashboard state and is never upgraded into an outcome claim or copied as adapter content.

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

## Local-first security boundary

- loopback bind by default and an always-loopback AionUi URL;
- optional private exposure requires either direct browser-trusted TLS or one trusted loopback TLS
  terminator; plaintext private requests fail closed;
- the recommended Tailscale Serve mode keeps OpsWitness on `127.0.0.1` and trusts forwarded HTTPS
  only when the socket peer is loopback and the Host exactly matches configured `public_host`;
- private requests require a revocable `Secure`, `HttpOnly`, `SameSite=Strict` device cookie whose
  raw bearer value is never persisted; pairing codes are short-lived, single-use, rate-limited, and
  stored only as hashes;
- no CORS and no API documentation routes;
- random bootstrap CSRF token on every modifying request;
- exact same-origin checks and JSON content-type enforcement;
- CSP, frame denial, nosniff, no-referrer, and no-store headers;
- HSTS on effective private HTTPS and strict Host validation;
- PWA service-worker scope contains only versioned static assets, icons, manifest, and an offline
  notice; `/api/` is never intercepted or cached;
- private `0700` directories and atomic `0600` plan records;
- unique `0700` AionUi workspaces per planning or mail request, removed together with the Team;
- apart from a one-time OpenAI input held only for the current connection request, no credentials in
  persistent frontend state, plan prompts, Paperclip metadata, or ledger payloads;
- no third-party exception text in plan records, dashboard state, or ledger payloads.
- fixed vendor login argv only; OpenAI uses a one-time stdin handoff, Anthropic/DeepSeek/xAI use
  explicitly confirmed Keychain storage through stdin, and provider subprocess
  output is discarded and never becomes API data;
- approval mutation requires paired or local access, exact Origin, CSRF, JSON, an explicit review acknowledgement, and
  an exact pending UUID.

OpsWitness is the approval-decision surface. Before calling Paperclip's fixed approve/reject API,
it fsyncs `approval_decision_requested`; afterward it records a fixed outcome. The optional note is
sent to the governance record but only its SHA-256 is written to the local ledger. The authoritative
local actor in version 1 is `local_console`: this is a single-owner boundary, not a claim of
multi-user identity or Paperclip-authenticated human identity. A paired device is revocable access
material, not a new user account or proof of a particular human. The standalone Paperclip MCP remains
unmounted in AionUi. Existing OpsWitness gate and allowlist rules remain authoritative.

Paperclip v2026.707.0 permits approval resolution only for a `board` actor. In the pinned
`local_trusted` deployment, OpsWitness therefore keeps the service-agent bearer token on ordinary
projection calls but deliberately omits it for approve/reject only after an unauthenticated health
probe proves the exact API base is loopback and reports `deploymentMode=local_trusted`. A non-loopback
base or authenticated deployment fails closed; OpsWitness never relabels an agent token as a user
and never writes the Paperclip database directly.

For AionUi execution Teams, AionUi remains the component that physically pauses the tool call,
Paperclip remains the approval object and decision store, and OpsWitness binds both with the exact
plan, conversation, call, and request hash. The console exposes only allow-once and reject, always
sends `always_allow=false`, and retries delivery only after the Paperclip decision is durable. A
missing, changed, duplicated, or unreachable confirmation fails closed; a pending count alone is
never presented as an actionable approval. `automatic` and legacy `automatic_safe` use the same
path and truth split; the only difference is which snapshotted local policy, rather than a click,
supplies the single-use decision.

## Rejected alternatives

- **A second general control plane or DAG editor:** duplicates Paperclip/LangGraph and expands the
  security surface.
- **Direct execution from the task prompt:** removes the review contract and permits plan swapping.
- **AionUi side-question API:** the pinned build exposes only a placeholder; normal ephemeral Team
  sessions provide a testable versioned API.
- **A long-lived universal planner team:** retains unnecessary conversation state and increases
  cross-task data leakage.
- **Treating agent completion as outcome success:** contradicts the execution/outcome evidence law.
- **A global AI employee directory:** converts task-local adapters into a second identity system and
  creates stale implied authority. Reusable topology belongs in explicit private blueprints instead.
- **In-place runtime mutation or automatic runtime fallback:** makes an approved hash lie about what
  actually executed and hides local capability failures.
- **Embedding AionUi or Paperclip as user-facing pages:** leaks implementation topology and turns
  replaceable adapters into product navigation.
- **A generic API-key editor or key store:** expands secret custody and confuses consumer login with
  API billing. The sole OpenAI API option is a fixed, one-time handoff to the installed Codex CLI;
  it cannot store, query, reuse, or proxy a key.

## Consequences

The operator gets one concise OpsWitness surface while Paperclip, AionUi, launchd, and provider
CLIs keep their existing ownership boundaries behind it. Workspace remains the default chatbox and
reduces task creation to one clear description-and-confirm flow; Today provides an optional
evidence-based operating view rather than replacing that main entry. Task teams, manually saved blueprints, runtime revisions,
and member observations remain bounded presentation and planning constructs, not new orchestration,
identity, or outcome authority. The frontend adds a packaging and responsive-layout test surface,
but no new orchestration authority. Vertical practitioner UI remains a separate private product and
is still blocked by the paid-design-partner gate.
