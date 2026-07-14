# Quarterdeck Readiness

Snapshot date: 2026-07-14 · This file is a SINGLE current snapshot; all earlier review
text is preserved verbatim under History. ADRs remain the source of design truth;
`INSTALL-PAPERCLIP.md` records the approved M2 procedure. Remaining rollout steps stay
blocked by the current open gates below.

## Current baseline

- M0-M4, M5/M6 preparation, and production permission hardening are committed on `main`.
  M2 permanent install and live integration
  executed successfully, while its elapsed soak gates remain open.
- Full suite: 290 tests pass in three consecutive runs; ruff and mypy pass. DCO, worktree
  gitleaks, and full-history gitleaks are clean.
- Process-tree signalling no longer executes `pgrep`, recursion, sleeps, or subprocesses
  in a signal handler. The handler writes a self-pipe; the supervisor snapshots
  `(pid, create_time)`, verifies descendants, escalates after 750ms, and emits
  `tree_signal_degraded` when cleanup cannot be proven.
- Watchdog, digest, and bootstrap share one `classify_schedule()` definition.
- Mutable `retired:` config has been removed. `qd retire/unretire --reason` records
  lifecycle events; a post-retirement run becomes `resurrected` and breaks health.
- Canary and seven-day elapsed gates now use append-only `soak_started`, `soak_reset`, and
  non-authoritative `soak_checkpoint` events. `qd soak status` freezes cadence and fails on
  trigger gaps, bad/degraded runs, schedule drift, torn lines, lifecycle violations, or
  unreconciled projection events. See [ADR-0006](adr/0006-append-only-soak-gates.md).
- M1 install readiness is implemented without touching production: structured
  `qd doctor --json`; strict config/secrets permissions; secure `qd service exec`;
  five secret-free launchd templates; encrypted backup and isolated restore dry-runs.
- `uv build` succeeds; the wheel was installed into an isolated `/tmp` tool root,
  `qd version` ran, and a packaged watchdog plist rendered and passed `plutil -lint`.
- Permanent Paperclip/Postgres/launchd are installed. The previously installed `qd doctor` is
  green, but it is itself stale: the stable tool lacks the newer `soak` and `console` commands.
  Current-HEAD doctor now detects this as `qd_command_surface=fail`; every other live check passes.
  Upgrading the uv tool before the 24-hour canary would violate the required quiesced maintenance
  window and reset continuous evidence, so the drift remains an explicit post-canary gate. Doctor
  verifies installed plist drift, rejects symlinks, checks private log/backup leaf modes,
  and fails on unhealthy launchd runtime state; encrypted backup + isolated restore and the
  projector four-test matrix pass.
- `com.tianyuzhou.register-trigger` is the sole canary; its pristine `.qd-bak` exists,
  seven ledger runs have succeeded, watchdog/digest are green, and projection backlog is zero.
  The active contract contains two natural starts and two successes, with a 21,606.956-second
  maximum gap under its frozen 25,920-second limit. A 22-minute
  schema-mismatch interruption required controlled recovery, so continuous evidence restarted
  at 2026-07-13 15:23 PDT and cannot pass 24 hours before 2026-07-14 15:23 PDT. Append-only
  contract `01KXETZM2A7BXN7D4Z54MF7RH0` now enforces that gate as `m2-canary`; its first
  production status correctly returned pending/exit 1 with only elapsed time outstanding.
  Evidence: [M2-VALIDATION.md](M2-VALIDATION.md).
- Feed-monitor and sox-monitor are not adopted. Their production source hashes, dry-run
  diffs, executable paths, schedule semantics, and isolated
  `apply -> lint -> rollback -> identical hash` drills are recorded in
  [M2-VALIDATION.md](M2-VALIDATION.md). Both labels had last exit status 0; adoption must
  wait for the canary gate and for each target to have no active PID.
- M3 is GO for its stated non-interactive `qd gated-claude` boundary. Two real Bash calls
  stopped at Paperclip approvals, resumed the same sessions, consumed once, executed once,
  and produced complete local evidence chains. Contextual command redaction passed live;
  gate-recovery is installed with a 60-second cadence and latest exit 0. Evidence:
  [M3-VALIDATION.md](M3-VALIDATION.md).
