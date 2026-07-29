import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const apiSource = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');
const onboardingSource = readFileSync(
  new URL('../src/onboarding.tsx', import.meta.url),
  'utf8',
);
const typesSource = readFileSync(new URL('../src/types.ts', import.meta.url), 'utf8');
const stylesSource = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');
const productBoundariesSource = readFileSync(
  new URL('../src/product-boundaries.ts', import.meta.url),
  'utf8',
);

test('retryable migration failures keep both recovery choices visible', () => {
  assert.match(onboardingSource, /const recoverableMigrationFailure = Boolean\(/);
  assert.match(
    onboardingSource,
    /\(status\.failure \|\| status\.state === 'failed'\) && !recoverableMigrationFailure/,
  );
  assert.match(onboardingSource, /\{status\.failure\.detail\}/);
  assert.match(onboardingSource, /chooseMigration\('fresh'\)/);
  assert.match(onboardingSource, /chooseMigration\('import'\)/);
});

test('artifact signoff binds the exact registered events and displayed digests', () => {
  assert.match(onboardingSource, /firstWork\?\.evidence_status !== 'registered'/);
  assert.match(onboardingSource, /verification\?\.evidence_status !== 'registered'/);
  for (const field of [
    'first_work_event_id',
    'first_work_sha256',
    'verification_event_id',
    'verification_sha256',
  ]) {
    assert.match(onboardingSource, new RegExp(field));
    assert.match(apiSource, new RegExp(field));
  }
  assert.match(apiSource, /JSON\.stringify\(\{ confirmed: true, \.\.\.review \}\)/);
});

test('technical-demo success is shown only after completed signoff', () => {
  assert.equal(
    [...onboardingSource.matchAll(/技术演示通过；未评估任何真实业务结果。/g)].length,
    1,
  );
  assert.match(onboardingSource, /\{status\.complete \? \(/);
  assert.match(onboardingSource, /技术演示尚待验证；不会据此评估任何真实业务结果。/);
  assert.match(onboardingSource, /合成客户回复演示通过；没有评估任何真实客户或业务结果。/);
  assert.match(appSource, /onboardingCompletionPending/);
  assert.match(appSource, /onComplete=\{\(status\) => \{/);
});

test('first Work promises per-call approval instead of an unsafe batch grant', () => {
  assert.match(onboardingSource, /分别询问 · 预计 2 次/);
  assert.match(onboardingSource, /预期两次本地保存之外的请求，请拒绝并停止/);
  assert.match(onboardingSource, /first-work\.json 或 verification\.json；其他请求一律拒绝/);
  assert.doesNotMatch(onboardingSource, /一次批准两次写入/);
});

test('first Work presents a fictional customer inquiry and a useful result', () => {
  assert.match(onboardingSource, /回复第一条客户咨询/);
  assert.match(onboardingSource, /Harbor Bakery 的 Maya/);
  assert.match(onboardingSource, /业务助手 \+ 审核助手/);
  assert.match(onboardingSource, /回复草稿 \+ 审核结果/);
  assert.match(onboardingSource, /生成客户回复/);
  assert.match(onboardingSource, /reply_draft/);
  assert.match(onboardingSource, /没有擅自确认价格/);
  assert.match(onboardingSource, /流程没有客户发送步骤/);
});

test('plan fingerprint is preserved but hidden under technical details by default', () => {
  assert.match(
    onboardingSource,
    /<details className="onboarding-technical-details">\s*<summary>\{t\('技术详情'\)\}<\/summary>[\s\S]*plan\.plan_sha256[\s\S]*<\/details>/,
  );
  assert.doesNotMatch(onboardingSource, /<details[^>]*\sopen(?:=|>)/);
  assert.match(
    onboardingSource,
    /confirmPlan\(plan\.plan_id, plan\.plan_sha256, 'automatic_safe'\)/,
  );
});

test('an unstarted legacy first Work can be explicitly upgraded without silent replacement', () => {
  assert.match(onboardingSource, /planReady && legacyFirstWork/);
  assert.match(onboardingSource, /prepareFirstWork\(true\)/);
  assert.match(apiSource, /replace_unstarted_legacy: replaceUnstartedLegacy/);
});

test('a recovered terminal Work without evidence offers an explicit immutable retry', () => {
  assert.match(onboardingSource, /incompleteTerminalEvidence/);
  assert.match(onboardingSource, /artifactsLoaded && !evidenceReviewable/);
  assert.match(onboardingSource, /prepareFirstWork\(false, true\)/);
  assert.match(onboardingSource, /保留旧记录并创建新的客户示例/);
  assert.match(apiSource, /replace_incomplete_terminal: replaceIncompleteTerminal/);
});

test('running onboarding shows trustworthy stages, elapsed time, and no invented percentage', () => {
  assert.match(onboardingSource, /onboardingRunProgress\(\{/);
  assert.match(onboardingSource, /plan\?\.execution\?\.dispatched_at \|\| plan\?\.confirmed_at/);
  assert.match(onboardingSource, /助手已上报完成 \{completed\} \/ \{total\}/);
  assert.match(onboardingSource, /Work 已启动；步骤状态会自动更新，不需要手动刷新。/);
  assert.match(onboardingSource, /本地保存审批 \{current\} \/ \{total\}/);
  assert.match(onboardingSource, /起草客户回复/);
  assert.match(onboardingSource, /检查承诺风险/);
  assert.match(onboardingSource, /runProgress\.stages\.map/);
  assert.doesNotMatch(
    onboardingSource,
    /onboarding-run-(?:overview|track|stages)[\s\S]{0,300}(?:percent|%)/,
  );
});

test('run polling exposes reconnect state and refreshes approvals immediately', () => {
  assert.match(onboardingSource, /setPollFailures\(\(count\) => count \+ 1\)/);
  assert.match(onboardingSource, /pollFailures >= 4/);
  assert.match(onboardingSource, /本地状态连接暂时中断，正在重连/);
  assert.match(onboardingSource, /const RUN_POLL_INTERVAL_MS = 1500/);
  assert.match(
    onboardingSource,
    /next\.status === 'awaiting_approval' && !pendingApproval[\s\S]*await onRefresh\(\)/,
  );
  assert.match(onboardingSource, /checkFirstWork/);
  assert.match(onboardingSource, /立即检查状态/);
});

test('approval interrupts the activity view and receives keyboard focus', () => {
  assert.match(onboardingSource, /approvalRef\.current\?\.focus\(\)/);
  assert.match(onboardingSource, /ref=\{approvalRef\}/);
  assert.match(onboardingSource, /role="alert"/);
  assert.match(onboardingSource, /tabIndex=\{-1\}/);
});

test('mobile onboarding names the current step and respects reduced motion', () => {
  assert.match(onboardingSource, /className="onboarding-mobile-step"/);
  assert.match(stylesSource, /\.onboarding-mobile-step[\s\S]*display: none/);
  assert.match(
    stylesSource,
    /@media \(max-width: 720px\)[\s\S]*\.onboarding-mobile-step[\s\S]*display: block/,
  );
  assert.match(
    stylesSource,
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*\.onboarding-shell \.spin[\s\S]*animation: none/,
  );
});

test('public provider onboarding shows Codex while preserving legacy provider data', () => {
  assert.match(typesSource, /provider_choice: 'openai' \| 'anthropic' \| null/);
  assert.match(apiSource, /function selectOnboardingProvider\(/);
  assert.match(apiSource, /api\('\/api\/v1\/onboarding\/provider'/);
  assert.match(apiSource, /JSON\.stringify\(\{ provider, confirmed: true \}\)/);
  assert.match(onboardingSource, /'连接 Codex'/);
  assert.match(onboardingSource, /bootstrap\.providers\.openai/);
  assert.match(onboardingSource, /bootstrap\.providers\.anthropic/);
  assert.match(onboardingSource, /value="openai"/);
  assert.match(onboardingSource, /value="anthropic"/);
  assert.match(productBoundariesSource, /SHOW_ANTHROPIC_PROVIDER_UI = false/);
  assert.match(onboardingSource, /SHOW_ANTHROPIC_PROVIDER_UI && <section/);
  assert.match(
    onboardingSource,
    /useState<OnboardingProvider \| null>\(\s*status\.provider_choice \?\? 'openai'/,
  );
});

test('Codex uses account sign-in while the hidden legacy Claude path remains API-key-only', () => {
  assert.match(onboardingSource, /connectProvider\('openai', 'account'\)/);
  assert.match(
    onboardingSource,
    /connectProvider\('anthropic', 'api_key', apiKey, true\)/,
  );
  assert.doesNotMatch(onboardingSource, /connectProvider\('anthropic', 'account'\)/);
  assert.match(onboardingSource, /type="password"/);
  assert.match(onboardingSource, /anthropicConfirmed/);
  assert.match(onboardingSource, /anthropicProvider\.auth_mode === 'api_key'/);
  assert.match(onboardingSource, /Claude Pro\/Max 登录不能用于 OpsWitness/);
  assert.match(onboardingSource, /Keychain/);
});

test('provider connection stops automatic waiting and exposes accessible recovery', () => {
  assert.match(onboardingSource, /PROVIDER_WAIT_LIMIT_MS = 7 \* 60 \* 1000/);
  assert.match(onboardingSource, /setProviderWaitExpired\(true\)/);
  assert.match(onboardingSource, /自动等待已停止/);
  assert.match(onboardingSource, /不会继续无限等待/);
  assert.match(onboardingSource, /role="alert"/);
  assert.match(onboardingSource, /重新检查连接/);
  assert.match(stylesSource, /\.onboarding-provider-options[\s\S]*grid-template-columns/);
  assert.match(
    stylesSource,
    /@media \(max-width: 720px\)[\s\S]*\.onboarding-provider-options[\s\S]*grid-template-columns: 1fr/,
  );
});
