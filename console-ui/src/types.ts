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
export type ContractControl = 'deny' | 'always_ask' | 'inherit_run_mode';

export type AgentContract = {
  schema_version: 1;
  instructions: string;
  prohibitions: string[];
  inputs: Array<{
    input_id: string;
    label: string;
    relative_path?: string | null;
    source_agent_id?: string | null;
    source_output_id?: string | null;
    required: boolean;
    sha256?: string | null;
  }>;
  outputs: Array<{
    output_id: string;
    label: string;
    relative_path: string;
    media_type?: string | null;
    acceptance_criteria: string[];
    required: boolean;
  }>;
  acceptance_criteria: string[];
  default_tool_policy: ContractControl;
  tool_rules: Array<{ tool_name: string; policy: ContractControl }>;
  data_scope: {
    allowed_relative_paths: string[];
    attachment_ids: string[];
    managed_network_domains: string[];
  };
  side_effects: {
    file_write: ContractControl;
    operator_input: ContractControl;
    managed_network: ContractControl;
    send: ContractControl;
    publish: ContractControl;
    delete: 'deny' | 'always_ask';
  };
  memory: {
    mode: 'none' | 'selected';
    version_ids: string[];
  };
  handoff: {
    allowed_target_agent_ids: string[];
    acceptance_criteria: string[];
    require_cas_receipt: boolean;
  };
  escalation: {
    target_agent_id?: string | null;
    conditions: string[];
  };
  approval_checkpoints: string[];
  retry: {
    max_attempts: number;
    retryable_errors: Array<
      | 'runtime_temporarily_unavailable'
      | 'rate_limited'
      | 'network_temporarily_unavailable'
      | 'tool_temporarily_unavailable'
    >;
    backoff_seconds: number;
  };
  stop: {
    timeout_seconds: number;
    stop_conditions: string[];
    stop_on_approval_rejection: boolean;
    stop_on_contract_violation: boolean;
    stop_on_digest_mismatch: boolean;
  };
};

export type PlannedAgent = {
  agent_id?: string;
  name: string;
  role: 'lead' | 'researcher' | 'operator' | 'reviewer' | 'reporter' | 'specialist';
  responsibility: string;
  runtime: 'claude_code' | 'codex_cli' | 'aion_cli';
  model?: string | null;
  runtime_reason: string;
  reports_to?: string | null;
  reports_to_agent_id?: string | null;
  model_binding?: 'exact' | 'alias' | 'default';
  runtime_binding?: {
    adapter_version: string;
    executable_sha256?: string | null;
    status: 'bound' | 'alias' | 'default' | 'unverified';
  };
  contract?: AgentContract;
};

export type ReportingLine = {
  employee: string;
  reports_to: string | null;
};

export type CollaborationLoop = {
  source_agent?: string;
  target_agent?: string;
  source_agent_id?: string;
  target_agent_id?: string;
  condition: string;
  max_iterations: number;
};

