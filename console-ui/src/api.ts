import type {
  AgentContractDiffEntry,
  AgentContractPreview,
  Bootstrap,
  ApprovalMode,
  AgentRuntimeAssignment,
  CollaborationLoop,
  MailAuthorizationJob,
  MailAuthorizationStatus,
  MailSummaryJob,
  KnowledgeCardVersion,
  LibraryCardJob,
  LibraryCollection,
  LibraryCollectionPolicy,
  LibraryDocumentVersion,
  LibraryExport,
  LibraryImport,
  LibraryIndexStatus,
  LibrarySemanticModelStatus,
  LibrarySearchResult,
  OnboardingFirstWork,
  OnboardingStatus,
  PairedDevice,
  PairingInvitation,
  PlanArtifact,
  PlanArtifactPreview,
  PlanningAttachmentUpload,
  PlanRecord,
  ProjectLibraryItem,
  ProjectLibraryItemPreview,
  ProviderConnectionJob,
  RecoveryState,
  ReportingLine,
  RuntimeInputArtifact,
  RuntimeInputArtifactPreview,
  WorkspaceConversation,
  WorkspaceMemoryView,
  TaskTemplate,
  TeamBlueprint,
  TelegramSetupStatus,
} from './types';
import {
  DEFAULT_UI_LANGUAGE,
  resolveUiLanguage,
  translateApiError,
  UI_LANGUAGE_STORAGE_KEY,
} from './i18n.js';
import type { AgentGraphRevisionPayload } from './agent-graph-model.js';

let csrfToken = '';

function currentUiLanguage() {
  if (typeof window === 'undefined') return DEFAULT_UI_LANGUAGE;
  try {
    return resolveUiLanguage(window.localStorage.getItem(UI_LANGUAGE_STORAGE_KEY));
  } catch {
    return DEFAULT_UI_LANGUAGE;
  }
}

async function readError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { code?: string; detail?: string };
    const fallback = payload.detail || `请求失败 (${response.status})`;
    return translateApiError(currentUiLanguage(), payload.code, fallback);
  } catch {
    return `请求失败 (${response.status})`;
  }
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.method && init.method !== 'GET') {
    headers.set('Content-Type', 'application/json');
    headers.set('X-QD-CSRF', csrfToken);
  }
  const response = await fetch(path, { ...init, headers, credentials: 'same-origin' });
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as T;
}

async function apiBinary<T>(path: string, body: Blob): Promise<T> {
  const headers = new Headers({
    'Content-Type': 'application/octet-stream',
    'X-QD-CSRF': csrfToken,
  });
  const response = await fetch(path, {
    method: 'PUT',
    headers,
    body,
    credentials: 'same-origin',
  });
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as T;
}

export async function loadBootstrap(): Promise<Bootstrap> {
  const payload = await api<Bootstrap>('/api/v1/bootstrap');
  csrfToken = payload.csrf_token;
  return payload;
}

export function loadOnboarding(): Promise<OnboardingStatus> {
  return api('/api/v1/onboarding');
}

export function chooseOnboardingMigration(
  choice: 'fresh' | 'import',
): Promise<OnboardingStatus> {
  return api('/api/v1/onboarding/migration', {
    method: 'POST',
    body: JSON.stringify({ choice, confirmed: true }),
  });
}

export function selectOnboardingProvider(
  provider: 'openai' | 'anthropic',
): Promise<OnboardingStatus> {
  return api('/api/v1/onboarding/provider', {
    method: 'POST',
    body: JSON.stringify({ provider, confirmed: true }),
  });
}

export function prepareOnboardingFirstWork(
  replaceUnstartedLegacy = false,
  replaceIncompleteTerminal = false,
): Promise<OnboardingFirstWork> {
  return api('/api/v1/onboarding/first-work', {
    method: 'POST',
    body: JSON.stringify({
      confirmed: true,
      replace_unstarted_legacy: replaceUnstartedLegacy,
      replace_incomplete_terminal: replaceIncompleteTerminal,
    }),
  });
}

