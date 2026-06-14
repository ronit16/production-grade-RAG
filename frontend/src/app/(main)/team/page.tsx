'use client';

import { useState, useCallback } from 'react';
import useSWR from 'swr';
import { useAuth } from '@/lib/auth';
import { listUsers, changeUserRole, deactivateUser, generateInvite } from '@/lib/api';
import AppShell from '@/components/AppShell';
import type { TeamMember, InviteResponse, UserRole } from '@/types/rag';

const ROLE_BADGE: Record<UserRole, string> = {
  owner:  'bg-amber-900/60 text-amber-300',
  admin:  'bg-indigo-900/60 text-indigo-300',
  member: 'bg-gray-700 text-gray-300',
};

function fmtDate(s: string | null): string {
  if (!s) return 'Never';
  return new Date(s).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

export default function TeamPage() {
  const { user } = useAuth();
  const isOwner = user?.role === 'owner';
  const canManage = user?.role === 'owner' || user?.role === 'admin';

  const [invite, setInvite] = useState<InviteResponse | null>(null);
  const [inviteLoading, setInviteLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const { data: members = [], mutate } = useSWR<TeamMember[]>(
    user && canManage ? 'team-members' : null,
    () => listUsers(user!.token),
  );

  const handleGenerateInvite = useCallback(async () => {
    if (!user) return;
    setInviteLoading(true);
    try {
      const result = await generateInvite(user.token);
      setInvite(result);
    } catch { /* ignore */ }
    finally { setInviteLoading(false); }
  }, [user]);

  const handleCopy = useCallback(() => {
    if (!invite) return;
    const url = `${window.location.origin}/register?invite=${invite.invite_code}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [invite]);

  const handleRoleChange = useCallback(async (userId: string, role: string) => {
    if (!user) return;
    await changeUserRole(userId, role, user.token);
    mutate();
  }, [user, mutate]);

  const handleDeactivate = useCallback(async (m: TeamMember) => {
    if (!user) return;
    if (!window.confirm(`Deactivate ${m.username ?? m.email}? They will lose access immediately.`)) return;
    await deactivateUser(m.user_id, user.token);
    mutate();
  }, [user, mutate]);

  if (!canManage) {
    return (
      <AppShell>
        <div className="flex-1 flex items-center justify-center">
          <p className="text-gray-500 text-sm">You don&apos;t have permission to manage the team.</p>
        </div>
      </AppShell>
    );
  }

  const inviteUrl = invite ? `${typeof window !== 'undefined' ? window.location.origin : ''}/register?invite=${invite.invite_code}` : '';

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-8 py-10">
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-white">Team</h1>
            <p className="mt-1 text-sm text-gray-500">Manage members and invite new people to your organization.</p>
          </div>

          {/* Invite section */}
          <div className="rounded-xl bg-[#2a2a2a] border border-white/5 p-5 mb-8">
            <h2 className="text-sm font-semibold text-white mb-1">Invite a team member</h2>
            <p className="text-xs text-gray-500 mb-4">
              Generate a single-use invite link. The link expires in 7 days.
            </p>
            {!invite ? (
              <button
                onClick={handleGenerateInvite}
                disabled={inviteLoading}
                className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
              >
                {inviteLoading ? 'Generating…' : 'Generate invite link'}
              </button>
            ) : (
              <div className="space-y-2">
                <div className="flex gap-2">
                  <input
                    readOnly
                    value={inviteUrl}
                    className="flex-1 bg-[#1a1a1a] border border-white/10 rounded-lg px-3 py-2 text-xs text-gray-300 font-mono outline-none"
                  />
                  <button
                    onClick={handleCopy}
                    className="px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-sm text-gray-300 transition-colors flex-shrink-0"
                  >
                    {copied ? '✓ Copied' : 'Copy'}
                  </button>
                </div>
                <p className="text-xs text-gray-600">
                  Expires {new Date(invite.expires_at).toLocaleDateString()} · Single use
                </p>
                <button
                  onClick={() => { setInvite(null); setCopied(false); }}
                  className="text-xs text-gray-600 hover:text-gray-400 transition-colors"
                >
                  Generate a new one
                </button>
              </div>
            )}
          </div>

          {/* Members table */}
          <div>
            <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">
              Members · {members.length}
            </h2>
            <div className="rounded-xl border border-white/5 overflow-hidden">
              {members.map((m, idx) => (
                <div
                  key={m.user_id}
                  className={`flex items-center gap-3 px-4 py-3 ${idx < members.length - 1 ? 'border-b border-white/5' : ''}`}
                >
                  {/* Avatar */}
                  <div className="w-8 h-8 rounded-full bg-indigo-600/60 flex items-center justify-center text-xs text-white font-semibold flex-shrink-0">
                    {(m.username ?? m.email)[0].toUpperCase()}
                  </div>
                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-white truncate">{m.username ?? m.email}</p>
                    <p className="text-xs text-gray-500 truncate">{m.email} · Last login {fmtDate(m.last_login)}</p>
                  </div>
                  {/* Role badge / dropdown */}
                  {m.role === 'owner' || !isOwner ? (
                    <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${ROLE_BADGE[m.role as UserRole]}`}>
                      {m.role}
                    </span>
                  ) : (
                    <select
                      value={m.role}
                      onChange={(e) => handleRoleChange(m.user_id, e.target.value)}
                      className="text-xs bg-[#2a2a2a] border border-white/10 text-gray-300 rounded-lg px-2 py-1 outline-none cursor-pointer"
                    >
                      <option value="admin">admin</option>
                      <option value="member">member</option>
                    </select>
                  )}
                  {/* Deactivate */}
                  {isOwner && m.role !== 'owner' && m.user_id !== user?.user_id && (
                    <button
                      onClick={() => handleDeactivate(m)}
                      title="Deactivate user"
                      className="p-1 rounded text-gray-600 hover:text-red-400 transition-colors flex-shrink-0"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                      </svg>
                    </button>
                  )}
                </div>
              ))}
              {members.length === 0 && (
                <div className="px-4 py-8 text-center text-sm text-gray-600">No members yet.</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
