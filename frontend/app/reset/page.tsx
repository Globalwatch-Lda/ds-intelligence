'use client';
import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { SynertiaLoginShell, SynertiaField, IconLock } from '@globalwatch-hub/synertia-ui';

function ResetInner() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get('token') ?? '';
  const [state, setState] = useState<'checking' | 'valid' | 'invalid' | 'done'>('checking');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) { setState('invalid'); return; }
    fetch(`/api/auth/reset/validate?token=${encodeURIComponent(token)}`)
      .then((r) => (r.ok ? r.json() : { valid: false }))
      .then((d) => setState(d?.valid ? 'valid' : 'invalid'))
      .catch(() => setState('invalid'));
  }, [token]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (password.length < 8) { setErr('A palavra-passe deve ter pelo menos 8 caracteres.'); return; }
    if (password !== confirm) { setErr('As palavras-passe não coincidem.'); return; }
    setBusy(true);
    try {
      const res = await fetch('/api/auth/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, password }),
      });
      if (!res.ok) {
        const t = await res.text();
        setErr(t.includes('expirado') ? 'Link inválido ou expirado. Peça um novo.' : 'Não foi possível repor a palavra-passe.');
        setBusy(false);
        return;
      }
      setState('done');
      setTimeout(() => router.replace('/login'), 2500);
    } catch {
      setErr('Erro de ligação ao servidor.');
      setBusy(false);
    }
  }

  return (
    <SynertiaLoginShell clientLogoSrc="/ds-logo.svg" productName="DS Matrix" accent="#a91b60">
      {state === 'checking' && <p className="text-sm text-ink-400">A validar o link …</p>}

      {state === 'invalid' && (
        <div className="space-y-3">
          <p className="text-sm text-ds-700">Este link de recuperação é inválido ou expirou.</p>
          <a href="/login" className="btn-primary w-full justify-center py-2.5">Voltar ao início de sessão</a>
        </div>
      )}

      {state === 'done' && (
        <div className="space-y-2">
          <p className="text-sm text-ink-700">✓ Palavra-passe alterada com sucesso.</p>
          <p className="text-sm text-ink-400">A redirecionar para o início de sessão …</p>
        </div>
      )}

      {state === 'valid' && (
        <form onSubmit={submit} className="space-y-3">
          <p className="text-sm text-ink-500">Defina a sua nova palavra-passe (mínimo 8 caracteres).</p>
          <SynertiaField
            icon={<IconLock />}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            placeholder="Nova palavra-passe"
          />
          <SynertiaField
            icon={<IconLock />}
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
            placeholder="Confirmar palavra-passe"
          />
          {err && <p className="text-sm text-ds-700">{err}</p>}
          <button type="submit" disabled={busy} className="btn-primary w-full justify-center py-2.5">
            {busy ? 'A guardar …' : 'Repor palavra-passe'}
          </button>
        </form>
      )}
    </SynertiaLoginShell>
  );
}

export default function ResetPage() {
  return (
    <Suspense fallback={<p className="text-ink-400">A carregar …</p>}>
      <ResetInner />
    </Suspense>
  );
}
