/** Deterministic selection and polling rules for the combined Work view. */
const ACTIVE_WORK_STATUSES = new Set([
  'planning',
  'confirmed',
  'dispatching',
  'running',
  'awaiting_approval',
  'awaiting_input',
  'pause_requested',
  'resuming',
  'cancel_requested',
]);

export function latestWorkItems(plans) {
  const retained = plans.filter((record) => !record.erased_at);
  const byPlanId = new Map(plans.map((record) => [record.plan_id, record]));
  return retained.filter((record) => !retained.some((candidate) => {
    const seen = new Set();
    let parentPlanId = candidate.parent_plan_id || null;
    while (parentPlanId && !seen.has(parentPlanId)) {
      if (parentPlanId === record.plan_id) return true;
      seen.add(parentPlanId);
      parentPlanId = byPlanId.get(parentPlanId)?.parent_plan_id || null;
    }
    return false;
  }));
}

export function currentWorkItem(plans, focusedPlanId) {
  const items = latestWorkItems(plans);
  return items.find((record) => record.plan_id === focusedPlanId) || items[0] || null;
}

export function workRunHistory(record, taskRuns) {
  if (!record) return [];
  const byPlanId = new Map(taskRuns.map((run) => [run.plan_id, run]));
  const rows = [];
  const seen = new Set();
  let planId = record.plan_id;
  let parentPlanId = record.parent_plan_id || null;
  while (planId && !seen.has(planId)) {
    seen.add(planId);
    const run = byPlanId.get(planId);
    if (run && !run.deleted) rows.push(run);
    const nextParent = run?.parent_plan_id ?? parentPlanId;
    planId = nextParent || '';
    parentPlanId = null;
  }
  return rows;
}

export function shouldPollWork(view, record) {
  return view === 'work' && Boolean(record && ACTIVE_WORK_STATUSES.has(record.status));
}