export function signoffOnboardingArtifacts(
  planId: string,
  review: {
    first_work_event_id: string;
    first_work_sha256: string;
    verification_event_id: string;
    verification_sha256: string;
  },
): Promise<OnboardingStatus> {
  return api(`/api/v1/works/${encodeURIComponent(planId)}/artifact-signoff`, {
    method: 'POST',
    body: JSON.stringify({ confirmed: true, ...review }),
  });
}

export function getPairedDevices(): Promise<PairedDevice[]> {
  return api('/api/v1/pairing/devices');
}

export function createPairingInvitation(): Promise<PairingInvitation> {
  return api('/api/v1/pairing/invitations', {
    method: 'POST',
    body: JSON.stringify({ confirmed: true }),
  });
}

export function revokePairedDevice(deviceId: string): Promise<{ device_id: string; revoked: true }> {
  return api(`/api/v1/pairing/devices/${encodeURIComponent(deviceId)}/revoke`, {
    method: 'POST',
    body: JSON.stringify({ confirmed: true }),
  });
}

export function requestPlan(body: {
  objective: string;
  constraints: string;
  workspace: string;
  preferred_cadence: string;
  blueprint_id?: string | null;
  attachments?: PlanningAttachmentUpload[];
}): Promise<PlanRecord> {
  return api('/api/v1/plans', { method: 'POST', body: JSON.stringify(body) });
}

export function getPlan(planId: string): Promise<PlanRecord> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}`);
}

export function retryFailedPlanning(planId: string, objective: string): Promise<PlanRecord> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}/planning-retries`, {
    method: 'POST',
    body: JSON.stringify({ objective, confirmed: true }),
  });
}

export function getWorkRecovery(workId: string): Promise<RecoveryState> {
  return api(`/api/v1/works/${encodeURIComponent(workId)}/recovery`);
}

export function checkWorkRecovery(workId: string): Promise<RecoveryState> {
  return api(`/api/v1/works/${encodeURIComponent(workId)}/recovery/check`, {
    method: 'POST',
    body: JSON.stringify({ confirmed: true }),
  });
}

export function decideWorkRecovery(
  workId: string,
  expectedProposalSha256: string,
): Promise<{ recovery: RecoveryState; repair_work: PlanRecord }> {
  return api(`/api/v1/works/${encodeURIComponent(workId)}/recovery/decision`, {
    method: 'POST',
    body: JSON.stringify({
      action: 'create_repair_work',
      expected_proposal_sha256: expectedProposalSha256,
      confirmed: true,
    }),
  });
}

export function revisePlan(planId: string, instruction: string): Promise<PlanRecord> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}/revise`, {
    method: 'POST',
    body: JSON.stringify({ instruction }),
  });
}

export function preparePlanRerun(
  planId: string,
  executionProfile: 'fast' | 'balanced' | 'deep' = 'fast',
): Promise<PlanRecord> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}/rerun`, {
    method: 'POST',
    body: JSON.stringify({ execution_profile: executionProfile, confirmed: true }),
  });
}

export function continuePlanRun(planId: string, message: string): Promise<PlanRecord> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}/continue`, {
    method: 'POST',
    body: JSON.stringify({ message, confirmed: true }),
  });
}

export function forkPlan(planId: string): Promise<PlanRecord> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}/fork`, {
    method: 'POST',
    body: JSON.stringify({ confirmed: true }),
  });
}

export function controlPlan(
  planId: string,
  action: 'pause' | 'resume' | 'terminate',
): Promise<PlanRecord> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}/control`, {
    method: 'POST',
    body: JSON.stringify({ action, confirmed: true }),
  });
}

export function changeExecutionApprovalMode(
  planId: string,
  approvalMode: 'automatic' | 'manual_all',
  expectedCurrentMode: ApprovalMode,
): Promise<PlanRecord> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}/approval-mode`, {
    method: 'POST',
    body: JSON.stringify({
      approval_mode: approvalMode,
      expected_current_mode: expectedCurrentMode,
      confirmed: true,
    }),
  });
}

