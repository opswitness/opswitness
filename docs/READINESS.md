# OpsWitness Readiness

## Static public website source update (2026-07-22)

The repository now contains a static `opswitness.com` source with real synthetic-data product
screens, Community Alpha boundaries, GitHub Release installation, public issue routes, and GitHub
Private Vulnerability Reporting. The site explicitly states that the full console remains on the
operator's Mac and is not a hosted SaaS. Its Pages workflow uses pinned GitHub-owned actions and is
gated by `PUBLIC_SITE_APPROVED=true`, so it cannot deploy during the private RC stage.

This is release-surface work only and does not change the OpsWitness runtime. It must still be part
of the exact commit that passes PR CI and public-main release validation. The site must not be
opened for downloads until the inspected prerelease and final blank-install smoke exist. Current
host `doctor` remains red because projector, watchdog, and gate-recovery interval triggers are
pending without execution. `alpha-rc-3` and `alpha-rc-4` remain immutable failures. The next
contract is `alpha-rc-5`, and it may start only after the staged macOS update/restart and repeated
automatic interval probes pass.

## Exact Actions RC and `alpha-rc-4` failure update (2026-07-22)

Private Release validation run
[29927606948](https://github.com/opswitness/opswitness/actions/runs/29927606948) passed
preflight, Ubuntu and macOS quality, DCO, full-history gitleaks, and build for source commit
`3bd2b0d005d86495b8121477d3425ac0bd264ec9`. Publication was intentionally skipped because the
workflow was an untagged private validation. Independent inspection verified `clean_tree=true`,
the release identity, checksums, manifest, and SPDX package identity. A blank isolated uv-tool
install returned `0.1.0a1` from both `opswitness` and `qd`, completed a synthetic wrapped run,
served the packaged console and bootstrap API, and passed a browser smoke of Workspace and the
priority Work templates.

The exact Actions wheel was then installed under a quiesced maintenance window. The encrypted
state backup is
`~/.local/state/quarterdeck/backups/opswitness-20260722T142908Z.tar.age`; the prior uv tool,
command links, nine related plists, and pre-migration state hashes are retained under
`~/.local/state/quarterdeck/release-rollback/opswitness-actions-3bd2b0d-20260722T142908Z/`.
Legacy ledger, CAS, configuration roots, and service labels were adopted in place. Post-install
CAS hashes are unchanged, projection backlog is zero, and the five official services are
single-instance. The earlier doctor snapshot returned `healthy=true`, but a later interval probe
proved that periodic launchd triggers were pending without execution. Doctor now treats that state
as a failure instead of trusting a prior exit-zero run.

`alpha-rc-3` is immutable failed evidence. It started at
`2026-07-22T06:21:34.204863+00:00` and acquired a hard cadence gap after executable source changed;
later runs cannot erase that gap. The exact Actions artifact has its own append-only contract,
`alpha-rc-4`, event `01KY53ZFJZCQWHS6FC60XRB4Y5`, with evidence starting at
`2026-07-22T14:34:21.145132+00:00`. Its first run succeeded, but the next interval trigger was
received and pended by launchd instead of executed. At `2026-07-22T15:02:33.528698+00:00` the
authoritative verdict was permanently failed: one start, one success, zero task failures, zero
projection backlog, and a 1,647.999-second cadence gap against the frozen 1,200-second allowance.
A harmless 10-second `/usr/bin/true` probe reproduced `runs=0` with
`pended nondemand spawn = interval`, proving this was not the wrapped command or canary plist.
macOS 26.5.2 is staged and requires restart; a fresh contract must not start until the update and
reboot complete and repeated automatic interval probes pass. `alpha-rc-1` through `alpha-rc-4`
and `m2-canary` remain permanent failed records.

This update changes the doctor runtime check but does not change any prior contract, ledger, or CAS
object. Public Alpha remains blocked by a rebuilt exact artifact, a fresh post-reboot 24-hour
canary, professional confusing-similarity review, private merge and green
`main`, repository security/publication controls, public-main release validation, approved exact
tag, prerelease asset/attestation inspection, and final blank-install smoke.

## Planning history, Repeatable Work and Workspace Memory source update (2026-07-22)

Workspace now folds immutable Plan revision chains into selectable planning conversation history.
Opening a row restores the latest intact revision for review with no planner, confirmation, or
execution side effect. Saving a row as a task template requires explicit confirmation and records
the exact source Plan id/hash; the template remains objective-only. Backend tests cover grouping,
latest-version selection, hash validation, CSRF, provenance, and zero dispatch. Frontend tests cover
selection, restore, explicit template confirmation, and no execution call.

Workspace now derives **My repeatable Work** from the latest ended, intact reviewed version in
each immutable Work chain. Preparing one uses the existing rerun path, creates an unconfirmed child,
and has no execution side effect. Task templates remain objective-only and team blueprints remain
topology-only; no second mutable Work database was introduced.

The source also implements candidate-first, auditable Workspace Memory under
[ADR-0008](adr/0008-repeatable-work-and-auditable-workspace-memory.md). Process and knowledge
versions are private Obsidian-compatible Markdown documents. Agents can propose candidates, while
only explicit human approval makes a hash-verified version active. Supersession, revocation, and
exact-version rollback are ledger lifecycle events. New planning receives only a bounded approved
snapshot; confirmation fails closed if that snapshot is no longer active. Memory bodies never enter
the ledger or bootstrap summary.

This was product code after the Alpha release freeze and invalidated `alpha-rc-2` as evidence for
the current source build. The exact-source private build, isolated install, browser smoke, and
rollback-safe production migration are now complete as recorded above. `alpha-rc-4` failed and
cannot validate that artifact; all prior contracts remain immutable historical evidence. The
doctor fix requires a rebuilt exact artifact and a new post-reboot contract.

Earlier local acceptance on 2026-07-22 built and independently inspected a wheel from the working tree,
preserved the previous uv-tool installation as a rollback copy, installed the wheel, restarted only
the console service, and confirmed the packaged Workspace/Memory UI at `127.0.0.1:8765` with a fully
green real-host `opswitness doctor --json`. This is local smoke evidence only. The source tree is not
a clean release commit, so this installation does not satisfy the fresh RC or canary requirements
by itself; the later exact Actions artifact validation above supersedes it for RC identity.

## Execution-profile source update (2026-07-21)

The review surface now offers Fast, Balanced, and Deep execution profiles. New Work resolves
Balanced by default; Run again prepares a Fast child by default; manual per-Agent model selection
produces Custom. Every preset is resolved against the sanitized local capability catalog before
confirmation, writes each selected model id into a new immutable plan/hash, and has no dispatch
side effect or silent runtime fallback. Historical plans with no profile retain their exact legacy
hash payload.

This is a source-code change after the installed Alpha release candidate. It does not alter the
currently installed runtime, services, ledger, or the append-only `alpha-rc-2` contract. Even if
that contract later passes its frozen checks, it proves only the previous installed RC, not this
new source build. Publication of the profile-enabled build therefore requires a fresh clean RC
artifact, install/smoke acceptance, and a new append-only canary under a new contract id. Existing
failed and in-progress canary evidence remains untouched.

## Product-goal record (2026-07-21)

The durable product target is now explicit in [PRODUCT-VISION.md](PRODUCT-VISION.md): OpsWitness is
the simple repeatable-work operating layer for a one-person company, not a replacement for Codex,
Claude, or the underlying Agent runtimes. The ordinary path remains Workspace -> reviewed plan and
team -> confirmation -> Work -> History/Results -> Run again, revise, or fork. Future capabilities
must preserve this path, hide adapter complexity by default, and strengthen repeatability rather
than add another general Agent platform surface. This documentation decision changes no Alpha
release, canary, security, or durability gate.

## Community Alpha release-candidate update (2026-07-21)

The approved source migration targets `v0.1.0-alpha.1` (`0.1.0a1` in Python metadata) with
`opswitness` as the distribution, module, and primary CLI. The `qd` CLI, `QD_*` environment
aliases, former data roots, launchd labels, and known Keychain services remain bounded
compatibility surfaces. Conflicts between old and new state fail closed, and no historical
ledger, CAS, plan hash, artifact hash, protocol marker, or validation record is rewritten.

The `opswitness` GitHub organization, private `opswitness/opswitness` repository, and
`opswitness.com` domain are reserved. Draft PR #1 has passed Linux, macOS, DCO, and full-history
gitleaks checks. These facts close identifier reservation and ordinary PR CI only; they do not
constitute legal clearance or a public-release verdict.

Private Release validation run
[29794782849](https://github.com/opswitness/opswitness/actions/runs/29794782849) passed its
preflight, Linux/macOS quality, DCO, full-history gitleaks, and build jobs at commit
`92d10d557f13f0358fa1a424049054fa53dcb467`. Its downloaded wheel, sdist, checksums, manifest, and
SPDX SBOM passed independent verification and a blank uv-tool install. The verified wheel is now
the production RC: `opswitness`, `qd`, and all five legacy-label services run `0.1.0a1`; real doctor
is fully green; old state roots were adopted in place; and all pre-migration ledger/CAS hashes were
preserved.

The independent append-only `alpha-rc-1` canary failed after macOS sleep produced a
7,504.433-second cadence gap against its frozen 1,200-second allowance. `pmset` records software
sleep followed by thermal-emergency sleep/dark-wake cycles; the explanation does not waive the
hard contract. No checkpoint or reset exists. A distinct `alpha-rc-2` contract started at
`2026-07-22T00:36:01.202548+00:00` with a dedicated `/usr/bin/caffeinate -is` launchd assertion.
The authoritative status recomputed at `2026-07-22T13:29:01.947352+00:00` is also failed: 36
starts, 36 successes, zero task failures, zero running tasks, zero projection backlog, and a
14,820.799-second maximum gap against the frozen 1,200-second allowance. The unelapsed 24-hour
minimum is an additional pending blocker, not a reason to overlook the hard cadence failure. The
cause of this later gap has not yet been attributed and does not change the verdict. The former
`m2-canary` also remains a permanent failed record: its observed cadence gap reached 50,171
seconds against a frozen 25,920-second allowance. None of these failed contracts may be deleted,
rewritten, reset into a pass, or cited as successful Alpha evidence.

The post-freeze source differed from the artifact that started `alpha-rc-2`; the clean-source
Release build, exact-artifact install, browser smoke, and migration have since passed for commit
`3bd2b0d`. `alpha-rc-3` and `alpha-rc-4` also failed their frozen cadence contracts and remain
preserved. Publication therefore depends on a rebuilt exact artifact and fresh post-reboot canary
plus professional confusing-similarity review, private merge/public-main checks, and final prerelease
asset/attestation inspection. Mobile
access is not advertised in Alpha;
private HTTPS, pairing, and PWA remain Beta until physical iPhone Safari/Chrome acceptance passes.
Stable remains blocked on the seven-day soak and recovery/adoption gates recorded below. Detailed evidence:
[ALPHA-RC-VALIDATION.md](ALPHA-RC-VALIDATION.md).

The private remote is a validation stage, not a publication stage: its manual workflow builds and
verifies artifacts with read-only repository permissions. GitHub documents
[private-repository artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
as an Enterprise Cloud feature, so the OIDC-enabled `publish` job is restricted to the final
approved tag after the repository is public (or Enterprise support is independently confirmed).

The operational text below is the preserved 2026-07-16 pre-migration snapshot. Its old product
name, paths, service labels, version numbers, and candidate-brand statements are historical
evidence, not current installation instructions. For fresh Alpha installation use
[QUICKSTART.md](QUICKSTART.md); for current support boundaries use
[SUPPORT-MATRIX.md](SUPPORT-MATRIX.md) and [KNOWN-LIMITATIONS.md](KNOWN-LIMITATIONS.md).

## Pre-migration operational snapshot

Snapshot date: 2026-07-16 · This file is a SINGLE current snapshot; all earlier review
text is preserved verbatim under History. ADRs remain the source of design truth;
`INSTALL-PAPERCLIP.md` records the approved M2 procedure. Remaining rollout steps stay
blocked by the current open gates below.

## Current baseline

- M0-M4, M5/M6 preparation, and production permission hardening are committed on `main`.
  M2 permanent install and live integration
  executed successfully, while its elapsed soak gates remain open.
- Full suite: 384 Python tests and 37 frontend tests pass; ruff, mypy, TypeScript, and the packaged
  Vite build pass. The current worktree gitleaks scan is clean; DCO and full-history gitleaks remain
  release gates for the eventual committed revision.
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
  end-to-end synthetic showcase, a thirteen-tool ops MCP, and a structurally isolated two-tool
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
  bound only to the thirteen-tool ops MCP.
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
  React UI on loopback by default. The optional private surface now fails closed unless effective
  HTTPS and a paired-device credential are both present. It supports direct TLS and a recommended
  trusted-loopback Tailscale Serve mode; Host/Origin/CSRF checks, one-time pairing, immediate
  revocation, hashed credential storage, and proxy-spoof rejection have deterministic tests. The
  packaged PWA has Safari/Chrome manifest metadata, PNG icons, a static-only service worker, and an
  offline page that explicitly withholds task data. The 2026-07-14 live-tailnet acceptance passed:
  the console runs as a user LaunchAgent behind a tailnet-only Tailscale Serve route; HTTP/2, HSTS,
  unpaired redirect/API denial, real code claim, authenticated bootstrap, immediate revocation,
  Chrome, Safari, and 390px no-overflow checks all passed. Physical-iPhone acceptance remains an
  environment gate because the enrolled phone was offline during this run; it is not inferred from
  the responsive browser check. The original chat-first Workspace remains the default route and a
  permanent navigation category; only Tasks and Team are merged into Work:
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
  layouts have zero horizontal overflow; the New work composer stays above the five-item mobile
  navigation, quick prompts only populate local input, and New conversation resets it without a
  planning side effect. The built wheel contains the versioned static assets.
  Workspace preserves selectable immutable planning conversation history and provides 27 bilingual, locally searchable and
  category-filtered common-task presets. Each preset is a detailed planning brief with an explicit approval/data boundary;
  selecting one only fills the composer and cannot call planning, confirmation, or execution.
  Six are visibly marked as proven Work templates with Agent/stage counts, handoff, cadence, outputs,
  and a human checkpoint. Three are available directly on the empty Workspace through an explicit
  one-click planning action. That action creates only an unconfirmed proposal and cannot confirm or
  dispatch it.
  Search remains browser-local. The catalog includes the synthetic
  Bazi demo with fixed `DEMO-001`, deterministic `lunar-python`, three review roles, human sign-off,
  traceable JSON/citation/review/PDF outputs, no delivery, and no real-person data.
  My task templates and Team blueprints sit beside that catalog, so reusable starting points no
  longer require a separate top-level Library route. The template entry lets the operator save, search, reuse, and archive private
  task objectives. Files are mode `0600`, ledger events contain hashes rather than template text,
  writes require CSRF and explicit confirmation, and selection has no planning or dispatch side
  effect. A template created from planning history also binds its source Plan id/hash without
  copying team or execution state. Task templates remain distinct from topology-only TeamBlueprints.
  Mail stays visibly `未启用` until the existing consent/OAuth gate closes, but its setup button now
  opens the exact readonly and model-metadata consent contract instead of a dead control. Design authority:
  [ADR-0007](adr/0007-local-operator-console.md).
- The console now defaults to English and offers an English/中文 selector in Settings. The preference
  is browser-local presentation state; static controls and safety copy switch immediately while
  authored task content, backend state, plan hashes, and ledger evidence remain untouched. Frontend
  unit coverage fixes English as the invalid-or-absent fallback and verifies both localized member
  observations and task-adjustment drafts.
- Quarterdeck is now the sole ordinary operator surface. The Connections view probes the real
  local ChatGPT/OpenAI and Claude login state and launches fixed vendor-owned login flows. Claude
  exposes local subscription (`--claudeai`), Console API billing (`--console`), and explicit API Key
  paths; the subscription path is only for the operator's own local single-user session. Anthropic
  keys require an explicit persistence confirmation, are validated with `GET /v1/models`, enter
  macOS Keychain through stdin, and are read by Claude through a Quarterdeck-owned `apiKeyHelper`.
  OpenAI retains a CSRF-protected, one-time stdin handoff to the fixed Codex CLI. Neither path
  returns, logs, or records a raw key in the ledger. Planning automatically selects a ready provider
  and starts the hidden AI adapter when needed. The new Approval view lists redacted pending calls
  and performs fixed approve/reject mutations behind explicit review, loopback Origin, CSRF, and
  JSON gates. The local ledger fsyncs the request before the governance API call and records a
  fixed outcome afterward; free-text notes enter the ledger only as SHA-256. AionUi and Paperclip
  are absent from normal navigation and appear only in a closed advanced-diagnostics disclosure.
  Version 1 is explicitly a single-owner surface whose local actor is `local_console`, not
  a multi-user identity system. Final source-console acceptance showed `chatgpt` and `account`
  auth modes with both registered runtimes ready; the UI labeled them separately, exposed no
  provider output or internal system name, kept diagnostics closed, had no browser warnings, and
  had zero horizontal overflow at desktop and 390x844 mobile sizes.
- The Connections view also exposes DeepSeek API Key, xAI API Key, and official Grok account login.
  DeepSeek/xAI keys use fixed Models endpoints and separate macOS Keychain items; source tests prove
  the secret is absent from argv, helper files, API responses, and ledger payloads. Grok account
  login is enabled only when the official `grok` executable is present. On this machine it is not
  installed, so the account action correctly remains unavailable while xAI API Key setup remains
  available. These providers deliberately report credential connection separately from
  `runtime_ready`; no DeepSeek/Grok Agent execution adapter is claimed or selectable yet. Live
  credential validation was not attempted because no key was entered during source acceptance.
- The Connections view now also exposes Ollama and LM Studio as local-model providers. Their
  endpoints are compile-time fixed to `127.0.0.1:11434` and `127.0.0.1:1234`; the UI accepts no
  custom URL or key. An explicit confirmation starts the vendor-owned local service, reads a
  bounded model-name list, starts the hidden AionUi adapter when needed, and creates or reconciles
  an OpenAI-compatible provider using only `ollama`/`lm-studio` non-secret placeholders. Runtime
  readiness requires a live server, at least one model, reconciled provider registration, and the
  team-selectable `aion_cli` Assistant. Source tests cover fixed endpoints, no-model fail-closed,
  fixed startup commands, confirmation, append-only evidence, registration payloads, and runtime
  gating. On this machine both apps/CLIs are installed, but their API servers were intentionally
  left stopped during source acceptance; live model execution therefore remains an explicit gate.
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
- Task deletion is implemented as an idempotent append-only `task_plan_deleted` visibility
  tombstone. The private plan file and all evidence remain byte-for-byte available; ordinary list,
  direct-get, dashboard, and startup-recovery paths hide tombstoned plans. Only ready, failed, and
  completed-unverified plans are eligible, while active work and parents with visible revisions
  fail closed. Work settings and the retained detail dialog expose the action behind an explicit
  confirmation dialog. Source-console acceptance opened and cancelled that dialog without deleting
  any real plan; the desktop layout and 390x844 mobile dialog had no horizontal overflow, all
  controls remained visible, and the browser console stayed clean.
- History now separates whole-Work visibility removal from exact-run private-content erasure. The
  latter is terminal-only and hash-confirmed; it removes the local plan body, exclusive Aion session,
  application-managed workspace, unshared planning materials and unshared CAS blobs, while keeping
  a content-free `task_run_erased` receipt. Shared sessions fail closed and shared/external data is
  reported as retained. Source and focused regression tests are complete; a fresh installed RC and
  non-destructive browser acceptance are still required before this becomes an Alpha claim.
- The unified Work view removes the duplicate task/team lists. Its Team tab graphically groups the
  selected work item's task-scoped team by reporting level, while Activity, Outputs, and Settings
  keep execution signals, outcome evidence, and lifecycle controls distinct. Legacy plans
  remain hash-compatible and display as a lead-centered organization without file migration.
  Today's currently labelled Task Teams panel is a read-only projection of the same plan ids, limited
  to confirmed, dispatching, running, approval-waiting, and input-waiting records. It stores no second team object
  and cannot edit hierarchy, runtime, model, evidence, or lifecycle state.
- Work Overview now places the AI adjustment chat directly under the current summary. A ready,
  failed, cancelled, or completed-unverified version can request changes to its objective, stages,
  Agent roles, reporting hierarchy, bounded loops, cadence, outputs, or checkpoints. The request
  creates a new planning child with source id/hash provenance and no execution side effect; the new
  version must be reviewed and hash-confirmed before dispatch. Active versions remain read-only.
- Any intact reviewed Work exposes an explicitly confirmed `Fork work` action. The new Work remains
  independently visible at version 1, binds source plan id/hash into its own confirmation hash, and
  records `task_plan_forked` metadata without dispatching an adapter. It copies no execution,
  approval, operator answer, artifact, or outcome state and returns to Workspace review before run.
- Failed and `completed_unverified` Work items expose `Run again` in the detail header. It prepares
  an idempotent ready child that preserves the reviewed structure while resolving the default Fast
  profile into advertised per-Agent model ids, uses the default `automatic` approval mode, writes a
  new version/hash, and records `task_plan_rerun_prepared` evidence. Preparation performs no runtime
  dispatch; manual approval remains selectable and the ordinary plan review checkbox/hash
  confirmation remain mandatory.
- Aion team executions now expose source-complete Start/Continue, Pause, and End controls in a
  fixed three-position Work group. Only the action accepted by the current state is enabled:
  Start/Continue resumes a runtime-confirmed pause and never bypasses initial plan/hash review.
  Pause/resume/cancel requests are fsynced before adapter calls; pending
  states remain visible until Aion confirms the resulting run state. Stop uses an explicit second
  confirmation, preserves partial outputs/evidence, and becomes `cancelled` only after the exact
  run is no longer active. Cooperative pause is not claimed as an OS-level process freeze, and
  workflow runs remain uncontrollable in the UI. Fake-adapter/API tests pass; a real task was not
  paused or terminated during source validation, so live run-control acceptance remains open.
- New confirmations and reviewed reruns default to the snapshotted `automatic` approval mode.
  After exact plan confirmation it creates the ordinary Paperclip approval, fsyncs policy evidence,
  and resolves each AionUi tool call allow-once through the same delivery path without a user
  prompt. A confirmation-screen switch selects `manual_all`. Existing `automatic_safe` plans
  retain their exact read-only allowlist, and records with no stored mode remain manual.
- Active Aion Work now exposes the current execution approval mode beside Pause/Continue/End.
  Auto-off is an immediate tightening; Auto-on requires explicit confirmation and affects only
  future tool calls. Existing paused approvals preserve their request-time policy. The endpoint
  uses expected-current-mode compare-and-set semantics, changes only `ExecutionState`, leaves the
  reviewed plan/hash untouched, writes requested/committed evidence, and recovers interrupted
  changes to the more restrictive mode. Fake-service, request-snapshot, crash-recovery, CSRF, and
  API validation tests pass; source validation did not change the policy of a live task.
- Manual approvals now render in the same Work attention slot as runtime operator questions.
  Quarterdeck accepts the inline binding only for its exact Aion approval source and an existing
  local `plan_id`; unrelated or malformed global approvals cannot appear under another task.
  Approve/reject, optional note, and explicit review acknowledgement happen without navigation.
  After a manual `qd_request_input` allow-once decision, the resulting suggested-answer panel
  replaces it in place. The global Approval view remains a cross-task queue and recovery surface.
- The normal ops MCP now has thirteen tools: `qd_python_package_status` replaces shell-based package
  presence checks, and `qd_request_input` lets an active planned Agent create one bounded operator
  question. Work and Today expose `awaiting_input`; an answer resumes the same confirmed AionUi
  team. Question/answer plaintext stays in the private task channel and only SHA-256 identities are
  appended to the ledger. A stale runtime refresh cannot overwrite a newly committed question.
  For ready plans, each non-lead employee can select one direct manager; self-reporting, missing
  employees, multiple roots, and cycles fail closed. Saving creates a ready append-only child
  version with a new confirmation hash and a hashed `task_plan_organization_revised` event rather
  than mutating the reviewed plan. A separate graphical loop editor allows self-review and cyclic
  collaboration with an explicit condition and 1-10 iteration cap, while the management tree remains
  acyclic. The complete loop contract is hash-bound and included in Paperclip and AionUi prompts.
  Because the current AionUi Team API exposes no verifiable round-limit control, this is plan-level
  enforcement and the UI does not claim a deterministic runtime cutoff. Confirmed and active teams
  are read-only. The effective hierarchy is included in both the Paperclip issue and AionUi execution
  prompt, while no second employee
  database or runtime is introduced. Source-console acceptance used the existing synthetic Bazi
  team: two reporting levels rendered correctly, changing the report editor's manager produced a
  three-level preview, the cycle-causing reverse choice disappeared, and the edit survived a full
  background refresh. A later acceptance added one loop, changed it to self-review, set its cap to
  four, edited the stop condition, and kept save enabled at desktop and 390x844 mobile widths. Both
  changes were cancelled, so the real plan remains revision 1 with zero loops and no new ledger
  event. At 390x844 the current four-item navigation, organization cards, manager/loop controls, and save
  action remained usable with zero page overflow and no browser warnings.
- Work now exposes evidence-based live execution progress instead of a generic running spinner.
  Active AionUi records refresh every 2.5 seconds and may show only an exactly mapped Agent slot,
  elapsed duration, slow/blocked state, safe tool identifier/status, response marker, timestamp,
  and collapsed repeat count. Each newly dispatched plan stage is also bound to one AionUi team
  work item, so Work can show `not_started`, `running`, `blocked`, `completed`, and failure evidence
  per stage without inventing percentages. Tool arguments, output, message bodies, arbitrary command
  titles, chain-of-thought, inferred stage completion, and fabricated percentages never enter the API.
  A legacy `completed_unverified` record gets at most one schema-versioned, read-only stage mapping
  backfill that cannot change terminal state, append another finish event, or rerun work; failed
  records do not use this path. Live acceptance against the completed synthetic Bazi run recovered
  all five confirmed stages: stages 1-3 were Agent-reported complete with four bounded activity rows
  each, stage 4 remained not started, and stage 5 remained blocked on stage 4. The Work item correctly
  stayed `completed_unverified` rather than claiming business success. Raw commands, response bodies,
  and percentages were absent. Desktop and 390px checks had zero page overflow; all five stage cards,
  twelve safe activity rows, New work, and Approvals remained reachable; browser logs were clean.
  Python is now 385/385; frontend tests are 38/38; ruff, mypy, TypeScript, Vite build, and both git-history
  and working-tree gitleaks scans are green.
- Per-Agent model selection is now a second level under runtime selection. The bootstrap API returns
  only bounded, secret-free model metadata from the active local adapters; the UI marks exact ids,
  rolling aliases, and runtime default separately. Saving a change creates a new immutable plan
  version whose hash binds both runtime and model, and AionUi receives that exact value at dispatch.
  Legacy plans keep their prior hash and render as runtime-default until explicitly revised.
- History is no longer a top-level navigation item. **Activity** shows the selected Work version's
  current bounded runtime signals; **History** folds its immutable run chain deterministically from
  `task_plan_confirmed`, requested, dispatched, continuation, and terminal ledger events. An ended
  Aion run with exact team/conversation identity can be continued as a new hash-bound child while
  retaining `continued_from_plan_id` provenance to the selected run. The follow-up body is sent only
  to the same local Aion team and only its SHA-256 enters the ledger. Active Work, workflow runs,
  missing identity, unconfirmed delivery, or unavailable governance fail closed. New snapshots are
  bounded by the continuation dispatch timestamp, so old conversation activity cannot appear as
  new-run evidence. Tombstone retention and `completed_unverified` versus outcome proof remain unchanged.
  Wrapped system jobs that cannot belong to one Work item remain available in the collapsed
  Settings diagnostics section. Missing expected ledger evidence is rendered as a warning rather than a healthy
  state. Backend deletion-retention coverage remains in the full suite; the current source suite
  passes 390 Python and 40 frontend tests; ruff, mypy,
  TypeScript, and the packaged Vite build are green. Rebuilt source-console acceptance showed the
  honest empty Agent-run state and eight real wrapped-automation rows; 1964px desktop and 390x844
  mobile had zero document overflow, the wide automation table scrolled only inside its panel, and
  the browser console remained clean. No real task was confirmed or launched for this acceptance.
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

### Non-blocking console follow-up

- Rename Today's **Task Teams** heading to **Active Work / 正在推进** and make each summary card
  navigate directly to the corresponding `Work -> Team` view. The current cards are honest,
  read-only summaries and the action queue can route active work, but the cards themselves are not
  yet navigation controls. This is a discoverability gap, not a separate data model or evidence gap.

## Open gates and deferred items (status explicit)

1. **Private Release validation** — complete for commit `3bd2b0d`; exact assets, identity,
   checksums, clean-tree manifest, SPDX package, blank install, dual CLIs, synthetic wrap, and
   packaged browser surface passed.
2. **Rollback-safe production RC migration** — complete for the prior exact Actions wheel;
   encrypted backup and exact rollback bundle exist, legacy state was adopted in place, CAS
   remained unchanged, and services are single-instance. The new doctor change requires a rebuilt
   artifact before another RC canary begins.
3. **Independent Alpha canary** — preserve failed `alpha-rc-1` through `alpha-rc-4` and
   `m2-canary` as immutable historical evidence. Install macOS 26.5.2 and reboot, then require a
   temporary interval probe to execute repeatedly without a pended trigger. Only then rebuild and
   install the exact RC and start a new append-only 24-hour contract. No prior contract is reset,
   relabeled, or reused. Checkpoint only if the recomputed verdict has no hard or pending blocker.
4. **Professional brand review** — the exact organization, private repository, and domain are
   reserved, but a qualified confusing-similarity review for intended markets remains required.
5. **Mobile Beta promotion (non-blocking for Alpha)** — Alpha does not advertise mobile access.
   Private HTTPS, pairing, and PWA remain Beta until a real iPhone Safari and Chrome
   pairing/PWA/write/revoke test passes.
6. **Public-main release sequence** — merge only after the blocking private gates pass, make the repository
   public, immediately enable required checks/security settings, validate the exact main SHA,
   create an approved annotated Alpha tag, and verify the resulting prerelease assets and
   attestation from a blank install. `PUBLIC_RELEASE_APPROVED` must be absent at every earlier step.
7. **Seven-day stable soak** — Alpha does not satisfy Stable. Feed-monitor and sox-monitor adoption,
   isolated recovery acceptance, and seven elapsed days remain required for `v0.1.0`.
8. **Telegram digest** — secure hidden-input CLI and total-console setup/test/disable tooling is
   implemented, atomically writes only the `0600` secret file, refuses silent replacement, hides
   validation inputs, and records no credential values. Production credentials are still absent
   and the separately confirmed fixed delivery probe must be exercised during soak without
   exposing or copying tokens into chat, repo, argv, logs, or plists.
9. **Daily mail consent and OAuth** — before enabling the adapter or creating the hidden
   09:00 America/Los_Angeles task, the operator must create and privately import a Google Desktop
   OAuth client, then explicitly approve Gmail readonly OAuth
   and sending sender/subject/date/message-id metadata to the selected model provider,
   set `mail.model_metadata_consent: true`, and bind a separate internal assistant only to the
   mail profile. Then run one real metadata-only acceptance check; automatic
   send/draft/delete/label mutation remains out of scope.
10. **M6 commercial gate** — no practitioner UI or private product repository until a
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
  added three allowlisted launch tools. Their direct then-eleven-tool handshake, isolated workflow,
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
  the normal thirteen-tool ops surface. `gws 0.22.5` is installed under the user-owned Quarterdeck
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
- AionUi execution confirmations follow the same truth split: AionUi pauses the tool, Paperclip
  stores the single-owner decision, and Quarterdeck binds and consumes it once. The adapter rejects
  permanent allow, unknown option sets, request-hash drift, and duplicate approval markers.
- `automatic` does not remove this truth split: the approval object and evidence chain remain, and
  the snapshotted plan policy supplies the allow-once decision. Existing `automatic_safe` records
  continue using their fixed exact-name policy. `manual_all` requires the local click for execution
  tools. Operator-input notifications are exempt because they perform no external side effect and
  otherwise could deadlock before the question becomes visible.
- Paperclip v2026.707.0 requires a board actor for approve/reject. The local console uses the
  service-agent token for reads and projections, then strips authorization only for the fixed
  decision request after proving the exact API base is loopback and `/api/health` reports
  `deploymentMode=local_trusted`. Remote or authenticated deployments fail closed.
- Live 2026-07-15 acceptance reproduced the former service-agent `403`, installed the repaired
  client, and reconciled the operator's exact pending allow-once decision. Paperclip records
  `local-board`, the original AionUi call has one finished tool record, and the ledger has exactly
  one delivery request and one delivery finish. The resumed Agent then raised a new, distinct
  knowledge-base inspection approval; it remains pending and was not implicitly approved.

## Next task

Freeze and commit the current post-release product source, validate a clean private Release
artifact, install and smoke-test that exact artifact, then start a new append-only `alpha-rc-3`
canary. Complete professional brand review in parallel. Keep mobile access unadvertised until the
separate physical iPhone Beta acceptance passes. Keep failed `alpha-rc-1`, failed `alpha-rc-2`,
failed `m2-canary`, and every legacy ledger/CAS object intact. Do not make the repository public,
set `PUBLIC_RELEASE_APPROVED`, create a tag, adopt feed-monitor/sox-monitor, or build the
practitioner UI before their independent gates pass.

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
