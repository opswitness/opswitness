# Product Experience Spec — the simplicity contract

Drafted: 2026-07-29. Companion to `OSS-INTEGRATION-BLUEPRINT.md` (which fixes the
components) and `CURRENT-PROGRESS.md` (which fixes the release gates). This document fixes
the **user experience** those components must be folded into.

The target user is the operator of a one-person company. The reference persona is a solo
professional (for example a lawyer or accountant) who does not use a terminal, git, or
configuration files. A developer can drop into advanced surfaces; a non-developer must
never need them. Every promised workflow must be completable start-to-finish with mouse
and plain language only.

## North star

> Describe the work. Review who will do what. Approve a few clearly-explained actions.
> Keep the sealed record.

If a screen, setting, or word does not serve one of those four sentences, it does not
belong in the primary experience.

## The five product nouns

The primary UI exposes exactly five nouns. Everything else lives behind Settings or
Advanced.

| Noun | What the user does there | Existing surface it maps to |
|---|---|---|
| **Work** | Describe an outcome, review the proposed team and plan, watch observable progress, review results | `homeActionView('tasks'|'team')` → work view; task presets; execution progress |
| **Approvals** | One queue of pending actions, each explained in one sentence, regardless of which AI runtime raised it | approvals view; ACP `session/request_permission` interception (blueprint §1) |
| **Playbooks** | Save a signed-off Work as a repeatable process; run it again; improve it as a new version; copy it to another project | process versioning promise on the public site; work templates |
| **Evidence** | Per-Work sealed record: timeline, diffs, artifacts; one-click export of an evidence packet; one-click verify | project library evidence projection; blueprint §3 + §5 |
| **Knowledge** | Drag in files or a folder snapshot, review cards, bind exact versions into new Work | Knowledge Hub (shipped in source) |

## How the six stack functions and four gaps fold in

### 1. One AI connection, chosen once

Onboarding asks for one decision: sign in to the supported AI account. Provider entry
points stay gated by `product-boundaries.ts` flags exactly as today; when a second runtime
passes its redistribution and executable gates, it appears as a Settings toggle
("backup runtime"), not as a new workflow. The user never learns which protocol connects
them.

**Gap closed (cross-vendor):** all runtimes raise approvals into the same queue and write
into the same evidence chain via the ACP permission flow; the unification is invisible.
The user sees one approval language, one evidence format, one place.

### 2. Trust levels instead of a contract editor

The primary UI never shows a policy editor. It shows one selector with three levels:

1. **Review everything** — every action pauses for approval. Default for a new
   Workspace and for the first run of any Playbook.
2. **Standard** — reads proceed; writes, sends, and anything leaving the workspace pause.
3. **Trusted Playbook** — steps this exact Playbook version has previously performed
   with approval proceed; anything new or high-risk pauses.

**Red lines are not a level.** Sending anything outside the machine, deleting, publishing,
payments, and credential access always pause for approval at every level. This list is
product-fixed, visible in Docs Center, and not user-disableable in the primary UI.

Trust is earned, not configured: after a Playbook version completes N approved runs, the
approval card offers "always allow this step for this Playbook" — explicit, per-step,
revocable in one click, and itself recorded in the evidence chain. The Agent Contract v2
editor remains available under Advanced; the three levels compile down to contracts, so
Advanced users see exactly what a level means. The graph in Advanced renders enforced
state only (blueprint §4) and visually distinguishes OS-enforced boundaries from
cooperative instructions — the same honesty rule as everywhere else.

### 3. The approval card — the product's most important screen

Every approval must answer "what happens if I say yes" within ten seconds, without
scrolling:

- **One sentence, plain language**: *"The drafting assistant wants to overwrite
  `Chen-contract-v3.docx` (2 similar files in this folder are also affected)."*
  Actor + action + target + scope. No tool names, no protocol names.
- **Scope preview** (gap 3 closed): a small read-only map — this agent → this capability →
  these files/places — with the affected region highlighted. Rendered from enforced
  contract state via React Flow + dagre (blueprint §4). Three columns, no interaction
  needed; click expands to the full map.
- **The change itself** when it is a file change: an inline diff.
- **Two buttons and one checkbox**: Approve / Reject, plus (when eligible) "always allow
  this step for this Playbook". Nothing else.

Approvals from any runtime, and from terminal sessions in Developer mode, render as the
same card.

