# M3 Claude Tool Gate Validation

Date: 2026-07-12 America/Los_Angeles

Status: repository implementation and deterministic tests pass. Live enforcement is
**NO-GO** until the local Claude Code login and one real board-approved defer/resume drill
pass. No real `~/.claude` settings were modified and the recovery launchd job is not loaded.

## Contract and boundary

- Scope is only non-interactive `claude -p`, wrapped by `qd gated-claude`.
- Claude Code must be at least 2.1.89. The machine has 2.1.146.
- The official [hooks reference](https://code.claude.com/docs/en/hooks) defines `defer` as
  the subprocess/custom-UI contract: the tool is preserved, the process returns
  `stop_reason=tool_deferred`, and `--resume <session-id>` re-fires PreToolUse.
- Hook code never polls or calls Paperclip. It fsyncs a local request and immediately
  returns defer, allow, or deny.
- The supervisor owns Paperclip request/list/get and waits outside the hook. Paperclip UI
  is the only decision source; no Quarterdeck approve command exists.
- `--setting-sources ""`, `dontAsk`, an isolated Quarterdeck settings file, and a strict
  argument allowlist remove user/project/local permission rules and reject bypass, custom
  settings, sessions, plugins, and MCP configuration in v1.
- Safe read tools are `Read`, `Glob`, and `Grep`. Bash/Edit/Write/NotebookEdit and future
  MCP tools match the gate. If parallel defer is not returned by Claude, the new requests
  are closed and normal `dontAsk` handling remains deny.

## Evidence state machine

The local append-only ledger is authoritative for:

1. `tool_gate_requested`
2. `tool_gate_linked`
3. `tool_gate_decided`
4. `tool_gate_consumed`
5. `tool_gate_executed` or `tool_gate_failed`
6. `tool_gate_expired` when no decision is consumable

Request identity binds SHA-256 of session, tool-use id, tool name, and original input.
Only a recursively redacted input summary is persisted or sent to Paperclip. The second
hook holds an exclusive local lease and fsyncs `consumed` before returning allow. Duplicate
resume, request mismatch, expiry, missing ledger writes, and resume without hook consumption
all deny or terminate degraded.

## Deterministic matrix

Covered with an injected fake Claude process and fake Paperclip client:

- single defer -> linked approval -> approved -> same-session resume -> consumed -> executed;
- parallel tool calls where Claude does not return defer;
- expiry before hook and before recovery;
- duplicate resume and one-shot consumption;
- changed input under the same session/tool-use id;
- resume where the expected hook/MCP tool is missing;
- Claude below 2.1.89;
- bypass, alternate permission/settings/session/plugin/MCP flags;
- post-tool execution without prior consumption;
- Paperclip approval list/create/get request shapes;
- structured CLI hook output, including malformed-input deny.

The secret-free `com.quarterdeck.gate-recovery` launchd template runs
`qd gate recover --once` every 60 seconds and passes the same plist validation as the M2
services. It remains uninstalled until the live gate passes.

Full repository verification after M3: 122 tests pass; ruff and mypy pass. Full-history
gitleaks is required again immediately before the M3 commit.

## Live blocker

An isolated real command used Claude Code 2.1.146, `--setting-sources ""`, `dontAsk`, a
temporary PreToolUse defer hook, and only AskUserQuestion. Claude exited before inference
with `Not logged in`; no tool call or hook fired and cost was zero. Quarterdeck will not
substitute an API key, inspect credentials, or change authentication paths.

No file-based Claude managed-settings plist/JSON was present at the documented macOS paths.
Server-managed settings cannot be audited until login; live acceptance must confirm they do
not introduce governed-tool allow rules that weaken the parallel-call `dontAsk` fallback.

Live GO requires: user completes normal Claude login, one harmless governed tool call is
deferred, a human approves it in Paperclip, the exact session resumes, the hook consumes the
decision once, the tool executes exactly once, and a duplicate resume denies. Only then may
the recovery plist be bootstrapped.
