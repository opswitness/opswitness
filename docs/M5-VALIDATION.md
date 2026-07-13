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
- `NOTICE`, `SECURITY.md`, and a secret-free synthetic fleet showcase are committed release
  inputs. The showcase covers wrapped execution, outage backlog, ordered replay,
  reconcile-without-repost, one-shot approval evidence, artifact eval/signoff, and the
  execution/outcome digest split.
- Quarterdeck MCP now exposes eight tools, including artifact listing and CAS verification.
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
  listed exactly eight expected tools. Final in-app handshake confirmation is still pending
  because the Mac locked before the result could be read.
- Paperclip governance UI and artifact work-product projection were already accepted live
  under M2/M4; see `M2-VALIDATION.md` and `M4-VALIDATION.md`.

## Public-release blockers

1. **Brand clearance:** `QUARTERDECK` is an active US registration (serial 98265168,
   registration 7860652) in class 42 for online software, and the name has substantial
   historic and current software usage. Treat the working name as unavailable for public
   commercial release unless qualified counsel clears it. A project-wide rename is the
   preferred path.
2. **No remote:** this repository has no git remote, so neither GitHub Actions nor private
   vulnerability reporting has run in the real hosting environment.
3. **No release publication:** no tag, GitHub release, package index upload, org creation,
   domain purchase, or public announcement may occur until the name is settled and the
   resulting metadata is updated consistently.
4. **AionUi acceptance:** unlock the Mac and rerun `Check MCP Availability`; record a
   successful local handshake and eight-tool listing.

The release workflow intentionally does not publish to PyPI yet. Trusted publishing,
repository URLs, package name, SBOM identity, and provenance subject must be configured only
after the final brand and remote are known.