export type TaskPlan = {
  schema_version: 1 | 2;
  title: string;
  summary: string;
  execution_profile?: ExecutionProfile | null;
  execution_mode: 'aion_team' | 'workflow';
  workflow_id: string | null;
  runtime_mode?: 'aion_compatible' | 'strict';
  agents: PlannedAgent[];
  collaboration_loops: CollaborationLoop[];
  stages: Array<{
    order: number;
    title: string;
    owner?: string;
    owner_agent_id?: string;
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

export type AgentContractDiffEntry = {
  path: string;
  change: 'added' | 'removed' | 'changed';
  direction: 'tighter' | 'looser' | 'neutral';
  before: unknown;
  after: unknown;
};

export type AgentContractPreview = {
  parent_plan_id: string;
  parent_plan_sha256: string;
  normalized_plan: TaskPlan;
  candidate_plan_sha256: string;
  contract_sha256: string;
  diff: AgentContractDiffEntry[];
  envelopes: Array<{
    agent_id: string;
    agent_name: string;
    delivery: 'exact_lead_payload' | 'exact_plan_packet' | 'strict_runtime';
    canonical_json: string;
    sha256: string;
    enforcement: Record<
      string,
      'software_enforced' | 'runtime_approval' | 'execution_instruction' | 'unsupported'
    >;
  }>;
  strict_runtime_available: boolean;
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

export type RecoveryAction =
  | 'refresh_status'
  | 'resume_same_run'
  | 'create_repair_work'
  | 'request_operator';

export type RecoveryState = {
  schema_version: 1;
  state:
    | 'idle'
    | 'observing'
    | 'diagnosing'
    | 'proposal_ready'
    | 'auto_recovering'
    | 'verifying'
    | 'recovered'
    | 'failed'
    | 'escalated';
  progress_sha256?: string | null;
  progress_changed_at?: string | null;
  last_observed_at?: string | null;
  stalled_since?: string | null;
  attempt_count: number;
  diagnosis_id?: string | null;
  diagnosis_claimed_at?: string | null;
  diagnosis_category?: string | null;
  diagnosis_summary?: string | null;
  recommended_action?: RecoveryAction | null;
  rationale_codes: string[];
  proposal_sha256?: string | null;
  diagnosed_at?: string | null;
  bound_team_id?: string | null;
  previous_team_run_id?: string | null;
  action_started_at?: string | null;
  action_completed_at?: string | null;
  repair_work_id?: string | null;
  verification_evidence_sha256?: string | null;
  verification_deadline?: string | null;
  cooldown_until?: string | null;
  last_error_code?:
    | 'model_unavailable'
    | 'identity_changed'
    | 'action_not_auto_allowed'
    | 'action_unconfirmed'
    | 'attempt_limit_reached'
    | null;
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

export type ProjectLibraryItem = {
  schema_version: 1;
  asset_id: string;
  source_kind: 'planning_input' | 'registered_output' | 'workspace_output';
  source_ref: string;
  plan_id: string;
  work_id: string;
  work_title: string;
  revision_number: number;
  name: string;
  mime: string;
  file_type: string;
  size: number;
  sha256: string;
  evidence_status: 'retained_input' | 'registered' | 'workspace_unverified';
  preview_supported: boolean;
  created_at: string;
  event_id?: string | null;
  system_tags: string[];
  user_tags: string[];
  supersedes_asset_id?: string | null;
  supersedes_status: 'none' | 'available' | 'unavailable';
  superseded_by_asset_ids: string[];
  content_url: string;
};

export type ProjectLibraryItemPreview = ProjectLibraryItem & {
  preview_kind: 'none' | 'json' | 'text';
  preview: unknown;
};

export type LibraryCollectionPolicy = {
  schema_version: 1;
  purpose: string;
  default_tags: string[];
  allowed_formats: string[];
  exclude_name_patterns: string[];
  knowledge_card_language: 'auto' | 'zh-CN' | 'en';
  generation_instructions: string;
};

export type LibraryCollection = {
  schema_version: 1;
  collection_id: string;
  name: string;
  revision: number;
  policy_version_id: string;
  policy_sha256: string;
  policy: LibraryCollectionPolicy;
  is_inbox: boolean;
  document_count: number;
  approved_card_count: number;
  created_at: string;
  updated_at: string;
};

export type LibraryImportEntry = {
  entry_id: string;
  relative_path: string;
  size_bytes: number;
  media_type: string;
  file_format: string;
  status:
    | 'pending'
    | 'uploaded'
    | 'duplicate'
    | 'new_version'
    | 'skipped'
    | 'error'
    | 'committed';
  sha256?: string | null;
  classification?: 'new' | 'duplicate' | 'new_version' | 'skipped' | null;
  reason?: string | null;
  document_version_id?: string | null;
};

export type LibraryImport = {
  schema_version: 1;
  import_id: string;
  collection_id: string;
  collection_revision: number;
  policy_version_id: string;
  policy_sha256: string;
  status: 'staging' | 'ready' | 'committing' | 'committed' | 'cancelled' | 'expired';
  entries: LibraryImportEntry[];
  files_total: number;
  files_uploaded: number;
  files_skipped: number;
  files_failed: number;
  bytes_total: number;
  bytes_uploaded: number;
  manifest_sha256?: string | null;
  created_at: string;
  updated_at: string;
  expires_at: string;
};

export type LibraryDocumentVersion = {
  schema_version: 1;
  document_id: string;
  version_id: string;
  collection_id: string;
  version_number: number;
  previous_version_id?: string | null;
  relative_path: string;
  display_name: string;
  media_type: string;
  file_format: string;
  size_bytes: number;
  sha256: string;
  blob_ref: string;
  aliases: string[];
  tags: string[];
  metadata_revision: number;
  policy_version_id: string;
  policy_sha256: string;
  extraction_status:
    | 'included'
    | 'metadata_only'
    | 'encrypted'
    | 'no_text'
    | 'extraction_failed';
  extraction_detail?: string | null;
  text_chunk_count: number;
  text_character_count: number;
  text_sha256?: string | null;
  status: 'active' | 'tombstoned';
  created_at: string;
  tombstoned_at?: string | null;
};

export type LibraryCitation = {
  schema_version: 1;
  document_version_id: string;
  document_sha256: string;
  locator_type: 'page' | 'sheet' | 'line' | 'chunk' | 'metadata';
  locator: string;
  chunk_id?: string | null;
  excerpt: string;
  excerpt_sha256: string;
};

export type KnowledgeCardVersion = {
  schema_version: 1;
  card_id: string;
  version_id: string;
  collection_id: string;
  source_document_version_ids: string[];
  title: string;
  summary: string;
  key_points: Array<{ statement: string; citations: LibraryCitation[] }>;
  suggested_tags: string[];
  coverage_scope: string;
  coverage: 'complete' | 'partial' | 'metadata_only';
  state: 'candidate' | 'approved' | 'superseded' | 'dismissed' | 'revoked';
  card_sha256: string;
  source_manifest_sha256: string;
  policy_sha256: string;
  provider: 'openai' | 'anthropic';
  model: string;
  generator_version: string;
  created_at: string;
  decided_at?: string | null;
};

export type LibraryCardJob = {
  schema_version: 1;
  job_id: string;
  collection_id: string;
  document_version_ids: string[];
  provider: 'openai' | 'anthropic';
  model: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  files_total: number;
  files_processed: number;
  card_version_ids: string[];
  error_code?: string | null;
  created_at: string;
  updated_at: string;
};

export type LibrarySearchHit = {
  hit_id: string;
  source_type: 'document' | 'knowledge_card' | 'project_library' | 'workspace_memory';
  collection_id?: string | null;
  title: string;
  snippet: string;
  source_status: string;
  version_id: string;
  sha256: string;
  evidence_status: string;
  tags: string[];
  locator?: string | null;
  relevance_score: number;
};

export type LibrarySearchResult = {
  schema_version: 1;
  query: string;
  mode_requested: 'lexical' | 'semantic' | 'hybrid';
  mode_used: 'lexical' | 'semantic' | 'hybrid';
  semantic_status:
    | 'not_requested'
    | 'ready'
    | 'model_missing'
    | 'offline'
    | 'integrity_failed'
    | 'runtime_unavailable';
  index_version: number;
  hits: LibrarySearchHit[];
  next_cursor?: string | null;
};

export type LibraryIndexStatus = {
  schema_version: 1;
  state: 'idle' | 'building' | 'ready' | 'failed';
  phase: string;
  files_scanned: number;
  bytes_processed: number;
  succeeded: number;
  skipped: number;
  failed: number;
  index_version: number;
  semantic_status: string;
  updated_at: string;
};

export type LibrarySemanticModelStatus = {
  schema_version: 1;
  model_id: 'intfloat/multilingual-e5-small';
  revision: string;
  state:
    | 'model_missing'
    | 'downloading'
    | 'ready'
    | 'offline'
    | 'integrity_failed'
    | 'runtime_unavailable'
    | 'failed';
  bytes_total: number;
  bytes_downloaded: number;
  current_file?: string | null;
  manifest_sha256: string;
  error_code?: string | null;
  updated_at: string;
};

export type LibraryExport = {
  schema_version: 1;
  export_id: string;
  collection_id: string;
  status: 'ready' | 'expired' | 'failed';
  policy_sha256: string;
  manifest_sha256: string;
  output_sha256: string;
  card_count: number;
  created_at: string;
  expires_at: string;
  download_url: string;
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
  kind: 'aion_team' | 'workflow' | 'onboarding_managed';
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
  recovery?: RecoveryState;
  input_requests: RuntimeInputRequest[];
  onboarding_artifact_writes?: Array<{
    request_id: string;
    approval_id: string;
    agent_name: 'Business Assistant' | 'Review Assistant';
    relative_path: 'artifacts/first-work.json' | 'artifacts/verification.json';
    content_sha256: string;
    nonce: string;
    requested_at: string;
    status: 'pending' | 'committed' | 'rejected';
    decided_at?: string | null;
    artifact_event_id?: string | null;
  }>;
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
  library_input_binding?: {
    schema_version: 1;
    binding_id: string;
    items: Array<{
      document_version_id: string;
      collection_id: string;
      name: string;
      media_type: string;
      size_bytes: number;
      sha256: string;
      attachment_id: string;
    }>;
    knowledge_card_version_ids: string[];
    knowledge_card_manifest_sha256?: string | null;
    manifest_sha256: string;
    created_at: string;
  } | null;
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

export type WorkspaceMemoryState =
  | 'candidate'
  | 'approved'
  | 'superseded'
  | 'revoked'
  | 'dismissed';

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
  origin: 'operator' | 'automatic_experience';
  generation_key?: string | null;
  fingerprint?: string | null;
  source_terminal_event_id?: string | null;
  source_terminal_event_sha256?: string | null;
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

export type OnboardingState =
  | 'preparing'
  | 'self_check'
  | 'migration_required'
  | 'provider_required'
  | 'first_work_ready'
  | 'first_work_running'
  | 'evidence_review'
  | 'complete'
  | 'failed';

export type OnboardingFailure = {
  code: string;
  detail: string;
  retryable: boolean;
};

export type OnboardingStatus = {
  state: OnboardingState;
  complete: boolean;
  required_free_bytes: number;
  available_free_bytes: number;
  disk_ready: boolean;
  migration_required: boolean;
  legacy_sources: string[];
  migration_choice?: 'fresh' | 'import' | null;
  runtime_ready: boolean;
  provider_runtime_ready: boolean;
  provider_choice: 'openai' | 'anthropic' | null;
  first_work_plan_id?: string | null;
  failure?: OnboardingFailure | null;
};

export type OnboardingFirstWork = {
  onboarding: OnboardingStatus;
  plan: PlanRecord;
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
