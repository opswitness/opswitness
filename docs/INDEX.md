# OpsWitness Documentation Center

This index is the canonical entry point for OpsWitness documentation. The macOS App also includes
an offline **Docs Center** with six practical operator topics; it does not fetch help content from
the network.

## Start here

- [Current progress](CURRENT-PROGRESS.md) — what is downloadable now, what exists only in source,
  refreshed evidence, release blockers, and the next priority.
- [Quickstart](QUICKSTART.md) — install or start OpsWitness and create the first Work.
- [Naming standard](NAMING.md) — canonical product, CLI, compatibility, Work, file, and evidence
  terminology.
- [Product experience spec](PRODUCT-EXPERIENCE-SPEC.md) — the simplicity contract: five
  product nouns, trust levels, the approval card, silent evidence, and delivery slices.
- [Known limitations](KNOWN-LIMITATIONS.md) — current Alpha boundaries and unsupported claims.
- [Support matrix](SUPPORT-MATRIX.md) — supported systems and runtime combinations.
- [Security policy](../SECURITY.md) — report vulnerabilities and understand the security boundary.

## Use OpsWitness

- **First use** — choose a fresh environment or explicitly import a copy, connect Codex, review the
  built-in demonstration, approve its two bounded local writes, and review both evidence files.
- **Run a Work** — describe an outcome and constraints, review the proposed team and plan, confirm
  the exact plan, follow observable progress, and review results.
- **Approvals and safety** — verify the Work, agent, tool, action, and target on every approval;
  reject anything unexpected or broader than the reviewed plan.
- [**Knowledge Hub**](KNOWLEDGE-HUB.md) — import files or folder snapshots, deduplicate exact
  bodies, approve citation-bound cards, search retained knowledge, and bind exact versions into a
  new reviewable Work. The original Project Library remains available as the evidence projection
  for retained Work inputs and registered outputs.
- **Evidence and sign-off** — distinguish execution completion from human review and from any real
  business-result claim.
- **Troubleshooting and recovery** — retry without double-dispatching, preserve prior runs, and let
  the desktop supervisor reconcile recorded state after a restart.

These six topics are authored in `console-ui/src/docs-center.tsx` so the installed App can display
the same safety guidance offline.

## Architecture and operation

- [Architecture](ARCHITECTURE.md)
- [OSS integration blueprint](OSS-INTEGRATION-BLUEPRINT.md) — which permissive-license
  components to adopt for approvals, evidence chain, topology view, and export; license
  traps; what stays custom.
- [Local console and AionCore adapter](aionui.md)
- [Vendored runtimes](VENDORED-RUNTIMES.md)
- [Private console access](private-console.md)
- [Paperclip installation history](INSTALL-PAPERCLIP.md)
- [Readiness](READINESS.md)
- [Completion audit](COMPLETION-AUDIT.md)

## Release and validation

- [Alpha release-candidate validation](ALPHA-RC-VALIDATION.md)
- [Alpha canary evidence](ALPHA-CANARY-EVIDENCE.md)
- [Website release](WEBSITE-RELEASE.md)
- [Commercialization](COMMERCIALIZATION.md)
- [Brand clearance](BRAND-CLEARANCE.md)

Files named `M*-VALIDATION.md`, schemas, ADRs, and historical installation records are engineering
evidence. They remain readable under their original identifiers and wording; the naming standard
does not rewrite history.
