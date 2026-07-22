import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Bot,
  CalendarClock,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  ClipboardCheck,
  Clock3,
  Copy,
  Cpu,
  Database,
  Trash2,
  ExternalLink,
  FileJson,
  FileUp,
  FileCheck2,
  FolderOpen,
  GitCompareArrows,
  History as HistoryIcon,
  Inbox,
  Library,
  ListTodo,
  LoaderCircle,
  Mail,
  MessageSquare,
  Smartphone,
  Network,
  Pause,
  Play,
  Plus,
  PencilLine,
  RefreshCw,
  Repeat2,
  RotateCcw,
  Save,
  Search,
  Send,
  Server,
  Settings,
  ShieldCheck,
  Sparkles,
  BrainCircuit,
  Scale,
  Square,
  Users,
  Zap,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  archiveTaskTemplate,
  archiveTeamBlueprint,
  approveWorkspaceMemory,
  answerRuntimeInput,
  changeExecutionApprovalMode,
  confirmPlan,
  connectProvider,
  configureMailOAuthClient,
  configureTelegram,
  continuePlanRun,
  controlPlan,
  createWorkspaceMemoryCandidate,
  createPairingInvitation,
  deletePlan,
  disableTelegram,
  disableMail,
  decideApproval,
  getMailAuthorization,
  getMailAuthorizationStatus,
  getMailSummary,
  getPairedDevices,
  getPlan,
  getPlanArtifact,
  getPlanArtifacts,
  getProviderConnection,
  getRuntimeInputArtifact,
  getRuntimeInputArtifacts,
  getWorkspaceMemories,
  getTelegramStatus,
  forkPlan,
  loadBootstrap,
  planArtifactContentUrl,
  preparePlanRerun,
  proposeProcessMemory,
  requestMailAuthorization,
  requestMailSummary,
  requestPlan,
  revokeWorkspaceMemory,
  revokePairedDevice,
  revisePlan,
  revisePlanExecutionProfile,
  revisePlanOrganization,
  revisePlanRuntimes,
  rollbackWorkspaceMemory,
  saveTaskTemplate,
  saveTaskTemplateFromPlan,
  saveTeamBlueprint,
  testTelegram,
} from './api';
import { WorkspaceMemoryDialog } from './workspace-memory-dialog';
import {
  canReviseWork,
  canSaveRuntimeRevision,
  homeActionView,
  observationPresentation,
  selectedBlueprintId,
  taskAdjustmentExamples,
} from './home-routing.js';
import {
  executionControlPresentation,
  formatExecutionElapsed,
  runtimeActivitySource,
  runtimeActivityTone,
  stageProgressPresentation,
  stageProgressSummary,
} from './execution-progress.js';
import {
  buildResultSummary,
  selectResultPreviewArtifacts,
} from './result-summary.js';
import type {
  ResultSummaryCheck,
  ResultSummaryFact,
} from './result-summary.js';
import { useLanguage } from './language';
import type { UiLanguage } from './i18n.js';
import { APP_VERSION } from './version';
import {
  currentWorkItem,
  latestWorkItems,
  shouldPollWork,
  workRunHistory,
} from './work-selection.js';
import {
  FEATURED_WORK_TEMPLATES,
  filterTaskPresets,
  localizedTaskPreset,
  TASK_PRESET_CATEGORIES,
  TASK_PRESETS,
} from './task-presets.js';
import type {
  FeaturedWorkTemplate,
  TaskPreset,
  TaskPresetCategoryId,
} from './task-presets.js';
import type {
  Bootstrap,
  AIProvider,
  AIProviderName,
  ActiveMemberProgress,
  AgentRuntimeAssignment,
  AgentObservation,
  ApprovalCard,
  ApprovalMode,
  CollaborationLoop,
  ExecutionProfile,
  Integration,
  MailAuthorizationJob,
  MailAuthorizationStatus,
  MailSummaryJob,
  PairedDevice,
  PairingInvitation,
  HomeAction,
  PlanArtifact,
  PlanArtifactPreview,
  PlanRecord,
  PlannedAgent,
  ProviderConnectionJob,
  ReportingLine,
  RunRecord,
  RepeatableWork,
  TaskRunHistory,
  TaskTemplate,
  TaskPlan,
  TeamBlueprint,
  RuntimeCapability,
  RuntimeActivity,
  RuntimeInputArtifact,
  RuntimeInputArtifactPreview,
  TelegramSetupStatus,
  WorkspaceMemoryStatus,
  WorkspaceMemoryView,
  WorkspaceConversation,
} from './types';

type View = 'workspace' | 'today' | 'work' | 'approvals' | 'settings';
type WorkTab = 'overview' | 'history' | 'settings';
type HistoryTab = 'process' | 'results';
type Translate = ReturnType<typeof useLanguage>['t'];
type LocalProviderName = Extract<AIProviderName, 'ollama' | 'lmstudio'>;
type CredentialProviderName = Exclude<AIProviderName, LocalProviderName>;

function isLocalProvider(provider: AIProviderName): provider is LocalProviderName {
  return provider === 'ollama' || provider === 'lmstudio';
}

function defaultWorkTab(record: PlanRecord | null | undefined): WorkTab {
  if (!record) return 'overview';
  return ['planning', 'ready'].includes(record.status) ? 'overview' : 'history';
}

function defaultHistoryTab(status?: PlanRecord['status'] | TaskRunHistory['status']): HistoryTab {
  return status && ['failed', 'cancelled', 'completed_unverified'].includes(status)
    ? 'results'
    : 'process';
}

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
  awaiting_input: '等待补充信息',
  pause_requested: '正在暂停',
  paused: '已暂停',
  resuming: '正在继续',
  cancel_requested: '正在终止',
  cancelled: '已终止',
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

function formatTime(value?: string | null, language: UiLanguage = 'en'): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(language === 'zh' ? 'zh-CN' : 'en-US', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
}

function formatDuration(value?: number | null): string {
  if (value == null) return '—';
  if (value < 60) return `${value.toFixed(1)}s`;
  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60);
  return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
}

function shortId(value?: string | null): string {
  if (!value) return '—';
  return value.length > 14 ? `${value.slice(0, 7)}…${value.slice(-5)}` : value;
}

