/** Small deterministic UI rules shared by the console and its Node test. */
export function homeActionView(target) {
  if (target === 'today') return 'workspace';
  if (target === 'connections' || target === 'history') return 'settings';
  if (target === 'tasks' || target === 'team') return 'work';
  return target;
}

export function observationPresentation(state, language = 'en') {
  const labels = language === 'zh' ? {
    activity_observed: '活动已观测',
    response_observed: '已有回应',
    unobserved: '未观测',
    unavailable: '状态不可用',
  } : {
    activity_observed: 'Activity observed',
    response_observed: 'Response observed',
    unobserved: 'Not observed',
    unavailable: 'Status unavailable',
  };
  const tone = state === 'unavailable' ? 'danger' : state === 'unobserved' ? 'neutral' : 'active';
  return { label: labels[state] || labels.unavailable, tone };
}

export function canSaveRuntimeRevision(agents, capabilities, assignments) {
  const selected = (agent) => assignments[agent.name] || {
    runtime: agent.runtime,
    model: agent.model || 'default',
  };
  const changed = agents.some((agent) => {
    const assignment = selected(agent);
    return assignment.runtime !== agent.runtime
      || assignment.model !== (agent.model || 'default');
  });
  const selectedAvailable = agents.every((agent) => {
    const assignment = selected(agent);
    const capability = capabilities.find((item) => (
      item.runtime === assignment.runtime && item.available
    ));
    if (!capability) return false;
    const models = Array.isArray(capability.models) && capability.models.length
      ? capability.models
      : [{ id: capability.default_model || 'default' }];
    return models.some((model) => model.id === assignment.model);
  });
  return changed && selectedAvailable;
}

export function selectedBlueprintId(blueprint) {
  return blueprint && typeof blueprint.blueprint_id === 'string' ? blueprint.blueprint_id : null;
}

/** Preset language for the task-scoped AI adjustment chat. Selecting one only drafts text. */
export function taskAdjustmentExamples(language = 'en') {
  return language === 'zh' ? [
    {
      label: '调整循环协作',
      instruction: '调整协作循环：引用核验未通过时，返回给解读 Agent 重新处理，最多两轮；其余安排保持不变。',
    },
    {
      label: '调整团队分工',
      instruction: '调整团队分工：明确每位 Agent 的职责和汇报关系，保留现有交付物与审批检查点。',
    },
    {
      label: '调整更新节奏',
      instruction: '调整更新节奏和汇报频率，保留现有团队结构、约束与审批要求。',
    },
  ] : [
    {
      label: 'Adjust collaboration loops',
      instruction: 'Adjust the collaboration loop: when citation verification fails, return the work to the interpretation agent for revision, for at most two rounds; keep all other assignments unchanged.',
    },
    {
      label: 'Adjust team assignments',
      instruction: 'Adjust team assignments: clarify each agent responsibility and reporting line while preserving the current deliverables and approval checkpoints.',
    },
    {
      label: 'Adjust update cadence',
      instruction: 'Adjust the update cadence and reporting frequency while preserving the current team structure, constraints, and approval requirements.',
    },
  ];
}
