# Community Alpha Quickstart

OpsWitness is a local-first, single-operator application for macOS. The public website and source
are available for review, but the install package has not been posted yet.

## Current availability

- Review the product at [opswitness.com](https://opswitness.com).
- Inspect the public source and open issues in the
  [GitHub repository](https://github.com/opswitness/opswitness).
- Check [GitHub Releases](https://github.com/opswitness/opswitness/releases) for the verified
  Community Alpha package.

Do not install a wheel copied from an issue, branch artifact, or third-party mirror. The official
release will publish the wheel, source archive, checksums, build manifest, SPDX SBOM, and
attestation together.

## Planned requirements

- macOS 14 or newer;
- Python 3.12 exactly;
- `uv`;
- a loopback browser for the default console.

AionUi and Paperclip are required only for the full team-execution and governance path. Linux runs
the tested core in CI but is not a supported launchd or desktop-console target in Alpha.

## After the package is posted

The release notes will contain the exact installation command. Both `opswitness version` and the
compatibility command `qd version` must report the same version before you begin.

Start with synthetic or non-critical work. Read the
[support matrix](SUPPORT-MATRIX.md) and [known limitations](KNOWN-LIMITATIONS.md) before adopting
important workflows. Stable durability requires additional soak and restore evidence beyond the
Community Alpha gate.