### 4. Evidence is automatic and silent

The hash chain (blueprint §3) runs always-on underneath every Work. The user never
encounters the words hash, Merkle, chain, signature, or attestation in the primary UI.
They encounter three things:

- an **Evidence** tab per Work: timeline of actions and approvals, diffs, artifacts;
- one button: **Export evidence packet** — produces the ZIP (+ optional PDF summary) from
  blueprint §5, named and dated, with the verify script inside;
- one button: **Verify** — re-checks the sealed record locally and shows
  "Record intact — verified just now" or a plain-language failure.

UI vocabulary: "sealed record", "verified", "exported packet". The packet's README explains
to a third-party recipient (client, auditor) how to verify independently.

### 5. Playbooks make reuse one click

On a signed-off Work: **Save as Playbook**. Running one shows the same plan-review screen
with what will differ this time. Editing produces a new version; old versions stay
runnable and immutable (the public site already promises this). Copy-to-project is a
button. Underneath these are files under version control; the user never sees git.

### 6. Knowledge stays as shipped

The Knowledge Hub source contract (drag/snapshot import, dedupe, card review, bind exact
versions) already matches this spec's bar. Simplicity rule to preserve: import is one drag
plus one review screen; binding is a picker on the New Work screen.

## Developer mode (off by default)

A Settings toggle, not a parallel product. When enabled, OpsWitness detects Claude
Code / Codex / Gemini CLI on the machine and offers to install the hook shim
(blueprint §1 backstop) so terminal sessions raise cards in the same Approvals queue and
write into the same evidence chain. Uninstall is one click and restores prior hook
configs. This closes gap 4 in the other direction: the developer's existing stack gains
the unified queue and sealed evidence without changing how they work.

## Simplicity rules (testable, enforced in review)

1. **Three decisions to first value.** Fresh-or-import data, AI sign-in, run the built-in
   demonstration Work. Anything that adds a fourth required decision to first-run fails
   review.
2. **One sentence per approval.** If the card's headline needs a second sentence, the
   headline generator is wrong, not the layout.
3. **Zero terminal, zero files-as-config** in every primary workflow, including export
   and verify.
4. **Forbidden vocabulary** in primary UI copy: hash, Merkle, signature, attestation,
   DSSE, RFC 3161, MCP, ACP, hook, YAML/JSON/TOML, sandbox profile, worktree, commit.
   Replacements: sealed record, verified, tool, safe workspace, version.
5. **Advanced is optional everywhere.** No promised workflow may require entering
   Advanced. Anything in Advanced states plainly whether it is enforced or cooperative.
6. **Vendor identity is informational, not structural.** The runtime's name appears on
   cards and evidence (accountability) but never changes the workflow shape.
7. **Every automation is revocable in one click**, and both the grant and the revocation
   are recorded in evidence.

## Anti-goals

- Not an IDE, not a terminal replacement, not a parallel-session multiplexer — first-party
  apps own that and give it away free.
- No editable graph canvas. The map renders enforced state; drawing does not grant.
- No SaaS dependency for any promised workflow; external timestamping is opt-in and
  clearly labeled as the only network call evidence ever makes.
- No claim that cooperative gating is a hard guarantee. The strict-isolation rule from
  the support matrix stands: a Contract requiring strict isolation fails closed.

## Delivery slices (after the CURRENT-PROGRESS P0 chain)

Ordered so each slice is independently shippable and testable; each lands only with its
own tests plus the standard rebuilt-App executable gates.

1. **S1 — Trust levels**: the three-level selector compiling to existing contracts; red
   lines fixed; contract editor moves under Advanced. (UI + mapping layer only.)
2. **S2 — Silent evidence chain + Export/Verify**: blueprint §3 retrofitted under existing
   run evidence; Evidence tab gains the two buttons.
3. **S3 — Unified approval queue**: ACP `session/request_permission` interception behind
   the existing approvals view.
4. **S4 — Approval-card scope preview**: React Flow/dagre mini-map from enforced state.
5. **S5 — Playbook save/version UX** over the existing process-versioning machinery.
6. **S6 — Developer mode**: hook shim install/uninstall with config restore.

Acceptance for the persona bar: a first-time, non-technical operator completes the
demonstration Work — including both approvals, evidence review, packet export, and
verify — in under ten minutes with no assistance and no terminal. This scripted
acceptance joins the P0-style executable gates for each slice that touches first-use.