- M4 repository implementation now includes atomic CAS, artifact lineage/eval/signoff,
  rebuildable indexes, work-product reconciliation, outcome digest, and backup/restore
  coverage. Live canary projection and zero-repost drain pass. Evidence:
  [M4-VALIDATION.md](M4-VALIDATION.md) and
  [ADR-0003](adr/0003-artifact-authority.md).
- M5 name-independent release preparation includes cross-platform CI, DCO enforcement,
  wheel/sdist hashes, SPDX SBOM, GitHub provenance attestation, release assets, an
  end-to-end synthetic showcase, an eleven-tool ops MCP, and a structurally isolated two-tool
  mail MCP. The first-run local core
  clears the ten-minute target. Public release remains blocked by the brand and remote
  gates. Evidence: [M5-VALIDATION.md](M5-VALIDATION.md).
- Release-input verification now fails closed before hashes, SBOM, attestation, or upload. It was
  added after an unpublished local audit found Hatch's default sdist selection had included
  untracked `.claude` workspace files. The rebuilt sdist contains 114 paths; only Hatch's tracked
  root `.gitignore` is hidden, private-path hits are zero, and every regular input is checked
  against `git ls-files`. Focused leak regressions and the real rebuilt archives pass.
- Tagged release approval is now a dependency-level preflight rather than a late build step.
  Without `PUBLIC_RELEASE_APPROVED=true`, no tagged archive, SBOM, attestation, workflow artifact,
  or GitHub release step can run; a workflow-structure regression test enforces that ordering.
- All external workflow actions use immutable full-length commit SHAs. Dependabot will maintain
  GitHub Actions, uv, and console npm dependencies weekly once the remote exists, while CI rejects
  mutable action tags before they can become release inputs.
- The AionUi launch adapter is code-complete: a strict `0600` workflow allowlist, fixed absolute
  argv, no runtime parameters or shell, per-workflow concurrency lock, detached supervisor, and
  fsync dispatch barrier. The isolated complete showcase passed and the real manifest contains
  only that showcase. Live AionUi Manual Task acceptance now passes through a guarded custom
  Claude ACP agent whose persisted mode is `default`; a one-click run completed with full ledger
  evidence and projection acknowledgements. That acceptance itself left production qd and
  launchd unchanged; the later mail-schema recovery used the documented maintenance procedure.
- AionUi now shows the enabled custom Assistant `每日工作台`, fixed to `Permission=default` and
  bound only to the eleven-tool ops MCP.
  Mail data is intentionally excluded from that surface: a future `邮件回复` assistant must bind
  only `qd mcp --profile mail`, whose two tools cannot launch workflows or mutate the fleet. The
  adapter is fixed-query, metadata-only, pinned to `gws 0.22.5`, and disabled by default. The
  separate `quarterdeck-mail` connection is tested at exactly two tools but remains disabled;
  Gmail OAuth is absent and no mailbox access has occurred. A real console attempt failed in under
  half a second because no Google Desktop OAuth client existed; the old UI had checked only the gws
  binary and incorrectly exposed the login action. The corrected dialog now reports structured
  client readiness and stops at an explicit local import step. Imported JSON must be a Desktop app
  with fixed Google endpoints and localhost redirect, is atomically stored under `0700`/`0600`, and
  is never echoed or written to evidence. Only then do two literal-true acknowledgements gate the
  fixed readonly Gmail login command. Desktop and 390x844 mobile acceptance pass with no horizontal
  overflow; the real state remains `oauth_client_issue=missing` and disabled.
- The local operator console is code-complete at `qd console serve`: FastAPI serves the packaged
  React UI on loopback only. Its default left-navigation Workspace is a chat-first task entry:
  one plain-language description opens the existing ephemeral tool-free AionUi Plan Mode contract,
  expands terse intent into a validated six-section execution brief, then renders the Agent
  architecture, stages, cadence, checkpoints, artifacts, and risks inline. Persisted backend phases
  drive the progress bar and step list; elapsed time and the conservative typical/worst-case range
  stay visible without exposing or inventing chain-of-thought.
  CSRF/origin/content-type/CSP controls protect writes; confirmation remains bound to the exact
  plan SHA-256; only then can Paperclip issue creation and AionUi Team/allowlisted-workflow dispatch
  occur. A real
  synthetic request returned a four-Agent/four-stage review plan and stopped at the unchecked,
  disabled confirmation action, so no execution side effect occurred. Desktop and 390px mobile
  layouts have zero horizontal overflow; the Workspace composer stays above the six-item mobile
  navigation, quick prompts only populate local input, and New conversation resets it without a
  planning side effect. The built wheel contains the versioned static assets.
  Mail stays visibly `未启用` until the existing consent/OAuth gate closes, but its setup button now
  opens the exact readonly and model-metadata consent contract instead of a dead control. Design authority:
  [ADR-0007](adr/0007-local-operator-console.md).
