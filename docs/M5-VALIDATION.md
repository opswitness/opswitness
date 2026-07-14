# M5 Open-source v0.1 Validation

Date: 2026-07-12 America/Los_Angeles

Status: name-independent release engineering is ready; public release is **NO-GO**.

## Release engineering completed

- CI now runs tests, ruff, mypy, package build, manifest generation, and the synthetic
  showcase on Ubuntu and macOS. A separate job enforces DCO signoffs.
- The tag workflow builds wheel and sdist, emits SHA-256 checksums and build metadata,
  generates an SPDX JSON SBOM, creates GitHub artifact attestations, and attaches the
  files to a GitHub release. A tag fails closed unless the repository variable
  `PUBLIC_RELEASE_APPROVED` is exactly `true`.
  Its OIDC, attestations, and artifact-metadata permissions match the current official
  `actions/attest@v4` contract.
- The approval check is an independent `preflight` job and the build job depends on it. An
  unapproved tag therefore fails before checkout, archive creation, SBOM, attestation, artifact
  upload, or release creation. Preflight has no token permissions; write/OIDC permissions belong
  only to the build job. Workflow-dispatch rehearsals build and upload an Actions artifact for
  inspection but neither attest nor create a release.
- Every external GitHub Action is pinned to a full 40-character commit from its official
  repository. Checkout, setup-python, setup-node, and upload-artifact were advanced to their
  current supported majors before pinning. Dependabot is configured weekly for GitHub Actions,
  the root uv project, and the console npm lockfile; CI rejects any future mutable `uses:` ref.
- A local release audit found that Hatch's default sdist discovery could include an untracked
  `.claude/settings.local.json` and local skill files. No archive was published. The build now
  uses an explicit source allowlist, and both CI and release run `verify_distribution.py` before
  hashes, SBOM, attestation, or upload. Apart from Hatch's tracked root `.gitignore`, the verifier
  rejects hidden/private paths, archive links, path traversal, unexpected roots, untracked files,
  and missing license/console assets.
- `NOTICE`, `SECURITY.md`, and a secret-free synthetic fleet showcase are committed release
  inputs. The showcase covers wrapped execution, outage backlog, ordered replay,
  reconcile-without-repost, one-shot approval evidence, artifact eval/signoff, and the
  execution/outcome digest split.
- Quarterdeck keeps two structurally separate MCP profiles. `~/.local/bin/qd mcp` exposes eleven
  evidence/projection/workflow tools and no mailbox data. `qd mcp --profile mail` exposes only
  fixed-query metadata status/check and no fleet mutation. Credentials are read only by
  Quarterdeck from permission-checked local configuration, not copied into AionUi.

## Local evidence

- 2026-07-13 release-boundary rehearsal: rebuilt wheel and sdist pass the tracked-only verifier;
  the sdist has 114 paths, exactly one documented hidden path (`.gitignore`), and zero private
  path hits. Three regression tests prove a valid tracked archive passes while `.claude` and an
  arbitrary untracked Python source file fail closed. No affected archive was published.
- Full-history DCO check: all current non-merge commits are signed off.
- Synthetic showcase: first gate `defer`, second gate `allow`, outage backlog 5, replay 5,
  second drain 0, final backlog 0, healthy digest.
- Fresh isolated wheel installation: 0.06 seconds.
- First isolated `qd wrap --job first-run -- /usr/bin/true`: 0.94 seconds.
- The local-only core therefore clears the under-ten-minute first-run target without
  counting Paperclip/Postgres installation.
- The current `428deef` wheel was independently installed with the MCP dependency into a fresh
  `/private/tmp` uv tool root. It exposes the post-canary `soak` and `console` command surfaces,
  completed an isolated `/usr/bin/true` wrap in 0.123 seconds, and served its packaged console on
  loopback: health, JavaScript, and CSS each returned HTTP 200. This rehearsal did not replace the
  production uv tool or touch the canary.
- Existing AionUi 2.1.33 is notarized and arm64. The local MCP entry was added without an
  env block. The first handshake exposed a missing MCP extra; the user-level tool was then
  reinstalled with `--with mcp`. A direct MCP client handshake against that stable binary
  listed exactly eight expected tools. On 2026-07-13, AionUi's own Settings -> Tools ->
  quarterdeck -> Check MCP Availability succeeded and expanded the same eight-tool list.
- ADR-0004 adds three tools without replacing the canary's production uv tool. A direct stdio
  handshake against the isolated repository environment listed exactly eleven tools. An
  isolated fixed-command launch completed `requested -> dispatched -> run_started ->
  run_finished` with exit 0, while a dispatch-fsync fault test proved the worker never executes.
  The real `0600` manifest now contains only `quarterdeck-showcase`.
