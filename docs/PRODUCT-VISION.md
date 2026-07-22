# Product Vision

Status: product-direction contract. This document sets priorities and acceptance criteria; it does
not claim that every described capability is complete in the current release.

## Product promise

> **一人公司的可重复 AI 工作台：说出目标，确认团队和流程，一键运行、复用和追溯。**

OpsWitness is the simplest first place for a solo operator to turn one-off AI work into a
repeatable company process. It does not try to replace Codex, Claude, AionUi, Paperclip, or a
specialist workflow engine. Those systems remain the workers and infrastructure. OpsWitness owns
the small, durable layer that makes their work easy to start again and safe to understand later:
the reviewed plan, Agent structure, versions, run history, outputs, approvals, and evidence.

The product should feel like operating a small company, not configuring an Agent platform.

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

## First-use experience

The ordinary path stays deliberately small:

```text
Workspace chat
  -> describe a goal or choose a preset/template
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
- content research, drafting, review, and publication preparation;
- customer-support triage and follow-up preparation;
- lead research and outreach preparation;
- recurring website, automation, and data-quality checks;
- meeting preparation and action-item follow-up;
- document, report, and specialist-practice workflows; and
- software planning, implementation, review, testing, and release preparation.

Presets accelerate the first plan, but the reviewed Work and its evidence remain the product.

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
- the operator can understand the team, current state, required attention, and outputs without
  opening Paperclip or AionUi; and
- adding more models or adapters does not add more ordinary top-level workflows to learn.

## Scope boundary

OpsWitness is a management and repeatability layer for a one-person company. Codex and Claude may
remain the best places to perform deep coding or open-ended work. AionUi or future runtimes may
remain the best places to execute Agent teams. Paperclip may remain the governance backend.
OpsWitness wins when the operator can turn those capabilities into a durable company process and
use it again without rebuilding the team, instructions, controls, or evidence trail.
