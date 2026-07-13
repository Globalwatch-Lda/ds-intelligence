'use client';
import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { SynertiaLoginShell } from '@globalwatch-lda/synertia-ui';

function UnsubInner() {
  const params = useSearchParams();
  const token = params.get('t') ?? '';
  const [state, setState] = useState<'checking' | 'valid' | 'invalid' | 'done'>('checking');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) { setState('invalid'); return; }
    fetch(`/api/public/unsubscribe/check?t=${encodeURIComponent(token)}`)
      .then((r) => (r.ok ? r.json() : { valid: false }))
      .then((d) => setState(d?.valid ? 'valid' : 'invalid'))
      .catch(() => setState('invalid'));
  }, [token]);

  async function confirm() {
    setBusy(true);
    try {
      const res = await fetch('/api/public/unsubscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ t: token }),
      });
      setState(res.ok ? 'done' : 'invalid');
    } catch {
      setState('invalid');
    } finally {
      setBusy(false);
    }
  }

  return (
    <SynertiaLoginShell clientLogoSrc="/ds-logo.svg" productName="DS Matrix" accent="#a91b60">
      {state === 'checking' && <p className="text-sm text-ink-400">A validar a ligação …</p>}

      {state === 'invalid' && (
        <p className="text-sm text-ds-700">Esta ligação de cancelamento é inválida ou já não é válida.</p>
      )}

      {state === 'valid' && (
        <div className="space-y-3">
          <p className="text-sm text-ink-700">
            Deseja deixar de receber comunicações de marketing da <b>DS Crédito</b>?
          </p>
          <button onClick={confirm} disabled={busy} className="btn-primary w-full justify-center py-2.5">
            {busy ? 'A cancelar …' : 'Cancelar subscrição'}
          </button>
        </div>
      )}

      {state === 'done' && (
        <div className="space-y-2">
          <p className="text-sm text-ink-700">✓ Subscrição cancelada.</p>
          <p className="text-sm text-ink-400">Não voltará a receber comunicações de marketing. Obrigado.</p>
        </div>
      )}
    </SynertiaLoginShell>
  );
}

export default function UnsubscribePage() {
  return (
    <Suspense fallback={<p className="text-ink-400">A carregar …</p>}>
      <UnsubInner />
    </Suspense>
  );
}
