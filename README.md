# OpsWitness

Website: [opswitness.com](https://opswitness.com/) ·
[Community Alpha prerelease](https://github.com/opswitness/opswitness/releases/tag/v0.1.0-alpha.1) ·
[Quickstart](docs/QUICKSTART.md) · [Support matrix](docs/SUPPORT-MATRIX.md)

The public alpha.1 DMG is available only for a small, informed friend test. It is ad-hoc signed,
not notarized, and older than the current development source. The complete OpsWitness console runs
locally on the operator's own Mac; the website is a download, product-information and feedback
surface, not a hosted SaaS.

> **Community Alpha boundary.** Do not use the public alpha.1 build for secrets, critical work or
> irreversible actions. New source-complete behavior still requires an exact rebuilt App,
> clean-install and first-Work acceptance, recovery validation and a fresh executable canary.
> OpsWitness is the public product identity. The former Quarterdeck name remains only for
> compatibility with existing local installations and immutable historical evidence.

**Turn one-off AI work into repeatable company operations.**

OpsWitness is a local-first AI workbench for a one-person company. Describe a goal, review the
proposed Agent team and workflow, confirm the exact plan, run it on your own Mac, and keep every
version, result, approval, and piece of evidence together.

It does not replace Claude, Codex, AionUi, Paperclip, or your existing automation. It gives those
systems one simple operator-facing workflow while keeping execution adapters replaceable and
evidence local.

> **OpsWitness 帮助一人公司把一个想法自动变成可重复的 AI 团队流程，并通过一键运行、版本历史和可验证结果长期经营。**

OpsWitness is the ordinary first door for a one-person company, not another coding assistant,
agent runtime, or control plane. An operator describes an outcome in the local console; OpsWitness
drafts a bounded team and execution plan, makes its cadence, risks, artifacts, and approval
checkpoints reviewable, and starts nothing until the exact plan is confirmed. It then delegates
execution to replaceable adapters such as AionUi, Claude Code, Codex, Paperclip, and existing
automation, while the local ledger remains the evidence authority for what actually ran.

The core object is a reusable **Work**, not a disposable chat. Work keeps the reviewed plan, Agent
architecture, immutable versions, independent run history, outputs, approvals, and provenance
together. The operator can prepare another run from one clear action, revise it as a new version,
or fork it into an independent Work without rebuilding the process from scratch. Run again still
returns to exact-plan confirmation before dispatch. New Work starts on the **Balanced** execution
profile; Run again prepares a **Fast** child version by default; **Deep** remains an explicit choice
for first-pass or complex work. A profile is never a runtime hint: OpsWitness resolves it to the
locally advertised model id for every Agent, writes those choices into a new immutable plan and
hash, and shows them before confirmation.

The operating model is `Work Blueprint -> Run -> Revision`. Workspace derives **My repeatable
Work** from the latest ended, intact version of each Work: one action prepares a new reviewable
child, but never dispatches it. Task templates still reuse objective wording only, while team
blueprints reuse role topology only. This keeps one obvious full-process reuse path without adding
a second mutable Work database.

Workspace also preserves **planning conversation history** as a read-only projection of immutable
Plan revision chains. Selecting an earlier conversation restores its latest intact Plan version to
review; it does not create, confirm, or run anything. The operator may save that exact reviewed
source as an objective-only task template. The template records the source Plan id and hash for
provenance, while team structure, runtime state, approvals, replies, artifacts, and evidence remain
outside the template. In the development source, a planning failure stays in that same
conversation: the failed attempt remains visible, its objective returns to the composer for
editing, and retry creates a new immutable child that reuses only the exact prior attachment
manifest. Earlier attempts remain above the current turn, and background refresh does not pull a
user away from history they are reading. This recovery behavior is not in the public alpha.1 DMG.

Before planning, the operator may attach up to five explicitly selected local materials (5 MiB each,
15 MiB total). Text, Markdown, CSV, JSON, and PDF receive bounded planning excerpts; Word, Excel,
and image files are visible to planning by metadata only. Every material is stored privately,
content-hashed into the immutable Plan identity, and revalidated before confirmation. The confirmed
Aion team receives hash-verified read-only copies in its execution workspace. File bodies and names
do not enter the append-only ledger; it records only the material count and manifest hash.

The source candidate also implements a private **Knowledge Hub** for material that should remain
available across Work. It provides named collections, one-time file/folder snapshots, streaming
SHA-256 deduplication into a separate input CAS, version relationships, citation-bound knowledge
card candidates, human approval, Chinese/English FTS5 search, and a hash-revalidated “Use in new
Work” path. Direct planning upload keeps the limits above; a library-backed draft may select up to
ten exact versions and 250 MiB, and still returns to ordinary plan review before it can run.
Optional local semantic search downloads one exact manifest-pinned model only after confirmation
and never falls back to a hosted embedding API. Offline `safe_partner` H5 export includes only
selected approved cards and redacted citation excerpts; a copied static export cannot be revoked
or given real recipient access control. See [Knowledge Hub](docs/KNOWLEDGE-HUB.md).

OpsWitness also keeps an Obsidian-compatible private **Workspace Memory** vault for process lessons
and sourced knowledge. Agents can propose candidates; only human-approved, immutable versions are
included read-only in a new planning snapshot. Approval, supersession, revocation, and rollback are
hash-bound ledger events, while the memory body stays in local `0600` Markdown files. History and
CAS artifacts do not become memory merely because they exist. See
[ADR-0008](docs/adr/0008-repeatable-work-and-auditable-workspace-memory.md).

The current source also implements the review-time **Agent Contract v2** surface: stable Agent IDs,
one-to-five Agent add/delete, six-page structured editing, per-Agent Memory selection, exact
OpsWitness-managed execution-envelope preview, JSON Pointer field diffs, immutable child versions,
and per-Agent tool policy enforcement over the mapped Aion approval bridge. In Aion-compatible
mode, file/data scope, handoffs, loop counts, retries, and timeouts remain execution instructions;
they are not filesystem or process isolation. A strict sequential coordinator and private-workspace
primitives exist, but no current Aion adapter satisfies the strict runtime protocol, so a Contract
that requires strict isolation is rejected before execution rather than silently downgraded. See
[From Skills to Structured Work](docs/STRUCTURED-WORK.md).

## Current release status

OpsWitness source and the bounded alpha.1 friend-test download are public:

- `opswitness.com` is live and links to the exact
  [`v0.1.0-alpha.1`](https://github.com/opswitness/opswitness/releases/tag/v0.1.0-alpha.1)
  GitHub Prerelease;
- the Apple Silicon DMG is ad-hoc signed and not notarized, so macOS displays an Apple verification
  warning; it is not an approved broad launch;
- the public alpha.1 binary predates the current onboarding, Agent Contract, Knowledge Hub and
  failed-planning recovery source;
- vendored-runtime redistribution review, an exact rebuilt App, clean installation, complete first
  Work, recovery validation and a new executable canary remain open for alpha.2;
- Agent Contract v2 is source-complete but has not passed a rebuilt Mac App, clean-machine first
  Work, recovery drill, or new executable canary; the strict runtime adapter remains unavailable.
- Knowledge Hub source is implemented but is not part of an approved public binary. Its exact
  App bundle, backup/restore drill, fresh-machine first Work, packaging license review, and new
  executable canary remain release gates.

The durable product goal and the simplicity tests for future features are recorded in
[PRODUCT-VISION.md](docs/PRODUCT-VISION.md).
Commercial packaging and its open-core boundary are recorded in
[COMMERCIALIZATION.md](docs/COMMERCIALIZATION.md).

## Community Alpha quickstart

For the bounded friend test, use the Apple Silicon Mac App described in
[Quickstart](docs/QUICKSTART.md). The wheel remains a developer/existing-user channel and requires
Python 3.12; PyPI publishing is intentionally not configured.

```bash
uv tool install --with mcp \
  https://github.com/opswitness/opswitness/releases/download/v0.1.0-alpha.1/opswitness-0.1.0a1-py3-none-any.whl
opswitness version
opswitness init
opswitness console serve --open
```

The primary command is `opswitness`. The compatibility command `qd` invokes the same entry
point through at least `v0.2.0`. See [Quickstart](docs/QUICKSTART.md),
[Support matrix](docs/SUPPORT-MATRIX.md), and
[Known limitations](docs/KNOWN-LIMITATIONS.md) before connecting real work.

After trying the Alpha, use the
[guided experience report](https://github.com/opswitness/opswitness/issues/new?template=alpha_experience.yml)
for onboarding and repeatable-Work feedback, the
[bug report](https://github.com/opswitness/opswitness/issues/new?template=bug_report.yml) for a
reproducible defect, or the
[feature request](https://github.com/opswitness/opswitness/issues/new?template=feature_request.yml)
for a bounded Community improvement. Never include credentials, private task text, or customer
data in a public issue.

It adds the three things the platforms don't cover:

| Module | What it does | Why it doesn't exist elsewhere |
|---|---|---|
| **`opswitness wrap`** | Zero-modification onboarding for launchd/cron jobs: runs land in a local append-only ledger (crash-safe JSONL + SQLite index) and are projected into Paperclip as issues/comments/work-products ([ADR-0001](docs/adr/0001-run-ledger-write-model.md)). Never breaks the wrapped job (offline spool, exit-code mirroring). | Paperclip's watchdog only verifies its *own* issue trees; external heartbeat runs are read-only by design — nothing monitors external scheduled scripts. |
| **`opswitness gate`** | Fail-closed, *tool-call-level* human approval for non-interactive Claude Code via the official PreToolUse defer contract: defer → Paperclip board decision → same-session resume. Every transition lands in the local evidence ledger. | Paperclip approvals are issue-level sign-offs ([#3017](https://github.com/paperclipai/paperclip/issues/3017) is open); hobby hooks have no independent evidence ledger behind them. |
| **`opswitness artifacts`** | Authoritative artifact events in the local ledger; queries served by the disposable SQLite index; content stored content-addressed (attachment / immutable blob); Paperclip work-products are a rebuildable projection. | Work-products carry no content hashes and no server-side idempotency (`externalId` has no unique constraint) — evidence-grade artifacts need an authority outside the platform. |
| **`opswitness console`** | Serves one local operator UI. The original chat-first **Workspace** remains the default top-level entry: describe an outcome, choose a common task, private template, or team blueprint, review the six-section brief and exact hash, then confirm without being redirected away. New plans default to evidence-recorded automatic single-use approval; a switch makes every execution tool manual. Manual approvals and bounded Agent questions share one task-local attention panel in **Work**: the operator reviews, approves/rejects, or replies without navigating away, while the global Approval view remains a cross-task queue. Active Aion team work keeps a fixed **Start/Continue · Pause · End** control group in its overview: only a runtime-confirmed pause enables Continue, End requires a second confirmation, and every request and confirmed transition is append-only. The same overview binds AionUi's structured team work items to the confirmed plan stages, showing each Agent's reported pending/running/blocked/completed state and a bounded content-free activity timeline. These are execution observations, never hidden reasoning or business-outcome proof. The optional **Today** action view is temporarily hidden from navigation while its backend summary remains available for later restoration. **Work** combines only the former Tasks and Team navigation for each goal, its task-scoped team, activity, outputs, and settings. Ended or terminated work exposes **Run again**, which preserves the reviewed structure while preparing a Fast, model-pinned, hash-bound child version and returns to confirmation without dispatching it. Any reviewed Work can instead be **forked** into an independent top-level Work: plan/team/settings are copied, source id/hash are bound into the new hash, and no run, approval, reply, or output state crosses the boundary. Task changes are chat-first and always create a new immutable plan version before execution. | AionUi and Paperclip each expose a useful specialist UI, but neither provides one evidence-aware entry for daily operations, plan review, organization review, and confirmed execution. The console delegates to both; it is not a second control plane or agent runtime. |
| **`opswitness workflow`** | Register a fixed, shell-free workflow once, then launch it asynchronously from AionUi's native **Run now** button. Dispatch order, single-workflow concurrency, and terminal state are ledger evidence. | AionUi supplies the button and agent session; OpsWitness supplies the command allowlist and evidence boundary. No second workflow engine or generic remote shell is built. |
| **`opswitness mail`** | Run one administrator-fixed Gmail query through pinned `gws`, returning only sender, subject, date, and message id. First-time setup privately imports a Google Desktop OAuth client, then binds Gmail readonly OAuth and model-metadata transmission to two explicit acknowledgements. Evidence contains counts and hashes, never mail fields, client secrets, or OAuth output. | AionUi supplies the model runtime and optional daily scheduler. OpsWitness revalidates the private Desktop client boundary, encrypted OAuth, live token, readonly scope, and explicit model-metadata consent; its isolated mail MCP exposes no fleet mutation, body, draft, send, delete, or runtime-query tool. |
| **`opswitness soak`** | Freeze a canary/soak cadence contract, then derive a nonzero-until-proven verdict from elapsed time, every trigger gap, terminal/degraded evidence, schedule drift, torn lines, and projection backlog ([ADR-0006](docs/adr/0006-append-only-soak-gates.md)). | A Markdown timestamp or one manual success cannot enforce a rollout gate. Start/reset/checkpoint are append-only; status is always recomputed from raw evidence. |

## Alpha candidate

The candidate being reviewed is centered on three ordinary surfaces:

1. **Workspace** - describe an outcome and review the generated team and plan.
2. **Work** - run, pause, resume, stop, rerun, fork, and inspect a repeatable process.
3. **Settings** - connect local model providers and inspect advanced diagnostics when needed.

The candidate includes immutable plan versions, execution history, readable results, approvals and
operator input, content-addressed artifacts, append-only evidence, reusable templates, team
blueprints, and approved Workspace memory.

- **Wrap, don't rewrite.** Your launchd plists, cron lines, and `claude -p` invocations stay exactly as they are.
- **Fail closed.** No decision means no. API unreachable means no. Expired means no.
- **Evidence over trust.** Append-only audit events, content-hashed artifacts, honest failure records.
- **Lifecycle is evidence.** Retirements and reversals are ledger events (`opswitness retire/unretire`),
  never mutable config that can erase a known job from coverage.
- **Elapsed gates are evidence.** `opswitness soak` freezes cadence at start/reset; changing grace or
  running once cannot manufacture a continuous canary or seven-day soak.
- **Your credentials stay yours.** The alpha.2 App exposes Codex connection only. Its Claude and
  Anthropic connection entry is hidden, it bundles no Claude Agent SDK/runtime, and it does not
  advertise Claude execution. Developer-source compatibility paths can still talk to a separately
  installed and authenticated `claude` CLI or validate an explicitly supplied Anthropic API Key,
  but those paths are not an alpha.2 App capability and are not a redistribution shortcut. The
  optional OpenAI API Key connection remains a
  one-time local stdin handoff to the installed Codex CLI. DeepSeek and xAI API Keys are validated
  against each provider's fixed Models endpoint and stored in separate macOS Keychain items; they
  are never copied into AionUi. Grok account login, when the official Grok Build CLI is installed,
  remains inside the vendor-owned `grok login` browser flow. Credential connection is shown
  separately from task-runtime readiness: DeepSeek/Grok are not selectable for Agents until a
  reviewed execution adapter exists. Ollama and LM Studio are separate local-model connections:
  OpsWitness probes only their fixed loopback APIs, requires explicit confirmation before starting
  either service, and registers detected model names with the hidden AionUi adapter using a
  non-secret placeholder. No arbitrary endpoint or real local-model key is accepted. The local
  runtime is selectable only when the server is online, at least one model is present, the provider
  registration is reconciled, and the team-selectable local Assistant is ready. Hosted/product
  deployments must use API keys rather than consumer-account credentials.
- **Notification secrets never become evidence.** Telegram token and chat ID use password inputs
  and private `secrets.yaml`; the ledger records only fixed configuration/test transitions.
- **Launch is not a shell.** AionUi can start only ids in the local `0600` workflow manifest;
  it cannot submit paths, commands, environment variables, or runtime arguments.
- **Mail is untrusted data, never an instruction.** Mail checks use one fixed local query and
  metadata-only OAuth access. Automatic sending and drafting are outside this surface.
- **Plan before execution.** Drafting runs without tools. No Paperclip issue, AionUi execution
  team, or allowlisted workflow starts until the operator confirms the exact plan hash.
- **Runtime and model choice are reviewable.** Each Agent can use a different Claude, Codex, or
  local runtime and one model id advertised by that runtime. The two-level change is allowed only
  before confirmation and creates a hash-bound child plan after local availability validation; it
  never mutates a reviewed plan or silently falls back. The UI distinguishes an exact model id from
  a rolling alias and from the unpinned runtime default. Fast, Balanced, and Deep are review-time
  presets over this same mechanism, not hidden routing: applying one creates another immutable child
  version and manual per-Agent edits mark the version Custom.
- **Teams are task-scoped.** A reusable team blueprint contains only role topology and runtime
  preference. It is manually saved, versioned locally, and never creates a global employee record.
- **Memory is candidate-first.** History and artifacts remain evidence, not future instructions.
  Agents may propose process or knowledge memory, but only a human-approved immutable snapshot can
  enter planning; revoke, supersede, and rollback remain attributable ledger events.
- **Observed activity is not a result.** A team member may be labeled observed, responded,
  unobserved, or unavailable. None of those labels proves business outcome success.
- **Management is not iteration.** Direct reporting remains one acyclic tree. Review loops are
  separate, bounded, hash-bound contracts and must never be presented as stronger enforcement than
  the active execution adapter can prove.

OpsWitness remains a single-operator, local-first Alpha. It does not claim autonomous business
outcomes, hosted SaaS, multi-user identity, or stable durability. Regulated workflows must produce
reviewable evidence packages for a qualified human decision-maker; OpsWitness is not the licensed
professional and does not submit, pay, file, bind, or send on the operator's behalf by default.

## Compatibility

```bash
opswitness console serve --open
```

The console defaults to `127.0.0.1` (port `8765`). Private-network access is an explicit second
mode: browser-trusted HTTPS and a revocable paired-device credential are both mandatory, while
AionUi, Paperclip, and provider CLIs remain loopback-only. OpsWitness can sit behind a trusted
loopback Tailscale Serve proxy (recommended) or terminate a supplied certificate directly. The
installable PWA caches only versioned static assets and an honest offline page; API, task, approval,
mail, and evidence responses always stay network-only. See
[Private HTTPS, device pairing, and PWA](docs/private-console.md).

Every session enters the chat-first **Workspace** by default: one plain-language task description becomes an
inline execution brief with a proposed Agent team, runtime and model recommendation, stages, cadence,
checkpoints, artifacts, and risks. While planning, the page shows persisted external stages, elapsed
time, and a conservative duration range; it never exposes or fabricates model chain-of-thought. The
composer also accepts bounded local materials before planning and lets the operator inspect or remove
each selection. Their content is sent only to the currently selected planning model as described
above; credentials and unauthorized documents must not be attached. The
operator may revise each proposed runtime and its advertised model before confirmation, which creates a new immutable child
plan and hash. The review surface also offers Fast, Balanced, and Deep profiles and immediately shows
the resulting model selection for each Agent. These profiles prioritize latency or quality; they do
not promise a wall-clock duration because tools, operator input, collaboration, and provider queues
remain observable parts of the run. Confirmation stays in Workspace. **Today** is an optional operating view that puts approvals,
failed or blocked work, coverage or projection concerns, observed active teams, mail summary, and a
new-work entry first; technical health is available in a disclosure rather than competing with the
operator's next action. **Work** replaces only the former duplicated Tasks and Team navigation: selecting
one work item keeps its overview, task-scoped organization, evidence-only activity, immutable run
history, outputs, and settings in one place. The **Workspace** homepage contains planning conversation
history alongside common task presets, private task templates, and manually saved team blueprints.
They share a surface, not a data model: a planning chain, a work goal, its
plan-version team, each execution run, and a reusable blueprint retain distinct identities.
The selected Work's **Overview** also keeps a plain-language adjustment box beside the current
summary and team. The operator may ask to change the goal, stages, Agent roles, reporting hierarchy,
bounded loops, cadence, outputs, or checkpoints. A request from a ready or ended Work always creates
a new immutable child plan and hash; it never edits the displayed version, confirms it, or dispatches
it. Active Work remains locked until it reaches an ended state.
The active-team summary in **Today** is a read-only projection of those same Work records, not a
second team registry. It includes only `confirmed`, `dispatching`, `running`,
`awaiting_approval`, and `awaiting_input` work and exposes bounded member-observation signals; organization, runtime,
model, activity, output, and lifecycle changes remain owned by the selected Work item.
Forking is distinct from revision and rerun. A fork is a new root Work at version 1 with explicit
`forked_from_plan_id` and `forked_from_plan_sha256` provenance. Its confirmation hash binds that
provenance, while execution sessions, approvals, operator answers, artifacts, and outcome state stay
with the source. The fork opens in Workspace review and cannot execute until its new hash is confirmed.
While a Work item runs, its overview polls a bounded execution snapshot every 2.5 seconds and shows
the exactly observed active Agent, elapsed time, safe tool-name/status events, member observations,
and approval state. It deliberately shows no model reasoning, tool arguments or output, fabricated
percentage, or inferred stage completion. The plan stages remain the confirmed sequence; artifact,
eval, and sign-off evidence still decide whether the business result is complete.

Each Work item's **History** tab follows its immutable parent chain and keeps every run independently
addressable. An ended Aion run with an exact team/session mapping may be selected and continued with
new operator input. Continuation sends the plaintext only to that same Aion team, stores only its
SHA-256 in OpsWitness's ledger, and creates a new child plan, plan hash, Paperclip issue, and run.
The child is attached to the Work's current leaf while its provenance points to the selected source
run. Active work, workflow runs, missing session identity, or adapter failure are rejected rather
than silently starting a new team or changing runtime. The new run filters shared-conversation
telemetry at its dispatch timestamp, so old replies and tool calls cannot prove new progress.

History also offers an exact-run privacy-erasure action for terminal Runs. It removes the local plan
body, operator-input state, exclusive Aion session, application-managed workspace, planning
materials, and result blobs that are not referenced by another retained Run. A content-free hash and
erasure receipt remain in the append-only ledger, while shared blobs, explicit external workspaces,
backups, and already projected governance records are retained. A shared Agent conversation blocks
the action rather than pretending one Run can be removed independently.

Plan confirmation snapshots an approval mode. New plans and reviewed reruns default to
`automatic`: after the operator confirms the exact plan hash, every AionUi tool confirmation
receives an automatic single-use decision. OpsWitness still creates the Paperclip approval and
fsync-backed local policy/delivery evidence, so Auto removes per-tool interruption rather than the
audit trail. The review switch opts into `manual_all`, where every execution tool pauses for a
human decision. While a supported Aion team is active, Work shows the current mode beside the
lifecycle controls. Turning Auto off tightens the running execution immediately; turning it back on
requires an explicit confirmation and applies only to future tool calls. A call already waiting for
approval keeps the mode captured when that request was created. This changes only the execution
policy, not the reviewed plan or its hash, and the requested/committed transition is append-only;
an interrupted transition recovers to the more restrictive mode. Each actionable approval carries
a validated source `plan_id` and is rendered
inside that Work item's attention panel with its redacted tool request, risks, optional note, and
explicit single-use confirmation. Deciding it refreshes the same Work item; it never requires a
round trip to the global Approval view. Existing `automatic_safe` records keep their original exact
read-only allowlist semantics, and legacy records with no stored mode remain manual. The bounded `qd_request_input`
notification is side-effect-free and remains available in every mode so an Agent cannot deadlock
before asking its operator a question.

An active AionUi team may have one pending operator question. The planned Agent name and private
question are stored in the local plan record, while `task_input_requested`,
`task_input_answered`, and `task_input_delivered` evidence stores only identities, counts, and
SHA-256 hashes. The answer is tagged and delivered idempotently to the same team; it does not create
a new plan, alter the confirmed hash, or enter the ledger as plaintext. The UI explicitly warns
against entering passwords or API keys. When a manually governed `qd_request_input` first pauses
for approval, its allow-once decision and the resulting suggested-answer input appear sequentially
in that same task-local panel.

If the pending question explicitly names a single-level `artifacts/<filename>` JSON attachment,
Work presents it as a request-bound, read-only preview beside the suggested answers. The preview
recomputes SHA-256, shows candidate/signoff state and source boundaries, and never returns an
absolute filesystem path. Unmentioned files, traversal, symlinks, invalid JSON, and files above the
bounded preview limit fail closed. Opening the preview is not approval, artifact registration,
evaluation, or signoff; an execution-workspace candidate becomes outcome evidence only through the
ordinary CAS/eval/signoff path.

The interface defaults to English on first use. **Settings** provides an immediate English/中文
switch stored only in that browser's local storage. This preference localizes product chrome and
fixed safety copy; it never changes authored task content, plan hashes, backend records, or ledger
events.

The empty Workspace also offers 31 searchable bilingual task presets across operations, research
and decision support, growth, customer operations, and specialist workflows. They cover recurring
work such as project-risk review, SOP and document digestion, data analysis, product feedback,
sales preparation, client onboarding, hiring-process design, contract review, and incident response.
Each preset is an authored planning brief with explicit data, approval, and side-effect boundaries.
Ten of those presets are marked as **proven Work templates** and add a concrete recipe: Agent count,
stage count, team handoff, cadence, expected outputs, and a human checkpoint. Four priority templates
are shown directly on the empty Workspace: company commercial analysis, a CPA/EA month-end workpaper
pack, a customs entry-support evidence pack, and a commercial P&C renewal-readiness pack. The three
professional-service templates stop at a source-linked exception or readiness package for licensed
review; they do not post accounts, file tax or customs records, recommend or bind insurance, or replace
the CPA/EA, customs broker, or insurance producer. Their explicit **Generate team** action submits the authored objective to the
planner in one click, but still stops at the ordinary review screen; it never confirms a plan or starts
execution. Search stays browser-local. Selecting any card inside the full catalog only fills the local composer: it does not submit a
planning request, create a task, start an Agent, or bypass the normal AI-plan, runtime review,
exact-hash confirmation, and managed-execution sequence. Presets are not team blueprints and never
create persistent employees.
Directly below that catalog, **My task templates** stores operator-authored names and task objectives
in the private console state directory. The user can create, search, reuse, and delete templates;
deletion is an audited archive transition. Template files are mode `0600`, ledger events retain only
content hashes, and selecting a template only fills the composer. Saving or selecting one never
calls the planner, creates a task, or starts execution. A template saved from Workspace conversation
history additionally binds the exact source Plan id/hash, but remains objective-only.
A blueprint carries only topology and runtime preference, is never an employee directory, and always
goes through fresh AI planning, review, runtime selection, and hash confirmation before use.
Each work item's **Activity** tab shows bounded evidence for the selected current execution. Its
**History** tab folds all confirmed Agent runs from append-only ledger commit order, keeps
tombstoned-task evidence retained, and provides the guarded continuation path described above.
Wrapped system automation that cannot belong to one Work item remains available under
**Settings → Advanced diagnostics**.
Confirmation launches one
managed run; a proposed daily/weekly cadence does not silently create a recurring schedule. A
finished Agent Team is labeled `completed_unverified` until artifact, eval, or human sign-off
proves the business outcome. See
[ADR-0007](docs/adr/0007-local-operator-console.md).

Run controls are deliberately adapter-scoped. Aion team executions expose **Pause**, **Continue**,
and an explicitly confirmed **Stop** action. Pause is a cooperative runtime state, not an operating-
system process freeze. Continue reuses the same immutable plan/hash and records a fixed resume marker.
Stop remains `cancel_requested` until Aion reports the exact run inactive or terminal; partial outputs
and evidence remain available but never become a completion claim. Registered workflows do not show
these controls until their executor can provide the same confirmation contract.

An optional secret-free KeepAlive launchd template is available through
`opswitness service render console`. Install it only in the same quiesced maintenance window used to
upgrade the stable `opswitness` tool; never replace the uv tool environment while wrapped or
periodic OpsWitness jobs can start.

## Showcases

The same contract, three verticals:

1. **Practitioner workbench** (fortune-chart reading): deterministic chart engine → multi-agent draft → human sign-off → traceable report.
2. **Software delivery**: requirement → Codex/Claude Code run → tests → gated PR.
3. **Research analysis**: collection → analysis → citation verification → delivery.

## Status

Alpha. Built against Paperclip v2026.707. Not affiliated with Paperclip.

The local P2 code path and M1 install-readiness tooling are test-complete. A verified private
Release wheel remains installed as the production `OpsWitness 0.1.0a1` RC; Paperclip, Postgres,
the console, and all five legacy-label launchd services are installed. Private Release validation
run [29968869522](https://github.com/opswitness/opswitness/actions/runs/29968869522) passed for
executable-source commit `3859493`. After an approved restart, the host still reports macOS
`26.5 (25F71)`, and the real-host doctor remains red because projector, watchdog, and gate-recovery
interval triggers are pended without execution. No `alpha-rc-5` contract has started.
`alpha-rc-1` through `alpha-rc-4`, and the earlier `m2-canary`, remain preserved as immutable
failed evidence and are not cited as Alpha success.
Feed-monitor and sox-monitor remain blocked until the later Stable gates in READINESS pass.
Evidence: [ALPHA-RC-VALIDATION.md](docs/ALPHA-RC-VALIDATION.md).
Mobile access is not part of the Alpha promise. Private HTTPS, device pairing, and PWA support
remain unadvertised Beta capabilities until physical iPhone Safari/Chrome acceptance passes.
M3's non-interactive Claude gate passed two
live defer/board-approval/resume drills; its one-minute recovery service is installed and
fail-closed. M4 content-addressed artifact/eval/signoff and live Paperclip work-product
reconciliation pass. These claims do not extend M3 enforcement to interactive Claude, Codex,
or other agent runtimes.

Start with [ARCHITECTURE.md](docs/ARCHITECTURE.md) — layer position, design laws, and why
this layer is deliberately designed to shrink. Release gates live in
[READINESS.md](docs/READINESS.md).

The primary command and public package name are `opswitness`. Existing local installations may
continue to use the compatibility command `qd`, legacy `QD_*` environment variables, legacy data
directories, and legacy `com.quarterdeck.*` launchd labels. Historical ledger events, plan hashes,
artifact hashes, and service evidence are never rewritten for branding.

## Security

Report suspected vulnerabilities through the repository's private vulnerability reporting
channel. Do not include credentials, private task text, customer data, or exploit details in a
public issue. CI scans the complete Git history with a pinned gitleaks release and fails closed when
a finding is detected.

## License

Apache-2.0. Contributions are accepted under the
[Developer Certificate of Origin](CONTRIBUTING.md).
