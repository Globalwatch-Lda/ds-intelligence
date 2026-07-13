'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { UserPill } from '@globalwatch-lda/synertia-ui';

// DS-specific auth wiring around the shared UserPill: fetch the display name and
// handle logout against the platform's session API.
export default function LogoutButton() {
  const router = useRouter();
  const [nome, setNome] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/auth/me')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d?.nome) setNome(d.nome); })
      .catch(() => {});
  }, []);

  async function logout() {
    try {
      await fetch('/api/auth/logout', { method: 'POST' });
    } catch {
      /* ignore — bounce to login regardless */
    }
    router.replace('/login');
    router.refresh();
  }

  return <UserPill name={nome} onLogout={logout} />;
}
