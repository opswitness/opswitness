# Known Limitations

These limitations are release promises, not a hidden backlog.

1. **Durability remains experimental.** A 24-48 hour release canary is required for the Alpha
   candidate. Stable `v0.1.0` additionally requires the full seven-day soak, feed-monitor and
   sox-monitor adoption, and a successful isolated recovery drill.
2. **Execution is not outcome proof.** A process exit, Agent response, or Agent-reported completed
   stage does not prove that a report or other business result is correct. CAS artifacts, evals, and
   human sign-off supply outcome evidence.
3. **Aion stage telemetry is bounded and self-reported.** The UI deliberately omits chain-of-thought,
   raw tool arguments, message bodies, and fabricated completion percentages.
4. **Pause is cooperative.** Pause and stop become final only when the mapped runtime supplies
   confirming evidence. A successful RPC acknowledgement alone is not termination proof.
5. **Automatic approval is the default.** It still creates single-use governance records, but it
   removes the per-tool human interruption. Select manual mode before confirmation for sensitive
   work, or tighten a supported active run in Work.
6. **The customer-reply example uses one single-use approval per runtime write.** Its local reply
   draft and review evidence normally require two approvals. The workflow has no delivery step, but
   AionCore confirmations do not expose a structured filesystem capability, so the operator must
   reject any request other than the two expected local saves. A safe one-click grant requires an
   OpsWitness-owned write tool bound to the immutable `plan_sha256` and the exact
   `artifacts/first-work.json` and `artifacts/verification.json` relative paths; OpsWitness does not
   infer such authority from free-form command text.
7. **The Mac App is large and its runtimes are fixed.** The first App bundles the full pinned
   Paperclip/PostgreSQL, AionCore, Node, Python, and Codex runtime sets. It does not substitute newer
   programs from `PATH`, and changing a bundled runtime requires another signed release. The CLI
   distribution retains its separately documented external integration requirements.
8. **Private-network and mobile use are Beta.** Browser-trusted HTTPS and paired-device credentials
   are required. Physical Safari/Chrome acceptance must pass before the mobile entry is promoted.
9. **Provider readiness is explicit.** First use requires an explicit Codex or Anthropic choice and
   never silently changes providers. Anthropic uses a user-supplied API Key stored in macOS
   Keychain and billed to the user's API account; Claude Pro/Max subscription login is not a
   supported product credential. DeepSeek and Grok credentials may be connected, but they are not
   selectable execution runtimes in this Alpha. OpenClaw is not integrated.
10. **No team-of-teams or autonomous learning.** A Work contains its own planned Agent team and
   cannot yet invoke another Work as a worker. Workspace Memory is candidate-first and human
   approved; Agents cannot silently learn from runtime material or modify active memory.
11. **Compatibility is intentionally bounded.** `qd`, `QD_*`, old data roots, old launchd labels, and
    known Keychain services are supported for existing installs. The old Python import package is not.
12. **GitHub Release only.** PyPI is not configured for Alpha, and release assets are valid only when
    their checksums, build manifest, SPDX SBOM, and GitHub attestation agree.
13. **No SLA or production guarantee.** Community Alpha is suitable for synthetic and non-critical
    pilots. Keep independent backups and recovery paths for important work.
14. **Professional templates are preparation tools, not licensed services.** The CPA/EA, customs,
    and commercial-insurance templates produce source-linked workpapers, discrepancy lists, and
    readiness packs. They do not post books, choose tax positions, file returns or entries, determine
    customs treatment, recommend coverage, negotiate quotes, bind insurance, or replace the licensed
    professional's review and signature.
15. **Planning attachments are bounded and are not a document-ingestion platform.** A plan accepts
    at most five files, 5 MiB each and 15 MiB total. Text, Markdown, CSV, JSON, and PDF receive bounded
    excerpts; Word, Excel, and image content is not parsed during planning and no OCR is provided.
    Attached content is sent to the selected planning model, so credentials and unauthorized or
    unnecessarily sensitive documents must not be attached.
16. **Run erasure is local and reference-aware, not a forensic or external recall guarantee.** An
    ended Run can erase its local plan body, operator-input state, exclusive Agent session,
    application-managed workspace, attachment bytes, and CAS blobs that no other retained Run uses.
    OpsWitness keeps a content-free hash and erasure receipt, retains shared blobs and explicit
    external workspaces, and cannot retract records already projected to Paperclip or another
    external system. Runs sharing one Agent conversation fail closed until the linked retained Runs
    are handled together. Filesystem snapshots, backups, and provider-side retention remain outside
    this action.
17. **The first Mac App is Apple Silicon-only.** macOS 14 or newer is required. Intel Macs and a
    universal binary are not supported by this Alpha.
18. **App completion does not make a public release ready.** The exact DMG must pass Developer ID
    signing, Apple notarization and stapling, Gatekeeper verification, a clean-machine first Work,
    redistribution review, and a new 24–48 hour executable canary. Old CLI/RC soak evidence cannot
    be reused for the App candidate.
19. **Project Library metadata uses serialized last-write-wins updates.** File identity and SHA-256
    are rechecked, and metadata writes are serialized, but two already-open windows editing the same
    tags or version relationship do not yet compare a metadata revision. The later confirmed save can
    replace the earlier metadata edit; refresh before editing in another window. Source bytes,
    evidence digests, and immutable Work history are never rewritten by this metadata update.
20. **Recovery Agent is not an autonomous App updater.** It can diagnose a verifiably stalled Work
    from bounded, content-free runtime telemetry and can automatically refresh status or continue the
    same ledger-bound Work and team. It cannot read raw logs, source code, prompts, credentials, or
    arbitrary files during that diagnosis. A suspected product defect can create a separately
    confirmed, still-unexecuted Repair Work that is forced into manual approval mode. The signed App
    is never modified in place; product-code fixes still require review, a rebuilt signed release, and
    the normal update confirmation.
21. **Agent Contract enforcement depends on the selected runtime mode.** The Aion-compatible path
    enforces stable identity mapping, selected Memory, required artifact checks, and per-Agent
    `deny` / `always_ask` / inherited approval decisions. Its shared Workspace, handoff text, loop
    count, retry count, file/data scope, and timeout are still execution instructions rather than OS
    isolation or hard cutoffs. Strict mode never falls back to that path: until a runtime adapter
    implements verified sequential dispatch, private Agent Workspaces, brokered side effects,
    revocation, and termination confirmation, strict Contracts cannot run.
