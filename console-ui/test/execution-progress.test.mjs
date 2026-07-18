import assert from 'node:assert/strict';
import test from 'node:test';

import {
  executionControlPresentation,
  formatExecutionElapsed,
  runtimeActivitySource,
  runtimeActivityTone,
  stageProgressPresentation,
  stageProgressSummary,
} from '../src/execution-progress.js';

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
