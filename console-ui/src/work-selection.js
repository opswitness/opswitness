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
  return plans.filter(
    (record) => !plans.some((child) => child.parent_plan_id === record.plan_id),
  );
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
    if (run) rows.push(run);
    const nextParent = run?.parent_plan_id ?? parentPlanId;
    planId = nextParent || '';
    parentPlanId = null;
  }
  return rows;
}

export function shouldPollWork(view, record) {
  return view === 'work' && Boolean(record && ACTIVE_WORK_STATUSES.has(record.status));
}