- The live AionUi 2.1.33 Manual Task acceptance passed on 2026-07-13. A first attempt using
  built-in Claude was rejected before execution because AionUi normalized the cron agent mode
  to `bypassPermissions`; that task was deleted. The accepted task uses a connection-tested
  custom Claude ACP agent whose `yolo_id` and persisted task mode are both `default`, with a
  dedicated assistant bound only to the Quarterdeck MCP.
- A second enabled custom Assistant named `每日工作台` is visible on AionUi's main Assistants
  screen. A post-implementation threat review rejected placing mail data and workflow mutation
  tools in that same assistant: its persisted permission is `fixed/default`, its mail prompt and
  rules were removed, and the normal profile remains exactly eleven tools. AionUi connection
  `mcp_019f5d9b-b884-7831-b991-eda395e98cb6` passed a test exposing only `qd_mail_status` and
  `qd_mail_check`, but remains disabled; a future mail assistant must bind only that profile in
  a separate conversation. The pinned
  `gws 0.22.5` binary is installed, but Gmail OAuth, metadata-transmission consent, and the daily
  task are intentionally absent; no mailbox was accessed during this validation.
- Mail consent is enforced for both MCP and total-console sources before the Gmail command can
  run. A hostile failure test makes the summarizer exception echo a private sender and subject;
  neither reaches the returned job nor the ledger, which records only the fixed
  `mail_summary_failed` reason code.
- The total console now turns the disabled mail control into an explicit local setup dialog. Its
  two acknowledgements separately cover Gmail readonly OAuth and the four metadata fields sent to
  the configured AionUi model. The backend accepts only literal true values and can execute only
  `gws auth login --readonly --services gmail`; it revalidates the pinned version, encrypted
  credential storage, live token, and readonly scope before activation. A private managed file
  carries only enable/consent booleans and leaves user `config.yaml` byte-for-byte unchanged.
  Revocation disables future access even if its audit append fails. Real desktop and 390x844
  browser acceptance proved one acknowledgement keeps the action disabled and both enable it;
  the action itself was not clicked, no authorization event was written, and no mailbox was
  accessed. The full suite passes 261 tests in three consecutive runs.
- Telegram configuration is now available from the same loopback connection view without making
  the console a generic secret editor. Both token and chat ID are password inputs, are never
  returned, and reach only the existing atomic `0600` secrets merge after a literal-true storage
  acknowledgement. Configure/test/disable share one service lock. Test delivery has a separate
  confirmation and fsyncs `telegram_test_requested` before the fixed probe can leave the machine;
  removing credentials disables future sends even if its final audit append fails. API regressions
  prove Pydantic 422 responses redact both submitted values. Desktop and 390x844 acceptance showed
  empty password fields and a disabled save action; no credentials were entered, no Telegram event
  was written, and no message was sent. The resulting full suite passes 270 tests in three
  consecutive runs.
- Mail summarization now treats deletion of its temporary AionUi Team as part of success. A
  simulated cleanup failure prevents the summary from being returned and exposes only a fixed
  cleanup error, never the upstream exception or email fields.
- Plan drafting uses the same mandatory ephemeral-Team cleanup primitive. A valid model plan with
  a failed Team deletion is rejected before it can enter the user-confirmable `ready` state.
- Planning and mail summarization now use distinct per-request `0700` workspaces instead of shared
  directories. Focused tests prove unique paths, cleanup after success, cleanup when Team creation
  fails, and fail-closed behavior when workspace removal cannot be confirmed. A local no-run probe
  confirmed that AionUi's Team list returns the exact persisted workspace; the probe Team and
  workspace were removed and the Team count returned to zero. A second no-run probe confirmed that
  a real AionUi 2.1.33 Team ID can be atomically bound, reconciled, and removed without exposing the
  ID. Quarterdeck now fsyncs a `0600` marker before Team creation and, under the startup lease,
  reconciles only an exact
  workspace/name/optional-ID match with started/finished ledger evidence. Corrupt, ambiguous, or
  unconfirmed residue blocks startup. A pre-marker crash can leave only an unmarked local directory,
  which also blocks for manual inspection instead of being deleted by inference.
- Startup recovery atomically resumes only durable `confirmed` plans and refreshes active runs.
  Stranded `planning` and `dispatching` plans fail closed with fixed evidence because their AionUi,
  Paperclip, or workflow side effects cannot be proven absent. Concurrent confirmation and dispatch
  tests prove that one plan can create at most one remote execution path.
- Planning, dispatch, runtime-refresh, and schedule-parser failures now cross the console boundary
  only as fixed reason codes and fixed user guidance. Hostile exceptions containing private paths
  and plan-like text are absent from both API records and append-only ledger events.
