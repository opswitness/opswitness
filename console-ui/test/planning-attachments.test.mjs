import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const apiSource = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');
const typeSource = readFileSync(new URL('../src/types.ts', import.meta.url), 'utf8');

test('Workspace attaches bounded materials to the planning request', () => {
  assert.match(typeSource, /export type PlanningAttachmentUpload/);
  assert.match(typeSource, /export type PlanningAttachment/);
  assert.match(apiSource, /attachments\?: PlanningAttachmentUpload\[\]/);
  assert.match(appSource, /PLANNING_ATTACHMENT_MAX_FILES = 5/);
  assert.match(appSource, /PLANNING_ATTACHMENT_MAX_FILE_BYTES = 5 \* 1024 \* 1024/);
  assert.match(appSource, /PLANNING_ATTACHMENT_MAX_TOTAL_BYTES = 15 \* 1024 \* 1024/);
  assert.match(appSource, /type="file"/);
  assert.match(appSource, /multiple/);
  assert.match(appSource, /attachments: encodedAttachments/);
});

test('selected materials can be reviewed and removed before planning', () => {
  assert.match(appSource, /planning-attachment-list/);
  assert.match(appSource, /setPlanningAttachments\(\(files\) => files\.filter/);
  assert.match(appSource, /文件内容会发送给当前规划模型/);
  assert.match(appSource, /请勿上传密码、API key 或未授权资料/);
  assert.match(appSource, /\(record\.attachments\?\.length \?\? 0\) > 0/);
  assert.match(appSource, /attachment\.sha256\.slice\(0, 10\)/);
});

test('attachment selection never confirms or starts execution', () => {
  const selectionStart = appSource.indexOf('const selectPlanningAttachments');
  assert.notEqual(selectionStart, -1);
  const selectionEnd = appSource.indexOf('\n  const ', selectionStart + 1);
  const selectionBody = appSource.slice(
    selectionStart,
    selectionEnd === -1 ? undefined : selectionEnd,
  );
  assert.match(selectionBody, /setPlanningAttachments\(next\)/);
  assert.doesNotMatch(selectionBody, /onConfirm|confirmPlan|onControl|execute/);
});
