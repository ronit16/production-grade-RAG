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

function LimitRow({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="flex justify-between text-sm py-2 border-b border-white/5 last:border-0">
      <span className="text-gray-400">{label}</span>
      <span className="text-white font-medium">
        {value == null ? 'Unlimited' : value.toLocaleString()}
      </span>
    </div>
  );
}

export default function SettingsPage() {
  const { user } = useAuth();
  const isOwner = user?.role === 'owner';
  const { data, isLoading, error } = useSWR<TenantInfoResponse>(
    user ? 'tenant-info' : null,
    () => getTenantInfo(user!.token),
  );

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-2xl mx-auto px-8 py-10">
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-white">Settings</h1>
            <p className="mt-1 text-sm text-gray-500">Organization details and plan information.</p>
          </div>

          {isLoading && (
            <div className="space-y-4">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="rounded-xl bg-[#2a2a2a] border border-white/5 p-5 animate-pulse h-32" />
              ))}
            </div>
          )}

          {error && (
            <p className="text-sm text-red-400 bg-red-950/50 border border-red-900 rounded-lg px-4 py-3">
              Failed to load settings: {error.message}
            </p>
          )}

          {data && (
            <div className="space-y-5">
              {/* Organization */}
              <section className="rounded-xl bg-[#2a2a2a] border border-white/5 p-5">
                <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">Organization</h2>
                <div className="space-y-0">
                  <div className="flex justify-between text-sm py-2 border-b border-white/5">
                    <span className="text-gray-400">Name</span>
                    <span className="text-white">{data.tenant.name}</span>
                  </div>
                  <div className="flex justify-between text-sm py-2 border-b border-white/5">
                    <span className="text-gray-400">Slug</span>
                    <span className="text-gray-300 font-mono text-xs">{data.tenant.slug}</span>
                  </div>
                  <div className="flex justify-between text-sm py-2 border-b border-white/5">
                    <span className="text-gray-400">Plan</span>
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded ${PLAN_COLORS[data.tenant.plan] ?? PLAN_COLORS.free}`}>
                      {data.tenant.plan.toUpperCase()}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm py-2 border-b border-white/5">
                    <span className="text-gray-400">Status</span>
                    <span className={data.tenant.is_active ? 'text-green-400' : 'text-red-400'}>
                      {data.tenant.is_active ? 'Active' : 'Suspended'}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm py-2">
                    <span className="text-gray-400">Created</span>
                    <span className="text-gray-300">
                      {data.tenant.created_at ? new Date(data.tenant.created_at).toLocaleDateString() : '—'}
                    </span>
                  </div>
                </div>
              </section>

              {/* Plan limits */}
              <section className="rounded-xl bg-[#2a2a2a] border border-white/5 p-5">
                <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">Plan limits</h2>
                <LimitRow label="Max documents" value={data.limits.max_docs} />
                <LimitRow label="Tokens per day" value={data.limits.tokens_day} />
                <LimitRow label="Requests per second" value={data.limits.rps} />
                <LimitRow label="Max sessions" value={data.limits.max_sessions} />
              </section>

              {/* Account */}
              <section className="rounded-xl bg-[#2a2a2a] border border-white/5 p-5">
                <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">Your account</h2>
                <div className="space-y-0">
                  <div className="flex justify-between text-sm py-2 border-b border-white/5">
                    <span className="text-gray-400">Username</span>
                    <span className="text-white">{user?.username}</span>
                  </div>
                  <div className="flex justify-between text-sm py-2 border-b border-white/5">
                    <span className="text-gray-400">Email</span>
                    <span className="text-gray-300">{user?.email}</span>
                  </div>
                  <div className="flex justify-between text-sm py-2">
                    <span className="text-gray-400">Role</span>
                    <span className="text-indigo-300 font-medium capitalize">{user?.role}</span>
                  </div>
                </div>
              </section>

              {/* Danger zone (owner only) */}
              {isOwner && (
                <section className="rounded-xl bg-red-950/20 border border-red-900/40 p-5">
                  <h2 className="text-xs font-semibold text-red-400 uppercase tracking-wider mb-1">Danger zone</h2>
                  <p className="text-xs text-gray-500 mb-4">Destructive actions cannot be undone.</p>
                  <button
                    disabled
                    title="Contact support to delete your organization"
                    className="px-4 py-2 rounded-lg border border-red-900/60 text-red-500 text-sm font-medium opacity-50 cursor-not-allowed"
                  >
                    Delete organization
                  </button>
                  <p className="text-xs text-gray-600 mt-2">Contact support to delete your organization.</p>
                </section>
              )}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
