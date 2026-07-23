# ADR-0008: Repeatable Work and auditable Workspace Memory

Date: 2026-07-22 · Status: accepted and implemented in source

## Context

OpsWitness is for a solo operator who needs to turn useful one-off AI work into a company
process that can be run again, inspected, and improved. Objective-only task templates and
topology-only team blueprints are useful starting material, but neither is the full reusable
procedure. Run history and CAS artifacts preserve evidence, but they are not a memory policy:
an Agent-produced summary must not silently change later planning.

## Decision

### 1. The durable product model is Work -> Run -> Revision

```text
reviewed Work version
        -> one-click preparation
reviewable child version
        -> explicit hash confirmation
independent Run and evidence
        -> natural-language change
immutable Revision
```

`PlanRecord` remains the authoritative immutable Work-version record. OpsWitness does not add a
second mutable Work database. The Workspace derives **Repeatable Work** entries from the latest
ended, intact plan in each Work chain. Selecting one calls the existing rerun preparation path,
creates an unconfirmed child, and never dispatches by itself.

The reusable objects stay intentionally distinct:

| Object | Reuses | Does not reuse |
|---|---|---|
| Task Template | an objective and task wording | plan, team, runtime, or evidence |
| Team Blueprint | roles, reporting lines, loops, runtime preference | task body, credentials, or runs |
| Repeatable Work | the complete reviewed plan, team, stages, cadence, outputs, and model pins | prior execution state, approvals, replies, or artifacts |

### 2. Planning conversation history reuses immutable Plan chains

Workspace conversation history is a projection, not another conversation database. OpsWitness
folds each root `PlanRecord` chain, selects its latest intact revision, and exposes bounded title,
objective, status, version count, timestamps, Plan id, and hash metadata. Selecting a conversation
loads that exact Plan into the existing review surface and has no planning or execution side effect.

An operator may explicitly save the selected source as a TaskTemplate. The write requires CSRF and
confirmation, validates the complete source hash, and appends source Plan id/hash provenance. The
template still reuses objective wording only. It never copies the source team, runtime state,
approvals, operator input, artifacts, outcomes, or run evidence.

Planning history, Work History, and Workspace Memory remain distinct: planning history restores a
reviewed proposal; Work History proves executions; approved Workspace Memory supplies future
read-only planning context.

### 3. Workspace Memory is candidate-first and append-only

Memory has two kinds:

- **process memory**: validated workflow choices, checkpoints, failure lessons, cadence, and
  recurring inputs;
- **knowledge memory**: sourced domain knowledge intended for read-only planning context.

The lifecycle is:

```text
run or operator input
  -> candidate
  -> human approval
  -> active immutable version
  -> supersede / revoke / exact-version rollback
```

Agents may propose candidates but cannot approve or edit active memory. Approval, supersession,
revocation, and rollback are append-only ledger events. The ledger stores ids, state transitions,
paths, and hashes, never the memory body.

### 4. Storage is Obsidian-compatible Markdown plus ledger evidence

The private vault lives below the console state directory:

```text
workspace-memory/
  vault/
    process/<memory-id>/vNNNN-<version-id>.md
    knowledge/<memory-id>/vNNNN-<version-id>.md
  .opswitness/versions/
```

Each Markdown document has YAML frontmatter, provenance, content SHA-256, and an immutable version
id. Directories are `0700`, files are `0600`, symlinks are rejected, and existing bytes are
verified before use. The vault can be opened by Obsidian, but Obsidian is not a runtime dependency
and direct file edits do not become approved memory without a matching OpsWitness lifecycle event.

### 5. Planning reads only one approved snapshot

Before planning starts, OpsWitness folds the ledger, verifies every active approved document, and
builds a bounded, deterministic snapshot. The planner receives only that snapshot and explicit
instructions that memory is context rather than authority, credentials, or outcome proof.

The Work version stores the approved version ids and snapshot hash. Drafting and confirmation both
revalidate the exact snapshot. If a bound version is revoked or superseded before confirmation,
confirmation fails closed. Rerun, continuation, fork, organization revision, runtime revision, and
execution-profile revision inherit the source snapshot exactly; an ordinary natural-language plan
revision captures the currently approved snapshot.

The optional memory envelope is omitted from the canonical hash of historical plans, so existing
plan hashes remain byte-for-byte stable.

### 6. The ordinary UI remains small

Workspace displays completed Work as **My repeatable Work** with one `Prepare to run` action. It
lists prior planning conversations with restore and provenance-bound template actions, and exposes
one Workspace Memory dialog for search, candidate creation, deterministic process
memory proposals, approval, revocation, immutable revision, and rollback. Technical adapter names
remain hidden from this path.

## Consequences

- One-click reuse remains review-first and cannot become silent automatic execution.
- A history record is evidence; an approved memory version is future planning context. The two are
  related but never conflated.
- Directly dropping a Markdown file into the vault cannot influence planning.
- Memory bodies remain private local files and never enter the ledger, Paperclip metadata, or
  browser bootstrap summaries.
- Search is deliberately local and bounded. A vector database, autonomous self-learning loop,
  cross-user memory service, and Work-calling-Work are outside this decision.
- This source change requires a new release artifact and append-only RC canary; earlier canaries do
  not validate it.