export function revisePlanOrganization(
  planId: string,
  reportingLines: ReportingLine[],
  collaborationLoops: CollaborationLoop[],
): Promise<PlanRecord> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}/organization`, {
    method: 'POST',
    body: JSON.stringify({
      reporting_lines: reportingLines,
      collaboration_loops: collaborationLoops,
      confirmed: true,
    }),
  });
}

export function revisePlanAgentGraph(
  planId: string,
  payload: AgentGraphRevisionPayload,
): Promise<PlanRecord> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}/agent-graph/revisions`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function previewPlanAgentContract(
  planId: string,
  expectedPlanSha256: string,
  draft: Record<string, unknown> | null,
): Promise<AgentContractPreview> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}/agent-contract/preview`, {
    method: 'POST',
    body: JSON.stringify({
      expected_plan_sha256: expectedPlanSha256,
      draft,
    }),
  });
}

export function revisePlanAgentContract(
  planId: string,
  expectedPlanSha256: string,
  draft: Record<string, unknown>,
): Promise<PlanRecord> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}/agent-contract/revisions`, {
    method: 'POST',
    body: JSON.stringify({
      expected_plan_sha256: expectedPlanSha256,
      draft,
      confirmed: true,
    }),
  });
}

export function getAgentContractVersions(planId: string): Promise<Array<{
  plan_id: string;
  plan_sha256: string;
  parent_plan_id?: string | null;
  parent_plan_sha256?: string | null;
  revision_number: number;
  status: PlanRecord['status'];
  created_at: string;
  agent_count: number;
  contract_sha256: string;
}>> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}/agent-contract/versions`);
}

export function diffAgentContractVersions(
  childPlanId: string,
  basePlanId: string,
): Promise<AgentContractDiffEntry[]> {
  const query = new URLSearchParams({ base_plan_id: basePlanId });
  return api(
    `/api/v1/plans/${encodeURIComponent(childPlanId)}/agent-contract/diff?${query.toString()}`,
  );
}

export function revisePlanRuntimes(
  planId: string,
  assignments: AgentRuntimeAssignment[],
): Promise<PlanRecord> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}/runtimes`, {
    method: 'POST',
    body: JSON.stringify({ assignments, confirmed: true }),
  });
}

export function revisePlanExecutionProfile(
  planId: string,
  executionProfile: 'fast' | 'balanced' | 'deep',
): Promise<PlanRecord> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}/execution-profile`, {
    method: 'POST',
    body: JSON.stringify({ execution_profile: executionProfile, confirmed: true }),
  });
}

export function deletePlan(planId: string): Promise<{
  plan_id: string;
  deleted: true;
  deleted_at: string;
  evidence_event_id: string;
}> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}`, {
    method: 'DELETE',
    body: JSON.stringify({ confirmed: true }),
  });
}

export function eraseRun(planId: string, expectedPlanSha256: string): Promise<{
  plan_id: string;
  erased: true;
  erased_at: string;
  evidence_event_id: string;
  local_workspace_removed: boolean;
  exclusive_aion_team_removed: boolean;
  cas_blobs_removed: number;
  shared_blobs_retained: number;
  material_sets_removed: number;
  shared_material_sets_retained: number;
  external_workspace_retained: boolean;
  external_governance_retained: boolean;
}> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}/run-data`, {
    method: 'DELETE',
    body: JSON.stringify({
      confirmed: true,
      expected_plan_sha256: expectedPlanSha256,
    }),
  });
}

export function getTeamBlueprints(includeArchived = false): Promise<TeamBlueprint[]> {
  const query = includeArchived ? '?include_archived=true' : '';
  return api(`/api/v1/team-blueprints${query}`);
}

export function saveTeamBlueprint(sourcePlanId: string, name: string): Promise<TeamBlueprint> {
  return api('/api/v1/team-blueprints', {
    method: 'POST',
    body: JSON.stringify({ source_plan_id: sourcePlanId, name, confirmed: true }),
  });
}

export function archiveTeamBlueprint(blueprintId: string): Promise<TeamBlueprint> {
  return api(`/api/v1/team-blueprints/${encodeURIComponent(blueprintId)}/archive`, {
    method: 'POST',
    body: JSON.stringify({ confirmed: true }),
  });
}

export function getTaskTemplates(includeArchived = false): Promise<TaskTemplate[]> {
  const query = includeArchived ? '?include_archived=true' : '';
  return api(`/api/v1/task-templates${query}`);
}

export function saveTaskTemplate(name: string, objective: string): Promise<TaskTemplate> {
  return api('/api/v1/task-templates', {
    method: 'POST',
    body: JSON.stringify({ name, objective, confirmed: true }),
  });
}

export function saveTaskTemplateFromPlan(planId: string, name: string): Promise<TaskTemplate> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}/task-template`, {
    method: 'POST',
    body: JSON.stringify({ name, confirmed: true }),
  });
}

