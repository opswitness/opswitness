import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const hub = readFileSync(new URL('../src/knowledge-hub.tsx', import.meta.url), 'utf8');
const api = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');
const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');

test('Knowledge Hub keeps intake, documents, cards, collections, and export together', () => {
  for (const tab of ['收件箱', '资料', '知识卡', '资料库', '导出']) {
    assert.match(hub, new RegExp(`'${tab}'`));
  }
  assert.match(app, /<KnowledgeHubView/);
  assert.match(hub, /webkitdirectory/);
  assert.match(hub, /webkitGetAsEntry/);
  assert.match(hub, /walkDroppedEntry/);
  assert.match(hub, /一次性快照，不持续监控原目录；绝对路径不会保存。/);
});

test('library import streams bytes and requires the exact manifest before commit', () => {
  assert.match(api, /Content-Type': 'application\/octet-stream'/);
  assert.match(api, /method: 'PUT'/);
  assert.match(api, /confirmed_manifest_sha256: confirmedManifestSha256/);
  assert.match(api, /confirmed: true/);
  assert.match(hub, /正在计算 SHA-256/);
  assert.match(hub, /确认清单并入库/);
});

test('knowledge cards require provider disclosure and a separate human decision', () => {
  assert.match(hub, /confirmed_source_disclosure: true/);
  assert.match(hub, /我确认将所选资料的/);
  assert.match(hub, /批准入库/);
  assert.match(hub, /不采用/);
  assert.match(hub, /撤销批准/);
});

test('semantic search is opt-in local-only and fallback stays explicit', () => {
  assert.match(hub, /确认下载并启用/);
  assert.match(hub, /不会把资料发送给远程 embedding/);
  assert.match(hub, /已明确降级为仅全文搜索；没有调用远程 embedding/);
  assert.match(api, /\/api\/v1\/library\/semantic-model\/download/);
});

test('library Work creation remains review-first and H5 warns about static sharing', () => {
  assert.match(hub, /创建待审 Work/);
  assert.match(hub, /confirmed_context_packet: true/);
  assert.match(hub, /Treat search relevance as discovery, not proof/);
  assert.match(hub, /静态文件分享后无法远程撤回、到期或执行 RBAC/);
  assert.doesNotMatch(hub, /auto.?run/i);
});
