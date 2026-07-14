export type IntegrationStatus = 'online' | 'offline' | 'setup' | 'attention';

export type Integration = {
  status: IntegrationStatus;
  label: string;
  detail?: string;
  url?: string;
  privacy?: string;
};

export type AIProvider = Integration & {
  provider: 'openai' | 'anthropic';
  installed: boolean;
  authenticated: boolean;
  auth_mode: 'none' | 'unknown' | 'chatgpt' | 'api_key' | 'account' | 'console';
  runtime_ready: boolean;
};

export type ApprovalCard = {
  approval_id: string;
  status: 'pending';
  kind: 'tool_call' | 'governance';
  title: string;
  summary: string;
  recommended_action: string;
  tool_name?: string | null;
  tool_input?: string | null;
  risks: string[];
  expires_at?: string | null;
  requested_at?: string | null;
  can_decide: boolean;
};

export type PlannedAgent = {
  name: string;
  role: 'lead' | 'researcher' | 'operator' | 'reviewer' | 'reporter' | 'specialist';
  responsibility: string;
  runtime: 'claude_code' | 'codex_cli' | 'aion_cli';
  reports_to?: string | null;
};

export type ReportingLine = {
  employee: string;
  reports_to: string | null;
};

export type TaskPlan = {
  schema_version: 1;
  title: string;
  summary: string;
  execution_mode: 'aion_team' | 'workflow';
  workflow_id: string | null;
  agents: PlannedAgent[];
  stages: Array<{
    order: number;
    title: string;
    owner: string;
    outcome: string;
    checkpoint: boolean;
  }>;
  cadence: {
    kind: 'once' | 'daily' | 'weekdays' | 'weekly' | 'manual';
    timezone: string;
    local_time: string | null;
    update_interval: string;
  };
  tools: string[];
  approvals: string[];
  artifacts: string[];
  risks: string[];
  estimated_duration_minutes: number;
  update_policy: string;
};

export type ExecutionState = {
  kind: 'aion_team' | 'workflow';
  status: 'dispatching' | 'queued' | 'running' | 'awaiting_approval' | 'completed_unverified' | 'failed';
  paperclip_issue_id?: string | null;
  aion_team_id?: string | null;
  aion_team_run_id?: string | null;
  aion_conversation_ids: string[];
  workflow_run_id?: string | null;
  error?: string | null;
  dispatched_at?: string | null;
  finished_at?: string | null;
  outcome_verified: boolean;
};

export type PlanRecord = {
  schema_version: 1;
  plan_id: string;
  status:
    | 'planning'
    | 'ready'
    | 'confirmed'
    | 'dispatching'
    | 'running'
    | 'awaiting_approval'
    | 'completed_unverified'
    | 'failed';
  objective: string;
  constraints: string;
  workspace: string;
  preferred_cadence: string;
  created_at: string;
  updated_at: string;
  confirmed_at?: string | null;
  planning_progress?: {
    schema_version: 1;
    phase:
      | 'queued'
      | 'preparing'
      | 'generating_plan'
      | 'validating'
      | 'repairing'
      | 'cleaning_up'
      | 'complete'
      | 'failed';
    percent: number;
    started_at: string;
    expected_seconds: number;
    timeout_seconds: number;
  } | null;
  plan?: TaskPlan | null;
  plan_sha256?: string | null;
  parent_plan_id?: string | null;
  parent_plan_sha256?: string | null;
  revision_number: number;
  revision_instruction: string;
  revision_instruction_sha256?: string | null;
  error?: string | null;
  execution?: ExecutionState | null;
};

export type RunRecord = {
  run_id: string;
  job: string;
  started_ts?: string | null;
  finished_ts?: string | null;
  status: string;
  exit_code?: number | null;
  duration_s?: number | null;
  degraded?: number;
};

export type Workflow = {
  workflow_id: string;
  title: string;
  description: string;
  ready: boolean;
};

export type Bootstrap = {
  csrf_token: string;
  generated_at: string;
  integrations: Record<string, Integration>;
  providers: Record<'openai' | 'anthropic', AIProvider>;
  system: Record<'ai' | 'governance' | 'evidence', Integration>;
  fleet: {
    runs: number;
    artifacts: number;
    pending_projection: number;
    jobs: number;
    monitored_jobs: number;
    healthy_jobs: number;
    problem_jobs: number;
    missed_jobs: number;
    coverage_status: 'full' | 'partial' | 'none';
    coverage_error?: string | null;
    fleet_healthy: boolean;
  };
  pending_approvals: number | null;
  approvals_available: boolean;
  approvals: ApprovalCard[];
  workflows: Workflow[];
  plans: PlanRecord[];
  recent_runs: RunRecord[];
  mail_ready: boolean;
};

export type ProviderConnectionJob = {
  job_id: string;
  provider: 'openai' | 'anthropic';
  status: 'running' | 'ready' | 'failed';
  created_at: string;
  updated_at: string;
  error?: string | null;
};

export type MailSummaryJob = {
  job_id: string;
  status: 'running' | 'ready' | 'failed';
  created_at: string;
  updated_at: string;
  summary?: string | null;
  message_count: number;
  error?: string | null;
};

export type MailAuthorizationStatus = {
  enabled: boolean;
  available: boolean;
  authenticated: boolean;
  oauth_client_ready: boolean;
  oauth_client_issue: 'missing' | 'unsafe_permissions' | 'invalid' | null;
  model_metadata_consent: boolean;
  ready: boolean;
  oauth_scope: 'gmail.readonly';
  metadata_fields: Array<'from' | 'subject' | 'date' | 'message_id'>;
  privacy: 'metadata_only';
};

export type MailAuthorizationJob = {
  job_id: string;
  status: 'running' | 'ready' | 'failed';
  created_at: string;
  updated_at: string;
  error?: string | null;
};

export type TelegramSetupStatus = {
  configured: boolean;
  environment_controlled: boolean;
};
