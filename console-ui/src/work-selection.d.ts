import type { PlanRecord, TaskRunHistory } from './types';

export function latestWorkItems(plans: PlanRecord[]): PlanRecord[];
export function currentWorkItem(
  plans: PlanRecord[],
  focusedPlanId: string,
): PlanRecord | null;
export function workRunHistory(
  record: PlanRecord | null | undefined,
  taskRuns: TaskRunHistory[],
): TaskRunHistory[];
export function shouldPollWork(view: string, record: PlanRecord | null): boolean;
