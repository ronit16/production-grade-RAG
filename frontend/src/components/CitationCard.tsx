'use client';

import { useState } from 'react';
import type { QuerySource } from '@/types/rag';

interface Props {
  sources: QuerySource[];
}

export default function CitationCard({ sources }: Props) {
  const [expanded, setExpanded] = useState<number | null>(null);

  if (sources.length === 0) return null;

  return (
    <div className="mt-4 space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
        Sources ({sources.length})
      </p>
      {sources.map((src, i) => (
        <div
          key={i}
          className="rounded-lg overflow-hidden"
          style={{ background: 'var(--surface-2)', border: '1px solid var(--border-2)' }}
        >
          <button
            className="flex items-center gap-3 w-full px-4 py-3 text-left"
            onClick={() => setExpanded(expanded === i ? null : i)}
          >
            <span
              className="w-5 h-5 rounded flex items-center justify-center text-xs font-bold flex-shrink-0"
              style={{ background: 'rgba(99,102,241,0.2)', color: 'var(--accent)' }}
            >
              {i + 1}
            </span>
            <span className="flex-1 min-w-0">
              <span className="text-sm font-medium block truncate" style={{ color: 'var(--text)' }}>
                {src.filename}
              </span>
              {(src.page_number != null || src.section) && (
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  {src.section && `${src.section}`}
                  {src.section && src.page_number != null && ' · '}
                  {src.page_number != null && `Page ${src.page_number}`}
                </span>
              )}
            </span>
            <span
              className="text-xs px-2 py-0.5 rounded"
              style={{ background: 'var(--border-2)', color: 'var(--text-muted)' }}
            >
              {(src.score * 100).toFixed(0)}%
            </span>
            <svg
              className={`w-4 h-4 flex-shrink-0 transition-transform ${expanded === i ? 'rotate-180' : ''}`}
              style={{ color: 'var(--text-muted)' }}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {expanded === i && (
            <div
              className="px-4 pb-4 text-xs leading-relaxed"
              style={{ color: 'var(--text-muted)', borderTop: '1px solid var(--border)' }}
            >
              <div className="pt-3 font-mono whitespace-pre-wrap break-words">
                {src.chunk_text}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
