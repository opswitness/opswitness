# OpsWitness

**Turn an AI task into reviewable, repeatable work.** Describe a goal, approve a plan,
track execution, and inspect the result with its evidence. Local-first, single operator.

[30-second demo](https://github.com/user-attachments/assets/c25a7297-7f43-49b3-a64b-29fb56cd83fa) · [Download alpha.1](https://github.com/opswitness/opswitness/releases/tag/v0.1.0-alpha.1) · [Website](https://opswitness.com) · [Synthetic verification example](examples/showcase/README.md)

https://github.com/user-attachments/assets/c25a7297-7f43-49b3-a64b-29fb56cd83fa

*Goal → approval → execution → evidence. Chinese narration; public development UI screenshots
and synthetic DEMO-001 data. This is a screenshot walkthrough, not a continuous recording or
a fresh execution test. The screens do not establish which features ship in alpha.1.*

## What can I try today?

| Surface | Available now | What it means |
|---|---|---|
| **Downloadable test build** | [v0.1.0-alpha.1 prerelease](https://github.com/opswitness/opswitness/releases/tag/v0.1.0-alpha.1) | A **closed testing build**, not a stable release. macOS 14+ on Apple Silicon. Its release notes define the included capabilities. |
| **Main-branch source** | This public repository | Source for inspection and development. `main` is not the build identity of the downloadable DMG; use the release tag and assets when reproducing alpha.1. |
| **Development beyond alpha.1** | Separate source changes, previews and pull requests | The alpha.1 release notes explicitly exclude later Agent Contract v2, Knowledge Hub and failed-planning recovery work. A source feature or screenshot is not a shipped-feature promise. |

The alpha.1 build is ad-hoc signed and **not notarized by Apple**. macOS may block its first
launch. It is for informed Alpha testers using synthetic, non-critical work; there is no SLA
or production-readiness claim. Read the installation warning on the release page before trying it.

## How to verify

1. **Downloaded build:** get the DMG and `SHA256SUMS` from the same
   [alpha.1 release](https://github.com/opswitness/opswitness/releases/tag/v0.1.0-alpha.1).
   Compute the DMG's SHA-256 and compare it with that file before opening it. Keep the release
   tag and asset checksum with any feedback; a current `main` checkout is a different reference.
2. **Source behavior:** inspect and run the credential-free
   [synthetic showcase](examples/showcase/README.md) in an isolated development environment.
   Its documented checks cover approval decisions, outage/replay, artifact evidence and the
   distinction between execution status and outcome evidence. This is core-contract validation,
   not desktop, real-provider or production acceptance.
3. **Business result:** a completed run does not prove its output is correct. Inspect the
   artifacts, evaluations and human sign-off for that exact run.

## Product scope

Workspace captures goals and reviewable plans; Work keeps versions, run history and results;
Settings manages local connections. Execution adapters remain replaceable, and evidence stays
local. OpsWitness complements existing model tools rather than promising autonomous business
outcomes.

Development and release-candidate documents, including [Draft PR #1](https://github.com/opswitness/opswitness/pull/1),
may describe work beyond the downloadable build or historical release gates. The **specific
release page is authoritative for its assets and limitations**. Neither public source nor a
published testing build establishes stable durability, hosted SaaS or multi-user support.

Professional workflows prepare reviewable evidence for a qualified human decision-maker.
OpsWitness does not submit, pay, file, bind or send on the operator's behalf by default.

## Compatibility

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