- Quarterdeck is now the sole ordinary operator surface. The Connections view probes the real
  local ChatGPT/OpenAI and Claude login state and launches only fixed vendor-owned login flows;
  it never accepts or returns model credentials. Planning automatically selects a ready provider
  and starts the hidden AI adapter when needed. The new Approval view lists redacted pending calls
  and performs fixed approve/reject mutations behind explicit review, loopback Origin, CSRF, and
  JSON gates. The local ledger fsyncs the request before the governance API call and records a
  fixed outcome afterward; free-text notes enter the ledger only as SHA-256. AionUi and Paperclip
  are absent from normal navigation and appear only in a closed advanced-diagnostics disclosure.
  Version 1 is explicitly a single-user loopback surface whose local actor is `local_console`, not
  a multi-user identity system. Final source-console acceptance showed `chatgpt` and `account`
  auth modes with both registered runtimes ready; the UI labeled them separately, exposed no
  provider output or internal system name, kept diagnostics closed, had no browser warnings, and
  had zero horizontal overflow at desktop and 390x844 mobile sizes.
- Ready plans now separate **Modify plan** from **Start over**. Modify creates an append-only child
  record bound to the immutable parent id/hash and a ledger-only instruction hash, passes the full
  previous plan to the tool-free planner, rejects an identical result, and issues a new confirmation
  hash. A valid child blocks parent confirmation. The UI keeps the old plan visible while editing,
  then labels the revision number and lists changed structural sections; Start over alone clears the
  composer. Backend integrity, privacy, duplicate-request, parent-blocking, and CSRF paths have
  focused regression coverage. Rebuilt source-console acceptance kept the existing Bazi plan
  visible while a local-only revision instruction enabled the Generate revision action; cancel
  restored the unchanged plan without an API request. Desktop and 390x844 mobile layouts had no
  horizontal overflow, and the browser console remained clean.
- A real source-console acceptance submitted only the synthetic terse intent `算命师`. The first
  AionUi result failed the new brief contract, visibly moved into the repair phase, then returned a
  six-section Bazi demo brief with `DEMO-001`, deterministic `lunar-python`, knowledge-only AI
  interpretation, exactly three named Agents, human signoff, traceable JSON/citation/eval/PDF
  artifacts, no real personal information, and no sending. The confirmation checkbox remained
  clear and the run button disabled, so no execution, dependency install, or customer-data action
  occurred. The observed repair path also corrected the displayed maximum budget to cover two
  planner attempts plus cleanup rather than one model timeout.
- Console startup now scans every private plan record strictly. Durable `confirmed` work is
  resubmitted through an atomic per-plan dispatch claim, active work is refreshed, and ambiguous
  `planning`/`dispatching` interruptions fail closed with fixed ledger evidence. Corrupt records
  prevent startup instead of disappearing from recovery; concurrent confirmation and dispatch
  regressions prove a single remote execution path.
- The total console never persists or returns arbitrary AionUi, Paperclip, workflow, runtime, or
  schedule-parser exception text. Fixed reason codes preserve audit semantics while hostile echo
  tests prove that private paths and plan-like text do not cross into the API or ledger.
- The console now holds one exclusive `console.lease` before startup recovery. Duplicate processes
  are rejected across ports, failed startup releases app-owned leases, and graceful shutdown waits
  for background work before handing plan-state ownership to a successor. A live second-port start
  exited 2 before recovery while the primary health endpoint and existing `ready` plan remained
  unchanged; real directory/lease permissions are `0700`/`0600`.
- Every AionUi planning or mail request now gets a unique private `0700` workspace. Successful
  output requires confirmed cleanup of both the temporary Team and workspace; Team-creation and
  workspace-cleanup failures are covered explicitly. A `0600` marker is fsynced before Team
  creation; startup under the exclusive lease records intent, reconciles only an exact AionUi
  workspace/name/optional-ID match, proves remote absence, removes the workspace, and records
  completion. Missing/corrupt markers, insecure modes, ambiguous identity, API failure, or audit
  failure stop startup. A crash before marker publication can leave only an unmarked local
  directory, which remains an explicit manual-inspection state rather than an inferred deletion.
