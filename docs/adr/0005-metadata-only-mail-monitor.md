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
2. Every mailbox call revalidates encrypted OAuth credentials, a live token, and a least-privilege
   Gmail scope. `gmail.readonly` is required; full-mail or any Gmail mutation scope is rejected.
   Plaintext credentials and token environment variables are not ready.
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
8. Mail tools live only on `qd mcp --profile mail`. The normal Quarterdeck MCP excludes them,
   while the mail profile excludes every fleet, projection, workflow, shell, and browser action.
   AionUi must bind the two profiles to different assistants and conversations.
9. The loopback total console owns the local on-demand button and authorization dialog; AionUi
   remains the model runtime and its native Scheduled Task may own a future daily trigger.
   Quarterdeck does not build a second inbox or scheduler.
10. Console authorization first requires a Google OAuth client whose top-level type is `installed`
    (Desktop app), whose endpoints are Google's fixed HTTPS endpoints, and whose redirect is
    localhost. The console accepts the JSON only after a private-storage acknowledgement,
    canonicalizes it, and atomically writes gws's `client_secret.json` under `0700`/`0600`
    permissions. Client identifiers and secrets never enter the ledger or API response. Missing,
    invalid, or permission-unsafe client state prevents `gws auth login` from running.
11. Console authorization requires two independent literal-true acknowledgements: Gmail readonly
    OAuth and transmission of sender/subject/date/message-id to the configured model provider.
    The only login argv is `gws auth login --readonly --services gmail`. Completion is accepted
    only after a second version, encrypted-storage, live-token, and readonly-scope verification.
12. Activation state is atomically written to private `mail-activation.yaml`, which may contain
    only `mail.enabled` and `mail.model_metadata_consent`. This managed file has precedence over
    user `config.yaml`, so the console never rewrites comments or unrelated settings. Environment
    overrides remain authoritative. Revocation sets both values false before any future check.
13. OAuth-client import records fixed requested/finished/failed events without client data.
    Authorization records fixed `mail_authorization_requested/finished/failed` events; revocation
    records `mail_consent_revoked`. No account identity, token, credential path, OAuth output, or
    upstream exception enters those events or API responses. If final evidence is lost after
    activation, Quarterdeck rolls activation back to false.
14. Child output is bounded to 1 MiB and the process group is killed on timeout or overflow.

## Consequences

- “Check replies” means a metadata triage of unread inbox messages, not semantic verification of
  thread intent and not automatic replying.
- The adapter is read-only at both product and OAuth scope boundaries. Adding drafts or sends
  requires a new ADR, separate tools, explicit action-time approval, and new evidence semantics.
- AionUi can be replaced without changing the mail trust boundary; the fixed query and evidence
  remain local to Quarterdeck.
- The daily task uses a fresh conversation to reduce cross-run prompt contamination and fails
  closed when readiness, audit evidence, or the external service is unavailable.
