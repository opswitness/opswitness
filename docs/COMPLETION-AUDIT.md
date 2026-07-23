# OpsWitness Completion Audit

Post-restart and product-identity audit, 2026-07-22: **OpsWitness** is the only public product
identity. Quarterdeck remains solely in documented compatibility surfaces and immutable historical
records. Private Release validation run
[29968869522](https://github.com/opswitness/opswitness/actions/runs/29968869522) passed for
executable-source commit `38594931ee1607cd621c9356816fa5189ca2c0a7`; this documentation correction
must still pass its own PR checks and does not inherit that commit's release evidence. After the
operator-approved restart, macOS reports `26.5 (25F71)`. A real-host doctor check passes every
current check except the projector, watchdog, and gate-recovery runtime checks, which remain pended
without interval execution. No `alpha-rc-5` exists. Public Alpha remains blocked, and all prior
failed canaries remain immutable evidence.

Exact Actions RC update, 2026-07-22: private Release validation run
[29927606948](https://github.com/opswitness/opswitness/actions/runs/29927606948) passed all
preflight, Ubuntu/macOS quality, DCO, full-history gitleaks, and build jobs for clean commit
`3bd2b0d005d86495b8121477d3425ac0bd264ec9`. Independent verification covered the wheel, sdist,
checksums, build manifest, SPDX package identity, dual CLI aliases, isolated synthetic wrap, static
console, bootstrap API, and browser surface. The exact Actions wheel is installed locally under a
quiesced, encrypted, rollback-safe migration; legacy state was adopted in place, CAS hashes are
unchanged, projection backlog is zero, all five official services are single-instance, and the
real-host doctor initially returned green. A later independent interval probe demonstrated that
periodic launchd triggers were pending without execution; the doctor runtime check now fails closed
on that state.

The artifact's append-only canary `alpha-rc-4`, event
`01KY53ZFJZCQWHS6FC60XRB4Y5`, starting `2026-07-22T14:34:21.145132+00:00`, permanently failed its
frozen cadence contract after one successful run. launchd received the next interval trigger but
pended it without execution while a macOS update was staged for restart. A separate 10-second
`/usr/bin/true` probe reproduced the same condition. `alpha-rc-1` through `alpha-rc-4` and
`m2-canary` are immutable failed evidence. The later restart did not clear the interval-trigger
fault. Public Alpha is not yet approved: a rebuilt exact artifact and passing canary, professional
brand review, private merge/public-main
security sequence, exact tag,
asset/attestation inspection, and final blank-install smoke remain open.

Planning-history, Repeatable-work and Workspace-Memory update, 2026-07-22: Workspace now derives a
read-only conversation list from immutable Plan revision chains, restores the latest intact version
for review, and can save an explicitly confirmed objective template bound to the exact source Plan
id/hash. This path cannot call planning, confirmation, Paperclip, AionUi, or execution. The source also derives one-click
review-first reuse from the latest ended, intact Work version rather than creating a duplicate Work
database. It also implements private Obsidian-compatible process/knowledge memory with immutable
candidate versions, explicit human approval, supersession, revocation, exact-version rollback,
hash-only ledger evidence, and approved-only planning snapshots. Historical plans keep their old
canonical hash because the optional memory envelope is absent. Backend tests cover no-dispatch
preparation, candidate isolation, approval injection, revoke-before-confirm denial, revision,
rollback, and HTTP confirmation/CSRF boundaries; frontend tests cover the ordinary Workspace path
and confirmed memory lifecycle APIs. [ADR-0008](adr/0008-repeatable-work-and-auditable-workspace-memory.md)
is the design authority.

This was post-freeze product code, so no earlier RC artifact or canary validated it. The exact
clean artifact, isolated installation, browser acceptance, and rollback-safe migration passed for
the prior exact build. `alpha-rc-4` failed and cannot provide continuous canary evidence; the doctor
fix requires a rebuilt exact artifact and fresh post-reboot contract.

Earlier local smoke acceptance on 2026-07-22 verified a wheel built from the working tree, retained an exact
uv-tool rollback copy, installed the package, restarted only the console, loaded the packaged
repeatable-Work and Workspace-Memory assets at `127.0.0.1:8765`, and obtained a fully green
real-host doctor verdict. Because the wheel was not produced from a clean release commit, this
evidence validated local usability only; the later exact Actions artifact supersedes it for RC
identity without rewriting the earlier record.

Execution-profile source update, 2026-07-21: ready plans can now create immutable Fast, Balanced,
or Deep child versions whose per-Agent model ids are selected only from the sanitized local catalog
and bound into the new plan hash. New Work defaults to Balanced, Run again defaults to Fast, and
manual model edits are Custom. Presets do not dispatch, silently fall back, or claim a wall-clock
SLA. Legacy plans omit the absent profile from canonical hashing. Because this is post-RC product
code, the existing `alpha-rc-2` canary cannot validate this build; a new clean artifact and canary
are required before publication, without rewriting any prior contract.

Product-direction update, 2026-07-21: [PRODUCT-VISION.md](PRODUCT-VISION.md) now records the
one-person-company first-use contract. OpsWitness does not try to replace Codex or Claude; it turns
their one-off work and other local automation into reusable Work with a reviewed Agent structure,
immutable versions, independent runs, History/Results, a clear Run again path, and provenance-bound
forks. README, Architecture, Readiness, and Commercialization use the same boundary. This is a
documentation and prioritization decision only; it does not close any release or runtime gate.

Community Alpha update, 2026-07-20: the release candidate is normalized as
`OpsWitness v0.1.0-alpha.1` / Python `0.1.0a1`. The package/module rename preserves compatibility at
the CLI, configuration, data-root, launchd, and known Keychain boundaries without rewriting any
historical evidence or hash. Release engineering now requires a clean checkout, exact identity
mapping, dual CLI verification, Linux/macOS quality gates, full-history DCO/gitleaks, checksums,
build manifest, SPDX SBOM, and GitHub attestation. The GitHub organization, private repository, and
domain are reserved; Draft PR #1 is green on Linux, macOS, DCO, and gitleaks. Private Release
validation and rollback-safe production migration now pass. The independent `alpha-rc-1` contract
failed its frozen cadence contract after a host sleep gap (`7,504.433s > 1,200s`) and remains
immutable failure evidence. Its independent replacement `alpha-rc-2` also failed: the
authoritative status recomputed at `2026-07-22T13:29:01.947352+00:00` reports 36 starts, 36
successes, zero task failures, zero projection backlog, and a `14,820.799s > 1,200s` hard cadence
gap. Its 24-hour minimum was also still pending. The exact post-freeze build, artifact install, and
browser smoke now pass. `alpha-rc-3` and `alpha-rc-4` also failed their frozen cadence contracts
and remain preserved. Publication still requires a rebuilt exact artifact, a passing post-reboot
24-hour contract, professional brand review, and final public-main Release acceptance as recorded in
READINESS. Mobile access is not advertised in Alpha and remains a separate Beta acceptance
gate. The legacy `m2-canary` also permanently
failed its frozen cadence contract (`50,171s > 25,920s`) and is never promoted to Alpha evidence.

Operational snapshot: 2026-07-13 21:24 PDT. The source-only console updates below were recorded
through 2026-07-15 02:18 PDT without changing production state. This document maps the approved M0-M6
plan to evidence and remaining gates. [READINESS.md](READINESS.md) remains the single operational
snapshot.

## Requirement matrix

| Milestone | Current evidence | Verdict |
|---|---|---|
| M0 trusted baseline | Process-tree supervisor, shared schedule classification, append-only lifecycle, full tests | Complete |
| M1 install and recovery tooling | Doctor, secure service exec, encrypted backup/isolated restore, five secret-free launchd templates | Complete in source |
| M2 permanent install and soak | Exact Actions wheel from `3bd2b0d` is installed; Postgres/Paperclip/services run OpsWitness `0.1.0a1`; failed `alpha-rc-1` through `alpha-rc-4` and `m2-canary` are retained | Blocked: the approved restart did not clear pended interval triggers; prove automatic intervals and a green real-host doctor, rebuild the exact RC, then run a fresh 24-hour canary |
| M3 Claude gate | Two live defer/approval/resume/consume drills and 60-second recovery service | Complete for non-interactive `qd gated-claude` only |
| M4 artifact/eval/signoff | Atomic CAS, ledger authority, live projection/reconciliation and restore evidence | Complete |
| M5 Community Alpha | Private remote/PR CI, exact-source private Release validation, verified assets, blank install, production RC migration, and browser smoke pass; `alpha-rc-4` failed its cadence gate | Release candidate: blocked by a fresh post-reboot artifact/canary, professional review, and public-main release gates; mobile remains unpromoted Beta |
| M6 paid practitioner Pilot | Offer, privacy contract, technical boundary and success criteria exist | Blocked by written paid commitment/deposit; product code intentionally absent |
| Local total console | Default chat-first Workspace, immutable planning conversation history with exact restore and provenance-bound template creation, AI-expanded execution brief, derived repeatable Work preparation, candidate-first approved Workspace Memory, persisted planning stages and time range, provider connection facade, immutable Fast/Balanced/Deep model-profile revisions plus Custom per-Agent selection, versioned plan revision, independent hash-bound Work forks, evidence-preserving whole-Work removal, reference-aware exact-run private-content erasure, graphical hierarchy and bounded collaboration loops, evidence-backed Auto/manual approval modes with task-local decisions, resumable runtime operator questions, plan-bound AionUi team-task stage telemetry, ledger-folded immutable run history with exact-context continuation, hash-bound confirmation, atomic dispatch/recovery, fixed-error privacy boundary, single-instance lease, per-request private AionUi workspaces, responsive UI and packaged assets | Source-complete; installed RC and continuous durability require a fresh build and post-change canary |

## Source console change record

2026-07-21 Work-overview adjustment update: the selected Work now exposes its natural-language AI
revision box directly below the current summary instead of hiding it inside the ready-only team
editor. Ready and ended versions may request changes to goals, stages, Agent roles, reporting lines,
bounded loops, cadence, outputs, and checkpoints. Every request creates an unconfirmed immutable
child plan bound to the source id/hash; it neither mutates prior runs nor dispatches execution.
Running and otherwise active versions remain locked. Backend and frontend regression tests cover
ended-source revision, zero dispatch side effects, status eligibility, and Overview placement.

2026-07-16 Work-history continuation update: Work now owns a dedicated History tab that follows the
immutable parent chain and exposes each run's evidence timeline. An ended Aion run can be selected
and continued only when its exact team and Agent conversation mappings remain available and the
current Work leaf is terminal. Continuation creates a new child plan/hash, Paperclip issue, and run;
its parent remains the latest leaf while source id/hash bind the selected historical run. The
follow-up body is delivered only to the same Aion team and only its SHA-256 is stored in the ledger.
ACK loss is reconciled by an idempotent marker, and old shared-conversation activity is excluded by
the new dispatch timestamp. Workflow runs, active Work, missing mappings, or unconfirmed delivery
fail closed with no new-team or runtime fallback. Full source verification passes 390 Python tests,
40 frontend tests, Ruff, mypy, TypeScript, and the Vite build.

2026-07-16 live-stage update: Work now folds AionUi's built-in structured team-task records into
the confirmed stage list. Each stage can display pending/running/blocked/completed/failed plus a
bounded safe activity list. Task descriptions, message text, raw tool arguments/output, and hidden
reasoning stay behind the adapter boundary. Completion is explicitly labeled Agent-reported
execution telemetry and cannot satisfy artifact/eval/signoff outcome gates.

2026-07-16 Work-fork update: any intact reviewed Work now exposes `Fork work`. After an explicit
confirmation it creates a separate version-1 Work with copied plan/team/settings and source id/hash
bound into a distinct plan hash. `task_plan_forked` records metadata only. The fork carries no source
execution, approval, operator input, artifact, or outcome state and must pass ordinary Workspace
review before execution. It intentionally has no `parent_plan_id`, so revisions continue to collapse
inside one Work while forks remain independently visible.

2026-07-16 lifecycle-control visibility update: active Aion team Work now keeps Start/Continue,
Pause, and End in three stable positions. Running, paused, gated, and pending states enable only the
actions the existing evidence-first state machine accepts; pending transitions remain explicit.
Start/Continue resumes only a runtime-confirmed pause and cannot bypass initial plan/hash review.
End retains the existing second confirmation and unconfirmed-stop semantics.

2026-07-15 task-local attention update: manual Aion approvals no longer require a jump from Work
to the global Approval page. Approval cards carry a locally validated source `plan_id`; only exact
matches render inside the corresponding Work overview. Tool request, risks, approve/reject,
optional note, and explicit acknowledgement are completed inline. After allow-once delivery, a
resulting `qd_request_input` question replaces the approval in the same slot with its suggested
answers. The global Approval view remains available as a cross-task queue and recovery surface.

2026-07-15 run-control update: active Aion team work now exposes Pause and explicitly confirmed Stop;
paused work exposes Continue. OpsWitness records every request before the side effect, resumes only
the same immutable plan/hash with a fixed marker, and keeps pause/cancel in requested states until
Aion confirms the outcome. A cancel RPC acknowledgement alone is not treated as process termination.
Partial outputs and evidence survive cancellation but remain unverified. Workflow controls are hidden.
Source/fake-runtime acceptance passed without operating the user's live task; real run-control
acceptance remains a readiness item.

2026-07-15 rerun update: failed and `completed_unverified` Work items now expose a visible
`Run again` action beside `Open full plan`. The original action idempotently prepared the same reviewed
plan as a new immutable child version. The 2026-07-21 profile update preserves its structure but now
defaults the child to Fast with advertised per-Agent model ids. It resets review to `automatic`, records only
hash/provenance metadata, and returns to Workspace review. Manual approval remains selectable; it
cannot dispatch until the new hash is explicitly confirmed.

2026-07-15 approval-identity repair: Paperclip v2026.707.0 rejects approve/reject calls made with a
service-agent bearer because those routes require a board actor. OpsWitness now keeps that bearer
for ordinary reads and projections, but uses Paperclip's implicit local board only after proving the
exact API base is loopback and health reports `local_trusted`. Live acceptance reconciled the
operator's existing allow-once intent exactly once; the next distinct tool request remains pending.

2026-07-15 navigation-semantics update: Today's Task Teams panel is documented as a read-only
projection of active Work records, not a second team registry. Work remains the sole owner of the
goal, plan-version team, hierarchy, activity, outputs, runtime/model selection, and lifecycle
controls. The current summary cards do not yet navigate directly to `Work -> Team`; the label and
direct-navigation improvement remain a non-blocking UI follow-up in READINESS.

2026-07-15 approval-and-input update: new plan confirmation now defaults to `automatic`, while the
review switch can require manual approval for every execution tool. Auto supplies an audited
single-use decision for each AionUi confirmation after exact plan-hash confirmation; historical
`automatic_safe` records retain their old read-only allowlist. Automatic decisions still create
Paperclip approval objects and local requested/decided/delivered policy evidence. The AionUi team
can now ask one bounded runtime question; Work/Today show `awaiting_input`, the answer resumes the
same confirmed team idempotently, and the ledger retains hashes rather than question or answer
plaintext. The ops MCP grows from eleven to thirteen tools; the isolated mail profile remains two.

2026-07-16 active-approval-mode update: supported Aion Work now displays one inline Auto-mode
switch beside its lifecycle controls. Disabling Auto immediately selects `manual_all`; enabling it
requires a second confirmation and affects only later tool requests. Pending calls retain the
policy captured when they were created. The change is compare-and-set, append-only, and confined to
the execution state, so the reviewed plan/hash remains immutable; interrupted changes recover to
the more restrictive mode.

2026-07-15 hierarchy clarification: the validated plan contract accepts one to five Agents with one
lead and an acyclic complete reporting tree. Reassigning existing managers can therefore turn the
current two-level Bazi organization into a valid three-level chain, while adding or removing an
Agent still requires a chat-first immutable plan revision and fresh hash confirmation.

2026-07-15 source update: Settings added DeepSeek API Key, xAI API Key, and the official Grok Build
account flow. Persistent keys are validated at fixed Models endpoints and stored in separate
Keychain items without touching AionUi; Grok account login requires the official CLI. Credential
readiness remains separate from Agent runtime readiness, so neither provider is advertised as
executable before adapter acceptance. No real key or account login was used in source validation.

2026-07-15 local-model update: Settings added Ollama and LM Studio with fixed loopback discovery,
explicit service-start confirmation, bounded model enumeration, and idempotent hidden-AionUi
provider registration using non-secret placeholders. No custom endpoint or real local-model key is
accepted. `runtime_ready` stays false until service, model, provider registration, and local
Assistant readiness all agree. Source acceptance did not start either installed local server.

2026-07-15 model-version update: every planned Agent can now select a runtime and one model from a
secret-free live catalog. Exact ids, rolling aliases, and runtime default are labelled separately;
the selected value is hash-bound in an immutable child plan, revalidated before dispatch, and passed
unchanged to AionUi. Legacy plan hashes remain stable because absent model fields are omitted from
their canonical payload.

These source changes extend the operator-console sequence after the initial total-console baseline.
They changed no production plist, schedule, mailbox permission, or confirmed task execution.

| Commit | Recorded update | Evidence boundary |
|---|---|---|
| `5c1007b` | Gmail readonly setup gained a validated local Desktop OAuth-client precondition | Missing/invalid client state cannot launch login; client fields never enter API or evidence |
| `cd50fe4` | Chat-first Workspace became the default task entry | Quick prompts only populate local input; planning still requires explicit submit |
| `5fa2d17` | Persisted planning phases, progress bar, elapsed time, and conservative duration range | Shows external phase names only; never exposes or fabricates chain-of-thought |
| `68a976c` | Quarterdeck became the sole ordinary UI for provider status/login, planning, approvals, and evidence | AionUi/Paperclip remain hidden replaceable adapters; credentials stay in vendor login flows |
| `3ebbaab` | Ready plans gained append-only, hash-bound revision children | Parent plan/hash remain immutable; revised child requires fresh confirmation |
| `529b1ba` | Task deletion became an evidence-preserving visibility tombstone | Private plan and ledger evidence remain intact; active work cannot be deleted |
| `e668bc8` | Team view gained graphical direct-manager editing | One lead root, complete membership, and acyclic reporting remain fail-closed |
| `f42e10d` | History unified Agent executions and wrapped automation | Ledger commit order is authoritative; process completion remains distinct from outcome proof |
| `0f1cc8f` | Team view gained graphically editable bounded collaboration loops | Self-review/cycles allowed separately from management; 1-10 iteration cap is plan-level, not a verified runtime cutoff |

## Historical live evidence (2026-07-13 snapshot)

The observations below are retained for audit and are superseded for Alpha readiness. In
particular, the then-pending `m2-canary` later failed because its 50,171-second observed cadence gap
exceeded the immutable 25,920-second allowance. The failure remains in the append-only ledger and
must not be reset or reused as `alpha-rc-1`.

- Current-HEAD `qd soak status m2-canary --json`: `pending`; only blocker is
  `minimum_duration`, with 64,757 seconds remaining at 21:24 PDT. The tracked job has two starts,
  two successes, zero failures, a 21,606.956-second maximum gap against a 25,920-second limit,
  and zero projection backlog since the reset contract.
- Current-HEAD `qd status`: 14 total runs and zero pending projections. The third independently
  clicked AionUi one-click workflow run (`01KXF2VC2NGNK7NFKEXWEBWZEY`) exited 0 without degraded
  evidence.
- Current-HEAD watchdog: all one active scheduled jobs within expectations.
- Current-HEAD digest: green, complete coverage, zero missed runs; execution and outcome evidence
  remain separated.
- Real launchd: Paperclip is running as one instance; projector, watchdog, gate-recovery, and
  register-trigger all have latest exit code 0.
- Current-HEAD doctor correctly returns non-green for one reason only: the stable installed qd
  lacks `soak` and `console`. The older installed doctor cannot detect its own drift.
- Real-browser total-console acceptance passed at desktop and 390x844 mobile widths. The mobile
  document had no horizontal overflow, the current four-agent plan exposed every planning field,
  and its dispatch button remained fail-closed unless the separate confirmation checkbox was
  actively selected. No plan was dispatched during this acceptance.
- The default Workspace now presents new work as one chat-like description followed by inline
  architecture review and explicit confirmation. Browser acceptance verified all five navigation
  destinations, quick-prompt input, New conversation reset, zero desktop/mobile horizontal
  overflow, no composer/navigation overlap at 390x844, and no browser warnings. The acceptance did
  not submit a planning request or create an execution side effect.
- A later source-only acceptance intentionally submitted the synthetic terse intent `算命师` to
  exercise the new AI brief contract. Persisted progress showed preparation, generation, repair,
  and cleanup with elapsed-time feedback. The repaired result contained all required deterministic,
  privacy, three-Agent, signoff, and artifact defaults. Confirmation remained unchecked and no
  execution was dispatched. The timing budget now covers two bounded planner calls plus cleanup;
  progress reporting cannot interrupt ephemeral-session cleanup.
- Final bounded-loop acceptance used the existing ready synthetic Bazi team. The UI added one
  collaboration loop, changed it to `引用核验 Agent -> 引用核验 Agent`, set the cap to four, and
  edited the stop condition. Desktop width 1964 and mobile 390x844 had zero document overflow;
  save remained available and browser warnings/errors were empty. The edit was cancelled, leaving
  the real plan at revision 1 with zero loops and no new ledger event. The complete suite passed
  303 tests in three consecutive runs; ruff, mypy, TypeScript, Vite build, targeted worktree scans,
  and post-commit full-history gitleaks passed.
- Total-console health now uses the same fail-closed coverage/watchdog/outcome rules as the digest
  over one ledger snapshot. The live metric is `1/1 完整覆盖`; successful historical or on-demand
  runs no longer inflate the number of actively monitored jobs.
- Approval counts are also fail-closed: only a successful Paperclip query may display zero.
  Unavailable approval state is rendered separately as unknown/attention rather than “no pending
  approvals.”
- Plan startup recovery resumes only safe `confirmed` work through one atomic dispatch claim,
  refreshes active work without replay, and fails ambiguous `planning`/`dispatching` states closed.
  Concurrent confirmation/dispatch and corrupt-record tests pass within the current 303-test suite.
- Commit `93c8bbb` gives every AionUi planning or mail request a unique `0700` workspace and makes
  confirmed Team plus workspace cleanup part of successful return. The source console restarted
  cleanly on port 8765; its only plan remained `ready` with the same timestamp, the confirmation
  checkbox was false, the run button was disabled, and the browser logged no warnings or errors.
  No planning request, mail access, or execution was triggered during this acceptance.
- Crash recovery now fsyncs a private marker before Team creation and reconciles only an exact
  AionUi workspace/name/optional-ID match under the console lease, with append-only started/failed/
  finished evidence. A real isolated probe deliberately left its Team ID unbound to simulate the
  POST-response crash window; startup recovery deleted exactly one matching Team and its workspace,
  confirmed zero remote Teams, and recorded `started -> finished`. Missing/corrupt/insecure markers,
  ambiguous candidates, identity drift, API failure, cleanup failure, or evidence failure stop
  startup. A pre-marker crash can leave only an unmarked local directory and requires inspection.
- Post-commit acceptance restarted source commit `d645441` on loopback port 8765. Startup recovery
  completed with no residue, health stayed green, the sole plan remained `ready` with its original
  timestamp, the dashboard remained `1/1` covered with zero projection backlog, and the browser
  emitted no warnings or errors. No plan, mailbox, or production fleet action was triggered.
- The local mail setup path now has a Desktop-client preflight, complete two-consent UI, and fixed
  backend OAuth boundary. Missing client state cannot call login; the local import validates a
  Desktop document and atomically enforces `0700`/`0600` without echoing client data. Only
  `gws auth login --readonly --services gmail` is possible; activation follows a second
  encrypted-token/readonly-scope verification and uses an atomic `0600` managed file without
  rewriting user configuration. Revocation fails closed for future access. Focused tests, three
  consecutive 278-test full runs, frontend typecheck, ruff, mypy, desktop acceptance, and 390x844
  no-overflow acceptance pass. A real first attempt exposed the previously missing client
  precondition and created only fixed failed authorization evidence; it did not access Gmail.
  The corrected UI now stops at the unselected local JSON import, so no client or token exists and
  no mailbox was accessed.
- Telegram now has a local password-only configure/test/disable path in the total console. Secret
  writes use the existing atomic `0600` merge, concurrent mutations are serialized, submitted
  values are redacted even from validation errors, and a separately confirmed fixed probe cannot
  send before requested evidence is durable. Desktop and 390x844 acceptance passed with empty
  fields and a disabled save action. No credential was entered, no Telegram event exists, and no
  message was sent. The full suite passes 270 tests in three consecutive runs.
- Current commit `428deef` also passes a fresh isolated uv-tool rehearsal: packaged `soak` and
  `console` commands are present, an isolated wrap exits 0 without degradation, and the packaged
  loopback console health/JS/CSS endpoints return HTTP 200. Real-user-domain doctor still fails
  only the intentionally deferred stable-tool command-surface check. Feed/SOX production hashes
  remain locked and their dry-run wrapper diffs have not drifted.
- Isolated bootstrap found that production `schedules.generated.yaml` is a stale July 12 machine
  snapshot; the user-owned exact enrollment and the canary interval/grace remain correct. The
  current parser produces the right wrapped register-trigger record. Regeneration is therefore a
  named post-canary maintenance action, not a reason to mutate or reset the active evidence window.
- Arbitrary planning, Paperclip, workflow, runtime, and schedule-parser errors no longer cross into
  plan API responses or ledger records. Hostile private-path echoes are covered by regressions.
- A real primary console on port 8765 held the `0700` state directory's `0600` lease. A second
  source-tree start on port 8766 exited 2 before recovery; primary health and the existing `ready`
  plan were unchanged.
- Historical pre-migration doctor had one failing command-surface check because the installed
  `quarterdeck 0.0.1` lacked `soak` and `console`. The verified RC migration superseded that
  command-surface snapshot and production now runs `0.1.0a1`. Its first post-migration doctor
  result was green, but that verdict was later invalidated when automatic interval probes exposed
  pended periodic services. Current source doctor correctly reports those services red. Evidence:
  [ALPHA-RC-VALIDATION.md](ALPHA-RC-VALIDATION.md).

## Safe remaining sequence

1. Preserve failed `alpha-rc-1` through `alpha-rc-4` and `m2-canary` unchanged. Complete the staged
   macOS update and reboot, verify repeated automatic interval launches, then rebuild/install the
   exact artifact and begin a new append-only 24-hour contract. Do not checkpoint Alpha until every
   frozen contract check passes.
2. Complete professional confusing-similarity review. Keep private HTTPS, pairing, and PWA
   unadvertised until the separate physical iPhone Safari/Chrome Beta acceptance passes.
3. Only after the blocking gates pass, merge privately, publish the repository, enable required checks and
   security controls, validate public main, approve one exact annotated tag, and inspect the
   resulting prerelease assets/attestation from a blank install.
4. Adopt feed-monitor and sox-monitor only for the later seven-day Stable soak. Configure optional
   Telegram/mail integrations only through their existing consent and secret boundaries. Begin M6
   product code only after written paid commitment or deposit.

Project completion requires every row above to be complete. A green repository test suite, one
manual run, or a source-only console does not substitute for elapsed production, public release,
or paid-Pilot evidence.
