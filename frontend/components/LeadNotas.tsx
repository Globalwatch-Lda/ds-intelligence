'use client';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';

export type Nota = {
  id: number;
  lead_crm_id: number;
  lead_nome: string | null;
  texto: string;
  data_nota: string | null;
  lembrete_em: string | null;
  lembrete_canais: string[];
  notificado_em: string | null;
  visto_em: string | null;
  concluida_em: string | null;
  criado_por: string;
  criado_por_nome: string | null;
  created_at: string;
};

export type ResumoNotas = Record<
  string,
  { notas: number; proximo_lembrete: string | null; vencido: boolean }
>;

const fmtData = (v: string | null) =>
  v ? new Date(v).toLocaleDateString('pt-PT') : '—';
const fmtInstante = (v: string | null) =>
  v
    ? new Date(v).toLocaleString('pt-PT', {
        day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
      })
    : '—';

// Hoje em formato aceite por <input type="date"> / datetime-local, na hora local
// do browser (nunca UTC — toISOString adiantaria o dia a quem está a leste).
function paraInputLocal(d: Date, comHora: boolean) {
  const p = (n: number) => String(n).padStart(2, '0');
  const dia = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  return comHora ? `${dia}T${p(d.getHours())}:${p(d.getMinutes())}` : dia;
}

/** Atalhos de agendamento — o valor devolvido alimenta o input datetime-local. */
const ATALHOS: { label: string; calcula: () => Date }[] = [
  { label: 'Amanhã 9h', calcula: () => { const d = new Date(); d.setDate(d.getDate() + 1); d.setHours(9, 0, 0, 0); return d; } },
  { label: 'Daqui a 3 dias', calcula: () => { const d = new Date(); d.setDate(d.getDate() + 3); d.setHours(9, 0, 0, 0); return d; } },
  { label: 'Próxima semana', calcula: () => { const d = new Date(); d.setDate(d.getDate() + 7); d.setHours(9, 0, 0, 0); return d; } },
  { label: 'Daqui a 1 mês', calcula: () => { const d = new Date(); d.setMonth(d.getMonth() + 1); d.setHours(9, 0, 0, 0); return d; } },
];

export function IconSino({ className = '' }: { className?: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.7 21a2 2 0 0 1-3.4 0" />
    </svg>
  );
}

