# OpsWitness Current Progress

Last verified: 2026-07-29 PDT

This is the current handoff and decision record for OpsWitness. It separates what a friend can
download today, what exists only in the development source, and what still needs an exact rebuilt
App before it can be presented as working product behavior. Historical validation documents remain
immutable evidence; this file does not rewrite a failed or superseded release gate.

## Executive status

**The public Alpha is available for a small, informed friend test, but the current download is not
the latest development source and is not ready for broad promotion.**

| Surface | Current truth |
|---|---|
| Public website | `https://opswitness.com/` is live and shows **Download Alpha** |
| GitHub release | `v0.1.0-alpha.1` is a GitHub Prerelease, published 2026-07-27 |
| Public Mac download | `OpsWitness-0.1.0-alpha.1-macos-arm64.dmg`, macOS 14+ / Apple Silicon |
| Signing boundary | Ad-hoc signed and **not notarized**; Gatekeeper displays an Apple verification warning |
| Public DMG SHA-256 | `4d1dbd8694ce487d76dadcc573f1c70e1df0d1dcce7100bc46acfaebb8c54956` |
| Public repository head checked | `main` at `12d26627a1f6beb7127af0b2fe68521f9eacce2d` |
| Active development tree | Local branch `codex/opswitness-alpha-release` at `a58d039`, with intentional uncommitted App and website work |
| Broad launch verdict | **No** — rebuild, complete first-Work acceptance, recovery, clean-install and executable canary are still open |

The public DMG had nine recorded downloads when the release was checked on 2026-07-28. Download
count is not an acceptance test.

## What a friend can try today

The current public Alpha is appropriate only for synthetic or non-critical testing by someone who
understands the Gatekeeper warning and can report failures.

- Download the Apple Silicon DMG from the public website or GitHub Prerelease.
- Open the local single-operator App and connect the supported Codex account flow.
- Review a proposed Work before it starts.
- Observe approvals, local run state, artifacts and evidence surfaces that are present in that exact
  installed build.

Do not ask a tester to use customer secrets, production files, financial actions, external sending,
deletion, publication or other irreversible work. Do not tell a tester that the current DMG contains
the newest Agent Contract, Knowledge Hub or onboarding fixes until an exact rebuilt DMG proves it.

## Current development source

The development source is materially ahead of the public DMG.

| Area | Development status | Verified boundary | Required before user promise |
|---|---|---|---|
| First-use provider choice | Codex is selected by default; the supported account sign-in action is visible | Frontend test coverage | Rebuilt App and real first-use run |
| First-Work progress | Uses observed stage state, real elapsed time and exact approval order instead of a generic spinner or invented percentage | 123/123 frontend tests | Rebuilt App, two real approvals and evidence review |
| Approval refresh | Polls every 1.5 seconds and refreshes when an approval state exists without a rendered approval card | 123/123 frontend tests and 29/29 onboarding backend tests | Real runtime interruption and recovery drill |
| Failed-task editing and conversation history | A planning failure now returns the previous task to the composer; an edit creates an immutable retry in the same conversation, and retained earlier versions render above the current turn without forcing a user who scrolled up back to the bottom | 225/225 console backend tests, 123/123 frontend tests, TypeScript check and production UI build | Rebuilt App visual acceptance and a real failed-planning retry |
| Agent Contract v2 | Source-complete editor, version, diff, preview and supported Aion approval bridge | Source tests and support matrix | Fresh executable RC; strict adapter remains unavailable |
| Docs Center and naming | Six offline operator topics plus canonical naming contract are in source | Frontend tests | Rebuilt App visual and offline acceptance |
| Knowledge Hub lexical core | Named collections, snapshot import, SHA-256 dedupe, card review, FTS5 search and review-first Work binding are implemented in source | Source tests and closed product contract | Alpha.2 bundle, backup/restore, packaging review and clean install |
| Semantic search and safe H5 export | Implemented as opt-in local source features | Source tests and documented limits | Alpha.3 model/runtime packaging, security and export acceptance |
| Recovery Agent | Bounded diagnosis and identity-preserving recovery exist; Repair Work remains manual and unexecuted until confirmed | Source tests | Rebuilt App recovery drill; no self-patching claim |

The strict Agent Runtime is not available. The current Aion-compatible mode cannot turn shared
Workspace instructions, loop counts, timeouts or file scopes into OS-level isolation or hard
cutoffs. A Contract requiring strict isolation must continue to fail closed.

## Evidence refreshed on 2026-07-29

- `console-ui`: 123 passed, 0 failed; TypeScript validation and the production Vite build passed.
- Repository Python 3.12 tests: 825 passed in two isolated invocations. The configuration-layering
  tests were run separately so their default-path assertions were not overridden by the temporary
  paths required to isolate this Mac's existing OpsWitness and Quarterdeck data.
- `tests/test_console.py`: 225 passed, including immutable failed-planning retries, request and
  ledger tamper rejection, monotonic revision numbers, complete retained conversation history,
  CSRF enforcement, and request-lineage-bound erasure recovery.
