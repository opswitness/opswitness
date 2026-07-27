# From Skills to Structured Work

Status: product contract and current implementation boundary.

> **Skill proposes. Structure governs. Run evidence proves.**

Skills, prompts, and presets remain useful for discovering a method. Repeatable company work should
not require the operator to remember and reinterpret the same instructions on every run.
OpsWitness therefore turns a reviewed method into explicit, immutable product state: a Work
version, Agent topology, Agent Contract, stage ownership, controls, required outputs, evidence, and
history.

## Operator-owned Agent Contracts

AI-generated Agents are drafts. The operator can review and edit each Agent's:

- name, role, responsibility, full instructions, and prohibitions;
- structured inputs, outputs, acceptance criteria, and relative-path data scope;
- exact tool rules and file/input/network/send/publish/delete side-effect policy;
- selected immutable Workspace Memory versions;
- manager, handoff, escalation, collaboration loops, approval checkpoints, retries, and stop rules;
- runtime, model ID, binding type, adapter version, executable digest, and binding status.

Saving never mutates a reviewed or historical plan. The flow is:

```text
edit -> preview normalized contract and field diff -> create vN+1 -> confirm -> run
```

The advanced Effective Instructions view shows the exact OpsWitness-owned canonical envelope and
SHA-256 used by dispatch. It has three visible layers: editable operator instructions, structured
contract plus actual enforcement level, and the read-only platform safety layer. OpsWitness does
not claim access to provider-hidden instructions.

## Current implementation matrix

| Capability | Current Alpha source | Enforcement boundary |
|---|---|---|
| Read historical TaskPlan v1 | Implemented | Existing plan bytes and historical hashes are not rewritten |
| Upgrade v1 to v2 | Implemented | Creates a reviewed child version with server-generated stable Agent IDs |
| Add/delete Agent | Implemented, 1–5 | Deletion remediates stages, reports, loops, handoffs, inputs, and escalation before validation |
| Six-page Agent Studio | Implemented | Ordinary DOM controls are authoritative; SVG is visual-only |
| Preview/revision/version/diff APIs | Implemented | Preview and revision share one validator and one complete draft |
| Exact execution envelope | Implemented | Preview and actual dispatch use identical canonical bytes and SHA-256 |
| Per-Agent Memory | Implemented | Revoked/tampered/out-of-snapshot Memory blocks confirmation; Aion non-lead private Memory is refused |
| Per-Agent tool policy | Implemented for mapped Aion approvals | `deny` rejects, `always_ask` interrupts global Auto, `inherit_run_mode` uses Work mode; unknown identity/tool fails closed |
| Required artifact check | Implemented | Existence, SHA/CAS registration, and acceptance status are checked after execution |
| Aion shared-Workspace path, handoff, loop, retry, timeout rules | Visible and hash-bound | Execution instruction, not isolation or hard cutoff |
| Strict sequential runtime primitives | Implemented | State machine, private Workspaces, digest-bound input copy, CAS handoff, managed file/network/side-effect Broker, bounded retry, and stop confirmation |
| Strict runtime adapter | Not available | A strict Contract is refused before execution; it never silently downgrades |

The source-complete v2 implementation is not a released capability until the Mac App is rebuilt and
the exact executable passes a clean-machine first Work, crash/recovery tests, and a new canary.

## Context and Memory

The goal is not zero prompt tokens. Every Agent still needs its current role, stage, constraints,
approved inputs, and acceptance contract. Durable structure avoids repeatedly reconstructing stable
organization and controls, while selected Memory stays bounded, immutable, human-approved, and
separate from runtime history. Agents may generate experience candidates, but they cannot approve
them or silently change future Work.
