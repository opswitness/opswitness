import type {
  Bootstrap,
  MailAuthorizationJob,
  MailAuthorizationStatus,
  MailSummaryJob,
  PlanRecord,
  TelegramSetupStatus,
} from './types';

let csrfToken = '';

async function readError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail || `请求失败 (${response.status})`;
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

export function requestPlan(body: {
  objective: string;
  constraints: string;
  workspace: string;
  preferred_cadence: string;
}): Promise<PlanRecord> {
  return api('/api/v1/plans', { method: 'POST', body: JSON.stringify(body) });
}

export function getPlan(planId: string): Promise<PlanRecord> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}`);
}

export function confirmPlan(planId: string, planSha256: string): Promise<PlanRecord> {
  return api(`/api/v1/plans/${encodeURIComponent(planId)}/confirm`, {
    method: 'POST',
    body: JSON.stringify({ plan_sha256: planSha256, confirmed: true }),
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
