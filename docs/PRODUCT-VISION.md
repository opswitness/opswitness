# Product Vision

Status: product-direction contract. This document sets priorities and acceptance criteria; it does
not claim that every described capability is complete in the current release.

## Product promise

> **OpsWitness 帮助一人公司把一个想法自动变成可重复的 AI 团队流程，并通过一键运行、版本历史和可验证结果长期经营。**

OpsWitness is the simplest first place for a solo operator to turn one-off AI work into a
repeatable company process. It does not try to replace Codex, Claude, AionUi, Paperclip, or a
specialist workflow engine. Those systems remain the workers and infrastructure. OpsWitness owns
the small, durable layer that makes their work easy to start again and safe to understand later:
the reviewed plan, Agent structure, versions, run history, outputs, approvals, and evidence.

The product should feel like operating a small company, not configuring an Agent platform.

Its core loop is deliberately smaller than a general Agent platform:

```text
Work Blueprint (reviewed process and Agent architecture)
        -> one-click preparation and confirmation
Run (one independent execution and evidence history)
        -> natural-language improvement
Revision (a new immutable architecture version)
```

## Primary user

The primary user is one person running a business with AI and automation. They may use several
models, coding agents, scripts, and specialist tools, but they should not need to understand or
routinely open the underlying control planes.

Their recurring job is:

1. Describe an outcome in ordinary language.
2. Review the proposed work: inputs, steps, Agent roles, reporting lines, cadence, outputs, risks,
   and checkpoints.
3. Confirm the exact version before anything runs.
4. See what is active, what needs attention, and what evidence or output exists.
5. Run the same reviewed work again, revise it as a new version, or fork it for a new purpose.

## The core product object: Work

One **Work** is a reusable operating procedure, not merely one chat or one execution. It binds:

- the business goal and boundaries;
- the confirmed plan and version hash;
- an Agent or Agent-team structure, including reporting relationships;
- runtime and model assignments;
- required inputs, cadence, checkpoints, and expected outputs;
- every independent run and its process evidence;
- results, artifacts, evaluations, and human sign-off when available; and
- the provenance needed to run again, revise, fork, export, or recover it.

Runs never overwrite the Work definition or one another. A revision creates a new immutable
version. **Run again** prepares another run from a reviewed version and still requires exact-plan
confirmation before dispatch. **Fork work** creates an independent Work with explicit source
provenance. This is the foundation of repeatability.

The starting objects have narrow jobs. A **Task Template** keeps only reusable goal wording. A
**Team Blueprint** keeps only reusable role topology. A **Repeatable Work** is the latest ended,
intact, reviewed Work version and therefore preserves the complete plan, team, stages, cadence,
outputs, checkpoints, and exact runtime/model choices. Preparing it creates a reviewable child and
never dispatches on click. **Workspace Conversation History** is the read-only projection of
immutable planning revisions before execution: selecting one restores its latest intact Plan for
review, and saving it as a template records the exact source Plan id/hash without carrying runtime
or execution state.

## Flow memory before general memory

Long-term memory first serves repeatable company operations, not autonomous personality. It keeps:

- which Agent architecture and process was reviewed;
- why a later immutable revision changed it;
- which runs succeeded, failed, or still need verification; and
- which process lessons or sourced knowledge a human explicitly approved for reuse.

History and CAS artifacts remain evidence about past runs. They do not automatically become future
instructions. An Agent may propose a memory candidate, but only a human-approved, versioned,
hash-bound Workspace Memory snapshot is available read-only to a new planner. Approved memory can
be superseded, revoked, or rolled back without deleting prior versions. The private Markdown vault
is Obsidian-compatible; the append-only ledger records lifecycle and hashes rather than memory
bodies. See [ADR-0008](adr/0008-repeatable-work-and-auditable-workspace-memory.md).

## First-use experience

The ordinary path stays deliberately small:

```text
Workspace chat
  -> describe a goal, resume a planning conversation, or choose a preset/template
  -> review the generated plan and team
  -> confirm
  -> Work overview
  -> respond only when attention is needed
  -> History and Results
  -> Run again, revise, or fork
```

