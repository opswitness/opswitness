# Alpha canary evidence

The Alpha release gate accepts machine-readable observations, not operator-entered timestamps or
`passed` switches. The authoritative input is a closed six-file bundle uploaded as the GitHub
Actions artifact `alpha-canary-observation-<producer-run-id>-<producer-run-attempt>`:

- `alpha-canary-observation.json`;
- `sources/soak-status.json`;
- `sources/cadence-summary.json`;
- `sources/recovery-summary.json`;
- `sources/clean-install-summary.json`;
- `sources/first-work-summary.json`.

The bundle must be uploaded by the fixed `release-canary-observation` workflow on the protected
`alpha-canary-observation` environment and dedicated `opswitness-alpha-canary` runner group with
the `self-hosted, macOS, ARM64, opswitness-alpha-canary` labels. Restrict that group to this one
workflow. The host must be provisioned with the root-owned, mode `0444`
`/Library/Application Support/OpsWitnessCanary/host-identity.sha256` marker; its value must equal
the protected `ALPHA_CANARY_HOST_IDENTITY_SHA256` value. That workflow accepts no evidence path,
status, timestamp, or manual verdict input.

Before writing a request, the workflow requires `/Users/Shared` to be the root-owned sticky
directory and every existing `/Users/Shared/OpsWitnessAlphaCanary` handoff directory to be owned
by the runner, mode `0700`, non-symlink, and free of ACL grants. It never repairs or takes over an
unsafe existing tree. It then writes a run- and host-bound export request, ingests one stable
closed bundle from the restricted validation system, validates the observation's host identity
against the protected value, and reports both the observation file SHA-256 and GitHub artifact
SHA-256.

The `release-canary-evidence` workflow uses the attempt-specific GitHub API before extraction. It
requires the protected numeric workflow ID, fixed workflow path, repository name and numeric ID,
candidate commit on `main`, `workflow_dispatch` event, requested run attempt, and
`completed/success` conclusion. It requires the artifact name and GitHub API digest to equal the
operator-reviewed upload digest, downloads the exact ZIP, recomputes that digest, extracts only
regular non-colliding paths, verifies the caller-supplied observation SHA-256, requires exactly
those six regular non-symlink files and one `sources` directory, and runs
`scripts/release_candidate.py record-canary`. An `alpha-canary` environment reviewer still
approves the sealing workflow, but cannot replace measured evidence with a manual verdict.

## Observation schema

The input uses schema version 1 and evidence type `opswitness-alpha-canary-observation`. Its exact
machine-readable contract is [alpha-canary-observation.schema.json](alpha-canary-observation.schema.json).
The five sources use [alpha-canary-source.schema.json](alpha-canary-source.schema.json). Every JSON
file is canonical and every object is closed: omitted and unrecognized fields fail validation.
The Python validator recomputes every source SHA-256 before enforcing cross-field rules that JSON
Schema cannot express:

- `candidate` must match the candidate workflow run and attempt, commit, tag, exact notarized DMG
  SHA-256, and exact schema-3 manifest SHA-256;
- `run` must match the producer workflow run and attempt and bind a privacy-preserving host
  identity digest equal to the protected dedicated-host value; its normalized UTC window must be
  24–48 hours, begin after the candidate was created, and end in the past;
- every check must name its fixed source path and authority, use either `json` or `log_summary`,
  match the actual source bytes by SHA-256, and have a non-future capture time;
- soak must be continuous for the complete observation window with the frozen 24-hour minimum,
  48-hour maximum, no blockers, and an authoritative ledger-tail digest;
- cadence must have at least two successes, no failures, no gap beyond interval plus frozen grace,
  coverage at both window boundaries, and an event-stream digest;
- recovery must reconcile the original run ID, report zero duplicate dispatches and zero unknown
  process stops, and reverify ledger and artifact evidence;
- clean install must prove the exact DMG and manifest on macOS 14+ arm64, no preinstalled runtime,
  accepted Gatekeeper/notary evidence, loopback-only services, and the complete four-service
  runtime chain;
- first Work must bind the same DMG and manifest, prove Codex login and explicit write approval in
  a blank managed workspace, commit both artifact digests, reverify CAS, avoid user-file reads and
  external side effects, and explicitly avoid claiming a business result.

`soak-status.json` contains the closed `qd soak status --json` fields plus its ledger-tail digest.
The validator independently checks its status, exact window, frozen duration, zero blockers and
projection backlog, per-job successes/failures/gaps, and agreement with `cadence-summary.json`.
The remaining summaries repeat the candidate, observation run, capture time, authority, and their
closed evidence fields; all details must exactly match the observation.

Raw ledger and process logs may remain in the restricted validation system; their event-stream,
ledger-tail, recovery-event, artifact, and CAS digests are retained in these summaries. Do not put
credentials, account identifiers, absolute user paths, tokens, or customer content in the bundle.

## Sealed evidence and promotion

`record-canary` embeds all five verified secret-free sources, their checks, the observation
workflow identity, and observation SHA-256 into canonical schema-2
`alpha-canary-evidence.json`. Promotion downloads that exact sealed artifact, verifies its
configured SHA-256, recomputes every embedded source digest, revalidates every metric against the
exact candidate, and fails closed on any missing, rewritten, stale, future, or inconsistent field.
Promotion independently repeats the attempt-specific producer and artifact transport checks for
both the candidate and sealed canary artifact; it never trusts an artifact only because another
workflow used the requested name. It also requires the sealed host identity to match the protected
dedicated-host value.

Completing this evidence workflow does not set `PUBLIC_RELEASE_APPROVED`, create a tag, publish a
release, or shorten the 24–48 hour canary.
