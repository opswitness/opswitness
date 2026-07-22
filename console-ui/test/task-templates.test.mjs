import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const apiSource = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');

test('the workspace keeps common tasks, personal templates, and team blueprints together', () => {
  const commonIndex = appSource.indexOf("t('浏览 31 个常用任务')");
  const personalIndex = appSource.indexOf("t('我的任务模板')", commonIndex);
  const blueprintIndex = appSource.indexOf("t('团队蓝图')", personalIndex);
  assert.ok(commonIndex >= 0);
  assert.ok(personalIndex > commonIndex);
  assert.ok(blueprintIndex > personalIndex);
  assert.match(appSource, /taskTemplates\.length/);
  assert.match(appSource, /blueprints\.length/);
});

test('selecting a personal template only fills the composer', () => {
  const handler = appSource.match(
    /const selectTaskTemplate = useCallback\(\(template: TaskTemplate\) => \{([\s\S]*?)\}, \[\]\);/,
  );
  assert.ok(handler);
  assert.match(handler[1], /setDraft\(template\.objective\)/);
  assert.match(handler[1], /setTemplateOpen\(false\)/);
  assert.doesNotMatch(handler[1], /onPlan|submit/);
});

test('personal template writes carry confirmation and use archive deletion', () => {
  assert.match(
    apiSource,
    /saveTaskTemplate[\s\S]*JSON\.stringify\(\{ name, objective, confirmed: true \}\)/,
  );
  assert.match(
    apiSource,
    /archiveTaskTemplate[\s\S]*\/archive[\s\S]*JSON\.stringify\(\{ confirmed: true \}\)/,
  );
  assert.match(appSource, /archiveTarget === template\.template_id/);
});
