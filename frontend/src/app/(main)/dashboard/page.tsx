'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import DocumentUploader from '@/components/DocumentUploader';
import DocumentList from '@/components/DocumentList';
import type { DocumentUploadResponse } from '@/types/rag';

export default function DocumentsPage() {
  const [uploadedDocs, setUploadedDocs] = useState<DocumentUploadResponse[]>([]);
  const { user, logout } = useAuth();
  const router = useRouter();

  return (
    <div className="flex h-screen bg-[#212121]">
      {/* Minimal sidebar */}
      <aside className="w-64 flex flex-col h-full bg-[#171717] border-r border-white/5">
        <div className="p-3 border-b border-white/5">
          <Link
            href="/chat"
            className="flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-medium text-gray-300 hover:bg-white/5 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            Back to chat
          </Link>
        </div>
        <div className="flex-1" />
        <div className="border-t border-white/5 p-2">
          <div className="flex items-center gap-2.5 px-3 py-2 text-sm text-gray-500">
            <div className="w-6 h-6 rounded-full bg-indigo-600 flex items-center justify-center text-xs text-white font-semibold">
              {user?.email?.[0]?.toUpperCase() ?? 'U'}
            </div>
            <span className="truncate flex-1 text-gray-400">{user?.email}</span>
            <button onClick={() => { logout(); router.push('/login'); }} title="Sign out" className="hover:text-red-400 transition-colors">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
            </button>
          </div>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-8 py-10">
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-white">Documents</h1>
            <p className="mt-1 text-sm text-gray-500">
              Upload documents to build your knowledge base. Supported: PDF, DOCX, TXT, HTML, Markdown.
            </p>
          </div>
          <DocumentUploader onUploaded={(doc) => setUploadedDocs((p) => [doc, ...p])} />
          <div className="mt-8">
            <DocumentList pendingDocs={uploadedDocs} />
          </div>
        </div>
      </main>
    </div>
  );
}
