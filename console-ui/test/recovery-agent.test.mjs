import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  formatRecoveryCooldown,
  recoveryActionPolicy,
  recoveryIdleCopy,
  recoverySafeView,
  recoveryTimeline,
  shouldShowRecoveryPanel,
} from '../src/recovery-agent-model.js';

test('only the two identity-preserving recovery actions are automatic', () => {
  const refresh = recoveryActionPolicy('refresh_status');
  assert.equal(refresh.autoAllowed, true);
  assert.match(refresh.detail, /可能登记.*已生成的证据/);
  assert.match(refresh.detail, /不会授权新的文件写入或命令/);
  assert.equal(recoveryActionPolicy('resume_same_run').autoAllowed, true);
  assert.equal(recoveryActionPolicy('create_repair_work').autoAllowed, false);
  assert.equal(
    recoveryActionPolicy('create_repair_work').operatorApprovalRequired,
    true,
  );
  assert.equal(recoveryActionPolicy('request_operator').autoAllowed, false);
  assert.equal(recoveryActionPolicy('request_operator').operatorApprovalRequired, false);
  assert.equal(recoveryActionPolicy('request_operator').operatorActionRequired, true);
  assert.equal(recoveryActionPolicy('run_shell'), null);
  assert.match(
    recoveryActionPolicy('resume_same_run').label,
    /同一个 Work 的已绑定运行/,
  );
  assert.doesNotMatch(recoveryActionPolicy('resume_same_run').label, /同一次运行/);
});

test('safe recovery view drops logs, command parameters, prompts, and hidden reasoning', () => {
  const view = recoverySafeView({
    state: 'proposal_ready',
    attempt_count: 1,
    diagnosis_summary: 'The same run has not reported new progress.',
    recommended_action: 'create_repair_work',
    rationale_codes: ['unchanged_progress', 'insufficient_evidence', 'unknown_private_code'],
    last_observed_at: '2026-07-25T00:00:00Z',
    raw_log: 'SECRET LOG BODY',
    command: 'rm --private-argument',
    prompt: 'private user prompt',
    hidden_reasoning: 'chain of thought',
  });

  assert.equal(view.action.label, '修复 Work 建议（尚未创建）');
  assert.equal(view.action.operatorApprovalRequired, true);
  assert.deepEqual(
    view.reasons.map((reason) => reason.code),
    ['unchanged_progress', 'insufficient_evidence'],
  );
  assert.doesNotMatch(
    JSON.stringify(view),
    /SECRET LOG BODY|rm --private-argument|private user prompt|chain of thought/,
  );
  assert.equal(view.canCheckAgain, false);
});

test('recovered means runtime progress resumed, not business outcome verification', () => {
  const view = recoverySafeView({
    state: 'recovered',
    attempt_count: 1,
    diagnosis_summary: 'A new runtime status was observed.',
    recommended_action: 'refresh_status',
    rationale_codes: ['unchanged_progress'],
  });

  assert.match(view.label, /运行已恢复/);
  assert.match(view.detail, /业务结果仍需证据复核/);
  assert.match(view.detail, /经验候选仍需人工批准/);
  assert.doesNotMatch(view.detail, /业务结果已修复|自动批准/);
  assert.equal(recoveryTimeline('recovered').every((step) => step.status === 'completed'), true);
});

test('resume acknowledgement stays in verification until new evidence is observed', () => {
  const view = recoverySafeView({
    state: 'verifying',
    attempt_count: 1,
    diagnosis_summary: 'The bound execution accepted the resume request.',
    recommended_action: 'resume_same_run',
    rationale_codes: ['remote_run_paused'],
    verification_deadline: '2026-07-25T00:05:00Z',
    verification_evidence_sha256: null,
  });

  assert.equal(view.state, 'verifying');
  assert.equal(view.verificationDeadline, '2026-07-25T00:05:00Z');
  assert.doesNotMatch(view.label, /已恢复/);
  assert.equal(view.timeline.at(-1).status, 'current');
});

