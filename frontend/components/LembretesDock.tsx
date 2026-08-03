'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { api } from '../lib/api';
import type { Nota } from './LeadNotas';
import { IconSino } from './LeadNotas';

type Lembretes = { vencidos: Nota[]; proximos: Nota[]; total_vencidos: number };

const fmt = (v: string | null) =>
  v ? new Date(v).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—';

/**
 * Sino de lembretes — canto inferior esquerdo, ao lado do dock da Ana.
 *
 * Faz polling de minuto a minuto (o worker de email corre na mesma cadência, por
 * isso não vale a pena ser mais fino) e, quando um lembrete vence com a app
 * aberta, abre-se sozinho uma vez: foi o que o cliente pediu com "avisar para o
 * ecrã também". Abrir sozinho só na PRIMEIRA vez que cada lembrete aparece —
 * reabrir a cada ciclo tornaria a plataforma inutilizável.
 */
export default function LembretesDock() {
  const { data, mutate } = useSWR<Lembretes>('/api/lead-notas/lembretes', api, {
    refreshInterval: 60_000,
    revalidateOnFocus: true,
  });
  const [aberto, setAberto] = useState(false);
  const [jaAvisados, setJaAvisados] = useState<Set<number>>(new Set());

  const vencidos = data?.vencidos ?? [];
  const proximos = data?.proximos ?? [];

  useEffect(() => {
    if (!vencidos.length) return;
    const novos = vencidos.filter((n) => !jaAvisados.has(n.id));
    if (!novos.length) return;
    setAberto(true);
    setJaAvisados((s) => new Set([...s, ...novos.map((n) => n.id)]));
  }, [vencidos, jaAvisados]);

  async function dispensar(id: number) {
    await api(`/api/lead-notas/${id}`, { method: 'PATCH', body: JSON.stringify({ visto: true }) });
    mutate();
  }

  async function concluir(id: number) {
    await api(`/api/lead-notas/${id}`, { method: 'PATCH', body: JSON.stringify({ concluida: true }) });
    mutate();
  }

  const total = vencidos.length;

  if (!aberto) {
    return (
      <button
        type="button"
        onClick={() => setAberto(true)}
        title={total ? `${total} lembrete(s) por tratar` : 'Lembretes'}
        // Canto inferior direito, ACIMA do dock da Ana: à esquerda ficava por cima
        // do rodapé de utilizador da barra lateral.
        className="fixed bottom-20 right-6 z-40 inline-flex h-11 w-11 items-center justify-center rounded-full bg-white shadow-lg border border-ink-100 text-ink-700 hover:text-ds-600"
      >
        <IconSino className="h-5 w-5" />
        {total > 0 && (
          <span className="absolute -top-1 -right-1 min-w-[18px] rounded-full bg-ds-500 px-1 text-[10px] font-semibold leading-[18px] text-white">
            {total}
          </span>
        )}
      </button>
    );
  }

  return (
    <div className="fixed bottom-20 right-6 z-40 w-[360px] max-w-[92vw] rounded-2xl border border-ink-100 bg-white shadow-2xl">
      <div className="flex items-center justify-between border-b border-ink-100 px-4 py-3">
        <div className="flex items-center gap-2">
          <IconSino className="text-ds-600" />
          <span className="font-semibold text-ink-900">Lembretes</span>
          {total > 0 && <span className="chip chip-alert">{total} por tratar</span>}
        </div>
        <button onClick={() => setAberto(false)} className="text-xl leading-none text-ink-400 hover:text-ds-600">×</button>
      </div>

      <div className="max-h-[380px] overflow-y-auto px-4 py-3 text-sm">
        {!vencidos.length && !proximos.length && (
          <p className="text-ink-400">Sem lembretes marcados. Crie um a partir de uma lead.</p>
        )}

        {vencidos.map((n) => (
          <div key={n.id} className="mb-3 rounded-xl border border-ds-200 bg-ds-50/50 p-3">
            <div className="text-xs font-medium text-ds-700">{fmt(n.lembrete_em)}</div>
            <Link href={`/leads?lead=${n.lead_crm_id}`} className="text-ink-900 hover:text-ds-600">
              {n.lead_nome || `Lead ${n.lead_crm_id}`}
            </Link>
            <div className="mt-1 whitespace-pre-wrap text-ink-700">{n.texto}</div>
            <div className="mt-2 flex gap-3 text-xs text-ink-400">
              <button className="hover:text-ds-600" onClick={() => concluir(n.id)}>Marcar tratado</button>
              <button className="hover:text-ds-600" onClick={() => dispensar(n.id)}>Dispensar</button>
            </div>
          </div>
        ))}

        {proximos.length > 0 && (
          <>
            <div className="mb-2 mt-1 text-xs font-medium uppercase tracking-wide text-ink-400">A chegar</div>
            {proximos.map((n) => (
              <div key={n.id} className="mb-2 rounded-xl border border-ink-100 p-3">
                <div className="text-xs text-ink-400">{fmt(n.lembrete_em)}</div>
                <Link href={`/leads?lead=${n.lead_crm_id}`} className="text-ink-900 hover:text-ds-600">
                  {n.lead_nome || `Lead ${n.lead_crm_id}`}
                </Link>
                <div className="mt-1 line-clamp-2 text-ink-700">{n.texto}</div>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
