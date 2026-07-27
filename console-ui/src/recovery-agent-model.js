const AUTO_ALLOWED_ACTIONS = new Set(['refresh_status', 'resume_same_run']);

const ACTION_PRESENTATIONS = {
  refresh_status: {
    label: '重新核对运行状态',
    detail: '重新同步受限运行状态，并可能登记该 Work 已生成的证据；不会授权新的文件写入或命令。',
  },
  resume_same_run: {
    label: '继续同一个 Work 的已绑定运行',
    detail: '只在 Work、团队和账本关联完全匹配且远端已暂停时继续，不创建重复 Work。',
  },
  create_repair_work: {
    label: '修复 Work 建议（尚未创建）',
    detail: '这只是一个需要人工确认的新修复方案，不会直接修改文件或运行命令。',
  },
  request_operator: {
    label: '请人工处理',
    detail: '现有证据不足，OpsWitness 不会猜测或扩大权限。',
  },
};

const STATE_PRESENTATIONS = {
  idle: {
    label: '运行监测中',
    detail: '当前没有触发恢复流程。',
    tone: 'neutral',
  },
  observing: {
    label: '正在确认是否卡住',
    detail: '正在比较可验证的运行状态；短暂无活动不会被直接判定为故障。',
    tone: 'active',
  },
  diagnosing: {
    label: '正在生成诊断建议',
    detail: '模型只接收受限状态，不会读取日志正文、文件内容或隐藏推理。',
    tone: 'active',
  },
  proposal_ready: {
    label: '恢复建议待处理',
    detail: '诊断建议已生成；需要人工批准的动作不会自动执行。',
    tone: 'attention',
  },
  auto_recovering: {
    label: '正在执行安全恢复',
    detail: '只会执行允许的状态刷新，或继续同一个 Work 的已绑定运行。',
    tone: 'active',
  },
  verifying: {
    label: '正在确认运行是否恢复',
    detail: '正在等待新的可验证进展，不会把进程活动当成业务完成。',
    tone: 'active',
  },
  recovered: {
    label: '运行已恢复',
    detail: '已看到新的可验证运行进展；业务结果仍需证据复核，经验候选仍需人工批准。',
    tone: 'success',
  },
  failed: {
    label: '本次恢复没有成功',
    detail: '现有证据仍不足或安全恢复失败；不会继续无限重试。',
    tone: 'danger',
  },
  escalated: {
    label: '需要你的决定',
    detail: '下一步超出自动恢复范围，OpsWitness 已停止并等待人工处理。',
    tone: 'attention',
  },
};

const RATIONALE_LABELS = {
  unchanged_progress: '可验证状态长时间没有变化',
  runtime_unreachable: '暂时无法读取运行时',
  remote_run_paused: '已绑定的远端运行处于暂停状态',
  operator_approval_required: '下一步需要人工批准',
  operator_input_required: '任务正在等待你补充信息',
  identity_unverified: '无法确认是同一次运行',
  insufficient_evidence: '现有证据不足以安全恢复',
};

const ERROR_LABELS = {
  model_unavailable: '诊断模型暂时不可用；运行保持原状。',
  identity_changed: '运行身份已变化；为避免重复执行，自动恢复已停止。',
  action_not_auto_allowed: '建议动作超出自动恢复范围，正在等待人工处理。',
  action_unconfirmed: '自动恢复动作没有得到新的可验证确认；运行保持未恢复。',
  attempt_limit_reached: '已达到两次恢复上限，不会继续自动重试。',
};

const STATE_STEP_INDEX = {
  idle: 0,
  observing: 0,
  diagnosing: 1,
  proposal_ready: 2,
  auto_recovering: 2,
  verifying: 3,
  recovered: 4,
  failed: 3,
  escalated: 2,
};

export function recoveryActionPolicy(action) {
  if (!action || !ACTION_PRESENTATIONS[action]) return null;
  return {
    action,
    ...ACTION_PRESENTATIONS[action],
    autoAllowed: AUTO_ALLOWED_ACTIONS.has(action),
    operatorActionRequired: !AUTO_ALLOWED_ACTIONS.has(action),
    operatorApprovalRequired: action === 'create_repair_work',
  };
}

export function recoveryTimeline(state) {
  const currentIndex = STATE_STEP_INDEX[state] ?? 0;
  const terminal = state === 'recovered';
  const steps = [
    { key: 'observe', label: '确认停滞' },
    { key: 'diagnose', label: '受限诊断' },
    { key: 'act', label: '安全恢复' },
    { key: 'verify', label: '核对新进展' },
  ];
  return steps.map((step, index) => ({
    ...step,
    status: terminal || index < currentIndex
      ? 'completed'
      : index === currentIndex
        ? 'current'
        : 'pending',
  }));
}

