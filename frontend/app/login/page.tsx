'use client';
import { Suspense, useState } from 'react';
import { useRouter } from 'next/navigation';
import { SynertiaLoginShell, SynertiaField, IconUser, IconLock } from '@globalwatch-lda/synertia-ui';

function LoginInner() {
  const router = useRouter();
  const [mode, setMode] = useState<'login' | 'forgot'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Forgot-password state.
  const [forgotLogin, setForgotLogin] = useState('');
  const [forgotMsg, setForgotMsg] = useState<string | null>(null);
  const [devLink, setDevLink] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        setErr(res.status === 401 ? 'Credenciais inválidas.' : 'Não foi possível entrar. Tente novamente.');
        setBusy(false);
        return;
      }
      router.replace('/');
      router.refresh();
    } catch {
      setErr('Erro de ligação ao servidor.');
      setBusy(false);
    }
  }

  async function submitForgot(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setForgotMsg(null);
    setDevLink(null);
    try {
      const res = await fetch('/api/auth/forgot', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ login: forgotLogin }),
      });
      const data = res.ok ? await res.json().catch(() => ({})) : {};
      setForgotMsg('Se a conta existir, enviámos um email com o link de recuperação.');
      if (data?.dev_link) setDevLink(data.dev_link); // staging convenience only
    } catch {
      setForgotMsg('Se a conta existir, enviámos um email com o link de recuperação.');
    } finally {
      setBusy(false);
    }
  }

  if (mode === 'forgot') {
    return (
      <SynertiaLoginShell clientLogoSrc="/ds-logo.svg" productName="DS Matrix" accent="#a91b60">
        <form onSubmit={submitForgot} className="space-y-3">
          <p className="text-sm text-ink-500">
            Introduza o seu utilizador ou email e enviamos-lhe um link para repor a palavra-passe.
          </p>
          <SynertiaField
            icon={<IconUser />}
            value={forgotLogin}
            onChange={(e) => setForgotLogin(e.target.value)}
            autoComplete="username"
            placeholder="Utilizador ou email"
          />
          {forgotMsg && <p className="text-sm text-ink-600">{forgotMsg}</p>}
          {devLink && (
            <p className="text-xs text-ink-400 break-all">
              Link (staging): <a className="text-ds-700 underline" href={devLink}>{devLink}</a>
            </p>
          )}
          <button type="submit" disabled={busy || !forgotLogin} className="btn-primary w-full justify-center py-2.5">
            {busy ? 'A enviar …' : 'Enviar link de recuperação'}
          </button>
          <button
            type="button"
            onClick={() => { setMode('login'); setForgotMsg(null); setDevLink(null); }}
            className="w-full text-center text-sm text-ink-500 hover:text-ink-700"
          >
            ← Voltar ao início de sessão
          </button>
        </form>
      </SynertiaLoginShell>
    );
  }

  return (
    <SynertiaLoginShell clientLogoSrc="/ds-logo.svg" productName="DS Matrix" accent="#a91b60">
      <form onSubmit={submit} className="space-y-3">
        <SynertiaField
          icon={<IconUser />}
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          placeholder="Utilizador"
        />
        <SynertiaField
          icon={<IconLock />}
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          placeholder="Palavra-passe"
        />
        {err && <p className="text-sm text-ds-700">{err}</p>}
        <button type="submit" disabled={busy || !password} className="btn-primary w-full justify-center py-2.5">
          {busy ? 'A entrar …' : 'Entrar'}
        </button>
        <button
          type="button"
          onClick={() => { setMode('forgot'); setErr(null); }}
          className="w-full text-center text-sm text-ink-500 hover:text-ink-700"
        >
          Esqueceu-se da palavra-passe?
        </button>
      </form>
    </SynertiaLoginShell>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<p className="text-ink-400">A carregar …</p>}>
      <LoginInner />
    </Suspense>
  );
}
