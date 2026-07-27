# ADR-0009: Agent Studio is a Plan projection, not a second workflow engine

- Status: Accepted
- Date: 2026-07-25

## Context

OpsWitness needs the useful part of an n8n-style experience: an operator should be able to see
Agent roles and relationships, select a node, adjust its reviewed contract, and understand how
work returns for verification. Bundling n8n, Langflow, Flowise, or Node-RED would introduce another
runtime, credential store, plugin supply chain, and execution authority.

The existing `TaskPlan` already owns the Agent list, sequential stages, reporting tree, bounded
review loops, runtime/model selections, approvals, artifacts, immutable revisions, and execution
hash. A visual editor must not create a second mutable representation of those facts.

## Decision

Agent Studio is a deterministic visual projection of one exact `TaskPlan`.

- Solid edges show the single-root, acyclic reporting tree.
- Dashed edges show bounded review loops. They remain plan-level contracts and are not presented as
  a hard runtime cutoff.
- The inspector edits the current Agent names, roles, responsibilities, runtime/model selections,
  reporting lines, review loops, and sequential stage ownership.
- One save submits the complete projection with the expected parent Plan hash to
  `POST /api/v1/plans/{plan_id}/agent-graph/revisions`.
- The backend validates the whole graph, checks the source hash and runtime catalog, and creates one
  immutable child Plan plus a content-free ledger event. It never mutates the parent or dispatches
  the new version.
- Canvas coordinates and presentation state never enter `TaskPlan`, `agent_graph_sha256`, or
  `plan_sha256`.
- The Alpha keeps the existing Agent count fixed. Adding or removing Agents remains a full Work
  revision until stage migration and per-Agent contract migration have an explicit schema.

The initial renderer is local React and SVG because Alpha plans contain at most five Agents and the
desktop Console enforces a strict Content Security Policy. If larger graphs later justify a general
canvas library, the renderer may move to MIT-licensed
[React Flow](https://reactflow.dev/) without changing the backend graph contract.

## Explicit non-goals

Agent Studio does not add:

- arbitrary JavaScript, HTTP, shell, package-install, or community plugin nodes;
- a general branching/parallel workflow DAG;
- a second scheduler, retry engine, credential store, ledger, or artifact authority;
- silent Agent execution, confirmation, or permission escalation.

A future `WorkflowGraph` may add reviewed triggers, conditions, parallel branches, joins, retries,
approvals, and evidence nodes. It must remain separate from the Agent reporting graph and preserve
OpsWitness governance, ledger, CAS, and runtime boundaries.

## Consequences

The operator gets a direct graphical management surface without adopting n8n licensing or another
control plane. Existing API clients remain compatible because the organization and runtime revision
endpoints are retained. The tradeoff is intentional: the first version is an Agent organization and
contract editor, not a claim that OpsWitness now implements all of n8n.
