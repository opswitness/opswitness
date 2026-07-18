import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  DEFAULT_UI_LANGUAGE,
  resolveUiLanguage,
  translateApiError,
  translateUi,
  UI_LANGUAGE_STORAGE_KEY,
} from '../src/i18n.js';

test('English is the fail-closed default for absent or invalid preferences', () => {
  assert.equal(DEFAULT_UI_LANGUAGE, 'en');
  assert.equal(UI_LANGUAGE_STORAGE_KEY, 'quarterdeck.ui-language');
  assert.equal(resolveUiLanguage(null), 'en');
  assert.equal(resolveUiLanguage('fr'), 'en');
  assert.equal(resolveUiLanguage('zh'), 'zh');
});

test('stable API error codes render in the selected interface language', () => {
  const fallback = 'origin denied';
  assert.equal(
    translateApiError('en', 'origin_denied', fallback),
    'This console address is not authorized. Reopen Quarterdeck from the local address or the paired private HTTPS address.',
  );
  assert.equal(
    translateApiError('zh', 'origin_denied', fallback),
    '当前工作台地址未获授权。请从本机地址或已配对的私网 HTTPS 地址重新打开 Quarterdeck。',
  );
  assert.equal(translateApiError('en', 'unknown_code', fallback), fallback);
});

test('translations interpolate values without changing authored task content', () => {
  assert.equal(translateUi('en', '新建任务'), 'New task');
  assert.equal(translateUi('en', '工作'), 'Work');
  assert.equal(translateUi('en', '资源库'), 'Library');
  assert.equal(translateUi('zh', '新建任务'), '新建任务');
  assert.equal(
    translateUi('en', '{agents} 名员工 · {levels} 层汇报关系 · {loops} 个循环', {
      agents: 3,
      levels: 2,
      loops: 1,
    }),
    '3 agents · 2 reporting levels · 1 loops',
  );
  assert.equal(translateUi('en', '用户原始任务正文'), '用户原始任务正文');
});

test('every directly localized Chinese UI literal has an English translation', () => {
  const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  const sources = [...appSource.matchAll(/\bt\('([^'\n]*[\u3400-\u9fff][^'\n]*)'/g)]
    .map((match) => match[1]);
  const missing = [...new Set(sources)].filter((source) => translateUi('en', source) === source);
  assert.deepEqual(missing, []);
});
