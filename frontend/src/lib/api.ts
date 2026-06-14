import type {
  AuthResponse,
  DocumentListItem,
  DocumentUploadResponse,
  DocumentStatusResponse,
  InviteResponse,
  SessionCreateResponse,
  SessionListItem,
  SessionCloseResponse,
  SSEEvent,
  TeamMember,
  TenantInfoResponse,
} from '@/types/rag';

const BASE = '/api';

function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text();
    let message = `HTTP ${res.status}`;
    try {
      message = JSON.parse(body)?.detail ?? message;
    } catch { /* use status */ }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

// ── Auth ─────────────────────────────────────────────────────────────────────

export async function apiLogin(email: string, password: string): Promise<AuthResponse> {
  const res = await fetch(`${BASE}/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  return handleResponse<AuthResponse>(res);
}

export async function apiRegister(username: string, email: string, password: string): Promise<AuthResponse> {
  const res = await fetch(`${BASE}/v1/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, email, password }),
  });
  return handleResponse<AuthResponse>(res);
}

export async function generateInvite(token: string): Promise<InviteResponse> {
  const res = await fetch(`${BASE}/v1/auth/invite`, {
    method: 'POST',
    headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  return handleResponse<InviteResponse>(res);
}

export async function registerMember(data: {
  invite_code: string;
  username: string;
  email: string;
  password: string;
}): Promise<AuthResponse> {
  const res = await fetch(`${BASE}/v1/auth/register-member`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse<AuthResponse>(res);
}

// ── Documents ────────────────────────────────────────────────────────────────

export async function listDocuments(token: string): Promise<DocumentListItem[]> {
  const res = await fetch(`${BASE}/v1/documents`, { headers: authHeaders(token) });
  return handleResponse<DocumentListItem[]>(res);
}

export async function uploadDocument(
  file: File,
  token: string
): Promise<DocumentUploadResponse> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/v1/documents`, {
    method: 'POST',
    headers: authHeaders(token),
    body: form,
  });
  return handleResponse<DocumentUploadResponse>(res);
}

export async function getDocumentStatus(
  documentId: string,
  token: string
): Promise<DocumentStatusResponse> {
  const res = await fetch(`${BASE}/v1/documents/${documentId}`, {
    headers: authHeaders(token),
  });
  return handleResponse<DocumentStatusResponse>(res);
}

export async function deleteDocument(
  documentId: string,
  token: string
): Promise<{ deleted: boolean; document_id: string }> {
  const res = await fetch(`${BASE}/v1/documents/${documentId}`, {
    method: 'DELETE',
    headers: authHeaders(token),
  });
  return handleResponse(res);
}

// ── Sessions ─────────────────────────────────────────────────────────────────

export async function createSession(token: string): Promise<SessionCreateResponse> {
  const res = await fetch(`${BASE}/v1/sessions`, {
    method: 'POST',
    headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  return handleResponse<SessionCreateResponse>(res);
}

export async function listSessions(token: string): Promise<SessionListItem[]> {
  const res = await fetch(`${BASE}/v1/sessions`, { headers: authHeaders(token) });
  return handleResponse<SessionListItem[]>(res);
}

export async function deleteSession(
  sessionId: string,
  token: string
): Promise<SessionCloseResponse> {
  const res = await fetch(`${BASE}/v1/sessions/${sessionId}`, {
    method: 'DELETE',
    headers: authHeaders(token),
  });
  return handleResponse<SessionCloseResponse>(res);
}

// ── Streaming query ──────────────────────────────────────────────────────────

export async function* streamQuery(
  sessionId: string,
  question: string,
  token: string
): AsyncGenerator<SSEEvent> {
  const res = await fetch(`${BASE}/v1/query`, {
    method: 'POST',
    headers: {
      ...authHeaders(token),
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({ session_id: sessionId, question }),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `Query failed: HTTP ${res.status}`);
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    let eventType = '';
    let eventData = '';

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        eventData = line.slice(6).trim();
      } else if (line.trim() === '' && eventType && eventData) {
        try {
          yield { type: eventType, data: JSON.parse(eventData) } as SSEEvent;
        } catch { /* skip malformed chunk */ }
        eventType = '';
        eventData = '';
      }
    }
  }
}

// ── Users / Team ─────────────────────────────────────────────────────────────

export async function listUsers(token: string): Promise<TeamMember[]> {
  const res = await fetch(`${BASE}/v1/users`, { headers: authHeaders(token) });
  return handleResponse<TeamMember[]>(res);
}

export async function createUser(
  data: { username: string; email: string; password: string; role: string },
  token: string
): Promise<{ user_id: string; username: string; email: string; role: string; tenant_id: string }> {
  const res = await fetch(`${BASE}/v1/users`, {
    method: 'POST',
    headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

export async function changeUserRole(
  userId: string,
  role: string,
  token: string
): Promise<{ user_id: string; success: boolean }> {
  const res = await fetch(`${BASE}/v1/users/${userId}/role`, {
    method: 'PATCH',
    headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ role }),
  });
  return handleResponse(res);
}

export async function deactivateUser(
  userId: string,
  token: string
): Promise<{ user_id: string; success: boolean }> {
  const res = await fetch(`${BASE}/v1/users/${userId}`, {
    method: 'DELETE',
    headers: authHeaders(token),
  });
  return handleResponse(res);
}

// ── Tenant ────────────────────────────────────────────────────────────────────

export async function getTenantInfo(token: string): Promise<TenantInfoResponse> {
  const res = await fetch(`${BASE}/v1/tenant`, { headers: authHeaders(token) });
  return handleResponse<TenantInfoResponse>(res);
}