- A fifth secret-free launchd template now makes that console an optional loopback KeepAlive
  service. `qd service exec console` reads the private configuration then `execve`s the fixed
  `qd console serve --port <configured>` argv. Doctor treats it like Paperclip: installed plist,
  running state, and bound port must all pass. The template has passed real dry-run rendering and
  `plutil -lint`, but is intentionally not installed until the canary checkpoint permits one
  quiesced stable-tool upgrade.
- M6 is recruitment-ready but intentionally has no product code. The paid-design-partner
  gate, data boundary, implementation order, and success evidence are fixed in
  [M6-PILOT-GATE.md](M6-PILOT-GATE.md).

## Open gates (blocking, in order)

1. **Canary elapsed time** — `qd soak status m2-canary` must remain non-green until at least
   2026-07-14 15:23:32 PDT, then pass together with the independent production checks;
   register-trigger must remain healthy for 24–48 hours.
2. **Stable-tool and console service upgrade** — after the canary passes, quiesce every qd
   consumer, install the current wheel, verify stable `qd soak`/`qd console`, install the optional
   console plist, rebootstrap services, and require current-HEAD doctor to return fully green.
3. **Seven-day soak** — only after the canary and stable-tool upgrade pass may feed-monitor and sox-monitor
   be adopted; M2 remains incomplete until seven days pass.
4. **Telegram digest** — secure hidden-input CLI and total-console setup/test/disable tooling is
   implemented, atomically writes only the `0600` secret file, refuses silent replacement, hides
   validation inputs, and records no credential values. Production credentials are still absent
   and the separately confirmed fixed delivery probe must be exercised during soak without
   exposing or copying tokens into chat, repo, argv, logs, or plists.
5. **Daily mail consent and OAuth** — before enabling the adapter or creating the hidden
   09:00 America/Los_Angeles task, the operator must create and privately import a Google Desktop
   OAuth client, then explicitly approve Gmail readonly OAuth
   and sending sender/subject/date/message-id metadata to the selected model provider,
   set `mail.model_metadata_consent: true`, and bind a separate internal assistant only to the
   mail profile. Then run one real metadata-only acceptance check; automatic
   send/draft/delete/label mutation remains out of scope.
6. **Brand gate** — `QUARTERDECK` has an active US class-42 software registration and
   substantial software-name usage. `OpsWitness` is the preliminary recommended replacement,
   and its exact/broader official USPTO queries plus live package, GitHub, and domain checks
   are clear at the recorded snapshot. No rename or reservation has been approved. Evidence:
   [BRAND-CLEARANCE.md](BRAND-CLEARANCE.md).
7. **No git remote** — GitHub Actions, attestations, private vulnerability reporting,
   and the release workflow have never actually run.
8. **M6 commercial gate** — no practitioner UI or private product repository until a
   design partner gives a written paid commitment or deposit.

## Resumption update (2026-07-13 11:59 PDT)

The operator resumed the project after completing normal Claude login and unlocking macOS.
The former M3 and AionUi blockers are closed without weakening their acceptance criteria:

- Production now reports 14 ledger runs; register-trigger has seven historical successes, while
  the active canary contract contains two starts and two successes with zero projection backlog.
  The configuration mismatch and recovery window at 15:01-15:23 PDT reset continuous
  canary evidence; the earliest 24-hour checkpoint is 2026-07-14 15:23 PDT. Elapsed time cannot
  be replaced by tests or a manual trigger.
- Two harmless real Claude sessions completed the full
  `defer -> board approval -> resume -> consume -> execute once` chain. Duplicate recovery
  and hook replay did not re-execute. No auth material was inspected or copied.
- AionUi's own Check MCP Availability action succeeded and displayed all eight Quarterdeck
  tools, closing the in-app acceptance gate. The full Paperclip MCP is intentionally not
  mounted: its pinned package exposes approval writes and a generic API escape hatch without
  a server-enforced read-only mode. Approval decisions now use Quarterdeck's fixed local facade.
- That eight-tool acceptance remains valid for the evidence console. ADR-0004 subsequently
  added three allowlisted launch tools. Their direct eleven-tool handshake, isolated workflow,
  and live AionUi Manual Task now pass. Built-in Claude cron was found to force
  `bypassPermissions`, so it was rejected and deleted before execution. The accepted task uses
  a connection-tested guarded Claude ACP agent with `yolo_id=default`, grants only the individual
  start/status tools, and keeps the whole MCP server unapproved.
