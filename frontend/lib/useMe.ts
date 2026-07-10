'use client';
import useSWR from 'swr';
import { api } from './api';

export type Me = {
  authenticated: boolean;
  username?: string;
  nome?: string;
  role?: string;
  user_id?: number | null;
  can_newsletter?: boolean;
  capabilities?: string[];
  data_scope?: string;
};

// Shared session/capabilities hook. `can(cap)` gates UI on the RBAC capability
// keys returned by /api/auth/me (see backend/app/core/capabilities.py).
export function useMe() {
  const { data, isLoading } = useSWR<Me>('/api/auth/me', api);
  const caps = new Set(data?.capabilities ?? []);
  return {
    me: data,
    isLoading,
    caps,
    can: (cap: string) => caps.has(cap),
  };
}
