# OpsWitness Alpha RC Validation

Snapshot: 2026-07-21 17:38 PDT

This record covers the private build validation, rollback-safe production migration, the failed
independent `alpha-rc-1` canary, and its fail-closed replacement `alpha-rc-2` for
`OpsWitness v0.1.0-alpha.1`. It is evidence for a release candidate, not approval for a public tag
or stable release.

## Private Release build

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

## Rollback-safe production migration

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
temporary `com.opswitness.alpha-canary-awake` launchd service runs `/usr/bin/caffeinate -is`;
`pmset -g assertions` confirms both `PreventSystemSleep` and `PreventUserIdleSystemSleep`. Its
first wrapped run succeeded, and the normal projector reduced the temporary two-event backlog to
zero. The only current blocker is the unelapsed 24-hour minimum. Earliest duration-only eligibility
is `2026-07-23T00:36:01.202548+00:00` (2026-07-22 17:36 PDT).

The wake assertion does not override lid closure, manual sleep, power loss, or macOS thermal
protection. Any resulting gap still fails `alpha-rc-2`; no widened grace or evidence rewrite is
permitted.

## Gates still open

The repository remains private, PR #1 remains draft, no public tag or GitHub Release exists, and
`PUBLIC_RELEASE_APPROVED` remains unset. Public Alpha still requires:

1. a passing 24-hour `alpha-rc-2` status and append-only checkpoint; `alpha-rc-1` remains failed;
2. professional confusing-similarity review;
3. physical iPhone Safari and Chrome pairing/PWA/write/revoke acceptance, or removal of mobile
   claims from Alpha;
4. private merge plus green `main`, public-repository security controls, public-main release
   validation, exact annotated tag approval, prerelease asset/attestation inspection, and a final
   blank-install smoke test.

Stable `v0.1.0` remains separately blocked on the seven-day feed-monitor/sox-monitor soak and
isolated restore drill.
