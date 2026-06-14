'use client';

import useSWR from 'swr';
import { useAuth } from '@/lib/auth';
import { getTenantInfo } from '@/lib/api';
import AppShell from '@/components/AppShell';
import type { TenantInfoResponse } from '@/types/rag';

const PLAN_COLORS: Record<string, string> = {
  free: 'bg-gray-700 text-gray-300',
  starter: 'bg-blue-900/60 text-blue-300',
  professional: 'bg-indigo-900/60 text-indigo-300',
  enterprise: 'bg-amber-900/60 text-amber-300',
};

function fmt(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'k';
  return String(n);
}

function StatCard({
  label,
  value,
  limit,
  suffix = '',
}: {
  label: string;
  value: number;
  limit?: number | null;
  suffix?: string;
}) {
  const pct = limit ? Math.min(100, (value / limit) * 100) : null;
  return (
    <div className="rounded-xl bg-[#2a2a2a] border border-white/5 p-5">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">{label}</p>
      <p className="text-2xl font-bold text-white">
        {fmt(value)}{suffix}
        {limit != null && (
          <span className="text-sm font-normal text-gray-500 ml-1">/ {fmt(limit)}</span>
        )}
        {limit == null && limit !== undefined && (
          <span className="text-sm font-normal text-gray-500 ml-1">/ ∞</span>
        )}
      </p>
      {pct !== null && (
        <div className="mt-3 h-1.5 rounded-full bg-white/10">
          <div
            className={`h-1.5 rounded-full transition-all ${pct > 85 ? 'bg-red-500' : pct > 60 ? 'bg-amber-500' : 'bg-indigo-500'}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}

function Skeleton() {
  return (
    <div className="grid grid-cols-2 gap-4">
      {[...Array(4)].map((_, i) => (
        <div key={i} className="rounded-xl bg-[#2a2a2a] border border-white/5 p-5 animate-pulse">
          <div className="h-3 w-20 bg-white/10 rounded mb-3" />
          <div className="h-7 w-24 bg-white/10 rounded" />
        </div>
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const { data, error, isLoading } = useSWR<TenantInfoResponse>(
    user ? 'tenant-info' : null,
    () => getTenantInfo(user!.token),
  );

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-2xl mx-auto">
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className="text-2xl font-bold text-white">Dashboard</h1>
              <p className="text-sm text-gray-500 mt-1">
                {data ? `${data.tenant.name} · ` : ''}
                <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${PLAN_COLORS[data?.tenant.plan ?? 'free'] ?? PLAN_COLORS.free}`}>
                  {(data?.tenant.plan ?? 'free').toUpperCase()}
                </span>
              </p>
            </div>
          </div>

          {isLoading && <Skeleton />}
          {error && (
            <p className="text-sm text-red-400 bg-red-950/50 border border-red-900 rounded-lg px-4 py-3">
              Failed to load stats: {error.message}
            </p>
          )}
          {data && (
            <>
              <div className="grid grid-cols-2 gap-4">
                <StatCard
                  label="Documents"
                  value={data.usage.doc_count}
                  limit={data.limits.max_docs}
                />
                <StatCard
                  label="Tokens today"
                  value={data.usage.tokens_today}
                  limit={data.limits.tokens_day}
                />
                <StatCard
                  label="Active sessions"
                  value={data.usage.session_count}
                  limit={data.limits.max_sessions}
                />
                <StatCard
                  label="Team members"
                  value={data.member_count}
                />
              </div>

              <div className="mt-6 rounded-xl bg-[#2a2a2a] border border-white/5 p-5">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">
                  Queries today
                </p>
                <p className="text-2xl font-bold text-white">{fmt(data.usage.query_count_today)}</p>
              </div>

              <div className="mt-6 rounded-xl bg-[#2a2a2a] border border-white/5 p-5 space-y-2">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">Organization</p>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Name</span>
                  <span className="text-white">{data.tenant.name}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Slug</span>
                  <span className="text-gray-300 font-mono text-xs">{data.tenant.slug}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Created</span>
                  <span className="text-gray-300">
                    {data.tenant.created_at ? new Date(data.tenant.created_at).toLocaleDateString() : '—'}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Your role</span>
                  <span className="text-indigo-300 font-medium capitalize">{user?.role}</span>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </AppShell>
  );
}
