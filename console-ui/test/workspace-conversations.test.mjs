import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const apiSource = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');
const typeSource = readFileSync(new URL('../src/types.ts', import.meta.url), 'utf8');
const styleSource = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');

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

test('failed planning is edited as an immutable retry in the current conversation', () => {
  const retryStart = apiSource.indexOf('export function retryFailedPlanning');
  assert.notEqual(retryStart, -1);
  const retryEnd = apiSource.indexOf('\nexport function ', retryStart + 1);
  const retryBody = apiSource.slice(retryStart, retryEnd === -1 ? undefined : retryEnd);
  assert.match(
    retryBody,
    /plans\/\$\{encodeURIComponent\(planId\)\}\/planning-retries/,
  );
  assert.match(retryBody, /JSON\.stringify\(\{ objective, confirmed: true \}\)/);
  assert.doesNotMatch(retryBody, /requestPlan|confirmPlan|dispatch/);

  assert.match(typeSource, /planning_retry_source_plan_id\?: string \| null/);
  assert.match(typeSource, /planning_retry_source_request_sha256\?: string \| null/);
  assert.match(appSource, /record\.status === 'failed'/);
  assert.match(appSource, /!record\.plan/);
  assert.match(appSource, /!record\.plan_sha256/);
  assert.match(appSource, /!record\.execution/);
  assert.match(appSource, /setDraft\(record\.objective\)/);
  assert.match(appSource, /await onRetryFailedPlanning\(record, objective\)/);
  assert.match(appSource, /重试会保留失败记录，并在当前对话创建新的不可变版本/);
  assert.match(appSource, /if \(record \|\| objective\.length < 3 \|\| submitting \|\| locked\) return/);
});

test('active Workspace loads and renders the complete ordered conversation before the current turn', () => {
  const entriesStart = apiSource.indexOf('export function getWorkspaceConversationEntries');
  assert.notEqual(entriesStart, -1);
  const entriesEnd = apiSource.indexOf('\nexport function ', entriesStart + 1);
  const entriesBody = apiSource.slice(
    entriesStart,
    entriesEnd === -1 ? undefined : entriesEnd,
  );
  assert.match(
    entriesBody,
    /workspace-conversations\/\$\{encodeURIComponent\(planId\)\}\/entries/,
  );
  assert.doesNotMatch(entriesBody, /method: 'POST'|confirmed/);

  assert.match(appSource, /onLoadWorkspaceConversationEntries\(record\.plan_id\)/);
  assert.match(appSource, /\.filter\(\(entry\) => entry\.plan_id !== record\?\.plan_id\)/);
  assert.match(appSource, /left\.revision_number - right\.revision_number/);
  assert.match(appSource, /<WorkspaceConversationHistoryEntry/);
  assert.match(appSource, /<ol className="workspace-history-list">/);
  assert.match(appSource, /完整对话历史/);
  assert.match(appSource, /向上滚动查看/);
  assert.match(appSource, /className="chat-assistant-content" aria-live="polite"/);
});

test('Workspace history scrolling follows the tail only while the operator remains near it', () => {
  assert.match(appSource, /const threadRef = useRef<HTMLDivElement \| null>\(null\)/);
  assert.match(appSource, /const followingTailRef = useRef\(true\)/);
  assert.match(
    appSource,
    /thread\.scrollHeight - thread\.scrollTop - thread\.clientHeight/,
  );
  assert.match(appSource, /followingTailRef\.current = distanceFromBottom < 96/);
  assert.match(appSource, /if \(!thread \|\| !followingTailRef\.current\) return/);
  assert.match(appSource, /thread\.scrollTop = thread\.scrollHeight/);
  assert.match(
    appSource,
    /\[historicalEntries\.length, record\?\.plan_id\]/,
  );

  const threadRule = styleSource.match(/\.chat-thread \{[\s\S]*?\n\}/);
  assert.ok(threadRule);
  assert.match(threadRule[0], /overflow-y: auto/);
  assert.match(threadRule[0], /overscroll-behavior-y: contain/);
  assert.match(threadRule[0], /scrollbar-gutter: stable/);
  assert.match(styleSource, /\.workspace-conversation-history \{/);
  assert.match(styleSource, /\.workspace-history-list \{/);
  assert.match(styleSource, /\.failed-planning-retry-note \{/);
});
