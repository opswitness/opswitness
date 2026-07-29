# OSS Integration Blueprint

Research verified: 2026-07-29. Licenses were confirmed from repository/package metadata
(GitHub API license fields, LICENSE files, PyPI/npm metadata), not from secondary posts.

Direction: OpsWitness integrates existing permissive-license components instead of building
them. Custom code is reserved for the parts no library provides — the tamper-evidence chain,
cross-vendor policy normalization, and the review UX. This document records what to adopt,
what to avoid (with the license traps found), and what remains deliberately custom.

Nothing in this document is a shipped capability. Every adoption below still requires the
same executable gates as any other feature (rebuilt App, real run, evidence review).

## Capability → adoption map

### 1. Cross-vendor approval gate

| Decision | Component | License | Basis |
|---|---|---|---|
| Primary | **ACP `session/request_permission`** (agentclientprotocol) | Apache-2.0 | Protocol v1 stable; the agent must ask the client before tool calls: `allow_once / allow_always / reject_once / reject_always`, with tool kind, diffs, and file locations attached. The current Codex-only Alpha does not ship a cross-vendor ACP adapter; a future reviewed adapter may implement this client contract without changing OpsWitness approval semantics. Optionally serve ACP `fs/read_text_file` / `fs/write_text_file` so file I/O physically routes through OpsWitness. |
| Backstop (raw CLI outside ACP) | Vendor hooks exposed by a separately reviewed provider runtime | n/a (config) | Several providers expose a command-hook contract using JSON input and explicit allow/block output. Any future adapter must be vendor-pinned, separately consented to, and must not be bundled merely because its UI entry is hidden. |
| Do not adopt | HumanLayer SDK | Apache-2.0 | README declares the code deprecated; PyPI stale since 2025-06. Patterns may be read, dependency must not be taken. |

### 2. Action evidence capture

| Decision | Component | License | Basis |
|---|---|---|---|
| Adopt (sidecar or schema fork) | **Gryph** (safedep/gryph) | Apache-2.0 | Go single binary; hook-injection capture for claudecode, codex, cursor, gemini, opencode, windsurf and others into one SQLite `AuditEvent` schema (session/subagent lineage, diffs, secret redaction, sensitive-path flags, JSONL export). Young (151 stars, active releases through 2026-05) — vendor-pin exact versions. It has **no hash chain and no signatures**; tamper evidence is ours to add. |
| Optional secondary witness | Provider OpenTelemetry decision/result events | n/a | A separately connected provider may produce an independent second record of the same actions. This is not shipped in the Codex-only Alpha and requires its own adapter and redistribution review. |
| Optional corroboration | mitmproxy (MIT) for network evidence; watchdog (Apache-2.0) for filesystem events; ToolHive (Apache-2.0) as an MCP gateway capture point | MIT / Apache-2.0 | Evidence that does not depend on the supervised agent's self-reporting. Opt-in; not Alpha scope. |
| Avoid | fswatch (GPL-3.0), Objective-See monitors (GPL-3.0) | GPL | Copyleft; watchdog covers the need. |

### 3. Tamper-evident evidence chain

| Decision | Component | License | Basis |
|---|---|---|---|
| Build on stdlib (~200 lines) | `hashlib` SHA-256 hash chain in an append-only SQLite table with `BEFORE UPDATE/DELETE ... RAISE(ABORT)` trigger guards; periodic Merkle-root checkpoints | PSF / public domain | Every maintained third-party Merkle library fails: **pymerkle is GPL-3.0**; merkly pins pydantic <2 (conflicts with FastAPI); merkletools last released 2018. No adoptable transparency-log library exists in Python. |
| Adopt (signing) | `cryptography` (Ed25519) + `keyring` (macOS Keychain key storage) | Apache-2.0/BSD dual; MIT | Reference implementations; PyInstaller-proven. Do not use tauri-plugin-stronghold (deprecated, removed in Tauri v3). |
| Adopt (opt-in external timestamp) | `rfc3161-client` (Trail of Bits / sigstore) against freetsa.org + timestamp.digicert.com (SHA-256) | Apache-2.0 | Instant RFC 3161 tokens, verification included, self-contained macOS wheels (v1.0.7, 2026-07-07). Only hashes leave the machine, and only when the operator opts in. |
| Adopt (format) | **in-toto Attestation Statement + DSSE envelope** (via `securesystemslib`, MIT, or hand-rolled PAE), custom predicate type reusing OTel `gen_ai.*` attribute names | Apache-2.0 specs | No agent-specific evidence standard exists as of 2026-07 (CoSAI/OWASP/AGNTCY define requirements, not wire formats). in-toto+DSSE is what existing supply-chain verifiers already understand. Emit the JSON directly; the PyPI in-toto bindings are stale. |
| Adopt (frontend re-verification) | `@noble/hashes` + `@noble/curves` | MIT | Audited, active; lets the UI independently re-verify the chain and signatures. |
| Avoid | OpenTimestamps (LGPL-3.0 + hours-long Bitcoin confirmation), immudb (BUSL-1.1 current server + separate Go server to supervise), Trillian (service infrastructure), C2PA for the core log (asset-embedded manifests, 0.x churn) | — | License or shape mismatch. C2PA may return later for stamping provenance into produced artifact files. |

### 4. Permission-topology visualization

