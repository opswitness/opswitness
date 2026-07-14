import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Bot,
  CalendarClock,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  ClipboardCheck,
  Clock3,
  Database,
  ExternalLink,
  FileUp,
  FileCheck2,
  FolderOpen,
  GitCompareArrows,
  Inbox,
  LayoutDashboard,
  ListTodo,
  LoaderCircle,
  Mail,
  MessageSquare,
  Play,
  Plus,
  PencilLine,
  RefreshCw,
  RotateCcw,
  Send,
  Server,
  Settings,
  ShieldCheck,
  Sparkles,
  Users,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  confirmPlan,
  connectProvider,
  configureMailOAuthClient,
  configureTelegram,
  disableTelegram,
  disableMail,
  decideApproval,
  getMailAuthorization,
  getMailAuthorizationStatus,
  getMailSummary,
  getPlan,
  getProviderConnection,
  getTelegramStatus,
  loadBootstrap,
  requestMailAuthorization,
  requestMailSummary,
  requestPlan,
  revisePlan,
  testTelegram,
} from './api';
import type {
  Bootstrap,
  AIProvider,
  ApprovalCard,
  Integration,
  MailAuthorizationJob,
  MailAuthorizationStatus,
  MailSummaryJob,
  PlanRecord,
  ProviderConnectionJob,
  RunRecord,
  TaskPlan,
  TelegramSetupStatus,
} from './types';

type View = 'workspace' | 'dashboard' | 'tasks' | 'approvals' | 'evidence' | 'settings';

const cadenceOptions = [
  { value: 'once', label: '单次' },
  { value: 'daily', label: '每天' },
  { value: 'weekdays', label: '工作日' },
  { value: 'weekly', label: '每周' },
  { value: 'manual', label: '手动' },
] as const;

const statusLabel: Record<string, string> = {
  planning: '规划中',
  ready: '待确认',
  confirmed: '已确认',
  dispatching: '启动中',
  queued: '排队中',
  running: '运行中',
  awaiting_approval: '等待审批',
  completed_unverified: '执行完成 · 待核验',
  failed: '失败',
  succeeded: '成功',
};

const roleLabel: Record<string, string> = {
  lead: '负责人',
  researcher: '研究',
  operator: '执行',
  reviewer: '复核',
  reporter: '汇报',
  specialist: '专家',
};

const runtimeLabel: Record<string, string> = {
  claude_code: 'Claude',
  codex_cli: 'OpenAI',
  aion_cli: '本地 AI',
};

function formatTime(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
}

function shortId(value?: string | null): string {
  if (!value) return '—';
  return value.length > 14 ? `${value.slice(0, 7)}…${value.slice(-5)}` : value;
}

function statusTone(status: string): string {
  if (['failed', 'offline'].includes(status)) return 'danger';
  if (['awaiting_approval', 'attention', 'setup', 'ready'].includes(status)) return 'warning';
  if (['running', 'planning', 'dispatching', 'queued', 'confirmed'].includes(status)) return 'active';
  if (['completed_unverified'].includes(status)) return 'neutral';
  return 'success';
}

function inferCadence(objective: string): 'once' | 'daily' | 'weekdays' | 'weekly' | 'manual' {
  const text = objective.toLocaleLowerCase();
  if (/(工作日|weekday)/.test(text)) return 'weekdays';
  if (/(每天|每日|天天|daily)/.test(text)) return 'daily';
  if (/(每周|周报|weekly)/.test(text)) return 'weekly';
  if (/(手动|按需|manual)/.test(text)) return 'manual';
  return 'once';
}

function App() {
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null);
  const [view, setView] = useState<View>('workspace');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [activePlan, setActivePlan] = useState<PlanRecord | null>(null);
  const [workspaceRevision, setWorkspaceRevision] = useState(0);
  const [mailJob, setMailJob] = useState<MailSummaryJob | null>(null);
  const [mailSetupOpen, setMailSetupOpen] = useState(false);
  const [telegramSetupOpen, setTelegramSetupOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const refresh = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const next = await loadBootstrap();
      setBootstrap(next);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : '控制台状态读取失败');
    } finally {
      if (!quiet) setLoading(false);
    }
  }, []);

  const refreshAfterIntegrationChange = useCallback(async () => {
    await refresh(true);
  }, [refresh]);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(true), 15000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const mergePlan = useCallback((record: PlanRecord) => {
    setActivePlan(record);
    setBootstrap((current) => {
      if (!current) return current;
      const exists = current.plans.some((row) => row.plan_id === record.plan_id);
      return {
        ...current,
        plans: exists
          ? current.plans.map((row) => (row.plan_id === record.plan_id ? record : row))
          : [record, ...current.plans],
      };
    });
  }, []);

  const activeParentPlan = useMemo(() => {
    if (!activePlan?.parent_plan_id || !bootstrap) return null;
    return bootstrap.plans.find((row) => row.plan_id === activePlan.parent_plan_id)?.plan || null;
  }, [activePlan?.parent_plan_id, bootstrap]);

  useEffect(() => {
    if (!activePlan) return;
    if (!['planning', 'confirmed', 'dispatching', 'running', 'awaiting_approval'].includes(activePlan.status)) {
      return;
    }
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await getPlan(activePlan.plan_id);
        if (!cancelled) mergePlan(next);
      } catch {
        // The next dashboard refresh keeps the system state visible.
      }
    };
    const timer = window.setInterval(
      () => void poll(),
      activePlan.status === 'planning' ? 1000 : 2500,
    );
    void poll();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activePlan?.plan_id, activePlan?.status, mergePlan]);

  useEffect(() => {
    if (!mailJob || mailJob.status !== 'running') return;
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await getMailSummary(mailJob.job_id);
        if (!cancelled) setMailJob(next);
      } catch {
        // Keep the current running state until the next poll.
      }
    };
    const timer = window.setInterval(() => void poll(), 2000);
    void poll();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [mailJob?.job_id, mailJob?.status]);

  const openNewTask = () => {
    setActivePlan(null);
    setDrawerOpen(true);
  };

  const openPlan = (plan: PlanRecord) => {
    setActivePlan(plan);
    setDrawerOpen(true);
  };

  const startWorkspaceTask = () => {
    setActivePlan(null);
    setDrawerOpen(false);
    setWorkspaceRevision((value) => value + 1);
    setView('workspace');
  };

  const changeView = (next: View) => {
    setDrawerOpen(false);
    setView(next);
  };

  const title = {
    workspace: '工作台',
    dashboard: '总控制台',
    tasks: '任务',
    approvals: '审批',
    evidence: '证据',
    settings: '连接',
  }[view];

  return (
    <div className="app-shell">
      <Sidebar view={view} onChange={changeView} />
      <main className="main-area">
        <header className="topbar">
          <div className="topbar-title">
            <span className="eyebrow">QUARTERDECK</span>
            <h1>{title}</h1>
          </div>
          <div className="topbar-actions">
            <IntegrationRow integrations={bootstrap?.system} />
            <button className="icon-button" type="button" title="刷新" onClick={() => void refresh()}>
              <RefreshCw size={17} className={loading ? 'spin' : ''} />
            </button>
            <button
              className="primary-button"
              type="button"
              onClick={view === 'workspace' ? startWorkspaceTask : openNewTask}
            >
              <Plus size={17} />
              {view === 'workspace' ? '新对话' : '新建任务'}
            </button>
          </div>
        </header>

        {error && (
          <div className="alert-banner" role="alert">
            <AlertTriangle size={17} />
            <span>{error}</span>
            <button type="button" onClick={() => void refresh()}>
              重试
            </button>
          </div>
        )}

        <div className={view === 'workspace' ? 'page-content workspace-page' : 'page-content'}>
          {loading && !bootstrap ? (
            <LoadingState />
          ) : bootstrap ? (
            <>
              {view === 'workspace' && (
                <WorkspaceView
                  key={workspaceRevision}
                  record={activePlan}
                  previousPlan={activeParentPlan}
                  onPlan={async (body) => {
                    mergePlan(await requestPlan(body));
                  }}
                  onRevise={async (record, instruction) => {
                    mergePlan(await revisePlan(record.plan_id, instruction));
                  }}
                  onConfirm={async (record) => {
                    if (!record.plan_sha256) throw new Error('方案哈希缺失');
                    mergePlan(await confirmPlan(record.plan_id, record.plan_sha256));
                  }}
                  onRestart={() => setActivePlan(null)}
                />
              )}
              {view === 'dashboard' && (
                <Dashboard
                  data={bootstrap}
                  mailJob={mailJob}
                  onMail={async () => setMailJob(await requestMailSummary())}
                  onMailSetup={() => setMailSetupOpen(true)}
                  onOpenPlan={openPlan}
                  onNewTask={openNewTask}
                  onOpenApprovals={() => changeView('approvals')}
                />
              )}
              {view === 'tasks' && (
                <TasksView plans={bootstrap.plans} onOpen={openPlan} onNew={openNewTask} />
              )}
              {view === 'approvals' && (
                <ApprovalsView data={bootstrap} onChanged={refreshAfterIntegrationChange} />
              )}
              {view === 'evidence' && <EvidenceView runs={bootstrap.recent_runs} data={bootstrap} />}
              {view === 'settings' && (
                <ConnectionsView
                  data={bootstrap}
                  onMailSetup={() => setMailSetupOpen(true)}
                  onTelegramSetup={() => setTelegramSetupOpen(true)}
                  onChanged={refreshAfterIntegrationChange}
                />
              )}
            </>
          ) : null}
        </div>
      </main>

      <TaskDrawer
        open={drawerOpen}
        record={activePlan}
        previousPlan={activeParentPlan}
        onClose={() => setDrawerOpen(false)}
        onPlan={async (body) => {
          const record = await requestPlan(body);
          mergePlan(record);
        }}
        onRevise={async (record, instruction) => {
          mergePlan(await revisePlan(record.plan_id, instruction));
        }}
        onConfirm={async (record) => {
          if (!record.plan_sha256) throw new Error('方案哈希缺失');
          mergePlan(await confirmPlan(record.plan_id, record.plan_sha256));
        }}
        onRestart={() => setActivePlan(null)}
      />
      <MailSetupDialog
        open={mailSetupOpen}
        onClose={() => setMailSetupOpen(false)}
        onChanged={refreshAfterIntegrationChange}
      />
      <TelegramSetupDialog
        open={telegramSetupOpen}
        onClose={() => setTelegramSetupOpen(false)}
        onChanged={refreshAfterIntegrationChange}
      />
    </div>
  );
}

