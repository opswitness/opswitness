# Community Alpha Support Matrix

This matrix describes `v0.1.0-alpha.1`. “Supported” means it is part of the Community Alpha contract,
not that Stable durability or an SLA is available.

| Surface | Alpha status | Boundary |
|---|---|---|
| macOS 14+ / Python 3.12 | Supported | Primary local host; Python `>=3.12,<3.13` |
| Linux / Python 3.12 | CI-tested core | No launchd or full desktop experience commitment |
| Local Workspace and Work UI | Supported | Loopback, single operator |
| Plan review, immutable revisions, rerun and fork | Supported | Confirmation required before dispatch |
| AionUi team execution | Supported integration | Requires compatible local AionUi; stage completion is Agent-reported |
| Paperclip governance projection | Supported integration | Paperclip is not the evidence authority |
| JSONL ledger, CAS, History and evidence views | Supported | Append-only authority; SQLite views are rebuildable |
| Inline approval and operator input | Supported | Auto is default; manual mode remains available |
| Pause, continue and stop | Supported for mapped Aion team runs | Cooperative and evidence-confirmed; not an OS process freeze |
| `opswitness wrap` for launchd/cron commands | Supported | Existing command semantics and exit status remain authoritative |
| Private HTTPS, device pairing and PWA | Beta | Not required for Alpha; mobile entry may remain hidden |
| Gmail metadata-only integration | Experimental, default off | Readonly metadata and explicit model consent only |
| Telegram digest | Experimental, default off | Secrets remain local and must be configured explicitly |
| Claude Code non-interactive approval gate | Narrowly supported | Only the documented non-interactive path |
| Codex / Claude / local model connections | Connection dependent | A connection does not imply every execution adapter is ready |
| DeepSeek and Grok API connections | Connection only | No Alpha execution adapter promise |
| OpenClaw runtime | Not included | Planned after Alpha |
| Work calling another Work | Not included | Team-of-teams remains future work |
| Auditable long-term memory | Not included | Candidate learning must not be implied |
| SaaS, multiple users, mobile app | Not included | Local single-operator product only |

OpsWitness is Apache-2.0 and has no formal support SLA in Community Alpha.