| Decision | Component | License | Basis |
|---|---|---|---|
| Adopt | **@xyflow/react 12.x** (renderer) + **@dagrejs/dagre 3.x** (layered layout) | MIT; MIT | ~73 KB gz combined; React 19 supported; offline/no-CDN; nodes are React components, so allowed/ask/denied edge states and approval-time blast-radius highlighting are ordinary React code. Dagre v3 (2026-03) gives deterministic 3-rank layout for agents → tools/MCP servers → paths/domains. Nothing required is behind React Flow Pro; the free tier renders a small attribution badge — accept or budget for removal. |
| Adopt (evidence diffs) | react-diff-viewer-continued 4.x | MIT | React 19 in peerDeps; active (2026-07 release). |
| Hand-roll | Audit-trail timeline | — | A styled list; consistent with the existing minimal-dependency frontend. |
| Avoid | elkjs (EPL-2.0 OR GPL, 423 KB gz), mermaid for the interactive map (static SVG, very heavy), @antv/g6 (11-package footprint), d3-force (non-deterministic placement is wrong for an auditable map), react-cytoscapejs (wrapper unmaintained since 2022) | — | License flag, size, or determinism. Escape hatch at >~2–3k nodes: sigma + graphology + dagre (the Apache-2.0 BloodHound CE recipe). |

The graph must be **rendered from enforced contract state only** — never a hand-editable
canvas. A drawn boundary that is not enforced is exactly the "instruction presented as
guarantee" failure this product exists to prevent. Edges must visually distinguish
OS-enforced boundaries from cooperative (instruction-level) ones.

### 5. Evidence-packet export

| Decision | Component | License | Basis |
|---|---|---|---|
| Adopt (primary) | **typst-py** | Apache-2.0 | Single self-contained abi3 arm64 wheel — no dylib hunting under PyInstaller; offline; Typst templates keep the auditor-readable report maintainable. Verify bundled default fonts compile with no system fonts before shipping. |
| Fallback | reportlab (open-source toolkit) | BSD | Pure Python, cannot fail to bundle. The paid "PLUS" product is a separate templating add-on, not a gating of the toolkit. |
| Optional | pyHanko for a PAdES-signed PDF cover report with embedded RFC 3161 timestamp | MIT | Auditor-facing tier only. |
| Avoid | WeasyPrint (runtime dlopen of Pango/HarfBuzz — chronic macOS arm64 packaging failures), fpdf2 (**LGPL-3.0**) | — | Packaging pain; copyleft. |

Packet shape: ZIP of {JSONL chain + DSSE envelopes + Merkle checkpoint + `.tsr` timestamp
tokens + detached Ed25519 signature + a standalone verify script} + optional signed PDF summary.

## License trap list (found during verification — do not adopt)

- pymerkle — GPL-3.0 (the most-cited Python Merkle library)
- fpdf2 — LGPL-3.0-only
- OpenTimestamps client + lib — LGPL-3.0
- elkjs — EPL-2.0 OR GPL-3.0-or-later
- fswatch — GPL-3.0
- immudb server (current) — BUSL-1.1
- claude-agent-sdk-typescript — Anthropic Commercial Terms, not OSS. The Codex-only Alpha removes
  both AionCore's exact upstream payload and Paperclip's exact nested/native SDK payloads during
  deterministic staging. It retains only the exact first-party fail-closed compatibility shim
  required by AionCore startup. Paperclip receives no shim, but its retained MIT adapters and a
  host-installed provider still require a separate dispatch boundary; payload removal is not
  described as global runtime enforcement.
- PyPI package named `minisign` — MPL-2.0, unaudited, distinct from `py-minisign` (MIT)

## What remains custom — deliberately

These are small, and together they are the product:

1. ACP `session/request_permission` interception wired to the existing approval UI.
2. The unified hook shim (one binary, three vendors' hook dialects) + approval-queue IPC.
3. Policy normalization: one OpsWitness contract → the exact policy dialect of each
   separately reviewed runtime adapter. No library does this.
4. The hash chain, checkpoint signing, and evidence-packet assembly/verify script.
5. The contract → topology-graph data model (the graph is a projection of enforced state).
6. The review UX and the honest boundary language around it.

## Sequencing (does not preempt CURRENT-PROGRESS P0)

The P0 chain in `CURRENT-PROGRESS.md` (rebuild, first-Work acceptance, recovery, clean
install, canary) is unchanged and comes first. After P0:

1. **Evidence chain** (stdlib + cryptography + keyring): smallest surface, largest
   differentiator; retrofits onto existing run evidence.
2. **ACP permission interception**: turns the existing approval UI into a cross-vendor gate.
3. **Hook shim backstop + Gryph sidecar**: coverage for agents run outside ACP.
4. **Topology view (React Flow/dagre) + typst evidence packet**: the legibility layer.

Each step lands only with its own leak-free tests and executable-gate evidence, per the
existing release discipline.

## Verification caveats carried from research

- @xyflow/react has no explicit Vite 8 compatibility statement (plain ESM, no known issues)
  — smoke-test in this repo's Vite 8 build before committing.
- typst-py bundled-font behavior must be proven offline before packaging.
- Codex hooks stability milestone (v0.124.0) is third-party-sourced; the official docs
  confirm the hook events and decision contract.
- Antigravity CLI is closed (no public repo); integrate against OSS Gemini CLI
  (Apache-2.0, still actively released for enterprise/API users) and treat Antigravity as
  out of scope until its plugin contract is inspectable.
- Gryph is young (151 stars); pin exact versions in `desktop/vendor-lock.json` like every
  other vendored component.