- `tests/test_console_onboarding.py` under the repository Python 3.12 environment: 29 passed,
  1 third-party deprecation warning.
- Running the same backend test with the host's default Python 3.9 fails during third-party pytest
  plugin import. This is an invalid test environment because the project requires Python 3.12; it is
  not counted as a product test result.
- GitHub reports the exact Prerelease and four assets: DMG, wheel, source distribution and
  `SHA256SUMS`.
- The live website returns the phrases **Download Alpha**, **Ad-hoc signed** and **Not notarized**,
  and names the exact public DMG.

No new DMG, mounted-DMG smoke, first-Work success, restart recovery, clean Mac install, notarization,
or 24–48 hour executable canary has been completed for the current development source.

## Known documentation drift

The active development branch's README still says that the Alpha and website do not exist. That
statement is obsolete: the website and Prerelease are live. The README must be corrected without
weakening the warning that the public DMG is ad-hoc signed, not notarized, and older than the current
source.

The support matrix correctly distinguishes source-complete features from the public Alpha contract,
but the phrase “Supported” must never be copied into release notes unless the exact rebuilt asset has
passed its executable gate.

## Priority and blocker chain

### P0 — make the first downloadable experience trustworthy

1. Reconcile README and current-status documentation with the live Prerelease.
2. Freeze the intended post-alpha.1 source without discarding unrelated local changes.
3. Complete the exact vendored-runtime hashes, license/NOTICE inventory and redistribution reviews.
   The checked-in lock currently says `blocked`; hiding a provider in the UI does not remove its
   bundled code or approve redistribution.
4. Rebuild the corrected Apple Silicon App and generate a new exact DMG/checksum identity.
5. Install that exact DMG and complete the whole first-use flow:
   local runtime, fresh data choice, Codex sign-in, customer-reply example, two expected local-save
   approvals, artifact review and explicit sign-off.
6. Quit/reopen during or after the Work and prove reconciliation does not duplicate dispatch.
7. Repeat from a clean macOS 14+ Apple Silicon environment without external Python, Node,
   PostgreSQL, Paperclip, AionUi or Codex CLI.
8. Run the new executable canary. Prior CLI or alpha.1 evidence cannot approve the rebuilt App.

Notarization is a separate public-trust gate. It can remain deferred for a very small informed friend
test, but broad promotion must not hide the Gatekeeper consequence.

### P1 — graduate source-complete product surfaces

1. Package and accept the Knowledge Hub lexical core as `v0.1.0-alpha.2`.
2. Package and accept Agent Contract v2, Docs Center, naming and human-approved experience
   candidates in the same exact release candidate or an explicitly later one.
3. Prove backup/restore, deletion retention, digest revalidation and no sensitive body leakage into
   the ledger, logs or Paperclip.

### P2 — optional local discovery and sharing

1. Complete pinned-model and runtime redistribution review for semantic search.
2. Verify offline-only semantic fallback behavior.
3. Complete redaction, XSS, secret/path sentinel and zero-network checks for safe H5 export.

## Claude review brief

Claude should review this file together with `README.md`, `docs/SUPPORT-MATRIX.md`,
`docs/KNOWN-LIMITATIONS.md`, `docs/KNOWLEDGE-HUB.md`, `docs/STRUCTURED-WORK.md`, the current git
diff and the relevant tests.

The review must answer:

1. Which statements confuse the public alpha.1 DMG with the newer development source?
2. Which status or capability claim lacks direct current evidence?
3. Is any safety boundary weakened or presented as a hard guarantee when it is only an instruction
   or cooperative adapter behavior?
4. What is the smallest safe next change that removes a real user-facing inconsistency?
5. Which exact checks must pass before that change can be called complete?

Claude must not reset the worktree, rewrite historical evidence, alter canary/checkpoint/grace state,
publish a release, modify user data, read credentials, or claim success from source tests alone.

## Decision record

| Date | Decision | Reason |
|---|---|---|
| 2026-07-27 | Publish alpha.1 as ad-hoc signed and not notarized | Permit bounded friend testing before Developer ID/notary access is ready |
| 2026-07-27 | Put Download Alpha on the public site | Exact Prerelease assets and checksum exist; warnings remain visible |
| 2026-07-28 | Do not promote broadly yet | Public DMG predates onboarding fixes and has not passed the rebuilt executable gates |
| 2026-07-28 | Keep model-generated experience and memory as candidates | Human approval remains the authority; no unattended self-evolution |
| 2026-07-29 | Keep planning failures in one immutable conversation | Users can edit and retry without losing the failed attempt or mistaking it for a new root task |
| 2026-07-29 | Do not overwrite alpha.1 or switch the public download yet | The new binary needs an alpha.2 identity; vendored-runtime redistribution review is still explicitly blocked |

Update this file after a gate changes. Include the exact artifact or commit identity, the check that
ran, its verdict, and the next remaining blocker. Do not replace evidence with “looks good.”
