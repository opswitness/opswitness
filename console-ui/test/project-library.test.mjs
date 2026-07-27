import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  projectLibrarySourceLabel,
  projectLibraryVersionCandidates,
  splitProjectLibraryTags,
} from '../src/project-library-model.js';

const base = {
  asset_id: 'a',
  name: 'reply.json',
  file_type: 'json',
  work_id: 'work-1',
  revision_number: 2,
  created_at: '2026-07-24T12:00:00Z',
  source_kind: 'registered_output',
};
const librarySource = readFileSync(
  new URL('../src/project-library.tsx', import.meta.url),
  'utf8',
);
const typeSource = readFileSync(new URL('../src/types.ts', import.meta.url), 'utf8');

test('version candidates stay same-type, prefer the same Work, and exclude self', () => {
  const candidates = projectLibraryVersionCandidates([
    base,
    { ...base, asset_id: 'b', revision_number: 1 },
    { ...base, asset_id: 'c', name: 'other.json', work_id: 'work-2', revision_number: 4 },
    { ...base, asset_id: 'd', file_type: 'pdf' },
  ], base);
  assert.deepEqual(candidates.map((item) => item.asset_id), ['b', 'c']);
});

test('user tags normalize delimiters and duplicate spellings', () => {
  assert.deepEqual(
    splitProjectLibraryTags(' 客户, 待复核，客户 , FINAL, final '),
    ['客户', '待复核', 'FINAL'],
  );
});

test('source labels keep unregistered workspace outputs explicit', () => {
  assert.equal(projectLibrarySourceLabel(base), '已登记产物');
  assert.equal(
    projectLibrarySourceLabel({ ...base, source_kind: 'workspace_output' }),
    '运行目录产物 · 未登记',
  );
});

test('Project Library has a dedicated file view without replacing Workspace templates', () => {
  const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  const hub = readFileSync(new URL('../src/knowledge-hub.tsx', import.meta.url), 'utf8');
  assert.match(app, /id: 'files'.*label: '项目资料库'/);
  assert.match(app, /view === 'files'.*<KnowledgeHubView/s);
  assert.match(hub, /<EvidenceProjectLibraryView \/>/);
  assert.match(app, /function LibraryView\(/);
});

test('unavailable version predecessors remain explicit instead of breaking the library', () => {
  assert.match(
    typeSource,
    /supersedes_status: 'none' \| 'available' \| 'unavailable'/,
  );
  assert.match(librarySource, /selected\.supersedes_status === 'unavailable'/);
  assert.match(librarySource, /前一版本已不可用/);
});
