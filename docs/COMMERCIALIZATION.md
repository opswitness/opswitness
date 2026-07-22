# Commercialization Strategy

## Community Alpha packaging update

The first public candidate is the Apache-2.0, single-operator OpsWitness Community Alpha distributed
only as signed GitHub Release assets. It has no account requirement, artificial run quota, PyPI
dependency, token resale, or hosted control plane. Private HTTPS/PWA and optional mail/Telegram
connections remain clearly labeled Beta or Experimental; future commercial modules cannot weaken
the free core's local evidence, export, backup, approval, or fail-closed behavior.

Status: product decision, 2026-07-14. This document guides packaging and sequencing; it
is not legal, tax, privacy, or licensing advice.

## Decision

OpsWitness commercializes as an **open local core plus paid vertical delivery, then paid
team operations**. It does not begin as a generic freemium product with an artificial
feature paywall or a token-execution tax.

The Community product is first designed as the simple repeatable-work operating layer for a
one-person company. It does not compete with Codex or Claude for deep execution. It makes their
one-off work reusable through reviewed Work definitions, Agent architecture, immutable versions,
Run again, Fork work, History, Results, and locally owned evidence. This positioning is governed by
[PRODUCT-VISION.md](PRODUCT-VISION.md) and remains the product filter for both free and paid work.

> Free software establishes trust. Paid vertical workbenches establish early revenue.
> Shared governance and managed operations become the later recurring business.

The core is Apache-2.0. Anything distributed in that core remains freely usable under its
published license; future commercial value must therefore be separable from the start:
proprietary vertical applications and content, hosted or operated services, and paid
implementation/support. Do not assume an already-published open-core capability can later
be withdrawn into a paid edition.

## Community core: free and complete enough to trust

The local, single-operator Community edition remains open source and useful without an
account, vendor proxy, artificial run quota, or paid server. It includes the capabilities
that make OpsWitness credible:

- local append-only ledger, evidence review, export, and backup/restore paths;
- plan-confirmed Auto execution, an audited in-Work Auto/manual switch for future calls, opt-in
  per-tool manual approval, durable approval evidence, and honest health/coverage reporting;
- one task-local attention surface for manual approval and Agent questions, with the global queue
  retained for cross-task triage rather than sold as a usability upgrade;
- fixed, state-honest Start/Continue, Pause, and End controls for supported local Aion work, with
  second confirmation and evidence retention included in the free core;
- chat-first plan-before-execution, hash confirmation, versioned plan revision, evidence-preserving
  task deletion, independent provenance-bound Work forks, graphical team/loop editing, immutable
  run history with guarded same-context Aion continuation, and basic daily digest;
- one-click review-first preparation from completed Work, with the complete reviewed plan and Agent
  architecture retained without an execution, Agent, or Work quota;
- local auditable Workspace Memory: private Obsidian-compatible process/knowledge versions,
  candidate review, approval, supersession, revocation, rollback, search, and approved-only planning
  snapshots remain Community capabilities rather than a paid trust gate;
- an in-Overview AI adjustment box for evolving goals, stages, Agent hierarchy, bounded loops,
  cadence, outputs, and checkpoints through reviewable immutable versions, without a paid revision
  limit or automatic dispatch;
- one Work identity across the Today active summary and the full Work detail; no duplicate team
  registry or paid global-employee directory is required for the single-owner product;
- user-owned connections to supported local runtimes and existing automation;
- per-Agent runtime and advertised-model selection, including free Fast/Balanced/Deep review-time
  presets and Custom edits, with immutable hash binding and no silent fallback;
- plan-bound live stage telemetry from structured runtime work items, with safe activity metadata
  and an explicit separation between Agent-reported execution and verified business outcomes;
- fixed-loopback Ollama and LM Studio discovery/connection through the hidden local adapter, with
  no vendor proxy, remote endpoint, or OpsWitness token markup;
- core AionUi, Paperclip, Claude Code, and Codex adapter boundaries.

Community must remain sufficient for a solo operator to build an unlimited library of repeatable
company Work. Founder Pro may make that library easier to maintain, connect, back up, and recover,
but it must not remove the first-use flow or repeatability primitives from the free edition.

Safety, evidence, data export, and the ability to leave the product are not upsell levers.
Charging for those would conflict with the trust/evidence position and make the free edition
an unsafe demonstration rather than a product people can adopt.

## First revenue: paid vertical Pilot and implementation

The first commercial product is a paid, local-first vertical workbench, not a generic
"OpsWitness Pro" subscription. The initial case is the practitioner workbench described in
[M6-PILOT-GATE.md](M6-PILOT-GATE.md) and the customer-facing
[PRACTITIONER-PILOT-OFFER.zh-CN.md](PRACTITIONER-PILOT-OFFER.zh-CN.md).

The paid offer packages outcomes that are difficult to commoditize as a copied template:

- white-glove local installation and workflow configuration;
- a deterministic domain engine, signed knowledge corpus, eval fixtures, and report workflow;
- privacy/data-boundary implementation, backup/recovery guidance, and human sign-off;
- repeated workflow reviews, product feedback, and support during the Pilot;
- continuing rule, corpus, and eval updates after the Pilot only when a customer renews.

