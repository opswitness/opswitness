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
- `NOTICE`, `SECURITY.md`, and a secret-free synthetic fleet showcase are committed release
  inputs. The showcase covers wrapped execution, outage backlog, ordered replay,
  reconcile-without-repost, one-shot approval evidence, artifact eval/signoff, and the
  execution/outcome digest split.
- Quarterdeck MCP now exposes eleven tools: the original evidence/projection surface plus
  allowlisted workflow catalog, asynchronous start, and ledger-folded status.
  The stable user-level MCP command is `~/.local/bin/qd mcp`; credentials are read only by
  Quarterdeck from its permission-checked local configuration, not copied into AionUi.

## Local evidence

- Full-history DCO check: 33 commits verified at the time of this snapshot.
- Synthetic showcase: first gate `defer`, second gate `allow`, outage backlog 5, replay 5,
  second drain 0, final backlog 0, healthy digest.
- Fresh isolated wheel installation: 0.06 seconds.
- First isolated `qd wrap --job first-run -- /usr/bin/true`: 0.94 seconds.
- The local-only core therefore clears the under-ten-minute first-run target without
  counting Paperclip/Postgres installation.
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
- Initial confirmation granted session-level access only to `qd_workflow_start` and the read-only
  `qd_workflow_status`, never to the whole server. A later single **Run now** click required no
  confirmation and created run `01KXEQM5PVHH43HDA6VYQCZHKP`. AionUi reported `succeeded`; the
  authoritative ledger recorded `requested -> dispatched -> run_started -> run_finished`, exit
  0, `degraded=false`, followed by both Paperclip comment projection acknowledgements. The task
  remained `Permission = default` and AionUi recorded `last_status=ok`.
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
