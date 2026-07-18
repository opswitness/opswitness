export function homeActionView(
  target: 'approvals' | 'tasks' | 'team' | 'history' | 'connections' | 'workspace',
): 'approvals' | 'work' | 'settings' | 'workspace';

export function observationPresentation(
  state: 'activity_observed' | 'response_observed' | 'unobserved' | 'unavailable',
  language?: 'en' | 'zh',
): { label: string; tone: 'active' | 'neutral' | 'danger' };

export function canSaveRuntimeRevision(
  agents: Array<{ name: string; runtime: string; model?: string | null }>,
  capabilities: Array<{
    runtime: string;
    available: boolean;
    default_model?: string;
    models?: Array<{ id: string }>;
  }>,
  assignments: Record<string, { runtime: string; model: string }>,
): boolean;

export function selectedBlueprintId(blueprint: { blueprint_id?: string } | null | undefined): string | null;

export function taskAdjustmentExamples(language?: 'en' | 'zh'): Array<{ label: string; instruction: string }>;