The existing M6 rule holds: no practitioner UI or private vertical repository starts before
written paid commitment or a real deposit. The published USD 1,500, 30-day Pilot is a
validation baseline, not a promise that every future vertical has that price.

The Community catalog also exposes three **professional evidence-pack templates** as design-partner
starting points. Their commercial validation order is CPA/EA month-end and pre-tax workpapers first,
licensed-customs-broker entry-support evidence second, and commercial P&C renewal readiness third.
They are not public promises of automated tax filing, customs filing, claims handling, insurance
advice, or placement. In every case the buyer is the qualified professional, the product prepares a
traceable exception/readiness pack, and the professional resolves exceptions, takes the regulated
position, and signs or submits. The generic company commercial-analysis template is a Community
workflow, not a regulated conclusion or investment recommendation.

Do not build a private vertical application merely because the template exists. A professional
vertical advances only after a written paid commitment or deposit and must measure human minutes per
pack, exception rate, reviewer overturn/rework rate, renewal intent, and contribution margin. If the
operator spends the recurring workday on data entry, document chasing, or rewriting model output, or
the observed contribution margin cannot exceed 50%, classify it as services work rather than an AI
product. The current Practitioner Pilot remains the only published paid offer until one of these
design-partner paths earns its own validated scope and price.

Static prompts, YAML templates, and checklists are distribution material, not the primary
paid moat. The recurring value is dependable operation, curated and evolving domain content,
measured quality, accountable support, and a workbench shaped around a buyer's daily work.

## Later paid offers

### Founder Pro

Introduce Founder Pro only after Community operators repeatedly ask OpsWitness to operate the
local installation for them. It is a convenience and continuity layer for a one-person company,
not a license unlock for the trusted core. Candidate paid capabilities are:

- tested automatic upgrades with rollback;
- scheduled encrypted backups and isolated recovery verification;
- guided private-network access and device onboarding;
- maintained advanced connectors and compatibility updates; and
- priority installation, migration, and incident support.

Founder Pro must not impose Agent, Work, execution, token, ledger, Artifact, History, export,
restore, or approval limits on Community. Do not publish an experimental Founder Pro price until
repeated demand and delivery cost are observed; keep internal price tests out of the public
repository.

### Team / Business

Introduce only after several similar paying customers demonstrate the same recurring need.
Candidate paid capabilities are shared operational value, not single-user safety:

- shared organizations/workspaces, human identities, roles, and approval delegation;
- centralized audit exports, retention controls, policy administration, and compliance support;
- shared connection administration and external secret-manager integration;
- verifiable organization-wide iteration/policy controls only after the runtime can enforce and
  evidence them, never by relabeling a prompt-level loop cap as a compliance control;
- private deployment, upgrades, incident response, and contractual support.

Price the Team offer primarily per active organization/workspace plus the support level. Do
not price by raw agent count, model tokens, or every execution: customers already pay model
providers directly, and a low-value high-frequency job should not be punished more than a
high-value low-frequency workflow.

Team price experiments also remain internal until the repeated buyer and support boundary are
real. The public repository should explain value and packaging without anchoring an unvalidated
price range.

### Managed operations

Offer managed deployment, encrypted backups, optional multi-machine coordination, monitoring,
and update operations only after the operational and security burden can be carried honestly.
This is a service commitment, not an early feature checkbox. Preserve local control and clear
data residency boundaries; do not require customers to send raw operational or vertical data to
an OpsWitness cloud merely to use the core.

## Product and repository boundaries

- `opswitness` remains the Apache-2.0 platform core.
- Private vertical workbenches, proprietary domain corpora, eval/rule update services, and
  customer-specific configuration live in separate repositories and packages.
- Credentials, customer data, strategies, and private knowledge never enter the public core.
- Brand/trademark ownership remains separate from the code license and must pass the release
  gate in [BRAND-CLEARANCE.md](BRAND-CLEARANCE.md) before public commercial use.

## Sequencing gates

1. Ship and maintain an open Community core that is safe and valuable on one machine.
2. Obtain a written paid commitment or deposit for one vertical Pilot.
3. Deliver the Pilot, collect evidence of use and a clear renewal decision.
4. Repeat with enough comparable customers to identify a shared paid operating need.
5. Productize that repeated need as Team / Business; only then build billing, entitlement,
   multi-tenant, or hosted-operation machinery.

Until gate 4, consulting-quality implementation and vertical delivery are the business model.
Star counts, free installs, and verbal interest are distribution signals, not revenue validation.

## Explicit non-goals for the first commercial phase

- no token resale or hidden provider markup;
- no paid wall around local audit evidence, data export, or basic fail-closed safety;
- no generic subscription billing system before a paid Pilot proves the buyer;
- no multi-tenant SaaS, formal SLA, or cloud custody of raw practitioner PII;
- no claim that a static template marketplace is durable recurring revenue;
- no enterprise/compliance claim for the current collaboration-loop cap: it is hash-bound in the
  plan and visible in the UI, but the pinned execution adapter exposes no verifiable hard cutoff.

## Review trigger

Revisit this strategy after the first paid Pilot and again after three paying customers in one
repeatable segment. Change packaging based on observed recurring operational value, not on a
wish to imitate a generic "Free / Pro / Enterprise" pricing table.
