import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  filterTaskPresets,
  localizedTaskPreset,
  TASK_PRESET_CATEGORIES,
  TASK_PRESETS,
} from '../src/task-presets.js';

test('the built-in library contains 27 unique bilingual planning presets', () => {
  assert.equal(TASK_PRESETS.length, 27);
  assert.equal(new Set(TASK_PRESETS.map((preset) => preset.id)).size, 27);
  assert.deepEqual(
    Object.fromEntries(TASK_PRESET_CATEGORIES.map((category) => [
      category.id,
      TASK_PRESETS.filter((preset) => preset.category === category.id).length,
    ])),
    { operate: 7, decide: 6, grow: 6, serve: 4, specialist: 4 },
  );

  for (const preset of TASK_PRESETS) {
    for (const language of ['en', 'zh']) {
      assert.ok(preset.title[language].trim());
      assert.ok(preset.description[language].length >= 12);
      assert.ok(preset.objective[language].length >= 100);
    }
    assert.match(preset.objective.en, /\b(do not|never|require)\b/i);
    assert.match(preset.objective.zh, /(不要|不得|未经|必须|绝不)/);
  }
});

test('preset search is bilingual, category-aware, and local to authored catalog text', () => {
  assert.deepEqual(
    filterTaskPresets('en', 'all', 'spreadsheet').map((preset) => preset.id),
    ['spreadsheet-data-analysis'],
  );
  assert.deepEqual(
    filterTaskPresets('zh', 'all', '招聘').map((preset) => preset.id),
    ['hiring-scorecard-interview-kit', 'competitor-watch'],
  );
  assert.deepEqual(
    filterTaskPresets('zh', 'operate', '招聘').map((preset) => preset.id),
    ['hiring-scorecard-interview-kit'],
  );
  assert.deepEqual(
    filterTaskPresets('en', 'grow', 'audit').map((preset) => preset.id),
    ['website-seo-audit'],
  );
  assert.equal(filterTaskPresets('en', 'serve', 'incident').length, 0);
});

test('the Bazi preset keeps deterministic computation, synthetic data, sign-off, and artifacts explicit', () => {
  const preset = TASK_PRESETS.find((item) => item.id === 'bazi-report-demo');
  assert.ok(preset);
  assert.match(preset.objective.en, /DEMO-001/);
  assert.match(preset.objective.en, /lunar-python/);
  assert.match(preset.objective.en, /human sign-off/);
  assert.match(preset.objective.en, /chart JSON/);
  assert.match(preset.objective.zh, /人工审签/);
  assert.match(preset.objective.zh, /不要使用真人个人信息/);
});

test('localization returns authored task text without mutating the preset catalog', () => {
  const preset = TASK_PRESETS[0];
  const localized = localizedTaskPreset(preset, 'zh');
  assert.equal(localized.title, preset.title.zh);
  assert.equal(localized.objective, preset.objective.zh);
  assert.equal(TASK_PRESETS[0].title.en, 'Inbox command center');
});

test('selecting a preset only fills the composer and does not submit planning work', () => {
  const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  const selectionHandler = appSource.match(
    /const selectPreset = useCallback\(\(preset: TaskPreset\) => \{([\s\S]*?)\}, \[language\]\);/,
  );
  assert.ok(selectionHandler);
  assert.match(selectionHandler[1], /setDraft\(localizedTaskPreset\(preset, language\)\.objective\)/);
  assert.match(selectionHandler[1], /setPresetOpen\(false\)/);
  assert.doesNotMatch(selectionHandler[1], /onPlan|submit|confirm/);
});
