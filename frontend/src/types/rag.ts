// ── Auth ─────────────────────────────────────────────────────────────────────

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  tenant_id: string;
  email: string;
  username: string;
  role: string;
}

export interface StoredUser {
  token: string;
  user_id: string;
  tenant_id: string;
  email: string;
  username: string;
  role: string;
}

// ── Documents ─────────────────────────────────────────────────────────────────

export type DocumentStatus = 'pending' | 'processing' | 'ready' | 'failed';

export interface DocumentUploadResponse {
  document_id: string;
  filename: string;
  status: DocumentStatus;
}

export interface DocumentStatusResponse {
  document_id: string;
  filename: string;
  status: DocumentStatus;
  chunk_count: number | null;
  processing_ms: number | null;
  error: string | null;
  created_at: string;
}

export interface DocumentListItem {
  document_id: string;
  filename: string;
  content_type: string;
  file_size: number;
  status: DocumentStatus;
  chunk_count: number | null;
  processing_ms: number | null;
  error: string | null;
  created_at: string | null;
}

// ── Sessions ──────────────────────────────────────────────────────────────────

export interface SessionCreateResponse {
  session_id: string;
  created_at: string;
}

export interface SessionListItem {
  session_id: string;
  created_at: string;
  last_active: string;
}

export interface SessionCloseResponse {
  closed: boolean;
}

// ── Query / SSE ───────────────────────────────────────────────────────────────

export interface QuerySource {
  document_id: string;
  filename: string;
  page_number: number | null;
  section: string | null;
  chunk_text: string;
  score: number;
}

export type SSEEventType = 'status' | 'retrieval' | 'delta' | 'done' | 'error';

export interface SSEStatusEvent {
  type: 'status';
  data: { status: 'retrieving' | 'generating' };
}

export interface SSERetrievalEvent {
  type: 'retrieval';
  data: { chunk_count: number; rewritten_query: string };
}

export interface SSEDeltaEvent {
  type: 'delta';
  data: { text: string };
}

export interface SSEDoneEvent {
  type: 'done';
  data: { sources: QuerySource[]; query_id: string };
}

export interface SSEErrorEvent {
  type: 'error';
  data: { error: string };
}

export type SSEEvent =
  | SSEStatusEvent
  | SSERetrievalEvent
  | SSEDeltaEvent
  | SSEDoneEvent
  | SSEErrorEvent;

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: QuerySource[];
  isStreaming?: boolean;
  rewrittenQuery?: string;
}

// ── Users / Team ──────────────────────────────────────────────────────────────

export type UserRole = 'owner' | 'admin' | 'member';

export interface TeamMember {
  user_id: string;
  username: string | null;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string | null;
  last_login: string | null;
}

// ── Tenant / Settings ─────────────────────────────────────────────────────────

export interface TenantInfo {
  tenant_id: string;
  slug: string;
  name: string;
  plan: string;
  is_active: boolean;
  created_at: string | null;
}

export interface PlanLimits {
  max_docs: number | null;
  tokens_day: number | null;
  rps: number;
  max_sessions: number | null;
}

export interface TenantUsage {
  doc_count: number;
  session_count: number;
  tokens_today: number;
  query_count_today: number;
}

export interface TenantInfoResponse {
  tenant: TenantInfo;
  limits: PlanLimits;
  usage: TenantUsage;
  member_count: number;
}

// ── Invite ────────────────────────────────────────────────────────────────────

export interface InviteResponse {
  invite_code: string;
  expires_at: string;
}
