import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  canSaveRuntimeRevision,
  homeActionView,
  observationPresentation,
  selectedBlueprintId,
  taskAdjustmentExamples,
} from '../src/home-routing.js';

test('the original chat workspace remains the default route', () => {
  const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  assert.match(appSource, /useState<View>\('workspace'\)/);
  assert.doesNotMatch(appSource, /initialConsoleView/);
});

test('home actions route to product views without exposing adapter routes', () => {
  assert.equal(homeActionView('approvals'), 'approvals');
  assert.equal(homeActionView('today'), 'workspace');
  assert.equal(homeActionView('connections'), 'settings');
  assert.equal(homeActionView('history'), 'settings');
  assert.equal(homeActionView('tasks'), 'work');
  assert.equal(homeActionView('team'), 'work');
});

test('top-level navigation preserves Workspace, merges tasks and teams, and keeps Library inside Workspace', () => {
  const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  const sidebar = appSource.match(/function Sidebar\([\s\S]*?const items = \[([\s\S]*?)\n  \];/);
  assert.ok(sidebar);
  assert.match(sidebar[1], /id: 'workspace'/);
  assert.match(sidebar[1], /id: 'work'/);
  assert.doesNotMatch(sidebar[1], /id: 'today'/);
  assert.doesNotMatch(sidebar[1], /id: 'library'/);
  assert.doesNotMatch(sidebar[1], /id: 'history'/);
  assert.doesNotMatch(sidebar[1], /id: 'tasks'/);
  assert.doesNotMatch(sidebar[1], /id: 'team'/);
  assert.match(appSource, /type WorkTab = 'overview' \| 'history' \| 'settings'/);
  const workTabs = appSource.match(/const tabs: Array<\{ id: WorkTab; label: string \}> = \[([\s\S]*?)\n  \];/);
  assert.ok(workTabs);
  assert.doesNotMatch(workTabs[1], /id: 'team'/);
  assert.doesNotMatch(workTabs[1], /id: 'activity'/);
  assert.doesNotMatch(workTabs[1], /id: 'outputs'/);
  const overview = appSource.match(/\{tab === 'overview'[\s\S]*?\{tab === 'history'/);
  assert.ok(overview);
  assert.match(overview[0], /work-overview-team/);
  assert.match(overview[0], /<OrganizationChart/);
  assert.match(overview[0], /<TaskAdjustmentChat/);
  assert.match(overview[0], /<RuntimeAssignments/);
  assert.match(appSource, /tab === 'history'/);
  assert.match(appSource, /<SystemAutomationHistory runs=\{data\.recent_runs\} \/>/);
});

test('member status stays evidence-only and never becomes an outcome claim', () => {
  assert.deepEqual(observationPresentation('activity_observed'), { label: 'Activity observed', tone: 'active' });
  assert.deepEqual(observationPresentation('response_observed'), { label: 'Response observed', tone: 'active' });
  assert.deepEqual(observationPresentation('unobserved'), { label: 'Not observed', tone: 'neutral' });
  assert.deepEqual(observationPresentation('unavailable'), { label: 'Status unavailable', tone: 'danger' });
  assert.deepEqual(observationPresentation('activity_observed', 'zh'), { label: '活动已观测', tone: 'active' });
});

test('approval-waiting work resolves its exact task-bound decision inline', () => {
  const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  const executionView = appSource.match(/function ExecutionView\([\s\S]*?function StatusBadge/);
  assert.ok(executionView);
  assert.match(executionView[0], /record\.status === 'awaiting_approval'/);
  assert.match(executionView[0], /approval\.plan_id === record\.plan_id/);
  assert.match(executionView[0], /InlineApprovalPanel/);
  assert.match(executionView[0], /onDecideApproval/);
  assert.doesNotMatch(executionView[0], /onOpenApprovals/);
  assert.doesNotMatch(executionView[0], /查看审批/);
  assert.doesNotMatch(executionView[0], /allow_always/);
  assert.match(appSource, /function ApprovalsView/);
});

test('new confirmations default to uninterrupted Auto with manual approval opt-in', () => {
  const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  const apiSource = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');
  const typeSource = readFileSync(new URL('../src/types.ts', import.meta.url), 'utf8');
  assert.match(typeSource, /'automatic' \| 'automatic_safe' \| 'manual_all'/);
  assert.match(apiSource, /approvalMode: ApprovalMode = 'automatic'/);
  assert.match(appSource, /useState<ApprovalMode>\('automatic'\)/);
  assert.match(appSource, /event\.target\.checked \? 'manual_all' : 'automatic'/);
  assert.match(appSource, /任务确认后，执行工具会自动单次放行并保留完整审计记录/);
});

test('ended work exposes a review-first rerun action', () => {
  const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  const workView = appSource.match(/function WorkView\([\s\S]*?function SystemAutomationHistory/);
  assert.ok(workView);
  assert.match(workView[0], /\['failed', 'cancelled', 'completed_unverified'\]\.includes/);
  assert.match(workView[0], /onRerun/);
  assert.match(workView[0], /重新运行/);
  assert.match(appSource, /preparePlanRerun/);
});

test('Work history continues an exact ended Aion run as a new audited version', () => {
  const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  const apiSource = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');
  const typeSource = readFileSync(new URL('../src/types.ts', import.meta.url), 'utf8');
  const workView = appSource.match(/function WorkView\([\s\S]*?function LibraryView/);
  assert.ok(workView);
  assert.match(workView[0], /workRunHistory/);
  assert.match(workView[0], /continuation_available/);
  assert.match(workView[0], /继续和这次运行交互/);
  assert.match(workView[0], /onContinueRun/);
  assert.match(apiSource, /\/plans\/\$\{encodeURIComponent\(planId\)\}\/continue/);
  assert.match(apiSource, /confirmed: true/);
  assert.match(typeSource, /continuation_message_sha256/);
  assert.match(typeSource, /continuation_available: boolean/);
});

test('reviewed work exposes an explicit independent fork flow', () => {
  const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  const apiSource = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');
  const typeSource = readFileSync(new URL('../src/types.ts', import.meta.url), 'utf8');
  const workView = appSource.match(/function WorkView\([\s\S]*?function LibraryView/);
  assert.ok(workView);
  assert.match(workView[0], /onFork/);
  assert.match(workView[0], /创建工作副本/);
  assert.match(workView[0], /创建独立工作副本/);
  assert.match(workView[0], /forked_from_plan_id/);
  assert.match(apiSource, /\/plans\/\$\{encodeURIComponent\(planId\)\}\/fork/);
  assert.match(typeSource, /forked_from_plan_sha256/);
});

test('runtime revision requires a changed, locally advertised runtime and model', () => {
  const agents = [{ name: 'lead', runtime: 'claude_code', model: null }];
  const capabilities = [
    {
      runtime: 'claude_code',
      available: true,
      default_model: 'default',
      models: [{ id: 'default' }, { id: 'claude-fable-5[1m]' }],
    },
    {
      runtime: 'codex_cli',
      available: true,
      default_model: 'default',
      models: [{ id: 'default' }, { id: 'gpt-5.6-sol' }],
    },
  ];
  assert.equal(canSaveRuntimeRevision(agents, capabilities, {
    lead: { runtime: 'claude_code', model: 'default' },
  }), false);
  assert.equal(canSaveRuntimeRevision(agents, capabilities, {
    lead: { runtime: 'claude_code', model: 'claude-fable-5[1m]' },
  }), true);
  assert.equal(canSaveRuntimeRevision(agents, capabilities, {
    lead: { runtime: 'codex_cli', model: 'gpt-5.6-sol' },
  }), true);
  assert.equal(canSaveRuntimeRevision(agents, capabilities, {
    lead: { runtime: 'codex_cli', model: 'not-advertised' },
  }), false);
  assert.equal(canSaveRuntimeRevision(
    agents,
    [{ runtime: 'codex_cli', available: false, models: [{ id: 'gpt-5.6-sol' }] }],
    { lead: { runtime: 'codex_cli', model: 'gpt-5.6-sol' } },
  ), false);
});

test('blueprint reuse submits only an opaque blueprint id', () => {
  assert.equal(selectedBlueprintId({ blueprint_id: '01KXH5WWF9KG6AMXNDH0ACM2KC', name: 'private' }), '01KXH5WWF9KG6AMXNDH0ACM2KC');
  assert.equal(selectedBlueprintId(null), null);
});

test('task adjustment chat offers a bounded loop draft without executing work', () => {
  const loop = taskAdjustmentExamples().find((item) => item.label === 'Adjust collaboration loops');
  assert.ok(loop);
  assert.match(loop.instruction, /interpretation agent/);
  assert.match(loop.instruction, /at most two rounds/);
  assert.doesNotMatch(loop.instruction, /confirm and run/i);
  assert.equal(taskAdjustmentExamples('zh')[0].label, '调整循环协作');
});
