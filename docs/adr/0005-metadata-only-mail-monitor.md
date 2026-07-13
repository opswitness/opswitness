# ADR-0005: Metadata-only mail monitor

Status: Accepted for implementation; live OAuth and schedule remain gated

Date: 2026-07-13

## Context

AionUi already provides the assistant icon, recommended prompts, conversation history, and
scheduled-task UI. Gmail already provides OAuth and a read-only metadata API, while the pinned
Google Workspace CLI provides a `gmail +triage` helper. Building another inbox UI, scheduler,
mail client, or generic Google API proxy would fail the wheel test.

Email is also an adversarial input surface. Sender names and subjects can contain prompt
injection, private contact information, and instructions that must never become authority.
Daily automation makes an accidental permission expansion persistent.

## Decision

Quarterdeck adds a narrow evidence adapter, not a mail agent:

1. The executable is an absolute, administrator-configured path and its version must equal
   `0.22.5`.
2. Production readiness requires encrypted OAuth credentials with a refresh token and valid
   local decryption. Plaintext credentials and token environment variables are not ready.
3. The Gmail query is fixed in permission-checked local `config.yaml`. CLI and MCP accept no
   query, account, label, message id, or other mailbox selector.
4. The result is limited to sender, subject, date, and message id. Message bodies and snippets
   are never requested or returned.
5. `mail_check_requested` is fsync'd before Gmail access. If that write fails, Gmail is not
   accessed. `mail_check_finished` is fsync'd before metadata is returned; if it fails, the
   metadata is withheld and the run is degraded.
6. Ledger events contain only schema version, source, query SHA-256, limits, counts, and privacy
   mode. They never contain sender, subject, date, account identity, credential paths, or raw
   third-party stderr.
7. Every returned mail field is explicitly untrusted data. No body, draft, reply, send, delete,
   label mutation, link opening, attachment, or generic `gws` tool is exposed.
8. AionUi's native Custom Assistant owns the main-screen icon and common prompts. Its native
   Scheduled Task owns the daily trigger. Quarterdeck builds neither UI nor scheduler.
9. Before enabling a model-backed daily task, the operator must explicitly approve transmission
   of sender/subject/date/message-id to the configured model provider. Without that approval,
   local CLI inspection remains available.

## Consequences

- “Check replies” means a metadata triage of unread inbox messages, not semantic verification of
  thread intent and not automatic replying.
- The adapter is read-only at both product and OAuth scope boundaries. Adding drafts or sends
  requires a new ADR, separate tools, explicit action-time approval, and new evidence semantics.
- AionUi can be replaced without changing the mail trust boundary; the fixed query and evidence
  remain local to Quarterdeck.
- The daily task uses a fresh conversation to reduce cross-run prompt contamination and fails
  closed when readiness, audit evidence, or the external service is unavailable.
