import type {
  ApprovalCard,
  ExecutionProgress,
  RuntimeActivity,
  StageProgress,
} from './types';

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
export function onboardingApprovalOrder(
  approval: Pick<ApprovalCard, 'title' | 'summary'> | null | undefined,
): 1 | 2 | null;

export type OnboardingRunStage = {
  order: number;
  status: StageProgress['status'];
  observed: boolean;
  tone: 'active' | 'attention' | 'success' | 'danger' | 'neutral';
  agentName: string;
};

export function onboardingRunProgress(input: {
  workStatus: string;
  plannedStages?: Array<{ order: number; owner: string }>;
  progress?: ExecutionProgress | null;
  startedAt?: string | null;
  estimateMinutes?: number;
  nowMs?: number;
}): {
  available: boolean;
  observed: boolean;
  stages: OnboardingRunStage[];
  completed: number;
  total: number;
  currentOrder: number | null;
  elapsedSeconds: number | null;
  estimateMinutes: number | null;
  estimateExceeded: boolean;
  slow: boolean;
};
