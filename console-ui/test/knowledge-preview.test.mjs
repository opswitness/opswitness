import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const apiSource = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');

test('runtime input attachments are fetched through request-bound encoded routes', () => {
  assert.match(apiSource, /getRuntimeInputArtifacts/);
  assert.match(apiSource, /getRuntimeInputArtifact/);
  assert.match(
    apiSource,
    /input-requests\/\$\{encodeURIComponent\(requestId\)\}\/artifacts\/\$\{encodeURIComponent\(artifactName\)\}/,
  );
});

test('the Work input card opens an inline read-only knowledge base preview', () => {
  assert.match(appSource, /function KnowledgeBasePreviewDialog/);
  assert.match(appSource, /className="runtime-input-artifact-button"/);
  assert.match(appSource, /t\('查看知识库'\)/);
  assert.match(appSource, /t\('只读预览不代表批准或审签'\)/);
  assert.match(appSource, /preview\.sha256/);
  assert.match(appSource, /document\.excerpts/);
  assert.match(appSource, /<Search size=\{15\}/);
  assert.doesNotMatch(appSource, /dangerouslySetInnerHTML/);
});

test('artifact preview failures do not disable the operator answer path', () => {
  assert.match(appSource, /setArtifactError\(t\('附件暂时无法读取'\)\)/);
  assert.match(appSource, /disabled=\{!answer\.trim\(\) \|\| submitting\}/);
});
