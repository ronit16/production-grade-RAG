'use client';

import { useCallback, useState } from 'react';
import { useAuth } from '@/lib/auth';
import { uploadDocument } from '@/lib/api';
import type { DocumentUploadResponse } from '@/types/rag';

const ACCEPTED = '.pdf,.doc,.docx,.txt,.html,.htm,.md,.markdown';
const MAX_MB = 100;

interface Props {
  onUploaded: (doc: DocumentUploadResponse) => void;
}

export default function DocumentUploader({ onUploaded }: Props) {
  const { user } = useAuth();
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0 || !user?.token) return;
      const file = files[0];

      if (file.size > MAX_MB * 1024 * 1024) {
        setError(`File is too large. Max size is ${MAX_MB} MB.`);
        return;
      }

      setError('');
      setUploading(true);
      try {
        const doc = await uploadDocument(file, user?.token);
        onUploaded(doc);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Upload failed. Please try again.');
      } finally {
        setUploading(false);
      }
    },
    [user?.token, onUploaded]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles]
  );

  return (
    <div>
      <label
        className="relative flex flex-col items-center justify-center w-full h-48 rounded-xl cursor-pointer transition-all"
        style={{
          background: dragging ? 'rgba(99,102,241,0.08)' : 'var(--surface)',
          border: `2px dashed ${dragging ? 'var(--accent)' : 'var(--border-2)'}`,
        }}
        onDragEnter={(e) => { e.preventDefault(); setDragging(true); }}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input
          type="file"
          className="sr-only"
          accept={ACCEPTED}
          onChange={(e) => handleFiles(e.target.files)}
          disabled={uploading}
        />

        {uploading ? (
          <div className="flex flex-col items-center gap-3">
            <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
              Uploading…
            </p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <div
              className="w-12 h-12 rounded-xl flex items-center justify-center"
              style={{ background: 'rgba(99,102,241,0.12)' }}
            >
              <svg
                className="w-6 h-6"
                style={{ color: 'var(--accent)' }}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
            </div>
            <div className="text-center">
              <p className="text-sm font-medium" style={{ color: 'var(--text)' }}>
                Drop a file here, or{' '}
                <span style={{ color: 'var(--accent)' }}>browse</span>
              </p>
              <p className="mt-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                PDF, DOCX, TXT, HTML, Markdown — up to {MAX_MB} MB
              </p>
            </div>
          </div>
        )}
      </label>

      {error && (
        <p
          className="mt-3 text-sm px-4 py-2.5 rounded-lg"
          style={{ background: '#450a0a', color: 'var(--error)', border: '1px solid #7f1d1d' }}
        >
          {error}
        </p>
      )}
    </div>
  );
}