- During later UI navigation, stale accessibility targets inadvertently fired the synthetic
  showcase twice: runs `01KXEQE941TF2HD4CP9ZQ4RFHX` and
  `01KXEQM5PVHH43HDA6VYQCZHKP`. Both were allowlisted, harmless, exit 0, and
  `degraded=false`; no production fleet workflow was touched. AionUi and the ledger report
  success, with requested, dispatched, started, finished, and projection acknowledgements.
  Session recreation can require the two tool confirmations again, and AionUi upgrades require
  revalidating the guarded agent's versioned ACP runtime path.
- ADR-0005 subsequently added a separate two-tool metadata-only mail profile while preserving
  the normal eleven-tool ops surface. `gws 0.22.5` is installed under the user-owned Quarterdeck
  prefix, but mail remains disabled, OAuth status is unauthenticated, no Gmail request was made,
  and no daily schedule was created. AionUi connection
  `mcp_019f5d9b-b884-7831-b991-eda395e98cb6` passed a two-tool test but remains disabled. These
  gates require an explicit data-transmission decision from the operator.
- Gate-recovery is installed. One uv-tool replacement-window import failure exposed an
  upgrade race; the service recovered to latest exit 0, doctor now checks runtime state, and
  the install runbook requires quiescing all qd consumers during upgrades.
- `OpsWitness` remains only a preliminary replacement candidate. No package rename, GitHub
  remote, identifier reservation, or public release is authorized until the operator makes
  an explicit brand decision.
- Telegram delivery remains unconfigured. The total console now offers password-only local input,
  fixed-probe confirmation, and removal under the permission-checked secrets boundary. No values
  were entered and no message was sent during acceptance; token/chat identifiers must never be
  pasted into documentation, git, a plist, logs, or chat.
- M6 remains behind its paid-design-partner gate; no practitioner UI should be built merely
  to create the appearance of Pilot progress.

Continue in this order:

1. At or after the restarted 24-hour checkpoint on 2026-07-14 15:23 PDT, rerun production
   `qd soak status m2-canary`, doctor, status, digest, watchdog, projector, backup, and canary
   evidence checks. Append `qd soak checkpoint m2-canary` only after recomputing the verdict. Continue
   observation up to 48 hours if any result is ambiguous.
2. Only after that gate passes, enter the documented qd maintenance window: stop qd consumers,
   gracefully stop the manually running source console without deleting `console.lease`, install
   the current wheel, verify `soak` and `console`, run current-HEAD `qd init` once to refresh the
   machine-owned generated schedule snapshot without changing user enrollment, install/bootstrap
   the console service, restore periodic services/canary, and require current-HEAD doctor,
   watchdog, status, and digest to become fully green.
3. Only after that upgrade passes, follow the hash-locked, idle-PID adoption procedure in
   `M2-VALIDATION.md` for feed-monitor and sox-monitor. Start the seven-day soak only when
   both jobs are wrapped, enrolled by exact label, and healthy.
4. Obtain an explicit brand decision before creating a remote or changing public
   identifiers. Run real GitHub Actions and provenance only after that decision.
5. Build the private practitioner product only after written paid commitment or deposit.

M2 is complete only after the seven-day soak passes with zero unexplained loss, duplicate,
false-green state, process-tree survivor, or unrecovered backlog. M3, M5, and M6 retain their
own independent acceptance gates.

## P3 defer contract (implemented and accepted live)

- Non-interactive `claude -p` only; minimum version **v2.1.89** (machine: 2.1.146).
- Hook returns `permissionDecision: "defer"` → run exits with
  `stop_reason=tool_deferred`, carrying `session_id` + `deferred_tool_use`.
- Resume via `claude -p --resume <session-id>`; the same tool call re-fires the hook.
- **Parallel tool calls in one turn: defer is IGNORED** and the call falls into the
  normal permission flow ⇒ the gate always runs `--permission-mode dontAsk`, safe
  tools explicitly allowed, governed tools neither allowed nor asked — an ignored
  defer therefore still denies.
- No long-poll fallback: absence of defer support ⇒ deny. `bypassPermissions` is
  forbidden under the gate.
