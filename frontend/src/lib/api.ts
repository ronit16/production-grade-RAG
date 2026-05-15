import type {
  AuthResponse,
  DocumentUploadResponse,
  DocumentStatusResponse,
  SessionCreateResponse,
  SessionListItem,
  SessionCloseResponse,
  SSEEvent,
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

export async function apiRegister(email: string, password: string): Promise<AuthResponse> {
  const res = await fetch(`${BASE}/v1/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  return handleResponse<AuthResponse>(res);
}

// ── Documents ────────────────────────────────────────────────────────────────

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