function statusTone(status: string): string {
  if (['failed', 'offline'].includes(status)) return 'danger';
  if (['awaiting_approval', 'awaiting_input', 'pause_requested', 'paused', 'cancel_requested', 'attention', 'setup', 'ready'].includes(status)) return 'warning';
  if (['running', 'planning', 'dispatching', 'queued', 'confirmed', 'resuming'].includes(status)) return 'active';
  if (['cancelled', 'completed_unverified'].includes(status)) return 'neutral';
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

function translatedHomeAction(action: HomeAction, t: Translate): { title: string; summary: string } {
  let title = t(action.title);
  const pendingMatch = /^(\d+) 项待审批$/.exec(action.title);
  if (pendingMatch) {
    title = t('{count} 项待审批', { count: pendingMatch[1] });
  } else {
    const prefixes: Array<[string, string]> = [
      ['任务正在等待审批：', '任务正在等待审批：{title}'],
      ['需要你的信息：', '需要你的信息：{title}'],
      ['需要处理：', '需要处理：{title}'],
      ['正在推进：', '正在推进：{title}'],
    ];
    for (const [prefix, template] of prefixes) {
      if (action.title.startsWith(prefix)) {
        title = t(template, { title: action.title.slice(prefix.length) });
        break;
      }
    }
  }
  return { title, summary: t(action.summary) };
}

function translatedIntegrationDetail(detail: string | undefined, t: Translate): string {
  if (!detail) return '';
  const pendingMatch = /^待投影\s+(\d+)$/.exec(detail);
  if (pendingMatch) return t('待投影 {count}', { count: pendingMatch[1] });
  const localPatterns: Array<[RegExp, string]> = [
    [/^本地服务已启动，发现 (\d+) 个模型$/, '本地服务已启动，发现 {count} 个模型'],
    [/^发现 (\d+) 个本地模型；隐藏运行适配器待连接$/, '发现 {count} 个本地模型；隐藏运行适配器待连接'],
    [/^已连接 (\d+) 个本地模型；任务运行适配器待就绪$/, '已连接 {count} 个本地模型；任务运行适配器待就绪'],
    [/^已连接 (\d+) 个本地模型，可用于任务$/, '已连接 {count} 个本地模型，可用于任务'],
  ];
  for (const [pattern, template] of localPatterns) {
    const match = pattern.exec(detail);
    if (match) return t(template, { count: match[1] });
  }
  return t(detail);
}

function App() {
  const { language, t } = useLanguage();
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null);
  const [view, setView] = useState<View>('workspace');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [activePlan, setActivePlan] = useState<PlanRecord | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PlanRecord | null>(null);
  const [workspaceRevision, setWorkspaceRevision] = useState(0);
  const [workspaceBlueprint, setWorkspaceBlueprint] = useState<TeamBlueprint | null>(null);
  const [workspaceSeed, setWorkspaceSeed] = useState('');
  const [workFocusPlanId, setWorkFocusPlanId] = useState('');
  const [workFocusTab, setWorkFocusTab] = useState<WorkTab>('overview');
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
      setError(err instanceof Error ? err.message : t('控制台状态读取失败'));
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [t]);

  const refreshAfterIntegrationChange = useCallback(async () => {
    await refresh(true);
  }, [refresh]);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(true), 15000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const mergePlanIntoBootstrap = useCallback((record: PlanRecord) => {
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

  const mergePlan = useCallback((record: PlanRecord) => {
    setActivePlan(record);
    mergePlanIntoBootstrap(record);
  }, [mergePlanIntoBootstrap]);

  const decideWorkApproval = useCallback(async (
    record: PlanRecord,
    approval: ApprovalCard,
    decision: 'approve' | 'reject',
    decisionNote: string,
  ) => {
    if (approval.plan_id !== record.plan_id) {
      throw new Error(t('审批与当前任务不匹配，请刷新后重试。'));
    }
    await decideApproval(approval.approval_id, decision, decisionNote);
    let advanced = false;
    try {
      const next = await getPlan(record.plan_id);
      mergePlanIntoBootstrap(next);
      setActivePlan((current) => current?.plan_id === next.plan_id ? next : current);
      advanced = next.status !== 'awaiting_approval';
    } catch {
      // The existing task poll will reconcile the delivered decision without a blind resend.
    }
    if (advanced) await refresh(true);
  }, [mergePlanIntoBootstrap, refresh, t]);

  const focusedWorkPlan = useMemo(
    () => currentWorkItem(bootstrap?.plans || [], workFocusPlanId),
    [bootstrap?.plans, workFocusPlanId],
  );

  const activeParentPlan = useMemo(() => {
    if (!activePlan?.parent_plan_id || !bootstrap) return null;
    return bootstrap.plans.find((row) => row.plan_id === activePlan.parent_plan_id)?.plan || null;
  }, [activePlan?.parent_plan_id, bootstrap]);

  useEffect(() => {
    if (!activePlan) return;
    if (!['planning', 'confirmed', 'dispatching', 'running', 'awaiting_approval', 'awaiting_input', 'pause_requested', 'resuming', 'cancel_requested'].includes(activePlan.status)) {
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
    const planId = focusedWorkPlan?.plan_id;
    if (!planId || !shouldPollWork(view, focusedWorkPlan)) return;
    if (activePlan?.plan_id === planId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await getPlan(planId);
        if (!cancelled) mergePlanIntoBootstrap(next);
      } catch {
        // Keep the last visible record; the next detail poll retries independently.
      }
    };
    const timer = window.setInterval(() => void poll(), 2500);
    void poll();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [
    activePlan?.plan_id,
    focusedWorkPlan?.plan_id,
    focusedWorkPlan?.status,
    mergePlanIntoBootstrap,
    view,
  ]);

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
    setDrawerOpen(false);
    setWorkspaceBlueprint(null);
    setWorkspaceSeed('');
    setWorkspaceRevision((value) => value + 1);
    setView('workspace');
  };

  const openPlan = (plan: PlanRecord) => {
    setActivePlan(plan);
    setDrawerOpen(true);
  };

  const startWorkspaceTask = () => {
    setActivePlan(null);
    setDrawerOpen(false);
    setWorkspaceBlueprint(null);
    setWorkspaceSeed('');
    setWorkspaceRevision((value) => value + 1);
    setView('workspace');
  };

  const reviewWork = (record: PlanRecord) => {
    setActivePlan(record);
    setDrawerOpen(false);
    setWorkspaceBlueprint(null);
    setWorkspaceSeed('');
    setWorkspaceRevision((value) => value + 1);
    setView('workspace');
  };

  const changeView = (next: View) => {
    setDrawerOpen(false);
    setView(next);
  };

  const openHomeAction = (action: HomeAction) => {
    if (action.plan_id) {
      const target = bootstrap?.plans.find((record) => record.plan_id === action.plan_id);
      if (target && ['tasks', 'team'].includes(action.target)) {
        setWorkFocusPlanId(target.plan_id);
        setWorkFocusTab(action.target === 'team' ? 'overview' : defaultWorkTab(target));
        changeView('work');
        return;
      }
    }
    changeView(homeActionView(action.target) as View);
  };

  const title = t({
    workspace: '工作台',
    today: '今日',
    work: '工作',
    approvals: '审批',
    settings: '设置',
  }[view]);

  return (
    <div className="app-shell">
      <Sidebar
        view={view}
        onChange={changeView}
        privateAccess={bootstrap?.console_access?.exposure === 'private'}
      />
      <main className="main-area">
        <header className="topbar">
          <div className="topbar-title">
            <span className="eyebrow">OPSWITNESS · v{APP_VERSION}</span>
            <h1>{title}</h1>
          </div>
          <div className="topbar-actions">
            <button className="icon-button" type="button" title={t('刷新')} onClick={() => void refresh()}>
              <RefreshCw size={17} className={loading ? 'spin' : ''} />
            </button>
            <button
              className="icon-button approval-shortcut"
              type="button"
              title={t('审批')}
              aria-label={t('审批')}
              onClick={() => changeView('approvals')}
            >
              <ClipboardCheck size={18} />
              {bootstrap?.pending_approvals ? <span>{bootstrap.pending_approvals}</span> : null}
            </button>
            <button
              className="primary-button"
              type="button"
              onClick={view === 'workspace' ? startWorkspaceTask : openNewTask}
            >
              <Plus size={17} />
              {view === 'workspace' ? t('新对话') : t('新建工作')}
            </button>
          </div>
        </header>

        {error && (
          <div className="alert-banner" role="alert">
            <AlertTriangle size={17} />
            <span>{error}</span>
            <button type="button" onClick={() => void refresh()}>
              {t('重试')}
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
                  initialObjective={workspaceSeed}
                  previousPlan={activeParentPlan}
                  onPlan={async (body) => {
                    mergePlan(await requestPlan(body));
                  }}
                  onRevise={async (record, instruction) => {
                    mergePlan(await revisePlan(record.plan_id, instruction));
                  }}
                  onOrganizationSave={async (record, lines, loops) => {
                    mergePlan(await revisePlanOrganization(record.plan_id, lines, loops));
                  }}
                  runtimeCapabilities={bootstrap.runtime_capabilities}
                  onRuntimeSave={async (record, assignments) => {
                    mergePlan(await revisePlanRuntimes(record.plan_id, assignments));
                  }}
                  onProfileSave={async (record, profile) => {
                    mergePlan(await revisePlanExecutionProfile(record.plan_id, profile));
                  }}
                  taskTemplates={bootstrap.task_templates}
                  workspaceConversations={bootstrap.workspace_conversations || []}
                  onOpenWorkspaceConversation={async (conversation) => {
                    reviewWork(await getPlan(conversation.current_plan_id));
                  }}
                  onSaveConversationTemplate={async (conversation, name) => {
                    await saveTaskTemplateFromPlan(conversation.current_plan_id, name);
                    await refresh(true);
                  }}
                  onSaveTaskTemplate={async (name, objective) => {
                    await saveTaskTemplate(name, objective);
                    await refresh(true);
                  }}
                  onArchiveTaskTemplate={async (template) => {
                    await archiveTaskTemplate(template.template_id);
                    await refresh(true);
                  }}
                  blueprints={bootstrap.team_blueprints}
                  selectedBlueprint={workspaceBlueprint}
                  onBlueprintSelect={setWorkspaceBlueprint}
                  onArchiveBlueprint={async (blueprint) => {
                    await archiveTeamBlueprint(blueprint.blueprint_id);
                    setWorkspaceBlueprint((current) => (
                      current?.blueprint_id === blueprint.blueprint_id ? null : current
                    ));
                    await refresh(true);
                  }}
                  repeatableWorks={bootstrap.repeatable_works || []}
                  onPrepareRepeatableWork={async (work) => {
                    mergePlan(await preparePlanRerun(work.source_plan_id));
                  }}
                  workspaceMemoryStatus={bootstrap.workspace_memory || {
                    format: 'obsidian_markdown',
                    candidate_count: 0,
                    approved_count: 0,
                    vault_path: 'workspace-memory/vault',
                  }}
                  onLoadWorkspaceMemories={getWorkspaceMemories}
                  onCreateWorkspaceMemory={async (body) => {
                    const row = await createWorkspaceMemoryCandidate(body);
                    await refresh(true);
                    return row;
                  }}
                  onProposeProcessMemory={async (work) => {
                    const row = await proposeProcessMemory(work.source_plan_id);
                    await refresh(true);
                    return row;
                  }}
                  onApproveWorkspaceMemory={async (versionId, reason) => {
                    const row = await approveWorkspaceMemory(versionId, reason);
                    await refresh(true);
                    return row;
                  }}
                  onRevokeWorkspaceMemory={async (versionId, reason) => {
                    const row = await revokeWorkspaceMemory(versionId, reason);
                    await refresh(true);
                    return row;
                  }}
                  onRollbackWorkspaceMemory={async (versionId, reason) => {
                    const row = await rollbackWorkspaceMemory(versionId, reason);
                    await refresh(true);
                    return row;
                  }}
                  onConfirm={async (record, approvalMode) => {
                    if (!record.plan_sha256) throw new Error(t('方案哈希缺失'));
                    mergePlan(await confirmPlan(record.plan_id, record.plan_sha256, approvalMode));
                    void refresh(true);
                  }}
                  onAnswerInput={async (record, requestId, answer) => {
                    mergePlan(await answerRuntimeInput(record.plan_id, requestId, answer));
                    void refresh(true);
                  }}
                  onControl={async (record, action) => {
                    mergePlan(await controlPlan(record.plan_id, action));
                    void refresh(true);
                  }}
                  approvals={bootstrap.approvals}
                  approvalsAvailable={bootstrap.approvals_available}
                  onDecideApproval={decideWorkApproval}
                  onRestart={() => setActivePlan(null)}
                />
              )}
              {view === 'today' && (
                <TodayView
                  data={bootstrap}
                  mailJob={mailJob}
                  onMail={async () => setMailJob(await requestMailSummary())}
                  onMailSetup={() => setMailSetupOpen(true)}
                  onNewTask={openNewTask}
                  onAction={openHomeAction}
                />
              )}
              {view === 'work' && (
                <WorkView
                  plans={bootstrap.plans}
                  taskRuns={bootstrap.task_runs}
                  focusedPlanId={workFocusPlanId}
                  focusedTab={workFocusTab}
                  onFocus={(planId, tab) => {
                    setWorkFocusPlanId(planId);
                    setWorkFocusTab(tab);
                  }}
                  runtimeCapabilities={bootstrap.runtime_capabilities}
                  onReview={reviewWork}
                  onRerun={async (record) => {
                    const rerun = await preparePlanRerun(record.plan_id);
                    mergePlan(rerun);
                    setWorkFocusPlanId(rerun.plan_id);
                    reviewWork(rerun);
                  }}
                  onContinueRun={async (run, message) => {
                    const continued = await continuePlanRun(run.plan_id, message);
                    mergePlanIntoBootstrap(continued);
                    setWorkFocusPlanId(continued.plan_id);
                    setWorkFocusTab('overview');
                    await refresh(true);
                  }}
                  onFork={async (record) => {
                    const forked = await forkPlan(record.plan_id);
                    mergePlan(forked);
                    setWorkFocusPlanId(forked.plan_id);
                    reviewWork(forked);
                  }}
                  onRevise={async (record, instruction) => {
                    const revision = await revisePlan(record.plan_id, instruction);
                    mergePlan(revision);
                    setWorkFocusPlanId(revision.plan_id);
                  }}
                  onOrganizationSave={async (record, lines, loops) => {
                    const revision = await revisePlanOrganization(record.plan_id, lines, loops);
                    mergePlan(revision);
                    setWorkFocusPlanId(revision.plan_id);
                  }}
                  onRuntimeSave={async (record, assignments) => {
                    const revision = await revisePlanRuntimes(record.plan_id, assignments);
                    mergePlan(revision);
                    setWorkFocusPlanId(revision.plan_id);
                  }}
                  onProfileSave={async (record, profile) => {
                    const revision = await revisePlanExecutionProfile(record.plan_id, profile);
                    mergePlan(revision);
                    setWorkFocusPlanId(revision.plan_id);
                  }}
                  onSaveBlueprint={async (record, name) => {
                    await saveTeamBlueprint(record.plan_id, name);
                    await refresh(true);
                  }}
                  approvals={bootstrap.approvals}
                  approvalsAvailable={bootstrap.approvals_available}
                  onDecideApproval={decideWorkApproval}
                  onAnswerInput={async (record, requestId, answer) => {
                    mergePlanIntoBootstrap(
                      await answerRuntimeInput(record.plan_id, requestId, answer),
                    );
                    void refresh(true);
                  }}
                  onControl={async (record, action) => {
                    mergePlanIntoBootstrap(await controlPlan(record.plan_id, action));
                    void refresh(true);
                  }}
                  onApprovalModeChange={async (record, approvalMode, expectedCurrentMode) => {
                    mergePlanIntoBootstrap(
                      await changeExecutionApprovalMode(
                        record.plan_id,
                        approvalMode,
                        expectedCurrentMode,
                      ),
                    );
                    void refresh(true);
                  }}
                  onDelete={setDeleteTarget}
                  onNew={openNewTask}
                />
              )}
              {view === 'approvals' && (
                <ApprovalsView data={bootstrap} onChanged={refreshAfterIntegrationChange} />
              )}
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
        plans={bootstrap?.plans || []}
        onClose={() => setDrawerOpen(false)}
        onPlan={async (body) => {
          const record = await requestPlan(body);
          mergePlan(record);
        }}
        onRevise={async (record, instruction) => {
          mergePlan(await revisePlan(record.plan_id, instruction));
        }}
        onOrganizationSave={async (record, lines, loops) => {
          mergePlan(await revisePlanOrganization(record.plan_id, lines, loops));
        }}
        runtimeCapabilities={bootstrap?.runtime_capabilities || []}
        onRuntimeSave={async (record, assignments) => {
          mergePlan(await revisePlanRuntimes(record.plan_id, assignments));
        }}
        onProfileSave={async (record, profile) => {
          mergePlan(await revisePlanExecutionProfile(record.plan_id, profile));
        }}
        onConfirm={async (record, approvalMode) => {
          if (!record.plan_sha256) throw new Error(t('方案哈希缺失'));
          mergePlan(await confirmPlan(record.plan_id, record.plan_sha256, approvalMode));
          void refresh(true);
        }}
        onAnswerInput={async (record, requestId, answer) => {
          mergePlan(await answerRuntimeInput(record.plan_id, requestId, answer));
          void refresh(true);
        }}
        onControl={async (record, action) => {
          mergePlan(await controlPlan(record.plan_id, action));
          void refresh(true);
        }}
        approvals={bootstrap?.approvals || []}
        approvalsAvailable={bootstrap?.approvals_available ?? false}
        onDecideApproval={decideWorkApproval}
        onDelete={setDeleteTarget}
        onRestart={() => setActivePlan(null)}
      />
      <DeletePlanDialog
        record={deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={async (record) => {
          await deletePlan(record.plan_id);
          setBootstrap((current) => current ? {
            ...current,
            plans: current.plans.filter((row) => row.plan_id !== record.plan_id),
          } : current);
          if (activePlan?.plan_id === record.plan_id) {
            setActivePlan(null);
            setDrawerOpen(false);
          }
          setDeleteTarget(null);
        }}
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

function Sidebar({
  view,
  onChange,
  privateAccess = false,
}: {
  view: View;
  onChange: (view: View) => void;
  privateAccess?: boolean;
}) {
  const { t } = useLanguage();
  const accessLabel = t(privateAccess ? '私网 HTTPS 已启用' : '本地可信模式');
  const items = [
    { id: 'workspace' as const, label: '工作台', icon: MessageSquare },
    { id: 'work' as const, label: '工作', icon: ListTodo },
    { id: 'settings' as const, label: '设置', icon: Settings },
  ];
  return (
    <aside className="sidebar" aria-label={t('主导航')}>
      <div className="brand-mark" aria-label="OpsWitness">OW</div>
      <nav>
        {items.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            className={view === id ? 'nav-button active' : 'nav-button'}
            title={t(label)}
            aria-label={t(label)}
            onClick={() => onChange(id)}
          >
            <Icon size={20} />
            <span>{t(label)}</span>
          </button>
        ))}
      </nav>
      <div className="sidebar-shield" title={accessLabel} aria-label={accessLabel}>
        <ShieldCheck size={18} />
      </div>
    </aside>
  );
}

function IntegrationRow({ integrations }: { integrations?: Record<string, Integration> }) {
  const { t } = useLanguage();
  if (!integrations) return null;
  return (
    <div className="integration-row" aria-label={t('服务状态')}>
      {['ai', 'governance', 'evidence'].map((key) => {
        const item = integrations[key];
        if (!item) return null;
        return (
          <span key={key} className="integration-pill" title={translatedIntegrationDetail(item.detail || item.label, t)}>
            <span className={`status-dot ${statusTone(item.status)}`} />
            {t(item.label)}
          </span>
        );
      })}
    </div>
  );
}

function FeaturedWorkTemplateCard({
  template,
  language,
  disabled,
  onStart,
}: {
  template: FeaturedWorkTemplate;
  language: UiLanguage;
  disabled: boolean;
  onStart: (template: FeaturedWorkTemplate) => void;
}) {
  const { t } = useLanguage();
  const localized = localizedTaskPreset(template, language);
  const recipe = localized.recipe;
  if (!recipe) return null;
  return (
    <button
      className="featured-work-card"
      data-category={template.category}
      type="button"
      disabled={disabled}
      aria-label={t('生成团队：{name}', { name: localized.title })}
      onClick={() => onStart(template)}
    >
      <span className="featured-work-card-top">
        <span className="featured-work-badge">{t('成熟 Work 模板')}</span>
        <span>{t('{agents} 个 Agent · {stages} 个步骤', {
          agents: recipe.agentCount,
          stages: recipe.stageCount,
        })}</span>
      </span>
      <strong>{localized.title}</strong>
      <span className="featured-work-description">{localized.description}</span>
      <span className="featured-work-line"><Network size={14} />{recipe.team}</span>
      <span className="featured-work-line"><FileCheck2 size={14} />{recipe.outputs.join(' · ')}</span>
      <span className="featured-work-line"><ShieldCheck size={14} />{recipe.checkpoint}</span>
      <span className="featured-work-card-footer">
        <span><CalendarClock size={14} />{recipe.cadence}</span>
        <strong><Sparkles size={14} />{t('一键生成团队')}</strong>
      </span>
    </button>
  );
}

function TaskPresetDialog({
  language,
  onClose,
  onSelect,
}: {
  language: UiLanguage;
  onClose: () => void;
  onSelect: (preset: TaskPreset) => void;
}) {
  const { t } = useLanguage();
  const [category, setCategory] = useState<'all' | TaskPresetCategoryId>('all');
  const [query, setQuery] = useState('');
  const visiblePresets = filterTaskPresets(language, category, query);

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onClose]);

  return (
    <div className="modal-layer" role="dialog" aria-modal="true" aria-label={t('常用任务预设')}>
      <button className="modal-backdrop" type="button" aria-label={t('关闭任务预设')} onClick={onClose} />
      <section className="mail-setup-dialog task-preset-dialog">
        <header className="modal-header">
          <div>
            <span className="section-kicker">{t('任务起点')}</span>
            <h2>{t('常用任务预设')}</h2>
          </div>
          <button className="icon-button" type="button" title={t('关闭')} aria-label={t('关闭任务预设')} onClick={onClose}>
            <X size={19} />
          </button>
        </header>
        <div className="task-preset-content">
          <div className="task-preset-intro">
            <strong>{t('选择一个成熟场景，再交给 AI 生成完整团队与计划。')}</strong>
            <span>{t('预设只会填入任务描述；不会立即规划、执行或绕过确认。')}</span>
          </div>
          <label className="task-preset-search">
            <Search size={16} />
            <input
              type="search"
              value={query}
              aria-label={t('搜索常用任务')}
              placeholder={t('搜索任务、交付物或工作流…')}
              onChange={(event) => setQuery(event.target.value)}
            />
            <span>{t('显示 {count} 项', { count: visiblePresets.length })}</span>
          </label>
          <div className="task-preset-tabs" aria-label={t('任务类别')}>
            <button
              type="button"
              className={category === 'all' ? 'active' : ''}
              aria-pressed={category === 'all'}
              onClick={() => setCategory('all')}
            >
              {t('全部')}
            </button>
            {TASK_PRESET_CATEGORIES.map((item) => (
              <button
                key={item.id}
                type="button"
                className={category === item.id ? 'active' : ''}
                aria-pressed={category === item.id}
                onClick={() => setCategory(item.id)}
              >
                {item.label[language]}
              </button>
            ))}
          </div>
          {visiblePresets.length ? (
            <div className="task-preset-grid">
              {visiblePresets.map((preset) => {
                const featured = FEATURED_WORK_TEMPLATES.find((item) => item.id === preset.id);
                const localized = localizedTaskPreset(featured || preset, language);
                const categoryLabel = TASK_PRESET_CATEGORIES.find((item) => item.id === preset.category)?.label[language];
                return (
                  <button
                    key={preset.id}
                    className={`task-preset-card${localized.recipe ? ' featured' : ''}`}
                    data-category={preset.category}
                    type="button"
                    onClick={() => onSelect(preset)}
                  >
                    <span className="task-preset-card-top">
                      <span className="task-preset-category">
                        {localized.recipe ? t('成熟 Work 模板') : categoryLabel}
                      </span>
                      <ArrowRight size={16} />
                    </span>
                    <strong>{localized.title}</strong>
                    <span className="task-preset-description">{localized.description}</span>
                    {localized.recipe && (
                      <span className="task-preset-recipe">
                        <Network size={13} />
                        {t('{agents} 个 Agent · {stages} 个步骤', {
                          agents: localized.recipe.agentCount,
                          stages: localized.recipe.stageCount,
                        })}
                        <span>· {localized.recipe.cadence}</span>
                      </span>
                    )}
                    <span className="task-preset-action">{t('填入任务描述')}</span>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="task-preset-empty">
              <Search size={20} />
              <strong>{t('没有匹配的任务预设')}</strong>
              <span>{t('尝试其他关键词或任务类别。')}</span>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function TaskTemplateDialog({
  templates,
  initialObjective,
  onClose,
  onSelect,
  onSave,
  onArchive,
}: {
  templates: TaskTemplate[];
  initialObjective: string;
  onClose: () => void;
  onSelect: (template: TaskTemplate) => void;
  onSave: (name: string, objective: string) => Promise<void>;
  onArchive: (template: TaskTemplate) => Promise<void>;
}) {
  const { language, t } = useLanguage();
  const [query, setQuery] = useState('');
  const [name, setName] = useState('');
  const [objective, setObjective] = useState(initialObjective.trim());
  const [busy, setBusy] = useState('');
  const [archiveTarget, setArchiveTarget] = useState('');
  const [error, setError] = useState('');
  const locale = language === 'zh' ? 'zh-CN' : 'en-US';
  const normalizedQuery = query.trim().toLocaleLowerCase(locale);
  const visibleTemplates = templates.filter((template) => {
    if (!normalizedQuery) return true;
    return [template.name, template.objective].some((value) =>
      value.toLocaleLowerCase(locale).includes(normalizedQuery),
    );
  });

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onClose]);

  const save = async () => {
    const cleanName = name.trim();
    const cleanObjective = objective.trim();
    if (!cleanName || cleanObjective.length < 3 || busy) return;
    setBusy('save');
    setError('');
    try {
      await onSave(cleanName, cleanObjective);
      setName('');
      setObjective('');
    } catch (err) {
      setError(err instanceof Error ? err.message : t('任务模板保存失败'));
    } finally {
      setBusy('');
    }
  };

  const archive = async (template: TaskTemplate) => {
    if (busy) return;
    setBusy(template.template_id);
    setError('');
    try {
      await onArchive(template);
      setArchiveTarget('');
    } catch (err) {
      setError(err instanceof Error ? err.message : t('任务模板删除失败'));
    } finally {
      setBusy('');
    }
  };

  return (
    <div className="modal-layer" role="dialog" aria-modal="true" aria-label={t('我的任务模板')}>
      <button className="modal-backdrop" type="button" aria-label={t('关闭我的任务模板')} onClick={onClose} />
      <section className="mail-setup-dialog task-template-dialog">
        <header className="modal-header">
          <div>
            <span className="section-kicker">{t('你的任务起点')}</span>
            <h2>{t('我的任务模板')}</h2>
          </div>
          <button className="icon-button" type="button" title={t('关闭')} aria-label={t('关闭我的任务模板')} onClick={onClose}>
            <X size={19} />
          </button>
        </header>
        <div className="task-template-content">
          <form
            className="task-template-form"
            aria-label={t('保存任务模板')}
            onSubmit={(event) => {
              event.preventDefault();
              void save();
            }}
          >
            <div className="task-template-form-heading">
              <div>
                <strong>{t('保存一个常用任务')}</strong>
                <span>{t('模板只保存在这台设备上；使用时仍需 AI 规划和你的确认。')}</span>
              </div>
              <Save size={18} />
            </div>
            <label>
              <span>{t('模板名称')}</span>
              <input
                value={name}
                maxLength={100}
                placeholder={t('例如：每周客户进展复盘')}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label>
              <span>{t('任务描述')}</span>
              <textarea
                value={objective}
                rows={4}
                maxLength={2000}
                placeholder={t('描述目标、输入、交付物、限制和人工检查点…')}
                onChange={(event) => setObjective(event.target.value)}
              />
            </label>
            <div className="task-template-form-actions">
              <span>{t('保存不会启动规划或执行')}</span>
              <button className="primary-button" type="submit" disabled={!name.trim() || objective.trim().length < 3 || Boolean(busy)}>
                {busy === 'save' ? <LoaderCircle size={16} className="spin" /> : <Save size={16} />}
                {t('保存模板')}
              </button>
            </div>
          </form>

          <div className="task-template-library-heading">
            <div>
              <strong>{t('已保存模板')}</strong>
              <span>{t('{count} 个模板', { count: templates.length })}</span>
            </div>
            <label className="task-preset-search task-template-search">
              <Search size={16} />
              <input
                type="search"
                value={query}
                aria-label={t('搜索我的任务模板')}
                placeholder={t('搜索名称或任务描述…')}
                onChange={(event) => setQuery(event.target.value)}
              />
              <span>{t('显示 {count} 项', { count: visibleTemplates.length })}</span>
            </label>
          </div>

          {visibleTemplates.length ? (
            <div className="task-template-grid">
              {visibleTemplates.map((template) => (
                <article className="task-template-card" key={template.template_id}>
                  <div className="task-template-card-copy">
                    <span className="task-preset-category">{t('我的模板')}</span>
                    <strong>{template.name}</strong>
                    <p>{template.objective}</p>
                    <small>{formatTime(template.created_at, language)} · {shortId(template.template_sha256)}</small>
                  </div>
                  {archiveTarget === template.template_id ? (
                    <div className="task-template-delete-confirm" role="status">
                      <span>{t('删除这个模板？')}</span>
                      <button type="button" onClick={() => setArchiveTarget('')} disabled={Boolean(busy)}>{t('取消')}</button>
                      <button className="danger-button" type="button" onClick={() => void archive(template)} disabled={Boolean(busy)}>
                        {busy === template.template_id ? <LoaderCircle size={14} className="spin" /> : <Trash2 size={14} />}
                        {t('删除')}
                      </button>
                    </div>
                  ) : (
                    <div className="task-template-card-actions">
                      <button className="secondary-button" type="button" onClick={() => onSelect(template)}>
                        <ArrowRight size={15} />{t('使用模板')}
                      </button>
                      <button className="icon-button" type="button" title={t('删除模板')} aria-label={t('删除模板：{name}', { name: template.name })} onClick={() => setArchiveTarget(template.template_id)}>
                        <Trash2 size={15} />
                      </button>
                    </div>
                  )}
                </article>
              ))}
            </div>
          ) : (
            <div className="task-preset-empty task-template-empty">
              <Save size={20} />
              <strong>{templates.length ? t('没有匹配的任务模板') : t('还没有自己的任务模板')}</strong>
              <span>{templates.length ? t('尝试其他关键词。') : t('把经常重复的目标保存在上方，之后可以一键填入。')}</span>
            </div>
          )}
          {error && <InlineError text={error} />}
        </div>
      </section>
    </div>
  );
}

function ConversationTemplateDialog({
  conversation,
  onClose,
  onSave,
}: {
  conversation: WorkspaceConversation;
  onClose: () => void;
  onSave: (name: string) => Promise<void>;
}) {
  const { t } = useLanguage();
  const [name, setName] = useState(conversation.title);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onClose();
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [busy, onClose]);

  const save = async () => {
    const cleanName = name.trim();
    if (!cleanName || !confirmed || busy) return;
    setBusy(true);
    setError('');
    try {
      await onSave(cleanName);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('历史模板保存失败'));
      setBusy(false);
    }
  };

  return (
    <div className="modal-layer" role="dialog" aria-modal="true" aria-label={t('从历史保存模板')}>
      <button
        className="modal-backdrop"
        type="button"
        aria-label={t('关闭从历史保存模板')}
        onClick={() => !busy && onClose()}
      />
      <section className="mail-setup-dialog conversation-template-dialog">
        <header className="modal-header">
          <div>
            <span className="section-kicker">{t('对话历史')}</span>
            <h2>{t('从历史保存模板')}</h2>
          </div>
          <button
            className="icon-button"
            type="button"
            disabled={busy}
            title={t('关闭')}
            aria-label={t('关闭从历史保存模板')}
            onClick={onClose}
          >
            <X size={19} />
          </button>
        </header>
        <form
          className="task-template-content conversation-template-content"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <div className="conversation-template-source">
            <HistoryIcon size={18} />
            <div>
              <strong>{conversation.title}</strong>
              <span>{t('{count} 个版本 · 来源方案 {id} · 哈希 {hash}', {
                count: conversation.version_count,
                id: shortId(conversation.current_plan_id),
                hash: shortId(conversation.current_plan_sha256),
              })}</span>
              <p>{conversation.objective}</p>
            </div>
          </div>
          <label className="conversation-template-name">
            <span>{t('模板名称')}</span>
            <input
              autoFocus
              value={name}
              maxLength={100}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label className="confirm-check conversation-template-confirm">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            <span><ShieldCheck size={15} />{t('我确认将这个已审核方案保存为可复用任务模板')}</span>
          </label>
          <div className="conversation-template-boundary">
            <ShieldCheck size={15} />
            <span>{t('模板绑定此方案版本与哈希；保存不会启动规划或执行。')}</span>
          </div>
          {error && <InlineError text={error} />}
          <div className="conversation-template-actions">
            <button className="secondary-button" type="button" disabled={busy} onClick={onClose}>
              {t('取消')}
            </button>
            <button className="primary-button" type="submit" disabled={!name.trim() || !confirmed || busy}>
              {busy ? <LoaderCircle size={16} className="spin" /> : <Save size={16} />}
              {t('保存模板')}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function TeamBlueprintDialog({
  blueprints,
  selectedBlueprint,
  onClose,
  onSelect,
  onArchive,
}: {
  blueprints: TeamBlueprint[];
  selectedBlueprint: TeamBlueprint | null;
  onClose: () => void;
  onSelect: (blueprint: TeamBlueprint) => void;
  onArchive: (blueprint: TeamBlueprint) => Promise<void>;
}) {
  const { t } = useLanguage();
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onClose]);

  const archive = async (blueprint: TeamBlueprint) => {
    if (busy) return;
    setBusy(blueprint.blueprint_id);
    setError('');
    try {
      await onArchive(blueprint);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('团队蓝图归档失败'));
    } finally {
      setBusy('');
    }
  };

  return (
    <div className="modal-layer" role="dialog" aria-modal="true" aria-label={t('团队蓝图')}>
      <button className="modal-backdrop" type="button" aria-label={t('关闭团队蓝图')} onClick={onClose} />
      <section className="mail-setup-dialog task-template-dialog">
        <header className="modal-header">
          <div>
            <span className="section-kicker">{t('可复用结构')}</span>
            <h2>{t('团队蓝图')}</h2>
          </div>
          <button className="icon-button" type="button" title={t('关闭')} aria-label={t('关闭团队蓝图')} onClick={onClose}>
            <X size={19} />
          </button>
        </header>
        <div className="task-template-content">
          {blueprints.length ? (
            <div className="blueprint-list">
              {blueprints.map((blueprint) => (
                <div className="blueprint-row" key={blueprint.blueprint_id}>
                  <div>
                    <strong>{blueprint.name}</strong>
                    <small>{t('{agents} 个角色 · {loops} 个循环 · {status}', {
                      agents: blueprint.agents.length,
                      loops: blueprint.collaboration_loops.length,
                      status: t(blueprint.verification_status === 'verified' ? '已验证' : '未验证'),
                    })}</small>
                    <code>{shortId(blueprint.blueprint_sha256)}</code>
                  </div>
                  <div>
                    <button
                      className="secondary-button"
                      type="button"
                      disabled={Boolean(busy)}
                      onClick={() => onSelect(blueprint)}
                    >
                      {selectedBlueprint?.blueprint_id === blueprint.blueprint_id ? <Check size={15} /> : <ArrowRight size={15} />}
                      {selectedBlueprint?.blueprint_id === blueprint.blueprint_id ? t('已选择') : t('用于新工作')}
                    </button>
                    <button
                      className="icon-button"
                      type="button"
                      disabled={Boolean(busy)}
                      title={t('归档蓝图')}
                      aria-label={t('归档蓝图：{name}', { name: blueprint.name })}
                      onClick={() => void archive(blueprint)}
                    >
                      {busy === blueprint.blueprint_id ? <LoaderCircle size={16} className="spin" /> : <Trash2 size={16} />}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="work-empty">
              <Network size={28} />
              <strong>{t('还没有保存的蓝图')}</strong>
              <span>{t('从工作详情的设置页保存角色与协作结构。')}</span>
            </div>
          )}
          <div className="blueprint-boundary">
            <ShieldCheck size={15} />
            {t('蓝图只是新方案的输入。每次使用仍会生成完整方案、允许调整运行时，并要求重新确认。')}
          </div>
          {error && <InlineError text={error} />}
        </div>
      </section>
    </div>
  );
}

function WorkspaceView({
  record,
  initialObjective,
  previousPlan,
  onPlan,
  onRevise,
  onOrganizationSave,
  runtimeCapabilities,
  onRuntimeSave,
  onProfileSave,
  taskTemplates,
  workspaceConversations,
  onOpenWorkspaceConversation,
  onSaveConversationTemplate,
  onSaveTaskTemplate,
  onArchiveTaskTemplate,
  blueprints,
  selectedBlueprint,
  onBlueprintSelect,
  onArchiveBlueprint,
  repeatableWorks,
  onPrepareRepeatableWork,
  workspaceMemoryStatus,
  onLoadWorkspaceMemories,
  onCreateWorkspaceMemory,
  onProposeProcessMemory,
  onApproveWorkspaceMemory,
  onRevokeWorkspaceMemory,
  onRollbackWorkspaceMemory,
  onConfirm,
  onAnswerInput,
  onControl,
  approvals,
  approvalsAvailable,
  onDecideApproval,
  onRestart,
}: {
  record: PlanRecord | null;
  initialObjective: string;
  previousPlan: TaskPlan | null;
  onPlan: (body: {
    objective: string;
    constraints: string;
    workspace: string;
    preferred_cadence: string;
    blueprint_id?: string | null;
  }) => Promise<void>;
  onRevise: (record: PlanRecord, instruction: string) => Promise<void>;
  onOrganizationSave: (
    record: PlanRecord,
    lines: ReportingLine[],
    loops: CollaborationLoop[],
  ) => Promise<void>;
  runtimeCapabilities: RuntimeCapability[];
  onRuntimeSave: (
    record: PlanRecord,
    assignments: AgentRuntimeAssignment[],
  ) => Promise<void>;
  onProfileSave: (
    record: PlanRecord,
    profile: Exclude<ExecutionProfile, 'custom'>,
  ) => Promise<void>;
  taskTemplates: TaskTemplate[];
  workspaceConversations: WorkspaceConversation[];
  onOpenWorkspaceConversation: (conversation: WorkspaceConversation) => Promise<void>;
  onSaveConversationTemplate: (
    conversation: WorkspaceConversation,
    name: string,
  ) => Promise<void>;
  onSaveTaskTemplate: (name: string, objective: string) => Promise<void>;
  onArchiveTaskTemplate: (template: TaskTemplate) => Promise<void>;
  blueprints: TeamBlueprint[];
  selectedBlueprint: TeamBlueprint | null;
  onBlueprintSelect: (blueprint: TeamBlueprint | null) => void;
  onArchiveBlueprint: (blueprint: TeamBlueprint) => Promise<void>;
  repeatableWorks: RepeatableWork[];
  onPrepareRepeatableWork: (work: RepeatableWork) => Promise<void>;
  workspaceMemoryStatus: WorkspaceMemoryStatus;
  onLoadWorkspaceMemories: (
    query?: string,
    includeHistory?: boolean,
  ) => Promise<WorkspaceMemoryView[]>;
  onCreateWorkspaceMemory: (body: {
    kind: 'process' | 'knowledge';
    title: string;
    content: string;
    tags: string[];
    workspace?: string;
    source_plan_id?: string | null;
    supersedes_version_id?: string | null;
  }) => Promise<WorkspaceMemoryView>;
  onProposeProcessMemory: (work: RepeatableWork) => Promise<WorkspaceMemoryView>;
  onApproveWorkspaceMemory: (
    versionId: string,
    reason?: string,
  ) => Promise<WorkspaceMemoryView>;
  onRevokeWorkspaceMemory: (
    versionId: string,
    reason?: string,
  ) => Promise<WorkspaceMemoryView>;
  onRollbackWorkspaceMemory: (
    versionId: string,
    reason: string,
  ) => Promise<WorkspaceMemoryView>;
  onConfirm: (record: PlanRecord, approvalMode: ApprovalMode) => Promise<void>;
  onAnswerInput: (record: PlanRecord, requestId: string, answer: string) => Promise<void>;
  onControl: (record: PlanRecord, action: 'pause' | 'resume' | 'terminate') => Promise<void>;
  approvals: ApprovalCard[];
  approvalsAvailable: boolean;
  onDecideApproval: (
    record: PlanRecord,
    approval: ApprovalCard,
    decision: 'approve' | 'reject',
    decisionNote: string,
  ) => Promise<void>;
  onRestart: () => void;
}) {
  const { language, t } = useLanguage();
  const [draft, setDraft] = useState(initialObjective);
  const [submitting, setSubmitting] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [approvalMode, setApprovalMode] = useState<ApprovalMode>('automatic');
  const [revisionOpen, setRevisionOpen] = useState(false);
  const [presetOpen, setPresetOpen] = useState(false);
  const [templateOpen, setTemplateOpen] = useState(false);
  const [blueprintOpen, setBlueprintOpen] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [historyTemplateTarget, setHistoryTemplateTarget] = useState<WorkspaceConversation | null>(null);
  const [conversationBusy, setConversationBusy] = useState('');
  const [repeatableBusy, setRepeatableBusy] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    setConfirmed(false);
    setApprovalMode(record?.approval_mode === 'manual_all' ? 'manual_all' : 'automatic');
    setRevisionOpen(false);
    setError('');
  }, [record?.plan_id, record?.status]);

  const locked = Boolean(
    record && !['failed', 'cancelled', 'completed_unverified'].includes(record.status),
  );

  const planObjective = async (objective: string) => {
    if (objective.length < 3 || submitting || locked) return;
    setSubmitting(true);
    setError('');
    try {
      await onPlan({
        objective,
        constraints: '',
        workspace: '',
        preferred_cadence: inferCadence(objective),
        blueprint_id: selectedBlueprintId(selectedBlueprint),
      });
      setDraft('');
    } catch (err) {
      setError(err instanceof Error ? err.message : t('规划请求失败'));
    } finally {
      setSubmitting(false);
    }
  };

  const submit = async () => {
    await planObjective(draft.trim());
  };

  const startFeaturedTemplate = async (template: FeaturedWorkTemplate) => {
    const objective = localizedTaskPreset(template, language).objective;
    setDraft(objective);
    await planObjective(objective);
  };

  const confirm = async () => {
    if (!record || !confirmed || submitting) return;
    setSubmitting(true);
    setError('');
    try {
      await onConfirm(record, approvalMode);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('确认失败'));
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
      setError(err instanceof Error ? err.message : t('方案修改失败'));
    } finally {
      setSubmitting(false);
    }
  };

  const restart = () => {
    setDraft('');
    onRestart();
  };

  const closePresetLibrary = useCallback(() => setPresetOpen(false), []);
  const selectPreset = useCallback((preset: TaskPreset) => {
    setDraft(localizedTaskPreset(preset, language).objective);
    setPresetOpen(false);
  }, [language]);
  const closeTaskTemplates = useCallback(() => setTemplateOpen(false), []);
  const selectTaskTemplate = useCallback((template: TaskTemplate) => {
    setDraft(template.objective);
    setTemplateOpen(false);
  }, []);
  const closeTeamBlueprints = useCallback(() => setBlueprintOpen(false), []);
  const selectTeamBlueprint = useCallback((blueprint: TeamBlueprint) => {
    onBlueprintSelect(blueprint);
    setBlueprintOpen(false);
  }, [onBlueprintSelect]);
  const prepareRepeatableWork = async (work: RepeatableWork) => {
    if (submitting || repeatableBusy) return;
    setRepeatableBusy(work.work_id);
    setError('');
    try {
      await onPrepareRepeatableWork(work);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('无法准备这项可重复 Work'));
    } finally {
      setRepeatableBusy('');
    }
  };

  const openWorkspaceConversation = async (conversation: WorkspaceConversation) => {
    if (conversationBusy || submitting) return;
    setConversationBusy(conversation.conversation_id);
    setError('');
    try {
      await onOpenWorkspaceConversation(conversation);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('无法打开这段对话历史'));
    } finally {
      setConversationBusy('');
    }
  };

  return (
    <section className="workspace-shell" aria-label={t('AI 工作台')}>
      <div className="chat-thread" aria-live="polite">
        {!record ? (
          <div className="chat-empty">
            <div className="chat-empty-mark"><Sparkles size={24} /></div>
            <h2>{t('今天要完成什么？')}</h2>
            {workspaceConversations.length > 0 && (
              <section className="workspace-conversation-section" aria-labelledby="workspace-conversation-title">
                <div className="featured-work-heading">
                  <div>
                    <span className="section-kicker">{t('对话历史')}</span>
                    <strong id="workspace-conversation-title">{t('继续之前的规划')}</strong>
                  </div>
                  <small>{t('选择历史会恢复其最新方案版本；不会自动执行。')}</small>
                </div>
                <div className="workspace-conversation-list">
                  {workspaceConversations.slice(0, 8).map((conversation) => (
                    <article className="workspace-conversation-row" key={conversation.conversation_id}>
                      <button
                        className="workspace-conversation-open"
                        type="button"
                        disabled={Boolean(conversationBusy)}
                        aria-label={t('打开对话：{title}', { title: conversation.title })}
                        onClick={() => void openWorkspaceConversation(conversation)}
                      >
                        <span className="workspace-conversation-icon"><HistoryIcon size={17} /></span>
                        <span className="workspace-conversation-copy">
                          <strong>{conversation.title}</strong>
                          <small>{t('{count} 个版本 · {time}', {
                            count: conversation.version_count,
                            time: formatTime(conversation.updated_at, language),
                          })}</small>
                        </span>
                        <StatusBadge status={conversation.status} />
                        {conversationBusy === conversation.conversation_id
                          ? <LoaderCircle size={17} className="spin" />
                          : <ChevronRight size={17} />}
                      </button>
                      <button
                        className="workspace-conversation-template-button"
                        type="button"
                        disabled={!conversation.template_source_available || Boolean(conversationBusy)}
                        title={conversation.template_source_available
                          ? t('从历史创建模板')
                          : t('此对话尚未形成完整可复用方案')}
                        onClick={() => setHistoryTemplateTarget(conversation)}
                      >
                        <Save size={15} />
                        <span>{t('保存为模板')}</span>
                      </button>
                    </article>
                  ))}
                </div>
              </section>
            )}
            {selectedBlueprint && (
              <div className="selected-blueprint" role="status">
                <Network size={16} />
                <span>{t('将参考团队蓝图：')}<strong>{selectedBlueprint.name}</strong></span>
                <button type="button" onClick={() => onBlueprintSelect(null)} aria-label={t('移除团队蓝图')}>
                  <X size={14} />
                </button>
              </div>
            )}
            {repeatableWorks.length > 0 && (
              <div className="repeatable-work-section">
                <div className="featured-work-heading">
                  <div>
                    <span className="section-kicker">{t('我的可重复 Work')}</span>
                    <strong>{t('沿用已经验证过的团队与流程')}</strong>
                  </div>
                  <small>{t('点击后生成待确认的新版本，不会直接执行。')}</small>
                </div>
                <div className="repeatable-work-list">
                  {repeatableWorks.slice(0, 4).map((work) => (
                    <button
                      className="repeatable-work-row"
                      type="button"
                      key={work.work_id}
                      disabled={Boolean(repeatableBusy)}
                      onClick={() => void prepareRepeatableWork(work)}
                    >
                      <span className="repeatable-work-icon"><Repeat2 size={17} /></span>
                      <span>
                        <strong>{work.title}</strong>
                        <small>{t('{agents} 个 Agent · 第 {version} 版 · {cadence}', {
                          agents: work.agent_count,
                          version: work.revision_number,
                          cadence: t(cadenceOptions.find((item) => item.value === work.cadence)?.label || work.cadence),
                        })}</small>
                      </span>
                      {repeatableBusy === work.work_id
                        ? <LoaderCircle size={17} className="spin" />
                        : <><span className="repeatable-work-action">{t('准备运行')}</span><ChevronRight size={17} /></>}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="featured-work-section">
              <div className="featured-work-heading">
                <div>
                  <span className="section-kicker">{t('重点 Work 模板')}</span>
                  <strong>{t('从商业分析与专业证据包开始')}</strong>
                </div>
                <small>{t('一键生成可确认的 Agent 架构；确认前不会执行。')}</small>
              </div>
              <div className="featured-work-grid">
                {FEATURED_WORK_TEMPLATES.slice(0, 4).map((template) => (
                  <FeaturedWorkTemplateCard
                    key={template.id}
                    template={template}
                    language={language}
                    disabled={submitting || locked}
                    onStart={(selected) => void startFeaturedTemplate(selected)}
                  />
                ))}
              </div>
            </div>
            <button className="preset-library-trigger" type="button" onClick={() => setPresetOpen(true)}>
              <span className="preset-library-icon"><Library size={18} /></span>
              <span>
                <strong>{t('浏览 31 个常用任务')}</strong>
                <small>{t('含 10 个成熟模板，以及更多灵活任务起点')}</small>
              </span>
              <ChevronRight size={17} />
            </button>
            <button className="preset-library-trigger user-template-trigger" type="button" onClick={() => setTemplateOpen(true)}>
              <span className="preset-library-icon"><Save size={18} /></span>
              <span>
                <strong>{t('我的任务模板')}</strong>
                <small>{taskTemplates.length
                  ? t('{count} 个已保存模板，可随时复用', { count: taskTemplates.length })
                  : t('保存常用目标，之后一键填入')}</small>
              </span>
              <ChevronRight size={17} />
            </button>
            <button className="preset-library-trigger blueprint-library-trigger" type="button" onClick={() => setBlueprintOpen(true)}>
              <span className="preset-library-icon"><Network size={18} /></span>
              <span>
                <strong>{t('团队蓝图')}</strong>
                <small>{blueprints.length
                  ? t('{count} 个已保存蓝图，可用于新工作', { count: blueprints.length })
                  : t('保存并复用 Agent 角色与协作结构')}</small>
              </span>
              <ChevronRight size={17} />
            </button>
            <button className="preset-library-trigger memory-library-trigger" type="button" onClick={() => setMemoryOpen(true)}>
              <span className="preset-library-icon"><BrainCircuit size={18} /></span>
              <span>
                <strong>{t('Workspace 记忆')}</strong>
                <small>{workspaceMemoryStatus.approved_count
                  ? t('{approved} 条已批准 · {candidates} 条待审核', {
                    approved: workspaceMemoryStatus.approved_count,
                    candidates: workspaceMemoryStatus.candidate_count,
                  })
                  : t('审核流程经验和知识后，供新 Work 只读使用')}</small>
              </span>
              <ChevronRight size={17} />
            </button>
          </div>
        ) : (
          <>
            <div className="chat-message user-message">
              <div className="chat-user-bubble">
                {record.objective}
                {record.parent_plan_id && record.revision_instruction && (
                  <small>{t('修改要求：')}{record.revision_instruction}</small>
                )}
                {record.source_blueprint_id && (
                  <small>{t('已参考团队蓝图 · {id}', { id: shortId(record.source_blueprint_id) })}</small>
                )}
                {record.memory_version_ids?.length > 0 && (
                  <small>{t('已绑定 {count} 条已批准记忆 · {hash}', {
                    count: record.memory_version_ids.length,
                    hash: shortId(record.memory_snapshot_sha256),
                  })}</small>
                )}
              </div>
              <div className="chat-avatar user-avatar">{t('你')}</div>
            </div>
            <div className="chat-message assistant-message">
              <div className="chat-avatar assistant-avatar"><Bot size={17} /></div>
              <div className="chat-assistant-content">
                <div className="chat-assistant-heading">
                  <strong>OpsWitness</strong>
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
                    onOrganizationSave={(lines, loops) => onOrganizationSave(record, lines, loops)}
                    runtimeCapabilities={runtimeCapabilities}
                    onRuntimeSave={(assignments) => onRuntimeSave(record, assignments)}
                    onProfileSave={(profile) => onProfileSave(record, profile)}
                  />
                )}
                {['confirmed', 'dispatching', 'running', 'pause_requested', 'paused', 'resuming', 'cancel_requested', 'cancelled', 'awaiting_approval', 'awaiting_input', 'completed_unverified', 'failed'].includes(record.status) && (
                  <ExecutionView
                    record={record}
                    approvals={approvals}
                    approvalsAvailable={approvalsAvailable}
                    onDecideApproval={(approval, decision, decisionNote) => (
                      onDecideApproval(record, approval, decision, decisionNote)
                    )}
                    onAnswerInput={(requestId, answer) => onAnswerInput(record, requestId, answer)}
                    onControl={(action) => onControl(record, action)}
                  />
                )}
                {record.status === 'ready' && (
                  <div className="chat-confirm-panel">
                    {revisionOpen ? (
                      <TaskAdjustmentChat
                        submitting={submitting}
                        onCancel={() => setRevisionOpen(false)}
                        onSubmit={revise}
                      />
                    ) : (
                      <>
                        <ApprovalModeControl mode={approvalMode} onChange={setApprovalMode} />
                        <label className="confirm-check">
                          <input
                            type="checkbox"
                            checked={confirmed}
                            onChange={(event) => setConfirmed(event.target.checked)}
                          />
                          <span><Check size={15} />{t('确认此方案并启动受管执行')}</span>
                        </label>
                        <div className="confirm-actions revision-actions">
                          <button className="secondary-button" type="button" onClick={() => setRevisionOpen(true)}>
                            <MessageSquare size={16} />{t('用 AI 调整')}
                          </button>
                          <button className="text-button" type="button" onClick={restart}>
                            <RotateCcw size={15} />{t('重新开始')}
                          </button>
                          <button
                            className="primary-button"
                            type="button"
                            disabled={!confirmed || submitting}
                            onClick={() => void confirm()}
                          >
                            {submitting ? <LoaderCircle size={17} className="spin" /> : <Play size={17} />}
                            {t('确认并运行')}
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
            aria-label={t('任务描述')}
            value={draft}
            rows={3}
            maxLength={2000}
            disabled={locked || submitting}
            placeholder={locked ? t('当前任务等待完成或确认') : t('描述你想完成的任务…')}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                void submit();
              }
            }}
          />
          <div className="chat-composer-actions">
            <span><ShieldCheck size={14} />{t('先规划，确认后运行')}</span>
            <button
              className="chat-send-button"
              type="submit"
              title={t('发送任务描述')}
              aria-label={t('发送任务描述')}
              disabled={draft.trim().length < 3 || submitting || locked}
            >
              {submitting ? <LoaderCircle size={18} className="spin" /> : <Send size={18} />}
            </button>
          </div>
        </form>
        {error && !record && <InlineError text={error} />}
      </div>
      {presetOpen && (
        <TaskPresetDialog
          language={language}
          onClose={closePresetLibrary}
          onSelect={selectPreset}
        />
      )}
      {templateOpen && (
        <TaskTemplateDialog
          templates={taskTemplates}
          initialObjective={draft}
          onClose={closeTaskTemplates}
          onSelect={selectTaskTemplate}
          onSave={onSaveTaskTemplate}
          onArchive={onArchiveTaskTemplate}
        />
      )}
      {blueprintOpen && (
        <TeamBlueprintDialog
          blueprints={blueprints}
          selectedBlueprint={selectedBlueprint}
          onClose={closeTeamBlueprints}
          onSelect={selectTeamBlueprint}
          onArchive={onArchiveBlueprint}
        />
      )}
      {memoryOpen && (
        <WorkspaceMemoryDialog
          status={workspaceMemoryStatus}
          repeatableWorks={repeatableWorks}
          onClose={() => setMemoryOpen(false)}
          onLoad={onLoadWorkspaceMemories}
          onCreate={onCreateWorkspaceMemory}
          onProposeProcess={onProposeProcessMemory}
          onApprove={onApproveWorkspaceMemory}
          onRevoke={onRevokeWorkspaceMemory}
          onRollback={onRollbackWorkspaceMemory}
        />
      )}
      {historyTemplateTarget && (
        <ConversationTemplateDialog
          conversation={historyTemplateTarget}
          onClose={() => setHistoryTemplateTarget(null)}
          onSave={async (name) => {
            await onSaveConversationTemplate(historyTemplateTarget, name);
            setHistoryTemplateTarget(null);
          }}
        />
      )}
    </section>
  );
}

function TodayView({
  data,
  mailJob,
  onMail,
  onMailSetup,
  onNewTask,
  onAction,
}: {
  data: Bootstrap;
  mailJob: MailSummaryJob | null;
  onMail: () => Promise<void>;
  onMailSetup: () => void;
  onNewTask: () => void;
  onAction: (action: HomeAction) => void;
}) {
  const { t } = useLanguage();
  return (
    <div className="today-layout">
      <section className="panel today-actions-panel">
        <div className="section-heading compact">
          <div>
            <span className="section-kicker">{t('今天')}</span>
            <h2>{t('先处理这些')}</h2>
          </div>
          <button className="secondary-button" type="button" onClick={onNewTask}>
            <Plus size={16} />{t('新任务')}
          </button>
        </div>
        {data.home.action_queue.length ? (
          <div className="home-action-list">
            {data.home.action_queue.map((action) => {
              const copy = translatedHomeAction(action, t);
              return (
                <button
                  key={action.action_id}
                  className={`home-action ${action.kind}`}
                  type="button"
                  onClick={() => onAction(action)}
                >
                  <span className="home-action-icon">
                    {action.kind === 'approval' ? <ClipboardCheck size={18} />
                      : action.kind === 'input_required' ? <MessageSquare size={18} />
                      : action.kind === 'task_blocked' || action.kind === 'operational' ? <AlertTriangle size={18} />
                        : action.kind === 'running' ? <Activity size={18} /> : <Inbox size={18} />}
                  </span>
                  <span><strong>{copy.title}</strong><small>{copy.summary}</small></span>
                  <ChevronRight size={18} />
                </button>
              );
            })}
          </div>
        ) : (
          <div className="today-clear-state">
            <CheckCircle2 size={22} />
            <span>{t('没有需要立即处理的事项。')}</span>
          </div>
        )}
      </section>

      <div className="today-grid">
        <section className="panel active-team-panel">
          <div className="section-heading compact">
            <div><span className="section-kicker">{t('正在推进')}</span><h2>{t('任务团队')}</h2></div>
            <span className="count-label">{data.home.active_teams.length}</span>
          </div>
          {data.home.active_teams.length ? (
            <div className="active-team-list">
              {data.home.active_teams.map((team) => (
                <div className="active-team-card" key={team.plan_id}>
                  <div className="active-team-heading">
                    <strong>{team.title}</strong><StatusBadge status={team.status} />
                  </div>
                  <div className="member-observation-list">
                    {team.members.map((member) => <MemberObservationBadge key={member.agent_name} member={member} />)}
                  </div>
                  <small>{t('成员状态只表示已观测到的执行信号，不证明业务结果。')}</small>
                </div>
              ))}
            </div>
          ) : (
            <div className="team-empty compact-empty"><Bot size={24} /><strong>{t('当前没有运行中的团队')}</strong><span>{t('创建任务后，团队进度会显示在这里。')}</span></div>
          )}
        </section>

        <section className="panel mail-panel">
          <div className="section-heading">
            <div>
              <span className="section-kicker">{t('今天')}</span>
              <h2>{t('邮箱摘要')}</h2>
            </div>
            <Mail size={20} />
          </div>
          <MailSummary data={data} job={mailJob} onRun={onMail} onSetup={onMailSetup} />
        </section>
      </div>
      <details className="panel health-disclosure">
        <summary><span><Activity size={16} />{t('运行健康')}</span><ChevronDown size={16} /></summary>
        <div>
          <span>{t('自动化覆盖：{status}', { status: t(data.home.health.coverage_status === 'full' ? '完整' : data.home.health.coverage_status === 'partial' ? '不完整' : '不可用') })}</span>
          <span>{t('已纳管任务：{count}', { count: data.home.health.monitored_jobs })}</span>
          <span>{t('待同步证据：{count}', { count: data.home.health.pending_projection })}</span>
          <span>{t(data.home.health.fleet_healthy ? '当前没有健康告警' : '存在需要检查的运行项')}</span>
        </div>
      </details>
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
  const { t } = useLanguage();
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
          {t('{count} 封匹配邮件', { count: job.message_count })}
          <button className="text-button" type="button" onClick={() => void run()}>
            {t('重新生成')}
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
        <strong>{t('摘要未生成')}</strong>
        <span>{job.error}</span>
        <button className="secondary-button" type="button" onClick={() => void run()}>{t('重试')}</button>
      </div>
    );
  }
  if (job?.status === 'running' || running) {
    return (
      <div className="empty-state">
        <LoaderCircle size={26} className="spin" />
        <strong>{t('正在生成摘要')}</strong>
        <span>{t('正在处理固定范围的未读邮件')}</span>
      </div>
    );
  }
  const detail = t(data.integrations.mail?.detail || '邮箱连接待配置');
  return (
    <div className="empty-state">
      <Inbox size={28} />
      <strong>{t(data.mail_ready ? '今日摘要尚未生成' : '邮箱尚未就绪')}</strong>
      <span>{data.mail_ready ? t('读取固定范围的未读邮件元数据') : detail}</span>
      <button
        className="secondary-button"
        type="button"
        onClick={data.mail_ready ? () => void run() : onSetup}
      >
        <Mail size={16} />
        {t(data.mail_ready ? '查看今日摘要' : '设置邮箱')}
      </button>
    </div>
  );
}

function WorkView({
  plans,
  taskRuns,
  focusedPlanId,
  focusedTab,
  onFocus,
  runtimeCapabilities,
  onReview,
  onRerun,
  onContinueRun,
  onFork,
  onRevise,
  onOrganizationSave,
  onRuntimeSave,
  onProfileSave,
  onSaveBlueprint,
  approvals,
  approvalsAvailable,
  onDecideApproval,
  onAnswerInput,
  onControl,
  onApprovalModeChange,
  onDelete,
  onNew,
}: {
  plans: PlanRecord[];
  taskRuns: TaskRunHistory[];
  focusedPlanId: string;
  focusedTab: WorkTab;
  onFocus: (planId: string, tab: WorkTab) => void;
  runtimeCapabilities: RuntimeCapability[];
  onReview: (record: PlanRecord) => void;
  onRerun: (record: PlanRecord) => Promise<void>;
  onContinueRun: (run: TaskRunHistory, message: string) => Promise<void>;
  onFork: (record: PlanRecord) => Promise<void>;
  onRevise: (record: PlanRecord, instruction: string) => Promise<void>;
  onOrganizationSave: (
    record: PlanRecord,
    lines: ReportingLine[],
    loops: CollaborationLoop[],
  ) => Promise<void>;
  onRuntimeSave: (
    record: PlanRecord,
    assignments: AgentRuntimeAssignment[],
  ) => Promise<void>;
  onProfileSave: (
    record: PlanRecord,
    profile: Exclude<ExecutionProfile, 'custom'>,
  ) => Promise<void>;
  onSaveBlueprint: (record: PlanRecord, name: string) => Promise<void>;
  approvals: ApprovalCard[];
  approvalsAvailable: boolean;
  onDecideApproval: (
    record: PlanRecord,
    approval: ApprovalCard,
    decision: 'approve' | 'reject',
    decisionNote: string,
  ) => Promise<void>;
  onAnswerInput: (record: PlanRecord, requestId: string, answer: string) => Promise<void>;
  onControl: (record: PlanRecord, action: 'pause' | 'resume' | 'terminate') => Promise<void>;
  onApprovalModeChange: (
    record: PlanRecord,
    approvalMode: 'automatic' | 'manual_all',
    expectedCurrentMode: ApprovalMode,
  ) => Promise<void>;
  onDelete: (record: PlanRecord) => void;
  onNew: () => void;
}) {
  const { language, t } = useLanguage();
  const workItems = useMemo(() => latestWorkItems(plans), [plans]);
  const [adjustmentBusy, setAdjustmentBusy] = useState(false);
  const [adjustmentError, setAdjustmentError] = useState('');
  const [blueprintName, setBlueprintName] = useState('');
  const [blueprintBusy, setBlueprintBusy] = useState(false);
  const [blueprintError, setBlueprintError] = useState('');
  const [rerunBusy, setRerunBusy] = useState(false);
  const [rerunError, setRerunError] = useState('');
  const [forkOpen, setForkOpen] = useState(false);
  const [forkBusy, setForkBusy] = useState(false);
  const [forkError, setForkError] = useState('');
  const [historyRunId, setHistoryRunId] = useState('');
  const [historyTabOverride, setHistoryTabOverride] = useState<HistoryTab | null>(null);
  const [continuationMessage, setContinuationMessage] = useState('');
  const [continuationBusy, setContinuationBusy] = useState(false);
  const [continuationError, setContinuationError] = useState('');

  const selected = workItems.find((record) => record.plan_id === focusedPlanId) || workItems[0];
  const tab = selected?.plan_id === focusedPlanId ? focusedTab : defaultWorkTab(selected);
  const historyRuns = useMemo(
    () => workRunHistory(selected, taskRuns),
    [selected, taskRuns],
  );
  const selectedHistoryRun = historyRuns.find((run) => run.plan_id === historyRunId)
    || historyRuns[0];
  const selectedHistoryRecord = selectedHistoryRun
    ? plans.find((record) => record.plan_id === selectedHistoryRun.plan_id)
    : undefined;
  const historyTab = historyTabOverride
    || defaultHistoryTab(selectedHistoryRun?.status || selected?.status);
  const canSaveBlueprint = Boolean(
    selected && selected.plan && ['ready', 'failed', 'cancelled', 'completed_unverified'].includes(selected.status),
  );
  const verifiedSource = Boolean(
    selected?.status === 'completed_unverified' && selected.execution?.outcome_verified,
  );
  const canRerun = Boolean(
    selected?.plan && ['failed', 'cancelled', 'completed_unverified'].includes(selected.status),
  );
  const canAdjustWork = Boolean(selected?.plan && canReviseWork(selected.status));
  const canFork = Boolean(selected?.plan && selected.plan_sha256 && selected.status !== 'planning');
  const currentWorkEnded = Boolean(
    selected && ['failed', 'cancelled', 'completed_unverified'].includes(selected.status),
  );
  const canContinueHistory = Boolean(
    selectedHistoryRun?.continuation_available
    && !selectedHistoryRun.deleted
    && currentWorkEnded,
  );

  useEffect(() => {
    setAdjustmentBusy(false);
    setAdjustmentError('');
    setBlueprintName('');
    setBlueprintError('');
    setRerunBusy(false);
    setRerunError('');
    setForkOpen(false);
    setForkBusy(false);
    setForkError('');
    setHistoryRunId('');
    setHistoryTabOverride(null);
    setContinuationMessage('');
    setContinuationBusy(false);
    setContinuationError('');
  }, [selected?.plan_id]);

  const reviseSelected = async (instruction: string) => {
    if (!selected || adjustmentBusy) return;
    setAdjustmentBusy(true);
    setAdjustmentError('');
    try {
      await onRevise(selected, instruction);
    } catch (err) {
      setAdjustmentError(err instanceof Error ? err.message : t('任务调整失败'));
    } finally {
      setAdjustmentBusy(false);
    }
  };

  const saveBlueprint = async () => {
    if (!selected || !blueprintName.trim() || blueprintBusy) return;
    setBlueprintBusy(true);
    setBlueprintError('');
    try {
      await onSaveBlueprint(selected, blueprintName.trim());
      setBlueprintName('');
    } catch (err) {
      setBlueprintError(err instanceof Error ? err.message : t('团队蓝图保存失败'));
    } finally {
      setBlueprintBusy(false);
    }
  };

  const rerunSelected = async () => {
    if (!selected || !canRerun || rerunBusy) return;
    setRerunBusy(true);
    setRerunError('');
    try {
      await onRerun(selected);
    } catch (err) {
      setRerunError(err instanceof Error ? err.message : t('重新运行准备失败'));
    } finally {
      setRerunBusy(false);
    }
  };

  const forkSelected = async () => {
    if (!selected || !canFork || forkBusy) return;
    setForkBusy(true);
    setForkError('');
    try {
      await onFork(selected);
      setForkOpen(false);
    } catch (err) {
      setForkError(err instanceof Error ? err.message : t('创建工作副本失败'));
    } finally {
      setForkBusy(false);
    }
  };

  const continueHistory = async () => {
    const message = continuationMessage.trim();
    if (!selectedHistoryRun || !canContinueHistory || !message || continuationBusy) return;
    setContinuationBusy(true);
    setContinuationError('');
    try {
      await onContinueRun(selectedHistoryRun, message);
      setContinuationMessage('');
    } catch (err) {
      setContinuationError(err instanceof Error ? err.message : t('历史运行继续失败'));
    } finally {
      setContinuationBusy(false);
    }
  };

  const chooseWork = (record: PlanRecord) => {
    onFocus(record.plan_id, defaultWorkTab(record));
  };

  const tabs: Array<{ id: WorkTab; label: string }> = [
    { id: 'overview', label: '概览' },
    { id: 'history', label: '历史' },
    { id: 'settings', label: '设置' },
  ];

  return (
    <div className="work-page">
      <section className="panel work-directory">
        <div className="section-heading compact">
          <div><span className="section-kicker">{t('全部工作')}</span><h2>{t('工作')}</h2></div>
          <button className="icon-button" type="button" title={t('新建工作')} onClick={onNew}><Plus size={17} /></button>
        </div>
        {workItems.length ? (
          <div className="work-selector" role="list" aria-label={t('工作列表')}>
            {workItems.map((record) => {
              const title = record.plan?.title || record.objective;
              return (
                <button
                  key={record.plan_id}
                  className={record.plan_id === selected?.plan_id ? 'active' : ''}
                  type="button"
                  role="listitem"
                  onClick={() => chooseWork(record)}
                >
                  <span>
                    <strong>{title}</strong>
                    <small>
                      {record.plan
                        ? t('{count} 名成员 · 第 {version} 版', {
                          count: record.plan.agents.length,
                          version: record.revision_number,
                        }) + (record.forked_from_plan_id ? ` · ${t('副本')}` : '')
                        : t('方案正在生成')}
                    </small>
                  </span>
                  <StatusBadge status={record.status} />
                </button>
              );
            })}
          </div>
        ) : (
          <div className="work-empty compact-empty">
            <ListTodo size={26} />
            <strong>{t('还没有工作')}</strong>
            <span>{t('描述一个目标，OpsWitness 会先生成团队和计划。')}</span>
            <button className="secondary-button" type="button" onClick={onNew}><Plus size={16} />{t('创建第一项工作')}</button>
          </div>
        )}
      </section>

      <section className="panel work-detail" aria-label={t('工作详情')}>
        {selected ? (
          <>
            <header className="work-detail-header">
              <div>
                <span className="section-kicker">{t('工作详情')}</span>
                <h2>{selected.plan?.title || selected.objective}</h2>
                <small>{shortId(selected.plan_id)} · {formatTime(selected.updated_at, language)}</small>
              </div>
              <div className="work-detail-header-actions">
                <StatusBadge status={selected.status} />
                {canRerun && (
                  <button
                    className="secondary-button"
                    type="button"
                    disabled={rerunBusy}
                    onClick={() => void rerunSelected()}
                  >
                    {rerunBusy
                      ? <LoaderCircle size={16} className="spin" />
                      : <RotateCcw size={16} />}
                    {t(rerunBusy ? '准备中' : '快速复跑')}
                  </button>
                )}
                {canFork && (
                  <button
                    className="secondary-button"
                    type="button"
                    disabled={forkBusy}
                    onClick={() => setForkOpen(true)}
                  >
                    <GitCompareArrows size={16} />{t('创建工作副本')}
                  </button>
                )}
                <button className="secondary-button" type="button" onClick={() => onReview(selected)}>
                  <ExternalLink size={16} />{t(selected.status === 'ready' ? '审阅并确认' : '打开完整方案')}
                </button>
              </div>
            </header>
            {rerunError && <div className="work-header-error"><InlineError text={rerunError} /></div>}
            <div className="work-tabs" role="tablist" aria-label={t('工作详情视图')}>
              {tabs.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  aria-selected={tab === item.id}
                  className={tab === item.id ? 'active' : ''}
                  onClick={() => onFocus(selected.plan_id, item.id)}
                >
                  {t(item.label)}
                </button>
              ))}
            </div>
            <div className="work-detail-body">
              {tab === 'overview' && (
                <div className="work-overview">
                  {selected.status === 'planning' && <PlanningProgressView progress={selected.planning_progress} />}
                  {selected.plan && (
                    <>
                      <div className="work-summary">
                        <p>{selected.plan.summary}</p>
                        <div className="plan-facts">
                          <span><Users size={15} />{selected.plan.agents.length} Agent</span>
                          {selected.plan.execution_profile && (
                            <span><Cpu size={15} />{t('执行档位：{profile}', { profile: t(executionProfileName(selected.plan.execution_profile)) })}</span>
                          )}
                          <span><Clock3 size={15} />{t('约 {count} 分钟', { count: selected.plan.estimated_duration_minutes })}</span>
                          <span><CalendarClock size={15} />{selected.plan.cadence.update_interval}</span>
                          <span><Repeat2 size={15} />{t('{count} 个有界循环', { count: selected.plan.collaboration_loops.length })}</span>
                        </div>
                      </div>
                      {canAdjustWork && (
                        <TaskAdjustmentChat
                          className="work-overview-adjustment"
                          submitting={adjustmentBusy}
                          onSubmit={reviseSelected}
                        />
                      )}
                      {adjustmentError && <InlineError text={adjustmentError} />}
                      {!['planning', 'ready'].includes(selected.status) && (
                        <div className="work-overview-shortcuts">
                          <button
                            className="secondary-button"
                            type="button"
                            onClick={() => {
                              setHistoryTabOverride('results');
                              onFocus(selected.plan_id, 'history');
                            }}
                          >
                            <FileCheck2 size={16} />{t('查看运行结果')}
                          </button>
                          <button
                            className="secondary-button"
                            type="button"
                            onClick={() => {
                              setHistoryTabOverride('process');
                              onFocus(selected.plan_id, 'history');
                            }}
                          >
                            <Activity size={16} />{t('查看执行过程')}
                          </button>
                        </div>
                      )}
                      <section className="work-overview-team" aria-label={t('团队')}>
                        <div className="review-title">
                          <h3>{t('团队')}</h3>
                          <span>{selected.plan.agents.length} Agent</span>
                        </div>
                        <OrganizationChart
                          plan={selected.plan}
                          editable={selected.status === 'ready' && selected.plan.execution_mode === 'aion_team'}
                          onSave={(lines, loops) => onOrganizationSave(selected, lines, loops)}
                        />
                        {selected.status === 'ready' && (
                          <RuntimeAssignments
                            agents={selected.plan.agents}
                            capabilities={runtimeCapabilities}
                            executionProfile={selected.plan.execution_profile}
                            onProfileSave={(profile) => onProfileSave(selected, profile)}
                            onSave={(assignments) => onRuntimeSave(selected, assignments)}
                          />
                        )}
                        {selected.status !== 'ready' && (
                          <div className="organization-readonly-note"><ShieldCheck size={15} />{t('执行中的组织关系已由方案哈希锁定，只能查看。')}</div>
                        )}
                      </section>
                    </>
                  )}
                  {!selected.plan && selected.status !== 'planning' && (
                    <div className="work-empty">
                      <AlertTriangle size={26} />
                      <strong>{t('方案不可用')}</strong>
                      <span>{selected.error || t('打开完整方案查看错误详情。')}</span>
                    </div>
                  )}
                </div>
              )}

              {tab === 'history' && (
                <div className="work-history">
                  <div className="work-evidence-note">
                    <HistoryIcon size={17} />
                    <span>{t('每次运行都保留独立证据。继续历史运行会复用所选团队上下文，但创建新的不可变版本和运行记录。')}</span>
                  </div>
                  {historyRuns.length && selectedHistoryRun ? (
                    <div className="work-history-layout">
                      <div className="work-run-list" role="list" aria-label={t('运行历史')}>
                        {historyRuns.map((run) => (
                          <button
                            key={run.run_id}
                            type="button"
                            role="listitem"
                            className={run.plan_id === selectedHistoryRun.plan_id ? 'active' : ''}
                            onClick={() => {
                              setHistoryRunId(run.plan_id);
                              setHistoryTabOverride(null);
                              setContinuationMessage('');
                              setContinuationError('');
                            }}
                          >
                            <span className="work-run-version">v{run.revision_number}</span>
                            <span className="work-run-copy">
                              <strong>{run.title}</strong>
                              <small>{formatTime(run.started_at, language)} · {formatDuration(run.duration_s)}</small>
                            </span>
                            <StatusBadge status={run.status} />
                          </button>
                        ))}
                      </div>
                      <section className="work-run-detail" aria-label={t('运行详情')}>
                        <header className="work-run-detail-header">
                          <div>
                            <span className="section-kicker">RUN · v{selectedHistoryRun.revision_number}</span>
                            <h3>{selectedHistoryRun.title}</h3>
                            <small>{shortId(selectedHistoryRun.run_id)} · {formatTime(selectedHistoryRun.updated_at, language)}</small>
                          </div>
                          <StatusBadge status={selectedHistoryRun.status} />
                        </header>
                        <div className="work-run-facts">
                          <span><small>{t('执行方式')}</small><strong>{selectedHistoryRun.execution_mode === 'workflow' ? 'Workflow' : t('Agent 团队')}</strong></span>
                          <span><small>{t('团队')}</small><strong>{selectedHistoryRun.agent_count} Agent</strong></span>
                          <span><small>{t('耗时')}</small><strong>{formatDuration(selectedHistoryRun.duration_s)}</strong></span>
                          <span><small>{t('结果证据')}</small><strong>{t(selectedHistoryRun.outcome_verified ? '已核验' : '待核验')}</strong></span>
                        </div>
                        {selectedHistoryRun.continued_from_plan_id && (
                          <div className="work-run-provenance">
                            <GitCompareArrows size={14} />
                            <span>{t('由历史运行继续')}</span>
                            <code>{shortId(selectedHistoryRun.continued_from_plan_id)}</code>
                          </div>
                        )}
                        <div className="work-run-content-tabs" role="tablist" aria-label={t('运行内容')}>
                          <button
                            type="button"
                            role="tab"
                            aria-selected={historyTab === 'process'}
                            className={historyTab === 'process' ? 'active' : ''}
                            onClick={() => setHistoryTabOverride('process')}
                          >
                            <Activity size={15} />{t('过程')}
                          </button>
                          <button
                            type="button"
                            role="tab"
                            aria-selected={historyTab === 'results'}
                            className={historyTab === 'results' ? 'active' : ''}
                            onClick={() => setHistoryTabOverride('results')}
                          >
                            <FileCheck2 size={15} />{t('结果')}
                          </button>
                        </div>
                        {historyTab === 'process' && (
                          <div className="work-run-process" role="tabpanel">
                            {selectedHistoryRecord ? (
                              <>
                                <ExecutionView
                                  record={selectedHistoryRecord}
                                  approvals={approvals}
                                  approvalsAvailable={approvalsAvailable}
                                  onDecideApproval={(approval, decision, decisionNote) => (
                                    onDecideApproval(selectedHistoryRecord, approval, decision, decisionNote)
                                  )}
                                  onAnswerInput={(requestId, answer) => onAnswerInput(selectedHistoryRecord, requestId, answer)}
                                  onControl={(action) => onControl(selectedHistoryRecord, action)}
                                  onApprovalModeChange={(approvalMode, expectedCurrentMode) => (
                                    onApprovalModeChange(selectedHistoryRecord, approvalMode, expectedCurrentMode)
                                  )}
                                />
                                <div className="work-evidence-note"><Activity size={17} /><span>{t('显示可验证的阶段状态和活动；不显示隐藏推理、原始工具参数或输出正文。')}</span></div>
                                {selectedHistoryRecord.plan && (
                                  <ExecutionStageList
                                    plan={selectedHistoryRecord.plan}
                                    execution={selectedHistoryRecord.execution}
                                    workStatus={selectedHistoryRecord.status}
                                  />
                                )}
                              </>
                            ) : (
                              <div className="work-empty compact-empty"><AlertTriangle size={22} /><span>{t('这次运行的方案版本暂时无法读取。')}</span></div>
                            )}
                            <section className="work-run-timeline">
                              <div className="review-title">
                                <h3>{t('证据时间线')}</h3>
                                <span>{t('{count} 个事件', { count: selectedHistoryRun.events.length })}</span>
                              </div>
                              {selectedHistoryRun.events.length ? (
                                <div className="work-timeline">
                                  {selectedHistoryRun.events.map((event) => (
                                    <div key={event.event_id}>
                                      <span className="status-dot active" />
                                      <div>
                                        <strong>{t(taskRunEventLabel[event.kind])}</strong>
                                        <small>{formatTime(event.ts, language)} · {shortId(event.event_id)}</small>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <div className="work-empty compact-empty"><HistoryIcon size={22} /><span>{t('这次运行没有可显示的账本事件。')}</span></div>
                              )}
                              {selectedHistoryRun.evidence_gap && (
                                <div className="history-warning"><AlertTriangle size={14} />{t('当前状态缺少对应的 ledger 证据')}</div>
                              )}
                            </section>
                          </div>
                        )}
                        {historyTab === 'results' && (
                          <div className="work-run-results" role="tabpanel">
                            {selectedHistoryRecord ? (
                              <>
                                <div className={selectedHistoryRecord.execution?.outcome_verified ? 'outcome-state verified' : 'outcome-state pending'}>
                                  {selectedHistoryRecord.execution?.outcome_verified ? <CheckCircle2 size={22} /> : <FileCheck2 size={22} />}
                                  <div>
                                    <strong>{t(selectedHistoryRecord.execution?.outcome_verified ? '业务结果已有核验证据' : '业务结果仍待核验')}</strong>
                                    <span>{t(selectedHistoryRecord.execution?.outcome_verified
                                      ? '结果证据已绑定到这次执行。'
                                      : '进程退出和 Agent 回应不能单独证明交付物正确。')}</span>
                                  </div>
                                </div>
                                <RunArtifactsPanel record={selectedHistoryRecord} />
                                {selectedHistoryRecord.plan ? (
                                  <>
                                    <div className="plan-details-grid">
                                      <DetailList title={t('预期交付物')} items={selectedHistoryRecord.plan.artifacts} empty={t('未声明交付物')} />
                                      <DetailList title={t('人工检查点')} items={selectedHistoryRecord.plan.approvals} empty={t('无额外审批')} />
                                    </div>
                                    <div className="hash-line"><ShieldCheck size={14} /><span>{t('方案哈希')}</span><code>{selectedHistoryRecord.plan_sha256 || '—'}</code></div>
                                  </>
                                ) : (
                                  <div className="work-empty compact-empty"><FileCheck2 size={22} /><span>{t('这次运行没有可读取的方案交付定义。')}</span></div>
                                )}
                              </>
                            ) : (
                              <div className="work-empty compact-empty"><AlertTriangle size={22} /><span>{t('这次运行的方案版本暂时无法读取。')}</span></div>
                            )}
                          </div>
                        )}
                        <div className="work-run-continuation">
                          <div className="work-run-continuation-heading">
                            <MessageSquare size={18} />
                            <div>
                              <strong>{t('继续和这次运行交互')}</strong>
                              <span>{t('消息正文只进入本机 Aion 会话；OpsWitness 账本只保存哈希。')}</span>
                            </div>
                          </div>
                          <textarea
                            value={continuationMessage}
                            maxLength={4000}
                            disabled={!canContinueHistory || continuationBusy}
                            placeholder={t('例如：基于上一轮结果，补充核验引用并生成一份修订报告。')}
                            onChange={(event) => setContinuationMessage(event.target.value)}
                          />
                          {!selectedHistoryRun.continuation_available && (
                            <div className="history-continuation-note"><AlertTriangle size={14} />{t('这次运行没有可证明的 Aion 团队上下文，不能安全续聊。')}</div>
                          )}
                          {selectedHistoryRun.continuation_available && !currentWorkEnded && (
                            <div className="history-continuation-note"><Clock3 size={14} />{t('请先等待当前 Work 版本结束，再继续历史运行。')}</div>
                          )}
                          {continuationError && <InlineError text={continuationError} />}
                          <div className="work-run-continuation-footer">
                            <span><ShieldCheck size={14} />{t('继续后会创建新的版本、方案哈希和独立运行证据。')}</span>
                            <button
                              className="primary-button"
                              type="button"
                              disabled={!canContinueHistory || !continuationMessage.trim() || continuationBusy}
                              onClick={() => void continueHistory()}
                            >
                              {continuationBusy ? <LoaderCircle size={16} className="spin" /> : <Send size={16} />}
                              {t(continuationBusy ? '正在续接历史运行' : '继续此运行')}
                            </button>
                          </div>
                        </div>
                      </section>
                    </div>
                  ) : (
                    <div className="work-empty"><HistoryIcon size={28} /><strong>{t('还没有运行历史')}</strong><span>{t('方案确认并启动后，每次运行会显示在这里。')}</span></div>
                  )}
                </div>
              )}

              {tab === 'settings' && (
                <div className="work-settings">
                  <section className="work-settings-section">
                    <div className="review-title"><h3>{t('计划设置')}</h3><span>{t('只读')}</span></div>
                    <div className="work-settings-list">
                      <div><span>{t('更新节奏')}</span><strong>{selected.plan?.cadence.update_interval || selected.preferred_cadence}</strong></div>
                      <div><span>{t('工作目录')}</span><code>{selected.workspace || '—'}</code></div>
                      <div><span>{t('来源蓝图')}</span><code>{shortId(selected.source_blueprint_id)}</code></div>
                      {selected.forked_from_plan_id && (
                        <div><span>{t('来源工作')}</span><code>{shortId(selected.forked_from_plan_id)}</code></div>
                      )}
                    </div>
                  </section>
                  {canSaveBlueprint && (
                    <section className="work-settings-section">
                      <div className="review-title"><h3>{t('保存团队蓝图')}</h3><span>{t(verifiedSource ? '已验证来源' : '未验证来源')}</span></div>
                      <p>{t('只保存角色、汇报关系、循环和运行时偏好，不保存任务正文。')}</p>
                      <div className="work-blueprint-form">
                        <input value={blueprintName} maxLength={100} placeholder={t('蓝图名称')} onChange={(event) => setBlueprintName(event.target.value)} />
                        <button className="secondary-button" type="button" disabled={!blueprintName.trim() || blueprintBusy} onClick={() => void saveBlueprint()}>
                          {blueprintBusy ? <LoaderCircle size={15} className="spin" /> : <Save size={15} />}{t('保存')}
                        </button>
                      </div>
                      {blueprintError && <InlineError text={blueprintError} />}
                    </section>
                  )}
                  <section className="work-settings-section danger-zone">
                    <div><h3>{t('从工作列表移除')}</h3><p>{t('只创建可审计的可见性墓碑；历史记录和证据不会物理删除。')}</p></div>
                    <button
                      className="secondary-button danger-button"
                      type="button"
                      disabled={Boolean(planDeleteBlockReason(selected, plans))}
                      title={t(planDeleteBlockReason(selected, plans) || '删除任务')}
                      onClick={() => onDelete(selected)}
                    >
                      <Trash2 size={16} />{t('删除')}
                    </button>
                  </section>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="work-empty"><ListTodo size={30} /><strong>{t('选择或创建一项工作')}</strong><span>{t('团队、活动、交付物和设置都会集中显示在这里。')}</span></div>
        )}
      </section>
      {selected && forkOpen && (
        <div className="modal-layer" role="dialog" aria-modal="true" aria-label={t('创建独立工作副本？')}>
          <button
            className="modal-backdrop"
            type="button"
            aria-label={t('关闭')}
            disabled={forkBusy}
            onClick={() => setForkOpen(false)}
          />
          <section className="mail-setup-dialog fork-work-dialog">
            <header className="modal-header">
              <div><span className="section-kicker">FORK</span><h2>{t('创建独立工作副本？')}</h2></div>
              <button className="icon-button" type="button" title={t('关闭')} disabled={forkBusy} onClick={() => setForkOpen(false)}><X size={19} /></button>
            </header>
            <div className="mail-setup-content">
              <div className="fork-work-summary">
                <GitCompareArrows size={20} />
                <div><strong>{selected.plan?.title || selected.objective}</strong><span>{shortId(selected.plan_id)}</span></div>
              </div>
              <p className="fork-work-copy">{t('将复制已审核的方案、团队与设置，创建一项独立工作。')}</p>
              <p className="fork-work-copy">{t('运行、审批、用户回复和交付物不会复制。新工作必须重新审阅并确认后才能运行。')}</p>
              {forkError && <InlineError text={forkError} />}
              <div className="fork-work-actions">
                <button className="secondary-button" type="button" disabled={forkBusy} onClick={() => setForkOpen(false)}>{t('取消')}</button>
                <button className="primary-button" type="button" disabled={forkBusy} onClick={() => void forkSelected()}>
                  {forkBusy ? <LoaderCircle size={16} className="spin" /> : <GitCompareArrows size={16} />}
                  {t('创建副本')}
                </button>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

function LibraryView({
  taskTemplates,
  blueprints,
  onUsePreset,
  onUseTemplate,
  onUseBlueprint,
  onSaveTaskTemplate,
  onArchiveTaskTemplate,
  onArchiveBlueprint,
}: {
  taskTemplates: TaskTemplate[];
  blueprints: TeamBlueprint[];
  onUsePreset: (preset: TaskPreset) => void;
  onUseTemplate: (template: TaskTemplate) => void;
  onUseBlueprint: (blueprint: TeamBlueprint) => void;
  onSaveTaskTemplate: (name: string, objective: string) => Promise<void>;
  onArchiveTaskTemplate: (template: TaskTemplate) => Promise<void>;
  onArchiveBlueprint: (blueprint: TeamBlueprint) => Promise<void>;
}) {
  const { language, t } = useLanguage();
  const [tab, setTab] = useState<'common' | 'templates' | 'blueprints'>('common');
  const [category, setCategory] = useState<'all' | TaskPresetCategoryId>('all');
  const [query, setQuery] = useState('');
  const [templateQuery, setTemplateQuery] = useState('');
  const [templateName, setTemplateName] = useState('');
  const [templateObjective, setTemplateObjective] = useState('');
  const [busy, setBusy] = useState('');
  const [archiveTarget, setArchiveTarget] = useState('');
  const [error, setError] = useState('');
  const visiblePresets = filterTaskPresets(language, category, query);
  const locale = language === 'zh' ? 'zh-CN' : 'en-US';
  const normalizedTemplateQuery = templateQuery.trim().toLocaleLowerCase(locale);
  const visibleTemplates = taskTemplates.filter((template) => (
    !normalizedTemplateQuery
    || [template.name, template.objective].some((value) =>
      value.toLocaleLowerCase(locale).includes(normalizedTemplateQuery),
    )
  ));

  const saveTemplate = async () => {
    const name = templateName.trim();
    const objective = templateObjective.trim();
    if (!name || objective.length < 3 || busy) return;
    setBusy('save');
    setError('');
    try {
      await onSaveTaskTemplate(name, objective);
      setTemplateName('');
      setTemplateObjective('');
    } catch (err) {
      setError(err instanceof Error ? err.message : t('任务模板保存失败'));
    } finally {
      setBusy('');
    }
  };

  const archiveTemplate = async (template: TaskTemplate) => {
    if (busy) return;
    setBusy(template.template_id);
    setError('');
    try {
      await onArchiveTaskTemplate(template);
      setArchiveTarget('');
    } catch (err) {
      setError(err instanceof Error ? err.message : t('任务模板删除失败'));
    } finally {
      setBusy('');
    }
  };

  return (
    <div className="library-page">
      <div className="library-tabs" role="tablist" aria-label={t('资源库视图')}>
        <button type="button" role="tab" aria-selected={tab === 'common'} className={tab === 'common' ? 'active' : ''} onClick={() => setTab('common')}>
          {t('常用任务')} <span>{TASK_PRESETS.length}</span>
        </button>
        <button type="button" role="tab" aria-selected={tab === 'templates'} className={tab === 'templates' ? 'active' : ''} onClick={() => setTab('templates')}>
          {t('我的任务模板')} <span>{taskTemplates.length}</span>
        </button>
        <button type="button" role="tab" aria-selected={tab === 'blueprints'} className={tab === 'blueprints' ? 'active' : ''} onClick={() => setTab('blueprints')}>
          {t('团队蓝图')} <span>{blueprints.length}</span>
        </button>
      </div>

      {tab === 'common' && (
        <section className="panel library-panel">
          <div className="section-heading">
            <div>
              <span className="section-kicker">{t('任务起点')}</span>
              <h2>{t('常用任务')}</h2>
              <p>{t('选择一个成熟起点，再由 AI 生成完整团队和计划。')}</p>
            </div>
          </div>
          <div className="library-toolbar">
            <label className="task-preset-search">
              <Search size={16} />
              <input
                type="search"
                value={query}
                aria-label={t('搜索常用任务')}
                placeholder={t('搜索任务、交付物或工作流…')}
                onChange={(event) => setQuery(event.target.value)}
              />
              <span>{t('显示 {count} 项', { count: visiblePresets.length })}</span>
            </label>
            <div className="task-preset-tabs" aria-label={t('任务类别')}>
              <button type="button" className={category === 'all' ? 'active' : ''} aria-pressed={category === 'all'} onClick={() => setCategory('all')}>{t('全部')}</button>
              {TASK_PRESET_CATEGORIES.map((item) => (
                <button key={item.id} type="button" className={category === item.id ? 'active' : ''} aria-pressed={category === item.id} onClick={() => setCategory(item.id)}>
                  {item.label[language]}
                </button>
              ))}
            </div>
          </div>
          {visiblePresets.length ? (
            <div className="task-preset-grid library-grid">
              {visiblePresets.map((preset) => {
                const featured = FEATURED_WORK_TEMPLATES.find((item) => item.id === preset.id);
                const localized = localizedTaskPreset(featured || preset, language);
                const categoryLabel = TASK_PRESET_CATEGORIES.find((item) => item.id === preset.category)?.label[language];
                return (
                  <button key={preset.id} className={`task-preset-card${localized.recipe ? ' featured' : ''}`} data-category={preset.category} type="button" onClick={() => onUsePreset(preset)}>
                    <span className="task-preset-card-top"><span className="task-preset-category">{localized.recipe ? t('成熟 Work 模板') : categoryLabel}</span><ArrowRight size={16} /></span>
                    <strong>{localized.title}</strong>
                    <span className="task-preset-description">{localized.description}</span>
                    {localized.recipe && (
                      <span className="task-preset-recipe">
                        <Network size={13} />
                        {t('{agents} 个 Agent · {stages} 个步骤', { agents: localized.recipe.agentCount, stages: localized.recipe.stageCount })}
                        <span>· {localized.recipe.cadence}</span>
                      </span>
                    )}
                    <span className="task-preset-action">{t('用于新工作')}</span>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="task-preset-empty"><Search size={20} /><strong>{t('没有匹配的任务预设')}</strong><span>{t('尝试其他关键词或任务类别。')}</span></div>
          )}
        </section>
      )}

      {tab === 'templates' && (
        <section className="panel library-panel">
          <form className="task-template-form library-template-form" onSubmit={(event) => { event.preventDefault(); void saveTemplate(); }}>
            <div className="task-template-form-heading">
              <div><strong>{t('保存一个常用任务')}</strong><span>{t('模板只保存在这台设备上；使用时仍需 AI 规划和你的确认。')}</span></div>
              <Save size={18} />
            </div>
            <div className="library-template-fields">
              <label><span>{t('模板名称')}</span><input value={templateName} maxLength={100} placeholder={t('例如：每周客户进展复盘')} onChange={(event) => setTemplateName(event.target.value)} /></label>
              <label><span>{t('任务描述')}</span><textarea value={templateObjective} rows={4} maxLength={2000} placeholder={t('描述目标、输入、交付物、限制和人工检查点…')} onChange={(event) => setTemplateObjective(event.target.value)} /></label>
            </div>
            <div className="task-template-form-actions">
              <span>{t('保存不会启动规划或执行')}</span>
              <button className="primary-button" type="submit" disabled={!templateName.trim() || templateObjective.trim().length < 3 || Boolean(busy)}>
                {busy === 'save' ? <LoaderCircle size={16} className="spin" /> : <Save size={16} />}{t('保存模板')}
              </button>
            </div>
          </form>
          <div className="library-list-heading">
            <div><span className="section-kicker">{t('你的任务起点')}</span><h2>{t('我的任务模板')}</h2></div>
            <label className="task-preset-search task-template-search">
              <Search size={16} />
              <input type="search" value={templateQuery} aria-label={t('搜索我的任务模板')} placeholder={t('搜索名称或任务描述…')} onChange={(event) => setTemplateQuery(event.target.value)} />
              <span>{t('显示 {count} 项', { count: visibleTemplates.length })}</span>
            </label>
          </div>
          {visibleTemplates.length ? (
            <div className="task-template-grid library-grid">
              {visibleTemplates.map((template) => (
                <article className="task-template-card" key={template.template_id}>
                  <div className="task-template-card-copy">
                    <span className="task-preset-category">{t('我的模板')}</span>
                    <strong>{template.name}</strong>
                    <p>{template.objective}</p>
                    <small>{formatTime(template.created_at, language)} · {shortId(template.template_sha256)}</small>
                  </div>
                  {archiveTarget === template.template_id ? (
                    <div className="task-template-delete-confirm" role="status">
                      <span>{t('删除这个模板？')}</span>
                      <button type="button" onClick={() => setArchiveTarget('')} disabled={Boolean(busy)}>{t('取消')}</button>
                      <button className="danger-button" type="button" onClick={() => void archiveTemplate(template)} disabled={Boolean(busy)}>
                        {busy === template.template_id ? <LoaderCircle size={14} className="spin" /> : <Trash2 size={14} />}{t('删除')}
                      </button>
                    </div>
                  ) : (
                    <div className="task-template-card-actions">
                      <button className="secondary-button" type="button" onClick={() => onUseTemplate(template)}><ArrowRight size={15} />{t('用于新工作')}</button>
                      <button className="icon-button" type="button" title={t('删除模板')} aria-label={t('删除模板：{name}', { name: template.name })} onClick={() => setArchiveTarget(template.template_id)}><Trash2 size={15} /></button>
                    </div>
                  )}
                </article>
              ))}
            </div>
          ) : (
            <div className="task-preset-empty task-template-empty">
              <Save size={20} />
              <strong>{taskTemplates.length ? t('没有匹配的任务模板') : t('还没有自己的任务模板')}</strong>
              <span>{taskTemplates.length ? t('尝试其他关键词。') : t('把经常重复的目标保存在上方，之后可以一键填入。')}</span>
            </div>
          )}
          {error && <InlineError text={error} />}
        </section>
      )}

      {tab === 'blueprints' && (
        <section className="panel library-panel blueprint-panel">
          <div className="section-heading compact">
            <div><span className="section-kicker">{t('可复用结构')}</span><h2>{t('团队蓝图')}</h2></div>
            <span className="count-label">{blueprints.length}</span>
          </div>
          {blueprints.length ? (
            <div className="blueprint-list">
              {blueprints.map((blueprint) => (
                <div className="blueprint-row" key={blueprint.blueprint_id}>
                  <div>
                    <strong>{blueprint.name}</strong>
                    <small>{t('{agents} 个角色 · {loops} 个循环 · {status}', {
                      agents: blueprint.agents.length,
                      loops: blueprint.collaboration_loops.length,
                      status: t(blueprint.verification_status === 'verified' ? '已验证' : '未验证'),
                    })}</small>
                    <code>{shortId(blueprint.blueprint_sha256)}</code>
                  </div>
                  <div>
                    <button className="secondary-button" type="button" onClick={() => onUseBlueprint(blueprint)}>{t('用于新工作')}</button>
                    <button className="icon-button" type="button" title={t('归档蓝图')} aria-label={t('归档蓝图：{name}', { name: blueprint.name })} onClick={() => void onArchiveBlueprint(blueprint)}><Trash2 size={16} /></button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="work-empty"><Network size={28} /><strong>{t('还没有保存的蓝图')}</strong><span>{t('从工作详情的设置页保存角色与协作结构。')}</span></div>
          )}
          <div className="blueprint-boundary"><ShieldCheck size={15} />{t('蓝图只是新方案的输入。每次使用仍会生成完整方案、允许调整运行时，并要求重新确认。')}</div>
        </section>
      )}
    </div>
  );
}

function TasksView({
  plans,
  onOpen,
  onDelete,
  onNew,
}: {
  plans: PlanRecord[];
  onOpen: (plan: PlanRecord) => void;
  onDelete: (plan: PlanRecord) => void;
  onNew: () => void;
}) {
  const { t } = useLanguage();
  return (
    <section className="panel full-panel">
      <div className="section-heading compact">
        <div>
          <span className="section-kicker">{t('全部')}</span>
          <h2>{t('任务计划')}</h2>
        </div>
        <button className="secondary-button" type="button" onClick={onNew}>
          <Plus size={16} />{t('新建')}
        </button>
      </div>
      <PlanTable
        plans={plans}
        allPlans={plans}
        onOpen={onOpen}
        onDelete={onDelete}
        emptyAction={onNew}
      />
    </section>
  );
}

function TeamView({
  plans,
  onOpen,
  focusedPlanId,
  blueprints,
  onUseBlueprint,
  onSaveBlueprint,
  onArchiveBlueprint,
  onRevise,
  onOrganizationSave,
}: {
  plans: PlanRecord[];
  onOpen: (plan: PlanRecord) => void;
  focusedPlanId: string;
  blueprints: TeamBlueprint[];
  onUseBlueprint: (blueprint: TeamBlueprint) => void;
  onSaveBlueprint: (record: PlanRecord, name: string) => Promise<void>;
  onArchiveBlueprint: (blueprint: TeamBlueprint) => Promise<void>;
  onRevise: (record: PlanRecord, instruction: string) => Promise<void>;
  onOrganizationSave: (
    record: PlanRecord,
    lines: ReportingLine[],
    loops: CollaborationLoop[],
  ) => Promise<void>;
}) {
  const { t } = useLanguage();
  const teams = useMemo(
    () => plans.filter(
      (record) => record.plan && !plans.some((child) => child.parent_plan_id === record.plan_id),
    ),
    [plans],
  );
  const [tab, setTab] = useState<'teams' | 'blueprints'>('teams');
  const [selectedId, setSelectedId] = useState('');
  const [blueprintName, setBlueprintName] = useState('');
  const [blueprintBusy, setBlueprintBusy] = useState(false);
  const [blueprintError, setBlueprintError] = useState('');
  const [adjustmentBusy, setAdjustmentBusy] = useState(false);
  const [adjustmentError, setAdjustmentError] = useState('');
  useEffect(() => {
    if (!teams.length) {
      setSelectedId('');
      return;
    }
    const focused = teams.find((record) => record.plan_id === focusedPlanId);
    if (focused) {
      setSelectedId(focused.plan_id);
    } else if (!teams.some((record) => record.plan_id === selectedId)) {
      setSelectedId(teams[0].plan_id);
    }
  }, [focusedPlanId, selectedId, teams]);
  const selected = teams.find((record) => record.plan_id === selectedId) || teams[0];
  const canSaveBlueprint = Boolean(
    selected && ['ready', 'failed', 'completed_unverified'].includes(selected.status),
  );
  const verifiedSource = Boolean(
    selected?.status === 'completed_unverified' && selected.execution?.outcome_verified,
  );

  useEffect(() => {
    setAdjustmentBusy(false);
    setAdjustmentError('');
  }, [selected?.plan_id]);

  const saveBlueprint = async () => {
    if (!selected || !blueprintName.trim() || blueprintBusy) return;
    setBlueprintBusy(true);
    setBlueprintError('');
    try {
      await onSaveBlueprint(selected, blueprintName.trim());
      setBlueprintName('');
      setTab('blueprints');
    } catch (err) {
      setBlueprintError(err instanceof Error ? err.message : t('团队蓝图保存失败'));
    } finally {
      setBlueprintBusy(false);
    }
  };

  const reviseSelectedTask = async (instruction: string) => {
    if (!selected || adjustmentBusy) return;
    setAdjustmentBusy(true);
    setAdjustmentError('');
    try {
      await onRevise(selected, instruction);
    } catch (err) {
      setAdjustmentError(err instanceof Error ? err.message : t('任务调整失败'));
    } finally {
      setAdjustmentBusy(false);
    }
  };

  return (
    <div className="team-page">
      <div className="team-tabs" role="tablist" aria-label={t('团队视图')}>
        <button type="button" role="tab" aria-selected={tab === 'teams'} className={tab === 'teams' ? 'active' : ''} onClick={() => setTab('teams')}>{t('任务团队')}</button>
        <button type="button" role="tab" aria-selected={tab === 'blueprints'} className={tab === 'blueprints' ? 'active' : ''} onClick={() => setTab('blueprints')}>{t('团队蓝图')}</button>
      </div>
      {tab === 'teams' ? (
        selected?.plan ? (
          <div className="team-layout">
            <section className="panel team-directory">
              <div className="section-heading compact">
                <div><span className="section-kicker">{t('任务团队')}</span><h2>{t('当前分工')}</h2></div>
                <span className="count-label">{teams.length}</span>
              </div>
              <div className="team-selector" role="list" aria-label={t('任务团队')}>
                {teams.map((record) => (
                  <button key={record.plan_id} className={record.plan_id === selected.plan_id ? 'active' : ''} type="button" role="listitem" onClick={() => setSelectedId(record.plan_id)}>
                    <span><strong>{record.plan?.title || record.objective}</strong><small>{t('{count} 名成员 · 第 {version} 版', { count: record.plan?.agents.length || 0, version: record.revision_number })}</small></span>
                    <StatusBadge status={record.status} />
                  </button>
                ))}
              </div>
              {canSaveBlueprint && (
                <div className="blueprint-save-box">
                  <strong>{t(verifiedSource ? '这项已核验的任务可作为蓝图' : '手动保存为未验证蓝图')}</strong>
                  <span>{t(verifiedSource ? '系统建议保存，但不会自动创建或启用。' : '蓝图只保存角色与协作结构，不保存任务正文。')}</span>
                  <div><input value={blueprintName} maxLength={100} placeholder={t('蓝图名称')} onChange={(event) => setBlueprintName(event.target.value)} /><button className="secondary-button" type="button" disabled={!blueprintName.trim() || blueprintBusy} onClick={() => void saveBlueprint()}>{blueprintBusy ? <LoaderCircle size={15} className="spin" /> : <Save size={15} />}{t('保存')}</button></div>
                  {blueprintError && <InlineError text={blueprintError} />}
                </div>
              )}
            </section>
            <section className="panel team-organization-panel">
              <div className="section-heading compact team-panel-heading">
                <div><span className="section-kicker">{t('组织架构')}</span><h2>{selected.plan.title}</h2></div>
                <button className="secondary-button" type="button" onClick={() => onOpen(selected)}><ExternalLink size={16} />{t('任务详情')}</button>
              </div>
              {selected.status === 'ready' && (
                <TaskAdjustmentChat
                  submitting={adjustmentBusy}
                  onSubmit={reviseSelectedTask}
                  className="team-task-adjustment"
                />
              )}
              {adjustmentError && <InlineError text={adjustmentError} />}
              <OrganizationChart plan={selected.plan} editable={selected.status === 'ready'} onSave={(lines, loops) => onOrganizationSave(selected, lines, loops)} />
              {selected.status !== 'ready' && <div className="organization-readonly-note"><ShieldCheck size={15} />{t('执行中的组织关系已由方案哈希锁定，只能查看。')}</div>}
            </section>
          </div>
        ) : <section className="panel full-panel team-empty"><Network size={30} /><strong>{t('还没有可管理的任务团队')}</strong><span>{t('先在工作台生成一项任务，团队分工会显示在这里。')}</span></section>
      ) : (
        <section className="panel blueprint-panel">
          <div className="section-heading compact"><div><span className="section-kicker">{t('可复用结构')}</span><h2>{t('团队蓝图')}</h2></div><span className="count-label">{blueprints.length}</span></div>
          {blueprints.length ? <div className="blueprint-list">{blueprints.map((blueprint) => (
            <div className="blueprint-row" key={blueprint.blueprint_id}>
              <div><strong>{blueprint.name}</strong><small>{t('{agents} 个角色 · {loops} 个循环 · {status}', { agents: blueprint.agents.length, loops: blueprint.collaboration_loops.length, status: t(blueprint.verification_status === 'verified' ? '已验证' : '未验证') })}</small><code>{shortId(blueprint.blueprint_sha256)}</code></div>
              <div><button className="secondary-button" type="button" onClick={() => onUseBlueprint(blueprint)}>{t('用作新任务输入')}</button><button className="icon-button" type="button" title={t('归档蓝图')} aria-label={t('归档蓝图：{name}', { name: blueprint.name })} onClick={() => void onArchiveBlueprint(blueprint)}><Trash2 size={16} /></button></div>
            </div>
          ))}</div> : <div className="team-empty compact-empty"><Network size={28} /><strong>{t('还没有保存的蓝图')}</strong><span>{t('从一个非活动任务手动保存角色和协作结构后，会在这里出现。')}</span></div>}
          <div className="blueprint-boundary"><ShieldCheck size={15} />{t('蓝图只是新方案的输入。每次使用仍会生成完整方案、允许调整运行时，并要求重新确认。')}</div>
        </section>
      )}
    </div>
  );
}

function PlanTable({
  plans,
  allPlans,
  onOpen,
  onDelete,
  emptyAction,
}: {
  plans: PlanRecord[];
  allPlans: PlanRecord[];
  onOpen: (plan: PlanRecord) => void;
  onDelete: (plan: PlanRecord) => void;
  emptyAction: () => void;
}) {
  const { t, language } = useLanguage();
  if (!plans.length) {
    return (
      <div className="table-empty">
        <ListTodo size={28} />
        <span>{t('还没有任务')}</span>
        <button className="text-button" type="button" onClick={emptyAction}>{t('创建第一项')}</button>
      </div>
    );
  }
  return (
    <div className="data-table plan-table" role="table">
      <div className="table-head" role="row">
        <span>{t('任务')}</span><span>{t('架构')}</span><span>{t('状态')}</span><span>{t('更新时间')}</span><span /><span />
      </div>
      {plans.map((record) => {
        const title = record.plan?.title || record.objective;
        const deleteBlocked = planDeleteBlockReason(record, allPlans);
        return (
          <div className="plan-row" role="row" key={record.plan_id}>
            <button
              className="plan-row-main"
              type="button"
              aria-label={t('打开任务：{title}', { title })}
              onClick={() => onOpen(record)}
            >
              <span className="task-name-cell">
                <strong>{title}</strong>
                <small>{shortId(record.plan_id)}</small>
              </span>
              <span>{record.plan ? `${record.plan.agents.length} Agent` : '—'}</span>
              <span><StatusBadge status={record.status} /></span>
              <span>{formatTime(record.updated_at, language)}</span>
              <ChevronRight size={17} />
            </button>
            <button
              className="plan-delete-button"
              type="button"
              aria-label={t('删除任务：{title}', { title })}
              title={deleteBlocked ? t(deleteBlocked) : t('删除任务')}
              disabled={Boolean(deleteBlocked)}
              onClick={() => onDelete(record)}
            >
              <Trash2 size={16} />
            </button>
          </div>
        );
      })}
    </div>
  );
}

function planDeleteBlockReason(record: PlanRecord, plans: PlanRecord[]): string {
  if (plans.some((row) => row.parent_plan_id === record.plan_id)) {
    return '请先删除这个任务的较新修改版';
  }
  if (!['ready', 'failed', 'cancelled', 'completed_unverified'].includes(record.status)) {
    return record.status === 'planning'
      ? '规划中的任务暂不能删除'
      : '任务正在执行或等待处理，暂不能删除';
  }
  return '';
}

const taskRunEventLabel: Record<TaskRunHistory['events'][number]['kind'], string> = {
  task_plan_continuation_requested: '历史续聊请求已记账',
  task_plan_confirmed: '方案已确认',
  task_execution_requested: '执行请求已记账',
  task_execution_dispatched: 'Agent 已启动',
  task_plan_continuation_delivered: '续聊消息已送达原团队',
  task_input_requested: 'Agent 请求补充信息',
  task_input_answered: '用户回答已记账',
  task_input_delivered: '回答已送达 Agent',
  task_execution_pause_requested: '暂停请求已记账',
  task_execution_paused: '运行已暂停',
  task_execution_resume_requested: '继续请求已记账',
  task_execution_resumed: '运行已继续',
  task_execution_cancel_requested: '终止请求已记账',
  task_execution_cancelled: '运行已终止',
  task_execution_control_failed: '运行控制失败已记账',
  task_approval_mode_change_requested: '审批模式切换请求已记账',
  task_approval_mode_changed: '审批模式已切换',
  task_approval_mode_change_aborted: '审批模式切换已中止',
  task_approval_mode_change_recovered: '审批模式已安全恢复',
  task_execution_failed: '执行失败已记账',
  task_execution_finished: '执行终态已记账',
};

function HistoryView({
  taskRuns,
  automationRuns,
  data,
}: {
  taskRuns: TaskRunHistory[];
  automationRuns: RunRecord[];
  data: Bootstrap;
}) {
  const { t, language } = useLanguage();
  const [historyKind, setHistoryKind] = useState<'tasks' | 'automation'>('tasks');
  return (
    <div className="evidence-layout">
      <section className="metric-strip compact-metrics">
        <Metric label={t('AI 任务')} value={String(taskRuns.length)} detail={t('最近运行')} icon={Bot} tone="success" />
        <Metric label={t('自动化运行')} value={String(data.fleet.runs)} detail="append-only" icon={Database} tone="success" />
        <Metric label={t('待同步')} value={String(data.fleet.pending_projection)} detail={t('治理记录')} icon={RefreshCw} tone={data.fleet.pending_projection ? 'warning' : 'success'} />
      </section>
      <section className="panel full-panel">
        <div className="section-heading compact history-heading">
          <div><span className="section-kicker">EVIDENCE LEDGER</span><h2>{t('运行历史')}</h2></div>
          <div className="history-switch" role="tablist" aria-label={t('历史类型')}>
            <button
              type="button"
              role="tab"
              aria-selected={historyKind === 'tasks'}
              className={historyKind === 'tasks' ? 'active' : ''}
              onClick={() => setHistoryKind('tasks')}
            >
              {t('AI 任务')}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={historyKind === 'automation'}
              className={historyKind === 'automation' ? 'active' : ''}
              onClick={() => setHistoryKind('automation')}
            >
              {t('系统自动化')}
            </button>
          </div>
        </div>
        {historyKind === 'tasks' ? (
          taskRuns.length ? (
            <div className="task-history-list">
              <div className="task-history-head" aria-hidden="true">
                <span>{t('任务')}</span><span>{t('状态')}</span><span>{t('团队')}</span><span>{t('耗时')}</span><span>{t('更新时间')}</span><span />
              </div>
              {taskRuns.map((run) => (
                <details className="task-history-entry" key={run.run_id}>
                  <summary className="task-history-summary">
                    <span className="task-name-cell">
                      <strong>{run.title}</strong>
                      <small>
                        {shortId(run.run_id)} · {formatTime(run.updated_at, language)}
                        {run.deleted ? ` · ${t('已移除')}` : ''}
                      </small>
                    </span>
                    <StatusBadge status={run.status} />
                    <span className="history-team">{run.agent_count} Agent</span>
                    <span className="history-duration">{formatDuration(run.duration_s)}</span>
                    <span className="history-time">{formatTime(run.updated_at, language)}</span>
                    <ChevronDown className="history-chevron" size={17} />
                  </summary>
                  <div className="task-history-detail">
                    <div className="history-facts">
                      <span><small>Run</small><code>{run.run_id}</code></span>
                      <span><small>{t('执行方式')}</small><strong>{run.execution_mode === 'workflow' ? 'Workflow' : t('Agent 团队')}</strong></span>
                      <span><small>{t('方案版本')}</small><strong>v{run.revision_number}</strong></span>
                      <span><small>{t('结果证据')}</small><strong>{t(run.outcome_verified ? '已核验' : '待核验')}</strong></span>
                    </div>
                    <ol className="history-timeline">
                      {run.events.map((event) => (
                        <li key={event.event_id}>
                          <span><Check size={12} /></span>
                          <div><strong>{t(taskRunEventLabel[event.kind])}</strong><small>{formatTime(event.ts, language)}</small></div>
                        </li>
                      ))}
                    </ol>
                    {run.evidence_gap && (
                      <div className="history-warning"><AlertTriangle size={14} />{t('当前状态缺少对应的 ledger 证据')}</div>
                    )}
                  </div>
                </details>
              ))}
            </div>
          ) : (
            <div className="table-empty"><HistoryIcon size={28} /><span>{t('还没有已确认任务的运行记录')}</span></div>
          )
        ) : (
          <div className="data-table run-table" role="table">
            <div className="table-head" role="row"><span>Job</span><span>Run</span><span>{t('状态')}</span><span>{t('耗时')}</span><span>{t('时间')}</span></div>
            {automationRuns.map((run) => (
              <div className="table-row static" role="row" key={run.run_id}>
                <span className="task-name-cell"><strong>{run.job}</strong><small>exit {run.exit_code ?? '—'}</small></span>
                <code>{shortId(run.run_id)}</code>
                <StatusBadge status={run.status} />
                <span>{formatDuration(run.duration_s)}</span>
                <span>{formatTime(run.finished_ts || run.started_ts, language)}</span>
              </div>
            ))}
            {!automationRuns.length && (
              <div className="table-empty"><Database size={28} /><span>{t('还没有自动化运行记录')}</span></div>
            )}
          </div>
        )}
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
  const { t, language } = useLanguage();
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
      setError(err instanceof Error ? err.message : t('审批提交失败'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="approvals-layout">
      <section className="panel full-panel">
        <div className="section-heading compact">
          <div><span className="section-kicker">{t('人工检查点')}</span><h2>{t('待审批')}</h2></div>
          <span className="count-label">{data.approvals_available ? data.approvals.length : '—'}</span>
        </div>
        {!data.approvals_available ? (
          <div className="table-empty danger-state">
            <AlertTriangle size={28} />
            <span>{t('审批服务暂不可用，所有受管操作继续保持阻断。')}</span>
          </div>
        ) : data.approvals.length === 0 ? (
          <div className="table-empty">
            <ClipboardCheck size={28} />
            <span>{t('当前没有需要你处理的审批')}</span>
          </div>
        ) : (
          <div className="approval-list">
            {data.approvals.map((approval) => (
              <article className="approval-card" key={approval.approval_id}>
                <div className="approval-card-main">
                  <div className="approval-card-heading">
                    <span className="approval-kind"><ShieldCheck size={14} />{t(approval.kind === 'tool_call' ? '工具调用' : '治理请求')}</span>
                    <span>{formatTime(approval.requested_at, language)}</span>
                  </div>
                  <h3>{approval.title}</h3>
                  <p>{approval.summary}</p>
                  {approval.tool_name && (
                    <div className="approval-tool"><span>{t('工具')}</span><code>{approval.tool_name}</code></div>
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
                    <X size={16} />{t('拒绝')}
                  </button>
                  <button className="primary-button" type="button" onClick={() => openDecision(approval, 'approve')}>
                    <Check size={16} />{t('批准')}
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      {selected && (
        <div className="modal-layer" role="dialog" aria-modal="true" aria-label={t('确认审批决定')}>
          <button className="modal-backdrop" type="button" aria-label={t('关闭')} onClick={() => !busy && setSelected(null)} />
          <section className="mail-setup-dialog approval-dialog">
            <header className="modal-header">
              <div><span className="section-kicker">{t('人工决定')}</span><h2>{t(decision === 'approve' ? '批准这项操作' : '拒绝这项操作')}</h2></div>
              <button className="icon-button" type="button" title={t('关闭')} disabled={busy} onClick={() => setSelected(null)}><X size={19} /></button>
            </header>
            <div className="mail-setup-content">
              <div className="decision-summary"><strong>{selected.title}</strong><span>{selected.summary}</span></div>
              <label className="secret-field">
                <span>{t('决定说明（可选）')}</span>
                <textarea rows={3} maxLength={500} value={decisionNote} onChange={(event) => setDecisionNote(event.target.value)} placeholder={t('记录为什么批准或拒绝')} />
              </label>
              <label className="consent-row">
                <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
                <span>{t('我已检查这项请求的内容、工具和风险，并确认本次决定')}</span>
              </label>
              {error && <InlineError text={error} />}
              <button
                className={decision === 'approve' ? 'primary-button full-button' : 'secondary-button danger-button full-button'}
                type="button"
                disabled={!confirmed || busy}
                onClick={() => void submitDecision()}
              >
                {busy ? <LoaderCircle size={17} className="spin" /> : decision === 'approve' ? <Check size={17} /> : <X size={17} />}
                {t(decision === 'approve' ? '确认批准' : '确认拒绝')}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

function SystemAutomationHistory({ runs }: { runs: RunRecord[] }) {
  const { language, t } = useLanguage();
  const visibleRuns = runs.slice(0, 8);
  return (
    <section className="diagnostics-history" aria-label={t('系统自动化历史')}>
      <div className="diagnostics-history-heading">
        <span><HistoryIcon size={15} />{t('系统自动化历史')}</span>
        <small>{t('最近 {count} 条', { count: visibleRuns.length })}</small>
      </div>
      {visibleRuns.length ? (
        <div className="diagnostics-run-list">
          {visibleRuns.map((run) => (
            <div className="diagnostics-run-row" key={run.run_id}>
              <div>
                <strong>{run.job}</strong>
                <small>{shortId(run.run_id)} · exit {run.exit_code ?? '—'} · {formatDuration(run.duration_s)}</small>
              </div>
              <StatusBadge status={run.status} />
              <time>{formatTime(run.finished_ts || run.started_ts, language)}</time>
            </div>
          ))}
        </div>
      ) : (
        <div className="diagnostics-history-empty">{t('还没有自动化运行记录')}</div>
      )}
      <p>{t('任务级历史保留在每项 Work 的 Activity 中；这里仅显示无法归属到单项 Work 的系统运行。')}</p>
    </section>
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
  const { language, setLanguage, t } = useLanguage();
  const [job, setJob] = useState<ProviderConnectionJob | null>(null);
  const [error, setError] = useState('');
  const [openaiApiKeyOpen, setOpenaiApiKeyOpen] = useState(false);
  const [anthropicApiKeyOpen, setAnthropicApiKeyOpen] = useState(false);
  const [deepseekApiKeyOpen, setDeepseekApiKeyOpen] = useState(false);
  const [xaiApiKeyOpen, setXaiApiKeyOpen] = useState(false);
  const [localProviderOpen, setLocalProviderOpen] = useState<LocalProviderName | null>(null);
  const [pairedDevices, setPairedDevices] = useState<PairedDevice[]>([]);
  const [pairingInvitation, setPairingInvitation] = useState<PairingInvitation | null>(null);
  const [pairingBusy, setPairingBusy] = useState(false);
  const [pendingRevoke, setPendingRevoke] = useState<string | null>(null);
  const consoleAccess = data.console_access || {
    exposure: 'loopback' as const,
    public_url: window.location.origin,
    paired: false,
    can_manage_devices: false,
  };

  useEffect(() => {
    if (consoleAccess.exposure !== 'private' || !consoleAccess.can_manage_devices) {
      setPairedDevices([]);
      return;
    }
    let cancelled = false;
    void getPairedDevices()
      .then((rows) => {
        if (!cancelled) setPairedDevices(rows);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : t('设备列表读取失败'));
      });
    return () => {
      cancelled = true;
    };
  }, [consoleAccess.can_manage_devices, consoleAccess.exposure, t]);

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
        if (!cancelled) setError(err instanceof Error ? err.message : t('连接状态读取失败'));
      }
    };
    const timer = window.setInterval(() => void poll(), 1500);
    void poll();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [job?.job_id, job?.status, onChanged, t]);

  const startConnection = async (
    provider: AIProviderName,
    method: 'account' | 'api' | 'api_key' | 'local',
    apiKey?: string,
  ): Promise<string | null> => {
    setError('');
    try {
      setJob(await connectProvider(provider, method, apiKey));
      return null;
    } catch (err) {
      const message = err instanceof Error ? err.message : t('无法启动登录');
      setError(message);
      return message;
    }
  };

  const beginPairing = async () => {
    setPairingBusy(true);
    setError('');
    try {
      setPairingInvitation(await createPairingInvitation());
    } catch (err) {
      setError(err instanceof Error ? err.message : t('无法创建配对码'));
    } finally {
      setPairingBusy(false);
    }
  };

  const revokeDevice = async (deviceId: string) => {
    setPairingBusy(true);
    setError('');
    try {
      await revokePairedDevice(deviceId);
      setPairedDevices((rows) => rows.filter((row) => row.device_id !== deviceId));
      setPendingRevoke(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('无法撤销设备'));
    } finally {
      setPairingBusy(false);
    }
  };

  const providerRows = [
    data.providers.openai,
    data.providers.anthropic,
    data.providers.deepseek,
    data.providers.xai,
    data.providers.ollama,
    data.providers.lmstudio,
  ];
  const dailyRows = [
    ['mail', data.integrations.mail, Mail, onMailSetup],
    ['telegram', data.integrations.telegram, Send, onTelegramSetup],
  ] as const;
  return (
    <div className="connections-layout">
      <section className="panel full-panel language-settings-panel">
        <div className="section-heading compact">
          <div><span className="section-kicker">{t('常规')}</span><h2>{t('语言')}</h2></div>
        </div>
        <div className="language-setting-row">
          <div>
            <strong>{t('界面语言')}</strong>
            <span>{t('只保存在当前浏览器，不会修改任务、方案或账本。')}</span>
          </div>
          <div className="segmented-control language-selector" role="group" aria-label={t('界面语言')}>
            <button type="button" className={language === 'en' ? 'selected' : ''} aria-pressed={language === 'en'} onClick={() => setLanguage('en')}>English</button>
            <button type="button" className={language === 'zh' ? 'selected' : ''} aria-pressed={language === 'zh'} onClick={() => setLanguage('zh')}>中文</button>
          </div>
        </div>
      </section>
      <section className="panel full-panel">
        <div className="section-heading compact">
          <div><span className="section-kicker">ACCESS</span><h2>{t('设备访问')}</h2></div>
          <StatusBadge
            status={consoleAccess.exposure === 'private' ? 'online' : 'setup'}
            label={t(consoleAccess.exposure === 'private' ? '私网 HTTPS' : '仅此 Mac')}
          />
        </div>
        <div className="private-access-summary">
          <div className="connection-icon"><Smartphone size={19} /></div>
          <div>
            <strong>{t(consoleAccess.exposure === 'private' ? '已配对设备' : '本机访问')}</strong>
            <span>{consoleAccess.exposure === 'private' ? consoleAccess.public_url : t('私网访问尚未启用')}</span>
          </div>
          {consoleAccess.exposure === 'private' && consoleAccess.can_manage_devices && (
            <button className="secondary-button" type="button" disabled={pairingBusy} onClick={() => void beginPairing()}>
              {pairingBusy ? <LoaderCircle size={16} className="spin" /> : <Plus size={16} />}
              {t('添加设备')}
            </button>
          )}
        </div>
        {pairingInvitation && (
          <div className="pairing-invitation" role="status">
            <div><span>{t('一次性配对码')}</span><code>{pairingInvitation.code}</code><small>{t('有效至 {time}', { time: formatTime(pairingInvitation.expires_at, language) })}</small></div>
            <button
              className="icon-button"
              type="button"
              title={t('复制配对码')}
              onClick={() => void navigator.clipboard.writeText(pairingInvitation.code)}
            >
              <Copy size={17} />
            </button>
          </div>
        )}
        {consoleAccess.exposure === 'private' && consoleAccess.can_manage_devices && (
          <div className="paired-device-list">
            {pairedDevices.map((device) => (
              <div className="paired-device-row" key={device.device_id}>
                <div><strong>{device.name}</strong><span>{t('最近访问 {time}', { time: formatTime(device.last_seen_at, language) })}</span></div>
                {pendingRevoke === device.device_id ? (
                  <div className="inline-confirm-actions">
                    <button className="secondary-button danger-button" type="button" disabled={pairingBusy} onClick={() => void revokeDevice(device.device_id)}>{t('确认撤销')}</button>
                    <button className="icon-button" type="button" title={t('取消')} onClick={() => setPendingRevoke(null)}><X size={16} /></button>
                  </div>
                ) : (
                  <button className="icon-button" type="button" title={t('撤销设备 {name}', { name: device.name })} onClick={() => setPendingRevoke(device.device_id)}><Trash2 size={16} /></button>
                )}
              </div>
            ))}
            {pairedDevices.length === 0 && <div className="empty-device-row">{t('还没有已配对设备')}</div>}
          </div>
        )}
      </section>
      <section className="panel full-panel">
        <div className="section-heading compact">
          <div><span className="section-kicker">AI</span><h2>{t('模型连接')}</h2></div>
        </div>
        <div className="provider-list">
          {providerRows.map((provider: AIProvider) => {
            const connecting = job?.provider === provider.provider && job.status === 'running';
            const connected = provider.runtime_ready;
            const localProvider = isLocalProvider(provider.provider);
            return (
              <div className="provider-row" key={provider.provider}>
                <div className="provider-mark">
                  {localProvider
                    ? <Cpu size={21} />
                    : <Bot size={21} />}
                </div>
                <div className="provider-copy">
                  <strong>{provider.label}</strong>
                  <span>{translatedIntegrationDetail(provider.detail, t)}</span>
                  <small>{t(provider.privacy || '')}</small>
                </div>
                <StatusBadge
                  status={provider.status}
                  label={t(connected ? '可用' : provider.authenticated ? '已连接' : provider.provider === 'xai' ? '待连接' : provider.installed ? '待连接' : '未安装')}
                />
                <div className={`provider-actions ${localProvider ? 'single' : 'multiple'} ${provider.provider}`}>
                  {provider.provider === 'openai' ? (
                    <>
                      <button
                        className="secondary-button provider-button"
                        type="button"
                        disabled={!provider.installed || connecting}
                        onClick={() => void startConnection('openai', 'account')}
                      >
                        {connecting && job?.method === 'account' ? <LoaderCircle size={16} className="spin" /> : <ExternalLink size={16} />}
                        {connecting && job?.method === 'account' ? t('等待登录') : 'ChatGPT'}
                      </button>
                      <button
                        className="primary-button provider-button"
                        type="button"
                        disabled={!provider.installed || connecting}
                        onClick={() => setOpenaiApiKeyOpen(true)}
                      >
                        {connecting && job?.method === 'api' ? <LoaderCircle size={16} className="spin" /> : <ShieldCheck size={16} />}
                        {connecting && job?.method === 'api' ? t('正在验证') : 'API Key'}
                      </button>
                    </>
                  ) : provider.provider === 'anthropic' ? (
                    <>
                      <button
                        className="secondary-button provider-button"
                        type="button"
                        disabled={!provider.installed || connecting}
                        onClick={() => void startConnection('anthropic', 'account')}
                      >
                        {connecting && job?.method === 'account' ? <LoaderCircle size={16} className="spin" /> : <ExternalLink size={16} />}
                        {connecting && job?.method === 'account' ? t('等待登录') : t('Claude 账户')}
                      </button>
                      <button
                        className="secondary-button provider-button"
                        type="button"
                        disabled={!provider.installed || connecting}
                        onClick={() => void startConnection('anthropic', 'api')}
                      >
                        {connecting && job?.method === 'api' ? <LoaderCircle size={16} className="spin" /> : <ExternalLink size={16} />}
                        {connecting && job?.method === 'api' ? t('等待登录') : t('Console 登录')}
                      </button>
                      <button
                        className="primary-button provider-button"
                        type="button"
                        disabled={!provider.installed || connecting}
                        onClick={() => setAnthropicApiKeyOpen(true)}
                      >
                        {connecting && job?.method === 'api_key' ? <LoaderCircle size={16} className="spin" /> : <ShieldCheck size={16} />}
                        {connecting && job?.method === 'api_key' ? t('正在验证') : 'API Key'}
                      </button>
                    </>
                  ) : provider.provider === 'deepseek' ? (
                    <button
                      className="primary-button provider-button"
                      type="button"
                      disabled={connecting}
                      onClick={() => setDeepseekApiKeyOpen(true)}
                    >
                      {connecting ? <LoaderCircle size={16} className="spin" /> : <ShieldCheck size={16} />}
                      {connecting ? t('正在验证') : 'API Key'}
                    </button>
                  ) : provider.provider === 'xai' ? (
                    <>
                      <button
                        className="secondary-button provider-button"
                        type="button"
                        disabled={!provider.installed || connecting}
                        title={!provider.installed ? t('安装官方 Grok Build 后可连接账户') : undefined}
                        onClick={() => void startConnection('xai', 'account')}
                      >
                        {connecting && job?.method === 'account' ? <LoaderCircle size={16} className="spin" /> : <ExternalLink size={16} />}
                        {connecting && job?.method === 'account' ? t('等待登录') : t('Grok 账户')}
                      </button>
                      <button
                        className="primary-button provider-button"
                        type="button"
                        disabled={connecting}
                        onClick={() => setXaiApiKeyOpen(true)}
                      >
                        {connecting && job?.method === 'api_key' ? <LoaderCircle size={16} className="spin" /> : <ShieldCheck size={16} />}
                        {connecting && job?.method === 'api_key' ? t('正在验证') : 'API Key'}
                      </button>
                    </>
                  ) : (
                    <button
                      className="primary-button provider-button"
                      type="button"
                      disabled={!provider.installed || connecting}
                      onClick={() => {
                        if (isLocalProvider(provider.provider)) setLocalProviderOpen(provider.provider);
                      }}
                    >
                      {connecting ? <LoaderCircle size={16} className="spin" /> : <Cpu size={16} />}
                      {connecting ? t('正在连接') : t(connected ? '同步模型' : '连接本地模型')}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        {job?.status === 'running' && (
          <div className="provider-notice" role="status">
            <LoaderCircle size={17} className="spin" />
            {job.method === 'local'
              ? t('正在启动本地模型服务、读取模型列表并连接隐藏运行适配器。')
              : job.provider === 'openai' && job.method === 'api'
              ? t('正在验证 OpenAI API Key；密钥只会交给本机 Codex CLI。')
              : job.provider === 'anthropic' && job.method === 'api_key'
                ? t('正在验证 Anthropic API Key，并将其保存到本机 macOS Keychain。')
              : job.provider === 'deepseek'
                ? t('正在验证 DeepSeek API Key，并将其保存到本机 macOS Keychain。')
              : job.provider === 'xai' && job.method === 'api_key'
                ? t('正在验证 xAI API Key，并将其保存到本机 macOS Keychain。')
              : job.provider === 'xai'
                ? t('请在官方 xAI 页面完成 Grok 账户登录；OpsWitness 不会读取登录凭据。')
              : job.provider === 'anthropic' && job.method === 'api'
                ? t('请在已打开的 Anthropic Console 页面完成 API 登录。')
                : t('请在厂商打开的页面完成登录；OpsWitness 不会读取登录凭据。')}
          </div>
        )}
        {job?.status === 'failed' && <InlineError text={job.error || t('登录未完成')} />}
        {error && <InlineError text={error} />}
      </section>

      <section className="panel full-panel">
        <div className="section-heading compact">
          <div><span className="section-kicker">{t('日常工具')}</span><h2>{t('消息与数据')}</h2></div>
        </div>
        <div className="connection-list">
          {dailyRows.map(([key, item, Icon, action]) => (
            <div className="connection-row" key={key}>
              <div className="connection-icon"><Icon size={19} /></div>
              <div><strong>{t(item.label)}</strong><span>{translatedIntegrationDetail(item.detail || (item.status === 'online' ? '已连接' : '待配置'), t)}</span></div>
              <StatusBadge status={item.status} label={t(item.status === 'online' ? '已连接' : '待设置')} />
              <button className="icon-button compact-icon" type="button" title={t('管理{name}', { name: t(item.label) })} onClick={action}>
                <Settings size={16} />
              </button>
            </div>
          ))}
        </div>
      </section>

      <details className="diagnostics-panel">
        <summary><span><Server size={16} />{t('系统诊断')}</span><ChevronDown size={16} /></summary>
        <div className="diagnostics-list">
          {['aionui', 'paperclip', 'ledger'].map((key) => {
            const item = data.integrations[key];
            return item ? (
              <div key={key}><span className={`status-dot ${statusTone(item.status)}`} /><strong>{t(item.label)}</strong><small>{translatedIntegrationDetail(item.detail, t)}</small></div>
            ) : null;
          })}
        </div>
        <SystemAutomationHistory runs={data.recent_runs} />
      </details>
      <ProviderApiKeyDialog
        provider="openai"
        open={openaiApiKeyOpen}
        onClose={() => setOpenaiApiKeyOpen(false)}
        onSubmit={(apiKey) => startConnection('openai', 'api', apiKey)}
      />
      <ProviderApiKeyDialog
        provider="anthropic"
        open={anthropicApiKeyOpen}
        onClose={() => setAnthropicApiKeyOpen(false)}
        onSubmit={(apiKey) => startConnection('anthropic', 'api_key', apiKey)}
      />
      <ProviderApiKeyDialog
        provider="deepseek"
        open={deepseekApiKeyOpen}
        onClose={() => setDeepseekApiKeyOpen(false)}
        onSubmit={(apiKey) => startConnection('deepseek', 'api_key', apiKey)}
      />
      <ProviderApiKeyDialog
        provider="xai"
        open={xaiApiKeyOpen}
        onClose={() => setXaiApiKeyOpen(false)}
        onSubmit={(apiKey) => startConnection('xai', 'api_key', apiKey)}
      />
      <LocalProviderDialog
        provider={localProviderOpen}
        onClose={() => setLocalProviderOpen(null)}
        onSubmit={(provider) => startConnection(provider, 'local')}
      />
    </div>
  );
}

function LocalProviderDialog({
  provider,
  onClose,
  onSubmit,
}: {
  provider: LocalProviderName | null;
  onClose: () => void;
  onSubmit: (provider: LocalProviderName) => Promise<string | null>;
}) {
  const { t } = useLanguage();
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const metadata = provider ? {
    ollama: {
      name: 'Ollama',
      endpoint: 'http://127.0.0.1:11434/v1',
      start: '将打开本机 Ollama App；如果服务已经运行，只会刷新模型列表。',
    },
    lmstudio: {
      name: 'LM Studio',
      endpoint: 'http://127.0.0.1:1234/v1',
      start: '将通过本机 lms 启动 LM Studio API Server；如果服务已经运行，只会刷新模型列表。',
    },
  }[provider] : null;

  useEffect(() => {
    setConfirmed(false);
    setBusy(false);
    setError('');
  }, [provider]);

  if (!provider || !metadata) return null;

  const close = () => {
    if (busy) return;
    onClose();
  };

  const submit = async () => {
    if (!confirmed) {
      setError(t('请先确认启动本地服务并登记模型。'));
      return;
    }
    setBusy(true);
    setError('');
    try {
      const failure = await onSubmit(provider);
      if (failure) {
        setError(failure);
        return;
      }
      onClose();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-layer" role="dialog" aria-modal="true" aria-label={t('连接 {name}', { name: metadata.name })}>
      <button className="modal-backdrop" type="button" aria-label={t('关闭')} onClick={close} />
      <section className="mail-setup-dialog provider-api-dialog local-provider-dialog">
        <header className="modal-header">
          <div>
            <span className="section-kicker">LOCAL AI</span>
            <h2>{t('连接 {name}', { name: metadata.name })}</h2>
          </div>
          <button className="icon-button" type="button" title={t('关闭')} disabled={busy} onClick={close}>
            <X size={19} />
          </button>
        </header>
        <div className="mail-setup-content">
          <div className="privacy-summary">
            <strong>{t('只在这台 Mac 上运行')}</strong>
            <span>{t('模型请求只走固定的本机回环地址。OpsWitness 不接受自定义远程 URL，也不会生成或保存真实 API Key。')}</span>
          </div>
          <div className="local-provider-facts">
            <div><span>{t('服务')}</span><strong>{metadata.name}</strong></div>
            <div><span>{t('固定端点')}</span><code>{metadata.endpoint}</code></div>
            <p>{t(metadata.start)}</p>
            <p>{t('检测到的模型会用非秘密占位符登记到隐藏运行适配器；至少需要一个已下载或已加载模型。')}</p>
          </div>
          <label className="consent-row">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            <span>{t('我确认启动本地模型服务，并把检测到的模型登记到 OpsWitness 的本机运行适配器')}</span>
          </label>
          {error && <InlineError text={error} />}
          <button className="primary-button full-button" type="button" disabled={busy || !confirmed} onClick={() => void submit()}>
            {busy ? <LoaderCircle size={17} className="spin" /> : <Cpu size={17} />}
            {t(busy ? '正在连接' : '启动并连接')}
          </button>
        </div>
      </section>
    </div>
  );
}

function ProviderApiKeyDialog({
  provider,
  open,
  onClose,
  onSubmit,
}: {
  provider: CredentialProviderName;
  open: boolean;
  onClose: () => void;
  onSubmit: (apiKey: string) => Promise<string | null>;
}) {
  const { t } = useLanguage();
  const [apiKey, setApiKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const persistent = provider !== 'openai';
  const metadata = {
    openai: {
      kicker: 'OPENAI',
      label: 'OpenAI API Key',
      placeholder: 'sk-...',
      title: '连接 OpenAI API Key',
      invalid: '请输入有效的 OpenAI API Key。',
      description: 'Key 只会通过 stdin 交给官方 Codex CLI；OpsWitness 不保存、回显或写入证据。',
      consent: '',
    },
    anthropic: {
      kicker: 'ANTHROPIC',
      label: 'Anthropic API Key',
      placeholder: 'sk-ant-...',
      title: '连接 Anthropic API Key',
      invalid: '请输入有效的 Anthropic API Key。',
      description: 'Key 先由 Anthropic Models API 验证，再通过 stdin 保存到 macOS Keychain；Claude 只读取官方 apiKeyHelper，密钥不会回显、返回或写入配置、日志与账本。',
      consent: '我确认将 Key 保存到此 Mac 的 Keychain，并由我的 Anthropic API 账户承担用量费用',
    },
    deepseek: {
      kicker: 'DEEPSEEK',
      label: 'DeepSeek API Key',
      placeholder: 'sk-...',
      title: '连接 DeepSeek API Key',
      invalid: '请输入有效的 DeepSeek API Key。',
      description: 'Key 先由 DeepSeek Models API 验证，再通过 stdin 保存到 macOS Keychain；不会写入 AionUi、配置、日志或账本。',
      consent: '我确认将 Key 保存到此 Mac 的 Keychain，并由我的 DeepSeek API 账户承担用量费用',
    },
    xai: {
      kicker: 'XAI',
      label: 'xAI API Key',
      placeholder: 'xai-...',
      title: '连接 xAI API Key',
      invalid: '请输入有效的 xAI API Key。',
      description: 'Key 先由 xAI Models API 验证，再通过 stdin 保存到 macOS Keychain；不会写入 AionUi、配置、日志或账本。Grok 订阅与 xAI API 用量分别计费。',
      consent: '我确认将 Key 保存到此 Mac 的 Keychain，并由我的 xAI API 账户承担用量费用',
    },
  }[provider];

  useEffect(() => {
    if (open) return;
    setApiKey('');
    setBusy(false);
    setError('');
    setConfirmed(false);
  }, [open]);

  if (!open) return null;

  const close = () => {
    setApiKey('');
    setError('');
    setConfirmed(false);
    onClose();
  };

  const submit = async () => {
    if (apiKey.length < 8 || /\s/.test(apiKey)) {
      setError(t(metadata.invalid));
      return;
    }
    if (persistent && !confirmed) {
      setError(t('请确认本机 Keychain 保存与 API 计费。'));
      return;
    }
    setBusy(true);
    setError('');
    try {
      const failure = await onSubmit(apiKey);
      if (failure) {
        setError(failure);
        return;
      }
      close();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="modal-layer"
      role="dialog"
      aria-modal="true"
      aria-label={t(metadata.title)}
    >
      <button className="modal-backdrop" type="button" aria-label={t('关闭')} onClick={close} />
      <section className="mail-setup-dialog provider-api-dialog">
        <header className="modal-header">
          <div>
            <span className="section-kicker">{metadata.kicker}</span>
            <h2>{t('连接 API Key')}</h2>
          </div>
          <button className="icon-button" type="button" title={t('关闭')} onClick={close}>
            <X size={19} />
          </button>
        </header>
        <form
          className="mail-setup-content"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <div className="privacy-summary">
            <strong>{t(persistent ? '本机安全保存' : '仅用于本机登录')}</strong>
            <span>
              {t(metadata.description)}
            </span>
          </div>
          <label className="provider-api-key-field">
            <span>{metadata.label}</span>
            <input
              type="password"
              value={apiKey}
              minLength={8}
              maxLength={512}
              autoComplete="off"
              spellCheck={false}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder={metadata.placeholder}
            />
          </label>
          {persistent && (
            <label className="consent-row">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(event) => setConfirmed(event.target.checked)}
              />
              <span>{t(metadata.consent)}</span>
            </label>
          )}
          {error && <InlineError text={error} />}
          <button
            className="primary-button full-button"
            type="submit"
            disabled={busy || apiKey.length < 8 || (persistent && !confirmed)}
          >
            {busy ? <LoaderCircle size={17} className="spin" /> : <ShieldCheck size={17} />}
            {t('连接 API Key')}
          </button>
        </form>
      </section>
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
  const { t } = useLanguage();
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
      .catch((err) => setError(err instanceof Error ? err.message : t('邮箱状态读取失败')))
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
          setError(err instanceof Error ? err.message : t('授权状态读取失败'));
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
      setError(err instanceof Error ? err.message : t('授权请求失败'));
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
      if (clientFile.size > 65_536) throw new Error(t('OAuth client JSON 超过 64 KiB'));
      const clientJson = await clientFile.text();
      await configureMailOAuthClient(clientJson);
      await loadStatus();
      setClientFile(null);
      setClientStorageAck(false);
      setClientInputKey((value) => value + 1);
      setNotice(t('Desktop OAuth client 已安全导入；现在可以继续 Gmail 只读授权。'));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('OAuth client 导入失败'));
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
      setError(err instanceof Error ? err.message : t('停用失败'));
    } finally {
      setBusy(false);
    }
  };

  const ready = status?.ready === true;
  const clientReady = status?.oauth_client_ready === true;
  const running = job?.status === 'running';
  return (
    <div className="modal-layer" role="dialog" aria-modal="true" aria-label={t('邮箱授权')}>
      <button className="modal-backdrop" type="button" aria-label={t('关闭')} onClick={onClose} />
      <section className="mail-setup-dialog">
        <header className="modal-header">
          <div>
            <span className="section-kicker">GMAIL</span>
            <h2>{t(ready ? '邮箱摘要已连接' : '设置邮箱摘要')}</h2>
          </div>
          <button className="icon-button" type="button" title={t('关闭')} onClick={onClose}>
            <X size={19} />
          </button>
        </header>

        {ready ? (
          <div className="mail-setup-content">
            <div className="setup-success">
              <ShieldCheck size={24} />
              <div>
                <strong>{t('Gmail 只读授权有效')}</strong>
                <span>{t('首页现在可以按需生成元数据摘要。')}</span>
              </div>
            </div>
            <div className="privacy-summary">
              <strong>{t('固定数据边界')}</strong>
              <span>{t('仅发件人、主题、日期和 message-id；不读取正文。')}</span>
              <span>{t('没有发送、草稿、删除或标签权限。')}</span>
            </div>
            <label className="consent-row">
              <input
                type="checkbox"
                checked={revokeAck}
                onChange={(event) => setRevokeAck(event.target.checked)}
              />
              <span>{t('确认停用后续邮箱读取与模型元数据传输')}</span>
            </label>
            <button
              className="secondary-button danger-button"
              type="button"
              disabled={!revokeAck || busy}
              onClick={() => void revoke()}
            >
              {t('停用邮箱摘要')}
            </button>
          </div>
        ) : (
          <div className="mail-setup-content">
            <div className="privacy-summary">
              <strong>{t('最小权限')}</strong>
              <span>{t('授权页只申请 Gmail readonly；token 由 gws 加密保存，OpsWitness 不读取或回显。')}</span>
              <span>{t('固定查询仅查看最近未读收件箱，排除垃圾邮件和回收站。')}</span>
            </div>
            {status && !status.available && (
              <div className="inline-error">{t('本机固定版本 gws 尚未就绪，请先运行 doctor。')}</div>
            )}
            {status?.available && !clientReady ? (
              <div className="setup-step">
                <div className="setup-step-heading">
                  <span>1</span>
                  <div>
                    <strong>{t('导入 Google Desktop OAuth client')}</strong>
                    <small>{t('首次设置一次；请选择 Google Cloud 下载的 client_secret JSON。')}</small>
                  </div>
                </div>
                <a
                  className="secondary-button link-button full-button"
                  href="https://console.cloud.google.com/apis/credentials"
                  target="_blank"
                  rel="noreferrer"
                >
                  <ExternalLink size={16} />
                  {t('打开 Google Cloud 凭据页')}
                </a>
                <label className="client-file-field">
                  <FileUp size={17} />
                  <span>{clientFile?.name || t('选择 Desktop client JSON')}</span>
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
                  <span>{t('确认将该 Desktop client 配置以 0600 权限保存到本机 gws 私有目录')}</span>
                </label>
                <button
                  className="primary-button full-button"
                  type="button"
                  disabled={!clientFile || !clientStorageAck || busy}
                  onClick={() => void importOAuthClient()}
                >
                  {busy ? <LoaderCircle size={17} className="spin" /> : <FileUp size={17} />}
                  {t('安全导入并继续')}
                </button>
              </div>
            ) : status?.available ? (
              <div className="setup-step">
                <div className="setup-step-heading">
                  <span>2</span>
                  <div>
                    <strong>{t('授权与摘要同意')}</strong>
                    <small>{t('Google 授权和 AI 摘要元数据传输分别确认。')}</small>
                  </div>
                </div>
                <label className="consent-row">
                  <input
                    type="checkbox"
                    checked={readonlyAck}
                    onChange={(event) => setReadonlyAck(event.target.checked)}
                  />
                  <span>{t('我同意打开 Google 授权页并仅授予 Gmail 只读权限')}</span>
                </label>
                <label className="consent-row">
                  <input
                    type="checkbox"
                    checked={metadataAck}
                    onChange={(event) => setMetadataAck(event.target.checked)}
                  />
                  <span>{t('我同意将发件人、主题、日期和 message-id 发送给当前 AI 模型生成摘要')}</span>
                </label>
                {running && (
                  <div className="oauth-progress" role="status">
                    <LoaderCircle size={20} className="spin" />
                    <span>{t('请在已打开的 Google 页面完成授权')}</span>
                  </div>
                )}
                <button
                  className="primary-button full-button"
                  type="button"
                  disabled={busy || running || !readonlyAck || !metadataAck}
                  onClick={() => void startAuthorization()}
                >
                  {busy ? <LoaderCircle size={17} className="spin" /> : <ShieldCheck size={17} />}
                  {t(status?.authenticated ? '确认并启用摘要' : '打开 Google 只读授权')}
                </button>
              </div>
            ) : null}
            {status?.oauth_client_issue === 'unsafe_permissions' && (
              <div className="inline-error">{t('现有 OAuth client 文件权限不安全，请重新导入修复。')}</div>
            )}
            {status?.oauth_client_issue === 'invalid' && (
              <div className="inline-error">{t('现有 OAuth client 不是有效的 Desktop 配置，请重新导入。')}</div>
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
  const { t } = useLanguage();
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
      .catch((err) => setError(err instanceof Error ? err.message : t('Telegram 状态读取失败')))
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
      setNotice(t('凭据已保存；发送测试消息后才算交付链路验收完成。'));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('Telegram 配置失败'));
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
      setNotice(t('固定测试消息已发送。'));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('Telegram 测试失败'));
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
      setNotice(t('本机 Telegram 凭据已移除。'));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('Telegram 停用失败'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-layer" role="dialog" aria-modal="true" aria-label={t('Telegram 设置')}>
      <button className="modal-backdrop" type="button" aria-label={t('关闭')} onClick={closeDialog} />
      <section className="mail-setup-dialog">
        <header className="modal-header">
          <div>
            <span className="section-kicker">TELEGRAM</span>
            <h2>{t(status?.configured ? 'Telegram 已配置' : '设置 Telegram')}</h2>
          </div>
          <button className="icon-button" type="button" title={t('关闭')} onClick={closeDialog}>
            <X size={19} />
          </button>
        </header>

        <div className="mail-setup-content">
          <div className="privacy-summary">
            <strong>{t('本机秘密边界')}</strong>
            <span>{t('Bot token 与 chat ID 只写入本机 0600 secrets.yaml，不进入账本或页面回显。')}</span>
            <span>{t('测试按钮只发送固定的 OpsWitness 探针文本。')}</span>
          </div>

          {status?.environment_controlled ? (
            <div className="inline-error">{t('凭据由外部环境管理，控制台不能覆盖或删除。')}</div>
          ) : status?.configured && !editing ? (
            <>
              <div className="setup-success">
                <Send size={22} />
                <div>
                  <strong>{t('本机凭据已配置')}</strong>
                  <span>{t('不会显示 token 或 chat ID。')}</span>
                </div>
              </div>
              <label className="consent-row">
                <input
                  type="checkbox"
                  checked={testAck}
                  onChange={(event) => setTestAck(event.target.checked)}
                />
                <span>{t('确认向已配置的目标发送一条固定测试消息')}</span>
              </label>
              <button
                className="primary-button full-button"
                type="button"
                disabled={!testAck || busy}
                onClick={() => void sendTest()}
              >
                <Send size={17} />{t('发送测试消息')}
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
                {t('更换凭据')}
              </button>
              <label className="consent-row">
                <input
                  type="checkbox"
                  checked={disableAck}
                  onChange={(event) => setDisableAck(event.target.checked)}
                />
                <span>{t('确认从本机移除 Telegram 凭据并停止后续推送')}</span>
              </label>
              <button
                className="secondary-button danger-button"
                type="button"
                disabled={!disableAck || busy}
                onClick={() => void disable()}
              >
                {t('停用 Telegram')}
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
                <span>{t('确认将这两项凭据保存到本机私有 secrets.yaml')}</span>
              </label>
              <button
                className="primary-button full-button"
                type="button"
                disabled={!botToken || !chatId || !storageAck || busy}
                onClick={() => void configure()}
              >
                {busy ? <LoaderCircle size={17} className="spin" /> : <ShieldCheck size={17} />}
                {t(status?.configured ? '替换本机凭据' : '保存本机凭据')}
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
                  {t('取消更换')}
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
  plans,
  onClose,
  onPlan,
  onRevise,
  onOrganizationSave,
  runtimeCapabilities,
  onRuntimeSave,
  onProfileSave,
  onConfirm,
  onAnswerInput,
  onControl,
  approvals,
  approvalsAvailable,
  onDecideApproval,
  onDelete,
  onRestart,
}: {
  open: boolean;
  record: PlanRecord | null;
  previousPlan: TaskPlan | null;
  plans: PlanRecord[];
  onClose: () => void;
  onPlan: (body: { objective: string; constraints: string; workspace: string; preferred_cadence: string }) => Promise<void>;
  onRevise: (record: PlanRecord, instruction: string) => Promise<void>;
  onOrganizationSave: (
    record: PlanRecord,
    lines: ReportingLine[],
    loops: CollaborationLoop[],
  ) => Promise<void>;
  runtimeCapabilities: RuntimeCapability[];
  onRuntimeSave: (
    record: PlanRecord,
    assignments: AgentRuntimeAssignment[],
  ) => Promise<void>;
  onProfileSave: (
    record: PlanRecord,
    profile: Exclude<ExecutionProfile, 'custom'>,
  ) => Promise<void>;
  onConfirm: (record: PlanRecord, approvalMode: ApprovalMode) => Promise<void>;
  onAnswerInput: (record: PlanRecord, requestId: string, answer: string) => Promise<void>;
  onControl: (record: PlanRecord, action: 'pause' | 'resume' | 'terminate') => Promise<void>;
  approvals: ApprovalCard[];
  approvalsAvailable: boolean;
  onDecideApproval: (
    record: PlanRecord,
    approval: ApprovalCard,
    decision: 'approve' | 'reject',
    decisionNote: string,
  ) => Promise<void>;
  onDelete: (record: PlanRecord) => void;
  onRestart: () => void;
}) {
  const { t } = useLanguage();
  const [objective, setObjective] = useState('');
  const [constraints, setConstraints] = useState('');
  const [workspace, setWorkspace] = useState('');
  const [cadence, setCadence] = useState('once');
  const [submitting, setSubmitting] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [approvalMode, setApprovalMode] = useState<ApprovalMode>('automatic');
  const [revisionOpen, setRevisionOpen] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    setConfirmed(false);
    setApprovalMode(record?.approval_mode === 'manual_all' ? 'manual_all' : 'automatic');
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
  const deleteBlocked = record ? planDeleteBlockReason(record, plans) : '';
  const submit = async () => {
    setSubmitting(true);
    setError('');
    try {
      await onPlan({ objective, constraints, workspace, preferred_cadence: cadence });
    } catch (err) {
      setError(err instanceof Error ? err.message : t('规划请求失败'));
    } finally {
      setSubmitting(false);
    }
  };
  const confirm = async () => {
    if (!record) return;
    setSubmitting(true);
    setError('');
    try {
      await onConfirm(record, approvalMode);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('确认失败'));
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
      setError(err instanceof Error ? err.message : t('方案修改失败'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="drawer-layer" role="dialog" aria-modal="true" aria-label={t('新建任务')}>
      <button className="drawer-backdrop" type="button" aria-label={t('关闭')} onClick={onClose} />
      <aside className="task-drawer">
        <div className="drawer-header">
          <div><span className="section-kicker">NEW TASK</span><h2>{record?.plan?.title || t('创建任务')}</h2></div>
          <div className="drawer-header-actions">
            {record && (
              <button
                className="icon-button delete-icon-button"
                type="button"
                title={deleteBlocked ? t(deleteBlocked) : t('删除任务')}
                aria-label={t('删除任务')}
                disabled={Boolean(deleteBlocked)}
                onClick={() => onDelete(record)}
              >
                <Trash2 size={17} />
              </button>
            )}
            <button className="icon-button" type="button" title={t('关闭')} onClick={onClose}><X size={19} /></button>
          </div>
        </div>
        <StepTrack phase={phase} />
        <div className="drawer-body">
          {!record && (
            <div className="task-form">
              <label>
                <span>{t('目标')}</span>
                <textarea value={objective} onChange={(event) => setObjective(event.target.value)} maxLength={2000} rows={5} placeholder={t('例如：每天早上汇总未读邮件，并标出需要回复的事项')} />
              </label>
              <label>
                <span>{t('约束')}</span>
                <textarea value={constraints} onChange={(event) => setConstraints(event.target.value)} maxLength={2000} rows={3} placeholder={t('数据范围、交付格式、审批要求')} />
              </label>
              <label>
                <span>{t('更新节奏')}</span>
                <div className="segmented-control">
                  {cadenceOptions.map((option) => (
                    <button key={option.value} type="button" className={cadence === option.value ? 'selected' : ''} onClick={() => setCadence(option.value)}>{t(option.label)}</button>
                  ))}
                </div>
              </label>
              <label>
                <span>{t('工作目录')}</span>
                <div className="input-with-icon"><FolderOpen size={17} /><input value={workspace} onChange={(event) => setWorkspace(event.target.value)} placeholder={t('可选：绝对路径')} /></div>
              </label>
              {error && <InlineError text={error} />}
              <div className="drawer-actions">
                <button className="primary-button wide" type="button" disabled={objective.trim().length < 3 || submitting} onClick={() => void submit()}>
                  {submitting ? <LoaderCircle size={17} className="spin" /> : <Sparkles size={17} />}
                  {t('生成方案')}
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
              onOrganizationSave={(lines, loops) => onOrganizationSave(record, lines, loops)}
              runtimeCapabilities={runtimeCapabilities}
              onRuntimeSave={(assignments) => onRuntimeSave(record, assignments)}
              onProfileSave={(profile) => onProfileSave(record, profile)}
            />
          )}

          {record && ['confirmed', 'dispatching', 'running', 'pause_requested', 'paused', 'resuming', 'cancel_requested', 'cancelled', 'awaiting_approval', 'awaiting_input', 'completed_unverified', 'failed'].includes(record.status) && (
            <ExecutionView
              record={record}
              approvals={approvals}
              approvalsAvailable={approvalsAvailable}
              onDecideApproval={(approval, decision, decisionNote) => (
                onDecideApproval(record, approval, decision, decisionNote)
              )}
              onAnswerInput={(requestId, answer) => onAnswerInput(record, requestId, answer)}
              onControl={(action) => onControl(record, action)}
            />
          )}
        </div>

        {record?.status === 'ready' && (
          <div className="confirm-footer">
            {error && <InlineError text={error} />}
            {revisionOpen ? (
              <TaskAdjustmentChat
                submitting={submitting}
                onCancel={() => setRevisionOpen(false)}
                onSubmit={revise}
              />
            ) : (
              <>
                <ApprovalModeControl mode={approvalMode} onChange={setApprovalMode} />
                <label className="confirm-check">
                  <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
                  <span><Check size={15} />{t('确认此方案并启动受管执行')}</span>
                </label>
                <div className="confirm-actions revision-actions">
                  <button className="secondary-button" type="button" onClick={() => setRevisionOpen(true)}>
                    <MessageSquare size={16} />{t('用 AI 调整')}
                  </button>
                  <button className="text-button" type="button" onClick={onRestart}>
                    <RotateCcw size={15} />{t('重新开始')}
                  </button>
                  <button className="primary-button" type="button" disabled={!confirmed || submitting} onClick={() => void confirm()}>
                    {submitting ? <LoaderCircle size={17} className="spin" /> : <Play size={17} />}
                    {t('确认并运行')}
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

function DeletePlanDialog({
  record,
  onClose,
  onConfirm,
}: {
  record: PlanRecord | null;
  onClose: () => void;
  onConfirm: (record: PlanRecord) => Promise<void>;
}) {
  const { t } = useLanguage();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  if (!record) return null;
  const title = record.plan?.title || record.objective;
  const submit = async () => {
    setBusy(true);
    setError('');
    try {
      await onConfirm(record);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('任务删除失败'));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="modal-layer" role="dialog" aria-modal="true" aria-label={t('确认删除任务')}>
      <button className="modal-backdrop" type="button" aria-label={t('关闭')} onClick={() => !busy && onClose()} />
      <section className="mail-setup-dialog delete-plan-dialog">
        <header className="modal-header">
          <div><span className="section-kicker">{t('删除任务')}</span><h2>{t('从任务列表移除？')}</h2></div>
          <button className="icon-button" type="button" title={t('关闭')} disabled={busy} onClick={onClose}><X size={19} /></button>
        </header>
        <div className="mail-setup-content">
          <div className="delete-plan-summary">
            <Trash2 size={20} />
            <div><strong>{title}</strong><span>{shortId(record.plan_id)}</span></div>
          </div>
          <p className="delete-plan-copy">
            {t('任务会从工作台和任务列表中移除。原始规划与审计证据仍会保留，不会被物理删除。')}
          </p>
          {error && <InlineError text={error} />}
          <div className="delete-plan-actions">
            <button className="secondary-button" type="button" disabled={busy} onClick={onClose}>{t('取消')}</button>
            <button className="secondary-button danger-button" type="button" disabled={busy} onClick={() => void submit()}>
              {busy ? <LoaderCircle size={16} className="spin" /> : <Trash2 size={16} />}
              {t('删除任务')}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

function TaskAdjustmentChat({
  submitting,
  onCancel,
  onSubmit,
  className = '',
}: {
  submitting: boolean;
  onCancel?: () => void;
  onSubmit: (instruction: string) => Promise<void>;
  className?: string;
}) {
  const { language, t } = useLanguage();
  const [instruction, setInstruction] = useState('');
  const ready = instruction.trim().length >= 3 && !submitting;
  return (
    <section className={`task-adjustment-chat ${className}`} aria-label={t('用 AI 调整任务')}>
      <div className="task-adjustment-chat-heading">
        <Bot size={18} />
        <div>
          <strong>{t('直接对话调整这个 Work')}</strong>
          <span>{t('可修改目标、步骤、Agent、层级、循环、节奏、产出和检查点')}</span>
        </div>
      </div>
      <div className="task-adjustment-suggestions" role="group" aria-label={t('常用任务调整')}>
        {taskAdjustmentExamples(language).map((example) => (
          <button
            key={example.label}
            className="task-adjustment-suggestion"
            type="button"
            disabled={submitting}
            onClick={() => setInstruction(example.instruction)}
          >
            {example.label}
          </button>
        ))}
      </div>
      <textarea
        aria-label={t('任务调整要求')}
        value={instruction}
        onChange={(event) => setInstruction(event.target.value)}
        maxLength={2000}
        rows={3}
        placeholder={t('例如：把报告目标改为每周经营复盘，增加一名数据核验 Agent 向负责人汇报，并在数据不完整时返回重做，最多两轮。')}
      />
      <div className="task-adjustment-chat-footer">
        <span><ShieldCheck size={14} />{t('新方案待确认后运行')}</span>
        <div>
          {onCancel && <button className="text-button" type="button" disabled={submitting} onClick={onCancel}>{t('取消')}</button>}
          <button className="primary-button" type="button" disabled={!ready} onClick={() => void onSubmit(instruction.trim())}>
            {submitting ? <LoaderCircle size={16} className="spin" /> : <Sparkles size={16} />}
            {t('生成修改版本')}
          </button>
        </div>
      </div>
    </section>
  );
}

function StepTrack({ phase }: { phase: number }) {
  const { t } = useLanguage();
  return (
    <div className="step-track">
      {['需求', '方案', '运行'].map((label, index) => {
        const step = index + 1;
        return (
          <div key={label} className={step <= phase ? 'step active' : 'step'}>
            <span>{step < phase ? <Check size={13} /> : step}</span>
            <small>{t(label)}</small>
          </div>
        );
      })}
    </div>
  );
}

function PlanningProgressView({ progress }: { progress: PlanRecord['planning_progress'] }) {
  const { t } = useLanguage();
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
    t('准备安全规划环境'),
    t('AI 补全任务摘要与 Agent 方案'),
    t(phase === 'repairing' ? '修正并重新校验方案' : '严格校验方案契约'),
    t('清理临时规划会话'),
  ];
  const phaseLabel = t({
    queued: '规划任务已进入队列',
    preparing: '正在准备安全规划环境',
    generating_plan: '正在补全任务摘要与 Agent 方案',
    validating: '正在校验 Agent、检查点与交付物',
    repairing: '方案未通过首轮校验，正在自动修正',
    cleaning_up: '方案已生成，正在清理临时会话',
    complete: '规划完成',
    failed: '规划未完成',
  }[phase]);
  const expectedRange = expected < 60
    ? t('{min}–{max} 秒', { min: Math.max(10, expected - 15), max: expected + 15 })
    : t('{min}–{max} 分钟', {
      min: Math.max(1, Math.floor(expected / 60)),
      max: Math.max(Math.max(1, Math.floor(expected / 60)) + 1, Math.ceil(expected / 60)),
    });
  const timeoutLabel = timeout < 60
    ? t('{value} 秒', { value: timeout })
    : t('{value} 分钟', { value: Math.ceil(timeout / 60) });
  const timing = elapsed < expected
    ? t('已等待 {elapsed} 秒 · 通常总耗时约 {range}', { elapsed, range: expectedRange })
    : t('已等待 {elapsed} 秒 · 已超过通常耗时，仍在处理（最久约 {timeout}）', { elapsed, timeout: timeoutLabel });

  return (
    <div className="planning-state">
      <div className="planning-orbit">
        <LoaderCircle size={34} className="spin" />
        <Sparkles size={17} />
      </div>
      <strong>{t('AI 正在规划')}</strong>
      <span>{phaseLabel}</span>
      <div
        className="planning-progress-track"
        role="progressbar"
        aria-label={t('规划进度')}
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

function effectiveReportingLines(plan: TaskPlan): ReportingLine[] {
  const lead = plan.agents.find((agent) => agent.role === 'lead');
  const hasExplicitHierarchy = plan.agents.some((agent) => Boolean(agent.reports_to));
  return plan.agents.map((agent) => ({
    employee: agent.name,
    reports_to: hasExplicitHierarchy
      ? agent.reports_to || null
      : agent.name === lead?.name ? null : lead?.name || null,
  }));
}

function organizationLevels(agents: PlannedAgent[], lines: ReportingLine[]): PlannedAgent[][] {
  const parents = new Map(lines.map((line) => [line.employee, line.reports_to]));
  const grouped = new Map<number, PlannedAgent[]>();
  for (const agent of agents) {
    let depth = 0;
    let cursor = parents.get(agent.name) || null;
    const seen = new Set([agent.name]);
    while (cursor && !seen.has(cursor) && depth < agents.length) {
      seen.add(cursor);
      depth += 1;
      cursor = parents.get(cursor) || null;
    }
    grouped.set(depth, [...(grouped.get(depth) || []), agent]);
  }
  return [...grouped.entries()]
    .sort(([left], [right]) => left - right)
    .map(([, rows]) => rows);
}

function managerWouldCreateCycle(
  employee: string,
  manager: string,
  lines: ReportingLine[],
): boolean {
  const parents = new Map(lines.map((line) => [line.employee, line.reports_to]));
  let cursor: string | null = manager;
  while (cursor) {
    if (cursor === employee) return true;
    cursor = parents.get(cursor) || null;
  }
  return false;
}

function collaborationLoopError(
  agents: PlannedAgent[],
  loops: CollaborationLoop[],
): string {
  const agentNames = new Set(agents.map((agent) => agent.name));
  const pairs = new Set<string>();
  for (const loop of loops) {
    if (!agentNames.has(loop.source_agent) || !agentNames.has(loop.target_agent)) {
      return '循环协作必须选择当前团队中的员工';
    }
    if (loop.condition.trim().length < 3) return '请写明循环返回与停止条件';
    if (!Number.isInteger(loop.max_iterations)
      || loop.max_iterations < 1
      || loop.max_iterations > 10) {
      return '循环次数必须是 1 到 10 的整数';
    }
    const pair = `${loop.source_agent}\u0000${loop.target_agent}`;
    if (pairs.has(pair)) return '同一方向的员工组合只能设置一个循环';
    pairs.add(pair);
  }
  return '';
}

function OrganizationChart({
  plan,
  editable,
  onSave,
  compact = false,
}: {
  plan: TaskPlan;
  editable: boolean;
  onSave?: (lines: ReportingLine[], loops: CollaborationLoop[]) => Promise<void>;
  compact?: boolean;
}) {
  const { t } = useLanguage();
  const organizationKey = JSON.stringify({
    agents: plan.agents,
    loops: plan.collaboration_loops || [],
  });
  const initialLines = useMemo(
    () => effectiveReportingLines(plan),
    // The dashboard refresh replaces equal plan objects; only structural changes reset editing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [organizationKey],
  );
  const initialLoops = useMemo(
    () => (plan.collaboration_loops || []).map((loop) => ({ ...loop })),
    // The plan hash owns this structure; only a new plan version resets the editor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [organizationKey],
  );
  const [editing, setEditing] = useState(false);
  const [draftLines, setDraftLines] = useState<ReportingLine[]>(initialLines);
  const [draftLoops, setDraftLoops] = useState<CollaborationLoop[]>(initialLoops);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    setEditing(false);
    setDraftLines(initialLines);
    setDraftLoops(initialLoops);
    setError('');
  }, [organizationKey]);
  const visibleLines = editing ? draftLines : initialLines;
  const levels = useMemo(
    () => organizationLevels(plan.agents, visibleLines),
    [plan.agents, visibleLines],
  );
  const parentByEmployee = new Map(
    visibleLines.map((line) => [line.employee, line.reports_to]),
  );
  const changed = JSON.stringify({ lines: draftLines, loops: draftLoops })
    !== JSON.stringify({ lines: initialLines, loops: initialLoops });
  const rawLoopError = collaborationLoopError(plan.agents, draftLoops);
  const loopError = rawLoopError ? t(rawLoopError) : '';

  const changeManager = (employee: string, reportsTo: string) => {
    setDraftLines((current) => current.map((line) => (
      line.employee === employee ? { ...line, reports_to: reportsTo } : line
    )));
    setError('');
  };
  const changeLoop = (index: number, patch: Partial<CollaborationLoop>) => {
    setDraftLoops((current) => current.map((loop, loopIndex) => (
      loopIndex === index ? { ...loop, ...patch } : loop
    )));
    setError('');
  };
  const addLoop = () => {
    if (draftLoops.length >= 5) return;
    const preferred = plan.agents.length > 1
      ? [plan.agents[1], plan.agents[0], ...plan.agents.slice(2)]
      : plan.agents;
    for (const source of preferred) {
      for (const target of plan.agents) {
        if (!draftLoops.some(
          (loop) => loop.source_agent === source.name && loop.target_agent === target.name,
        )) {
          setDraftLoops((current) => [...current, {
            source_agent: source.name,
            target_agent: target.name,
            condition: t('验收未通过时返回修改；通过即停止'),
            max_iterations: 2,
          }]);
          setError('');
          return;
        }
      }
    }
    setError(t('没有可添加的唯一循环组合'));
  };
  const save = async () => {
    if (!onSave || !changed || saving) return;
    if (loopError) {
      setError(loopError);
      return;
    }
    setSaving(true);
    setError('');
    try {
      await onSave(
        draftLines,
        draftLoops.map((loop) => ({ ...loop, condition: loop.condition.trim() })),
      );
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('组织架构保存失败'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={`organization-chart ${compact ? 'compact' : ''}`}>
      <div className="organization-toolbar">
        <span>
          <Network size={15} />
          {t('{agents} 名员工 · {levels} 层汇报关系 · {loops} 个循环', { agents: plan.agents.length, levels: levels.length, loops: draftLoops.length })}
        </span>
        {editable && (
          editing ? (
            <div className="organization-actions">
              <button
                className="text-button"
                type="button"
                disabled={saving}
                onClick={() => {
                  setDraftLines(initialLines);
                  setDraftLoops(initialLoops);
                  setEditing(false);
                  setError('');
                }}
              >
                {t('取消')}
              </button>
              <button
                className="secondary-button"
                type="button"
                disabled={!changed || Boolean(loopError) || saving}
                onClick={() => void save()}
              >
                {saving ? <LoaderCircle size={15} className="spin" /> : <Save size={15} />}
                {t('保存为新版本')}
              </button>
            </div>
          ) : (
            <button
              className="text-button"
              type="button"
              title={t('需要精确指定汇报关系或循环次数时使用')}
              aria-label={t('高级手动编辑组织与循环')}
              onClick={() => setEditing(true)}
            >
              <PencilLine size={14} />{t('高级手动编辑')}
            </button>
          )
        )}
      </div>

      <div className="organization-levels">
        {levels.map((agents, levelIndex) => (
          <div className="organization-level" key={`level-${levelIndex}`}>
            <div className="organization-level-label">
              <span>{levelIndex === 0 ? t('负责人') : t('第 {level} 层', { level: levelIndex + 1 })}</span>
              <small>{t('{count} 人', { count: agents.length })}</small>
            </div>
            <div className="organization-nodes">
              {agents.map((agent) => {
                const manager = parentByEmployee.get(agent.name) || null;
                const managerOptions = plan.agents.filter(
                  (candidate) => candidate.name !== agent.name
                    && !managerWouldCreateCycle(agent.name, candidate.name, visibleLines),
                );
                return (
                  <article className={`organization-node role-${agent.role}`} key={agent.name}>
                    <div className="agent-node-top">
                      <Bot size={18} />
                      <span>{t(roleLabel[agent.role])}</span>
                    </div>
                    <strong>{agent.name}</strong>
                    <small>{t(runtimeLabel[agent.runtime])}{agent.model ? ` · ${agent.model}` : ''}</small>
                    <p>{agent.responsibility}</p>
                    {agent.role === 'lead' ? (
                      <div className="organization-manager root-manager">
                        <ShieldCheck size={14} /><span>{t('最高负责人')}</span>
                      </div>
                    ) : editing ? (
                      <label className="organization-manager-select">
                        <span>{t('直属上级')}</span>
                        <select
                          value={manager || ''}
                          onChange={(event) => changeManager(agent.name, event.target.value)}
                        >
                          {managerOptions.map((candidate) => (
                            <option key={candidate.name} value={candidate.name}>{candidate.name}</option>
                          ))}
                        </select>
                      </label>
                    ) : (
                      <div className="organization-manager">
                        <span>{t('直属上级')}</span><strong>{manager || '—'}</strong>
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="collaboration-loops">
        <div className="collaboration-loop-heading">
          <span><Repeat2 size={15} />{t('循环协作')}</span>
          {editing && (
            <button
              className="text-button"
              type="button"
              disabled={draftLoops.length >= 5}
              onClick={addLoop}
            >
              <Plus size={14} />{t('添加循环')}
            </button>
          )}
        </div>
        {draftLoops.length ? (
          <div className="collaboration-loop-list">
            {draftLoops.map((loop, index) => (
              <div
                className={`collaboration-loop-row ${editing ? 'editing' : ''}`}
                key={`${loop.source_agent}-${loop.target_agent}-${index}`}
              >
                {editing ? (
                  <>
                    <label>
                      <span>{t('发起员工')}</span>
                      <select
                        aria-label={t('循环 {index} 发起员工', { index: index + 1 })}
                        value={loop.source_agent}
                        onChange={(event) => changeLoop(index, { source_agent: event.target.value })}
                      >
                        {plan.agents.map((agent) => (
                          <option key={agent.name} value={agent.name}>{agent.name}</option>
                        ))}
                      </select>
                    </label>
                    <ArrowRight className="collaboration-loop-arrow" size={16} />
                    <label>
                      <span>{t('返回员工')}</span>
                      <select
                        aria-label={t('循环 {index} 返回员工', { index: index + 1 })}
                        value={loop.target_agent}
                        onChange={(event) => changeLoop(index, { target_agent: event.target.value })}
                      >
                        {plan.agents.map((agent) => (
                          <option key={agent.name} value={agent.name}>{agent.name}</option>
                        ))}
                      </select>
                    </label>
                    <label className="collaboration-loop-count">
                      <span>{t('最多轮次')}</span>
                      <input
                        aria-label={t('循环 {index} 最多轮次', { index: index + 1 })}
                        type="number"
                        min={1}
                        max={10}
                        step={1}
                        value={loop.max_iterations}
                        onChange={(event) => changeLoop(index, {
                          max_iterations: Number(event.target.value),
                        })}
                      />
                    </label>
                    <button
                      className="icon-button collaboration-loop-delete"
                      type="button"
                      title={t('删除循环')}
                      aria-label={t('删除循环 {index}', { index: index + 1 })}
                      onClick={() => setDraftLoops((current) => current.filter(
                        (_, loopIndex) => loopIndex !== index,
                      ))}
                    >
                      <Trash2 size={15} />
                    </button>
                    <label className="collaboration-loop-condition">
                      <span>{t('返回与停止条件')}</span>
                      <input
                        aria-label={t('循环 {index} 返回与停止条件', { index: index + 1 })}
                        value={loop.condition}
                        maxLength={300}
                        onChange={(event) => changeLoop(index, { condition: event.target.value })}
                      />
                    </label>
                  </>
                ) : (
                  <>
                    <div className="collaboration-loop-route">
                      <strong>{loop.source_agent}</strong>
                      <ArrowRight size={15} />
                      <strong>{loop.target_agent}</strong>
                      <span>{t('最多 {count} 轮', { count: loop.max_iterations })}</span>
                    </div>
                    <p>{loop.condition}</p>
                  </>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="collaboration-loop-empty">{t('无循环协作；各阶段按顺序执行一次。')}</div>
        )}
        <div className="collaboration-loop-boundary">
          <ShieldCheck size={14} />
          <span>{t('次数上限会写入并锁定在确认方案；当前属于计划级约束，不冒充运行时硬截断。')}</span>
        </div>
      </div>
      {editing && (
        <div className="organization-edit-note">
          {t('保存会生成新的不可变方案版本；当前版本及其哈希不会被覆盖。')}
        </div>
      )}
      {error && <InlineError text={error} />}
    </div>
  );
}

function PlanReview({
  plan,
  hash,
  showStatus = true,
  previousPlan = null,
  revisionNumber = 1,
  onOrganizationSave,
  runtimeCapabilities = [],
  onRuntimeSave,
  onProfileSave,
}: {
  plan: TaskPlan;
  hash: string;
  showStatus?: boolean;
  previousPlan?: TaskPlan | null;
  revisionNumber?: number;
  onOrganizationSave?: (
    lines: ReportingLine[],
    loops: CollaborationLoop[],
  ) => Promise<void>;
  runtimeCapabilities?: RuntimeCapability[];
  onRuntimeSave?: (
    assignments: AgentRuntimeAssignment[],
  ) => Promise<void>;
  onProfileSave?: (
    profile: Exclude<ExecutionProfile, 'custom'>,
  ) => Promise<void>;
}) {
  const { language, t } = useLanguage();
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
            <strong>{t('第 {version} 版 · 基于上一版修改', { version: revisionNumber })}</strong>
            <span>
              {changedSections.length
                ? t('已变更：{sections}', { sections: changedSections.map((section) => t(section)).join(language === 'zh' ? '、' : ', ') })
                : t('未检测到结构变化，请重点检查摘要内容。')}
            </span>
          </div>
        </div>
      )}
      <div className="plan-summary">
        <div className="plan-summary-heading">
          <span><Sparkles size={15} />{t('AI 生成的任务摘要')}</span>
          {showStatus && <StatusBadge status="ready" />}
        </div>
        <p>{plan.summary}</p>
        <div className="plan-facts">
          <span><Users size={15} />{plan.agents.length} Agent</span>
          {plan.execution_profile && (
            <span><Cpu size={15} />{t('执行档位：{profile}', { profile: t(executionProfileName(plan.execution_profile)) })}</span>
          )}
          {(plan.collaboration_loops || []).length > 0 && (
            <span><Repeat2 size={15} />{t('{count} 个有界循环', { count: plan.collaboration_loops.length })}</span>
          )}
          <span><Clock3 size={15} />{t('约 {count} 分钟', { count: plan.estimated_duration_minutes })}</span>
          <span><CalendarClock size={15} />{plan.cadence.update_interval}</span>
        </div>
      </div>

      <section className="review-section">
        <div className="review-title"><h3>{t('Agent 架构')}</h3><span>{plan.execution_mode === 'workflow' ? plan.workflow_id : t('Agent 团队')}</span></div>
        <OrganizationChart
          plan={plan}
          editable={Boolean(onOrganizationSave) && plan.execution_mode === 'aion_team'}
          onSave={onOrganizationSave}
          compact
        />
      </section>

      {onRuntimeSave && (
        <RuntimeAssignments
          agents={plan.agents}
          capabilities={runtimeCapabilities}
          executionProfile={plan.execution_profile}
          onProfileSave={onProfileSave}
          onSave={onRuntimeSave}
        />
      )}

      <section className="review-section">
        <div className="review-title"><h3>{t('执行阶段')}</h3><span>{t('{count} 步', { count: plan.stages.length })}</span></div>
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
        <DetailList title={t('审批')} items={plan.approvals} empty={t('无额外审批')} />
        <DetailList title={t('交付证据')} items={plan.artifacts} empty={t('执行结果待登记')} />
        <DetailList title={t('风险')} items={plan.risks} empty={t('无已知风险')} />
        <DetailList
          title={t('更新')}
          items={[
            plan.update_policy,
            t('本次确认只启动一次；重复调度需另行登记并确认。'),
          ]}
          empty="—"
        />
      </div>
      <div className="hash-line"><ShieldCheck size={14} /><code>{hash}</code></div>
    </div>
  );
}

function executionProfileName(profile: ExecutionProfile): string {
  return {
    fast: '快速',
    balanced: '平衡',
    deep: '深度',
    custom: '自定义',
  }[profile];
}

function RuntimeAssignments({
  agents,
  capabilities,
  executionProfile,
  onProfileSave,
  onSave,
}: {
  agents: PlannedAgent[];
  capabilities: RuntimeCapability[];
  executionProfile?: ExecutionProfile | null;
  onProfileSave?: (profile: Exclude<ExecutionProfile, 'custom'>) => Promise<void>;
  onSave: (assignments: AgentRuntimeAssignment[]) => Promise<void>;
}) {
  const { t } = useLanguage();
  const [assignments, setAssignments] = useState<Record<string, {
    runtime: PlannedAgent['runtime'];
    model: string;
  }>>({});
  const [busy, setBusy] = useState(false);
  const [profileBusy, setProfileBusy] = useState<Exclude<ExecutionProfile, 'custom'> | ''>('');
  const [error, setError] = useState('');
  useEffect(() => {
    setAssignments(Object.fromEntries(agents.map((agent) => [agent.name, {
      runtime: agent.runtime,
      model: agent.model || 'default',
    }])));
    setError('');
    setProfileBusy('');
  }, [agents]);
  const canSave = canSaveRuntimeRevision(agents, capabilities, assignments);
  const modelsFor = (capability: RuntimeCapability | undefined) => (
    capability?.models?.length
      ? capability.models
      : [{
          id: capability?.default_model || 'default',
          label: t('运行时默认（不固定版本）'),
          description: t('运行时将在会话启动时选择模型。'),
          pinning: 'default' as const,
        }]
  );
  const save = async () => {
    if (!canSave || busy || profileBusy) return;
    setBusy(true);
    setError('');
    try {
      await onSave(agents.map((agent) => ({
        agent_name: agent.name,
        runtime: assignments[agent.name]?.runtime || agent.runtime,
        model: assignments[agent.name]?.model || agent.model || 'default',
      })));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('运行时版本创建失败'));
    } finally {
      setBusy(false);
    }
  };
  const applyProfile = async (profile: Exclude<ExecutionProfile, 'custom'>) => {
    if (!onProfileSave || busy || profileBusy || executionProfile === profile) return;
    setProfileBusy(profile);
    setError('');
    try {
      await onProfileSave(profile);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('执行档位版本创建失败'));
      setProfileBusy('');
    }
  };
  const profiles: Array<{
    id: Exclude<ExecutionProfile, 'custom'>;
    icon: typeof Zap;
    title: string;
    detail: string;
  }> = [
    { id: 'fast', icon: Zap, title: '快速', detail: '适合重复运行，优先低延迟模型。' },
    { id: 'balanced', icon: Scale, title: '平衡', detail: '新任务默认，在速度与质量之间平衡。' },
    { id: 'deep', icon: BrainCircuit, title: '深度', detail: '适合首次或复杂分析，优先高质量模型。' },
  ];
  return (
    <section className="review-section runtime-assignment-section">
      <div className="review-title"><h3>{t('运行时与模型')}</h3><span>{t('确认前可调整')}</span></div>
      {onProfileSave && (
        <div className="execution-profile-picker">
          <div className="execution-profile-heading">
            <span>{t('执行档位')}</span>
            <small>{t('选择后生成新版本，并锁定下方每位 Agent 的确切模型。')}</small>
          </div>
          <div className="execution-profile-options">
            {profiles.map((profile) => {
              const Icon = profile.icon;
              const selected = executionProfile === profile.id;
              return (
                <button
                  type="button"
                  key={profile.id}
                  className={selected ? 'selected' : ''}
                  aria-pressed={selected}
                  disabled={Boolean(busy || profileBusy)}
                  onClick={() => void applyProfile(profile.id)}
                >
                  {profileBusy === profile.id ? <LoaderCircle size={17} className="spin" /> : <Icon size={17} />}
                  <span><strong>{t(profile.title)}</strong><small>{t(profile.detail)}</small></span>
                  {selected && <Check size={15} />}
                </button>
              );
            })}
          </div>
          {executionProfile === 'custom' && (
            <div className="execution-profile-custom"><PencilLine size={14} />{t('当前为逐 Agent 自定义模型。')}</div>
          )}
        </div>
      )}
      <p className="runtime-assignment-note">{t('也可以逐项选择运行时和模型；手动保存后标记为自定义。执行时不会自动换用其他模型。')}</p>
      <div className="runtime-assignment-list">
        {agents.map((agent) => {
          const assignment = assignments[agent.name] || {
            runtime: agent.runtime,
            model: agent.model || 'default',
          };
          const capability = capabilities.find((item) => item.runtime === assignment.runtime);
          const models = modelsFor(capability);
          const selectedModel = models.find((model) => model.id === assignment.model);
          return (
            <div className="runtime-assignment-item" key={agent.name}>
              <span className="runtime-assignment-agent">
                <strong>{agent.name}</strong>
                <small>{agent.runtime_reason}</small>
              </span>
              <div className="runtime-assignment-controls">
                <label>
                  <span>{t('运行时')}</span>
                  <select
                    aria-label={t('{agent} 的运行时', { agent: agent.name })}
                    value={assignment.runtime}
                    onChange={(event) => {
                      const runtime = event.target.value as PlannedAgent['runtime'];
                      const nextCapability = capabilities.find((item) => item.runtime === runtime);
                      setAssignments((current) => ({
                        ...current,
                        [agent.name]: {
                          runtime,
                          model: nextCapability?.default_model || 'default',
                        },
                      }));
                    }}
                  >
                    {capabilities.map((item) => (
                      <option key={item.runtime} value={item.runtime} disabled={!item.available}>
                        {t(item.label)}{item.available ? '' : ` · ${t('不可用')}`}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>{t('模型版本')}</span>
                  <select
                    aria-label={t('{agent} 的模型版本', { agent: agent.name })}
                    value={assignment.model}
                    disabled={!capability?.available}
                    onChange={(event) => setAssignments((current) => ({
                      ...current,
                      [agent.name]: { ...assignment, model: event.target.value },
                    }))}
                  >
                    {!selectedModel && (
                      <option value={assignment.model} disabled>
                        {assignment.model} · {t('当前不可用')}
                      </option>
                    )}
                    {models.map((model) => (
                      <option key={model.id} value={model.id}>
                        {t(model.label)}{model.id === 'default' ? '' : ` · ${model.id}`}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              {selectedModel && (
                <div className={`runtime-model-detail ${selectedModel.pinning}`}>
                  <span>{t(selectedModel.pinning === 'exact' ? '精确模型 ID' : selectedModel.pinning === 'alias' ? '滚动模型别名' : '运行时自动选择')}</span>
                  <code>{selectedModel.id}</code>
                  {selectedModel.description && <small>{t(selectedModel.description)}</small>}
                </div>
              )}
            </div>
          );
        })}
      </div>
      {!canSave && <div className="runtime-unavailable">{t('请选择至少一个有变化、且本机当前可用的运行时或模型版本。')}</div>}
      <div className="runtime-save-row"><button className="secondary-button" type="button" disabled={!canSave || busy || Boolean(profileBusy)} onClick={() => void save()}>{busy ? <LoaderCircle size={16} className="spin" /> : <Save size={16} />}{t('保存为新版本')}</button></div>
      {error && <InlineError text={error} />}
    </section>
  );
}

function MemberObservationBadge({ member }: { member: AgentObservation }) {
  const { language, t } = useLanguage();
  const presentation = observationPresentation(member.state, language);
  return <span className={`member-observation ${presentation.tone}`} title={member.observed_at ? t('最近观测：{time}', { time: formatTime(member.observed_at, language) }) : undefined}><span className="status-dot" />{member.agent_name} · {presentation.label}</span>;
}

function changedPlanSections(previous: TaskPlan | null, current: TaskPlan): string[] {
  if (!previous) return [];
  const sections: Array<[string, unknown, unknown]> = [
    ['任务摘要', [previous.title, previous.summary, previous.estimated_duration_minutes], [current.title, current.summary, current.estimated_duration_minutes]],
    ['Agent 架构', previous.agents, current.agents],
    ['运行时安排', previous.agents.map((agent) => [agent.name, agent.runtime, agent.model || 'default']), current.agents.map((agent) => [agent.name, agent.runtime, agent.model || 'default'])],
    ['循环协作', previous.collaboration_loops || [], current.collaboration_loops || []],
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

function ActiveMemberCard({ member }: { member: ActiveMemberProgress }) {
  const { language, t } = useLanguage();
  const stateLabel = member.state === 'running'
    ? '工作中'
    : member.state === 'blocked'
      ? '阻塞'
      : '排队';
  return (
    <div className={`active-member-card ${member.state}`}>
      <div className="active-member-icon"><Bot size={18} /></div>
      <div className="active-member-copy">
        <strong>{member.agent_name}</strong>
        <span>{t(stateLabel)}</span>
      </div>
      <div className="active-member-time">
        <Clock3 size={13} />
        <span>
          {member.elapsed_seconds == null
            ? t('活动已观测')
            : t('已运行 {duration}', {
              duration: formatExecutionElapsed(member.elapsed_seconds, language),
            })}
        </span>
      </div>
      {member.slow && <span className="active-member-slow">{t('持续时间较长')}</span>}
    </div>
  );
}

function RuntimeActivityList({
  activities,
  limit,
}: {
  activities: RuntimeActivity[];
  limit?: number;
}) {
  const { language, t } = useLanguage();
  const rows = typeof limit === 'number' ? activities.slice(0, limit) : activities;
  const statusLabels: Record<RuntimeActivity['status'], string> = {
    running: '执行中',
    completed: '调用完成',
    failed: '调用失败',
    observed: '已观测',
  };
  return (
    <div className="runtime-activity-list" role="list">
      {rows.map((activity) => {
        const source = runtimeActivitySource(activity);
        return (
          <div className="runtime-activity-row" role="listitem" key={`${activity.agent_name}-${activity.activity_id}`}>
            <span className={`runtime-activity-marker ${runtimeActivityTone(activity.status)}`}>
              {activity.kind === 'response' ? <MessageSquare size={14} /> : <Activity size={14} />}
            </span>
            <div className="runtime-activity-copy">
              <strong>{activity.agent_name}</strong>
              <span>{t(source.label, source.values)}</span>
            </div>
            <div className="runtime-activity-meta">
              <span className={runtimeActivityTone(activity.status)}>{t(statusLabels[activity.status])}</span>
              <time dateTime={activity.observed_at}>{formatTime(activity.observed_at, language)}</time>
              {activity.count > 1 && <small>×{activity.count}</small>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ExecutionStageList({
  plan,
  execution,
  workStatus,
}: {
  plan: TaskPlan;
  execution?: PlanRecord['execution'];
  workStatus: PlanRecord['status'];
}) {
  const { language, t } = useLanguage();
  const progressRows = execution?.progress?.stages || [];
  const progressByOrder = new Map(progressRows.map((stage) => [stage.stage_order, stage]));
  const summary = stageProgressSummary(progressRows);
  const runningWork = [
    'dispatching',
    'running',
    'pause_requested',
    'paused',
    'resuming',
    'cancel_requested',
    'awaiting_approval',
    'awaiting_input',
  ].includes(workStatus);

  return (
    <section className="review-section work-stage-section" aria-label={t('执行阶段')}>
      <div className="review-title">
        <h3>{t('执行阶段')}</h3>
        <span>
          {summary.observed
            ? t('Agent 已上报完成 {completed}/{total}', {
              completed: summary.completed,
              total: plan.stages.length,
            })
            : t('{count} 步', { count: plan.stages.length })}
        </span>
      </div>
      {summary.observed && (
        <div
          className="stage-progress-track"
          role="img"
          aria-label={t('Agent 已上报完成 {completed}/{total}', {
            completed: summary.completed,
            total: plan.stages.length,
          })}
        >
          {plan.stages.map((stage) => {
            const row = progressByOrder.get(stage.order);
            const presentation = stageProgressPresentation(row?.status || 'not_started', workStatus);
            return <span key={stage.order} className={`stage-progress-segment ${presentation.tone}`} />;
          })}
        </div>
      )}
      <div className="stage-evidence-note">
        {summary.observed ? <ShieldCheck size={14} /> : <Activity size={14} />}
        <span>{t(summary.observed
          ? '阶段状态来自 AionUi 团队工作项；不展示隐藏思维、工具参数或输出正文，也不证明业务结果正确。'
          : runningWork
            ? '运行时尚未提供可绑定到步骤的团队工作项；以下仍是已确认的计划顺序。'
            : '以下是已确认的计划顺序；当前没有阶段级运行证据。')}</span>
      </div>
      <div className="stage-list">
        {plan.stages.map((stage) => {
          const stageProgress = progressByOrder.get(stage.order);
          const status = stageProgress?.status || 'not_started';
          const presentation = stageProgressPresentation(status, workStatus);
          const observedAt = stageProgress?.completed_at || stageProgress?.updated_at || stageProgress?.started_at;
          const stageActivities = stageProgress?.recent_activity || [];
          return (
            <div className={`stage-runtime-item ${presentation.tone}`} key={stage.order}>
              <div className="stage-row">
                <span className="stage-number">{stage.order}</span>
                <div>
                  <strong>{stage.title}</strong>
                  <p>{stage.outcome}</p>
                  <div className="stage-runtime-detail">
                    <span>{stageProgress?.agent_name || stage.owner}</span>
                    {stageProgress?.blocked_by.length ? (
                      <span>{t('依赖步骤 {steps}', { steps: stageProgress.blocked_by.join(', ') })}</span>
                    ) : null}
                    {observedAt ? <time dateTime={observedAt}>{formatTime(observedAt, language)}</time> : null}
                  </div>
                </div>
                <span className="stage-owner">{stage.owner}</span>
                <span className={`stage-runtime-status ${presentation.tone}`}>
                  {status === 'running' ? <LoaderCircle size={14} className="spin" />
                    : status === 'completed' ? <CheckCircle2 size={14} />
                      : status === 'failed' || status === 'unknown' ? <AlertTriangle size={14} />
                        : status === 'blocked' ? <Clock3 size={14} />
                          : stage.checkpoint ? <ShieldCheck size={14} /> : <Circle size={12} />}
                  <span>{t(presentation.label)}</span>
                </span>
              </div>
              {stageActivities.length > 0 && (
                <div className="stage-runtime-activity">
                  <RuntimeActivityList activities={stageActivities} limit={4} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function ApprovalModeControl({
  mode,
  onChange,
}: {
  mode: ApprovalMode;
  onChange: (mode: ApprovalMode) => void;
}) {
  const { t } = useLanguage();
  const manual = mode === 'manual_all';
  return (
    <section className="approval-mode-control" aria-label={t('审批模式')}>
      <div className="approval-mode-copy">
        <span className="approval-mode-icon"><ShieldCheck size={17} /></span>
        <div>
          <strong>{t(manual ? '逐项人工审批' : '自动模式')}</strong>
          <span>{t(manual
            ? '打开后，每个执行工具都会暂停等待你的决定。'
            : '任务确认后，执行工具会自动单次放行并保留完整审计记录。')}</span>
        </div>
      </div>
      <label className="approval-mode-switch">
        <span>{t('逐项人工审批')}</span>
        <input
          type="checkbox"
          role="switch"
          checked={manual}
          onChange={(event) => onChange(event.target.checked ? 'manual_all' : 'automatic')}
        />
      </label>
      <p>
        <AlertTriangle size={13} />
        {t(manual
          ? '每项工具调用都需要人工批准或拒绝。'
          : 'Auto 模式不会跳过方案确认；每次自动决定仍可审计。')}
      </p>
    </section>
  );
}

type KnowledgeExcerpt = {
  id: string;
  category: string;
  title: string;
  statement: string;
  source: string;
};

type KnowledgeDocument = {
  scope: string;
  sourcingNote: string;
  disclaimer: string;
  usageRule: string;
  excerpts: KnowledgeExcerpt[];
};

function objectValue(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function textValue(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function knowledgeDocument(value: unknown): KnowledgeDocument | null {
  const root = objectValue(value);
  if (!root || !Array.isArray(root.excerpts)) return null;
  const excerpts = root.excerpts.flatMap((item) => {
    const row = objectValue(item);
    if (!row) return [];
    const id = textValue(row.id);
    const statement = textValue(row.statement);
    if (!id || !statement) return [];
    return [{
      id,
      category: textValue(row.category),
      title: textValue(row.title),
      statement,
      source: textValue(row.source),
    }];
  });
  return {
    scope: textValue(root.scope),
    sourcingNote: textValue(root.sourcing_note),
    disclaimer: textValue(root.disclaimer),
    usageRule: textValue(root.usage_rule),
    excerpts,
  };
}

function formatArtifactSize(size: number | null | undefined): string {
  if (size == null) return '—';
  if (size < 1024) return `${size.toLocaleString()} B`;
  return `${(size / 1024).toFixed(size < 10 * 1024 ? 1 : 0)} KB`;
}

function resultFactLabel(fact: ResultSummaryFact, t: Translate): string {
  const labels: Record<ResultSummaryFact['kind'], string> = {
    customer: '对象',
    data_scope: '数据范围',
    four_pillars: '四柱',
    day_master: '日主',
    engine: '确定性引擎',
    subject: '主题',
  };
  return t(labels[fact.kind]);
}

function resultFactValue(fact: ResultSummaryFact, t: Translate): string {
  return fact.kind === 'data_scope' && fact.value === 'synthetic'
    ? t('合成演示数据')
    : fact.value;
}

function resultCheckCopy(check: ResultSummaryCheck, t: Translate): { label: string; detail: string } {
  if (check.kind === 'audit') {
    return {
      label: t('引用核验'),
      detail: check.detail ? t('{count} 可追溯', { count: check.detail }) : t('审核记录已生成'),
    };
  }
  if (check.kind === 'consistency') {
    return {
      label: t('一致性检查'),
      detail: check.detail === '0'
        ? t('未发现不一致')
        : t('{count} 项待检查', { count: check.detail || '—' }),
    };
  }
  if (check.kind === 'signoff') {
    return {
      label: t('人工审签'),
      detail: t(check.state === 'pass' ? '已附签署记录' : '审签文件尚未成为已登记证据'),
    };
  }
  return {
    label: t('证据绑定'),
    detail: t('{count} 个文件已绑定', { count: check.detail }),
  };
}

function RunArtifactPreviewDialog({
  preview,
  onClose,
}: {
  preview: PlanArtifactPreview;
  onClose: () => void;
}) {
  const { t } = useLanguage();
  const registered = preview.evidence_status === 'registered';
  return (
    <div className="modal-layer run-artifact-preview-layer" role="dialog" aria-modal="true" aria-label={t('运行文件预览')}>
      <button className="modal-backdrop" type="button" aria-label={t('关闭')} onClick={onClose} />
      <section className="run-artifact-preview-dialog">
        <header className="modal-header">
          <div><span className="section-kicker">{t('本次运行')}</span><h2>{t('运行文件预览')}</h2></div>
          <button className="icon-button" type="button" title={t('关闭')} onClick={onClose}><X size={19} /></button>
        </header>
        <div className="run-artifact-preview-content">
          <div className="run-artifact-preview-summary">
            <span><FileJson size={20} /></span>
            <div><strong>{preview.name}</strong><small>{formatArtifactSize(preview.size)}</small></div>
            <span className={registered ? 'run-artifact-registered' : 'run-artifact-unverified'}>
              {t(registered ? '已登记为本次运行证据' : '未登记为结果证据')}
            </span>
          </div>
          <dl className="knowledge-preview-facts">
            <div><dt>SHA-256</dt><dd><code>{preview.sha256}</code></dd></div>
            <div><dt>{t('文件类型')}</dt><dd>{preview.mime || 'application/octet-stream'}</dd></div>
          </dl>
          <div className="run-artifact-boundary"><AlertTriangle size={15} /><span>{t(registered
            ? '该文件已按哈希绑定到本次执行；仍需 eval 或人工审签才能证明业务结果。'
            : '这是运行目录中的只读文件；能查看不代表内容已经通过 eval、CAS 登记或人工审签。')}</span></div>
          <pre className="run-artifact-json">{JSON.stringify(preview.content, null, 2)}</pre>
        </div>
      </section>
    </div>
  );
}

function RunArtifactsPanel({ record }: { record: PlanRecord }) {
  const { t } = useLanguage();
  const [artifacts, setArtifacts] = useState<PlanArtifact[]>([]);
  const [summaryPreviews, setSummaryPreviews] = useState<PlanArtifactPreview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [previewLoading, setPreviewLoading] = useState('');
  const [preview, setPreview] = useState<PlanArtifactPreview | null>(null);

  useEffect(() => {
    let cancelled = false;
    setArtifacts([]);
    setSummaryPreviews([]);
    setLoading(true);
    setError('');
    setPreview(null);
    void getPlanArtifacts(record.plan_id)
      .then(async (rows) => {
        if (cancelled) return;
        setArtifacts(rows);
        const results = await Promise.allSettled(
          selectResultPreviewArtifacts(rows).map((artifact) => (
            getPlanArtifact(record.plan_id, artifact.name)
          )),
        );
        if (!cancelled) {
          setSummaryPreviews(results.flatMap((result) => (
            result.status === 'fulfilled' ? [result.value] : []
          )));
        }
      })
      .catch(() => {
        if (!cancelled) setError(t('运行文件暂时无法读取'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [record.plan_id, record.updated_at, t]);

  const openArtifact = async (artifact: PlanArtifact) => {
    if (!artifact.preview_supported || previewLoading) return;
    setError('');
    setPreviewLoading(artifact.name);
    try {
      setPreview(await getPlanArtifact(record.plan_id, artifact.name));
    } catch {
      setError(t('运行文件暂时无法读取'));
    } finally {
      setPreviewLoading('');
    }
  };

  const stageSummary = stageProgressSummary(record.execution?.progress?.stages || []);
  const resultSummary = useMemo(
    () => buildResultSummary(summaryPreviews, artifacts),
    [artifacts, summaryPreviews],
  );
  const expectsPdf = Boolean(record.plan?.artifacts.some((item) => /pdf/i.test(item)));
  const hasPdf = artifacts.some((artifact) => (
    artifact.mime === 'application/pdf' || artifact.name.toLowerCase().endsWith('.pdf')
  ));

  return (
    <section className="run-artifacts-section" aria-label={t('本次运行结果')}>
      <header className="run-artifacts-heading">
        <div>
          <span className="section-kicker">{t('本次运行')}</span>
          <h3>{t('最终结果')}</h3>
        </div>
        <span>{t('结论优先 · 证据可展开')}</span>
      </header>
      {loading && <div className="run-artifacts-loading"><LoaderCircle size={17} className="spin" />{t('正在整理最终结果')}</div>}
      {!loading && resultSummary.report && (
        <section className="run-primary-report">
          <span className="run-primary-report-icon"><FileCheck2 size={22} /></span>
          <div>
            <strong>{t('完整报告')}</strong>
            <span>{resultSummary.report.name} · {formatArtifactSize(resultSummary.report.size)}</span>
            <small>{t(resultSummary.report.evidence_status === 'registered'
              ? '报告已按哈希绑定到本次运行，可直接打开。'
              : '已发现报告文件，但尚未登记为本次运行证据。')}</small>
          </div>
          {resultSummary.report.evidence_status === 'registered' ? (
            <a
              className="primary-button"
              href={planArtifactContentUrl(record.plan_id, resultSummary.report.name)}
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink size={16} />{t('打开完整报告')}
            </a>
          ) : (
            <button className="secondary-button" type="button" disabled>
              <FileCheck2 size={16} />{t('报告尚未登记')}
            </button>
          )}
        </section>
      )}
      {!loading && resultSummary.facts.length > 0 && (
        <dl className="run-summary-facts">
          {resultSummary.facts.map((fact) => (
            <div key={fact.kind}>
              <dt>{resultFactLabel(fact, t)}</dt>
              <dd>{resultFactValue(fact, t)}</dd>
            </div>
          ))}
        </dl>
      )}
      {!loading && resultSummary.conclusions.length > 0 && (
        <section className="run-summary-conclusions">
          <header>
            <div><span className="section-kicker">{t('可读结果')}</span><h4>{t('主要结论')}</h4></div>
            <span>{t('{count} 条', { count: resultSummary.conclusions.length })}</span>
          </header>
          <ol>
            {resultSummary.conclusions.slice(0, 6).map((conclusion, index) => (
              <li key={`${conclusion.source}-${conclusion.title}-${index}`}>
                <span>{index + 1}</span>
                <div>{conclusion.title && <strong>{conclusion.title}</strong>}<p>{conclusion.statement}</p></div>
              </li>
            ))}
          </ol>
          {resultSummary.conclusions.length > 6 && (
            <details className="run-more-conclusions">
              <summary>{t('查看其余 {count} 条结论', { count: resultSummary.conclusions.length - 6 })}<ChevronDown size={15} /></summary>
              <ol start={7}>
                {resultSummary.conclusions.slice(6).map((conclusion, index) => (
                  <li key={`${conclusion.source}-${conclusion.title}-${index + 6}`}>
                    <span>{index + 7}</span>
                    <div>{conclusion.title && <strong>{conclusion.title}</strong>}<p>{conclusion.statement}</p></div>
                  </li>
                ))}
              </ol>
            </details>
          )}
        </section>
      )}
      {!loading && resultSummary.checks.length > 0 && (
        <section className="run-summary-checks" aria-label={t('结果检查')}>
          {resultSummary.checks.map((check) => {
            const copy = resultCheckCopy(check, t);
            return (
              <div className={check.state} key={check.kind}>
                {check.state === 'pass' ? <CheckCircle2 size={17} /> : <AlertTriangle size={17} />}
                <span><strong>{copy.label}</strong><small>{copy.detail}</small></span>
              </div>
            );
          })}
        </section>
      )}
      {!loading && !resultSummary.hasReadableSummary && artifacts.length > 0 && (
        <div className="run-summary-unavailable"><AlertTriangle size={16} /><span>{t('本次运行没有标准化的可读摘要；完整报告和技术证据仍可查看。')}</span></div>
      )}
      {!loading && artifacts.length > 0 && (
        <details className="run-technical-evidence">
          <summary>
            <Database size={17} />
            <span><strong>{t('技术证据')}</strong><small>{t('{count} 个文件 · 哈希与原始数据', { count: artifacts.length })}</small></span>
            <ChevronDown size={16} />
          </summary>
          <div className="run-technical-evidence-body">
            <div className="run-result-facts">
              <span><strong>{artifacts.length}</strong><small>{t('运行文件')}</small></span>
              <span><strong>{stageSummary.observed ? `${stageSummary.completed}/${stageSummary.total}` : '—'}</strong><small>{t('Agent 上报阶段完成')}</small></span>
              <span><strong>{record.execution?.outcome_verified ? t('已核验') : t('待核验')}</strong><small>{t('业务结果')}</small></span>
            </div>
            <div className="run-artifact-list">
              {artifacts.map((artifact) => (
                <article className="run-artifact-row" key={artifact.name}>
                  <span className="run-artifact-file-icon"><FileJson size={19} /></span>
                  <div className="run-artifact-copy">
                    <strong>{artifact.name}</strong>
                    <small>{formatArtifactSize(artifact.size)} · SHA-256 {artifact.sha256?.slice(0, 12) || '—'}...</small>
                    <span className={artifact.evidence_status === 'registered' ? 'registered' : undefined}>
                      {t(artifact.evidence_status === 'registered'
                        ? 'CAS 证据 · 已绑定本次执行'
                        : '运行目录文件 · 尚未登记为结果证据')}
                    </span>
                  </div>
                  <button
                    className="secondary-button"
                    type="button"
                    disabled={!artifact.preview_supported || Boolean(previewLoading)}
                    onClick={() => void openArtifact(artifact)}
                  >
                    {previewLoading === artifact.name
                      ? <LoaderCircle size={15} className="spin" />
                      : artifact.artifact_type === 'candidate_knowledge_base' ? <BookOpen size={15} /> : <Search size={15} />}
                    {t(artifact.preview_supported ? '查看内容' : '暂不支持预览')}
                  </button>
                </article>
              ))}
            </div>
          </div>
        </details>
      )}
      {!loading && artifacts.length === 0 && !error && (
        <div className="work-empty compact-empty"><FileCheck2 size={24} /><strong>{t('未发现运行文件')}</strong><span>{t('Agent 回应或进程结束并不等于已经生成可交付文件。')}</span></div>
      )}
      {!loading && expectsPdf && !hasPdf && (
        <div className="run-artifact-gap"><AlertTriangle size={15} /><span>{t('方案要求 PDF，但本次运行目录中未发现 PDF；交付仍不完整。')}</span></div>
      )}
      {error && <InlineError text={error} />}
      {preview && (
        preview.artifact_type === 'candidate_knowledge_base'
          ? <KnowledgeBasePreviewDialog preview={preview} onClose={() => setPreview(null)} />
          : <RunArtifactPreviewDialog preview={preview} onClose={() => setPreview(null)} />
      )}
    </section>
  );
}

function KnowledgeBasePreviewDialog({
  preview,
  onClose,
}: {
  preview: RuntimeInputArtifactPreview;
  onClose: () => void;
}) {
  const { t } = useLanguage();
  const [query, setQuery] = useState('');
  const document = useMemo(() => knowledgeDocument(preview.content), [preview.content]);
  const filtered = useMemo(() => {
    if (!document) return [];
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return document.excerpts;
    return document.excerpts.filter((entry) => (
      [entry.id, entry.category, entry.title, entry.statement, entry.source]
        .join('\n')
        .toLocaleLowerCase()
        .includes(normalized)
    ));
  }, [document, query]);
  const candidate = preview.status === 'candidate_pending_signoff';

  return (
    <div className="modal-layer knowledge-preview-layer" role="dialog" aria-modal="true" aria-label={t('知识库预览')}>
      <button className="modal-backdrop" type="button" aria-label={t('关闭')} onClick={onClose} />
      <section className="knowledge-preview-dialog">
        <header className="modal-header">
          <div>
            <span className="section-kicker">{t('运行附件')}</span>
            <h2>{t('知识库预览')}</h2>
          </div>
          <button className="icon-button" type="button" title={t('关闭')} onClick={onClose}>
            <X size={19} />
          </button>
        </header>
        <div className="knowledge-preview-content">
          <div className="knowledge-preview-summary">
            <span><BookOpen size={20} /></span>
            <div>
              <strong>{preview.name}</strong>
              <small>{preview.item_count == null
                ? t('JSON 运行附件')
                : t('{count} 条规则', { count: preview.item_count })}</small>
            </div>
            <span className={`knowledge-preview-state ${candidate ? 'candidate' : ''}`}>
              {t(candidate ? '候选知识库 · 尚未审签' : (preview.status || '运行附件'))}
            </span>
          </div>
          <dl className="knowledge-preview-facts">
            <div>
              <dt>SHA-256</dt>
              <dd><code>{preview.sha256}</code></dd>
            </div>
            <div>
              <dt>{t('文件大小')}</dt>
              <dd>{preview.size == null ? t('未知') : `${preview.size.toLocaleString()} bytes`}</dd>
            </div>
          </dl>
          {document ? (
            <>
              {document.scope && (
                <section className="knowledge-preview-note">
                  <strong>{t('适用范围')}</strong>
                  <p>{document.scope}</p>
                </section>
              )}
              {(document.sourcingNote || document.disclaimer) && (
                <section className="knowledge-preview-note subdued">
                  <strong>{t('来源与边界')}</strong>
                  {document.sourcingNote && <p>{document.sourcingNote}</p>}
                  {document.disclaimer && <p>{document.disclaimer}</p>}
                </section>
              )}
              <div className="knowledge-preview-toolbar">
                <label>
                  <Search size={15} />
                  <input
                    type="search"
                    value={query}
                    placeholder={t('搜索规则、分类或来源')}
                    aria-label={t('搜索知识库')}
                    onChange={(event) => setQuery(event.target.value)}
                  />
                </label>
                <span>{t('显示 {shown} / {total} 条', {
                  shown: filtered.length,
                  total: document.excerpts.length,
                })}</span>
              </div>
              <div className="knowledge-rule-list">
                {filtered.map((entry) => (
                  <article className="knowledge-rule-row" key={entry.id}>
                    <header>
                      <code>{entry.id}</code>
                      {entry.category && <span>{entry.category}</span>}
                      <strong>{entry.title}</strong>
                    </header>
                    <p>{entry.statement}</p>
                    {entry.source && <footer>{t('来源：{source}', { source: entry.source })}</footer>}
                  </article>
                ))}
                {filtered.length === 0 && (
                  <p className="knowledge-preview-empty">{t('没有匹配的规则')}</p>
                )}
              </div>
              {document.usageRule && (
                <section className="knowledge-preview-note usage-rule">
                  <strong>{t('使用规则')}</strong>
                  <p>{document.usageRule}</p>
                </section>
              )}
            </>
          ) : (
            <pre className="knowledge-json-preview">{JSON.stringify(preview.content, null, 2)}</pre>
          )}
        </div>
      </section>
    </div>
  );
}

function RuntimeInputPanel({
  planId,
  request,
  onAnswer,
}: {
  planId: string;
  request: NonNullable<PlanRecord['execution']>['input_requests'][number];
  onAnswer: (answer: string) => Promise<void>;
}) {
  const { t } = useLanguage();
  const [answer, setAnswer] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [artifacts, setArtifacts] = useState<RuntimeInputArtifact[]>([]);
  const [artifactLoading, setArtifactLoading] = useState(true);
  const [artifactError, setArtifactError] = useState('');
  const [previewLoading, setPreviewLoading] = useState('');
  const [preview, setPreview] = useState<RuntimeInputArtifactPreview | null>(null);

  useEffect(() => {
    let cancelled = false;
    setArtifacts([]);
    setArtifactError('');
    setArtifactLoading(true);
    setPreview(null);
    void getRuntimeInputArtifacts(planId, request.request_id)
      .then((rows) => {
        if (!cancelled) setArtifacts(rows);
      })
      .catch(() => {
        if (!cancelled) setArtifactError(t('附件暂时无法读取'));
      })
      .finally(() => {
        if (!cancelled) setArtifactLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [planId, request.request_id, t]);

  const openArtifact = async (artifact: RuntimeInputArtifact) => {
    if (!artifact.available || !artifact.preview_supported || previewLoading) return;
    setArtifactError('');
    setPreviewLoading(artifact.name);
    try {
      setPreview(await getRuntimeInputArtifact(planId, request.request_id, artifact.name));
    } catch {
      setArtifactError(t('附件暂时无法读取'));
    } finally {
      setPreviewLoading('');
    }
  };

  const submit = async () => {
    const normalized = answer.trim();
    if (!normalized || submitting) return;
    setSubmitting(true);
    setError('');
    try {
      await onAnswer(normalized);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('回答未能送达，请重试'));
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <section className="runtime-input-panel" aria-label={t('任务需要补充信息')}>
      <div className="runtime-input-heading">
        <span><MessageSquare size={17} /></span>
        <div>
          <strong>{t('{agent} 需要你补充信息', { agent: request.agent_name })}</strong>
          <small>{t('回答后会继续同一支已确认的团队。')}</small>
        </div>
      </div>
      <p className="runtime-input-question">{request.question}</p>
      {(artifactLoading || artifacts.length > 0 || artifactError) && (
        <section className="runtime-input-artifacts" aria-label={t('本次审定附件')}>
          <header>
            <span><BookOpen size={15} />{t('本次审定附件')}</span>
            <small>{t('只读预览不代表批准或审签')}</small>
          </header>
          {artifactLoading && (
            <div className="runtime-input-artifact-loading">
              <LoaderCircle size={15} className="spin" />{t('正在读取附件')}
            </div>
          )}
          {!artifactLoading && artifacts.length > 0 && (
            <div className="runtime-input-artifact-list">
              {artifacts.map((artifact) => {
                const canPreview = artifact.available && artifact.preview_supported;
                return (
                  <button
                    className="runtime-input-artifact-button"
                    type="button"
                    key={artifact.name}
                    disabled={!canPreview || Boolean(previewLoading)}
                    onClick={() => void openArtifact(artifact)}
                  >
                    <span className="runtime-input-artifact-icon"><FileJson size={18} /></span>
                    <span>
                      <strong>{artifact.name}</strong>
                      <small className="runtime-input-artifact-meta">
                        {artifact.item_count == null
                          ? t('JSON 运行附件')
                          : t('{count} 条规则', { count: artifact.item_count })}
                        {artifact.sha256 && <code>SHA-256 {artifact.sha256.slice(0, 12)}...</code>}
                      </small>
                    </span>
                    <span className="runtime-input-artifact-action">
                      {previewLoading === artifact.name
                        ? <LoaderCircle size={15} className="spin" />
                        : canPreview ? t('查看知识库') : t('附件不可用')}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
          {artifactError && <small className="runtime-input-artifact-error">{artifactError}</small>}
        </section>
      )}
      {request.choices.length > 0 && (
        <div className="runtime-input-choices" role="group" aria-label={t('可选回答')}>
          {request.choices.map((choice) => (
            <button
              key={choice}
              type="button"
              aria-pressed={answer === choice}
              className={answer === choice ? 'selected' : ''}
              disabled={submitting}
              onClick={() => setAnswer(choice)}
            >
              {choice}
            </button>
          ))}
        </div>
      )}
      <label className="runtime-input-answer">
        <span>{t('你的回答')}</span>
        <textarea
          value={answer}
          rows={3}
          maxLength={4000}
          disabled={submitting}
          placeholder={t('补充任务所需的信息；不要在这里填写密码或 API key。')}
          onChange={(event) => setAnswer(event.target.value)}
        />
      </label>
      {error && <InlineError text={error} />}
      <div className="runtime-input-footer">
        <span><ShieldCheck size={13} />{t('回答作为任务数据发送；账本只保存哈希，不保存正文。')}</span>
        <button
          className="primary-button"
          type="button"
          disabled={!answer.trim() || submitting}
          onClick={() => void submit()}
        >
          {submitting ? <LoaderCircle size={16} className="spin" /> : <Send size={16} />}
          {t('提交并继续')}
        </button>
      </div>
      {preview && (
        <KnowledgeBasePreviewDialog preview={preview} onClose={() => setPreview(null)} />
      )}
    </section>
  );
}

function InlineApprovalPanel({
  approval,
  onDecision,
}: {
  approval: ApprovalCard;
  onDecision: (
    approval: ApprovalCard,
    decision: 'approve' | 'reject',
    decisionNote: string,
  ) => Promise<void>;
}) {
  const { t } = useLanguage();
  const [decision, setDecision] = useState<'approve' | 'reject' | null>(null);
  const [decisionNote, setDecisionNote] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setDecision(null);
    setDecisionNote('');
    setConfirmed(false);
    setBusy(false);
    setError('');
  }, [approval.approval_id]);

  const choose = (next: 'approve' | 'reject') => {
    if (busy) return;
    setDecision(next);
    setConfirmed(false);
    setError('');
  };

  const submit = async () => {
    if (!decision || !confirmed || busy) return;
    setBusy(true);
    setError('');
    try {
      await onDecision(approval, decision, decisionNote);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('审批提交失败'));
      setBusy(false);
    }
  };

  return (
    <section className="runtime-input-panel inline-approval-panel" aria-label={t('此任务需要你的决定')}>
      <div className="runtime-input-heading">
        <span><ClipboardCheck size={17} /></span>
        <div>
          <strong>{t('此任务需要你的决定')}</strong>
          <small>{t('在这里处理后会继续同一支已确认的团队。')}</small>
        </div>
      </div>
      <p className="runtime-input-question">{approval.title}</p>
      <p className="inline-approval-summary">{approval.summary}</p>
      {approval.tool_name && (
        <div className="approval-tool"><span>{t('工具')}</span><code>{approval.tool_name}</code></div>
      )}
      {approval.tool_input && <pre className="approval-input">{approval.tool_input}</pre>}
      {approval.risks.length > 0 && (
        <div className="approval-risks">
          {approval.risks.map((risk) => <span key={risk}><AlertTriangle size={13} />{risk}</span>)}
        </div>
      )}
      <small className="inline-approval-recommendation">{approval.recommended_action}</small>

      {decision ? (
        <div className="inline-approval-confirmation">
          <div className="inline-approval-decision-title">
            <strong>{t(decision === 'approve' ? '批准这项操作' : '拒绝这项操作')}</strong>
            <button type="button" disabled={busy} onClick={() => setDecision(null)}>{t('取消决定')}</button>
          </div>
          <label className="runtime-input-answer">
            <span>{t('决定说明（可选）')}</span>
            <textarea
              value={decisionNote}
              rows={2}
              maxLength={500}
              disabled={busy}
              placeholder={t('记录为什么批准或拒绝')}
              onChange={(event) => setDecisionNote(event.target.value)}
            />
          </label>
          <label className="consent-row inline-approval-consent">
            <input
              type="checkbox"
              checked={confirmed}
              disabled={busy}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            <span>{t('我已检查这项请求的内容、工具和风险，并确认本次决定')}</span>
          </label>
          {error && <InlineError text={error} />}
          <div className="runtime-input-footer inline-approval-footer">
            <span><ShieldCheck size={13} />{t('本次决定只用于这条已暂停的工具调用，并写入审计记录。')}</span>
            <button
              className={decision === 'approve' ? 'primary-button' : 'secondary-button danger-button'}
              type="button"
              disabled={!confirmed || busy}
              onClick={() => void submit()}
            >
              {busy ? <LoaderCircle size={16} className="spin" /> : decision === 'approve' ? <Check size={16} /> : <X size={16} />}
              {t(busy ? '正在恢复任务' : decision === 'approve' ? '确认批准' : '确认拒绝')}
            </button>
          </div>
        </div>
      ) : (
        <div className="runtime-input-footer inline-approval-footer">
          <span><ShieldCheck size={13} />{t('选择后会在此处确认，不会离开当前任务。')}</span>
          <div className="inline-approval-actions">
            <button className="secondary-button danger-button" type="button" onClick={() => choose('reject')}>
              <X size={16} />{t('拒绝')}
            </button>
            <button className="primary-button" type="button" onClick={() => choose('approve')}>
              <Check size={16} />{t('批准')}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function ExecutionView({
  record,
  approvals,
  approvalsAvailable,
  onDecideApproval,
  onAnswerInput,
  onControl,
  onApprovalModeChange,
}: {
  record: PlanRecord;
  approvals: ApprovalCard[];
  approvalsAvailable: boolean;
  onDecideApproval?: (
    approval: ApprovalCard,
    decision: 'approve' | 'reject',
    decisionNote: string,
  ) => Promise<void>;
  onAnswerInput?: (requestId: string, answer: string) => Promise<void>;
  onControl?: (action: 'pause' | 'resume' | 'terminate') => Promise<void>;
  onApprovalModeChange?: (
    approvalMode: 'automatic' | 'manual_all',
    expectedCurrentMode: ApprovalMode,
  ) => Promise<void>;
}) {
  const { language, t } = useLanguage();
  const [controlBusy, setControlBusy] = useState<'pause' | 'resume' | 'terminate' | null>(null);
  const [controlError, setControlError] = useState('');
  const [terminateOpen, setTerminateOpen] = useState(false);
  const [approvalModeBusy, setApprovalModeBusy] = useState(false);
  const [approvalModeError, setApprovalModeError] = useState('');
  const [autoModeConfirmOpen, setAutoModeConfirmOpen] = useState(false);
  const execution = record.execution;
  const failed = record.status === 'failed';
  const done = record.status === 'completed_unverified';
  const cancelled = record.status === 'cancelled';
  const paused = record.status === 'paused';
  const pauseRequested = record.status === 'pause_requested';
  const resuming = record.status === 'resuming';
  const cancelRequested = record.status === 'cancel_requested';
  const progress = execution?.progress;
  const observations = execution?.member_observations || [];
  const activeMembers = progress?.active_members || [];
  const recentActivity = progress?.recent_activity || [];
  const pendingInput = execution?.input_requests.find((request) => request.status === 'pending');
  const awaitingInput = record.status === 'awaiting_input';
  const awaitingApproval = record.status === 'awaiting_approval';
  const taskApprovals = approvals.filter((approval) => approval.plan_id === record.plan_id);
  const controllable = execution?.kind === 'aion_team' && Boolean(onControl);
  const controlPresentation = executionControlPresentation(record.status, controlBusy);
  const showExecutionControls = controllable && controlPresentation.visible;
  const currentApprovalMode = execution?.approval_mode
    || record.approval_mode
    || 'manual_all';
  const autoModeEnabled = currentApprovalMode !== 'manual_all';
  const showApprovalModeControl = execution?.kind === 'aion_team'
    && Boolean(onApprovalModeChange)
    && ['running', 'awaiting_approval', 'awaiting_input', 'pause_requested', 'paused', 'resuming']
      .includes(record.status);
  const showLiveProgress = ['dispatching', 'running', 'pause_requested', 'resuming', 'cancel_requested', 'awaiting_approval', 'awaiting_input'].includes(record.status);
  const showProgressPanel = Boolean(
    showLiveProgress
    || (progress && (!progress.available || activeMembers.length || recentActivity.length)),
  );

  useEffect(() => {
    setControlBusy(null);
    setControlError('');
    setTerminateOpen(false);
    setApprovalModeBusy(false);
    setApprovalModeError('');
    setAutoModeConfirmOpen(false);
  }, [record.plan_id]);

  const runControl = async (action: 'pause' | 'resume' | 'terminate') => {
    if (!onControl || controlBusy) return;
    setControlBusy(action);
    setControlError('');
    try {
      await onControl(action);
      if (action === 'terminate') setTerminateOpen(false);
    } catch (err) {
      setControlError(err instanceof Error ? err.message : t('运行控制请求失败'));
    } finally {
      setControlBusy(null);
    }
  };

  const updateApprovalMode = async (nextMode: 'automatic' | 'manual_all') => {
    if (!onApprovalModeChange || approvalModeBusy) return;
    setApprovalModeBusy(true);
    setApprovalModeError('');
    try {
      await onApprovalModeChange(nextMode, currentApprovalMode);
      setAutoModeConfirmOpen(false);
    } catch (err) {
      setApprovalModeError(err instanceof Error ? err.message : t('审批模式切换失败'));
    } finally {
      setApprovalModeBusy(false);
    }
  };

  const summaryTitle = failed
    ? '任务未启动或已停止'
    : done
      ? '执行已结束'
      : cancelled
        ? '任务已终止'
        : paused
          ? '任务已暂停'
          : pauseRequested
            ? '正在暂停任务'
            : resuming
              ? '正在继续任务'
              : cancelRequested
                ? '正在终止任务'
                : awaitingInput
                  ? '等待你补充信息'
                  : awaitingApproval
                    ? '等待人工审批'
                    : '任务正在运行';
  const summaryCopy = failed
    ? record.error
    : done
      ? t('进程行为已记录，业务结果仍需 artifact、eval 或审签证明。')
      : cancelled
        ? t('运行时已确认停止；已产生的部分交付物与审计证据仍会保留。')
        : paused
          ? t('运行时已确认活动 Agent 暂停；点击继续后会沿用同一份已确认方案。')
          : pauseRequested
            ? t('暂停请求已记录，正在等待运行时确认所有活动 Agent 已暂停。')
            : resuming
              ? t('继续请求已记录，正在等待运行时启动同一份已确认方案。')
              : cancelRequested
                ? t('终止请求已记录，只有运行时确认停止后才会显示为已终止。')
                : awaitingInput
                  ? t('Agent 已暂停当前步骤；回答后会继续同一支已确认的团队。')
                  : awaitingApproval
                    ? t('Agent 已暂停当前工具调用；在此处决定后会继续同一支已确认的团队。')
                    : t('治理记录已保存，已确认的 Agent 团队正在执行。');
  const iconTone = failed
    ? 'danger'
    : done || cancelled
      ? 'neutral'
      : awaitingInput || awaitingApproval || paused || pauseRequested
        ? 'attention'
        : 'active';
  const summaryIcon = failed
    ? <AlertTriangle size={23} />
    : done
      ? <FileCheck2 size={23} />
      : cancelled
        ? <Square size={21} />
        : paused
          ? <Pause size={23} />
          : awaitingInput
            ? <MessageSquare size={23} />
            : awaitingApproval
              ? <ClipboardCheck size={23} />
              : <LoaderCircle size={23} className="spin" />;
  const canTerminate = controllable && [
    'running',
    'awaiting_approval',
    'awaiting_input',
    'pause_requested',
    'paused',
    'resuming',
  ].includes(record.status);

  return (
    <>
      <div className="execution-view">
        <header className="execution-summary-bar">
          <div className={`execution-icon ${iconTone}`}>
            {summaryIcon}
          </div>
          <div className="execution-summary-copy">
            <StatusBadge status={record.status} />
            <h3>{t(summaryTitle)}</h3>
            <p>{summaryCopy}</p>
          </div>
          <div className="execution-summary-actions">
            {progress?.observed_at && (
              <span className="live-update"><Activity size={13} />{t('最近更新：{time}', { time: formatTime(progress.observed_at, language) })}</span>
            )}
            {showApprovalModeControl && (
              <div className="execution-auto-mode">
                <div className="execution-auto-mode-copy">
                  <ShieldCheck size={14} />
                  <span>
                    <strong>{t('Auto 模式')}</strong>
                    <small>{t(currentApprovalMode === 'automatic_safe'
                      ? '受限（旧版）'
                      : autoModeEnabled
                        ? '已开启'
                        : '已关闭')}</small>
                  </span>
                </div>
                <label
                  className="approval-mode-switch execution-auto-mode-switch"
                  title={t(autoModeEnabled
                    ? '关闭后，后续工具调用会在当前工作中等待你的决定。'
                    : '打开后，后续工具调用会自动单次放行并保留审计证据。')}
                >
                  <input
                    type="checkbox"
                    role="switch"
                    aria-label={t('切换 Auto 模式')}
                    checked={autoModeEnabled}
                    disabled={approvalModeBusy}
                    onChange={(event) => {
                      if (event.target.checked) {
                        setApprovalModeError('');
                        setAutoModeConfirmOpen(true);
                      } else {
                        void updateApprovalMode('manual_all');
                      }
                    }}
                  />
                </label>
                {approvalModeBusy && <LoaderCircle size={14} className="spin" />}
              </div>
            )}
            {showExecutionControls && (
              <div className="execution-control-buttons" role="group" aria-label={t('任务运行控制')}>
                <button
                  className={controlPresentation.start.enabled ? 'primary-button' : 'secondary-button'}
                  type="button"
                  disabled={!controlPresentation.start.enabled}
                  onClick={() => void runControl('resume')}
                >
                  {controlPresentation.start.pending
                    ? <LoaderCircle size={16} className="spin" />
                    : <Play size={16} />}
                  {t(controlPresentation.start.label)}
                </button>
                <button
                  className="secondary-button"
                  type="button"
                  disabled={!controlPresentation.pause.enabled}
                  onClick={() => void runControl('pause')}
                >
                  {controlPresentation.pause.pending
                    ? <LoaderCircle size={16} className="spin" />
                    : <Pause size={16} />}
                  {t(controlPresentation.pause.label)}
                </button>
                <button
                  className="secondary-button danger-button"
                  type="button"
                  disabled={!controlPresentation.stop.enabled}
                  onClick={() => setTerminateOpen(true)}
                >
                  {controlPresentation.stop.pending
                    ? <LoaderCircle size={16} className="spin" />
                    : <Square size={15} />}
                  {t(controlPresentation.stop.label)}
                </button>
              </div>
            )}
          </div>
        </header>

        {controlError && <InlineError text={controlError} />}
        {approvalModeError && !autoModeConfirmOpen && <InlineError text={approvalModeError} />}
        {execution?.control_error && <InlineError text={t(execution.control_error)} />}

        {awaitingInput && pendingInput && onAnswerInput && (
          <RuntimeInputPanel
            key={pendingInput.request_id}
            planId={record.plan_id}
            request={pendingInput}
            onAnswer={(answer) => onAnswerInput(pendingInput.request_id, answer)}
          />
        )}
        {awaitingInput && !pendingInput && (
          <InlineError text={t('问题记录暂时不可用，请刷新后重试。')} />
        )}
        {awaitingApproval && taskApprovals.map((approval) => (
          <InlineApprovalPanel
            key={approval.approval_id}
            approval={approval}
            onDecision={(card, decision, decisionNote) => {
              if (!onDecideApproval) return Promise.reject(new Error(t('审批服务暂不可用；任务继续保持暂停。')));
              return onDecideApproval(card, decision, decisionNote);
            }}
          />
        ))}
        {awaitingApproval && taskApprovals.length === 0 && (
          <InlineError text={t(approvalsAvailable
            ? '审批详情暂未同步到此任务，请稍候刷新。'
            : '审批服务暂不可用；任务继续保持暂停。')} />
        )}

        {showProgressPanel && (
          <section className="live-progress" aria-label={t(showLiveProgress ? '实时进度' : '最后观测活动')}>
            <div className="review-title">
              <h3>{t(showLiveProgress ? '实时进度' : '最后观测活动')}</h3>
              <span>{t(showLiveProgress ? '每 2.5 秒刷新' : '执行结束前的最后快照')}</span>
            </div>
            {!progress?.available ? (
              <div className="live-progress-unavailable"><AlertTriangle size={16} />{t('暂时无法读取实时运行信号。')}</div>
            ) : (
              <>
                <div className="live-progress-grid">
                  <section className="live-progress-section">
                    <div className="live-progress-section-title"><Bot size={15} /><strong>{t('当前活动')}</strong></div>
                    {activeMembers.length ? (
                      <div className="active-member-grid">
                        {activeMembers.map((member) => <ActiveMemberCard key={member.agent_name} member={member} />)}
                      </div>
                    ) : (
                      <p className="live-progress-empty">{t('当前没有精确到成员的运行槽位。')}</p>
                    )}
                  </section>
                  <section className="live-progress-section">
                    <div className="live-progress-section-title"><Activity size={15} /><strong>{t('最近活动')}</strong></div>
                    {recentActivity.length ? (
                      <RuntimeActivityList activities={recentActivity} limit={6} />
                    ) : (
                      <p className="live-progress-empty">{t('当前没有可验证的运行时活动。')}</p>
                    )}
                  </section>
                </div>
                {observations.length > 0 && (
                  <div className="execution-team-observations">
                    {observations.map((member) => <MemberObservationBadge key={member.agent_name} member={member} />)}
                  </div>
                )}
                <div className="execution-evidence-boundary"><ShieldCheck size={14} />{t('实时进度只证明运行活动，不证明业务结果完成。')}</div>
              </>
            )}
          </section>
        )}

        <details className="execution-identifiers">
          <summary><Database size={14} /><span>{t('运行标识')}</span><ChevronDown size={14} /></summary>
          <div className="execution-identifier-rows">
            <div><span>{t('任务计划')}</span><code>{shortId(record.plan_id)}</code></div>
            <div><span>{t('治理记录')}</span><code>{shortId(execution?.paperclip_issue_id)}</code></div>
            <div><span>{t(execution?.kind === 'workflow' ? '工作流运行' : '执行会话')}</span><code>{shortId(execution?.workflow_run_id || execution?.aion_team_id)}</code></div>
          </div>
        </details>
      </div>

      {terminateOpen && (
        <div className="modal-layer" role="dialog" aria-modal="true" aria-label={t('终止此任务？')}>
          <button className="modal-backdrop" type="button" aria-label={t('关闭')} disabled={Boolean(controlBusy)} onClick={() => setTerminateOpen(false)} />
          <section className="mail-setup-dialog terminate-run-dialog">
            <header className="modal-header">
              <div><span className="section-kicker">{t('运行控制')}</span><h2>{t('终止此任务？')}</h2></div>
              <button className="icon-button" type="button" title={t('关闭')} disabled={Boolean(controlBusy)} onClick={() => setTerminateOpen(false)}><X size={19} /></button>
            </header>
            <div className="mail-setup-content">
              <div className="delete-plan-summary">
                <Square size={20} />
                <div><strong>{record.plan?.title || record.objective}</strong><span>{shortId(record.plan_id)}</span></div>
              </div>
              <p className="delete-plan-copy">
                {t('OpsWitness 会请求运行时停止当前 Agent 工作。已产生的部分交付物与审计证据会保留，但不会被视为业务完成。')}
              </p>
              {controlError && <InlineError text={controlError} />}
              <div className="delete-plan-actions">
                <button className="secondary-button" type="button" disabled={Boolean(controlBusy)} onClick={() => setTerminateOpen(false)}>{t('继续运行')}</button>
                <button className="secondary-button danger-button" type="button" disabled={Boolean(controlBusy)} onClick={() => void runControl('terminate')}>
                  {controlBusy === 'terminate' ? <LoaderCircle size={16} className="spin" /> : <Square size={15} />}
                  {t(controlBusy === 'terminate' ? '正在请求终止' : '确认终止')}
                </button>
              </div>
            </div>
          </section>
        </div>
      )}
      {autoModeConfirmOpen && (
        <div className="modal-layer" role="dialog" aria-modal="true" aria-label={t('打开 Auto 模式？')}>
          <button
            className="modal-backdrop"
            type="button"
            aria-label={t('关闭')}
            disabled={approvalModeBusy}
            onClick={() => setAutoModeConfirmOpen(false)}
          />
          <section className="mail-setup-dialog approval-mode-dialog">
            <header className="modal-header">
              <div><span className="section-kicker">{t('审批模式')}</span><h2>{t('打开 Auto 模式？')}</h2></div>
              <button
                className="icon-button"
                type="button"
                title={t('关闭')}
                disabled={approvalModeBusy}
                onClick={() => setAutoModeConfirmOpen(false)}
              ><X size={19} /></button>
            </header>
            <div className="mail-setup-content">
              <div className="approval-mode-confirmation-summary">
                <ShieldCheck size={20} />
                <div>
                  <strong>{t('只自动处理后续工具调用')}</strong>
                  <span>{t('每条后续审批仍会创建单次决定并写入审计记录。')}</span>
                </div>
              </div>
              <p className="delete-plan-copy">{t('当前已经暂停的审批不会被自动放行，仍需在这项工作中手动处理。方案和方案哈希都不会改变。')}</p>
              {approvalModeError && <InlineError text={approvalModeError} />}
              <div className="delete-plan-actions">
                <button
                  className="secondary-button"
                  type="button"
                  disabled={approvalModeBusy}
                  onClick={() => setAutoModeConfirmOpen(false)}
                >{t('保持手动')}</button>
                <button
                  className="primary-button"
                  type="button"
                  disabled={approvalModeBusy}
                  onClick={() => void updateApprovalMode('automatic')}
                >
                  {approvalModeBusy
                    ? <LoaderCircle size={16} className="spin" />
                    : <ShieldCheck size={16} />}
                  {t(approvalModeBusy ? '正在打开' : '确认打开 Auto')}
                </button>
              </div>
            </div>
          </section>
        </div>
      )}
    </>
  );
}

function StatusBadge({ status, label }: { status: string; label?: string }) {
  const { t } = useLanguage();
  return <span className={`status-badge ${statusTone(status)}`}><span className="status-dot" />{label || t(statusLabel[status] || status)}</span>;
}

function InlineError({ text }: { text: string }) {
  return <div className="inline-error"><AlertTriangle size={15} /><span>{text}</span></div>;
}

function LoadingState() {
  const { t } = useLanguage();
  return <div className="loading-state"><LoaderCircle size={28} className="spin" /><span>{t('正在读取本机状态')}</span></div>;
}

export default App;