export function recoverySafeView(recovery, nowMs = Date.now()) {
  if (!recovery || typeof recovery !== 'object') return null;
  const repairWorkCreated = typeof recovery.repair_work_id === 'string'
    && recovery.repair_work_id.length > 0;
  const presentation = repairWorkCreated
    ? {
        label: '待审核 Repair Work 已创建',
        detail: '新 Work 仍需审阅和确认；尚未执行任何修复。',
        tone: 'attention',
      }
    : STATE_PRESENTATIONS[recovery.state] || STATE_PRESENTATIONS.idle;
  const action = recoveryActionPolicy(recovery.recommended_action);
  const cooldownMs = typeof recovery.cooldown_until === 'string'
    ? Date.parse(recovery.cooldown_until)
    : Number.NaN;
  const cooldownRemainingSeconds = Number.isFinite(cooldownMs)
    ? Math.max(0, Math.ceil((cooldownMs - nowMs) / 1000))
    : 0;
  const attemptCount = Number.isInteger(recovery.attempt_count)
    ? Math.min(2, Math.max(0, recovery.attempt_count))
    : 0;
  const reasons = Array.isArray(recovery.rationale_codes)
    ? recovery.rationale_codes
      .filter((code) => typeof code === 'string' && RATIONALE_LABELS[code])
      .slice(0, 4)
      .map((code) => ({ code, label: RATIONALE_LABELS[code] }))
    : [];

  return {
    state: typeof recovery.state === 'string' ? recovery.state : 'idle',
    label: presentation.label,
    detail: presentation.detail,
    tone: presentation.tone,
    diagnosisSummary: typeof recovery.diagnosis_summary === 'string'
      ? recovery.diagnosis_summary
      : '',
    action,
    reasons,
    attemptCount,
    attemptsRemaining: Math.max(0, 2 - attemptCount),
    repairWorkCreated,
    lastObservedAt: typeof recovery.last_observed_at === 'string'
      ? recovery.last_observed_at
      : null,
    stalledSince: typeof recovery.stalled_since === 'string'
      ? recovery.stalled_since
      : null,
    actionStartedAt: typeof recovery.action_started_at === 'string'
      ? recovery.action_started_at
      : null,
    actionCompletedAt: typeof recovery.action_completed_at === 'string'
      ? recovery.action_completed_at
      : null,
    verificationDeadline: typeof recovery.verification_deadline === 'string'
      ? recovery.verification_deadline
      : null,
    lastError: typeof recovery.last_error_code === 'string'
      ? ERROR_LABELS[recovery.last_error_code] || ''
      : '',
    cooldownRemainingSeconds,
    canCheckAgain: recovery.state === 'failed'
      && attemptCount < 2
      && cooldownRemainingSeconds === 0,
    timeline: recoveryTimeline(recovery.state),
  };
}

export function shouldShowRecoveryPanel(workStatus, recovery) {
  if (!recovery || typeof recovery !== 'object') return false;
  if (!['idle', 'observing'].includes(recovery.state)) return true;
  return [
    'running',
    'awaiting_approval',
    'awaiting_input',
    'pause_requested',
    'paused',
    'resuming',
  ].includes(workStatus);
}

export function recoveryIdleCopy(workStatus) {
  if (workStatus === 'awaiting_approval') {
    return '正在等你审批，不视为卡住，也不会自动诊断。';
  }
  if (workStatus === 'awaiting_input') {
    return '正在等你补充信息，不视为卡住，也不会自动诊断。';
  }
  if (workStatus === 'paused') {
    return 'Work 已暂停，不会自动诊断或自行继续。';
  }
  if (workStatus === 'running') {
    return '若 3 分钟没有新的可验证进展，将开始受限诊断；最多尝试 2 次。';
  }
  return '正在守护可验证运行状态；当前不会启动诊断。';
}

export function formatRecoveryCooldown(seconds, language = 'en') {
  if (!Number.isFinite(seconds) || seconds <= 0) return '';
  const rounded = Math.ceil(seconds);
  if (rounded < 60) return language === 'zh' ? `${rounded} 秒` : `${rounded}s`;
  const minutes = Math.ceil(rounded / 60);
  return language === 'zh' ? `${minutes} 分钟` : `${minutes}m`;
}
