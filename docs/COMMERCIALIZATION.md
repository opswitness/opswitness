# Commercialization Strategy

Status: product decision, 2026-07-14. This document guides packaging and sequencing; it
is not legal, tax, privacy, or licensing advice.

## Decision

Quarterdeck commercializes as an **open local core plus paid vertical delivery, then paid
team operations**. It does not begin as a generic freemium product with an artificial
feature paywall or a token-execution tax.

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
that make Quarterdeck credible:

- local append-only ledger, evidence review, export, and backup/restore paths;
- fail-closed approval boundary and honest health/coverage reporting;
- chat-first plan-before-execution, hash confirmation, versioned plan revision, evidence-preserving
  task deletion, graphical team/loop editing, run history, and basic daily digest;
- user-owned connections to supported local runtimes and existing automation;
- core AionUi, Paperclip, Claude Code, and Codex adapter boundaries.

Safety, evidence, data export, and the ability to leave the product are not upsell levers.
Charging for those would conflict with the trust/evidence position and make the free edition
an unsafe demonstration rather than a product people can adopt.

## First revenue: paid vertical Pilot and implementation

The first commercial product is a paid, local-first vertical workbench, not a generic
"Quarterdeck Pro" subscription. The initial case is the practitioner workbench described in
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

Static prompts, YAML templates, and checklists are distribution material, not the primary
paid moat. The recurring value is dependable operation, curated and evolving domain content,
measured quality, accountable support, and a workbench shaped around a buyer's daily work.

## Later paid offers

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

### Managed operations

Offer managed deployment, encrypted backups, optional multi-machine coordination, monitoring,
and update operations only after the operational and security burden can be carried honestly.
This is a service commitment, not an early feature checkbox. Preserve local control and clear
data residency boundaries; do not require customers to send raw operational or vertical data to
a Quarterdeck cloud merely to use the core.

## Product and repository boundaries

- `quarterdeck` remains the Apache-2.0 platform core.
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