The default interface should expose business language and primary actions, not adapter names,
issue systems, raw ledgers, model internals, or infrastructure health. Paperclip, AionUi, provider
CLIs, and automation details belong in Connections or advanced diagnostics.

Automatic execution is the normal single-owner path after exact plan confirmation. Manual tool
approval remains an explicit switch. Input requests, approvals, pause/continue/end, outputs, and
run history stay inside the selected Work instead of forcing navigation to specialist systems.

## Essential Community capabilities

The simple product is complete only when it preserves these capabilities:

- chat-to-plan creation with a review step before execution;
- visible Agent roles and team architecture without a separate employee database;
- immutable plan versions and a readable change history;
- one clear Run again path, exact-plan confirmation, and provenance-bound Fork work;
- repeatable schedules, templates, and common-task starting points;
- one-click preparation from completed Work without bypassing review;
- candidate-first, human-approved, versioned Workspace Memory for process lessons and sourced
  knowledge;
- clear live activity and attention requests without exposing hidden reasoning;
- per-run Process, Results, artifacts, approval, and evidence history;
- local ownership, export, backup, restore, and fail-closed behavior; and
- replaceable execution adapters with no silent model or runtime fallback.

These are not advanced enterprise features. They are the minimum needed for one person to trust
and reuse a growing library of company workflows.

## Example repeatable company work

OpsWitness should make it easy to build and reuse work such as:

- daily inbox review and reply queues;
- weekly project, customer, and financial summaries;
- research, comparison, and decision memos;
- source-backed company commercial analysis with explicit calculations and counterarguments;
- content research, drafting, review, and publication preparation;
- customer-support triage and follow-up preparation;
- lead research and outreach preparation;
- recurring website, automation, and data-quality checks;
- meeting preparation and action-item follow-up;
- document, report, and specialist-practice evidence packs for licensed human review; and
- software planning, implementation, review, testing, and release preparation.

Presets accelerate the first plan, but the reviewed Work and its evidence remain the product.
The priority professional templates deliberately prepare evidence rather than impersonating the
licensed service: CPA/EA workpapers stop before accounting entries, tax positions, or filing; customs
packs stop before classification, valuation, origin, or entry submission; commercial-insurance packs
stop before coverage advice, quoting, submission, or binding. The qualified professional remains the
decision maker and signer.

## Simplicity rules

Every proposed feature must pass all of these tests:

1. Does it help a solo operator create, run, understand, or reuse a real company process?
2. Does it reduce ordinary setup or navigation instead of exposing another subsystem?
3. Can its state be versioned, attributed, and reconstructed honestly?
4. Can an existing runtime or library provide the execution capability?
5. Can it be omitted from the default interface until the user actually needs it?

If the answer is no, defer it. OpsWitness does not need to become a general coding assistant,
model chat client, DAG engine, scheduler, Agent runtime, or enterprise control plane.

## Product measures

The north-star measures are usability and repeatability, not Agent count:

- a new operator can create and run the first useful local Work in under ten minutes;
- the operator can prepare a reviewed Work to run again from one clear primary action, then confirm
  the exact version before dispatch;
- every run can be distinguished, inspected, and reconstructed from its version and evidence;
- every planning conversation can be restored from its immutable revisions and deliberately turned
  into a provenance-bound objective template;
- an operator can approve, revoke, revise, or roll back Workspace Memory without an Agent silently
  changing later plans;
- the operator can understand the team, current state, required attention, and outputs without
  opening Paperclip or AionUi; and
- adding more models or adapters does not add more ordinary top-level workflows to learn.

## Scope boundary

OpsWitness is a management and repeatability layer for a one-person company. Codex and Claude may
remain the best places to perform deep coding or open-ended work. AionUi or future runtimes may
remain the best places to execute Agent teams. Paperclip may remain the governance backend.
OpsWitness wins when the operator can turn those capabilities into a durable company process and
use it again without rebuilding the team, instructions, controls, or evidence trail.
