import type { AgentContract, TaskPlan } from './types';

export type AgentGraphDraftAgent = {
  key: string;
  name: string;
  role: TaskPlan['agents'][number]['role'];
  responsibility: string;
  runtime: TaskPlan['agents'][number]['runtime'];
  model: string;
  model_binding: 'exact' | 'alias' | 'default';
  runtime_binding: {
    adapter_version: string;
    executable_sha256?: string | null;
    status: 'bound' | 'alias' | 'default' | 'unverified';
  };
  runtime_reason: string;
  reports_to_key: string | null;
  contract: AgentContract;
};

export type AgentGraphDraft = {
  schema_version: 2;
  runtime_mode: 'aion_compatible' | 'strict';
  agents: AgentGraphDraftAgent[];
  loops: Array<{
    source_key: string;
    target_key: string;
    condition: string;
    max_iterations: number;
  }>;
  stages: Array<{
    order: number;
    title: string;
    outcome: string;
    checkpoint: boolean;
    owner_key: string;
  }>;
};

export type AgentGraphRevisionPayload = {
  expected_plan_sha256: string;
  agents: TaskPlan['agents'];
  collaboration_loops: TaskPlan['collaboration_loops'];
  stage_assignments: Array<{ stage_order: number; owner: string }>;
  confirmed: true;
};

export function createAgentGraphDraft(plan: TaskPlan): AgentGraphDraft;
export function validateAgentGraphDraft(draft: AgentGraphDraft): string[];
export function agentGraphFingerprint(draft: AgentGraphDraft): string;
export function agentGraphRevisionRequest(
  draft: AgentGraphDraft,
  expectedPlanSha256: string,
): AgentGraphRevisionPayload;
export function agentContractPlanDraft(
  draft: AgentGraphDraft,
  plan: TaskPlan,
): Record<string, unknown>;
export function layoutAgentGraph(draft: AgentGraphDraft): {
  width: number;
  height: number;
  positions: Array<{
    key: string;
    x: number;
    y: number;
    width: number;
    height: number;
  }>;
};
