import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildResultSummary,
  selectResultPreviewArtifacts,
} from '../src/result-summary.js';

const registered = (name, overrides = {}) => ({
  name,
  available: true,
  preview_supported: name.endsWith('.json'),
  evidence_status: 'registered',
  mime: name.endsWith('.pdf') ? 'application/pdf' : 'application/json',
  ...overrides,
});

test('buildResultSummary presents structured facts, conclusions, checks, and the report', () => {
  const artifacts = [
    registered('demo-chart.json'),
    registered('demo-interpretation.json'),
    registered('citation-audit.json'),
    registered('report.pdf'),
    registered('signoff-sheet-signed.md', { preview_supported: false, mime: 'text/markdown' }),
  ];
  const previews = [
    {
      ...artifacts[0],
      content: {
        customer_id: 'DEMO-001',
        synthetic: true,
        day_master_gan: '戊',
        four_pillars: {
          year: { ganzhi: '己卯' },
          month: { ganzhi: '丙子' },
          day: { ganzhi: '戊午' },
          time: { ganzhi: '戊午' },
        },
        engine: { library: 'lunar-python', version: '1.4.8' },
      },
    },
    {
      ...artifacts[1],
      content: {
        interpretations: [
          { id: 'INT-01', title: '结构', statement: '这是第一条可读结论。' },
          { id: 'INT-02', title: '边界', statement: '这是第二条可读结论。' },
        ],
        consistency_check: { passed: true, mismatches: [] },
      },
    },
    {
      ...artifacts[2],
      content: {
        artifact_type: 'citation_audit',
        summary: {
          total_interpretations: 11,
          traceable: 11,
          overall_verdict: 'pass',
        },
      },
    },
  ];

  const summary = buildResultSummary(previews, artifacts);
  assert.deepEqual(summary.facts, [
    { kind: 'customer', value: 'DEMO-001' },
    { kind: 'data_scope', value: 'synthetic' },
    { kind: 'four_pillars', value: '己卯 · 丙子 · 戊午 · 戊午' },
    { kind: 'day_master', value: '戊' },
    { kind: 'engine', value: 'lunar-python 1.4.8' },
  ]);
  assert.equal(summary.conclusions.length, 2);
  assert.equal(summary.report?.name, 'report.pdf');
  assert.deepEqual(summary.checks.map((check) => [check.kind, check.state, check.detail]), [
    ['consistency', 'pass', '0'],
    ['audit', 'pass', '11/11'],
    ['signoff', 'pass', 'signoff-sheet-signed.md'],
    ['evidence', 'pass', '5/5'],
  ]);
  assert.equal(summary.hasReadableSummary, true);
});

test('selectResultPreviewArtifacts prioritizes conclusions and keeps a hard request bound', () => {
  const artifacts = [
    registered('knowledge.json'),
    registered('audit.json'),
    registered('chart.json'),
    registered('interpretation.json'),
    registered('report.pdf'),
  ];
  assert.deepEqual(
    selectResultPreviewArtifacts(artifacts, 3).map((artifact) => artifact.name),
    ['interpretation.json', 'chart.json', 'audit.json'],
  );
});

test('workspace signoff and files never become verified evidence', () => {
  const artifacts = [{
    ...registered('signoff-sheet-signed.md', { preview_supported: false, mime: 'text/markdown' }),
    evidence_status: 'workspace_unverified',
  }];
  const summary = buildResultSummary([], artifacts);
  assert.deepEqual(summary.checks, [
    { kind: 'signoff', state: 'attention', detail: 'signoff-sheet-signed.md' },
    { kind: 'evidence', state: 'attention', detail: '0/1' },
  ]);
  assert.equal(summary.report, null);
  assert.equal(summary.hasReadableSummary, false);
});
