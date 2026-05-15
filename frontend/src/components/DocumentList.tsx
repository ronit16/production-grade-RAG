'use client';

import useSWR from 'swr';
import { useAuth } from '@/lib/auth';
import { getDocumentStatus } from '@/lib/api';
import type { DocumentUploadResponse, DocumentStatusResponse, DocumentStatus } from '@/types/rag';

const STATUS_COLORS: Record<DocumentStatus, string> = {
  pending: '#f59e0b',
  processing: '#6366f1',
  ready: '#10b981',
  failed: '#ef4444',
};

const STATUS_LABELS: Record<DocumentStatus, string> = {
  pending: 'Pending',
  processing: 'Processing',
  ready: 'Ready',
  failed: 'Failed',
};

function StatusBadge({ status }: { status: DocumentStatus }) {
  const color = STATUS_COLORS[status];
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium"
      style={{ background: `${color}20`, color }}
    >
      {(status === 'pending' || status === 'processing') && (
        <span
          className="w-1.5 h-1.5 rounded-full animate-pulse"
          style={{ background: color }}
        />
      )}
      {status === 'ready' && (
        <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
        </svg>
      )}
      {status === 'failed' && (
        <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
        </svg>
      )}
      {STATUS_LABELS[status]}
    </span>
  );
}

function DocumentRow({ doc }: { doc: DocumentUploadResponse }) {
  const { user } = useAuth();

  const { data } = useSWR<DocumentStatusResponse>(
    user ? ['doc-status', doc.document_id] : null,
    () => getDocumentStatus(doc.document_id, user!.token),
    {
      refreshInterval: (data) =>
        data?.status === 'ready' || data?.status === 'failed' ? 0 : 2000,
    }
  );

  const status = data?.status ?? doc.status;
  const chunkCount = data?.chunk_count;
  const processingMs = data?.processing_ms;

  return (
    <div
      className="flex items-center gap-4 px-5 py-4"
      style={{ borderBottom: '1px solid var(--border)' }}
    >
      <div
        className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
        style={{ background: 'var(--surface-2)' }}
      >
        <svg className="w-5 h-5" style={{ color: 'var(--text-muted)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
        </svg>
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate" style={{ color: 'var(--text)' }}>
          {doc.filename}
        </p>
        <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
          {chunkCount != null && `${chunkCount} chunks`}
          {chunkCount != null && processingMs != null && ' · '}
          {processingMs != null && `${(processingMs / 1000).toFixed(1)}s`}
        </p>
      </div>
      <StatusBadge status={status} />
    </div>
  );
}

interface Props {
  pendingDocs: DocumentUploadResponse[];
}

export default function DocumentList({ pendingDocs }: Props) {
  if (pendingDocs.length === 0) {
    return (
      <div
        className="rounded-xl flex flex-col items-center justify-center py-16 gap-3"
        style={{ background: 'var(--surface)', border: '1px solid var(--border-2)' }}
      >
        <svg className="w-10 h-10" style={{ color: 'var(--border-2)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
          No documents yet. Upload one above to get started.
        </p>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-muted)' }}>
        Uploaded documents
      </h2>
      <div
        className="rounded-xl overflow-hidden"
        style={{ background: 'var(--surface)', border: '1px solid var(--border-2)' }}
      >
        {pendingDocs.map((doc) => (
          <DocumentRow key={doc.document_id} doc={doc} />
        ))}
      </div>
    </div>
  );
}
