import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Bot,
  CalendarClock,
  Check,
  CheckCircle2,
  ChevronRight,
  Circle,
  ClipboardCheck,
  Clock3,
  Database,
  ExternalLink,
  FileCheck2,
  FolderOpen,
  Inbox,
  LayoutDashboard,
  ListTodo,
  LoaderCircle,
  Mail,
  Play,
  Plus,
  RefreshCw,
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
  getMailSummary,
  getPlan,
  loadBootstrap,
  requestMailSummary,
  requestPlan,
} from './api';
import type {
  Bootstrap,
  Integration,
  MailSummaryJob,
  PlanRecord,
  RunRecord,
  TaskPlan,
} from './types';

type View = 'dashboard' | 'tasks' | 'evidence' | 'settings';

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
  claude_code: 'Claude Code',
  codex_cli: 'Codex',
  aion_cli: 'Aion',
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

function App() {
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null);
  const [view, setView] = useState<View>('dashboard');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [activePlan, setActivePlan] = useState<PlanRecord | null>(null);
  const [mailJob, setMailJob] = useState<MailSummaryJob | null>(null);
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
    const timer = window.setInterval(() => void poll(), 2500);
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

  const title = {
    dashboard: '总控制台',
    tasks: '任务',
    evidence: '证据',
    settings: '连接',
  }[view];

  return (
    <div className="app-shell">
      <Sidebar view={view} onChange={setView} />
      <main className="main-area">
        <header className="topbar">
          <div className="topbar-title">
            <span className="eyebrow">QUARTERDECK</span>
            <h1>{title}</h1>
          </div>
          <div className="topbar-actions">
            <IntegrationRow integrations={bootstrap?.integrations} />
            <button className="icon-button" type="button" title="刷新" onClick={() => void refresh()}>
              <RefreshCw size={17} className={loading ? 'spin' : ''} />
            </button>
            <button className="primary-button" type="button" onClick={openNewTask}>
              <Plus size={17} />
              新建任务
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

        <div className="page-content">
          {loading && !bootstrap ? (
            <LoadingState />
          ) : bootstrap ? (
            <>
              {view === 'dashboard' && (
                <Dashboard
                  data={bootstrap}
                  mailJob={mailJob}
                  onMail={async () => setMailJob(await requestMailSummary())}
                  onOpenPlan={openPlan}
                  onNewTask={openNewTask}
                />
              )}
              {view === 'tasks' && (
                <TasksView plans={bootstrap.plans} onOpen={openPlan} onNew={openNewTask} />
              )}
              {view === 'evidence' && <EvidenceView runs={bootstrap.recent_runs} data={bootstrap} />}
              {view === 'settings' && <ConnectionsView data={bootstrap} />}
            </>
          ) : null}
        </div>
      </main>

      <TaskDrawer
        open={drawerOpen}
        record={activePlan}
        paperclipUrl={bootstrap?.integrations.paperclip?.url}
        onClose={() => setDrawerOpen(false)}
        onPlan={async (body) => {
          const record = await requestPlan(body);
          mergePlan(record);
        }}
        onConfirm={async (record) => {
          if (!record.plan_sha256) throw new Error('方案哈希缺失');
          mergePlan(await confirmPlan(record.plan_id, record.plan_sha256));
        }}
        onRestart={() => setActivePlan(null)}
      />
    </div>
  );
}

