import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const apiSource = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');
const typeSource = readFileSync(new URL('../src/types.ts', import.meta.url), 'utf8');

test('Workspace exposes immutable conversation history and restores the latest plan', () => {
  assert.match(typeSource, /export type WorkspaceConversation/);
  assert.match(typeSource, /workspace_conversations: WorkspaceConversation\[\]/);
  assert.match(appSource, /继续之前的规划/);
  assert.match(appSource, /conversation\.current_plan_id/);
  assert.match(appSource, /reviewWork\(await getPlan\(conversation\.current_plan_id\)\)/);
  assert.match(appSource, /不会自动执行/);
});

test('creating a template from history binds the exact plan and requires confirmation', () => {
  const saveStart = apiSource.indexOf('export function saveTaskTemplateFromPlan');
  assert.notEqual(saveStart, -1);
  const saveEnd = apiSource.indexOf('\nexport function ', saveStart + 1);
  const saveBody = apiSource.slice(saveStart, saveEnd === -1 ? undefined : saveEnd);
  assert.match(saveBody, /plans\/\$\{encodeURIComponent\(planId\)\}\/task-template/);
  assert.match(saveBody, /JSON\.stringify\(\{ name, confirmed: true \}\)/);
  assert.doesNotMatch(saveBody, /confirmPlan|preparePlanRerun|requestPlan/);
  assert.match(appSource, /template_source_available/);
  assert.match(appSource, /我确认将这个已审核方案保存为可复用任务模板/);
  assert.match(appSource, /current_plan_sha256/);
});
