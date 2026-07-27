export type RecoveryAction =
  | 'refresh_status'
  | 'resume_same_run'
  | 'create_repair_work'
  | 'request_operator';

export type RecoveryStateName =
  | 'idle'
  | 'observing'
  | 'diagnosing'
  | 'proposal_ready'
  | 'auto_recovering'
  | 'verifying'
  | 'recovered'
  | 'failed'
  | 'escalated';

export type RecoveryStateLike = {
  state: RecoveryStateName;
  attempt_count?: number;
  diagnosis_summary?: string | null;
  recommended_action?: RecoveryAction | null;
  rationale_codes?: string[];
  last_observed_at?: string | null;
  stalled_since?: string | null;
  action_started_at?: string | null;
  action_completed_at?: string | null;
  verification_deadline?: string | null;
  repair_work_id?: string | null;
  cooldown_until?: string | null;
  [key: string]: unknown;
};

export type RecoveryActionPolicy = {
  action: RecoveryAction;
  label: string;
  detail: string;
  autoAllowed: boolean;
  operatorActionRequired: boolean;
  operatorApprovalRequired: boolean;
};

export type RecoverySafeView = {
  state: RecoveryStateName;
  label: string;
  detail: string;
  tone: 'neutral' | 'active' | 'attention' | 'success' | 'danger';
  diagnosisSummary: string;
  action: RecoveryActionPolicy | null;
  reasons: Array<{ code: string; label: string }>;
  attemptCount: number;
  attemptsRemaining: number;
  repairWorkCreated: boolean;
  lastObservedAt: string | null;
  stalledSince: string | null;
  actionStartedAt: string | null;
  actionCompletedAt: string | null;
  verificationDeadline: string | null;
  lastError: string;
  cooldownRemainingSeconds: number;
  canCheckAgain: boolean;
  timeline: Array<{
    key: string;
    label: string;
    status: 'completed' | 'current' | 'pending';
  }>;
};

export function recoveryActionPolicy(action?: string | null): RecoveryActionPolicy | null;
export function recoveryTimeline(state: RecoveryStateName): RecoverySafeView['timeline'];
export function recoverySafeView(
  recovery: RecoveryStateLike | null | undefined,
  nowMs?: number,
): RecoverySafeView | null;
export function shouldShowRecoveryPanel(
  workStatus: string,
  recovery: RecoveryStateLike | null | undefined,
): boolean;
export function recoveryIdleCopy(workStatus: string): string;
export function formatRecoveryCooldown(seconds: number, language?: string): string;