- Deterministic matrix passes: single defer/resume · parallel two-tool · approval timeout ·
  duplicate resume · one-shot consumption · MCP/hook missing on resume · old Claude
  version · bypassPermissions rejection. Two real single-tool sessions also pass.

## Truth split for approvals (P3)

- **Paperclip owns**: remote approval state and workflow state machine.
- **Quarterdeck console owns**: the only ordinary decision UI and the explicit local click
  acknowledgement. Version 1 identifies this single local operator only as `local_console`.
- **Quarterdeck ledger owns**: the authoritative evidence — request hash,
  tool_use_id, expiry, approval id, decision, decider, resume/consume outcome.
- Paperclip database loss ⇒ pending calls stay denied; every past decision remains
  auditable from the local ledger.

## Next task

Keep register-trigger under observation until `qd soak status m2-canary` can be evaluated no
earlier than 2026-07-14 15:23:32 PDT.
Approve or reject the `OpsWitness` candidate before starting the atomic rename. Revalidate the
hidden guarded AionUi adapter after any AionUi upgrade.
Do not adopt feed-monitor/sox-monitor, publish a release, or build the practitioner UI before
their respective gates pass.

---

## History (superseded reviews, retained verbatim for audit)

# Quarterdeck Readiness

Date: 2026-07-12
Status: local P2 code is usable for controlled development; permanent installation is **NO-GO**.

This document is the current readiness snapshot. ADRs remain the source of truth for design
decisions, while `INSTALL-PAPERCLIP.md` remains a proposed runbook and must not be executed
until every gate below is closed.

## Verified Baseline

Snapshot reviewed at commit `bc52f96`:

- `62 passed` on macOS, including the process-tree test outside the restricted sandbox.
- Ruff, mypy, and full-history gitleaks checks pass.
- The working tree was clean at review time.
- No real launchd plist was adopted and no `.qd-bak` existed under `~/Library/LaunchAgents`.
- `qd wrap` records start/finish evidence without requiring Paperclip.
- Projector replay, per-job fail-stop ordering, reconciliation, and local disposable indexing
  are covered by tests; live Paperclip integration remains an installation gate.
- `qd digest` now distinguishes execution evidence from outcome evidence, includes traceable
  run IDs for problems, reports missing watchdog configuration as unavailable, and exits 1
  for an unhealthy report.

## Digest Gaps

The digest hardening is substantially complete, but two trust semantics remain:

1. Watchdog coverage is currently a boolean based on whether `schedules.yaml` exists. It must
   become a structured result covering missing, empty, malformed, unsupported, partial, and
   observed-but-unregistered jobs. A file that covers one job must not make an otherwise
   uncovered fleet green.
2. A running-only job is currently rendered with a success mark. Running is neutral, not
   successful; rendering and tests need a three-state result: healthy, running-neutral, and
   problem.

Telegram HTML delivery also needs a bounded-field or HTML-aware fallback for a single dynamic
line longer than the chunk limit.

## Bootstrap Findings

`qd init` is not ready as the default first-run path. A read-only, isolated-config run against
the actual default `~/Library/LaunchAgents` produced:

```text
41 jobs discovered, 39 added, 28 calendar (fail-closed)
```

Running watchdog immediately afterward produced 39 alerts, including third-party updaters,
application login items, and gateway services that are not part of the intended fleet. The
reported nine-job smoke used the explicit plist-copy directory under `trade/usstock`, not the
default first-run directory.

Required bootstrap v2 changes:

- Discover candidates automatically, but require one explicit selection/acceptance before
  activating monitoring. Third-party and unscheduled services stay candidates by default.
- Use the full launchd label as the canonical identity. Short-name collisions such as
  `gateway` and `wake` must fail closed rather than silently dropping one source.
- Distinguish interval, calendar, and unscheduled/service plists.
- Split generated state from user overrides, for example `schedules.generated.yaml` plus a
  user-owned `schedules.yaml`. Never rewrite the user file, its comments, or unknown fields.
- Use atomic writes and a single-init lock; report invalid YAML and source drift without
  clobbering either file.
- Add fixtures for the real 41-entry shape, collisions, empty discovery, invalid YAML,
  concurrent init, and user override preservation.

Future grace learning must use schedule-start lateness or inter-arrival residuals derived from
`run_started`, not `p95 duration * 2`. Automatic policy changes require bounded deltas, an audit
event, provenance, and rollback. Permission relaxation remains proposal-only.

## Installation Blockers

