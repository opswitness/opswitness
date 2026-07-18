import type { RuntimeActivity, StageProgress } from './types';

export type ExecutionControlAction = 'pause' | 'resume' | 'terminate';
export type ExecutionControlButton = {
  enabled: boolean;
  pending: boolean;
  label: string;
};

export function executionControlPresentation(
  status: string,
  busy?: ExecutionControlAction | null,
): {
  visible: boolean;
  start: ExecutionControlButton;
  pause: ExecutionControlButton;
  stop: ExecutionControlButton;
};

export function runtimeActivitySource(
  activity: RuntimeActivity,
): { label: string; values: Record<string, string> };
export function runtimeActivityTone(
  status: RuntimeActivity['status'],
): 'active' | 'neutral' | 'danger';
export function stageProgressPresentation(
  status: StageProgress['status'],
  workStatus: string,
): {
  label: string;
  tone: 'active' | 'attention' | 'success' | 'danger' | 'neutral';
};
export function stageProgressSummary(stages: StageProgress[]): {
  observed: boolean;
  observedCount: number;
  completed: number;
  total: number;
  activeOrder: number | null;
};
export function formatExecutionElapsed(seconds: number, language?: 'en' | 'zh'): string;
