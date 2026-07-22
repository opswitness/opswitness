import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const styleSource = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');

test('Workspace groups reusable assets under one library heading', () => {
  assert.match(appSource, /workspace-library-title/);
  assert.match(appSource, /复用模板、团队与已批准记忆/);
  assert.match(appSource, /workspace-library-grid/);
  assert.match(appSource, /浏览 31 个常用任务/);
  assert.match(appSource, /我的任务模板/);
  assert.match(appSource, /团队蓝图/);
  assert.match(appSource, /Workspace 记忆/);
});

test('Workspace library uses a desktop grid and collapses on narrow screens', () => {
  assert.match(styleSource, /\.workspace-library-grid\s*\{[\s\S]*?grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(styleSource, /@media \(max-width: 820px\)[\s\S]*?\.workspace-library-grid\s*\{[\s\S]*?grid-template-columns:\s*1fr/);
});
