import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const apiSource = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');
const styleSource = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');
const typeSource = readFileSync(new URL('../src/types.ts', import.meta.url), 'utf8');

test('Work sends every confirmed run to History and chooses its evidence view by status', () => {
  const defaultTab = appSource.match(/function defaultWorkTab[\s\S]*?\n}/);
  assert.ok(defaultTab);
  assert.match(defaultTab[0], /\['planning', 'ready'\]/);
  assert.match(defaultTab[0], /'history'/);
  const defaultHistory = appSource.match(/function defaultHistoryTab[\s\S]*?\n}/);
  assert.ok(defaultHistory);
  assert.match(defaultHistory[0], /'completed_unverified'/);
  assert.match(defaultHistory[0], /'results'/);
  assert.match(defaultHistory[0], /'process'/);
  assert.match(appSource, /onFocus\(record\.plan_id, defaultWorkTab\(record\)\)/);
  assert.doesNotMatch(appSource, /\{ id: 'outputs', label: '结果' \}/);
  assert.doesNotMatch(appSource, /\{ id: 'activity', label: '过程' \}/);
});

test('History owns Process and Results for the exact selected run version', () => {
  const history = appSource.match(/\{tab === 'history'[\s\S]*?\{tab === 'settings'/);
  assert.ok(history);
  assert.match(history[0], /historyTab === 'process'/);
  assert.match(history[0], /historyTab === 'results'/);
  assert.match(appSource, /plans\.find\(\(record\) => record\.plan_id === selectedHistoryRun\.plan_id\)/);
  assert.match(history[0], /<ExecutionView/);
  assert.match(history[0], /<ExecutionStageList/);
  assert.match(history[0], /证据时间线/);
  assert.match(history[0], /<RunArtifactsPanel record=\{selectedHistoryRecord\}/);
  assert.doesNotMatch(history[0], /<RunArtifactsPanel record=\{selected\}/);
  assert.doesNotMatch(history[0], /隐藏推理[^<]*显示/);
});

test('Historical Results fetches plan-scoped generated files and labels them unverified', () => {
  assert.match(typeSource, /export type PlanArtifact/);
  assert.match(typeSource, /evidence_status: 'workspace_unverified'/);
  assert.match(apiSource, /getPlanArtifacts/);
  assert.match(apiSource, /getPlanArtifact/);
  assert.match(
    apiSource,
    /plans\/\$\{encodeURIComponent\(planId\)\}\/artifacts\/\$\{encodeURIComponent\(artifactName\)\}/,
  );
  assert.match(appSource, /function RunArtifactsPanel/);
  assert.match(appSource, /运行目录文件 · 尚未登记为结果证据/);
  assert.match(appSource, /方案要求 PDF，但本次运行目录中未发现 PDF/);
  assert.match(appSource, /function RunArtifactPreviewDialog/);
  assert.doesNotMatch(appSource, /dangerouslySetInnerHTML/);
});

test('long Work and run status labels use their own row instead of squeezing titles', () => {
  const workSelector = styleSource.match(/\.work-selector > button \{[\s\S]*?\n\}/);
  assert.ok(workSelector);
  assert.match(workSelector[0], /grid-template-columns: minmax\(0, 1fr\)/);
  assert.doesNotMatch(workSelector[0], /minmax\(0, 1fr\) auto/);
  assert.match(
    styleSource,
    /\.work-selector > button > \.status-badge \{[\s\S]*?justify-self: start;[\s\S]*?\n\}/,
  );

  const runSelector = styleSource.match(/\.work-run-list > button \{[\s\S]*?\n\}/);
  assert.ok(runSelector);
  assert.match(runSelector[0], /grid-template-columns: 32px minmax\(0, 1fr\)/);
  assert.doesNotMatch(runSelector[0], /minmax\(0, 1fr\) auto/);
  assert.match(
    styleSource,
    /\.work-run-list > button > \.status-badge \{[\s\S]*?grid-column: 2;[\s\S]*?\n\}/,
  );
});

test('Work details provide an explicit vertical scroller without nesting one on mobile', () => {
  assert.match(
    styleSource,
    /\.work-detail \{\s*display: flex;[\s\S]*?max-height: calc\(100dvh - 118px\);[\s\S]*?\n\}/,
  );

  const detailBody = styleSource.match(/\.work-detail-body \{[\s\S]*?\n\}/);
  assert.ok(detailBody);
  assert.match(detailBody[0], /overflow-y: auto/);
  assert.match(detailBody[0], /scrollbar-gutter: stable/);

  const mobile = styleSource.match(/@media \(max-width: 760px\) \{[\s\S]*$/);
  assert.ok(mobile);
  assert.match(mobile[0], /\.work-detail \{[\s\S]*?max-height: none;[\s\S]*?overflow: visible;[\s\S]*?\n  \}/);
  assert.match(mobile[0], /\.work-detail-body \{[\s\S]*?overflow-y: visible;[\s\S]*?\n  \}/);
});
