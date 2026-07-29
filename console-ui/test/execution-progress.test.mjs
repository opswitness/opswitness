import assert from 'node:assert/strict';
import test from 'node:test';

import {
  executionControlPresentation,
  formatExecutionElapsed,
  onboardingApprovalOrder,
  onboardingRunProgress,
  runtimeActivitySource,
  runtimeActivityTone,
  stageProgressPresentation,
  stageProgressSummary,
} from '../src/execution-progress.js';

test('onboarding maps only the two fixed local-save approvals to their visible order', () => {
  assert.equal(onboardingApprovalOrder({
    title: 'Allow one local save: artifacts/first-work.json',
    summary: 'Bound to the reviewed digest.',
  }), 1);
  assert.equal(onboardingApprovalOrder({
    title: 'Allow one local save',
    summary: 'Exact path: artifacts/verification.json',
  }), 2);
  assert.equal(onboardingApprovalOrder({
    title: 'Allow a network request',
    summary: 'Unexpected operation',
  }), null);
  assert.equal(onboardingApprovalOrder(null), null);
});

test('runtime activity exposes tool identity without arguments or output', () => {
  const activity = {
    kind: 'tool_call',
    status: 'completed',
    tool_name: 'mcp__aionui-team__team_task_update',
  };
  assert.deepEqual(runtimeActivitySource(activity), {
    label: '更新团队工作状态',
    values: {},
  });
  assert.equal(runtimeActivityTone(activity.status), 'neutral');
  assert.doesNotMatch(JSON.stringify(runtimeActivitySource(activity)), /raw_input|raw_output/);
});

test('runtime duration is readable without inventing a completion percentage', () => {
  assert.equal(formatExecutionElapsed(42), '42s');
  assert.equal(formatExecutionElapsed(3720), '1h 2m');
  assert.equal(formatExecutionElapsed(3720, 'zh'), '1 小时 2 分钟');
});

test('onboarding progress uses only observed runtime stages and a real elapsed clock', () => {
  const model = onboardingRunProgress({
    workStatus: 'running',
    plannedStages: [
      { order: 1, owner: 'Business Assistant' },
      { order: 2, owner: 'Review Assistant' },
    ],
    progress: {
      available: true,
      active_members: [
        { agent_name: 'Business Assistant', state: 'running', slow: false },
      ],
      stages: [
        {
          stage_order: 1,
          agent_name: 'Business Assistant',
          status: 'running',
          source: 'aion_team_task',
        },
        {
          stage_order: 2,
          agent_name: 'Review Assistant',
          status: 'pending',
          source: 'unobserved',
        },
      ],
    },
    startedAt: '2026-07-24T12:00:00.000Z',
    estimateMinutes: 3,
    nowMs: Date.parse('2026-07-24T12:00:42.000Z'),
  });

  assert.deepEqual(
    model.stages.map(({ order, status, observed }) => ({ order, status, observed })),
    [
      { order: 1, status: 'running', observed: true },
      { order: 2, status: 'not_started', observed: false },
    ],
  );
  assert.equal(model.currentOrder, 1);
  assert.equal(model.completed, 0);
  assert.equal(model.elapsedSeconds, 42);
  assert.equal(model.estimateExceeded, false);
  assert.doesNotMatch(JSON.stringify(model), /percent/);
});

test('onboarding keeps an earlier pending step current while a later step is blocked', () => {
  const model = onboardingRunProgress({
    workStatus: 'running',
    plannedStages: [
      { order: 1, owner: 'Business Assistant' },
      { order: 2, owner: 'Review Assistant' },
    ],
    progress: {
      available: true,
      stages: [
        {
          stage_order: 1,
          agent_name: 'Business Assistant',
          status: 'pending',
          source: 'aion_team_task',
        },
        {
          stage_order: 2,
          agent_name: 'Review Assistant',
          status: 'blocked',
          source: 'aion_team_task',
        },
      ],
    },
  });

  assert.equal(model.currentOrder, 1);
  assert.deepEqual(model.stages.map(({ order, status }) => ({ order, status })), [
    { order: 1, status: 'pending' },
    { order: 2, status: 'blocked' },
  ]);
});

test('onboarding progress reports slow and unavailable states without inventing failure', () => {
  const model = onboardingRunProgress({
    workStatus: 'running',
    plannedStages: [
      { order: 1, owner: 'Writer' },
      { order: 2, owner: 'Verifier' },
    ],
    progress: {
      available: false,
      active_members: [
        { agent_name: 'Writer', state: 'running', slow: true },
      ],
      stages: [],
    },
    startedAt: '2026-07-24T12:00:00.000Z',
    estimateMinutes: 1,
    nowMs: Date.parse('2026-07-24T12:02:00.000Z'),
  });

  assert.equal(model.available, false);
  assert.equal(model.observed, false);
  assert.equal(model.slow, true);
  assert.equal(model.estimateExceeded, true);
  assert.equal(model.currentOrder, 1);
  assert.equal(model.stages.every((stage) => stage.status === 'not_started'), true);
});

test('stage progress reports evidence without claiming business completion', () => {
  const stages = [
    { stage_order: 1, status: 'completed', source: 'aion_team_task' },
    { stage_order: 2, status: 'running', source: 'aion_team_task' },
    { stage_order: 3, status: 'not_started', source: 'unobserved' },
  ];
  assert.deepEqual(stageProgressSummary(stages), {
    observed: true,
    observedCount: 2,
    completed: 1,
    total: 3,
    activeOrder: 2,
  });
  assert.deepEqual(stageProgressPresentation('running', 'awaiting_input'), {
    label: '等待你的信息',
    tone: 'attention',
  });
  assert.deepEqual(stageProgressPresentation('completed', 'completed_unverified'), {
    label: 'Agent 已上报完成',
    tone: 'success',
  });
  assert.doesNotMatch(JSON.stringify(stageProgressSummary(stages)), /percent|business|verified/);
});

test('task run controls keep stable start, pause, and end positions', () => {
  const running = executionControlPresentation('running');
  assert.equal(running.visible, true);
  assert.deepEqual(running.start, { enabled: false, pending: false, label: '已开始' });
  assert.deepEqual(running.pause, { enabled: true, pending: false, label: '暂停' });
  assert.deepEqual(running.stop, { enabled: true, pending: false, label: '结束' });

  const paused = executionControlPresentation('paused');
  assert.deepEqual(paused.start, { enabled: true, pending: false, label: '继续' });
  assert.deepEqual(paused.pause, { enabled: false, pending: false, label: '已暂停' });
  assert.equal(paused.stop.enabled, true);

  const gated = executionControlPresentation('awaiting_approval');
  assert.equal(gated.start.enabled, false);
  assert.equal(gated.pause.enabled, false);
  assert.equal(gated.stop.enabled, true);

  assert.deepEqual(executionControlPresentation('pause_requested').pause, {
    enabled: false,
    pending: true,
    label: '暂停中',
  });
  assert.deepEqual(executionControlPresentation('resuming').start, {
    enabled: false,
    pending: true,
    label: '继续中',
  });
  assert.deepEqual(executionControlPresentation('cancel_requested').stop, {
    enabled: false,
    pending: true,
    label: '结束中',
  });
  assert.equal(executionControlPresentation('completed_unverified').visible, false);
});
