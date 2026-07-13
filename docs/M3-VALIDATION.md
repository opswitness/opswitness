# M3 Claude Tool Gate Validation

Date: 2026-07-13 America/Los_Angeles

Status: **GO for the stated v1 boundary**. Repository tests and two real
board-approved defer/resume drills pass. No real `~/.claude` settings were modified;
Quarterdeck's isolated settings are mode 0600 and the recovery launchd job is loaded.

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

The secret-free `com.quarterdeck.gate-recovery` launchd service runs
`qd gate recover --once` every 60 seconds and passes the same plist validation as the M2
services. It was installed only after the live gate passed.

Full repository verification after live M3 hardening: 147 tests pass; ruff, mypy, and
worktree gitleaks pass. Full-history gitleaks is required again immediately before commit.

## Live acceptance

Normal operator login was verified in the real macOS user environment; no API key or auth
material was inspected, copied, or substituted. Both live sessions used Claude Code 2.1.146,
`--setting-sources ""`, `dontAsk`, the isolated Quarterdeck settings, and an explicit cost
cap.

### Drill 1: one-shot approval

- A Bash request for `printf 'quarterdeck-gate-live-ok\n'` stopped before execution and
  created Paperclip approval `d1732f6f-f32a-4014-a828-50593d76ea73`.
- The operator approved it in Paperclip. The same session resumed and stdout was exactly
  `quarterdeck-gate-live-ok`; cost was USD 0.0689185.
- The authoritative ledger contains exactly one ordered requested, linked, decided,
  consumed, and executed event for request `01KXECN4ZV17SWGXGRJX2MBG7Z`.
- Recovery immediately returned zero pending/resumed/errors. Claude rejected a duplicate
  resume because the deferred marker was already consumed; replaying the same exact hook
  identity returned `deny: approval was already consumed or closed`. The ledger remained at
  five events with no second consumption or execution.

### Drill 2: persisted-input redaction

The first drill also made a privacy boundary visible: approval needs a useful command
summary, but short credentials embedded in a command do not match provider-prefix/entropy
redaction. Context-aware masking was added for assignments, secret flags, JSON/header values,
and Authorization values while the request hash continues to bind the untouched input.
`author` and ordinary URLs remain unmasked to prevent false confidence through over-redaction.

- A second Bash request used the deliberately fake sentinel `API_TOKEN=short-value` and
  printed `quarterdeck-redaction-live-ok`.
- Before approval, both the ledger and Paperclip payload showed
  `API_TOKEN=«redacted»`; the unmasked sentinel had zero matches in the complete ledger.
- Paperclip approval `3fb00d0e-dd37-4295-830e-13f60ba40ed1` resumed the exact session. The
  command executed once and produced the expected stdout; its state chain again contains
  exactly one of each required event.

### Recovery service

- The installed plist passes `plutil`, contains no secret, uses the stable qd path and
  `Umask=077`; output/error logs are mode 0600.
- A forced first run returned zero pending/linked/decided/resumed/errors and exit 0.
- Reinstalling the uv tool while the periodic service was live caused one observed import
  failure during the environment replacement window. A post-install kickstart returned exit
  0. The production doctor now checks every installed service's launchd runtime, not only its
  plist, and the install runbook requires a maintenance window for future qd upgrades.

M3 GO remains intentionally narrow: only `qd gated-claude` non-interactive sessions are
forced through this gate. Interactive Claude, Codex, Hermes, Paperclip-native agents, and
arbitrary direct `claude` invocations are not claimed as governed.
