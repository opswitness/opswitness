import assert from 'node:assert/strict';
import test from 'node:test';

import {
  currentWorkItem,
  latestWorkItems,
  shouldPollWork,
  workRunHistory,
} from '../src/work-selection.js';

const parent = { plan_id: 'parent', parent_plan_id: null, status: 'ready' };
const revision = { plan_id: 'revision', parent_plan_id: 'parent', status: 'awaiting_approval' };
const other = { plan_id: 'other', parent_plan_id: null, status: 'completed_unverified' };
const fork = {
  plan_id: 'fork',
  parent_plan_id: null,
  forked_from_plan_id: 'parent',
  status: 'ready',
};

test('work selection keeps only the latest revision and honors focus', () => {
  assert.deepEqual(latestWorkItems([parent, revision, other]), [revision, other]);
  assert.equal(currentWorkItem([parent, revision, other], 'revision'), revision);
  assert.equal(currentWorkItem([parent, revision, other], ''), revision);
});

test('a fork remains an independent Work instead of collapsing into its source', () => {
  assert.deepEqual(latestWorkItems([parent, revision, other, fork]), [revision, other, fork]);
  assert.equal(currentWorkItem([parent, revision, other, fork], 'fork'), fork);
});

test('only active work in the Work view receives a detail poll', () => {
  assert.equal(shouldPollWork('work', revision), true);
  assert.equal(
    shouldPollWork('work', { plan_id: 'question', status: 'awaiting_input' }),
    true,
  );
  assert.equal(shouldPollWork('work', { plan_id: 'pausing', status: 'pause_requested' }), true);
  assert.equal(shouldPollWork('work', { plan_id: 'paused', status: 'paused' }), false);
  assert.equal(shouldPollWork('work', { plan_id: 'stopping', status: 'cancel_requested' }), true);
  assert.equal(shouldPollWork('today', revision), false);
  assert.equal(shouldPollWork('work', other), false);
  assert.equal(shouldPollWork('work', null), false);
});

test('run history follows the selected immutable work chain newest first', () => {
  const taskRuns = [
    { plan_id: 'parent', parent_plan_id: null, revision_number: 1 },
    { plan_id: 'revision', parent_plan_id: 'parent', revision_number: 2 },
    { plan_id: 'other', parent_plan_id: null, revision_number: 1 },
  ];
  assert.deepEqual(workRunHistory(revision, taskRuns), [taskRuns[1], taskRuns[0]]);
  assert.deepEqual(workRunHistory(other, taskRuns), [taskRuns[2]]);
  assert.deepEqual(workRunHistory(null, taskRuns), []);
});

test('erased plan shells preserve lineage without appearing as Work or History rows', () => {
  const erasedRevision = {
    plan_id: 'erased-revision',
    parent_plan_id: 'parent',
    status: 'completed_unverified',
    erased_at: '2026-07-22T12:00:00Z',
  };
  const newest = {
    plan_id: 'newest',
    parent_plan_id: 'erased-revision',
    status: 'completed_unverified',
  };
  assert.deepEqual(latestWorkItems([parent, erasedRevision, newest, other]), [newest, other]);

  const taskRuns = [
    { plan_id: 'parent', parent_plan_id: null, revision_number: 1 },
    {
      plan_id: 'erased-revision',
      parent_plan_id: 'parent',
      revision_number: 2,
      deleted: true,
    },
    { plan_id: 'newest', parent_plan_id: 'erased-revision', revision_number: 3 },
  ];
  assert.deepEqual(workRunHistory(newest, taskRuns), [taskRuns[2], taskRuns[0]]);
});

test('erasing the latest revision reveals the newest retained parent Work', () => {
  const erasedLatest = {
    plan_id: 'revision',
    parent_plan_id: 'parent',
    status: 'completed_unverified',
    erased_at: '2026-07-22T12:00:00Z',
  };
  assert.deepEqual(latestWorkItems([parent, erasedLatest, other]), [parent, other]);
});