- `qd console serve` acquires an exclusive state-directory lease before browser launch, recovery,
  or remote work. A second service is rejected even on a different port; recovery failure releases
  a lease acquired by the app, while graceful shutdown drains background work before release.
  Live source-tree acceptance held the primary service on `127.0.0.1:8765`; a second start on
  `8766` exited 2 with the fixed `another console instance is already active` message. The primary
  health endpoint stayed green, the existing `ready` plan record was byte-state unchanged, and the
  state directory/lease modes were `0700`/`0600`.
- Initial confirmation granted session-level access only to `qd_workflow_start` and the read-only
  `qd_workflow_status`, never to the whole server. A later single **Run now** click required no
  confirmation. Later UI verification inadvertently activated the synthetic task twice through
  stale accessibility targets, creating `01KXEQE941TF2HD4CP9ZQ4RFHX` and
  `01KXEQM5PVHH43HDA6VYQCZHKP`. Both runs were allowlisted, exited 0 with
  `degraded=false`, and recorded the complete authoritative workflow event chain plus Paperclip
  acknowledgements; no production fleet job ran. The task remained `Permission = default` and
  AionUi recorded `last_status=ok`.
- After the Mac was explicitly unlocked, a fresh operator-visible **Run now** acceptance on
  2026-07-13 at 18:11 PDT produced `01KXF2VC2NGNK7NFKEXWEBWZEY`. AionUi reported `succeeded`;
  the authoritative ledger independently folded the same run to exit 0 in 0.327 seconds with
  `degraded=false`, and an immediate projector drain reported `pending=0`. This was the third
  successful `workflow:quarterdeck-showcase` run and again executed no production fleet job.
- The local total console was also exercised in a real browser against port 8765. At a 390x844
  viewport the document width remained exactly 390 pixels with no overflowing element. At the
  desktop viewport the dashboard exposed all four task columns and live AionUi/Paperclip/ledger
  status. The existing four-agent plan rendered its objective, cadence, roles, phases, approval,
  artifact, risks, and plan hash. `确认并运行` was disabled by default, enabled only while the
  explicit confirmation checkbox was selected, and became disabled again when it was cleared;
  the plan was not dispatched. The browser console contained no warnings or errors.
- The same acceptance exposed a trust bug in the dashboard: `healthy_jobs` counted every job whose
  latest exit was successful, even when that job was not covered by an active schedule. The
  console now derives health from the shared effective-schedule, watchdog, lifecycle, outcome,
  and digest contract over one authoritative ledger snapshot. Regression tests cover no active
  schedules, a successful but unregistered stray job, and projection backlog. The live dashboard
  consequently reports `1/1 完整覆盖` for the sole monitored canary instead of the misleading
  historical-run count `5/5`.
- A second fail-open presentation path was removed: an unavailable Paperclip approvals query used
  to be swallowed and rendered as zero pending approvals. The bootstrap response now distinguishes
  a verified zero from an unavailable query. The latter renders `—` and `审批状态不可用`, marks the
  Paperclip integration for attention, and never displays `当前无待审批项`. Tests pin both the
  successful-zero and unavailable branches.
- The acceptance used the repository virtual environment only. Production `~/.local/bin/qd` and
  every launchd service remained unchanged while the canary time gate continues to accumulate.
  The guarded agent references AionUi's versioned Node/ACP runtime, so every AionUi upgrade must
  repeat its connection test and MCP availability check before **Run now** is trusted again.
- The separate `@paperclipai/mcp-server@2026.707.0` package was audited but deliberately
  not mounted. It exposes approval decisions, other mutations, and a general `/api` escape
  hatch, requires a bearer token in its environment, and offers no documented read-only
  mode or scoped read-only token. Paperclip Web UI remains the sole approval-decision door.
- Paperclip governance UI and artifact work-product projection were already accepted live
  under M2/M4; see `M2-VALIDATION.md` and `M4-VALIDATION.md`.

## Public-release blockers

1. **Brand clearance:** `QUARTERDECK` is an active US registration (serial 98265168,
   registration 7860652) in class 42 for online software, and the name has substantial
   historic and current software usage. Treat the working name as unavailable for public
   commercial release unless qualified counsel clears it. A project-wide rename is the
   preferred path. On 2026-07-13, the official USPTO system returned no results for the
   exact `OpsWitness` forms or the documented broader `op`/`witness` orderings; PyPI, npm,
   the GitHub namespace, and the `.com` RDAP endpoint also returned `404`. This advances
   `OpsWitness` to an operator-decision candidate, not to a legally cleared or reserved name.
2. **No remote:** this repository has no git remote, so neither GitHub Actions nor private
   vulnerability reporting has run in the real hosting environment.
3. **No release publication:** no tag, GitHub release, package index upload, org creation,
   domain purchase, or public announcement may occur until the name is settled and the
   resulting metadata is updated consistently.
The release workflow intentionally does not publish to PyPI yet. Trusted publishing,
repository URLs, package name, SBOM identity, and provenance subject must be configured only
after the final brand and remote are known.
