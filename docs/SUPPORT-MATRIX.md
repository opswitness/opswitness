# Community Alpha Support Matrix

This matrix describes `v0.1.0-alpha.1`. “Supported” means it is part of the Community Alpha contract,
not that Stable durability or an SLA is available.

| Surface | Alpha status | Boundary |
|---|---|---|
| macOS 14+ / Python 3.12 | Supported | Primary local host; Python `>=3.12,<3.13` |
| Linux / Python 3.12 | CI-tested core | No launchd or full desktop experience commitment |
| Local Workspace and Work UI | Supported | Loopback, single operator |
| Plan review, immutable revisions, rerun and fork | Supported | Confirmation required before dispatch |
| Workspace planning conversation history | Source-complete; fresh RC required | Immutable Plan-chain projection; restore and template save have no execution side effect |
| Workspace planning materials | Source-complete; fresh RC required | Up to 5 allowlisted files, 5 MiB each / 15 MiB total; hash-bound, private and read-only; bounded text/PDF excerpts, no Office parsing or OCR |
| Built-in Work template catalog | Source-complete; fresh RC required | 31 bilingual starting points and 10 concrete recipes; professional evidence packs stop at licensed review |
| Repeatable Work | Source-complete; fresh RC required | Latest ended reviewed Work prepares an unconfirmed child; never one-click dispatch |
| Auditable Workspace Memory | Source-complete; fresh RC required | Local Obsidian-compatible Markdown; candidates require human approval; planning reads approved hash-bound snapshots only |
| AionUi team execution | Supported integration | Requires compatible local AionUi; stage completion is Agent-reported |
| Paperclip governance projection | Supported integration | Paperclip is not the evidence authority |
| JSONL ledger, CAS, History and evidence views | Supported | Append-only authority; SQLite views are rebuildable |
| Exact-run private-content erasure | Source-complete; fresh RC required | Terminal runs only; removes local plan content, exclusive Agent session, managed workspace and unshared inputs/results while retaining a content-free receipt and any externally projected or shared data |
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
| Autonomous self-learning memory | Not included | Agents may propose candidates but cannot approve or silently change later planning |
| Tax filing, customs filing, insurance advice or placement | Not included | Templates prepare traceable evidence for CPA/EA, licensed customs broker, or licensed producer sign-off only |
| SaaS, multiple users, mobile app | Not included | Local single-operator product only |

OpsWitness is Apache-2.0 and has no formal support SLA in Community Alpha.
