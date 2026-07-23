# ADR-0004: AionUi launches fixed workflows through an audited local allowlist

Date: 2026-07-13

Status: Accepted

## Context

AionUi already supplies the interface we need: MCP tool calls plus a Manual Scheduled Task
with a native **Run now** button. Rebuilding that UI would violate the wheel test. Exposing a
generic command tool would be worse: any model or prompt injection reaching the MCP server
would acquire a local shell.

The missing component is narrower. A human needs to register a known workflow entrypoint once,
then launch that exact entrypoint from AionUi while preserving OpsWitness's evidence and
fail-closed rules. A workflow may internally be a LangGraph application, deterministic script,
or another proven runtime; OpsWitness must not become a second workflow engine.

## Decision

1. `~/.config/opswitness/workflows.yaml` is the only launch allowlist. It is strict-schema,
   non-symlink, and mode `0600` inside the existing `0700` configuration directory.
2. Each definition contains a stable id, display metadata, an absolute fixed argv, an absolute
   cwd, enabled state, and `concurrency: forbid`. Runtime argv, shell strings, environment
   launchers, and apparent credentials are rejected. The MCP cannot create or edit definitions.
3. `qd_workflow_start` accepts one field: the exact workflow id. It receives no path, command,
   environment, or free-form parameter.
4. Dispatch is asynchronous and survives AionUi closing. A dedicated Python supervisor inherits
   a per-workflow flock and writes stdout/stderr to a private per-run log.
5. Commit order is enforced by a pipe barrier:

   ```text
   workflow_launch_requested (fsync)
   -> supervisor spawn, blocked on pipe
   -> workflow_launch_dispatched (fsync)
   -> release pipe
   -> run_started (fsync)
   -> exec
   -> run_finished (fsync)
   ```

   If requested or dispatched evidence cannot be committed, the barrier is never released and
   the command does not execute. Definition hash drift before execution also fails closed.
6. The worker receives a minimal environment (`HOME`, `PATH`, locale, temp/timezone, and explicit
   OpsWitness config/ledger paths). Workflow secrets must be loaded by the registered program
   through its own permission-checked boundary, never embedded in argv or AionUi.
7. Runs tied by run id to `workflow_launch_requested` are classified as auditable **on-demand**
   runs. They remain in execution health and problem reporting, but are not falsely reported as
   missing watchdog schedules.

## AionUi binding

For each desired button, create one AionUi Manual Scheduled Task whose fixed instruction is:

```text
Call qd_workflow_start exactly once with workflow_id "WORKFLOW_ID". Do not call any other
mutating tool. Return the run_id, then call qd_workflow_status for that run_id.
```

AionUi's **Run now** button is the launch gesture. This is not an approval decision. Paperclip Web
UI remains the sole source for M3 tool-call approvals, and AionUi YOLO/full-auto mode is not
required.

## Consequences

- One click can launch a complete registered workflow without exposing arbitrary command
  execution.
- A successful process exit remains execution evidence only. Artifact eval/signoff is still
  required to claim a correct business outcome.
- Updating a workflow remains a local administrative action (`qd workflow register --replace`),
  not something an agent can do through MCP.
- Parameters, cancellation, queueing, DAG semantics, retries, and distributed execution are
  deliberately absent. A workflow runtime owns those concerns when they are needed.

