# M6 Practitioner Pilot Gate

Date: 2026-07-12 America/Los_Angeles

Status: outreach-ready; product implementation is blocked on a written paid commitment or
deposit from one design partner. The customer-facing offer and confirmation template is
[PRACTITIONER-PILOT-OFFER.zh-CN.md](PRACTITIONER-PILOT-OFFER.zh-CN.md).

## Design-partner offer

The pilot is a 30-day, single-practitioner deployment on the practitioner's own Mac. Its
scope is ten real, human-reviewed reports using the workflow below:

1. client intake and explicit cloud-processing consent;
2. deterministic `lunar-python` chart construction and golden-test verification;
3. signed local knowledge retrieval;
4. model-generated draft using only the approved derived features and excerpts;
5. citation/eval checks;
6. mandatory practitioner signoff;
7. Playwright PDF generation, CAS registration, and practitioner-controlled delivery.

The commercial commitment must identify the practitioner, pilot fee or deposit, payment
date, 30-day start window, ten-report target, deployment Mac, customer-provided Anthropic
API key, and acceptance criteria. An email or signed statement of work is sufficient for
the product gate; a verbal expression of interest is not.

## Non-negotiable data boundary

- Name, contact details, and raw birth date/time stay in the local practitioner database.
- Those fields never enter model requests, Paperclip metadata, logs, Telegram, or artifact
  metadata.
- The only permitted model payload is an anonymous client ID, deterministic derived chart
  features, and the exact retrieved knowledge excerpts required for the draft.
- SQLite business fields use AES-256-GCM with per-record nonces; the master key lives in
  macOS Keychain, not a config file or repository.
- The product must expose consent state, export, deletion, and configurable retention.
- Reports are framed as entertainment/reflection and require human signoff; the system does
  not promise factual prediction, medical, legal, or financial outcomes.

## Engineering start gate

Do not create `opswitness-practitioner`, choose a frontend template, or implement UI before
paid evidence exists. Once it exists, implementation starts in this order:

1. threat model and egress allowlist tests;
2. encrypted local data model and Keychain integration;
3. deterministic chart golden fixtures;
4. signed Markdown corpus schema, FTS5 retrieval, and citation checks;
5. end-to-end workflow with mandatory artifact signoff;
6. FastAPI + React/Vite workbench and Playwright PDF;
7. local-only launchd packaging, data export/deletion, and operator runbook.

No subscription system, multi-tenant SaaS, vector database, mobile app, WeChat mini-program,
automatic customer sending, or formal SLA is in the first pilot.

## Success evidence

- 30 days and at least 10 paid real reports;
- 100% practitioner signoff and traceable citations;
- all deterministic chart golden tests pass;
- zero raw PII egress and zero artifact loss;
- completed payment and an explicit continue/renew decision from the practitioner.

Until the paid gate closes, the correct implementation state is deliberately empty: no
private product repository and no customer-data UI.
