import {
  Activity,
  AlertTriangle,
  Check,
  Circle,
  Clock3,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { checkWorkRecovery, decideWorkRecovery, getWorkRecovery } from './api';
import { useLanguage } from './language';
import {
  formatRecoveryCooldown,
  recoveryIdleCopy,
  recoverySafeView,
  shouldShowRecoveryPanel,
} from './recovery-agent-model.js';
import type { PlanRecord, RecoveryState } from './types';

function formatObservedTime(value: string | null, language: 'en' | 'zh'): string {
  if (!value) return '—';
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return '—';
  return new Intl.DateTimeFormat(language === 'zh' ? 'zh-CN' : 'en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(parsed));
}

export function RecoveryAgentPanel({
  planId,
  workStatus,
  recovery,
  onRepairWorkCreated,
}: {
  planId: string;
  workStatus: string;
  recovery?: RecoveryState | null;
  onRepairWorkCreated?: (record: PlanRecord) => void;
}) {
  const { language, t } = useLanguage();
  const [current, setCurrent] = useState<RecoveryState | null>(recovery || null);
  const [checking, setChecking] = useState(false);
  const [proposalOpen, setProposalOpen] = useState(false);
  const [proposalConfirmed, setProposalConfirmed] = useState(false);
  const [proposalBusy, setProposalBusy] = useState(false);
  const [error, setError] = useState('');
  const [nowMs, setNowMs] = useState(Date.now());

  useEffect(() => {
    if (recovery) setCurrent(recovery);
  }, [recovery]);

  useEffect(() => {
    setProposalOpen(false);
    setProposalConfirmed(false);
    setProposalBusy(false);
    setError('');
  }, [planId]);

  useEffect(() => {
    const active = [
      'running',
      'awaiting_approval',
      'awaiting_input',
      'pause_requested',
      'paused',
      'resuming',
    ].includes(workStatus);
    const recoveryInProgress = current
      && !['idle', 'recovered', 'failed', 'escalated'].includes(current.state);
    if (!active && !recoveryInProgress) return;
    let cancelled = false;
    let pollInFlight = false;
    const poll = async () => {
      if (pollInFlight) return;
      pollInFlight = true;
      try {
        const next = await getWorkRecovery(planId);
        if (!cancelled) {
          setCurrent(next);
          setError('');
        }
      } catch {
        // Keep the last verified state visible. Manual retry remains a distinct POST.
      } finally {
        pollInFlight = false;
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [current?.state, planId, workStatus]);

  useEffect(() => {
    if (!current?.cooldown_until) return;
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [current?.cooldown_until]);

  const view = useMemo(() => recoverySafeView(current, nowMs), [current, nowMs]);
  if (!view || !shouldShowRecoveryPanel(workStatus, current)) return null;

  const retry = async () => {
    if (!view.canCheckAgain || checking) return;
    setChecking(true);
    setError('');
    try {
      setCurrent(await checkWorkRecovery(planId));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('恢复检查暂时无法完成'));
    } finally {
      setChecking(false);
    }
  };

  const createRepairWork = async () => {
    if (
      proposalBusy
      || !proposalConfirmed
      || current?.recommended_action !== 'create_repair_work'
      || !current.proposal_sha256
      || current.repair_work_id
    ) return;
    setProposalBusy(true);
    setError('');
    try {
      const result = await decideWorkRecovery(planId, current.proposal_sha256);
      setCurrent(result.recovery);
      setProposalOpen(false);
      setProposalConfirmed(false);
      onRepairWorkCreated?.(result.repair_work);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('修复 Work 创建失败'));
    } finally {
      setProposalBusy(false);
    }
  };

  const compact = ['idle', 'observing'].includes(view.state);
  const compactLabel = workStatus === 'awaiting_approval'
    ? '等待你的审批'
    : workStatus === 'awaiting_input'
      ? '等待你补充信息'
      : workStatus === 'paused'
        ? 'Work 已暂停'
        : workStatus === 'running'
          ? '运行监测中'
          : view.label;
  const needsOperator = Boolean(view.action?.operatorActionRequired);
  const requiresApproval = Boolean(view.action?.operatorApprovalRequired);
  const canCreateRepairWork = requiresApproval
    && view.action?.action === 'create_repair_work'
    && ['proposal_ready', 'escalated'].includes(view.state)
    && Boolean(current?.proposal_sha256)
    && !current?.repair_work_id;
  const cooldown = formatRecoveryCooldown(view.cooldownRemainingSeconds, language);

  return (
    <section
      className={`recovery-agent-panel ${view.tone} ${compact ? 'compact' : ''}`}
      aria-label={t('运行恢复')}
      aria-live="polite"
    >
      <header className="recovery-agent-heading">
        <span className={`recovery-agent-icon ${view.tone}`}>
          {view.state === 'recovered'
            ? <Check size={18} />
            : ['failed', 'escalated'].includes(view.state)
              ? <AlertTriangle size={18} />
              : compact
                ? <ShieldCheck size={18} />
                : <LoaderCircle size={18} className={['observing', 'diagnosing', 'auto_recovering', 'verifying'].includes(view.state) ? 'spin' : ''} />}
        </span>
        <div>
          <span className="section-kicker">{t('受治理的 Recovery Agent')}</span>
          <strong>{t(compactLabel)}</strong>
          <small>{t(compact ? recoveryIdleCopy(workStatus) : view.detail)}</small>
        </div>
        <span className={`recovery-agent-state ${view.tone}`}>
          <span className="status-dot" />
          {t(compact
            ? workStatus === 'paused'
              ? '已暂停'
              : ['awaiting_approval', 'awaiting_input'].includes(workStatus)
                ? '等待你'
                : '守护中'
            : view.state === 'recovered'
              ? '已恢复运行'
              : '恢复流程')}
        </span>
      </header>

      {compact ? (
        <div className="recovery-agent-idle-note">
          <Clock3 size={14} />
          <span>{t(recoveryIdleCopy(workStatus))}</span>
        </div>
      ) : (
        <>
          <ol className="recovery-agent-timeline" aria-label={t('恢复进度')}>
            {view.timeline.map((step) => (
              <li key={step.key} className={step.status}>
                <span>{step.status === 'completed' ? <Check size={12} /> : <Circle size={10} />}</span>
                <small>{t(step.label)}</small>
              </li>
            ))}
          </ol>

          <div className="recovery-agent-grid">
            <section>
              <div className="recovery-agent-section-title">
                <Activity size={14} />
                <strong>{t('当前证据')}</strong>
              </div>
              <dl className="recovery-agent-facts">
                <div>
                  <dt>{t('最近状态观测')}</dt>
                  <dd>{formatObservedTime(view.lastObservedAt, language)}</dd>
                </div>
                <div>
                  <dt>{t('未变化起点')}</dt>
                  <dd>{formatObservedTime(view.stalledSince, language)}</dd>
                </div>
                <div>
                  <dt>{t('恢复尝试')}</dt>
                  <dd>{t('{used}/2 次', { used: view.attemptCount })}</dd>
                </div>
                {view.verificationDeadline && (
                  <div>
                    <dt>{t('等待新证据至')}</dt>
                    <dd>{formatObservedTime(view.verificationDeadline, language)}</dd>
                  </div>
                )}
              </dl>
              {view.reasons.length > 0 && (
                <ul className="recovery-agent-reasons">
                  {view.reasons.map((reason) => <li key={reason.code}>{t(reason.label)}</li>)}
                </ul>
              )}
            </section>

            <section>
              <div className="recovery-agent-section-title">
                <Sparkles size={14} />
                <strong>{t('模型诊断摘要')}</strong>
              </div>
              <p className="recovery-agent-diagnosis">
                {view.diagnosisSummary || t('正在等待受限诊断结果。')}
              </p>
              {view.lastError && (
                <p className="recovery-agent-error"><AlertTriangle size={13} />{t(view.lastError)}</p>
              )}
            </section>
          </div>

          {view.action && (
            <div className={`recovery-agent-action ${needsOperator ? 'operator' : 'automatic'}`}>
              <span>{needsOperator ? <AlertTriangle size={16} /> : <RefreshCw size={16} />}</span>
              <div>
                <small>{t(requiresApproval
                  ? '需要人工批准'
                  : needsOperator
                    ? '需要人工处理'
                    : '允许的自动动作')}</small>
                <strong>{t(view.repairWorkCreated ? '待审核 Repair Work 已创建' : view.action.label)}</strong>
                <p>{t(view.repairWorkCreated
                  ? '新 Work 仍需审阅和确认；尚未执行任何修复。'
                  : view.action.detail)}</p>
                {needsOperator && view.action.action === 'create_repair_work' && !view.repairWorkCreated && (
                  <>
                    <em>{t('批准后也只会创建一份待审核 Repair Work；不会直接改文件、运行命令或宣称问题已修复。')}</em>
                    {canCreateRepairWork && !proposalOpen && (
                      <button
                        className="secondary-button recovery-agent-proposal-button"
                        type="button"
                        onClick={() => {
                          setProposalConfirmed(false);
                          setProposalOpen(true);
                        }}
                      >
                        {t('创建待审核 Repair Work')}
                      </button>
                    )}
                    {canCreateRepairWork && proposalOpen && (
                      <div className="recovery-agent-proposal-confirmation">
                        <strong>{t('确认创建一份新的修复 Work？')}</strong>
                        <p>{t('它只会进入规划和人工审核，不会自动执行，也不会读取原 Work 的文件、私密日志或凭据。')}</p>
                        <label>
                          <input
                            type="checkbox"
                            checked={proposalConfirmed}
                            disabled={proposalBusy}
                            onChange={(event) => setProposalConfirmed(event.target.checked)}
                          />
                          <span>{t('我确认只创建待审核方案，后续执行仍需单独确认和审批')}</span>
                        </label>
                        <div>
                          <button
                            className="text-button"
                            type="button"
                            disabled={proposalBusy}
                            onClick={() => {
                              setProposalOpen(false);
                              setProposalConfirmed(false);
                            }}
                          >
                            {t('取消')}
                          </button>
                          <button
                            className="primary-button"
                            type="button"
                            disabled={!proposalConfirmed || proposalBusy}
                            onClick={() => void createRepairWork()}
                          >
                            {proposalBusy
                              ? <LoaderCircle size={15} className="spin" />
                              : <ShieldCheck size={15} />}
                            {t(proposalBusy ? '正在创建待审核 Work' : '确认创建待审核 Repair Work')}
                          </button>
                        </div>
                      </div>
                    )}
                  </>
                )}
                {view.repairWorkCreated && (
                  <span className="recovery-agent-repair-created">
                    <Check size={13} />{t('待审核 Repair Work 已创建；尚未执行。')}
                  </span>
                )}
              </div>
            </div>
          )}

          {(view.canCheckAgain || cooldown || view.attemptsRemaining === 0) && (
            <div className="recovery-agent-footer">
              <span>
                {cooldown
                  ? t('{time} 后可再次检查', { time: cooldown })
                  : view.attemptsRemaining === 0
                    ? t('已达到恢复上限，等待人工处理')
                    : t('还可手动检查 {count} 次', { count: view.attemptsRemaining })}
              </span>
              {view.canCheckAgain && (
                <button
                  className="secondary-button"
                  type="button"
                  disabled={checking}
                  onClick={() => void retry()}
                >
                  {checking ? <LoaderCircle size={15} className="spin" /> : <RefreshCw size={15} />}
                  {t(checking ? '正在重新检查' : '重新检查')}
                </button>
              )}
            </div>
          )}
          {error && <div className="recovery-agent-request-error"><AlertTriangle size={14} />{error}</div>}

          <div className="recovery-agent-boundary">
            <ShieldCheck size={13} />
            <span>{t('这里只显示受限状态和摘要，不显示隐藏推理、原始日志正文或命令参数。运行恢复也不代表业务结果已验证。')}</span>
          </div>
        </>
      )}
    </section>
  );
}
