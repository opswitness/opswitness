import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Bot,
  Check,
  CheckCircle2,
  Circle,
  Clock3,
  Database,
  FileCheck2,
  HardDrive,
  KeyRound,
  LoaderCircle,
  LogIn,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  chooseOnboardingMigration,
  confirmPlan,
  connectProvider,
  decideApproval,
  getPlan,
  getPlanArtifact,
  getPlanArtifacts,
  getProviderConnection,
  prepareOnboardingFirstWork,
  selectOnboardingProvider,
  signoffOnboardingArtifacts,
} from './api';
import {
  formatExecutionElapsed,
  onboardingRunProgress,
} from './execution-progress.js';
import { OnboardingHelp } from './docs-center';
import { useLanguage } from './language';
import { SHOW_ANTHROPIC_PROVIDER_UI } from './product-boundaries';
import type {
  Bootstrap,
  OnboardingStatus,
  PlanArtifact,
  PlanArtifactPreview,
  PlanRecord,
  ProviderConnectionJob,
} from './types';
import { APP_VERSION } from './version';

type OnboardingFlowProps = {
  status: OnboardingStatus;
  bootstrap: Bootstrap;
  onStatus: (status: OnboardingStatus) => void;
  onComplete: (status: OnboardingStatus) => void;
  onFinish: () => void;
  onRefresh: () => Promise<void>;
};

const ACTIVE_PLAN_STATES = new Set([
  'confirmed',
  'dispatching',
  'running',
  'awaiting_approval',
  'awaiting_input',
  'pause_requested',
  'paused',
  'resuming',
  'cancel_requested',
]);

const CUSTOMER_REPLY_PLAN_TITLE = 'Reply to Your First Customer';
const LEGACY_FIRST_WORK_TITLE = 'My First Evidence Work';
const PROVIDER_WAIT_LIMIT_MS = 7 * 60 * 1000;

type OnboardingProvider = 'openai' | 'anthropic';

function objectValue(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '0 GB';
  return `${(value / (1024 ** 3)).toFixed(1)} GB`;
}

function statusStep(status: OnboardingStatus, plan: PlanRecord | null): number {
  if (!status.disk_ready || status.state === 'preparing' || status.state === 'self_check') return 0;
  if (status.migration_required && !status.migration_choice) return 1;
  if (!status.provider_runtime_ready || status.state === 'provider_required') return 2;
  if (!plan || ['planning', 'ready'].includes(plan.status)) return 3;
  if (ACTIVE_PLAN_STATES.has(plan.status) || status.state === 'first_work_running') return 4;
  return 5;
}

