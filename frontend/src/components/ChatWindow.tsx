'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/lib/auth';
import { streamQuery } from '@/lib/api';
import CitationCard from './CitationCard';
import type { ChatMessage, QuerySource } from '@/types/rag';

interface Props {
  sessionId: string;
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} gap-3`}>
      {!isUser && (
        <div
          className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 mt-1"
          style={{ background: 'rgba(99,102,241,0.2)' }}
        >
          <svg className="w-4 h-4" style={{ color: 'var(--accent)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        </div>
      )}

      <div className={`max-w-2xl ${isUser ? 'items-end' : 'items-start'} flex flex-col gap-2`}>
        <div
          className="px-4 py-3 rounded-2xl text-sm leading-relaxed"
          style={
            isUser
              ? { background: 'var(--accent)', color: 'white', borderBottomRightRadius: '4px' }
              : { background: 'var(--surface-2)', color: 'var(--text)', borderBottomLeftRadius: '4px', border: '1px solid var(--border-2)' }
          }
        >
          {msg.content}
          {msg.isStreaming && (
            <span className="inline-block w-1.5 h-4 ml-1 bg-indigo-400 rounded-sm animate-pulse align-middle" />
          )}
        </div>

        {msg.rewrittenQuery && msg.rewrittenQuery !== msg.content && (
          <p className="text-xs px-1" style={{ color: 'var(--text-muted)' }}>
            Searched: &ldquo;{msg.rewrittenQuery}&rdquo;
          </p>
        )}

        {msg.sources && msg.sources.length > 0 && (
          <div className="w-full">
            <CitationCard sources={msg.sources} />
          </div>
        )}
      </div>
    </div>
  );
}

function StatusLine({ text }: { text: string }) {
  return (
    <div className="flex justify-start gap-3">
      <div
        className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0"
        style={{ background: 'rgba(99,102,241,0.1)' }}
      >
        <div className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
      <div
        className="flex items-center gap-2 px-4 py-2.5 rounded-2xl text-sm"
        style={{ background: 'var(--surface-2)', color: 'var(--text-muted)', border: '1px solid var(--border-2)' }}
      >
        {text}
      </div>
    </div>
  );
}

export default function ChatWindow({ sessionId }: Props) {
  const { user } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [statusText, setStatusText] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setMessages([]);
    setStatusText('');
  }, [sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, statusText]);

  const sendMessage = useCallback(async () => {
    const question = input.trim();
    if (!question || streaming || !user) return;

    setInput('');
    setStreaming(true);
    setStatusText('');

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: question,
    };

    const assistantId = crypto.randomUUID();
    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      isStreaming: true,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);

    try {
      let rewrittenQuery = '';
      let sources: QuerySource[] = [];

      for await (const event of streamQuery(sessionId, question, user.token)) {
        if (event.type === 'status') {
          setStatusText(
            event.data.status === 'retrieving' ? 'Searching knowledge base…' : 'Generating answer…'
          );
        } else if (event.type === 'retrieval') {
          rewrittenQuery = event.data.rewritten_query;
          setStatusText('');
        } else if (event.type === 'delta') {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: m.content + event.data.text } : m
            )
          );
        } else if (event.type === 'done') {
          sources = event.data.sources;
          setStatusText('');
        } else if (event.type === 'error') {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: `Error: ${event.data.error}`, isStreaming: false }
                : m
            )
          );
        }
      }

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId ? { ...m, isStreaming: false, sources, rewrittenQuery } : m
        )
      );
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                content: `Failed to get a response: ${err instanceof Error ? err.message : 'Unknown error'}`,
                isStreaming: false,
              }
            : m
        )
      );
    } finally {
      setStreaming(false);
      setStatusText('');
      inputRef.current?.focus();
    }
  }, [input, streaming, user, sessionId]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
            <p className="text-base font-medium" style={{ color: 'var(--text-muted)' }}>
              Ask anything about your uploaded documents
            </p>
            <p className="text-sm" style={{ color: 'var(--border-2)' }}>
              Shift+Enter for a new line, Enter to send
            </p>
          </div>
        ) : (
          messages.map((msg) => <MessageBubble key={msg.id} msg={msg} />)
        )}
        {statusText && <StatusLine text={statusText} />}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div
        className="px-6 py-4"
        style={{ borderTop: '1px solid var(--border-2)', background: 'var(--surface)' }}
      >
        <div
          className="flex items-end gap-3 rounded-xl px-4 py-3"
          style={{ background: 'var(--surface-2)', border: '1px solid var(--border-2)' }}
        >
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about your documents…"
            disabled={streaming}
            rows={1}
            className="flex-1 resize-none text-sm outline-none bg-transparent leading-6"
            style={{
              color: 'var(--text)',
              maxHeight: '160px',
              overflowY: 'auto',
            }}
          />
          <button
            onClick={sendMessage}
            disabled={streaming || !input.trim()}
            className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            style={{ background: 'var(--accent)', color: 'white' }}
            onMouseEnter={(e) =>
              !streaming && (e.currentTarget.style.background = 'var(--accent-hover)')
            }
            onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--accent)')}
          >
            {streaming ? (
              <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