function Sidebar({ view, onChange }: { view: View; onChange: (view: View) => void }) {
  const items = [
    { id: 'workspace' as const, label: '工作台', icon: MessageSquare },
    { id: 'dashboard' as const, label: '概览', icon: LayoutDashboard },
    { id: 'tasks' as const, label: '任务', icon: ListTodo },
    { id: 'approvals' as const, label: '审批', icon: ClipboardCheck },
    { id: 'evidence' as const, label: '证据', icon: FileCheck2 },
    { id: 'settings' as const, label: '连接', icon: Settings },
  ];
  return (
    <aside className="sidebar" aria-label="主导航">
      <div className="brand-mark" aria-label="Quarterdeck">QD</div>
      <nav>
        {items.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            className={view === id ? 'nav-button active' : 'nav-button'}
            title={label}
            aria-label={label}
            onClick={() => onChange(id)}
          >
            <Icon size={20} />
            <span>{label}</span>
          </button>
        ))}
      </nav>
      <div className="sidebar-shield" title="本地可信模式">
        <ShieldCheck size={18} />
      </div>
    </aside>
  );
}

function IntegrationRow({ integrations }: { integrations?: Record<string, Integration> }) {
  if (!integrations) return null;
  return (
    <div className="integration-row" aria-label="服务状态">
      {['ai', 'governance', 'evidence'].map((key) => {
        const item = integrations[key];
        if (!item) return null;
        return (
          <span key={key} className="integration-pill" title={item.detail || item.label}>
            <span className={`status-dot ${statusTone(item.status)}`} />
            {item.label}
          </span>
        );
      })}
    </div>
  );
}

