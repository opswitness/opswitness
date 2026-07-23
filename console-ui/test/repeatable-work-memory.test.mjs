import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const apiSource = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');
const dialogSource = readFileSync(new URL('../src/workspace-memory-dialog.tsx', import.meta.url), 'utf8');
const typeSource = readFileSync(new URL('../src/types.ts', import.meta.url), 'utf8');

test('completed Work is exposed as a review-first repeatable workflow', () => {
  assert.match(typeSource, /export type RepeatableWork/);
  assert.match(typeSource, /repeatable_works: RepeatableWork\[\]/);
  assert.match(appSource, /我的可重复 Work/);
  assert.match(appSource, /preparePlanRerun\(work\.source_plan_id\)/);
  assert.match(appSource, /点击后生成待确认的新版本，不会直接执行。/);

  const preparation = appSource.match(/onPrepareRepeatableWork=\{async \(work\) => \{[\s\S]*?\}\}/)?.[0] || '';
  assert.match(preparation, /preparePlanRerun/);
  assert.doesNotMatch(preparation, /confirmPlan|dispatchPlan/);
});

test('Workspace memory writes are explicit confirmed lifecycle actions', () => {
  assert.match(apiSource, /\/api\/v1\/workspace-memory\/candidates/);
  assert.match(apiSource, /workspace-memory\/\$\{encodeURIComponent\(versionId\)\}\/approve/);
  assert.match(apiSource, /workspace-memory\/\$\{encodeURIComponent\(versionId\)\}\/revoke/);
  assert.match(apiSource, /workspace-memory\/\$\{encodeURIComponent\(versionId\)\}\/rollback/);

  for (const functionName of [
    'createWorkspaceMemoryCandidate',
    'proposeProcessMemory',
    'approveWorkspaceMemory',
    'revokeWorkspaceMemory',
    'rollbackWorkspaceMemory',
  ]) {
    const start = apiSource.indexOf(`export function ${functionName}`);
    assert.notEqual(start, -1, `${functionName} should exist`);
    const nextExport = apiSource.indexOf('\nexport function ', start + 1);
    const body = apiSource.slice(start, nextExport === -1 ? undefined : nextExport);
    assert.match(body, /confirmed: true/);
  }
});

test('memory UI keeps candidates separate from approved planning memory', () => {
  assert.match(dialogSource, /Agents can only propose candidates|Agent 只能提出候选/);
  assert.match(dialogSource, /A human must approve|必须人工批准/);
  assert.match(dialogSource, /正式记忆不会被直接覆盖/);
  assert.match(dialogSource, /回滚到此版本/);
  assert.match(dialogSource, /content_sha256/);
  assert.match(appSource, /memory_version_ids/);
  assert.match(appSource, /memory_snapshot_sha256/);
});