`docs/INSTALL-PAPERCLIP.md` is not approved for execution. Before permanent installation:

- Commit and validate the three claimed launchd templates; the referenced `templates/`
  directory does not currently exist.
- Define a stable Quarterdeck installation path. There is no global `qd`; only the repository
  virtualenv currently provides it.
- Install pinned Paperclip into a user-owned prefix. The current global npm prefix targets a
  root-owned module directory.
- Launch Paperclip with an absolute Node executable and absolute `dist/index.js`; its
  `#!/usr/bin/env node` entrypoint cannot rely on launchd PATH.
- Keep the PostgreSQL password out of launchd plists. Store secrets only in permission-checked
  `0600` files or another explicit secret provider.
- Enforce the config contract: consistent API-key precedence, reject insecure
  `secrets.yaml` permissions, and reject secret fields in non-secret `config.yaml`.
- Use `PAPERCLIP_HOME` or `--data-dir`, not the nonexistent `PAPERCLIP_DATA_DIR`, for an
  isolated restore rehearsal. Restore into a separate database and alternate API port.
- Add the missing encrypted-backup prerequisite (`age` is not currently installed) and prove
  a coordinated database plus instance-file restore.
- Keep fault injection inside an isolated ledger and test company. Never edit the authoritative
  append-only ledger.
- Revalidate and gracefully stop the previously observed sandbox embedded-Postgres process
  before cleanup; do not trust a stale PID without checking its command line.

## Release Gates

1. **Digest coverage-final**: structured coverage, uncovered-job reporting, neutral running
   state, and regression tests.
2. **Bootstrap v2**: candidate discovery, explicit acceptance, canonical identities,
   generated/user split, and atomic merge behavior.
3. **Install-readiness final**: stable binaries, committed plist templates, secure secrets,
   schedules, isolated backup/restore script, and `plutil -lint` coverage.
4. **Explicit operator approval**: only after gates 1-3 pass may the runbook touch the real
   HOME, PostgreSQL, or launchd configuration.
5. **Canary and soak**: one non-critical job for 24-48 hours, then feed-monitor and sox-monitor
   for seven days before calling P2 operationally ready.

## Next Task

Implement digest coverage-final only. Keep installation and real plist/config writes disabled.
After that, implement bootstrap v2 as a separate, reviewable commit.

---

## Update 2026-07-12 (through f32ac92)

Landed since the `bc52f96` baseline above (each commit reviewed in-loop):

- `9dba684` projector per-job fail-stop ordering; faithful signal exit semantics
- `6297d6e` adopt dry-run doctrine + watchdog missed-run detection
- `36829d6` fail-closed watchdog for unsupported schedules; atomic plist writes; qd-path/collision gates
- `affe16a` crash-safe backup publish; real config layering (env > secrets > config > defaults)
- `ce8fb89`→`0e3f0f9`→`592f2b6` bootstrap v1→v2→v2.1: candidates-only discovery, full-label
  canonical IDs (immutable under later collisions), strict user-config schema, fsutil gaps
- `bc52f96`→`c42a6f2`→`716c062` digest hardening → coverage-final → coverage v3:
  structured coverage (active-only, full-ledger universe, retired excuse path),
  three-state job marks, unified legacy-schedules validation
- `84a90a4` MCP console surface (6 tools, stdio handshake smoke)
- `1c5b0e6` evidence-based digest + Telegram HTML renderer
- Suite at 79 tests; ruff/mypy/gitleaks green at every commit above.

### Open (unchanged verdicts)

1. **Signal fallback (`9f62656`) is live on the main path** while its deterministic
   rework is tracked: pgrep returncode unchecked (restricted envs return 3), per-level
   5s blocking in a signal handler, PID-reuse race. Not a digest gate; own workstream.
2. **P3 design pivoted to `defer`** (native `permissionDecision: "defer"` confirmed in
   the hooks reference; detailed save/resume semantics + minimum Claude Code version to
   be pinned by the P3 spike; long-poll hook demoted to fallback design).
3. **P4 idempotency corrected**: `externalId` has no unique constraint upstream
   (verified against pinned v2026.707 source) — projection is list-and-reconcile;
   artifact content must be content-addressed (attachment/immutable blob), never a
   mutable local path reference alone.
4. **INSTALL remains NO-GO**: launchd service templates, stable Node/qd absolute paths,
   npm prefix handling, secrets handling, isolated restore drill — unchanged.
