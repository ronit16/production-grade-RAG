'use client';

import useSWR from 'swr';
import { useAuth } from '@/lib/auth';
import { listSessions, createSession, deleteSession } from '@/lib/api';
import type { SessionListItem } from '@/types/rag';

interface Props {
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
}

function timeAgo(dateStr: string): string {
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function SessionSidebar({ activeSessionId, onSelectSession }: Props) {
  const { user } = useAuth();

  const { data: sessions = [], mutate, isLoading } = useSWR<SessionListItem[]>(
    user ? 'sessions' : null,
    () => listSessions(user!.token),
    { refreshInterval: 10000 }
  );

  async function handleCreate() {
    if (!user) return;
    const session = await createSession(user.token);
    await mutate();
    onSelectSession(session.session_id);
  }

  async function handleDelete(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    if (!user) return;
    await deleteSession(id, user.token);
    await mutate();
    if (activeSessionId === id) onSelectSession('');
  }

  return (
    <aside
      className="w-64 flex flex-col flex-shrink-0"
      style={{ background: 'var(--surface)', borderRight: '1px solid var(--border-2)' }}
    >
      {/* Header */}
      <div
        className="px-4 py-4 flex items-center justify-between"
        style={{ borderBottom: '1px solid var(--border-2)' }}
      >
        <span className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
          Sessions
        </span>
        <button
          onClick={handleCreate}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
          style={{ background: 'var(--accent)', color: 'white' }}
          onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--accent-hover)')}
          onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--accent)')}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New
        </button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto py-2">
        {isLoading ? (
          <div className="flex justify-center pt-8">
            <div className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : sessions.length === 0 ? (
          <p className="text-xs text-center pt-8 px-4" style={{ color: 'var(--text-muted)' }}>
            No sessions yet. Hit &quot;New&quot; to start.
          </p>
        ) : (
          sessions.map((s) => {
            const active = s.session_id === activeSessionId;
            return (
              <div
                key={s.session_id}
                onClick={() => onSelectSession(s.session_id)}
                className="group flex items-center gap-3 px-3 py-3 mx-2 rounded-lg cursor-pointer transition-all"
                style={{
                  background: active ? 'rgba(99,102,241,0.15)' : 'transparent',
                  border: `1px solid ${active ? 'rgba(99,102,241,0.3)' : 'transparent'}`,
                }}
              >
                <div
                  className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                  style={{ background: active ? 'rgba(99,102,241,0.25)' : 'var(--surface-2)' }}
                >
                  <svg
                    className="w-4 h-4"
                    style={{ color: active ? 'var(--accent-hover)' : 'var(--text-muted)' }}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                </div>
                <div className="flex-1 min-w-0">
                  <p
                    className="text-xs font-medium truncate"
                    style={{ color: active ? 'var(--accent-hover)' : 'var(--text)' }}
                  >
                    Session
                  </p>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    {timeAgo(s.last_active || s.created_at)}
                  </p>
                </div>
                <button
                  onClick={(e) => handleDelete(e, s.session_id)}
                  className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded"
                  style={{ color: 'var(--text-muted)' }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--error)')}
                  onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
                  title="Delete session"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}