export function OnboardingFlow({
  status,
  bootstrap,
  onStatus,
  onComplete,
  onFinish,
  onRefresh,
}: OnboardingFlowProps) {
  const { language, t } = useLanguage();
  const initialPlan = useMemo(
    () => (
      status.first_work_plan_id
        ? bootstrap.plans.find((row) => row.plan_id === status.first_work_plan_id) || null
        : null
    ),
    [bootstrap.plans, status.first_work_plan_id],
  );
  const [plan, setPlan] = useState<PlanRecord | null>(initialPlan);
  const [artifacts, setArtifacts] = useState<PlanArtifact[]>([]);
  const [artifactPreviews, setArtifactPreviews] = useState<PlanArtifactPreview[]>([]);
  const [artifactsLoaded, setArtifactsLoaded] = useState(false);
  const [providerJob, setProviderJob] = useState<ProviderConnectionJob | null>(null);
  const [providerSelection, setProviderSelection] = useState<OnboardingProvider | null>(
    status.provider_choice,
  );
  const [providerWaitExpired, setProviderWaitExpired] = useState(false);
  const [anthropicApiKey, setAnthropicApiKey] = useState('');
  const [anthropicConfirmed, setAnthropicConfirmed] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [importConfirmed, setImportConfirmed] = useState(false);
  const [reviewConfirmed, setReviewConfirmed] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [pollFailures, setPollFailures] = useState(0);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const approvalRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (initialPlan) setPlan(initialPlan);
  }, [initialPlan]);

  useEffect(() => {
    if (status.provider_choice) setProviderSelection(status.provider_choice);
  }, [status.provider_choice]);

  useEffect(() => {
    if (!providerJob || providerJob.status !== 'running' || providerWaitExpired) return;
    let cancelled = false;
    const poll = async () => {
      const createdAt = Date.parse(providerJob.created_at);
      if (
        Number.isFinite(createdAt)
        && Date.now() - createdAt >= PROVIDER_WAIT_LIMIT_MS
      ) {
        if (!cancelled) setProviderWaitExpired(true);
        return;
      }
      try {
        const next = await getProviderConnection(providerJob.job_id);
        if (cancelled) return;
        setProviderJob(next);
        if (
          next.status === 'ready'
          && (next.provider === 'openai' || next.provider === 'anthropic')
        ) {
          const selected = await selectOnboardingProvider(next.provider);
          if (cancelled) return;
          onStatus(selected);
          await onRefresh();
        }
      } catch (reason) {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : t('AI 提供商连接状态读取失败'));
        }
      }
    };
    const timer = window.setInterval(() => void poll(), 1500);
    void poll();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [onRefresh, onStatus, providerJob, providerWaitExpired, t]);

  useEffect(() => {
    if (!plan || !ACTIVE_PLAN_STATES.has(plan.status)) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await getPlan(plan.plan_id);
        if (cancelled) return;
        setPlan(next);
        setPollFailures(0);
        if (
          ['awaiting_approval', 'awaiting_input'].includes(next.status)
          && next.status !== plan.status
        ) {
          await onRefresh();
        }
        if (['completed_unverified', 'failed', 'cancelled'].includes(next.status)) {
          setArtifacts(await getPlanArtifacts(next.plan_id));
          await onRefresh();
        }
      } catch {
        // Preserve the last trustworthy run state and retry on the next interval.
        if (!cancelled) setPollFailures((count) => count + 1);
      }
    };
    const timer = window.setInterval(() => void poll(), 2500);
    void poll();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [onRefresh, plan?.plan_id, plan?.status]);

  useEffect(() => {
    if (!plan || !ACTIVE_PLAN_STATES.has(plan.status)) return;
    setNowMs(Date.now());
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [plan?.plan_id, plan?.status]);

  useEffect(() => {
    if (!plan || plan.status !== 'completed_unverified') return;
    let cancelled = false;
    setArtifactsLoaded(false);
    const load = async () => {
      try {
        const rows = await getPlanArtifacts(plan.plan_id);
        if (cancelled) return;
        setArtifacts(rows);
        const previewResults = await Promise.allSettled(
          rows
            .filter((artifact) => artifact.preview_supported)
            .map((artifact) => getPlanArtifact(plan.plan_id, artifact.name)),
        );
        if (!cancelled) {
          setArtifactPreviews(
            previewResults.flatMap((result) => (
              result.status === 'fulfilled' ? [result.value] : []
            )),
          );
          setArtifactsLoaded(true);
        }
      } catch {
        // Preserve the registered artifact metadata; the review button remains fail closed.
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [plan?.plan_id, plan?.status]);

  const run = async (name: string, action: () => Promise<void>) => {
    if (busy) return;
    setBusy(name);
    setError('');
    try {
      await action();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('首次设置未能完成'));
    } finally {
      setBusy('');
    }
  };

  const chooseMigration = (choice: 'fresh' | 'import') => run(`migration-${choice}`, async () => {
    const next = await chooseOnboardingMigration(choice);
    onStatus(next);
    await onRefresh();
  });

  const persistProviderChoice = (provider: OnboardingProvider) => run(
    `provider-select-${provider}`,
    async () => {
      const next = await selectOnboardingProvider(provider);
      onStatus(next);
      await onRefresh();
    },
  );

  const chooseProvider = (provider: OnboardingProvider) => {
    if (providerJob?.status === 'running' && !providerWaitExpired) return;
    setProviderSelection(provider);
    setProviderWaitExpired(false);
    setProviderJob(null);
    setError('');
    if (provider !== 'anthropic') {
      setAnthropicApiKey('');
      setAnthropicConfirmed(false);
    }
    if (bootstrap.providers[provider].runtime_ready) {
      void persistProviderChoice(provider);
    }
  };

  const loginCodex = () => run('provider-openai', async () => {
    setProviderSelection('openai');
    setProviderWaitExpired(false);
    setProviderJob(await connectProvider('openai', 'account'));
  });

  const connectAnthropic = () => run('provider-anthropic', async () => {
    if (anthropicApiKey.length < 8 || /\s/.test(anthropicApiKey)) {
      throw new Error(t('请输入有效的 Anthropic API Key。'));
    }
    if (!anthropicConfirmed) {
      throw new Error(t('请确认 Keychain 保存和 Anthropic API 计费。'));
    }
    const apiKey = anthropicApiKey;
    setAnthropicApiKey('');
    setProviderSelection('anthropic');
    setProviderWaitExpired(false);
    setProviderJob(await connectProvider('anthropic', 'api_key', apiKey, true));
  });

  const recheckProvider = () => run('provider-recheck', async () => {
    setProviderWaitExpired(false);
    if (providerJob) {
      const next = await getProviderConnection(providerJob.job_id);
      setProviderJob(next);
      if (
        next.status === 'ready'
        && (next.provider === 'openai' || next.provider === 'anthropic')
      ) {
        const selected = await selectOnboardingProvider(next.provider);
        onStatus(selected);
      }
    }
    await onRefresh();
  });

  const prepareFirstWork = (
    replaceUnstartedLegacy = false,
    replaceIncompleteTerminal = false,
  ) => run('prepare-work', async () => {
    const result = await prepareOnboardingFirstWork(
      replaceUnstartedLegacy,
      replaceIncompleteTerminal,
    );
    onStatus(result.onboarding);
    setPlan(result.plan);
    setArtifacts([]);
    setArtifactPreviews([]);
    setArtifactsLoaded(false);
  });

  const confirmFirstWork = () => run('confirm-work', async () => {
    if (!plan?.plan_sha256) throw new Error(t('首个 Work 缺少不可变方案哈希'));
    const next = await confirmPlan(plan.plan_id, plan.plan_sha256, 'automatic_safe');
    setPlan(next);
    await onRefresh();
  });

  const pendingApproval = bootstrap.approvals.find(
    (approval) => approval.plan_id === plan?.plan_id && approval.status === 'pending',
  );

  useEffect(() => {
    if (!pendingApproval) return;
    approvalRef.current?.focus();
  }, [pendingApproval?.approval_id]);

  const decideFirstApproval = (decision: 'approve' | 'reject') => run(`approval-${decision}`, async () => {
    if (!pendingApproval) throw new Error(t('审批请求尚未同步'));
    await decideApproval(
      pendingApproval.approval_id,
      decision,
      decision === 'approve'
        ? t('首次示例 Work：已审核本次本地保存')
        : t('首次示例 Work：拒绝本次请求'),
    );
    if (plan) setPlan(await getPlan(plan.plan_id));
    await onRefresh();
  });

  const checkFirstWork = () => run('refresh-work', async () => {
    if (!plan) throw new Error(t('首个 Work 尚未创建'));
    const next = await getPlan(plan.plan_id);
    setPlan(next);
    setPollFailures(0);
    await onRefresh();
  });

  const signoff = () => run('signoff', async () => {
    if (!plan) throw new Error(t('首个 Work 尚未创建'));
    if (!artifactReview) throw new Error(t('首个 Work 的证据尚未完整登记'));
    const next = await signoffOnboardingArtifacts(plan.plan_id, artifactReview);
    onComplete(next);
    await onRefresh();
  });

  const step = statusStep(status, plan);
  const steps = [
    '准备本地环境',
    '选择数据环境',
    '选择 AI 提供商',
    '查看客户示例',
    '生成并批准',
    '审阅回复',
  ];
  const planReady = plan?.status === 'ready' && !!plan.plan && !!plan.plan_sha256;
  const customerReplyPlan = plan?.plan?.title === CUSTOMER_REPLY_PLAN_TITLE;
  const legacyFirstWork = plan?.plan?.title === LEGACY_FIRST_WORK_TITLE;
  const terminalFailure = plan?.status === 'failed' || plan?.status === 'cancelled';
  const evidenceReady = plan?.status === 'completed_unverified' || status.state === 'evidence_review';
  const runProgress = useMemo(() => onboardingRunProgress({
    workStatus: plan?.status || 'confirmed',
    plannedStages: plan?.plan?.stages.map((stage) => ({
      order: stage.order,
      owner: stage.owner || plan.plan?.agents.find(
        (agent) => agent.agent_id === stage.owner_agent_id,
      )?.name || 'Agent',
    })) || [],
    progress: plan?.execution?.progress || null,
    startedAt: plan?.execution?.dispatched_at || plan?.confirmed_at || null,
    estimateMinutes: plan?.plan?.estimated_duration_minutes || 0,
    nowMs,
  }), [
    nowMs,
    plan?.confirmed_at,
    plan?.execution?.dispatched_at,
    plan?.execution?.progress,
    plan?.plan?.estimated_duration_minutes,
    plan?.plan?.stages,
    plan?.status,
  ]);
  const activeRunStage = runProgress.stages.find(
    (stage) => stage.order === runProgress.currentOrder,
  );
  const runStageLabel = (order: number) => {
    if (customerReplyPlan) {
      return order === 1 ? t('起草客户回复') : order === 2 ? t('检查承诺风险') : t('计划步骤 {step}', { step: order });
    }
    return order === 1 ? t('创建演示文件') : order === 2 ? t('核验演示文件') : t('计划步骤 {step}', { step: order });
  };
  const runStageStatus = (stage: (typeof runProgress.stages)[number]) => {
    if (stage.status === 'completed') return t('助手已完成 · 待最终核验');
    if (stage.status === 'running') {
      return t(plan?.status === 'awaiting_approval' ? '等待你的确认' : '正在进行');
    }
    if (stage.status === 'blocked') return t('等待前一步');
    if (stage.status === 'failed' || stage.status === 'unknown') return t('状态需要检查');
    return t('等待开始');
  };
  const currentActivity = (() => {
    if (plan?.status === 'awaiting_approval') {
      return {
        title: t('需要你确认'),
        detail: pendingApproval
          ? t('助手已暂停，等待你审核这次本地保存。')
          : t('正在同步需要你确认的操作，请稍候。'),
      };
    }
    if (plan?.status === 'awaiting_input') {
      return {
        title: t('正在等待你的信息'),
        detail: t('助手已暂停，OpsWitness 正在同步需要你回答的问题。'),
      };
    }
    if (plan?.status === 'paused' || plan?.status === 'pause_requested') {
      return {
        title: t('Work 已暂停'),
        detail: t('当前进度已经保留，不需要重新开始。'),
      };
    }
    if (!runProgress.observed || !activeRunStage) {
      return {
        title: t('正在启动本地助手'),
        detail: t('Work 已开始；暂未收到可绑定到步骤的更新，OpsWitness 会自动继续检查。'),
      };
    }
    if (customerReplyPlan && activeRunStage.order === 1) {
      return {
        title: t('业务助手正在起草'),
        detail: t('正在根据虚构咨询起草一份谨慎的回复。'),
      };
    }
    if (customerReplyPlan && activeRunStage.order === 2) {
      return {
        title: t('审核助手正在检查'),
        detail: t('正在检查价格、时间和发送风险。'),
      };
    }
    return {
      title: t(activeRunStage.order === 1 ? 'Writer 正在创建演示文件' : 'Verifier 正在核验演示文件'),
      detail: t(activeRunStage.order === 1
        ? '正在 App 管理的空白工作区生成固定范围的文件。'
        : '正在独立核对文件摘要和登记状态。'),
    };
  })();
  const recoverableMigrationFailure = Boolean(
    status.failure?.retryable !== false
    && status.migration_required
    && !status.migration_choice,
  );
  const artifactReview = useMemo(() => {
    const firstWork = artifacts.find((artifact) => artifact.name === 'first-work.json');
    const verification = artifacts.find((artifact) => artifact.name === 'verification.json');
    if (
      firstWork?.evidence_status !== 'registered'
      || verification?.evidence_status !== 'registered'
      || !firstWork.event_id
      || !verification.event_id
      || !firstWork.sha256
      || !verification.sha256
    ) {
      return null;
    }
    return {
      first_work_event_id: firstWork.event_id,
      first_work_sha256: firstWork.sha256,
      verification_event_id: verification.event_id,
      verification_sha256: verification.sha256,
    };
  }, [artifacts]);
  const replyPreview = artifactPreviews.find((artifact) => artifact.name === 'first-work.json');
  const reviewPreview = artifactPreviews.find((artifact) => artifact.name === 'verification.json');
  const replyContent = objectValue(replyPreview?.content);
  const reviewContent = objectValue(reviewPreview?.content);
  const reviewChecks = objectValue(reviewContent?.checks);
  const replyDraft = typeof replyContent?.reply_draft === 'string'
    ? replyContent.reply_draft
    : '';
  const customerEvidenceVisible = Boolean(
    replyDraft
    && replyContent?.scenario === 'synthetic_website_maintenance_inquiry'
    && replyContent?.draft_only === true
    && replyContent?.delivery_requested === false
    && replyContent?.technical_demo_only === true
    && reviewContent?.artifact === 'first-work.json'
    && reviewContent?.sha256 === replyPreview?.sha256
    && reviewContent?.approved_as_draft === true
    && reviewContent?.fictional_scenario === true
    && reviewContent?.technical_demo_only === true
    && reviewChecks?.follow_up_questions_present === true
    && reviewChecks?.no_price_commitment === true
    && reviewChecks?.no_start_date_commitment === true
    && reviewChecks?.delivery_requested === false,
  );
  const evidenceReviewable = Boolean(
    artifactReview && (!customerReplyPlan || customerEvidenceVisible),
  );
  const incompleteTerminalEvidence = evidenceReady && artifactsLoaded && !evidenceReviewable;
  const openaiProvider = bootstrap.providers.openai;
  const anthropicProvider = bootstrap.providers.anthropic;
  const providerConnectionLocked = Boolean(
    providerJob?.status === 'running' && !providerWaitExpired,
  );
  const anthropicKeyValid = (
    anthropicApiKey.length >= 8
    && !/\s/.test(anthropicApiKey)
  );
  const providerStatusLabel = (provider: typeof openaiProvider) => {
    if (provider.runtime_ready) return t('可用于 Work');
    if (!provider.installed) return t('此 Mac 不可用');
    if (provider.provider === 'anthropic' && provider.auth_mode !== 'api_key') {
      return t('需要连接');
    }
    if (provider.authenticated) return t('运行时尚未就绪');
    return t('需要连接');
  };

  return (
    <main className="onboarding-shell">
      <section className="onboarding-card" aria-label={t('OpsWitness 首次设置')}>
        <header className="onboarding-header">
          <div className="onboarding-brand">
            <span className="onboarding-mark"><ShieldCheck size={24} /></span>
            <div>
              <span>OpsWitness · v{APP_VERSION}</span>
              <h1>{t('设置你的本地 AI 工作空间')}</h1>
            </div>
          </div>
          <div className="onboarding-header-actions">
            <button
              className="onboarding-help-button"
              type="button"
              aria-haspopup="dialog"
              onClick={() => setHelpOpen(true)}
            >
              <BookOpen size={14} />
              {t('帮助')}
            </button>
            <span className="onboarding-local"><HardDrive size={14} />{t('本机运行')}</span>
          </div>
        </header>

        <ol className="onboarding-steps" aria-label={t('首次设置进度')}>
          {steps.map((label, index) => (
            <li className={index < step ? 'complete' : index === step ? 'active' : ''} key={label}>
              <span>{index < step ? <Check size={13} /> : index + 1}</span>
              <small>{t(label)}</small>
            </li>
          ))}
        </ol>
        <p className="onboarding-mobile-step">
          {t('第 {current} / {total} 步 · {label}', {
            current: Math.min(step + 1, steps.length),
            total: steps.length,
            label: t(steps[Math.min(step, steps.length - 1)]),
          })}
        </p>

        <div className="onboarding-content">
          {status.complete ? (
            <OnboardingMessage
              icon={<CheckCircle2 size={24} />}
              title={t('首次设置已完成')}
              detail={customerReplyPlan
                ? t('合成客户回复演示通过；没有评估任何真实客户或业务结果。')
                : t('技术演示通过；未评估任何真实业务结果。')}
            >
              <button className="primary-button" type="button" onClick={onFinish}>
                <ArrowRight size={16} />{t('进入 OpsWitness')}
              </button>
            </OnboardingMessage>
          ) : !status.disk_ready ? (
            <OnboardingMessage
              icon={<AlertTriangle size={24} />}
              tone="danger"
              title={t('需要更多可用空间')}
              detail={t('OpsWitness 需要至少 {required} 可用空间；当前约有 {available}。', {
                required: formatBytes(status.required_free_bytes),
                available: formatBytes(status.available_free_bytes),
              })}
            >
              <button className="secondary-button" type="button" onClick={() => void onRefresh()}>
                <RefreshCw size={16} />{t('重新检查')}
              </button>
            </OnboardingMessage>
          ) : (status.failure || status.state === 'failed') && !recoverableMigrationFailure ? (
            <OnboardingMessage
              icon={<AlertTriangle size={24} />}
              tone="danger"
              title={t('本地运行环境未准备好')}
              detail={status.failure?.detail || t('请导出诊断信息并重试；现有证据不会被删除。')}
            >
              {status.failure?.retryable !== false && (
                <button className="secondary-button" type="button" onClick={() => void onRefresh()}>
                  <RefreshCw size={16} />{t('重试检查')}
                </button>
              )}
            </OnboardingMessage>
          ) : status.migration_required && !status.migration_choice ? (
            <section className="onboarding-panel">
              <span className="onboarding-panel-icon"><Database size={24} /></span>
              <h2>{t('发现现有 OpsWitness 数据')}</h2>
              <p>{t('旧目录不会被移动或合并。你可以导入一份经过校验的副本，也可以创建完全独立的新环境。')}</p>
              <div className="onboarding-source-list">
                {status.legacy_sources.map((source) => <code key={source}>{source}</code>)}
              </div>
              {status.failure && (
                <div className="onboarding-inline-error" role="alert">
                  {status.failure.detail}
                </div>
              )}
              <label className="onboarding-check">
                <input
                  type="checkbox"
                  checked={importConfirmed}
                  onChange={(event) => setImportConfirmed(event.target.checked)}
                />
                <span>{t('我理解导入会先建立备份和文件清单，原目录保持不变')}</span>
              </label>
              <div className="onboarding-actions">
                <button
                  className="secondary-button"
                  type="button"
                  disabled={!!busy}
                  onClick={() => void chooseMigration('fresh')}
                >
                  {busy === 'migration-fresh' ? <LoaderCircle className="spin" size={16} /> : <Sparkles size={16} />}
                  {t('创建全新环境')}
                </button>
                <button
                  className="primary-button"
                  type="button"
                  disabled={!importConfirmed || !!busy}
                  onClick={() => void chooseMigration('import')}
                >
                  {busy === 'migration-import' ? <LoaderCircle className="spin" size={16} /> : <Database size={16} />}
                  {t('导入现有数据副本')}
                </button>
              </div>
            </section>
          ) : !status.runtime_ready || ['preparing', 'self_check'].includes(status.state) ? (
            <OnboardingMessage
              icon={<LoaderCircle className="spin" size={24} />}
              title={t('正在准备本地运行环境')}
              detail={t('正在校验并启动 OpsWitness、AionCore 和 Paperclip。首次启动可能需要几分钟。')}
            />
          ) : !status.provider_runtime_ready ? (
            <section className="onboarding-panel onboarding-provider-panel">
              <span className="onboarding-panel-icon"><KeyRound size={24} /></span>
              <h2>{t('连接 Codex')}</h2>
              <p>{t('首个 Work 使用 App 随附的 Codex；OpsWitness 不会静默切换到其他提供商。')}</p>
              <div
                className="onboarding-provider-options"
                role="radiogroup"
                aria-label={t('首个 Work 的 AI 提供商')}
              >
                <section
                  className={`onboarding-provider-card ${providerSelection === 'openai' ? 'selected' : ''}`}
                >
                  <label className="onboarding-provider-choice">
                    <input
                      type="radio"
                      name="onboarding-provider"
                      value="openai"
                      checked={providerSelection === 'openai'}
                      disabled={providerConnectionLocked}
                      onChange={() => chooseProvider('openai')}
                    />
                    <span className="onboarding-provider-mark"><Bot size={19} /></span>
                    <span className="onboarding-provider-copy">
                      <strong>Codex</strong>
                      <small>{t('随 OpsWitness App 提供 · 推荐')}</small>
                    </span>
                    <span className={`onboarding-provider-state ${openaiProvider.runtime_ready ? 'ready' : 'setup'}`}>
                      {providerStatusLabel(openaiProvider)}
                    </span>
                  </label>
                  <p>{t('通过官方 Codex 登录使用你的 ChatGPT/OpenAI 账户；OpsWitness 不读取账号密码或 OAuth 凭证。')}</p>
                  {providerSelection === 'openai' && (
                    <div className="onboarding-provider-controls">
                      {openaiProvider.runtime_ready ? (
                        <button
                          className="primary-button"
                          type="button"
                          disabled={!!busy}
                          onClick={() => void persistProviderChoice('openai')}
                        >
                          {busy === 'provider-select-openai'
                            ? <LoaderCircle className="spin" size={16} />
                            : <CheckCircle2 size={16} />}
                          {t('使用 Codex 继续')}
                        </button>
                      ) : !openaiProvider.installed ? (
                        <div className="onboarding-provider-warning" role="alert">
                          <AlertTriangle size={16} />
                          <span>{t('App 内置的 Codex 组件不可用。请重新检查；如果仍未恢复，请导出诊断。')}</span>
                        </div>
                      ) : openaiProvider.authenticated ? (
                        <div className="onboarding-provider-warning" role="status">
                          <AlertTriangle size={16} />
                          <span>{t('Codex 账户已连接，但任务运行时尚未就绪。')}</span>
                        </div>
                      ) : (
                        <button
                          className="primary-button"
                          type="button"
                          disabled={!!busy || providerJob?.status === 'running'}
                          onClick={() => void loginCodex()}
                        >
                          {busy === 'provider-openai'
                            ? <LoaderCircle className="spin" size={16} />
                            : <LogIn size={16} />}
                          {t('登录 Codex')}
                        </button>
                      )}
                    </div>
                  )}
                </section>

                {SHOW_ANTHROPIC_PROVIDER_UI && <section
                  className={`onboarding-provider-card ${providerSelection === 'anthropic' ? 'selected' : ''}`}
                >
                  <label className="onboarding-provider-choice">
                    <input
                      type="radio"
                      name="onboarding-provider"
                      value="anthropic"
                      checked={providerSelection === 'anthropic'}
                      disabled={providerConnectionLocked}
                      onChange={() => chooseProvider('anthropic')}
                    />
                    <span className="onboarding-provider-mark"><Bot size={19} /></span>
                    <span className="onboarding-provider-copy">
                      <strong>Claude</strong>
                      <small>{t('使用 Anthropic API Key')}</small>
                    </span>
                    <span className={`onboarding-provider-state ${anthropicProvider.runtime_ready ? 'ready' : 'setup'}`}>
                      {providerStatusLabel(anthropicProvider)}
                    </span>
                  </label>
                  <p>{t('使用你自己的 Anthropic API Key；Claude Pro/Max 登录不能用于 OpsWitness')}</p>
                  {providerSelection === 'anthropic' && (
                    <div className="onboarding-provider-controls">
                      {anthropicProvider.runtime_ready ? (
                        <button
                          className="primary-button"
                          type="button"
                          disabled={!!busy}
                          onClick={() => void persistProviderChoice('anthropic')}
                        >
                          {busy === 'provider-select-anthropic'
                            ? <LoaderCircle className="spin" size={16} />
                            : <CheckCircle2 size={16} />}
                          {t('使用 Claude 继续')}
                        </button>
                      ) : !anthropicProvider.installed ? (
                        <div className="onboarding-provider-warning" role="alert">
                          <AlertTriangle size={16} />
                          <span>{t('此 Mac 上的 Claude 运行时不可用。此选项不会自动改用 Codex。')}</span>
                        </div>
                      ) : (
                        anthropicProvider.authenticated
                        && anthropicProvider.auth_mode === 'api_key'
                      ) ? (
                        <div className="onboarding-provider-warning" role="status">
                          <AlertTriangle size={16} />
                          <span>{t('Anthropic API Key 已连接，但 Claude 任务运行时尚未就绪。')}</span>
                        </div>
                      ) : (
                        <div className="onboarding-provider-key-form">
                          <label htmlFor="onboarding-anthropic-key">{t('Anthropic API Key')}</label>
                          <input
                            id="onboarding-anthropic-key"
                            type="password"
                            value={anthropicApiKey}
                            autoComplete="new-password"
                            spellCheck={false}
                            placeholder="sk-ant-…"
                            disabled={!!busy || providerJob?.status === 'running'}
                            onChange={(event) => setAnthropicApiKey(event.target.value)}
                          />
                          <small>{t('Key 验证后只保存在此 Mac 的 Keychain。Anthropic API 用量单独计费，不包含在 Claude Pro/Max 订阅中。')}</small>
                          <label className="onboarding-provider-consent">
                            <input
                              type="checkbox"
                              checked={anthropicConfirmed}
                              disabled={!!busy || providerJob?.status === 'running'}
                              onChange={(event) => setAnthropicConfirmed(event.target.checked)}
                            />
                            <span>{t('我确认将 Key 保存到此 Mac 的 Keychain，并由我的 Anthropic API 账户承担用量费用')}</span>
                          </label>
                          <button
                            className="primary-button"
                            type="button"
                            disabled={(
                              !!busy
                              || providerJob?.status === 'running'
                              || !anthropicKeyValid
                              || !anthropicConfirmed
                            )}
                            onClick={() => void connectAnthropic()}
                          >
                            {busy === 'provider-anthropic'
                              ? <LoaderCircle className="spin" size={16} />
                              : <KeyRound size={16} />}
                            {t('验证 Key 并使用 Claude')}
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </section>}
              </div>

              {providerJob?.status === 'running' && !providerWaitExpired && (
                <div className="onboarding-progress-note onboarding-provider-progress" role="status">
                  <LoaderCircle className="spin" size={16} />
                  <span>
                    <strong>
                      {providerJob.provider === 'openai'
                        ? t('等待 Codex 官方登录完成')
                        : t('正在验证 Anthropic API Key')}
                    </strong>
                    <small>{t('最多自动等待 7 分钟；你可以随时重新检查状态。')}</small>
                  </span>
                </div>
              )}
              {providerWaitExpired && providerJob?.status === 'running' && (
                <div className="onboarding-inline-error onboarding-provider-error" role="alert">
                  <AlertTriangle size={16} />
                  <span>
                    <strong>{t('自动等待已停止')}</strong>
                    <small>{t('连接仍未确认。OpsWitness 不会继续无限等待；请重新检查，或明确选择另一提供商。')}</small>
                  </span>
                </div>
              )}
              {providerJob?.status === 'failed' && (
                <div className="onboarding-inline-error onboarding-provider-error" role="alert">
                  <AlertTriangle size={16} />
                  <span>
                    <strong>
                      {providerJob.provider === 'openai'
                        ? t('Codex 登录未完成')
                        : t('Anthropic API Key 连接未完成')}
                    </strong>
                    <small>{t('没有选择其他提供商，也没有开始首个 Work。请检查后重试。')}</small>
                  </span>
                </div>
              )}
              <div className="onboarding-actions">
                <button
                  className="secondary-button"
                  type="button"
                  disabled={!!busy}
                  onClick={() => void recheckProvider()}
                >
                  {busy === 'provider-recheck'
                    ? <LoaderCircle className="spin" size={16} />
                    : <RefreshCw size={16} />}
                  {t('重新检查连接')}
                </button>
              </div>
            </section>
          ) : !plan ? (
            <section className="onboarding-panel">
              <span className="onboarding-panel-icon success"><CheckCircle2 size={24} /></span>
              <h2>{t('本地运行环境已就绪')}</h2>
              <p>{t('接下来用一条虚构客户咨询，体验业务助手起草回复、审核助手检查承诺风险的完整流程。')}</p>
              <ul className="onboarding-safety-list">
                <li>{t('使用虚构客户与固定示例，不读取你的文件')}</li>
                <li>{t('只生成本地草稿；流程没有发送步骤')}</li>
                <li>{t('每次保存都会单独询问，不安装也不删除')}</li>
              </ul>
              <button
                className="primary-button"
                type="button"
                disabled={!!busy}
                onClick={() => void prepareFirstWork()}
              >
                {busy === 'prepare-work' ? <LoaderCircle className="spin" size={16} /> : <ArrowRight size={16} />}
                {t('查看客户咨询示例')}
              </button>
            </section>
          ) : plan.status === 'planning' ? (
            <OnboardingMessage
              icon={<LoaderCircle className="spin" size={24} />}
              title={t('正在准备客户咨询示例')}
              detail={t('正在建立固定范围的业务助手与审核助手方案；尚未开始执行。')}
            />
          ) : planReady && legacyFirstWork ? (
            <section className="onboarding-panel">
              <span className="onboarding-panel-icon"><Sparkles size={24} /></span>
              <h2>{t('换成更直观的客户咨询示例')}</h2>
              <p>{t('你尚未运行旧版技术示例。可以明确切换到新的虚构客户咨询；旧方案会保留在审计记录中，但不会执行。')}</p>
              <button
                className="primary-button"
                type="button"
                disabled={!!busy}
                onClick={() => void prepareFirstWork(true)}
              >
                {busy === 'prepare-work' ? <LoaderCircle className="spin" size={16} /> : <ArrowRight size={16} />}
                {t('使用客户咨询示例')}
              </button>
            </section>
          ) : planReady ? (
            <section className="onboarding-panel onboarding-plan">
              <span className="onboarding-panel-icon"><Bot size={24} /></span>
              <h2>{customerReplyPlan ? t('回复第一条客户咨询') : plan.plan?.title}</h2>
              {customerReplyPlan ? (
                <>
                  <p>{t('业务助手会先起草一份谨慎的回复，审核助手再检查是否擅自承诺价格或开始时间。')}</p>
                  <blockquote className="onboarding-inquiry-card">
                    <span>{t('虚构客户咨询')}</span>
                    <p>{t('你好，我是 Harbor Bakery 的 Maya。我需要每月维护网站，预算是每月 500 美元，希望下周开始。请问包含哪些服务？')}</p>
                    <small>{t('固定演示内容 · 不包含真实客户信息')}</small>
                  </blockquote>
                </>
              ) : (
                <p>{plan.plan?.summary}</p>
              )}
              <div className="onboarding-plan-facts">
                <div><span>{t('协作团队')}</span><strong>{t('业务助手 + 审核助手')}</strong></div>
                <div><span>{t('保存前')}</span><strong>{t('分别询问 · 预计 2 次')}</strong></div>
                <div><span>{t('你会得到')}</span><strong>{t('回复草稿 + 审核结果')}</strong></div>
              </div>
              <p>{t('两位助手在保存各自结果前都会暂停。如果出现预期两次本地保存之外的请求，请拒绝并停止。')}</p>
              <div className="onboarding-agent-list">
                {plan.plan?.agents.map((agent) => (
                  <div key={agent.name}>
                    <Bot size={16} />
                    <span>
                      <strong>{agent.name === 'Business Assistant' ? t('业务助手') : t('审核助手')}</strong>
                      <small>
                        {agent.name === 'Business Assistant'
                          ? t('根据虚构询价生成一份不擅自承诺价格或开始时间的回复草稿。')
                          : t('检查回复中的承诺风险、待确认问题和草稿状态。')}
                      </small>
                    </span>
                  </div>
                ))}
              </div>
              <details className="onboarding-technical-details">
                <summary>{t('技术详情')}</summary>
                <p>{t('方案指纹用于确认执行的正是你刚刚审阅的版本。')}</p>
                <code className="onboarding-hash">SHA-256 {plan.plan_sha256}</code>
              </details>
              <button
                className="primary-button"
                type="button"
                disabled={!!busy}
                onClick={() => void confirmFirstWork()}
              >
                {busy === 'confirm-work' ? <LoaderCircle className="spin" size={16} /> : <ShieldCheck size={16} />}
                {t('生成客户回复')}
              </button>
            </section>
          ) : terminalFailure ? (
            <OnboardingMessage
              icon={<AlertTriangle size={24} />}
              tone="danger"
              title={t('首个 Work 未完成')}
              detail={plan.execution?.error || t('失败证据已保留。重试会创建新的不可变运行，不会覆盖本次记录。')}
            >
              <button className="secondary-button" type="button" onClick={() => void prepareFirstWork()}>
                <RefreshCw size={16} />{t('创建新的重试')}
              </button>
            </OnboardingMessage>
          ) : evidenceReady ? (
            <section className="onboarding-panel onboarding-evidence">
              <span className="onboarding-panel-icon success"><FileCheck2 size={24} /></span>
              <h2>{customerReplyPlan ? t('这是为客户准备的回复草稿') : t('审阅首个 Work 的证据')}</h2>
              <p>
                {customerReplyPlan
                  ? t('这只是虚构场景的本地草稿。请先阅读回复和审核结果，再完成首次设置。')
                  : t('运行已经结束，但业务结果仍未自动标记为已验证。请核对下面的 artifact 和摘要。')}
              </p>
              {customerReplyPlan && replyDraft ? (
                <section className="onboarding-reply-preview">
                  <header>
                    <span>{t('客户回复草稿')}</span>
                    <small>{t('仅为草稿 · 流程未请求发送')}</small>
                  </header>
                  <pre>{replyDraft}</pre>
                </section>
              ) : customerReplyPlan ? (
                <div className="onboarding-progress-note">
                  <LoaderCircle className="spin" size={16} />
                  {t('正在读取已登记的回复草稿')}
                </div>
              ) : null}
              {customerReplyPlan && customerEvidenceVisible ? (
                <div className="onboarding-review-checks">
                  <div><CheckCircle2 size={16} /><span>{t('包含需要向客户确认的问题')}</span></div>
                  <div><CheckCircle2 size={16} /><span>{t('没有擅自确认价格')}</span></div>
                  <div><CheckCircle2 size={16} /><span>{t('没有擅自确认开始时间')}</span></div>
                  <div><CheckCircle2 size={16} /><span>{t('交付请求：否')}</span></div>
                </div>
              ) : customerReplyPlan && reviewContent ? (
                <div className="onboarding-inline-error">
                  {t('审核结果与已登记草稿不一致；不能完成首次设置。')}
                </div>
              ) : null}
              <details className="onboarding-technical-details">
                <summary>{t('技术证据')}</summary>
                <div className="onboarding-artifact-list">
                  {artifacts.map((artifact) => (
                    <div key={artifact.name}>
                      <FileCheck2 size={17} />
                      <span>
                        <strong>
                          {customerReplyPlan
                            ? t(artifact.name === 'first-work.json' ? '客户回复草稿' : '审核结果')
                            : artifact.name}
                        </strong>
                        <code>SHA-256 {artifact.sha256 || t('尚未注册')}</code>
                      </span>
                      <small>{artifact.evidence_status}</small>
                    </div>
                  ))}
                </div>
              </details>
              <div className="onboarding-boundary">
                <ShieldCheck size={17} />
                <strong>
                  {customerReplyPlan
                    ? t('合成客户回复演示尚待人工确认；它不代表任何真实客户结果。')
                    : t('技术演示尚待验证；不会据此评估任何真实业务结果。')}
                </strong>
              </div>
              {!artifactsLoaded ? (
                <div className="onboarding-progress-note">
                  <LoaderCircle className="spin" size={16} />
                  {t('正在检查可审阅的证据')}
                </div>
              ) : incompleteTerminalEvidence ? (
                <div className="onboarding-recovery">
                  <div className="onboarding-inline-error">
                    {t('上次运行在恢复前结束，没有留下完整可审阅的文件。旧记录会保留，但不能据此完成首次设置。')}
                  </div>
                  <button
                    className="secondary-button"
                    type="button"
                    disabled={!!busy}
                    onClick={() => void prepareFirstWork(false, true)}
                  >
                    {busy === 'prepare-work'
                      ? <LoaderCircle className="spin" size={16} />
                      : <RefreshCw size={16} />}
                    {t('保留旧记录并创建新的客户示例')}
                  </button>
                </div>
              ) : null}
              <label className="onboarding-check">
                <input
                  type="checkbox"
                  checked={reviewConfirmed}
                  disabled={!evidenceReviewable}
                  onChange={(event) => setReviewConfirmed(event.target.checked)}
                />
                <span>
                  {customerReplyPlan
                    ? t('我已阅读回复草稿和审核结果，并理解这只是虚构演示')
                    : t('我已审阅 artifact 名称、SHA-256 和技术演示边界')}
                </span>
              </label>
              <button
                className="primary-button"
                type="button"
                disabled={!reviewConfirmed || !evidenceReviewable || !!busy}
                onClick={() => void signoff()}
              >
                {busy === 'signoff' ? <LoaderCircle className="spin" size={16} /> : <CheckCircle2 size={16} />}
                {t('完成首次设置')}
              </button>
            </section>
          ) : (
            <section className="onboarding-panel onboarding-running">
              <span className="onboarding-panel-icon"><Activity size={24} /></span>
              <h2>{customerReplyPlan ? t('正在准备客户回复') : t('首个 Work 正在运行')}</h2>
              <p>
                {customerReplyPlan
                  ? t('业务助手正在起草回复，审核助手随后检查承诺风险。这个流程没有客户发送步骤。')
                  : t('Writer 与 Verifier 正在 App 管理的工作目录中生成并核验技术演示 artifact。')}
              </p>
              <div className="onboarding-run-overview">
                <div className="onboarding-run-head">
                  <div role="status" aria-live="polite" aria-atomic="true">
                    <strong>
                      {runProgress.observed && activeRunStage
                        ? t('第 {current} / {total} 步 · {label}', {
                          current: activeRunStage.order,
                          total: runProgress.total,
                          label: runStageLabel(activeRunStage.order),
                        })
                        : t('正在连接本地运行状态')}
                    </strong>
                    <span>{t('助手已上报完成 {completed} / {total}', {
                      completed: runProgress.completed,
                      total: runProgress.total,
                    })}</span>
                  </div>
                  <div className="onboarding-run-timing">
                    <Clock3 size={15} />
                    <span>
                      {runProgress.elapsedSeconds === null
                        ? t('正在启动')
                        : t(plan?.execution?.dispatched_at ? '已用时 {duration}' : '启动已用时 {duration}', {
                          duration: formatExecutionElapsed(runProgress.elapsedSeconds, language),
                        })}
                      {runProgress.estimateMinutes !== null
                        ? t(' · 方案预计约 {minutes} 分钟', { minutes: runProgress.estimateMinutes })
                        : ''}
                    </span>
                  </div>
                </div>

                <div
                  className="onboarding-run-track"
                  role="img"
                  aria-label={t('助手已上报完成 {completed} / {total}', {
                    completed: runProgress.completed,
                    total: runProgress.total,
                  })}
                >
                  {runProgress.stages.map((stage) => (
                    <span className={stage.observed ? stage.tone : 'neutral'} key={stage.order} />
                  ))}
                </div>

                <div className="onboarding-run-stages">
                  {runProgress.stages.map((stage) => (
                    <div className={`${stage.tone} ${stage.observed ? 'observed' : ''}`} key={stage.order}>
                      <span className="onboarding-run-stage-icon">
                        {stage.status === 'completed' ? <CheckCircle2 size={18} />
                          : stage.status === 'running' ? <LoaderCircle className="spin" size={18} />
                            : stage.status === 'failed' || stage.status === 'unknown' ? <AlertTriangle size={18} />
                              : stage.status === 'blocked' ? <Clock3 size={18} />
                                : <Circle size={15} />}
                      </span>
                      <span>
                        <strong>{runStageLabel(stage.order)}</strong>
                        <small>{runStageStatus(stage)}</small>
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {pendingApproval ? (
                <div
                  className="onboarding-approval"
                  ref={approvalRef}
                  role="alert"
                  tabIndex={-1}
                >
                  <strong>{pendingApproval.title}</strong>
                  <p>{pendingApproval.summary}</p>
                  {customerReplyPlan && (
                    <p className="onboarding-approval-warning">
                      {t('只批准写入 App 空白工作区的 first-work.json 或 verification.json；其他请求一律拒绝。')}
                    </p>
                  )}
                  <div className="onboarding-actions">
                    <button
                      className="secondary-button danger-button"
                      type="button"
                      disabled={!!busy}
                      onClick={() => void decideFirstApproval('reject')}
                    >
                      {t('拒绝')}
                    </button>
                    <button
                      className="primary-button"
                      type="button"
                      disabled={!!busy}
                      onClick={() => void decideFirstApproval('approve')}
                    >
                      {busy === 'approval-approve' ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}
                      {t(customerReplyPlan ? '批准这次本地保存' : '批准本次写入')}
                    </button>
                  </div>
                </div>
              ) : (
                <div
                  className={`onboarding-current-activity ${
                    plan?.status === 'awaiting_approval' || plan?.status === 'awaiting_input'
                      ? 'attention'
                      : ''
                  }`}
                  role="status"
                  aria-live="polite"
                >
                  <span>
                    {plan?.status === 'awaiting_approval' || plan?.status === 'awaiting_input'
                      ? <ShieldCheck size={20} />
                      : <LoaderCircle className="spin" size={20} />}
                  </span>
                  <div>
                    <strong>{currentActivity.title}</strong>
                    <p>{currentActivity.detail}</p>
                  </div>
                </div>
              )}

              {pollFailures >= 4 ? (
                <div className="onboarding-run-warning" role="alert">
                  <AlertTriangle size={17} />
                  <span>
                    <strong>{t('本地状态连接暂时中断，正在重连')}</strong>
                    <small>{t('最后一次可信进度已保留；请勿重复启动这个 Work。')}</small>
                  </span>
                </div>
              ) : !runProgress.available ? (
                <div className="onboarding-run-warning">
                  <AlertTriangle size={17} />
                  <span>
                    <strong>{t('暂时读不到本机运行信号')}</strong>
                    <small>{t('OpsWitness 正在自动重试；这不表示 Work 失败。')}</small>
                  </span>
                </div>
              ) : runProgress.slow ? (
                <div className="onboarding-run-warning">
                  <Clock3 size={17} />
                  <span>
                    <strong>{t('这一步比预计更久')}</strong>
                    <small>{t('仍在收到运行信号，无需重新开始。')}</small>
                  </span>
                </div>
              ) : runProgress.estimateExceeded ? (
                <div className="onboarding-run-warning">
                  <Clock3 size={17} />
                  <span>
                    <strong>{t('运行时间超过了方案预估')}</strong>
                    <small>{t('OpsWitness 仍在检查状态；请勿重复启动。')}</small>
                  </span>
                </div>
              ) : null}

              <div className="onboarding-run-next">
                <ShieldCheck size={16} />
                <span>
                  {customerReplyPlan
                    ? t('接下来：每次本地保存前都会询问你；预计 2 次。没有客户发送步骤。')
                    : t('接下来：每次文件写入前都会询问你；预计 2 次。')}
                </span>
              </div>
              <button
                className="secondary-button onboarding-check-status"
                type="button"
                disabled={!!busy}
                onClick={() => void checkFirstWork()}
              >
                {busy === 'refresh-work' ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />}
                {t('立即检查状态')}
              </button>
            </section>
          )}

          {error && <div className="onboarding-inline-error" role="alert">{error}</div>}
        </div>

        <footer className="onboarding-footer">
          <span><ShieldCheck size={14} />{t('本地优先 · 单用户 · 无托管 SaaS')}</span>
          <small>{t('模型请求只会发送给你选择并登录的提供商。')}</small>
        </footer>
      </section>
      {helpOpen && <OnboardingHelp onClose={() => setHelpOpen(false)} />}
    </main>
  );
}

function OnboardingMessage({
  icon,
  title,
  detail,
  tone = 'neutral',
  children,
}: {
  icon: React.ReactNode;
  title: string;
  detail: string;
  tone?: 'neutral' | 'danger';
  children?: React.ReactNode;
}) {
  return (
    <section className={`onboarding-panel onboarding-message ${tone}`}>
      <span className="onboarding-panel-icon">{icon}</span>
      <h2>{title}</h2>
      <p>{detail}</p>
      {children ? <div className="onboarding-actions">{children}</div> : null}
    </section>
  );
}