export function getWorkspaceConversations(): Promise<WorkspaceConversation[]> {
  return api('/api/v1/workspace-conversations');
}

export function getWorkspaceConversationEntries(planId: string): Promise<PlanRecord[]> {
  return api(
    `/api/v1/workspace-conversations/${encodeURIComponent(planId)}/entries`,
  );
}

export function archiveTaskTemplate(templateId: string): Promise<TaskTemplate> {
  return api(`/api/v1/task-templates/${encodeURIComponent(templateId)}/archive`, {
    method: 'POST',
    body: JSON.stringify({ confirmed: true }),
  });
}

export function getWorkspaceMemories(
  query = '',
  includeHistory = true,
): Promise<WorkspaceMemoryView[]> {
  const params = new URLSearchParams();
  if (query.trim()) params.set('query', query.trim());
  params.set('include_history', String(includeHistory));
  return api(`/api/v1/workspace-memory?${params.toString()}`);
}

export function createWorkspaceMemoryCandidate(body: {
  kind: 'process' | 'knowledge';
  title: string;
  content: string;
  tags: string[];
  workspace?: string;
  source_plan_id?: string | null;
  supersedes_version_id?: string | null;
}): Promise<WorkspaceMemoryView> {
  return api('/api/v1/workspace-memory/candidates', {
    method: 'POST',
    body: JSON.stringify({ ...body, confirmed: true }),
  });
}

export function proposeProcessMemory(
  planId: string,
  title?: string,
): Promise<WorkspaceMemoryView> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}/memory-candidates`, {
    method: 'POST',
    body: JSON.stringify({ title: title?.trim() || null, confirmed: true }),
  });
}

export function approveWorkspaceMemory(
  versionId: string,
  reason = '',
  expectedContentSha256: string | null = null,
  expectedFingerprint: string | null = null,
): Promise<WorkspaceMemoryView> {
  return api(`/api/v1/workspace-memory/${encodeURIComponent(versionId)}/approve`, {
    method: 'POST',
    body: JSON.stringify({
      reason,
      expected_content_sha256: expectedContentSha256,
      expected_fingerprint: expectedFingerprint,
      confirmed: true,
    }),
  });
}

export function dismissWorkspaceMemory(
  versionId: string,
  expectedContentSha256: string,
  expectedFingerprint: string | null,
  reason = '',
): Promise<WorkspaceMemoryView> {
  return api(`/api/v1/workspace-memory/${encodeURIComponent(versionId)}/dismiss`, {
    method: 'POST',
    body: JSON.stringify({
      reason,
      expected_content_sha256: expectedContentSha256,
      expected_fingerprint: expectedFingerprint,
      confirmed: true,
    }),
  });
}

export function revokeWorkspaceMemory(
  versionId: string,
  reason = '',
): Promise<WorkspaceMemoryView> {
  return api(`/api/v1/workspace-memory/${encodeURIComponent(versionId)}/revoke`, {
    method: 'POST',
    body: JSON.stringify({ reason, confirmed: true }),
  });
}

export function rollbackWorkspaceMemory(
  versionId: string,
  reason: string,
): Promise<WorkspaceMemoryView> {
  return api(`/api/v1/workspace-memory/${encodeURIComponent(versionId)}/rollback`, {
    method: 'POST',
    body: JSON.stringify({ reason, confirmed: true }),
  });
}

export function confirmPlan(
  planId: string,
  planSha256: string,
  approvalMode: ApprovalMode = 'automatic',
): Promise<PlanRecord> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}/confirm`, {
    method: 'POST',
    body: JSON.stringify({
      plan_sha256: planSha256,
      approval_mode: approvalMode,
      confirmed: true,
    }),
  });
}

