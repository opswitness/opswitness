import assert from 'node:assert/strict';
import test from 'node:test';

import {
  agentContractPlanDraft,
  agentGraphFingerprint,
  agentGraphRevisionRequest,
  createAgentGraphDraft,
  layoutAgentGraph,
  validateAgentGraphDraft,
} from '../src/agent-graph-model.js';

const plan = {
  schema_version: 1,
  title: 'Customer reply',
  summary: 'Draft and verify one customer reply.',
  execution_mode: 'aion_team',
  workflow_id: null,
  agents: [
    {
      name: 'Writer',
      role: 'lead',
      responsibility: 'Draft the reply',
      runtime: 'claude_code',
      model: 'default',
      runtime_reason: 'Balanced',
      reports_to: null,
    },
    {
      name: 'Verifier',
      role: 'reviewer',
      responsibility: 'Check claims',
      runtime: 'codex_cli',
      model: 'default',
      runtime_reason: 'Balanced',
      reports_to: 'Writer',
    },
  ],
  collaboration_loops: [
    {
      source_agent: 'Verifier',
      target_agent: 'Writer',
      condition: 'Return when a claim is unsupported',
      max_iterations: 2,
    },
  ],
  stages: [
    { order: 1, title: 'Draft', owner: 'Writer', outcome: 'Draft exists', checkpoint: false },
    { order: 2, title: 'Verify', owner: 'Verifier', outcome: 'Checks exist', checkpoint: true },
  ],
  cadence: {
    kind: 'once',
    timezone: 'America/Los_Angeles',
    local_time: null,
    update_interval: 'Once',
  },
  tools: [],
  approvals: [],
  artifacts: ['reply.md'],
  risks: [],
  estimated_duration_minutes: 5,
  update_policy: 'Update when complete.',
};

test('Agent Studio projects one immutable Plan into stable nodes and typed edges', () => {
  const draft = createAgentGraphDraft(plan);
  assert.deepEqual(draft.agents.map((agent) => agent.key), ['new:legacy_1', 'new:legacy_2']);
  assert.equal(draft.agents[1].reports_to_key, 'new:legacy_1');
  assert.deepEqual(draft.loops[0], {
    source_key: 'new:legacy_2',
    target_key: 'new:legacy_1',
    condition: 'Return when a claim is unsupported',
    max_iterations: 2,
  });
  assert.deepEqual(validateAgentGraphDraft(draft), []);
  assert.deepEqual(layoutAgentGraph(draft), layoutAgentGraph(draft));
});

test('Agent Studio renames references and stage ownership in one revision payload', () => {
  const draft = createAgentGraphDraft(plan);
  draft.agents[0].name = 'Customer Writer';
  draft.agents[1].responsibility = 'Verify every customer-facing claim';
  const request = agentGraphRevisionRequest(draft, 'a'.repeat(64));
  assert.equal(request.expected_plan_sha256, 'a'.repeat(64));
  assert.equal(request.agents[1].reports_to, 'Customer Writer');
  assert.equal(request.collaboration_loops[0].target_agent, 'Customer Writer');
  assert.deepEqual(request.stage_assignments, [
    { stage_order: 1, owner: 'Customer Writer' },
    { stage_order: 2, owner: 'Verifier' },
  ]);
  assert.equal(request.confirmed, true);
});

test('Agent Studio rejects reporting cycles and duplicate review-loop routes', () => {
  const draft = createAgentGraphDraft(plan);
  draft.agents[0].role = 'specialist';
  draft.agents[0].reports_to_key = 'new:legacy_2';
  draft.agents[1].role = 'reviewer';
  draft.agents[1].reports_to_key = 'new:legacy_1';
  draft.loops.push({ ...draft.loops[0] });
  const errors = validateAgentGraphDraft(draft);
  assert.ok(errors.includes('lead_count'));
  assert.ok(errors.includes('reporting_cycle'));
  assert.ok(errors.includes('loop_invalid'));
});

test('Agent Studio fingerprints semantic edits but not derived canvas layout', () => {
  const draft = createAgentGraphDraft(plan);
  const before = agentGraphFingerprint(draft);
  layoutAgentGraph(draft);
  assert.equal(agentGraphFingerprint(draft), before);
  draft.agents[0].responsibility = 'Draft one bounded reply';
  assert.notEqual(agentGraphFingerprint(draft), before);
});

test('Agent Studio emits a complete v2 contract and rejects duplicate output ids', () => {
  const draft = createAgentGraphDraft(plan);
  const v2 = agentContractPlanDraft(draft, plan);
  assert.equal(v2.schema_version, 2);
  assert.equal(v2.agents[0].contract.default_tool_policy, 'deny');
  assert.equal(v2.agents[1].reports_to_agent_id, 'new:legacy_1');

  draft.agents[1].contract.outputs = [
    {
      ...draft.agents[0].contract.outputs[0],
      relative_path: 'artifacts/verification.json',
    },
  ];
  draft.agents[1].contract.data_scope.allowed_relative_paths = [
    'artifacts/verification.json',
  ];
  assert.ok(validateAgentGraphDraft(draft).includes('output_ids'));
});