function WorkspaceView({
  record,
  previousPlan,
  onPlan,
  onRevise,
  onConfirm,
  onRestart,
}: {
  record: PlanRecord | null;
  previousPlan: TaskPlan | null;
  onPlan: (body: {
    objective: string;
    constraints: string;
    workspace: string;
    preferred_cadence: string;
  }) => Promise<void>;
  onRevise: (record: PlanRecord, instruction: string) => Promise<void>;
  onConfirm: (record: PlanRecord) => Promise<void>;
  onRestart: () => void;
}) {
  const [draft, setDraft] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [revisionOpen, setRevisionOpen] = useState(false);
  const [error, setError] = useState('');
  const quickStarts = [
    '每天早上汇总重要邮件，并列出需要回复的事项',
    '检查所有自动化任务的运行状态，并生成异常报告',
    '整理本周项目进展，输出下一步行动清单',
  ];

  useEffect(() => {
    setConfirmed(false);
    setRevisionOpen(false);
    setError('');
  }, [record?.plan_id, record?.status]);

  const locked = Boolean(
    record && !['failed', 'completed_unverified'].includes(record.status),
  );

  const submit = async () => {
    const objective = draft.trim();
    if (objective.length < 3 || submitting || locked) return;
    setSubmitting(true);
    setError('');
    try {
      await onPlan({
        objective,
        constraints: '',
        workspace: '',
        preferred_cadence: inferCadence(objective),
      });
      setDraft('');
    } catch (err) {
      setError(err instanceof Error ? err.message : '规划请求失败');
    } finally {
      setSubmitting(false);
    }
  };

  const confirm = async () => {
    if (!record || !confirmed || submitting) return;
    setSubmitting(true);
    setError('');
    try {
      await onConfirm(record);
    } catch (err) {
      setError(err instanceof Error ? err.message : '确认失败');
    } finally {
      setSubmitting(false);
    }
  };

  const revise = async (instruction: string) => {
    if (!record || submitting) return;
    setSubmitting(true);
    setError('');
    try {
      await onRevise(record, instruction);
    } catch (err) {
      setError(err instanceof Error ? err.message : '方案修改失败');
    } finally {
      setSubmitting(false);
    }
  };

  const restart = () => {
    setDraft('');
    onRestart();
  };

  return (
    <section className="workspace-shell" aria-label="AI 工作台">
      <div className="chat-thread" aria-live="polite">
        {!record ? (
          <div className="chat-empty">
            <div className="chat-empty-mark"><Sparkles size={24} /></div>
            <h2>今天要完成什么？</h2>
            <div className="quick-prompts">
              {quickStarts.map((prompt) => (
                <button key={prompt} type="button" onClick={() => setDraft(prompt)}>
                  <MessageSquare size={15} />
                  <span>{prompt}</span>
                  <ChevronRight size={15} />
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            <div className="chat-message user-message">
              <div className="chat-user-bubble">
                {record.objective}
                {record.parent_plan_id && record.revision_instruction && (
                  <small>修改要求：{record.revision_instruction}</small>
                )}
              </div>
              <div className="chat-avatar user-avatar">你</div>
            </div>
            <div className="chat-message assistant-message">
              <div className="chat-avatar assistant-avatar"><Bot size={17} /></div>
              <div className="chat-assistant-content">
                <div className="chat-assistant-heading">
                  <strong>Quarterdeck</strong>
                  <StatusBadge status={record.status} />
                </div>
                {record.status === 'planning' && (
                  <PlanningProgressView progress={record.planning_progress} />
                )}
                {record.status === 'ready' && record.plan && (
                  <PlanReview
                    plan={record.plan}
                    hash={record.plan_sha256 || ''}
                    showStatus={false}
                    previousPlan={previousPlan}
                    revisionNumber={record.revision_number}
                  />
                )}
                {['confirmed', 'dispatching', 'running', 'awaiting_approval', 'completed_unverified', 'failed'].includes(record.status) && (
                  <ExecutionView record={record} />
                )}
                {record.status === 'ready' && (
                  <div className="chat-confirm-panel">
                    {revisionOpen ? (
                      <RevisionComposer
                        submitting={submitting}
                        onCancel={() => setRevisionOpen(false)}
                        onSubmit={revise}
                      />
                    ) : (
                      <>
                        <label className="confirm-check">
                          <input
                            type="checkbox"
                            checked={confirmed}
                            onChange={(event) => setConfirmed(event.target.checked)}
                          />
                          <span><Check size={15} />确认此方案并启动受管执行</span>
                        </label>
                        <div className="confirm-actions revision-actions">
                          <button className="secondary-button" type="button" onClick={() => setRevisionOpen(true)}>
                            <PencilLine size={16} />修改方案
                          </button>
                          <button className="text-button" type="button" onClick={restart}>
                            <RotateCcw size={15} />重新开始
                          </button>
                          <button
                            className="primary-button"
                            type="button"
                            disabled={!confirmed || submitting}
                            onClick={() => void confirm()}
                          >
                            {submitting ? <LoaderCircle size={17} className="spin" /> : <Play size={17} />}
                            确认并运行
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                )}
                {error && <InlineError text={error} />}
              </div>
            </div>
          </>
        )}
      </div>

      <div className="chat-composer-shell">
        <form
          className="chat-composer"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <textarea
            aria-label="任务描述"
            value={draft}
            rows={3}
            maxLength={2000}
            disabled={locked || submitting}
            placeholder={locked ? '当前任务等待完成或确认' : '描述你想完成的任务…'}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                void submit();
              }
            }}
          />
          <div className="chat-composer-actions">
            <span><ShieldCheck size={14} />先规划，确认后运行</span>
            <button
              className="chat-send-button"
              type="submit"
              title="发送任务描述"
              aria-label="发送任务描述"
              disabled={draft.trim().length < 3 || submitting || locked}
            >
              {submitting ? <LoaderCircle size={18} className="spin" /> : <Send size={18} />}
            </button>
          </div>
        </form>
        {error && !record && <InlineError text={error} />}
      </div>
    </section>
  );
}

function Dashboard({
  data,
  mailJob,
  onMail,
  onMailSetup,
  onOpenPlan,
  onNewTask,
  onOpenApprovals,
}: {
  data: Bootstrap;
  mailJob: MailSummaryJob | null;
  onMail: () => Promise<void>;
  onMailSetup: () => void;
  onOpenPlan: (plan: PlanRecord) => void;
  onNewTask: () => void;
  onOpenApprovals: () => void;
}) {
  const healthDetail = data.fleet.coverage_error
    ? '配置无效'
    : data.fleet.coverage_status === 'none'
      ? '无 watchdog 覆盖'
      : data.fleet.coverage_status === 'partial'
        ? '覆盖不完整'
        : data.fleet.problem_jobs
          ? `${data.fleet.problem_jobs} 个需关注`
          : data.fleet.pending_projection
            ? '证据待投影'
            : '完整覆盖';
  return (
    <div className="dashboard-layout">
      <section className="metric-strip" aria-label="系统摘要">
        <Metric label="任务运行" value={String(data.fleet.runs)} detail={`${data.fleet.jobs} 个任务`} icon={Activity} />
        <Metric
          label="健康监控"
          value={`${data.fleet.healthy_jobs}/${data.fleet.monitored_jobs}`}
          detail={healthDetail}
          icon={CheckCircle2}
          tone={data.fleet.fleet_healthy ? 'success' : 'warning'}
        />
        <Metric
          label="待审批"
          value={data.approvals_available ? String(data.pending_approvals ?? 0) : '—'}
          detail={data.approvals_available ? 'Quarterdeck 审批队列' : '状态不可用'}
          icon={ClipboardCheck}
          tone={!data.approvals_available || data.pending_approvals ? 'warning' : 'neutral'}
        />
        <Metric
          label="投影积压"
          value={String(data.fleet.pending_projection)}
          detail={`${data.fleet.artifacts} 个 artifact`}
          icon={Database}
          tone={data.fleet.pending_projection ? 'warning' : 'success'}
        />
      </section>

      <div className="dashboard-grid">
        <section className="panel mail-panel">
          <div className="section-heading">
            <div>
              <span className="section-kicker">今天</span>
              <h2>邮箱摘要</h2>
            </div>
            <Mail size={20} />
          </div>
          <MailSummary data={data} job={mailJob} onRun={onMail} onSetup={onMailSetup} />
        </section>

        <section className="panel quick-panel">
          <div className="section-heading">
            <div>
              <span className="section-kicker">快捷入口</span>
              <h2>开始工作</h2>
            </div>
            <Sparkles size={20} />
          </div>
          <button className="quick-action" type="button" onClick={onNewTask}>
            <span className="quick-icon"><Plus size={20} /></span>
            <span>
              <strong>创建新任务</strong>
              <small>规划团队、节奏与检查点</small>
            </span>
            <ArrowRight size={18} />
          </button>
          <button className="quick-action" type="button" onClick={onOpenApprovals}>
            <span className="quick-icon"><ShieldCheck size={20} /></span>
            <span>
              <strong>治理状态</strong>
              <small>{!data.approvals_available
                ? '审批状态暂不可用'
                : data.pending_approvals
                  ? `${data.pending_approvals} 项等待处理`
                  : '当前无待审批项'}</small>
            </span>
            <ChevronRight size={18} />
          </button>
        </section>
      </div>

      <section className="panel task-panel">
        <div className="section-heading compact">
          <div>
            <span className="section-kicker">最近</span>
            <h2>任务</h2>
          </div>
          <span className="count-label">{data.plans.length}</span>
        </div>
        <PlanTable plans={data.plans.slice(0, 7)} onOpen={onOpenPlan} emptyAction={onNewTask} />
      </section>
    </div>
  );
}

function Metric({
  label,
  value,
  detail,
  icon: Icon,
  tone = 'neutral',
}: {
  label: string;
  value: string;
  detail: string;
  icon: typeof Activity;
  tone?: string;
}) {
  return (
    <div className={`metric ${tone}`}>
      <div className="metric-icon"><Icon size={18} /></div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

function MailSummary({
  data,
  job,
  onRun,
  onSetup,
}: {
  data: Bootstrap;
  job: MailSummaryJob | null;
  onRun: () => Promise<void>;
  onSetup: () => void;
}) {
  const [running, setRunning] = useState(false);
  const run = async () => {
    setRunning(true);
    try {
      await onRun();
    } finally {
      setRunning(false);
    }
  };
  if (job?.status === 'ready') {
    return (
      <div className="mail-result">
        <div className="mail-result-meta">
          <CheckCircle2 size={16} />
          {job.message_count} 封匹配邮件
          <button className="text-button" type="button" onClick={() => void run()}>
            重新生成
          </button>
        </div>
        <div className="summary-text">{job.summary}</div>
      </div>
    );
  }
  if (job?.status === 'failed') {
    return (
      <div className="empty-state danger-state">
        <AlertTriangle size={24} />
        <strong>摘要未生成</strong>
        <span>{job.error}</span>
        <button className="secondary-button" type="button" onClick={() => void run()}>重试</button>
      </div>
    );
  }
  if (job?.status === 'running' || running) {
    return (
      <div className="empty-state">
        <LoaderCircle size={26} className="spin" />
        <strong>正在生成摘要</strong>
        <span>正在处理固定范围的未读邮件</span>
      </div>
    );
  }
  const detail = data.integrations.mail?.detail || '邮箱连接待配置';
  return (
    <div className="empty-state">
      <Inbox size={28} />
      <strong>{data.mail_ready ? '今日摘要尚未生成' : '邮箱尚未就绪'}</strong>
      <span>{data.mail_ready ? '读取固定范围的未读邮件元数据' : detail}</span>
      <button
        className="secondary-button"
        type="button"
        onClick={data.mail_ready ? () => void run() : onSetup}
      >
        <Mail size={16} />
        {data.mail_ready ? '查看今日摘要' : '设置邮箱'}
      </button>
    </div>
  );
}

function TasksView({ plans, onOpen, onNew }: { plans: PlanRecord[]; onOpen: (plan: PlanRecord) => void; onNew: () => void }) {
  return (
    <section className="panel full-panel">
      <div className="section-heading compact">
        <div>
          <span className="section-kicker">全部</span>
          <h2>任务计划</h2>
        </div>
        <button className="secondary-button" type="button" onClick={onNew}>
          <Plus size={16} />新建
        </button>
      </div>
      <PlanTable plans={plans} onOpen={onOpen} emptyAction={onNew} />
    </section>
  );
}

function PlanTable({ plans, onOpen, emptyAction }: { plans: PlanRecord[]; onOpen: (plan: PlanRecord) => void; emptyAction: () => void }) {
  if (!plans.length) {
    return (
      <div className="table-empty">
        <ListTodo size={28} />
        <span>还没有任务</span>
        <button className="text-button" type="button" onClick={emptyAction}>创建第一项</button>
      </div>
    );
  }
  return (
    <div className="data-table plan-table" role="table">
      <div className="table-head" role="row">
        <span>任务</span><span>架构</span><span>状态</span><span>更新时间</span><span />
      </div>
      {plans.map((record) => (
        <button className="table-row" role="row" type="button" key={record.plan_id} onClick={() => onOpen(record)}>
          <span className="task-name-cell">
            <strong>{record.plan?.title || record.objective}</strong>
            <small>{shortId(record.plan_id)}</small>
          </span>
          <span>{record.plan ? `${record.plan.agents.length} Agent` : '—'}</span>
          <span><StatusBadge status={record.status} /></span>
          <span>{formatTime(record.updated_at)}</span>
          <ChevronRight size={17} />
        </button>
      ))}
    </div>
  );
}

function EvidenceView({ runs, data }: { runs: RunRecord[]; data: Bootstrap }) {
  return (
    <div className="evidence-layout">
      <section className="metric-strip compact-metrics">
        <Metric label="账本运行" value={String(data.fleet.runs)} detail="append-only" icon={Database} tone="success" />
        <Metric label="Artifact" value={String(data.fleet.artifacts)} detail="content-addressed" icon={FileCheck2} />
        <Metric label="待同步" value={String(data.fleet.pending_projection)} detail="治理记录" icon={RefreshCw} tone={data.fleet.pending_projection ? 'warning' : 'success'} />
      </section>
      <section className="panel full-panel">
        <div className="section-heading compact">
          <div><span className="section-kicker">最近</span><h2>运行证据</h2></div>
        </div>
        <div className="data-table run-table" role="table">
          <div className="table-head" role="row"><span>Job</span><span>Run</span><span>状态</span><span>耗时</span><span>时间</span></div>
          {runs.map((run) => (
            <div className="table-row static" role="row" key={run.run_id}>
              <span className="task-name-cell"><strong>{run.job}</strong><small>exit {run.exit_code ?? '—'}</small></span>
              <code>{shortId(run.run_id)}</code>
              <StatusBadge status={run.status} />
              <span>{run.duration_s == null ? '—' : `${run.duration_s.toFixed(1)}s`}</span>
              <span>{formatTime(run.finished_ts || run.started_ts)}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function ApprovalsView({
  data,
  onChanged,
}: {
  data: Bootstrap;
  onChanged: () => Promise<void>;
}) {
  const [selected, setSelected] = useState<ApprovalCard | null>(null);
  const [decision, setDecision] = useState<'approve' | 'reject'>('approve');
  const [decisionNote, setDecisionNote] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const openDecision = (approval: ApprovalCard, next: 'approve' | 'reject') => {
    setSelected(approval);
    setDecision(next);
    setDecisionNote('');
    setConfirmed(false);
    setError('');
  };

  const submitDecision = async () => {
    if (!selected || !confirmed || busy) return;
    setBusy(true);
    setError('');
    try {
      await decideApproval(selected.approval_id, decision, decisionNote);
      await onChanged();
      setSelected(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '审批提交失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="approvals-layout">
      <section className="panel full-panel">
        <div className="section-heading compact">
          <div><span className="section-kicker">人工检查点</span><h2>待审批</h2></div>
          <span className="count-label">{data.approvals_available ? data.approvals.length : '—'}</span>
        </div>
        {!data.approvals_available ? (
          <div className="table-empty danger-state">
            <AlertTriangle size={28} />
            <span>审批服务暂不可用，所有受管操作继续保持阻断。</span>
          </div>
        ) : data.approvals.length === 0 ? (
          <div className="table-empty">
            <ClipboardCheck size={28} />
            <span>当前没有需要你处理的审批</span>
          </div>
        ) : (
          <div className="approval-list">
            {data.approvals.map((approval) => (
              <article className="approval-card" key={approval.approval_id}>
                <div className="approval-card-main">
                  <div className="approval-card-heading">
                    <span className="approval-kind"><ShieldCheck size={14} />{approval.kind === 'tool_call' ? '工具调用' : '治理请求'}</span>
                    <span>{formatTime(approval.requested_at)}</span>
                  </div>
                  <h3>{approval.title}</h3>
                  <p>{approval.summary}</p>
                  {approval.tool_name && (
                    <div className="approval-tool"><span>工具</span><code>{approval.tool_name}</code></div>
                  )}
                  {approval.tool_input && <pre className="approval-input">{approval.tool_input}</pre>}
                  {approval.risks.length > 0 && (
                    <div className="approval-risks">
                      {approval.risks.map((risk) => <span key={risk}><AlertTriangle size={13} />{risk}</span>)}
                    </div>
                  )}
                  <small>{approval.recommended_action}</small>
                </div>
                <div className="approval-actions">
                  <button className="secondary-button danger-button" type="button" onClick={() => openDecision(approval, 'reject')}>
                    <X size={16} />拒绝
                  </button>
                  <button className="primary-button" type="button" onClick={() => openDecision(approval, 'approve')}>
                    <Check size={16} />批准
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      {selected && (
        <div className="modal-layer" role="dialog" aria-modal="true" aria-label="确认审批决定">
          <button className="modal-backdrop" type="button" aria-label="关闭" onClick={() => !busy && setSelected(null)} />
          <section className="mail-setup-dialog approval-dialog">
            <header className="modal-header">
              <div><span className="section-kicker">人工决定</span><h2>{decision === 'approve' ? '批准这项操作' : '拒绝这项操作'}</h2></div>
              <button className="icon-button" type="button" title="关闭" disabled={busy} onClick={() => setSelected(null)}><X size={19} /></button>
            </header>
            <div className="mail-setup-content">
              <div className="decision-summary"><strong>{selected.title}</strong><span>{selected.summary}</span></div>
              <label className="secret-field">
                <span>决定说明（可选）</span>
                <textarea rows={3} maxLength={500} value={decisionNote} onChange={(event) => setDecisionNote(event.target.value)} placeholder="记录为什么批准或拒绝" />
              </label>
              <label className="consent-row">
                <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
                <span>我已检查这项请求的内容、工具和风险，并确认本次决定</span>
              </label>
              {error && <InlineError text={error} />}
              <button
                className={decision === 'approve' ? 'primary-button full-button' : 'secondary-button danger-button full-button'}
                type="button"
                disabled={!confirmed || busy}
                onClick={() => void submitDecision()}
              >
                {busy ? <LoaderCircle size={17} className="spin" /> : decision === 'approve' ? <Check size={17} /> : <X size={17} />}
                {decision === 'approve' ? '确认批准' : '确认拒绝'}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

function ConnectionsView({
  data,
  onMailSetup,
  onTelegramSetup,
  onChanged,
}: {
  data: Bootstrap;
  onMailSetup: () => void;
  onTelegramSetup: () => void;
  onChanged: () => Promise<void>;
}) {
  const [job, setJob] = useState<ProviderConnectionJob | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!job || job.status !== 'running') return;
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await getProviderConnection(job.job_id);
        if (cancelled) return;
        setJob(next);
        if (next.status === 'ready') await onChanged();
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : '连接状态读取失败');
      }
    };
    const timer = window.setInterval(() => void poll(), 1500);
    void poll();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [job?.job_id, job?.status, onChanged]);

  const startConnection = async (provider: 'openai' | 'anthropic') => {
    setError('');
    try {
      setJob(await connectProvider(provider));
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法启动登录');
    }
  };

  const providerRows = [data.providers.openai, data.providers.anthropic];
  const dailyRows = [
    ['mail', data.integrations.mail, Mail, onMailSetup],
    ['telegram', data.integrations.telegram, Send, onTelegramSetup],
  ] as const;
  return (
    <div className="connections-layout">
      <section className="panel full-panel">
        <div className="section-heading compact">
          <div><span className="section-kicker">AI</span><h2>模型连接</h2></div>
        </div>
        <div className="provider-list">
          {providerRows.map((provider: AIProvider) => {
            const connecting = job?.provider === provider.provider && job.status === 'running';
            const connected = provider.status === 'online';
            return (
              <div className="provider-row" key={provider.provider}>
                <div className="provider-mark"><Bot size={21} /></div>
                <div className="provider-copy">
                  <strong>{provider.label}</strong>
                  <span>{provider.detail}</span>
                  <small>{provider.privacy}</small>
                </div>
                <StatusBadge
                  status={provider.status}
                  label={connected ? '可用' : provider.authenticated ? '准备中' : provider.installed ? '待连接' : '未安装'}
                />
                <button
                  className={connected ? 'secondary-button provider-button connected' : 'primary-button provider-button'}
                  type="button"
                  disabled={!provider.installed || connected || connecting}
                  onClick={() => void startConnection(provider.provider)}
                >
                  {connecting ? <LoaderCircle size={16} className="spin" /> : connected ? <Check size={16} /> : <ExternalLink size={16} />}
                  {connecting ? '等待登录' : connected ? '已连接' : provider.authenticated ? '重新连接' : '连接'}
                </button>
              </div>
            );
          })}
        </div>
        {job?.status === 'running' && (
          <div className="provider-notice" role="status">
            <LoaderCircle size={17} className="spin" />请在厂商打开的页面完成登录；Quarterdeck 不会读取登录凭据。
          </div>
        )}
        {job?.status === 'failed' && <InlineError text={job.error || '登录未完成'} />}
        {error && <InlineError text={error} />}
      </section>

      <section className="panel full-panel">
        <div className="section-heading compact">
          <div><span className="section-kicker">日常工具</span><h2>消息与数据</h2></div>
        </div>
        <div className="connection-list">
          {dailyRows.map(([key, item, Icon, action]) => (
            <div className="connection-row" key={key}>
              <div className="connection-icon"><Icon size={19} /></div>
              <div><strong>{item.label}</strong><span>{item.detail || (item.status === 'online' ? '已连接' : '待配置')}</span></div>
              <StatusBadge status={item.status} label={item.status === 'online' ? '已连接' : '待设置'} />
              <button className="icon-button compact-icon" type="button" title={`管理${item.label}`} onClick={action}>
                <Settings size={16} />
              </button>
            </div>
          ))}
        </div>
      </section>

      <details className="diagnostics-panel">
        <summary><span><Server size={16} />系统诊断</span><ChevronDown size={16} /></summary>
        <div className="diagnostics-list">
          {['aionui', 'paperclip', 'ledger'].map((key) => {
            const item = data.integrations[key];
            return item ? (
              <div key={key}><span className={`status-dot ${statusTone(item.status)}`} /><strong>{item.label}</strong><small>{item.detail}</small></div>
            ) : null;
          })}
        </div>
      </details>
    </div>
  );
}

function MailSetupDialog({
  open,
  onClose,
  onChanged,
}: {
  open: boolean;
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const [status, setStatus] = useState<MailAuthorizationStatus | null>(null);
  const [job, setJob] = useState<MailAuthorizationJob | null>(null);
  const [readonlyAck, setReadonlyAck] = useState(false);
  const [metadataAck, setMetadataAck] = useState(false);
  const [revokeAck, setRevokeAck] = useState(false);
  const [clientFile, setClientFile] = useState<File | null>(null);
  const [clientStorageAck, setClientStorageAck] = useState(false);
  const [clientInputKey, setClientInputKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const loadStatus = useCallback(async () => {
    const next = await getMailAuthorizationStatus();
    setStatus(next);
    return next;
  }, []);

  useEffect(() => {
    if (!open) return;
    setReadonlyAck(false);
    setMetadataAck(false);
    setRevokeAck(false);
    setClientFile(null);
    setClientStorageAck(false);
    setJob(null);
    setError('');
    setNotice('');
    setBusy(true);
    void loadStatus()
      .catch((err) => setError(err instanceof Error ? err.message : '邮箱状态读取失败'))
      .finally(() => setBusy(false));
  }, [open, loadStatus]);

  useEffect(() => {
    if (!open || !job || job.status !== 'running') return;
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await getMailAuthorization(job.job_id);
        if (cancelled) return;
        setJob(next);
        if (next.status === 'ready') {
          await loadStatus();
          await onChanged();
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '授权状态读取失败');
        }
      }
    };
    const timer = window.setInterval(() => void poll(), 1500);
    void poll();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [job?.job_id, job?.status, loadStatus, onChanged, open]);

  if (!open) return null;

  const startAuthorization = async () => {
    setBusy(true);
    setError('');
    try {
      setJob(await requestMailAuthorization());
    } catch (err) {
      setError(err instanceof Error ? err.message : '授权请求失败');
    } finally {
      setBusy(false);
    }
  };

  const importOAuthClient = async () => {
    if (!clientFile) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      if (clientFile.size > 65_536) throw new Error('OAuth client JSON 超过 64 KiB');
      const clientJson = await clientFile.text();
      await configureMailOAuthClient(clientJson);
      await loadStatus();
      setClientFile(null);
      setClientStorageAck(false);
      setClientInputKey((value) => value + 1);
      setNotice('Desktop OAuth client 已安全导入；现在可以继续 Gmail 只读授权。');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'OAuth client 导入失败');
    } finally {
      setBusy(false);
    }
  };

  const revoke = async () => {
    setBusy(true);
    setError('');
    try {
      await disableMail();
      await loadStatus();
      await onChanged();
      setJob(null);
      setRevokeAck(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : '停用失败');
    } finally {
      setBusy(false);
    }
  };

  const ready = status?.ready === true;
  const clientReady = status?.oauth_client_ready === true;
  const running = job?.status === 'running';
  return (
    <div className="modal-layer" role="dialog" aria-modal="true" aria-label="邮箱授权">
      <button className="modal-backdrop" type="button" aria-label="关闭" onClick={onClose} />
      <section className="mail-setup-dialog">
        <header className="modal-header">
          <div>
            <span className="section-kicker">GMAIL</span>
            <h2>{ready ? '邮箱摘要已连接' : '设置邮箱摘要'}</h2>
          </div>
          <button className="icon-button" type="button" title="关闭" onClick={onClose}>
            <X size={19} />
          </button>
        </header>

        {ready ? (
          <div className="mail-setup-content">
            <div className="setup-success">
              <ShieldCheck size={24} />
              <div>
                <strong>Gmail 只读授权有效</strong>
                <span>首页现在可以按需生成元数据摘要。</span>
              </div>
            </div>
            <div className="privacy-summary">
              <strong>固定数据边界</strong>
              <span>仅发件人、主题、日期和 message-id；不读取正文。</span>
              <span>没有发送、草稿、删除或标签权限。</span>
            </div>
            <label className="consent-row">
              <input
                type="checkbox"
                checked={revokeAck}
                onChange={(event) => setRevokeAck(event.target.checked)}
              />
              <span>确认停用后续邮箱读取与模型元数据传输</span>
            </label>
            <button
              className="secondary-button danger-button"
              type="button"
              disabled={!revokeAck || busy}
              onClick={() => void revoke()}
            >
              停用邮箱摘要
            </button>
          </div>
        ) : (
          <div className="mail-setup-content">
            <div className="privacy-summary">
              <strong>最小权限</strong>
              <span>授权页只申请 Gmail readonly；token 由 gws 加密保存，Quarterdeck 不读取或回显。</span>
              <span>固定查询仅查看最近未读收件箱，排除垃圾邮件和回收站。</span>
            </div>
            {status && !status.available && (
              <div className="inline-error">本机固定版本 gws 尚未就绪，请先运行 doctor。</div>
            )}
            {status?.available && !clientReady ? (
              <div className="setup-step">
                <div className="setup-step-heading">
                  <span>1</span>
                  <div>
                    <strong>导入 Google Desktop OAuth client</strong>
                    <small>首次设置一次；请选择 Google Cloud 下载的 client_secret JSON。</small>
                  </div>
                </div>
                <a
                  className="secondary-button link-button full-button"
                  href="https://console.cloud.google.com/apis/credentials"
                  target="_blank"
                  rel="noreferrer"
                >
                  <ExternalLink size={16} />
                  打开 Google Cloud 凭据页
                </a>
                <label className="client-file-field">
                  <FileUp size={17} />
                  <span>{clientFile?.name || '选择 Desktop client JSON'}</span>
                  <input
                    key={clientInputKey}
                    type="file"
                    accept="application/json,.json"
                    onChange={(event) => setClientFile(event.target.files?.[0] || null)}
                  />
                </label>
                <label className="consent-row">
                  <input
                    type="checkbox"
                    checked={clientStorageAck}
                    onChange={(event) => setClientStorageAck(event.target.checked)}
                  />
                  <span>确认将该 Desktop client 配置以 0600 权限保存到本机 gws 私有目录</span>
                </label>
                <button
                  className="primary-button full-button"
                  type="button"
                  disabled={!clientFile || !clientStorageAck || busy}
                  onClick={() => void importOAuthClient()}
                >
                  {busy ? <LoaderCircle size={17} className="spin" /> : <FileUp size={17} />}
                  安全导入并继续
                </button>
              </div>
            ) : status?.available ? (
              <div className="setup-step">
                <div className="setup-step-heading">
                  <span>2</span>
                  <div>
                    <strong>授权与摘要同意</strong>
                    <small>Google 授权和 AI 摘要元数据传输分别确认。</small>
                  </div>
                </div>
                <label className="consent-row">
                  <input
                    type="checkbox"
                    checked={readonlyAck}
                    onChange={(event) => setReadonlyAck(event.target.checked)}
                  />
                  <span>我同意打开 Google 授权页并仅授予 Gmail 只读权限</span>
                </label>
                <label className="consent-row">
                  <input
                    type="checkbox"
                    checked={metadataAck}
                    onChange={(event) => setMetadataAck(event.target.checked)}
                  />
                  <span>我同意将发件人、主题、日期和 message-id 发送给当前 AI 模型生成摘要</span>
                </label>
                {running && (
                  <div className="oauth-progress" role="status">
                    <LoaderCircle size={20} className="spin" />
                    <span>请在已打开的 Google 页面完成授权</span>
                  </div>
                )}
                <button
                  className="primary-button full-button"
                  type="button"
                  disabled={busy || running || !readonlyAck || !metadataAck}
                  onClick={() => void startAuthorization()}
                >
                  {busy ? <LoaderCircle size={17} className="spin" /> : <ShieldCheck size={17} />}
                  {status?.authenticated ? '确认并启用摘要' : '打开 Google 只读授权'}
                </button>
              </div>
            ) : null}
            {status?.oauth_client_issue === 'unsafe_permissions' && (
              <div className="inline-error">现有 OAuth client 文件权限不安全，请重新导入修复。</div>
            )}
            {status?.oauth_client_issue === 'invalid' && (
              <div className="inline-error">现有 OAuth client 不是有效的 Desktop 配置，请重新导入。</div>
            )}
            {job?.status === 'failed' && <div className="inline-error">{job.error}</div>}
            {notice && <div className="setup-notice">{notice}</div>}
            {error && <div className="inline-error">{error}</div>}
          </div>
        )}
      </section>
    </div>
  );
}

function TelegramSetupDialog({
  open,
  onClose,
  onChanged,
}: {
  open: boolean;
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const [status, setStatus] = useState<TelegramSetupStatus | null>(null);
  const [editing, setEditing] = useState(false);
  const [botToken, setBotToken] = useState('');
  const [chatId, setChatId] = useState('');
  const [storageAck, setStorageAck] = useState(false);
  const [testAck, setTestAck] = useState(false);
  const [disableAck, setDisableAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const loadStatus = useCallback(async () => {
    const next = await getTelegramStatus();
    setStatus(next);
    setEditing(!next.configured && !next.environment_controlled);
    return next;
  }, []);

  useEffect(() => {
    if (!open) return;
    setBotToken('');
    setChatId('');
    setStorageAck(false);
    setTestAck(false);
    setDisableAck(false);
    setError('');
    setNotice('');
    setBusy(true);
    void loadStatus()
      .catch((err) => setError(err instanceof Error ? err.message : 'Telegram 状态读取失败'))
      .finally(() => setBusy(false));
  }, [open, loadStatus]);

  if (!open) return null;

  const closeDialog = () => {
    setBotToken('');
    setChatId('');
    setStorageAck(false);
    onClose();
  };

  const configure = async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await configureTelegram({
        bot_token: botToken,
        chat_id: chatId,
        storage_acknowledged: true,
        replace_existing: status?.configured === true,
      });
      setBotToken('');
      setChatId('');
      setStorageAck(false);
      await loadStatus();
      await onChanged();
      setNotice('凭据已保存；发送测试消息后才算交付链路验收完成。');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Telegram 配置失败');
    } finally {
      setBusy(false);
    }
  };

  const sendTest = async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await testTelegram();
      setTestAck(false);
      setNotice('固定测试消息已发送。');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Telegram 测试失败');
    } finally {
      setBusy(false);
    }
  };

  const disable = async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await disableTelegram();
      await loadStatus();
      await onChanged();
      setDisableAck(false);
      setNotice('本机 Telegram 凭据已移除。');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Telegram 停用失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-layer" role="dialog" aria-modal="true" aria-label="Telegram 设置">
      <button className="modal-backdrop" type="button" aria-label="关闭" onClick={closeDialog} />
      <section className="mail-setup-dialog">
        <header className="modal-header">
          <div>
            <span className="section-kicker">TELEGRAM</span>
            <h2>{status?.configured ? 'Telegram 已配置' : '设置 Telegram'}</h2>
          </div>
          <button className="icon-button" type="button" title="关闭" onClick={closeDialog}>
            <X size={19} />
          </button>
        </header>

        <div className="mail-setup-content">
          <div className="privacy-summary">
            <strong>本机秘密边界</strong>
            <span>Bot token 与 chat ID 只写入本机 0600 secrets.yaml，不进入账本或页面回显。</span>
            <span>测试按钮只发送固定的 Quarterdeck 探针文本。</span>
          </div>

          {status?.environment_controlled ? (
            <div className="inline-error">凭据由外部环境管理，控制台不能覆盖或删除。</div>
          ) : status?.configured && !editing ? (
            <>
              <div className="setup-success">
                <Send size={22} />
                <div>
                  <strong>本机凭据已配置</strong>
                  <span>不会显示 token 或 chat ID。</span>
                </div>
              </div>
              <label className="consent-row">
                <input
                  type="checkbox"
                  checked={testAck}
                  onChange={(event) => setTestAck(event.target.checked)}
                />
                <span>确认向已配置的目标发送一条固定测试消息</span>
              </label>
              <button
                className="primary-button full-button"
                type="button"
                disabled={!testAck || busy}
                onClick={() => void sendTest()}
              >
                <Send size={17} />发送测试消息
              </button>
              <button
                className="secondary-button full-button"
                type="button"
                disabled={busy}
                onClick={() => {
                  setEditing(true);
                  setNotice('');
                  setError('');
                }}
              >
                更换凭据
              </button>
              <label className="consent-row">
                <input
                  type="checkbox"
                  checked={disableAck}
                  onChange={(event) => setDisableAck(event.target.checked)}
                />
                <span>确认从本机移除 Telegram 凭据并停止后续推送</span>
              </label>
              <button
                className="secondary-button danger-button"
                type="button"
                disabled={!disableAck || busy}
                onClick={() => void disable()}
              >
                停用 Telegram
              </button>
            </>
          ) : !status?.environment_controlled ? (
            <>
              <label className="secret-field">
                <span>Bot token</span>
                <input
                  type="password"
                  value={botToken}
                  autoComplete="off"
                  spellCheck={false}
                  onChange={(event) => setBotToken(event.target.value)}
                />
              </label>
              <label className="secret-field">
                <span>Chat ID</span>
                <input
                  type="password"
                  value={chatId}
                  autoComplete="off"
                  spellCheck={false}
                  onChange={(event) => setChatId(event.target.value)}
                />
              </label>
              <label className="consent-row">
                <input
                  type="checkbox"
                  checked={storageAck}
                  onChange={(event) => setStorageAck(event.target.checked)}
                />
                <span>确认将这两项凭据保存到本机私有 secrets.yaml</span>
              </label>
              <button
                className="primary-button full-button"
                type="button"
                disabled={!botToken || !chatId || !storageAck || busy}
                onClick={() => void configure()}
              >
                {busy ? <LoaderCircle size={17} className="spin" /> : <ShieldCheck size={17} />}
                {status?.configured ? '替换本机凭据' : '保存本机凭据'}
              </button>
              {status?.configured && (
                <button
                  className="text-button"
                  type="button"
                  onClick={() => {
                    setEditing(false);
                    setBotToken('');
                    setChatId('');
                    setStorageAck(false);
                  }}
                >
                  取消更换
                </button>
              )}
            </>
          ) : null}

          {notice && <div className="setup-notice">{notice}</div>}
          {error && <div className="inline-error">{error}</div>}
        </div>
      </section>
    </div>
  );
}

function TaskDrawer({
  open,
  record,
  previousPlan,
  onClose,
  onPlan,
  onRevise,
  onConfirm,
  onRestart,
}: {
  open: boolean;
  record: PlanRecord | null;
  previousPlan: TaskPlan | null;
  onClose: () => void;
  onPlan: (body: { objective: string; constraints: string; workspace: string; preferred_cadence: string }) => Promise<void>;
  onRevise: (record: PlanRecord, instruction: string) => Promise<void>;
  onConfirm: (record: PlanRecord) => Promise<void>;
  onRestart: () => void;
}) {
  const [objective, setObjective] = useState('');
  const [constraints, setConstraints] = useState('');
  const [workspace, setWorkspace] = useState('');
  const [cadence, setCadence] = useState('once');
  const [submitting, setSubmitting] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [revisionOpen, setRevisionOpen] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    setConfirmed(false);
    setRevisionOpen(false);
    setError('');
    if (!record) {
      setObjective('');
      setConstraints('');
      setWorkspace('');
      setCadence('once');
    }
  }, [open, record?.plan_id]);

  if (!open) return null;
  const phase = !record ? 1 : record.status === 'planning' ? 1 : record.status === 'ready' ? 2 : 3;
  const submit = async () => {
    setSubmitting(true);
    setError('');
    try {
      await onPlan({ objective, constraints, workspace, preferred_cadence: cadence });
    } catch (err) {
      setError(err instanceof Error ? err.message : '规划请求失败');
    } finally {
      setSubmitting(false);
    }
  };
  const confirm = async () => {
    if (!record) return;
    setSubmitting(true);
    setError('');
    try {
      await onConfirm(record);
    } catch (err) {
      setError(err instanceof Error ? err.message : '确认失败');
    } finally {
      setSubmitting(false);
    }
  };
  const revise = async (instruction: string) => {
    if (!record) return;
    setSubmitting(true);
    setError('');
    try {
      await onRevise(record, instruction);
    } catch (err) {
      setError(err instanceof Error ? err.message : '方案修改失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="drawer-layer" role="dialog" aria-modal="true" aria-label="新建任务">
      <button className="drawer-backdrop" type="button" aria-label="关闭" onClick={onClose} />
      <aside className="task-drawer">
        <div className="drawer-header">
          <div><span className="section-kicker">NEW TASK</span><h2>{record?.plan?.title || '创建任务'}</h2></div>
          <button className="icon-button" type="button" title="关闭" onClick={onClose}><X size={19} /></button>
        </div>
        <StepTrack phase={phase} />
        <div className="drawer-body">
          {!record && (
            <div className="task-form">
              <label>
                <span>目标</span>
                <textarea value={objective} onChange={(event) => setObjective(event.target.value)} maxLength={2000} rows={5} placeholder="例如：每天早上汇总未读邮件，并标出需要回复的事项" />
              </label>
              <label>
                <span>约束</span>
                <textarea value={constraints} onChange={(event) => setConstraints(event.target.value)} maxLength={2000} rows={3} placeholder="数据范围、交付格式、审批要求" />
              </label>
              <label>
                <span>更新节奏</span>
                <div className="segmented-control">
                  {cadenceOptions.map((option) => (
                    <button key={option.value} type="button" className={cadence === option.value ? 'selected' : ''} onClick={() => setCadence(option.value)}>{option.label}</button>
                  ))}
                </div>
              </label>
              <label>
                <span>工作目录</span>
                <div className="input-with-icon"><FolderOpen size={17} /><input value={workspace} onChange={(event) => setWorkspace(event.target.value)} placeholder="可选：绝对路径" /></div>
              </label>
              {error && <InlineError text={error} />}
              <div className="drawer-actions">
                <button className="primary-button wide" type="button" disabled={objective.trim().length < 3 || submitting} onClick={() => void submit()}>
                  {submitting ? <LoaderCircle size={17} className="spin" /> : <Sparkles size={17} />}
                  生成方案
                </button>
              </div>
            </div>
          )}

          {record?.status === 'planning' && (
            <PlanningProgressView progress={record.planning_progress} />
          )}

          {record?.status === 'ready' && record.plan && (
            <PlanReview
              plan={record.plan}
              hash={record.plan_sha256 || ''}
              previousPlan={previousPlan}
              revisionNumber={record.revision_number}
            />
          )}

          {record && ['confirmed', 'dispatching', 'running', 'awaiting_approval', 'completed_unverified', 'failed'].includes(record.status) && (
            <ExecutionView record={record} />
          )}
        </div>

        {record?.status === 'ready' && (
          <div className="confirm-footer">
            {error && <InlineError text={error} />}
            {revisionOpen ? (
              <RevisionComposer
                submitting={submitting}
                onCancel={() => setRevisionOpen(false)}
                onSubmit={revise}
              />
            ) : (
              <>
                <label className="confirm-check">
                  <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
                  <span><Check size={15} />确认此方案并启动受管执行</span>
                </label>
                <div className="confirm-actions revision-actions">
                  <button className="secondary-button" type="button" onClick={() => setRevisionOpen(true)}>
                    <PencilLine size={16} />修改方案
                  </button>
                  <button className="text-button" type="button" onClick={onRestart}>
                    <RotateCcw size={15} />重新开始
                  </button>
                  <button className="primary-button" type="button" disabled={!confirmed || submitting} onClick={() => void confirm()}>
                    {submitting ? <LoaderCircle size={17} className="spin" /> : <Play size={17} />}
                    确认并运行
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}

function RevisionComposer({
  submitting,
  onCancel,
  onSubmit,
}: {
  submitting: boolean;
  onCancel: () => void;
  onSubmit: (instruction: string) => Promise<void>;
}) {
  const [instruction, setInstruction] = useState('');
  const ready = instruction.trim().length >= 3 && !submitting;
  return (
    <div className="revision-composer">
      <div className="revision-composer-heading">
        <PencilLine size={17} />
        <div>
          <strong>基于当前方案修改</strong>
          <span>只写希望改变的部分；未提及内容会尽量保留。</span>
        </div>
      </div>
      <textarea
        aria-label="方案修改要求"
        value={instruction}
        onChange={(event) => setInstruction(event.target.value)}
        maxLength={2000}
        rows={3}
        placeholder="例如：改成每周五更新，只保留两个 Agent，并增加引用核验检查点"
      />
      <div className="revision-composer-footer">
        <span>{instruction.length}/2000</span>
        <div>
          <button className="text-button" type="button" disabled={submitting} onClick={onCancel}>取消</button>
          <button className="primary-button" type="button" disabled={!ready} onClick={() => void onSubmit(instruction.trim())}>
            {submitting ? <LoaderCircle size={16} className="spin" /> : <Sparkles size={16} />}
            生成修改版
          </button>
        </div>
      </div>
    </div>
  );
}

function StepTrack({ phase }: { phase: number }) {
  return (
    <div className="step-track">
      {['需求', '方案', '运行'].map((label, index) => {
        const step = index + 1;
        return (
          <div key={label} className={step <= phase ? 'step active' : 'step'}>
            <span>{step < phase ? <Check size={13} /> : step}</span>
            <small>{label}</small>
          </div>
        );
      })}
    </div>
  );
}

function PlanningProgressView({ progress }: { progress: PlanRecord['planning_progress'] }) {
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const phase = progress?.phase ?? 'generating_plan';
  const percent = progress?.percent ?? 30;
  const started = progress?.started_at ? Date.parse(progress.started_at) : now;
  const elapsed = Math.max(0, Math.floor((now - started) / 1000));
  const expected = progress?.expected_seconds ?? 150;
  const timeout = progress?.timeout_seconds ?? 390;
  const phaseIndex = {
    queued: 0,
    preparing: 0,
    generating_plan: 1,
    validating: 2,
    repairing: 2,
    cleaning_up: 3,
    complete: 4,
    failed: 4,
  }[phase];
  const stages = [
    '准备安全规划环境',
    'AI 补全任务摘要与 Agent 方案',
    phase === 'repairing' ? '修正并重新校验方案' : '严格校验方案契约',
    '清理临时规划会话',
  ];
  const phaseLabel = {
    queued: '规划任务已进入队列',
    preparing: '正在准备安全规划环境',
    generating_plan: '正在补全任务摘要与 Agent 方案',
    validating: '正在校验 Agent、检查点与交付物',
    repairing: '方案未通过首轮校验，正在自动修正',
    cleaning_up: '方案已生成，正在清理临时会话',
    complete: '规划完成',
    failed: '规划未完成',
  }[phase];
  const expectedRange = expected < 60
    ? `${Math.max(10, expected - 15)}–${expected + 15} 秒`
    : `${Math.max(1, Math.floor(expected / 60))}–${Math.max(
      Math.max(1, Math.floor(expected / 60)) + 1,
      Math.ceil(expected / 60),
    )} 分钟`;
  const timeoutLabel = timeout < 60 ? `${timeout} 秒` : `${Math.ceil(timeout / 60)} 分钟`;
  const timing = elapsed < expected
    ? `已等待 ${elapsed} 秒 · 通常总耗时约 ${expectedRange}`
    : `已等待 ${elapsed} 秒 · 已超过通常耗时，仍在处理（最久约 ${timeoutLabel}）`;

  return (
    <div className="planning-state">
      <div className="planning-orbit">
        <LoaderCircle size={34} className="spin" />
        <Sparkles size={17} />
      </div>
      <strong>AI 正在规划</strong>
      <span>{phaseLabel}</span>
      <div
        className="planning-progress-track"
        role="progressbar"
        aria-label="规划进度"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
      >
        <i style={{ width: `${percent}%` }} />
      </div>
      <div className="planning-timing">{timing}</div>
      <ol className="planning-steps">
        {stages.map((stage, index) => {
          const done = index < phaseIndex;
          const active = index === phaseIndex && phase !== 'complete' && phase !== 'failed';
          return (
            <li className={done ? 'done' : active ? 'active' : ''} key={stage}>
              <span>{done ? <Check size={13} /> : index + 1}</span>
              <p>{stage}</p>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function PlanReview({
  plan,
  hash,
  showStatus = true,
  previousPlan = null,
  revisionNumber = 1,
}: {
  plan: TaskPlan;
  hash: string;
  showStatus?: boolean;
  previousPlan?: TaskPlan | null;
  revisionNumber?: number;
}) {
  const changedSections = useMemo(
    () => changedPlanSections(previousPlan, plan),
    [previousPlan, plan],
  );
  return (
    <div className="plan-review">
      {previousPlan && (
        <div className="revision-summary" role="status">
          <GitCompareArrows size={18} />
          <div>
            <strong>第 {revisionNumber} 版 · 基于上一版修改</strong>
            <span>
              {changedSections.length
                ? `已变更：${changedSections.join('、')}`
                : '未检测到结构变化，请重点检查摘要内容。'}
            </span>
          </div>
        </div>
      )}
      <div className="plan-summary">
        <div className="plan-summary-heading">
          <span><Sparkles size={15} />AI 生成的任务摘要</span>
          {showStatus && <StatusBadge status="ready" />}
        </div>
        <p>{plan.summary}</p>
        <div className="plan-facts">
          <span><Users size={15} />{plan.agents.length} Agent</span>
          <span><Clock3 size={15} />约 {plan.estimated_duration_minutes} 分钟</span>
          <span><CalendarClock size={15} />{plan.cadence.update_interval}</span>
        </div>
      </div>

      <section className="review-section">
        <div className="review-title"><h3>Agent 架构</h3><span>{plan.execution_mode === 'workflow' ? plan.workflow_id : 'Agent 团队'}</span></div>
        <div className="agent-flow">
          {plan.agents.map((agent, index) => (
            <div className={`agent-node role-${agent.role}`} key={agent.name}>
              <div className="agent-node-top"><Bot size={18} /><span>{roleLabel[agent.role]}</span></div>
              <strong>{agent.name}</strong>
              <small>{runtimeLabel[agent.runtime]}</small>
              <p>{agent.responsibility}</p>
              {index < plan.agents.length - 1 && <ArrowRight className="agent-arrow" size={16} />}
            </div>
          ))}
        </div>
      </section>

      <section className="review-section">
        <div className="review-title"><h3>执行阶段</h3><span>{plan.stages.length} 步</span></div>
        <div className="stage-list">
          {plan.stages.map((stage) => (
            <div className="stage-row" key={stage.order}>
              <span className="stage-number">{stage.order}</span>
              <div><strong>{stage.title}</strong><p>{stage.outcome}</p></div>
              <span className="stage-owner">{stage.owner}</span>
              {stage.checkpoint ? <ShieldCheck size={16} /> : <Circle size={13} />}
            </div>
          ))}
        </div>
      </section>

      <div className="plan-details-grid">
        <DetailList title="审批" items={plan.approvals} empty="无额外审批" />
        <DetailList title="交付证据" items={plan.artifacts} empty="执行结果待登记" />
        <DetailList title="风险" items={plan.risks} empty="无已知风险" />
        <DetailList
          title="更新"
          items={[
            plan.update_policy,
            '本次确认只启动一次；重复调度需另行登记并确认。',
          ]}
          empty="—"
        />
      </div>
      <div className="hash-line"><ShieldCheck size={14} /><code>{hash}</code></div>
    </div>
  );
}

function changedPlanSections(previous: TaskPlan | null, current: TaskPlan): string[] {
  if (!previous) return [];
  const sections: Array<[string, unknown, unknown]> = [
    ['任务摘要', [previous.title, previous.summary, previous.estimated_duration_minutes], [current.title, current.summary, current.estimated_duration_minutes]],
    ['Agent 架构', previous.agents, current.agents],
    ['执行阶段', previous.stages, current.stages],
    ['更新节奏', [previous.cadence, previous.update_policy], [current.cadence, current.update_policy]],
    ['工具', previous.tools, current.tools],
    ['审批', previous.approvals, current.approvals],
    ['交付证据', previous.artifacts, current.artifacts],
    ['风险', previous.risks, current.risks],
  ];
  return sections
    .filter(([, before, after]) => JSON.stringify(before) !== JSON.stringify(after))
    .map(([label]) => label);
}

function DetailList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div className="detail-list">
      <strong>{title}</strong>
      {(items.length ? items : [empty]).map((item, index) => <span key={`${item}-${index}`}>{item}</span>)}
    </div>
  );
}

function ExecutionView({ record }: { record: PlanRecord }) {
  const execution = record.execution;
  const failed = record.status === 'failed';
  const done = record.status === 'completed_unverified';
  return (
    <div className="execution-view">
      <div className={`execution-icon ${failed ? 'danger' : done ? 'neutral' : 'active'}`}>
        {failed ? <AlertTriangle size={28} /> : done ? <FileCheck2 size={28} /> : <LoaderCircle size={28} className="spin" />}
      </div>
      <StatusBadge status={record.status} />
      <h3>{failed ? '任务未启动或已停止' : done ? '执行已结束' : record.status === 'awaiting_approval' ? '等待人工审批' : '任务正在运行'}</h3>
      <p>{failed ? record.error : done ? '进程行为已记录，业务结果仍需 artifact、eval 或审签证明。' : '治理记录已保存，已确认的 Agent 团队正在执行。'}</p>
      <div className="execution-identifiers">
        <div><span>任务计划</span><code>{shortId(record.plan_id)}</code></div>
        <div><span>治理记录</span><code>{shortId(execution?.paperclip_issue_id)}</code></div>
        <div><span>{execution?.kind === 'workflow' ? '工作流运行' : '执行会话'}</span><code>{shortId(execution?.workflow_run_id || execution?.aion_team_id)}</code></div>
      </div>
    </div>
  );
}

function StatusBadge({ status, label }: { status: string; label?: string }) {
  return <span className={`status-badge ${statusTone(status)}`}><span className="status-dot" />{label || statusLabel[status] || status}</span>;
}

function InlineError({ text }: { text: string }) {
  return <div className="inline-error"><AlertTriangle size={15} /><span>{text}</span></div>;
}

function LoadingState() {
  return <div className="loading-state"><LoaderCircle size={28} className="spin" /><span>正在读取本机状态</span></div>;
}

export default App;