export function answerRuntimeInput(
  planId: string,
  requestId: string,
  answer: string,
): Promise<PlanRecord> {
  return api(
    `/api/v1/plans/${encodeURIComponent(planId)}/input-requests/${encodeURIComponent(requestId)}/answer`,
    {
      method: 'POST',
      body: JSON.stringify({ answer, confirmed: true }),
    },
  );
}

export function getRuntimeInputArtifacts(
  planId: string,
  requestId: string,
): Promise<RuntimeInputArtifact[]> {
  return api(
    `/api/v1/plans/${encodeURIComponent(planId)}/input-requests/${encodeURIComponent(requestId)}/artifacts`,
  );
}

export function getRuntimeInputArtifact(
  planId: string,
  requestId: string,
  artifactName: string,
): Promise<RuntimeInputArtifactPreview> {
  return api(
    `/api/v1/plans/${encodeURIComponent(planId)}/input-requests/${encodeURIComponent(requestId)}/artifacts/${encodeURIComponent(artifactName)}`,
  );
}

export function getPlanArtifacts(planId: string): Promise<PlanArtifact[]> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}/artifacts`);
}

export function getPlanArtifact(
  planId: string,
  artifactName: string,
): Promise<PlanArtifactPreview> {
  return api(
    `/api/v1/plans/${encodeURIComponent(planId)}/artifacts/${encodeURIComponent(artifactName)}`,
  );
}

export function planArtifactContentUrl(planId: string, artifactName: string): string {
  return `/api/v1/plans/${encodeURIComponent(planId)}/artifacts/${encodeURIComponent(artifactName)}/content`;
}

export function getProjectLibrary(filters: {
  query?: string;
  tag?: string;
  file_type?: string;
  work_id?: string;
} = {}): Promise<ProjectLibraryItem[]> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value?.trim()) params.set(key, value.trim());
  });
  const suffix = params.toString();
  return api(`/api/v1/project-library${suffix ? `?${suffix}` : ''}`);
}

export function getProjectLibraryItem(assetId: string): Promise<ProjectLibraryItemPreview> {
  return api(`/api/v1/project-library/${encodeURIComponent(assetId)}`);
}

export function updateProjectLibraryItem(
  assetId: string,
  body: {
    expected_sha256: string;
    user_tags: string[];
    supersedes_asset_id: string | null;
  },
): Promise<ProjectLibraryItemPreview> {
  return api(`/api/v1/project-library/${encodeURIComponent(assetId)}`, {
    method: 'PATCH',
    body: JSON.stringify({ ...body, confirmed: true }),
  });
}

export function getLibraryCollections(): Promise<LibraryCollection[]> {
  return api('/api/v1/library/collections');
}

export function createLibraryCollection(body: {
  name: string;
  policy: LibraryCollectionPolicy;
}): Promise<LibraryCollection> {
  return api('/api/v1/library/collections', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function createLibraryImport(body: {
  collection_id: string;
  expected_collection_revision: number;
  entries: Array<{
    relative_path: string;
    size_bytes: number;
    media_type: string;
    source_kind: 'file';
  }>;
}): Promise<LibraryImport> {
  return api('/api/v1/library/imports', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function uploadLibraryImportEntry(
  importId: string,
  entryId: string,
  file: File,
): Promise<LibraryImport> {
  return apiBinary(
    `/api/v1/library/imports/${encodeURIComponent(importId)}/files/${encodeURIComponent(entryId)}`,
    file,
  );
}

export function getLibraryImport(importId: string): Promise<LibraryImport> {
  return api(`/api/v1/library/imports/${encodeURIComponent(importId)}`);
}

export function commitLibraryImport(
  importId: string,
  expectedCollectionRevision: number,
  confirmedManifestSha256: string,
): Promise<LibraryImport> {
  return api(`/api/v1/library/imports/${encodeURIComponent(importId)}/commit`, {
    method: 'POST',
    body: JSON.stringify({
      expected_collection_revision: expectedCollectionRevision,
      confirmed_manifest_sha256: confirmedManifestSha256,
      confirmed: true,
    }),
  });
}

export function cancelLibraryImport(importId: string): Promise<LibraryImport> {
  return api(`/api/v1/library/imports/${encodeURIComponent(importId)}`, {
    method: 'DELETE',
    body: JSON.stringify({}),
  });
}

export function getLibraryDocuments(
  collectionId = '',
  includeHistory = false,
): Promise<LibraryDocumentVersion[]> {
  const params = new URLSearchParams();
  if (collectionId) params.set('collection_id', collectionId);
  if (includeHistory) params.set('include_history', 'true');
  const suffix = params.toString();
  return api(`/api/v1/library/documents${suffix ? `?${suffix}` : ''}`);
}

export function createLibraryCardJob(body: {
  collection_id: string;
  document_version_ids: string[];
  provider: 'openai' | 'anthropic';
  model: string;
  disclosed_character_count: number;
  confirmed_source_disclosure: true;
}): Promise<LibraryCardJob> {
  return api('/api/v1/library/card-jobs', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function getLibraryCardJob(jobId: string): Promise<LibraryCardJob> {
  return api(`/api/v1/library/card-jobs/${encodeURIComponent(jobId)}`);
}

export function getLibraryCards(
  collectionId = '',
  state = '',
): Promise<KnowledgeCardVersion[]> {
  const params = new URLSearchParams();
  if (collectionId) params.set('collection_id', collectionId);
  if (state) params.set('state', state);
  const suffix = params.toString();
  return api(`/api/v1/library/cards${suffix ? `?${suffix}` : ''}`);
}

export function decideLibraryCard(
  versionId: string,
  action: 'approve' | 'dismiss' | 'revoke',
  expectedCardSha256: string,
): Promise<KnowledgeCardVersion> {
  return api(
    `/api/v1/library/cards/${encodeURIComponent(versionId)}/${action}`,
    {
      method: 'POST',
      body: JSON.stringify({
        expected_card_sha256: expectedCardSha256,
        confirmed: true,
      }),
    },
  );
}

export function searchLibrary(body: {
  query: string;
  mode: 'lexical' | 'semantic' | 'hybrid';
  collection_ids?: string[];
  states?: string[];
  source_types?: string[];
  evidence_statuses?: string[];
  limit?: number;
  cursor?: string | null;
}): Promise<LibrarySearchResult> {
  return api('/api/v1/library/search', {
    method: 'POST',
    body: JSON.stringify({ schema_version: 1, ...body }),
  });
}

export function getLibraryIndexStatus(): Promise<LibraryIndexStatus> {
  return api('/api/v1/library/index/status');
}

export function rebuildLibraryIndex(): Promise<LibraryIndexStatus> {
  return api('/api/v1/library/index/rebuild', {
    method: 'POST',
    body: JSON.stringify({}),
  });
}

export function getLibrarySemanticModelStatus(): Promise<LibrarySemanticModelStatus> {
  return api('/api/v1/library/semantic-model/status');
}

export function downloadLibrarySemanticModel(): Promise<LibrarySemanticModelStatus> {
  return api('/api/v1/library/semantic-model/download', {
    method: 'POST',
    body: JSON.stringify({ confirmed: true }),
  });
}

export function requestPlanFromLibrary(body: {
  objective: string;
  constraints: string;
  workspace: string;
  preferred_cadence: string;
  document_version_ids: string[];
  knowledge_card_version_ids: string[];
  confirmed_context_packet: true;
}): Promise<PlanRecord> {
  return api('/api/v1/plans/from-library', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export type LibraryExportPolicy = {
  schema_version: 1;
  profile: 'safe_partner';
  include_card_version_ids: string[];
  include_tags: boolean;
  include_citation_excerpts: boolean;
  custom_sensitive_terms: string[];
};

export function previewLibraryExport(body: {
  collection_id: string;
  expected_collection_revision: number;
  policy: LibraryExportPolicy;
}): Promise<{
  preview_sha256: string;
  included: Record<string, unknown>;
  excluded: string[];
  replacements: Record<string, unknown>;
  static_share_boundary: string;
}> {
  return api('/api/v1/library/exports/preview', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function createLibraryExport(body: {
  collection_id: string;
  expected_collection_revision: number;
  policy: LibraryExportPolicy;
  expected_preview_sha256: string;
  confirmed: true;
}): Promise<LibraryExport> {
  return api('/api/v1/library/exports', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function connectProvider(
  provider: 'openai' | 'anthropic' | 'deepseek' | 'xai' | 'ollama' | 'lmstudio',
  method: 'account' | 'api' | 'api_key' | 'local' = 'account',
  apiKey?: string,
  confirmed = false,
): Promise<ProviderConnectionJob> {
  const body: {
    method: 'account' | 'api' | 'api_key' | 'local';
    api_key?: string;
    confirmed?: true;
  } = { method };
  if (apiKey) body.api_key = apiKey;
  if (confirmed || method === 'api_key' || method === 'local') body.confirmed = true;
  return api(`/api/v1/providers/${provider}/connect`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function getProviderConnection(jobId: string): Promise<ProviderConnectionJob> {
  return api(`/api/v1/provider-connections/${encodeURIComponent(jobId)}`);
}

export function decideApproval(
  approvalId: string,
  decision: 'approve' | 'reject',
  decisionNote: string,
): Promise<{ approval_id: string; status: 'approved' | 'rejected'; reconciled: boolean }> {
  return api(`/api/v1/approvals/${encodeURIComponent(approvalId)}/decision`, {
    method: 'POST',
    body: JSON.stringify({
      decision,
      decision_note: decisionNote,
      confirmed: true,
    }),
  });
}

export function requestMailSummary(): Promise<MailSummaryJob> {
  return api('/api/v1/mail-summary', { method: 'POST', body: '{}' });
}

export function getMailSummary(jobId: string): Promise<MailSummaryJob> {
  return api(`/api/v1/mail-summary/${encodeURIComponent(jobId)}`);
}

export function getMailAuthorizationStatus(): Promise<MailAuthorizationStatus> {
  return api('/api/v1/mail-authorization/status');
}

export function requestMailAuthorization(): Promise<MailAuthorizationJob> {
  return api('/api/v1/mail-authorization', {
    method: 'POST',
    body: JSON.stringify({
      gmail_readonly_acknowledged: true,
      model_metadata_acknowledged: true,
    }),
  });
}

export function configureMailOAuthClient(clientJson: string): Promise<{ configured: true }> {
  return api('/api/v1/mail-authorization/client', {
    method: 'POST',
    body: JSON.stringify({
      client_json: clientJson,
      private_storage_acknowledged: true,
    }),
  });
}

export function getMailAuthorization(jobId: string): Promise<MailAuthorizationJob> {
  return api(`/api/v1/mail-authorization/${encodeURIComponent(jobId)}`);
}

export function disableMail(): Promise<{ disabled: true }> {
  return api('/api/v1/mail-authorization/disable', {
    method: 'POST',
    body: JSON.stringify({ confirmed: true }),
  });
}

export function getTelegramStatus(): Promise<TelegramSetupStatus> {
  return api('/api/v1/telegram/status');
}

export function configureTelegram(body: {
  bot_token: string;
  chat_id: string;
  storage_acknowledged: true;
  replace_existing: boolean;
}): Promise<{ configured: true }> {
  return api('/api/v1/telegram/configure', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function testTelegram(): Promise<{ sent: true }> {
  return api('/api/v1/telegram/test', {
    method: 'POST',
    body: JSON.stringify({ confirmed: true }),
  });
}

export function disableTelegram(): Promise<{ disabled: true }> {
  return api('/api/v1/telegram/disable', {
    method: 'POST',
    body: JSON.stringify({ confirmed: true }),
  });
}
