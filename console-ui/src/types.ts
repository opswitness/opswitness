export type IntegrationStatus = 'online' | 'offline' | 'setup' | 'attention';
export type AIProviderName =
  | 'openai'
  | 'anthropic'
  | 'deepseek'
  | 'xai'
  | 'ollama'
  | 'lmstudio';

export type Integration = {
  status: IntegrationStatus;
  label: string;
  detail?: string;
  url?: string;
  privacy?: string;
};

export type AIProvider = Integration & {
  provider: AIProviderName;
  installed: boolean;
  authenticated: boolean;
  auth_mode: 'none' | 'unknown' | 'chatgpt' | 'api_key' | 'account' | 'console' | 'local';
  runtime_ready: boolean;
  server_online?: boolean;
  adapter_registered?: boolean;
  model_count?: number;
  models?: string[];
};

export type ApprovalCard = {
  approval_id: string;
  plan_id?: string | null;
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

export type ApprovalMode = 'automatic' | 'automatic_safe' | 'manual_all';
export type ExecutionProfile = 'fast' | 'balanced' | 'deep' | 'custom';

export type PlannedAgent = {
  name: string;
  role: 'lead' | 'researcher' | 'operator' | 'reviewer' | 'reporter' | 'specialist';
  responsibility: string;
  runtime: 'claude_code' | 'codex_cli' | 'aion_cli';
  model?: string | null;
  runtime_reason: string;
  reports_to?: string | null;
};

export type ReportingLine = {
  employee: string;
  reports_to: string | null;
};

export type CollaborationLoop = {
  source_agent: string;
  target_agent: string;
  condition: string;
  max_iterations: number;
};

export type TaskPlan = {
  schema_version: 1;
  title: string;
  summary: string;
  execution_profile?: ExecutionProfile | null;
  execution_mode: 'aion_team' | 'workflow';
  workflow_id: string | null;
  agents: PlannedAgent[];
  collaboration_loops: CollaborationLoop[];
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

export type ActiveMemberProgress = {
  agent_name: string;
  state: 'queued' | 'running' | 'blocked';
  started_at?: string | null;
  elapsed_seconds?: number | null;
  slow: boolean;
};

export type RuntimeActivity = {
  activity_id: string;
  agent_name: string;
  kind: 'tool_call' | 'response';
  status: 'running' | 'completed' | 'failed' | 'observed';
  tool_name?: string | null;
  observed_at: string;
  count: number;
};

export type StageProgress = {
  stage_order: number;
  agent_name: string;
  status: 'not_started' | 'pending' | 'running' | 'blocked' | 'completed' | 'failed' | 'unknown';
  source: 'aion_team_task' | 'unobserved';
  task_id?: string | null;
  blocked_by: number[];
  started_at?: string | null;
  updated_at?: string | null;
  completed_at?: string | null;
  recent_activity: RuntimeActivity[];
};

export type ExecutionProgress = {
  available: boolean;
  observed_at: string;
  stage_history_recovered: boolean;
  stage_mapping_version: number;
  active_members: ActiveMemberProgress[];
  recent_activity: RuntimeActivity[];
  stages: StageProgress[];
};

export type RuntimeInputRequest = {
  request_id: string;
  agent_name: string;
  question: string;
  choices: string[];
  question_sha256: string;
  requested_at: string;
  status: 'pending' | 'answered';
  answered_at?: string | null;
  answer_sha256?: string | null;
};

export type RuntimeInputArtifact = {
  name: string;
  relative_path: string;
  available: boolean;
  sha256?: string | null;
  size?: number | null;
  mime?: string | null;
  preview_supported: boolean;
  artifact_type?: string | null;
  status?: string | null;
  item_count?: number | null;
};

export type RuntimeInputArtifactPreview = RuntimeInputArtifact & {
  content: unknown;
};

export type PlanArtifact = RuntimeInputArtifact & {
  evidence_status: 'workspace_unverified' | 'registered';
  event_id?: string | null;
  cas_uri?: string | null;
};

export type PlanArtifactPreview = PlanArtifact & {
  content: unknown;
};

export type PlanningAttachmentUpload = {
  name: string;
  media_type: string;
  content_base64: string;
};

export type PlanningAttachment = {
  attachment_id: string;
  storage_plan_id: string;
  name: string;
  media_type: string;
  size_bytes: number;
  sha256: string;
};

export type ExecutionState = {
  kind: 'aion_team' | 'workflow';
  status:
    | 'dispatching'
    | 'queued'
    | 'running'
    | 'awaiting_approval'
    | 'awaiting_input'
    | 'pause_requested'
    | 'paused'
    | 'resuming'
    | 'cancel_requested'
    | 'cancelled'
    | 'completed_unverified'
    | 'failed';
  approval_mode: ApprovalMode;
  paperclip_issue_id?: string | null;
  aion_team_id?: string | null;
  aion_team_run_id?: string | null;
  aion_conversation_ids: string[];
  aion_agent_sessions?: Array<{ agent_name: string; conversation_id: string }>;
  member_observations?: AgentObservation[];
  progress?: ExecutionProgress | null;
  input_requests: RuntimeInputRequest[];
  workflow_run_id?: string | null;
  error?: string | null;
  control_error?: string | null;
  control_marker?: string | null;
  control_requested_at?: string | null;
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
    | 'awaiting_input'
    | 'pause_requested'
    | 'paused'
    | 'resuming'
    | 'cancel_requested'
    | 'cancelled'
    | 'completed_unverified'
    | 'failed';
  objective: string;
  constraints: string;
  workspace: string;
  preferred_cadence: string;
  attachments?: PlanningAttachment[];
  source_blueprint_id?: string | null;
  source_blueprint_sha256?: string | null;
  memory_snapshot_sha256?: string | null;
  memory_version_ids: string[];
  created_at: string;
  updated_at: string;
  confirmed_at?: string | null;
  approval_mode?: ApprovalMode | null;
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
  forked_from_plan_id?: string | null;
  forked_from_plan_sha256?: string | null;
  continued_from_plan_id?: string | null;
  continued_from_plan_sha256?: string | null;
  continuation_message_sha256?: string | null;
  revision_number: number;
  revision_instruction: string;
  revision_instruction_sha256?: string | null;
  erased_at?: string | null;
  erasure_event_id?: string | null;
  error?: string | null;
  execution?: ExecutionState | null;
};

export type AgentObservation = {
  agent_name: string;
  state: 'activity_observed' | 'response_observed' | 'unobserved' | 'unavailable';
  observed_at?: string | null;
  source: 'adapter' | 'unavailable';
};

export type TeamBlueprint = {
  schema_version: 1;
  blueprint_id: string;
  name: string;
  created_at: string;
  archived_at?: string | null;
  source_plan_id: string;
  source_plan_sha256: string;
  verification_status: 'unverified' | 'verified';
  agents: Array<{
    key: string;
    role: PlannedAgent['role'];
    reports_to_key?: string | null;
    runtime: PlannedAgent['runtime'];
  }>;
  collaboration_loops: Array<{
    source_key: string;
    target_key: string;
    max_iterations: number;
  }>;
  blueprint_sha256: string;
};

export type TaskTemplate = {
  schema_version: 1;
  template_id: string;
  name: string;
  objective: string;
  created_at: string;
  archived_at?: string | null;
  source_plan_id?: string | null;
  source_plan_sha256?: string | null;
  template_sha256: string;
};

export type WorkspaceConversation = {
  schema_version: 1;
  conversation_id: string;
  current_plan_id: string;
  current_plan_sha256?: string | null;
  title: string;
  objective: string;
  status: PlanRecord['status'];
  version_count: number;
  created_at: string;
  updated_at: string;
  template_source_available: boolean;
};

export type RepeatableWork = {
  schema_version: 1;
  work_id: string;
  source_plan_id: string;
  source_plan_sha256: string;
  title: string;
  objective: string;
  revision_number: number;
  agent_count: number;
  cadence: TaskPlan['cadence']['kind'];
  last_status: 'failed' | 'cancelled' | 'completed_unverified';
  updated_at: string;
  outcome_verified: boolean;
};

export type WorkspaceMemoryState = 'candidate' | 'approved' | 'superseded' | 'revoked';

export type WorkspaceMemorySummary = {
  schema_version: 1;
  memory_id: string;
  version_id: string;
  version_number: number;
  kind: 'process' | 'knowledge';
  title: string;
  tags: string[];
  workspace: string;
  source_plan_id?: string | null;
  source_plan_sha256?: string | null;
  parent_version_id?: string | null;
  created_at: string;
  content_sha256: string;
  document_sha256: string;
  relative_path: string;
  state: WorkspaceMemoryState;
  active: boolean;
  decided_at?: string | null;
};

export type WorkspaceMemoryView = WorkspaceMemorySummary & {
  content: string;
};

export type WorkspaceMemoryStatus = {
  format: 'obsidian_markdown';
  candidate_count: number;
  approved_count: number;
  vault_path: string;
};

export type RuntimeCapability = {
  runtime: PlannedAgent['runtime'];
  label: string;
  available: boolean;
  reason: string;
  default_model: string;
  models: RuntimeModelOption[];
};

export type RuntimeModelOption = {
  id: string;
  label: string;
  description: string;
  pinning: 'default' | 'alias' | 'exact';
};

export type AgentRuntimeAssignment = {
  agent_name: string;
  runtime: PlannedAgent['runtime'];
  model: string;
};

export type HomeAction = {
  action_id: string;
  kind: 'approval' | 'input_required' | 'task_blocked' | 'operational' | 'running' | 'info';
  priority: number;
  title: string;
  summary: string;
  target: 'approvals' | 'tasks' | 'team' | 'history' | 'connections' | 'workspace';
  plan_id?: string | null;
};

export type HomeActiveTeam = {
  plan_id: string;
  title: string;
  status:
    | 'confirmed'
    | 'dispatching'
    | 'running'
    | 'awaiting_approval'
    | 'awaiting_input'
    | 'pause_requested'
    | 'paused'
    | 'resuming'
    | 'cancel_requested';
  updated_at: string;
  members: AgentObservation[];
};

export type HomeSummary = {
  first_use: boolean;
  has_unconfirmed_plan: boolean;
  default_view: 'workspace' | 'today';
  action_queue: HomeAction[];
  active_teams: HomeActiveTeam[];
  health: {
    fleet_healthy: boolean;
    coverage_status: 'full' | 'partial' | 'none';
    pending_projection: number;
    monitored_jobs: number;
  };
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

export type TaskRunHistory = {
  schema_version: 1;
  run_id: string;
  plan_id: string;
  title: string;
  status:
    | 'confirmed'
    | 'dispatching'
    | 'running'
    | 'awaiting_approval'
    | 'awaiting_input'
    | 'pause_requested'
    | 'paused'
    | 'resuming'
    | 'cancel_requested'
    | 'cancelled'
    | 'completed_unverified'
    | 'failed';
  execution_mode: 'aion_team' | 'workflow' | null;
  agent_count: number;
  revision_number: number;
  parent_plan_id?: string | null;
  continued_from_plan_id?: string | null;
  continuation_available: boolean;
  started_at: string;
  updated_at: string;
  finished_at?: string | null;
  duration_s?: number | null;
  outcome_verified: boolean;
  evidence_gap: boolean;
  deleted: boolean;
  events: Array<{
    event_id: string;
    kind:
      | 'task_plan_continuation_requested'
      | 'task_plan_confirmed'
      | 'task_execution_requested'
      | 'task_execution_dispatched'
      | 'task_plan_continuation_delivered'
      | 'task_execution_failed'
      | 'task_execution_finished'
      | 'task_input_requested'
      | 'task_input_answered'
      | 'task_input_delivered'
      | 'task_execution_pause_requested'
      | 'task_execution_paused'
      | 'task_execution_resume_requested'
      | 'task_execution_resumed'
      | 'task_execution_cancel_requested'
      | 'task_execution_cancelled'
      | 'task_execution_control_failed'
      | 'task_approval_mode_change_requested'
      | 'task_approval_mode_changed'
      | 'task_approval_mode_change_aborted'
      | 'task_approval_mode_change_recovered'
      | 'task_run_erased';
    ts: string;
  }>;
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
  providers: Record<AIProviderName, AIProvider>;
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
  task_runs: TaskRunHistory[];
  recent_runs: RunRecord[];
  mail_ready: boolean;
  home: HomeSummary;
  task_templates: TaskTemplate[];
  team_blueprints: TeamBlueprint[];
  repeatable_works: RepeatableWork[];
  workspace_conversations: WorkspaceConversation[];
  workspace_memories: WorkspaceMemorySummary[];
  workspace_memory: WorkspaceMemoryStatus;
  runtime_capabilities: RuntimeCapability[];
  console_access: {
    exposure: 'loopback' | 'private';
    public_url: string;
    paired: boolean;
    can_manage_devices: boolean;
  };
};

export type PairedDevice = {
  device_id: string;
  name: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
};

export type PairingInvitation = {
  invitation_id: string;
  code: string;
  expires_at: string;
  public_url: string;
};

export type ProviderConnectionJob = {
  job_id: string;
  provider: AIProviderName;
  method: 'account' | 'api' | 'api_key' | 'local';
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