test('a created Repair Work remains review-only and never reads as a completed repair', () => {
  const view = recoverySafeView({
    state: 'escalated',
    attempt_count: 1,
    diagnosis_summary: 'A separate Repair Work was requested.',
    recommended_action: 'create_repair_work',
    rationale_codes: ['operator_approval_required'],
    repair_work_id: '01KYBXQGF3Y0M34GWSEEWZ542M',
  });

  assert.equal(view.repairWorkCreated, true);
  assert.match(view.label, /待审核 Repair Work 已创建/);
  assert.match(view.detail, /尚未执行任何修复/);
  assert.doesNotMatch(`${view.label} ${view.detail}`, /问题已修复|修复完成/);
});

test('retry stays bounded by attempt limit and cooldown', () => {
  const cooling = recoverySafeView(
    {
      state: 'failed',
      attempt_count: 1,
      cooldown_until: '2026-07-25T00:05:00Z',
    },
    Date.parse('2026-07-25T00:04:00Z'),
  );
  assert.equal(cooling.canCheckAgain, false);
  assert.equal(cooling.cooldownRemainingSeconds, 60);
  assert.equal(formatRecoveryCooldown(60), '1m');
  assert.equal(formatRecoveryCooldown(60, 'zh'), '1 分钟');

  const exhausted = recoverySafeView({
    state: 'failed',
    attempt_count: 2,
    cooldown_until: '2026-07-25T00:00:00Z',
  }, Date.parse('2026-07-25T00:10:00Z'));
  assert.equal(exhausted.attemptsRemaining, 0);
  assert.equal(exhausted.canCheckAgain, false);

  const unconfirmed = recoverySafeView({
    state: 'failed',
    attempt_count: 1,
    last_error_code: 'action_unconfirmed',
  });
  assert.match(unconfirmed.lastError, /新的可验证确认/);
  assert.doesNotMatch(unconfirmed.lastError, /批准/);
});

test('recovery panel appears for active Work and stays visible after escalation', () => {
  assert.equal(shouldShowRecoveryPanel('running', { state: 'idle' }), true);
  assert.equal(shouldShowRecoveryPanel('completed_unverified', { state: 'idle' }), false);
  assert.equal(shouldShowRecoveryPanel('completed_unverified', { state: 'observing' }), false);
  assert.equal(shouldShowRecoveryPanel('completed_unverified', { state: 'escalated' }), true);
});

test('idle copy does not diagnose operator waits or an intentionally paused Work', () => {
  assert.match(recoveryIdleCopy('running'), /3 分钟/);
  assert.match(recoveryIdleCopy('awaiting_approval'), /等你审批/);
  assert.match(recoveryIdleCopy('awaiting_input'), /等你补充信息/);
  assert.match(recoveryIdleCopy('paused'), /已暂停/);
  for (const status of ['awaiting_approval', 'awaiting_input', 'paused']) {
    assert.doesNotMatch(recoveryIdleCopy(status), /3 分钟/);
  }
});

test('UI polls recovery with GET and requires a second explicit confirmation for Repair Work', async () => {
  const [component, api, app] = await Promise.all([
    readFile(new URL('../src/recovery-agent.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/api.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/App.tsx', import.meta.url), 'utf8'),
  ]);

  assert.match(api, /\/api\/v1\/works\/.*\/recovery`\)/);
  assert.match(api, /\/recovery\/decision/);
  assert.match(api, /expected_proposal_sha256/);
  assert.match(component, /getWorkRecovery\(planId\)/);
  assert.match(component, /setInterval\(\(\) => void poll\(\), 5000\)/);
  assert.match(component, /let pollInFlight = false/);
  assert.match(component, /if \(pollInFlight\) return/);
  assert.match(component, /const compact = \['idle', 'observing'\]\.includes/);
  assert.match(component, /awaiting_approval.*awaiting_input.*paused/s);
  assert.match(component, /创建待审核 Repair Work/);
  assert.match(component, /proposalConfirmed/);
  assert.match(component, /确认创建待审核 Repair Work/);
  assert.match(component, /onRepairWorkCreated\?\.\(result\.repair_work\)/);
  assert.match(app, /const openRepairWork[\s\S]*setView\('workspace'\)/);
  assert.match(app, /onRepairWorkCreated=\{openRepairWork\}/);
  assert.doesNotMatch(component, /raw_log|raw_output|command_input|hidden_reasoning/);
});
