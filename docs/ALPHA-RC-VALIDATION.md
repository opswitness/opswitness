# OpsWitness Alpha RC Validation

Snapshot refreshed: 2026-07-22 America/Los_Angeles

## Post-restart observation

Private Release validation run
[29968869522](https://github.com/opswitness/opswitness/actions/runs/29968869522) passed for
executable-source commit `38594931ee1607cd621c9356816fa5189ca2c0a7`. This is build validation only;
it is not a public-release approval and does not replace the exact-artifact history below.

The operator approved a host restart. After restart, macOS reports `26.5 (25F71)`. A real-host
doctor check passes every current check except projector, watchdog, and gate-recovery, whose
interval triggers remain pended without execution. The restart did not close the host scheduler
fault. No `alpha-rc-5` contract has started. A new canary remains prohibited until repeated
automatic interval probes pass and the real-host doctor is green.

The failed `alpha-rc-1` through `alpha-rc-4` contracts and `m2-canary` remain immutable. The
historical exact-source, asset hashes, rollback paths, and failure observations below are preserved
without reinterpretation.

This record covers the private build validations, rollback-safe production migrations, immutable
failed canary chain, including the exact-artifact `alpha-rc-4` contract for
`OpsWitness v0.1.0-alpha.1`. It is evidence for a release candidate, not approval for a public tag
or stable release. Documentation updates made before `alpha-rc-4` failed did not change executable
source, the installed artifact, the schedule, or any ledger/CAS object.

## Exact post-freeze private Release build

- GitHub Actions run: [29927606948](https://github.com/opswitness/opswitness/actions/runs/29927606948)
- Source commit: `3bd2b0d005d86495b8121477d3425ac0bd264ec9`
- Preflight, Ubuntu quality, macOS quality, DCO, full-history gitleaks, and build passed. Publish was
  intentionally skipped for the untagged private validation.
- The manifest reported schema 2, `clean_tree=true`, product `OpsWitness`, distribution
  `opswitness`, public version `0.1.0-alpha.1`, Python version `0.1.0a1`, the requested tag, and the
  exact source commit. Independent inspection verified the SPDX package identity as
  `opswitness 0.1.0a1`.

| Asset | SHA-256 |
|---|---|
| `opswitness-0.1.0a1-py3-none-any.whl` | `4cbb00087f6a310c875cf6bb5acfa2cde3120994e5b85705d3b7e152b4169b8e` |
| `opswitness-0.1.0a1.tar.gz` | `6839e015bc5babe25eb8844f76ca5b2477f2c242c54c8330635b9c083cbcbb99` |
| `sbom.spdx.json` | `7751a8ac550ed6da589cf1ef41fdfc12b053498178500b568aef30adf09a8639` |

The exact wheel was installed into an empty isolated uv-tool root. Both CLI aliases returned
`0.1.0a1`; a synthetic wrapped `/usr/bin/true` run succeeded and wrote a succeeded lifecycle; the
packaged console and `/api/v1/bootstrap` returned HTTP 200. Browser acceptance loaded Workspace
without warnings or errors and exposed the priority one-person-company templates, including
commercial analysis, CPA/EA workpaper, customs evidence, and P&C renewal workflows.

## Earlier private Release build (historical)

- GitHub Actions run: [29794782849](https://github.com/opswitness/opswitness/actions/runs/29794782849)
- Source commit: `92d10d557f13f0358fa1a424049054fa53dcb467`
- Preflight, Ubuntu quality, macOS quality, DCO, full-history gitleaks, and build jobs passed. The
  publication job was skipped because this was an untagged private validation run.
- The downloaded artifact contained the wheel, sdist, `SHA256SUMS`, build manifest, and SPDX 2.3
  SBOM. `shasum -a 256 -c SHA256SUMS` passed for every hashed asset.

| Asset | SHA-256 |
|---|---|
| `opswitness-0.1.0a1-py3-none-any.whl` | `bfea2d4e67f6786251529058ca16fb2812dce8e1610067180e89c60ce6aee953` |
| `opswitness-0.1.0a1.tar.gz` | `bbaafcba654cccaa5630ec7e2839baa1dcf0fa5ada3d2d76014ce337e6ad8d39` |
| `sbom.spdx.json` | `fc6396b0d634e8cc1f3088ff3c151b78affc703fb48f02df3a1dd65e5e7d08a4` |

The manifest reported `clean_tree=true`, the exact source commit, product `OpsWitness`,
distribution `opswitness`, public version `0.1.0-alpha.1`, and Python version `0.1.0a1`.

The downloaded wheel was installed into a blank temporary uv-tool root. Both
`opswitness version` and `qd version` returned `0.1.0a1`; a synthetic wrap succeeded; all thirteen
MCP tools were present; the packaged outage/replay/lost-ack showcase ended with zero pending
projection events; and the packaged console served its index, CSS, JavaScript, manifest, and
service worker.

## Exact-artifact production migration

- Nine related OpsWitness/legacy jobs were quiesced after confirming that no wrapped or gated
  Work execution was active.
- The encrypted state backup is
  `~/.local/state/quarterdeck/backups/opswitness-20260722T142908Z.tar.age` (64,763,512 bytes,
  mode `0600`).
- The exact rollback bundle is
  `~/.local/state/quarterdeck/release-rollback/opswitness-actions-3bd2b0d-20260722T142908Z/`.
  It contains the prior uv tool, both command links, all nine related plist files, a migration
  manifest, and SHA-256 evidence for every preexisting ledger/CAS file.
- The exact Actions wheel replaced the prior locally built `0.1.0a1` tool. Installed package
  provenance points to that wheel, and both `opswitness` and `qd` return `0.1.0a1`.
- No canonical fresh-install state or config root was created; the legacy roots remain the single
  adopted authority. Existing CAS hashes are identical after migration.
- The five official services were restored and explicitly kickstarted after launchd accepted the
  bootstrap without immediately scheduling each process. Paperclip, console, projector,
  watchdog, and gate recovery are single-instance; projection backlog is zero; the production
  console and bootstrap API return HTTP 200. The first doctor snapshot returned `healthy=true`,
  but a later interval probe proved the periodic services were pended; that green verdict is not
  accepted as runtime-health evidence.

## Earlier rollback-safe production migration (historical)

- Before quiescence, an encrypted full-state backup was created at
  `~/.local/state/quarterdeck/backups/quarterdeck-20260721T021437Z.tar.age` (52,646,648 bytes,
  mode `0600`).
- The old `quarterdeck 0.0.1` uv tool, `qd` symlink, and five installed plists were archived under
  `~/.local/state/quarterdeck/release-rollback/opswitness-0.1.0a1-20260721T021437Z/`.
- A real process scan found no running `wrap` or `gated-claude` process. Paperclip, projector,
  watchdog, gate-recovery, and console were booted out before the tool environment changed.
- The verified wheel replaced the old uv tool. The primary `opswitness` command, compatibility
  `qd` command, and legacy plist compatibility path all returned `0.1.0a1`.
- The installed legacy-label plists had hard-coded the former uv-tool internal path. The first
  production doctor correctly rejected all five. Only `ProgramArguments[0]` was then changed to
  the verified OpsWitness executable; labels, service names, schedules, environment, logs, and
  secret boundaries were unchanged. The original plist bytes remain in the rollback archive.
- The legacy `~/.config/quarterdeck` and `~/.local/state/quarterdeck` roots were adopted in place;
  neither canonical OpsWitness root was created. SHA-256 values for all ten ledger files and ten
  CAS blobs were identical before and after migration.
- Final real-user-domain doctor returned `healthy=true`: all dependency, command, credential,
  backup, log, template, installed-service, runtime, port, and single-instance checks passed.
  Paperclip and console were running; projector, watchdog, and gate-recovery had real exit-zero
  runs.
- The production browser loaded `OpsWitness v0.1.0-alpha.1`, displayed existing Work history and
  CAS-bound Results, and reported no browser warning or error logs.

## Independent Alpha canary

`com.opswitness.alpha-canary` is a new launchd job with a 900-second interval, `RunAtLoad`, private
umask, exact legacy-root environment, and one command only:

```text
opswitness wrap --job com.opswitness.alpha-canary -- /usr/bin/true
```

The user-owned schedule enrolls that exact label. It does not enroll a namespace and does not use
the former `m2-canary` or either historical release-canary service.

The append-only `alpha-rc-1` contract started at `2026-07-21T02:35:06.365539+00:00` with event
`01KY18DS7ZBS7KHZJZ3SCQHJYF`. It later failed its frozen cadence contract. The status recomputed at
`2026-07-22T00:39:07.309643+00:00` reported 61 starts, 61 successes, zero task failures, zero
running tasks, zero projection backlog, and a 7,504.433-second maximum gap against the frozen
1,200-second allowance. `cadence_gap` is a hard blocker. No checkpoint or reset was written.

macOS power evidence explains the gap but does not waive it. `pmset -g log` records entry into
sleep at 2026-07-21 01:47:57 PDT due to `Software Sleep pid=84736`, followed by thermal-emergency
sleep/dark-wake cycles and a full user wake at 09:54:20 PDT. The launchd canary ran only during
sparse wake windows. This is a host-availability failure and remains permanent release evidence.

`alpha-rc-2` started independently at `2026-07-22T00:36:01.202548+00:00` with event
`01KY3M0EHNH17A17KD7Y0MT78C` and the same exact 900-second schedule plus 300-second grace. A
temporary `com.opswitness.alpha-canary-awake` launchd service ran `/usr/bin/caffeinate -is`.
The authoritative status recomputed at `2026-07-22T13:29:01.947352+00:00` reports 36 starts, 36
successes, zero task failures, zero running tasks, zero projection backlog, and a
14,820.799-second maximum gap against the frozen 1,200-second allowance. `cadence_gap` is a hard
blocker. The 24-hour minimum was also still pending with 40,019.255 seconds remaining. The latest
observed start was `2026-07-22T09:22:01.148417+00:00`.

The cause of this later gap has not yet been attributed. Host availability, launchd behavior, and
the wake assertion may be inspected to explain it, but no explanation can waive the frozen
contract. No checkpoint, widened grace, reset, relabel, or evidence rewrite is permitted.
`alpha-rc-2` is permanent failed evidence and cannot validate either its former installed artifact
or the newer post-freeze source.

`alpha-rc-3` started at `2026-07-22T06:21:34.204863+00:00` with event
`01KY47S5M1K72XAQ2YZD48WEHY`. A later executable-source change required a distinct exact-artifact
contract. The resulting service interruption left `alpha-rc-3` with a hard cadence gap; subsequent
runs for the same enrolled job cannot remove the maximum observed gap. It remains permanent failed
evidence and is not reset, relabeled, or cited as success.

`alpha-rc-4` is bound to the exact Actions artifact from commit `3bd2b0d`. It started at
`2026-07-22T14:34:21.145132+00:00` with event `01KY53ZFJZCQWHS6FC60XRB4Y5`, a 900-second interval,
300-second grace, and 86,400-second minimum. Its first wrapped run succeeded and projection backlog
remained zero, but launchd received the next interval trigger and left it as
`pended nondemand spawn = interval`. At `2026-07-22T15:02:33.528698+00:00`, the authoritative
verdict reported one start, one success, zero task failures, and a 1,647.999-second maximum gap
against the frozen 1,200-second allowance. The contract is permanently failed; no checkpoint or
reset was written.

A separate 10-second LaunchAgent running only `/usr/bin/true` reproduced `runs=0` with the same
pended interval state. macOS reports 26.5.2 staged with a restart required, matching launchd's
on-demand-only behavior. This explains the host condition but does not waive the failed contract.
The update must complete and the Mac must reboot before automatic intervals are probed again. Only
after repeated automatic triggers pass may a rebuilt exact artifact start a new append-only
contract.

## Gates still open

The repository remains private, PR #1 remains draft, no public tag or GitHub Release exists, and
`PUBLIC_RELEASE_APPROVED` remains unset. Public Alpha still requires:

1. completion of the staged macOS update and reboot, repeated automatic interval-probe success,
   a rebuilt exact artifact, and a fresh passing 24-hour append-only contract; exact-source build,
   install, migration, and browser smoke for the prior artifact are complete, while
   `alpha-rc-1` through `alpha-rc-4` remain failed;
2. professional confusing-similarity review;
3. private merge plus green `main`, public-repository security controls, public-main release
   validation, exact annotated tag approval, prerelease asset/attestation inspection, and a final
   blank-install smoke test.

The Alpha does not advertise mobile access. Private HTTPS, device pairing, and PWA support remain
Beta capabilities, and physical iPhone Safari/Chrome acceptance is deferred to that Beta promotion
gate rather than treated as an Alpha publication blocker.

Stable `v0.1.0` remains separately blocked on the seven-day feed-monitor/sox-monitor soak and
isolated restore drill.
