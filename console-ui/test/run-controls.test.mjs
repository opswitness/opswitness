import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const apiSource = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');
const typesSource = readFileSync(new URL('../src/types.ts', import.meta.url), 'utf8');
const executionView = appSource.match(/function ExecutionView\([\s\S]*?function StatusBadge/);

test('run controls use a confirmed, structured API request', () => {
  assert.match(apiSource, /\/plans\/\$\{encodeURIComponent\(planId\)\}\/control/);
  assert.match(apiSource, /body: JSON\.stringify\(\{ action, confirmed: true \}\)/);
});

test('only Aion team executions expose pause, continue, and terminate controls', () => {
  assert.ok(executionView);
  assert.match(executionView[0], /execution\?\.kind === 'aion_team'/);
  assert.match(executionView[0], /runControl\('pause'\)/);
  assert.match(executionView[0], /runControl\('resume'\)/);
  assert.match(executionView[0], /runControl\('terminate'\)/);
  assert.match(executionView[0], /role="group" aria-label=\{t\('任务运行控制'\)\}/);
  assert.match(executionView[0], /controlPresentation\.start/);
  assert.match(executionView[0], /controlPresentation\.pause/);
  assert.match(executionView[0], /controlPresentation\.stop/);
  assert.match(executionView[0], /终止此任务？/);
  assert.match(executionView[0], /已产生的部分交付物与审计证据会保留，但不会被视为业务完成/);
});

test('pending controls stay explicit until runtime confirmation', () => {
  assert.ok(executionView);
  assert.match(executionView[0], /record\.status === 'pause_requested'/);
  assert.match(executionView[0], /record\.status === 'cancel_requested'/);
  assert.match(executionView[0], /只有运行时确认停止后才会显示为已终止/);
  assert.match(executionView[0], /execution\?\.control_error/);
});

test('active Work exposes an audited future-call Auto mode switch', () => {
  assert.ok(executionView);
  assert.match(apiSource, /\/plans\/\$\{encodeURIComponent\(planId\)\}\/approval-mode/);
  assert.match(apiSource, /expected_current_mode: expectedCurrentMode/);
  assert.match(apiSource, /confirmed: true/);
  assert.match(executionView[0], /execution\?\.approval_mode/);
  assert.match(executionView[0], /role="switch"/);
  assert.match(executionView[0], /updateApprovalMode\('manual_all'\)/);
  assert.match(executionView[0], /updateApprovalMode\('automatic'\)/);
  assert.match(executionView[0], /打开 Auto 模式？/);
  assert.match(executionView[0], /当前已经暂停的审批不会被自动放行/);
  assert.match(executionView[0], /方案和方案哈希都不会改变/);
  assert.match(typesSource, /task_approval_mode_change_requested/);
  assert.match(typesSource, /task_approval_mode_change_aborted/);
  assert.match(appSource, /task_approval_mode_change_recovered: '审批模式已安全恢复'/);
});
