const TOOL_LABELS = {
  'mcp__aionui-team__team_task_create': '创建团队工作项',
  'mcp__aionui-team__team_task_update': '更新团队工作状态',
  'mcp__opswitness__qd_fleet_status': '读取舰队状态',
  'mcp__opswitness__qd_artifacts': '检查登记制品',
  ListMcpResourcesTool: '检查可用工具',
  ToolSearch: '查找可用工具',
};

const RUN_CONTROL_STATUSES = new Set([
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

const TERMINABLE_STATUSES = new Set([
  'running',
  'awaiting_approval',
  'awaiting_input',
  'pause_requested',
  'paused',
  'resuming',
]);

export function executionControlPresentation(status, busy = null) {
  const paused = status === 'paused';
  const running = status === 'running';
  const starting = status === 'confirmed' || status === 'dispatching';
  const resuming = status === 'resuming' || (paused && busy === 'resume');
  const pausing = status === 'pause_requested' || (running && busy === 'pause');
  const stopping = status === 'cancel_requested' || busy === 'terminate';
  const busyNow = busy !== null;

  return {
    visible: RUN_CONTROL_STATUSES.has(status),
    start: {
      enabled: paused && !busyNow,
      pending: starting || resuming,
      label: paused
        ? (resuming ? '继续中' : '继续')
        : (starting ? '启动中' : resuming ? '继续中' : '已开始'),
    },
    pause: {
      enabled: running && !busyNow,
      pending: pausing,
      label: pausing ? '暂停中' : paused ? '已暂停' : '暂停',
    },
    stop: {
      enabled: TERMINABLE_STATUSES.has(status) && !busyNow && !stopping,
      pending: stopping,
      label: stopping ? '结束中' : '结束',
    },
  };
}

export function runtimeActivitySource(activity) {
  if (activity.kind === 'response') return { label: 'Agent 已回应', values: {} };
  if (activity.tool_name && TOOL_LABELS[activity.tool_name]) {
    return { label: TOOL_LABELS[activity.tool_name], values: {} };
  }
  if (activity.tool_name) {
    return { label: '使用工具：{tool}', values: { tool: activity.tool_name } };
  }
  return { label: '运行工具调用', values: {} };
}

export function runtimeActivityTone(status) {
  if (status === 'failed') return 'danger';
  if (status === 'running') return 'active';
  return 'neutral';
}

export function stageProgressPresentation(status, workStatus) {
  if (status === 'running') {
    if (workStatus === 'awaiting_input') return { label: '等待你的信息', tone: 'attention' };
    if (workStatus === 'awaiting_approval') return { label: '等待审批', tone: 'attention' };
    return { label: '进行中', tone: 'active' };
  }
  if (status === 'blocked') return { label: '等待前置步骤', tone: 'attention' };
  if (status === 'completed') return { label: 'Agent 已上报完成', tone: 'success' };
  if (status === 'failed') return { label: '失败', tone: 'danger' };
  if (status === 'pending') return { label: '待开始', tone: 'neutral' };
  if (status === 'unknown') return { label: '状态不明确', tone: 'danger' };
  return { label: '未观测', tone: 'neutral' };
}

export function stageProgressSummary(stages) {
  const observed = stages.filter((stage) => stage.source === 'aion_team_task');
  const completed = observed.filter((stage) => stage.status === 'completed').length;
  const active = observed.find((stage) => ['running', 'blocked'].includes(stage.status)) || null;
  return {
    observed: observed.length > 0,
    observedCount: observed.length,
    completed,
    total: stages.length,
    activeOrder: active?.stage_order ?? null,
  };
}

export function formatExecutionElapsed(seconds, language = 'en') {
  if (!Number.isFinite(seconds) || seconds < 0) return '—';
  const total = Math.floor(seconds);
  if (total < 60) return language === 'zh' ? `${total} 秒` : `${total}s`;
  const minutes = Math.floor(total / 60);
  if (minutes < 60) return language === 'zh' ? `${minutes} 分钟` : `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  if (!remainder) return language === 'zh' ? `${hours} 小时` : `${hours}h`;
  return language === 'zh'
    ? `${hours} 小时 ${remainder} 分钟`
    : `${hours}h ${remainder}m`;
}

export function onboardingRunProgress({
  workStatus,
  plannedStages = [],
  progress = null,
  startedAt = null,
  estimateMinutes = 0,
  nowMs = Date.now(),
}) {
  const progressByOrder = new Map(
    (progress?.stages || []).map((stage) => [stage.stage_order, stage]),
  );
  const stages = plannedStages.map((stage) => {
    const runtime = progressByOrder.get(stage.order);
    const observed = runtime?.source === 'aion_team_task';
    const status = observed ? runtime.status : 'not_started';
    return {
      order: stage.order,
      status,
      observed,
      tone: stageProgressPresentation(status, workStatus).tone,
      agentName: observed ? runtime.agent_name : stage.owner,
    };
  });
  const completed = stages.filter((stage) => stage.status === 'completed').length;
  const running = stages.find((stage) => stage.status === 'running');
  const next = stages.find((stage) => stage.status !== 'completed');
  const parsedStartedAt = typeof startedAt === 'string' ? Date.parse(startedAt) : Number.NaN;
  const elapsedSeconds = Number.isFinite(parsedStartedAt)
    ? Math.max(0, Math.floor((nowMs - parsedStartedAt) / 1000))
    : null;
  const normalizedEstimate = Number.isFinite(estimateMinutes) && estimateMinutes > 0
    ? estimateMinutes
    : null;

  return {
    available: progress?.available === true,
    observed: stages.some((stage) => stage.observed),
    stages,
    completed,
    total: stages.length,
    currentOrder: running?.order ?? next?.order ?? stages.at(-1)?.order ?? null,
    elapsedSeconds,
    estimateMinutes: normalizedEstimate,
    estimateExceeded: elapsedSeconds !== null
      && normalizedEstimate !== null
      && elapsedSeconds > normalizedEstimate * 60,
    slow: (progress?.active_members || []).some((member) => member.slow),
  };
}