function Sidebar({ view, onChange }: { view: View; onChange: (view: View) => void }) {
  const items = [
    { id: 'dashboard' as const, label: '概览', icon: LayoutDashboard },
    { id: 'tasks' as const, label: '任务', icon: ListTodo },
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
      {['aionui', 'paperclip', 'ledger'].map((key) => {
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

function Dashboard({
  data,
  mailJob,
  onMail,
  onOpenPlan,
  onNewTask,
}: {
  data: Bootstrap;
  mailJob: MailSummaryJob | null;
  onMail: () => Promise<void>;
  onOpenPlan: (plan: PlanRecord) => void;
  onNewTask: () => void;
}) {
  const healthDetail = data.fleet.coverage_status === 'none'
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
          detail={data.approvals_available ? 'Paperclip' : '状态不可用'}
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
          <MailSummary data={data} job={mailJob} onRun={onMail} />
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
          <div className="quick-action muted">
            <span className="quick-icon"><ShieldCheck size={20} /></span>
            <span>
              <strong>治理状态</strong>
              <small>{!data.approvals_available
                ? 'Paperclip 审批状态不可用'
                : data.pending_approvals
                  ? `${data.pending_approvals} 项等待处理`
                  : '当前无待审批项'}</small>
            </span>
            <span className={`status-dot ${!data.approvals_available || data.pending_approvals ? 'warning' : 'success'}`} />
          </div>
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

function MailSummary({ data, job, onRun }: { data: Bootstrap; job: MailSummaryJob | null; onRun: () => Promise<void> }) {
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
      <button className="secondary-button" type="button" disabled={!data.mail_ready} onClick={() => void run()}>
        <Mail size={16} />
        {data.mail_ready ? '查看今日摘要' : '待配置'}
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
        <Metric label="待投影" value={String(data.fleet.pending_projection)} detail="Paperclip" icon={RefreshCw} tone={data.fleet.pending_projection ? 'warning' : 'success'} />
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

function ConnectionsView({ data }: { data: Bootstrap }) {
  const icons: Record<string, typeof Server> = { aionui: Bot, paperclip: Server, ledger: Database, mail: Mail };
  return (
    <section className="panel full-panel">
      <div className="section-heading compact">
        <div><span className="section-kicker">本机</span><h2>服务连接</h2></div>
      </div>
      <div className="connection-list">
        {Object.entries(data.integrations).map(([key, item]) => {
          const Icon = icons[key] || Server;
          return (
            <div className="connection-row" key={key}>
              <div className="connection-icon"><Icon size={19} /></div>
              <div><strong>{item.label}</strong><span>{item.detail || (item.status === 'online' ? '已连接' : '不可用')}</span></div>
              <StatusBadge status={item.status} label={item.status === 'online' ? '在线' : undefined} />
              {item.url ? <a href={item.url} target="_blank" rel="noreferrer" title={`打开 ${item.label}`}><ExternalLink size={17} /></a> : <span />}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function TaskDrawer({
  open,
  record,
  paperclipUrl,
  onClose,
  onPlan,
  onConfirm,
  onRestart,
}: {
  open: boolean;
  record: PlanRecord | null;
  paperclipUrl?: string;
  onClose: () => void;
  onPlan: (body: { objective: string; constraints: string; workspace: string; preferred_cadence: string }) => Promise<void>;
  onConfirm: (record: PlanRecord) => Promise<void>;
  onRestart: () => void;
}) {
  const [objective, setObjective] = useState('');
  const [constraints, setConstraints] = useState('');
  const [workspace, setWorkspace] = useState('');
  const [cadence, setCadence] = useState('once');
  const [submitting, setSubmitting] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    setConfirmed(false);
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
            <div className="planning-state">
              <div className="planning-orbit"><LoaderCircle size={34} className="spin" /><Sparkles size={17} /></div>
              <strong>AionUi 正在规划</strong>
              <span>正在生成 Agent 架构与更新节奏</span>
              <div className="planning-lines"><i /><i /><i /></div>
            </div>
          )}

          {record?.status === 'ready' && record.plan && (
            <PlanReview plan={record.plan} hash={record.plan_sha256 || ''} />
          )}

          {record && ['confirmed', 'dispatching', 'running', 'awaiting_approval', 'completed_unverified', 'failed'].includes(record.status) && (
            <ExecutionView record={record} paperclipUrl={paperclipUrl} />
          )}
        </div>

        {record?.status === 'ready' && (
          <div className="confirm-footer">
            {error && <InlineError text={error} />}
            <label className="confirm-check">
              <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
              <span><Check size={15} />确认此方案并启动受管执行</span>
            </label>
            <div className="confirm-actions">
              <button className="secondary-button" type="button" onClick={onRestart}>重新规划</button>
              <button className="primary-button" type="button" disabled={!confirmed || submitting} onClick={() => void confirm()}>
                {submitting ? <LoaderCircle size={17} className="spin" /> : <Play size={17} />}
                确认并运行
              </button>
            </div>
          </div>
        )}
      </aside>
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

function PlanReview({ plan, hash }: { plan: TaskPlan; hash: string }) {
  return (
    <div className="plan-review">
      <div className="plan-summary">
        <StatusBadge status="ready" />
        <p>{plan.summary}</p>
        <div className="plan-facts">
          <span><Users size={15} />{plan.agents.length} Agent</span>
          <span><Clock3 size={15} />约 {plan.estimated_duration_minutes} 分钟</span>
          <span><CalendarClock size={15} />{plan.cadence.update_interval}</span>
        </div>
      </div>

      <section className="review-section">
        <div className="review-title"><h3>Agent 架构</h3><span>{plan.execution_mode === 'workflow' ? plan.workflow_id : 'AionUi Team'}</span></div>
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

function DetailList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div className="detail-list">
      <strong>{title}</strong>
      {(items.length ? items : [empty]).map((item, index) => <span key={`${item}-${index}`}>{item}</span>)}
    </div>
  );
}

function ExecutionView({ record, paperclipUrl }: { record: PlanRecord; paperclipUrl?: string }) {
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
      <p>{failed ? record.error : done ? '进程行为已记录，业务结果仍需 artifact、eval 或审签证明。' : 'Paperclip 保存治理任务，AionUi 运行已确认的 Agent Team。'}</p>
      <div className="execution-identifiers">
        <div><span>Plan</span><code>{shortId(record.plan_id)}</code></div>
        <div><span>Paperclip issue</span><code>{shortId(execution?.paperclip_issue_id)}</code></div>
        <div><span>{execution?.kind === 'workflow' ? 'Workflow run' : 'AionUi team'}</span><code>{shortId(execution?.workflow_run_id || execution?.aion_team_id)}</code></div>
      </div>
      {paperclipUrl && execution?.paperclip_issue_id && (
        <a className="secondary-button link-button" href={paperclipUrl} target="_blank" rel="noreferrer">
          <ExternalLink size={16} />打开 Paperclip
        </a>
      )}
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
