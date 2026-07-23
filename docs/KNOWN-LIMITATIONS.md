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
6. **Full operation has local dependencies.** The core wrapper works without Paperclip, but the
   full Workforce flow depends on compatible local AionUi and Paperclip services. There is no silent
   runtime fallback.
7. **Private-network and mobile use are Beta.** Browser-trusted HTTPS and paired-device credentials
   are required. Physical Safari/Chrome acceptance must pass before the mobile entry is promoted.
8. **Provider readiness is explicit.** DeepSeek and Grok credentials may be connected, but they are
   not selectable execution runtimes in this Alpha. OpenClaw is not integrated.
9. **No team-of-teams or autonomous learning.** A Work contains its own planned Agent team and
   cannot yet invoke another Work as a worker. Workspace Memory is candidate-first and human
   approved; Agents cannot silently learn from runtime material or modify active memory.
10. **Compatibility is intentionally bounded.** `qd`, `QD_*`, old data roots, old launchd labels, and
    known Keychain services are supported for existing installs. The old Python import package is not.
11. **GitHub Release only.** PyPI is not configured for Alpha, and release assets are valid only when
    their checksums, build manifest, SPDX SBOM, and GitHub attestation agree.
12. **No SLA or production guarantee.** Community Alpha is suitable for synthetic and non-critical
    pilots. Keep independent backups and recovery paths for important work.
13. **Professional templates are preparation tools, not licensed services.** The CPA/EA, customs,
    and commercial-insurance templates produce source-linked workpapers, discrepancy lists, and
    readiness packs. They do not post books, choose tax positions, file returns or entries, determine
    customs treatment, recommend coverage, negotiate quotes, bind insurance, or replace the licensed
    professional's review and signature.
14. **Planning attachments are bounded and are not a document-ingestion platform.** A plan accepts
    at most five files, 5 MiB each and 15 MiB total. Text, Markdown, CSV, JSON, and PDF receive bounded
    excerpts; Word, Excel, and image content is not parsed during planning and no OCR is provided.
    Attached content is sent to the selected planning model, so credentials and unauthorized or
    unnecessarily sensitive documents must not be attached.
15. **Run erasure is local and reference-aware, not a forensic or external recall guarantee.** An
    ended Run can erase its local plan body, operator-input state, exclusive Agent session,
    application-managed workspace, attachment bytes, and CAS blobs that no other retained Run uses.
    OpsWitness keeps a content-free hash and erasure receipt, retains shared blobs and explicit
    external workspaces, and cannot retract records already projected to Paperclip or another
    external system. Runs sharing one Agent conversation fail closed until the linked retained Runs
    are handled together. Filesystem snapshots, backups, and provider-side retention remain outside
    this action.
