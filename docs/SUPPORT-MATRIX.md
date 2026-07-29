# Community Alpha Support Matrix

This matrix describes the `v0.1.0-alpha.2` candidate. “Supported” means it is part of the Community
Alpha contract after the exact candidate passes its stated executable gate, not that Stable
durability or an SLA is available.

| Surface | Alpha status | Boundary |
|---|---|---|
| macOS 14+ / Apple Silicon App | Supported after signed Alpha asset passes its executable gate | Primary first-user path; compatible runtimes are bundled |
| macOS Intel | Not included | Separate Intel or universal distribution is not promised in this Alpha |
| Python 3.12 CLI | Supported | Developer/existing-user channel; Python `>=3.12,<3.13` and external integrations retain their documented requirements |
| Linux / Python 3.12 | CI-tested core | No launchd or full desktop experience commitment |
| Local Workspace and Work UI | Supported | Loopback, single operator |
| Plan review, immutable revisions, rerun and fork | Supported | Confirmation required before dispatch |
| Agent Contract v2 editor and immutable versions | Source-complete; fresh RC required | Stable Agent IDs; 1–5 Agents; six-page editor; exact owned-envelope preview; field-level diff and restore-to-draft |
| Per-Agent tool and Memory controls in Aion-compatible mode | Source-complete; fresh RC required | `deny` and `always_ask` override global Auto; unknown Agent/tool fails closed; non-lead private Memory is refused because exact private delivery cannot be proven |
| Strict Agent Runtime | Adapter unavailable; execution refused | Coordinator, private-workspace and CAS-handoff primitives exist, but no current Aion adapter implements the strict protocol; no silent downgrade |
| Workspace planning conversation history and failed retry | Source-complete; fresh RC required | Immutable Plan-chain projection; a failure returns the prior objective for an edited child retry in the same conversation, retains the failed attempt and exact attachment manifest, and never confirms or executes as a retry side effect |
| Workspace planning materials | Source-complete; fresh RC required | Up to 5 allowlisted files, 5 MiB each / 15 MiB total; hash-bound, private and read-only; bounded text/PDF excerpts, no Office parsing or OCR |
| Built-in Work template catalog | Source-complete; fresh RC required | 31 bilingual starting points and 10 concrete recipes; professional evidence packs stop at licensed review |
| Repeatable Work | Source-complete; fresh RC required | Latest ended reviewed Work prepares an unconfirmed child; never one-click dispatch |
| Auditable Workspace Memory | Source-complete; fresh RC required | Local Obsidian-compatible Markdown; candidates require human approval; planning reads approved hash-bound snapshots only |
| AionCore team execution in the Mac App | Supported integration | Pinned App sidecar; stage completion is Agent-reported |
| Paperclip governance projection in the Mac App | Supported integration | Pinned App sidecar and private embedded PostgreSQL; Paperclip is not the evidence authority |
| JSONL ledger, CAS, History and evidence views | Supported | Append-only authority; SQLite views are rebuildable |
| Exact-run private-content erasure | Source-complete; fresh RC required | Terminal runs only; removes local plan content, exclusive Agent session, managed workspace and unshared inputs/results while retaining a content-free receipt and any externally projected or shared data |
| Inline approval and operator input | Supported | Auto is default; manual mode remains available |
| Pause, continue and stop | Supported for mapped Aion team runs | Cooperative and evidence-confirmed; not an OS process freeze |
| `opswitness wrap` for launchd/cron commands | Supported | Existing command semantics and exit status remain authoritative |
| Private HTTPS, device pairing and PWA | Beta | Not required for Alpha; mobile entry may remain hidden |
| Gmail metadata-only integration | Experimental, default off | Readonly metadata and explicit model consent only |
| Telegram digest | Experimental, default off | Secrets remain local and must be configured explicitly |
| Claude Code non-interactive approval gate | Narrowly supported | Only the documented non-interactive path |
| Codex connection in the Mac App | Candidate; fresh RC required | The alpha.2 App exposes only bundled Codex and its official sign-in. It contains no upstream Anthropic runtime payload and does not show a Claude connection entry |
| External Claude / local model integrations | Developer/existing-user channel only | Existing source and CLI adapters remain readable for compatibility, but are not packaged or advertised as alpha.2 App capabilities; a connection never implies every execution adapter is ready |
| DeepSeek and Grok API connections | Connection only | No Alpha execution adapter promise |
| OpenClaw runtime | Not included | Planned after Alpha |
| Work calling another Work | Not included | Team-of-teams remains future work |
| Autonomous self-learning memory | Not included | Agents may propose candidates but cannot approve or silently change later planning |
| Tax filing, customs filing, insurance advice or placement | Not included | Templates prepare traceable evidence for CPA/EA, licensed customs broker, or licensed producer sign-off only |
| SaaS, multiple users, mobile app | Not included | Local single-operator product only |
| Automatic update | Alpha, operator-confirmed | Signed Alpha channel only; blocked while a Work is active |

OpsWitness is Apache-2.0 and has no formal support SLA in Community Alpha.
