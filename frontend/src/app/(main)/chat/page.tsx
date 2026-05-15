'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import useSWR from 'swr';
import { useAuth } from '@/lib/auth';
import { listSessions, createSession, deleteSession, streamQuery } from '@/lib/api';
import CitationCard from '@/components/CitationCard';
import type { SessionListItem, ChatMessage, QuerySource } from '@/types/rag';

// ── Session sidebar ───────────────────────────────────────────────────────────

function timeGroup(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const diff = Math.floor((now.getTime() - d.getTime()) / 86400000);
  if (diff === 0) return 'Today';
  if (diff === 1) return 'Yesterday';
  if (diff <= 7) return 'Previous 7 days';
  return 'Older';
}

function Sidebar({
  sessions,
  activeId,
  onSelect,
  onCreate,
  onDelete,
}: {
  sessions: SessionListItem[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
}) {
  const { user, logout } = useAuth();
  const router = useRouter();

  const grouped = sessions.reduce<Record<string, SessionListItem[]>>((acc, s) => {
    const g = timeGroup(s.last_active || s.created_at);
    (acc[g] ??= []).push(s);
    return acc;
  }, {});
  const ORDER = ['Today', 'Yesterday', 'Previous 7 days', 'Older'];

  return (
    <aside className="w-64 flex flex-col h-full bg-[#171717] border-r border-white/5">
      {/* New chat */}
      <div className="p-3 border-b border-white/5">
        <button
          onClick={onCreate}
          className="flex items-center gap-2.5 w-full px-3 py-2.5 rounded-xl text-sm font-medium text-gray-300 hover:bg-white/5 transition-colors"
        >
          <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
          </svg>
          New chat
          <svg className="w-4 h-4 ml-auto opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
        </button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto py-2 px-2 space-y-4">
        {ORDER.filter((g) => grouped[g]?.length).map((group) => (
          <div key={group}>
            <p className="px-2 py-1 text-xs font-semibold text-gray-500 uppercase tracking-wider">
              {group}
            </p>
            {grouped[group].map((s) => {
              const active = s.session_id === activeId;
              return (
                <div
                  key={s.session_id}
                  onClick={() => onSelect(s.session_id)}
                  className={`group relative flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer text-sm transition-colors ${
                    active ? 'bg-white/10 text-white' : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'
                  }`}
                >
                  <svg className="w-4 h-4 flex-shrink-0 opacity-60" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                  <span className="truncate flex-1">Chat {s.session_id.slice(0, 8)}</span>
                  <button
                    onClick={(e) => { e.stopPropagation(); onDelete(s.session_id); }}
                    className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:text-red-400 transition-all"
                    title="Delete"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              );
            })}
          </div>
        ))}
        {sessions.length === 0 && (
          <p className="text-xs text-gray-600 text-center pt-6 px-3">
            No conversations yet
          </p>
        )}
      </div>

      {/* Bottom */}
      <div className="border-t border-white/5 p-2 space-y-0.5">
        <Link
          href="/documents"
          className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-gray-400 hover:bg-white/5 hover:text-gray-200 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          Documents
        </Link>
        <div className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-gray-500">
          <div className="w-6 h-6 rounded-full bg-indigo-600 flex items-center justify-center text-xs text-white font-semibold flex-shrink-0">
            {user?.email?.[0]?.toUpperCase() ?? 'U'}
          </div>
          <span className="truncate flex-1 text-gray-400">{user?.email}</span>
          <button
            onClick={() => { logout(); router.push('/login'); }}
            title="Sign out"
            className="hover:text-red-400 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
          </button>
        </div>
      </div>
    </aside>
  );
}

// ── Message bubble ────────────────────────────────────────────────────────────

function Message({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user';

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] px-4 py-3 rounded-2xl rounded-br-sm bg-indigo-600 text-white text-sm leading-relaxed">
          {msg.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3 items-start">
      <div className="w-7 h-7 rounded-full bg-indigo-600/20 flex items-center justify-center flex-shrink-0 mt-0.5">
        <svg className="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm leading-relaxed text-gray-100 whitespace-pre-wrap">
          {msg.content}
          {msg.isStreaming && (
            <span className="inline-block w-1.5 h-4 ml-0.5 bg-indigo-400 rounded-sm animate-pulse align-middle" />
          )}
        </div>
        {msg.sources && msg.sources.length > 0 && (
          <CitationCard sources={msg.sources} />
        )}
      </div>
    </div>
  );
}

// ── Chat area ─────────────────────────────────────────────────────────────────

function ChatArea({ sessionId }: { sessionId: string }) {
  const { user } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [statusText, setStatusText] = useState('');
  const bottomRef = useState<HTMLDivElement | null>(null);

  useEffect(() => { setMessages([]); setStatusText(''); }, [sessionId]);

  const scrollToBottom = useCallback((el: HTMLDivElement | null) => {
    el?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  const send = useCallback(async () => {
    const question = input.trim();
    if (!question || streaming || !user) return;
    setInput('');
    setStreaming(true);

    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: 'user', content: question };
    const assistantId = crypto.randomUUID();
    const assistantMsg: ChatMessage = { id: assistantId, role: 'assistant', content: '', isStreaming: true };
    setMessages((p) => [...p, userMsg, assistantMsg]);

    try {
      let sources: QuerySource[] = [];
      let rewrittenQuery = '';

      for await (const event of streamQuery(sessionId, question, user.token)) {
        if (event.type === 'status') {
          setStatusText(event.data.status === 'retrieving' ? 'Searching knowledge base…' : 'Generating answer…');
        } else if (event.type === 'retrieval') {
          rewrittenQuery = event.data.rewritten_query;
          setStatusText('');
        } else if (event.type === 'delta') {
          setMessages((p) => p.map((m) => m.id === assistantId ? { ...m, content: m.content + event.data.text } : m));
        } else if (event.type === 'done') {
          sources = event.data.sources;
          setStatusText('');
        } else if (event.type === 'error') {
          setMessages((p) => p.map((m) => m.id === assistantId ? { ...m, content: `Error: ${event.data.error}`, isStreaming: false } : m));
        }
      }
      setMessages((p) => p.map((m) => m.id === assistantId ? { ...m, isStreaming: false, sources, rewrittenQuery } : m));
    } catch (err) {
      setMessages((p) => p.map((m) => m.id === assistantId ? { ...m, content: `Failed: ${err instanceof Error ? err.message : 'Unknown error'}`, isStreaming: false } : m));
    } finally {
      setStreaming(false);
      setStatusText('');
    }
  }, [input, streaming, user, sessionId]);

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 gap-3 text-center select-none">
              <div className="w-14 h-14 rounded-2xl bg-indigo-600/15 flex items-center justify-center">
                <svg className="w-7 h-7 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
              </div>
              <h2 className="text-lg font-semibold text-white">How can I help you?</h2>
              <p className="text-sm text-gray-500 max-w-xs">
                Ask anything about your uploaded documents. Upload files from the Documents page.
              </p>
            </div>
          ) : (
            messages.map((m) => <Message key={m.id} msg={m} />)
          )}
          {statusText && (
            <div className="flex gap-3 items-center">
              <div className="w-7 h-7 rounded-full bg-indigo-600/20 flex items-center justify-center flex-shrink-0">
                <div className="w-3.5 h-3.5 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
              </div>
              <span className="text-sm text-gray-500 italic">{statusText}</span>
            </div>
          )}
          <div ref={scrollToBottom} />
        </div>
      </div>

      {/* Input */}
      <div className="px-4 pb-6 pt-2 max-w-3xl mx-auto w-full">
        <div className="flex items-end gap-2 bg-[#2f2f2f] rounded-2xl px-4 py-3 border border-white/5 focus-within:border-indigo-500/50 transition-colors">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
            placeholder="Message RAG Studio…"
            disabled={streaming}
            rows={1}
            className="flex-1 bg-transparent text-sm text-gray-100 placeholder-gray-500 resize-none outline-none leading-6 max-h-40 overflow-y-auto"
          />
          <button
            onClick={send}
            disabled={streaming || !input.trim()}
            className="w-8 h-8 flex items-center justify-center rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed transition-all flex-shrink-0"
          >
            {streaming
              ? <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              : <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /></svg>
            }
          </button>
        </div>
        <p className="text-center text-xs text-gray-600 mt-2">
          Shift+Enter for new line · answers grounded in your uploaded documents
        </p>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ChatPage() {
  const { user } = useAuth();
  const [activeId, setActiveId] = useState<string | null>(null);

  const { data: sessions = [], mutate } = useSWR<SessionListItem[]>(
    user ? 'sessions' : null,
    () => listSessions(user!.token),
    { refreshInterval: 15000 }
  );

  const handleCreate = useCallback(async () => {
    if (!user) return;
    const s = await createSession(user.token);
    await mutate();
    setActiveId(s.session_id);
  }, [user, mutate]);

  const handleDelete = useCallback(async (id: string) => {
    if (!user) return;
    await deleteSession(id, user.token);
    await mutate();
    if (activeId === id) setActiveId(null);
  }, [user, mutate, activeId]);

  return (
    <div className="flex h-screen bg-[#212121]">
      <Sidebar
        sessions={sessions}
        activeId={activeId}
        onSelect={setActiveId}
        onCreate={handleCreate}
        onDelete={handleDelete}
      />

      <main className="flex-1 flex flex-col overflow-hidden">
        {activeId ? (
          <ChatArea sessionId={activeId} />
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center gap-4 select-none">
            <div className="w-14 h-14 rounded-2xl bg-indigo-600/15 flex items-center justify-center">
              <svg className="w-7 h-7 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
            </div>
            <div className="text-center">
              <h2 className="text-xl font-semibold text-white">RAG Studio</h2>
              <p className="mt-1 text-sm text-gray-500">Select a chat or create a new one to get started</p>
            </div>
            <button
              onClick={handleCreate}
              className="mt-2 px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors"
            >
              New chat
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
