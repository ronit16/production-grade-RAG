'use client';

import { useCallback, useRef } from 'react';
import useSWR from 'swr';
import { useAuth } from '@/lib/auth';
import { listDocuments, uploadDocument, deleteDocument } from '@/lib/api';
import AppShell from '@/components/AppShell';
import type { DocumentListItem, DocumentStatus } from '@/types/rag';

const STATUS_STYLES: Record<DocumentStatus, string> = {
  pending:    'bg-gray-700 text-gray-300',
  processing: 'bg-amber-900/60 text-amber-300',
  ready:      'bg-green-900/60 text-green-300',
  failed:     'bg-red-900/60 text-red-300',
};

function fmtBytes(n: number): string {
  if (n >= 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + ' MB';
  if (n >= 1024) return (n / 1024).toFixed(1) + ' KB';
  return n + ' B';
}

function fmtDate(s: string | null): string {
  if (!s) return '—';
  return new Date(s).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function DocRow({
  doc,
  canDelete,
  onDelete,
}: {
  doc: DocumentListItem;
  canDelete: boolean;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="flex items-center gap-3 px-4 py-3 rounded-lg hover:bg-white/3 transition-colors group">
      <svg className="w-5 h-5 text-gray-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-white truncate">{doc.filename}</p>
        <p className="text-xs text-gray-500 mt-0.5">
          {fmtBytes(doc.file_size)} · {doc.chunk_count != null ? `${doc.chunk_count} chunks` : 'processing'} · {fmtDate(doc.created_at)}
        </p>
      </div>
      <span className={`text-xs font-medium px-2 py-0.5 rounded-full flex-shrink-0 ${STATUS_STYLES[doc.status]}`}>
        {doc.status}
      </span>
      {canDelete && (
        <button
          onClick={() => {
            if (window.confirm(`Delete "${doc.filename}"?`)) onDelete(doc.document_id);
          }}
          className="opacity-0 group-hover:opacity-100 p-1 rounded hover:text-red-400 text-gray-500 transition-all flex-shrink-0"
          title="Delete document"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
        </button>
      )}
    </div>
  );
}

export default function DocumentsPage() {
  const { user } = useAuth();
  const fileRef = useRef<HTMLInputElement>(null);
  const canDelete = user?.role === 'owner' || user?.role === 'admin';

  const hasProcessing = (docs: DocumentListItem[]) =>
    docs.some((d) => d.status === 'pending' || d.status === 'processing');

  const { data: docs = [], mutate, isLoading } = useSWR<DocumentListItem[]>(
    user ? 'documents' : null,
    () => listDocuments(user!.token),
    {
      refreshInterval: (d) => (d && hasProcessing(d) ? 3000 : 0),
    },
  );

  const handleFiles = useCallback(async (files: FileList | null) => {
    if (!files || !user) return;
    await Promise.all(
      Array.from(files).map((f) => uploadDocument(f, user.token).catch(() => null))
    );
    mutate();
  }, [user, mutate]);

  const handleDelete = useCallback(async (id: string) => {
    if (!user) return;
    await deleteDocument(id, user.token);
    mutate();
  }, [user, mutate]);

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-8 py-10">
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-white">Documents</h1>
            <p className="mt-1 text-sm text-gray-500">
              Upload documents to build your knowledge base. Supported: PDF, DOCX, TXT, HTML, Markdown.
            </p>
          </div>

          {/* Upload zone */}
          <div
            className="border-2 border-dashed border-white/10 rounded-2xl p-10 text-center hover:border-indigo-500/50 transition-colors cursor-pointer"
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); handleFiles(e.dataTransfer.files); }}
          >
            <svg className="w-10 h-10 text-gray-600 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <p className="text-sm text-gray-400 font-medium">Drop files here or click to upload</p>
            <p className="text-xs text-gray-600 mt-1">PDF, DOCX, TXT, HTML, MD · Max 100 MB</p>
            <input
              ref={fileRef}
              type="file"
              multiple
              accept=".pdf,.docx,.txt,.html,.md,.markdown"
              className="hidden"
              onChange={(e) => handleFiles(e.target.files)}
            />
          </div>

          {/* Document list */}
          <div className="mt-8">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
                All documents
              </h2>
              <span className="text-xs text-gray-600">{docs.length} total</span>
            </div>

            {isLoading && (
              <div className="space-y-2">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="h-14 rounded-lg bg-white/5 animate-pulse" />
                ))}
              </div>
            )}

            {!isLoading && docs.length === 0 && (
              <div className="text-center py-12 text-gray-600 text-sm">
                No documents yet. Upload one above.
              </div>
            )}

            {docs.length > 0 && (
              <div className="space-y-1">
                {docs.map((doc) => (
                  <DocRow
                    key={doc.document_id}
                    doc={doc}
                    canDelete={canDelete}
                    onDelete={handleDelete}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