export default function LeadNotas({
  leadId,
  leadNome,
  onClose,
  onMudou,
}: {
  leadId: string;
  leadNome: string;
  onClose: () => void;
  onMudou: () => void;
}) {
  const [notas, setNotas] = useState<Nota[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  const [texto, setTexto] = useState('');
  const [dataNota, setDataNota] = useState(paraInputLocal(new Date(), false));
  const [comLembrete, setComLembrete] = useState(true);
  const [lembrete, setLembrete] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    d.setHours(9, 0, 0, 0);
    return paraInputLocal(d, true);
  });
  const [porEmail, setPorEmail] = useState(true);

  async function carregar() {
    setCarregando(true);
    try {
      const r = await api<{ notas: Nota[] }>(`/api/lead-notas/lead/${leadId}`);
      setNotas(r.notas);
      setErro(null);
    } catch (e: any) {
      setErro(e.message);
    } finally {
      setCarregando(false);
    }
  }

  useEffect(() => { carregar(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [leadId]);

  // Esc fecha — o painel é modal e tapa a tabela toda.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  async function guardar() {
    if (!texto.trim()) return;
    setGuardando(true);
    try {
      await api('/api/lead-notas', {
        method: 'POST',
        body: JSON.stringify({
          lead_crm_id: Number(leadId),
          lead_nome: leadNome,
          texto,
          data_nota: dataNota || null,
          // O input datetime-local não tem fuso: converte-se aqui para ISO com
          // offset, para o servidor guardar o instante e não uma hora à solta.
          lembrete_em: comLembrete && lembrete ? new Date(lembrete).toISOString() : null,
          lembrete_canais: comLembrete ? (porEmail ? ['app', 'email'] : ['app']) : [],
        }),
      });
      setTexto('');
      await carregar();
      onMudou();
    } catch (e: any) {
      setErro(e.message);
    } finally {
      setGuardando(false);
    }
  }

  async function alterar(id: number, patch: Record<string, unknown>) {
    try {
      await api(`/api/lead-notas/${id}`, { method: 'PATCH', body: JSON.stringify(patch) });
      await carregar();
      onMudou();
    } catch (e: any) {
      setErro(e.message);
    }
  }

  async function apagar(id: number) {
    try {
      await api(`/api/lead-notas/${id}`, { method: 'DELETE' });
      await carregar();
      onMudou();
    } catch (e: any) {
      setErro(e.message);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-ink-900/40 p-4 overflow-y-auto"
         onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-[640px] max-w-full mt-10 mb-10"
           onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-ink-100 flex items-start justify-between gap-4">
          <div>
            <div className="font-semibold text-ink-900">Notas e lembretes</div>
            <div className="text-xs text-ink-400">{leadNome}</div>
          </div>
          <button onClick={onClose} className="text-ink-400 hover:text-ds-600 text-xl leading-none">×</button>
        </div>

        <div className="px-5 py-4 space-y-3 border-b border-ink-100">
          <textarea
            className="w-full rounded-xl border border-ink-100 px-3 py-2 text-sm min-h-[80px]"
            placeholder="O que ficou combinado com esta lead?"
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
          />
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <label className="flex items-center gap-2 text-ink-700">
              Data da nota
              <input type="date" value={dataNota} onChange={(e) => setDataNota(e.target.value)}
                     className="rounded-lg border border-ink-100 px-2 py-1 text-sm" />
            </label>
            <label className="flex items-center gap-2 text-ink-700">
              <input type="checkbox" checked={comLembrete} onChange={(e) => setComLembrete(e.target.checked)} />
              <span className="inline-flex items-center gap-1"><IconSino /> Avisar-me</span>
            </label>
            {comLembrete && (
              <>
                <input type="datetime-local" value={lembrete} onChange={(e) => setLembrete(e.target.value)}
                       className="rounded-lg border border-ink-100 px-2 py-1 text-sm" />
                <label className="flex items-center gap-2 text-ink-700">
                  <input type="checkbox" checked={porEmail} onChange={(e) => setPorEmail(e.target.checked)} />
                  também por email
                </label>
              </>
            )}
          </div>
          {comLembrete && (
            <div className="flex flex-wrap gap-2">
              {ATALHOS.map((a) => (
                <button key={a.label} type="button" className="chip hover:bg-ink-200"
                        onClick={() => setLembrete(paraInputLocal(a.calcula(), true))}>
                  {a.label}
                </button>
              ))}
            </div>
          )}
          <div className="flex items-center justify-between">
            <span className="text-xs text-ink-400">
              {comLembrete ? 'Avisamos no sino da plataforma' + (porEmail ? ' e por email' : '') + '.' : 'Sem aviso — fica só registada.'}
            </span>
            <button className="btn-primary" disabled={guardando || !texto.trim()} onClick={guardar}>
              {guardando ? 'A guardar…' : 'Guardar nota'}
            </button>
          </div>
        </div>

        <div className="px-5 py-4 max-h-[45vh] overflow-y-auto">
          {erro && <p className="text-sm text-ds-600 mb-2">{erro}</p>}
          {carregando ? (
            <p className="text-sm text-ink-400">A carregar…</p>
          ) : !notas.length ? (
            <p className="text-sm text-ink-400">Ainda não há notas nesta lead.</p>
          ) : (
            <ul className="space-y-3">
              {notas.map((n) => {
                const vencido = !!n.lembrete_em && !n.concluida_em && new Date(n.lembrete_em) <= new Date();
                return (
                  <li key={n.id} className={`rounded-xl border p-3 ${n.concluida_em ? 'border-ink-100 bg-ink-50/50' : vencido ? 'border-ds-200 bg-ds-50/40' : 'border-ink-100'}`}>
                    <div className={`text-sm whitespace-pre-wrap ${n.concluida_em ? 'text-ink-400 line-through' : 'text-ink-900'}`}>
                      {n.texto}
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-400">
                      <span>Data: {fmtData(n.data_nota)}</span>
                      {n.lembrete_em && (
                        <span className={vencido ? 'text-ds-600 font-medium' : ''}>
                          <IconSino className="inline mr-1 -mt-0.5" />
                          {fmtInstante(n.lembrete_em)}
                          {n.lembrete_canais?.includes('email') ? ' · email' : ''}
                        </span>
                      )}
                      <span>· {n.criado_por_nome || n.criado_por}</span>
                      <span className="ml-auto flex items-center gap-2">
                        <button className="hover:text-ds-600"
                                onClick={() => alterar(n.id, { concluida: !n.concluida_em })}>
                          {n.concluida_em ? 'Reabrir' : 'Concluir'}
                        </button>
                        {n.lembrete_em && (
                          <button className="hover:text-ds-600" onClick={() => alterar(n.id, { limpar_lembrete: true })}>
                            Retirar aviso
                          </button>
                        )}
                        <button className="hover:text-ds-600" onClick={() => apagar(n.id)}>Apagar</button>
                      </span>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
