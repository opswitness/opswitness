import type {
  Bootstrap,
  ApprovalMode,
  AgentRuntimeAssignment,
  CollaborationLoop,
  MailAuthorizationJob,
  MailAuthorizationStatus,
  MailSummaryJob,
  PairedDevice,
  PairingInvitation,
  PlanArtifact,
  PlanArtifactPreview,
  PlanningAttachmentUpload,
  PlanRecord,
  ProviderConnectionJob,
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

export async function loadBootstrap(): Promise<Bootstrap> {
  const payload = await api<Bootstrap>('/api/v1/bootstrap');
  csrfToken = payload.csrf_token;
  return payload;
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
): Promise<WorkspaceMemoryView> {
  return api(`/api/v1/workspace-memory/${encodeURIComponent(versionId)}/approve`, {
    method: 'POST',
    body: JSON.stringify({ reason, confirmed: true }),
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

export function connectProvider(
  provider: 'openai' | 'anthropic' | 'deepseek' | 'xai' | 'ollama' | 'lmstudio',
  method: 'account' | 'api' | 'api_key' | 'local' = 'account',
  apiKey?: string,
): Promise<ProviderConnectionJob> {
  const body: {
    method: 'account' | 'api' | 'api_key' | 'local';
    api_key?: string;
    confirmed?: true;
  } = { method };
  if (apiKey) body.api_key = apiKey;
  if (method === 'api_key' || method === 'local') body.confirmed = true;
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
