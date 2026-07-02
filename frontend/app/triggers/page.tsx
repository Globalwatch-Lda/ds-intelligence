'use client';
import { useSearchParams } from 'next/navigation';
import useSWR from 'swr';
import { Suspense, useState } from 'react';
import { api } from '../../lib/api';

export const dynamic = 'force-dynamic';

const TRIGGER_LABELS: Record<string, string> = {
  aniversario: 'Aniversários',
  escritura_3m: 'Escritura · +3 meses',
  escritura_6m: 'Escritura · +6 meses',
  escritura_12m: 'Aniversário de escritura · 1 ano',
  apolice_60d: 'Apólices a vencer',
  taxa_fixa_90d: 'Taxa fixa a terminar',
  doc_atraso: 'Docs em falta há >7 dias',
  lead_dormente: 'Reativações (leads pendentes >30d)',
};
const TRIGGER_OPTIONS = Object.keys(TRIGGER_LABELS);
// Per-activity colour for the selected chip, so the focus colour reflects which
// activity is active (matches the dashboard card "intent" colours).
const CHIP_ACTIVE: Record<string, string> = {
  aniversario: '!bg-rose-600',
  escritura_3m: '!bg-amber-600',
  escritura_6m: '!bg-amber-600',
  escritura_12m: '!bg-amber-600',
  apolice_60d: '!bg-sky-600',
  taxa_fixa_90d: '!bg-indigo-600',
  doc_atraso: '!bg-ds-600',
  lead_dormente: '!bg-emerald-600',
};
// Activities whose result window is driven by a date interval.
const DATE_DRIVEN = new Set(['aniversario', 'escritura_3m', 'escritura_6m', 'escritura_12m', 'apolice_60d', 'taxa_fixa_90d']);

type Row = {
  cliente_id?: string;
  processo_id?: string;
  apolice_id?: string;
  nome?: string;
  telefone?: string | null;
  data?: string;
  data_escritura?: string;
  aniversario?: string;
  data_vencimento?: string;
  taxa_fixa_ate?: string;
  ramo?: string;
  seguradora?: string;
  premio_anual?: number;
  valor_credito?: number;
  dias_ate?: number;
  gestor?: string | null;
};

type PreviewResp = {
  preview: string;
  cliente_nome: string;
  cliente_telefone: string;
  demo_redirect_to: string | null;
};

export default function TriggersPage() {
  return (
    <Suspense fallback={<p className="text-ink-400">A carregar …</p>}>
      <TriggersInner />
    </Suspense>
  );
}

function TriggersInner() {
  const params = useSearchParams();
  // Single criterion at a time (item 7/8/9): a new choice replaces the previous
  // one and the result does not stack. We still read the legacy `types` query
  // (from older links) but keep only the first.
  const initialType =
    (params.get('type') && TRIGGER_OPTIONS.includes(params.get('type') as string) && (params.get('type') as string)) ||
    params.get('types')?.split(',').find((t) => TRIGGER_OPTIONS.includes(t)) ||
    'aniversario';

  const [selected, setSelected] = useState<string>(initialType);
  const [from, setFrom] = useState<string>(params.get('from') || '');
  const [to, setTo] = useState<string>(params.get('to') || '');

  const [previewRow, setPreviewRow] = useState<{ row: Row; trigger: string; preview: PreviewResp } | null>(null);
  const [editedMsg, setEditedMsg] = useState<string>('');
  const [sending, setSending] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  function select(t: string) {
    setSelected(t);
  }

  async function openPreview(row: Row, trigger: string) {
    setFeedback(null);
    try {
      const p = await api<PreviewResp>(`/api/triggers/preview`, {
        method: 'POST',
        body: JSON.stringify({ trigger, cliente_id: row.cliente_id, processo_id: row.processo_id, apolice_id: row.apolice_id }),
      });
      setPreviewRow({ row, trigger, preview: p });
      setEditedMsg(p.preview);
    } catch (e: any) {
      setFeedback(`Erro: ${e.message}`);
    }
  }

  async function confirmFire() {
    if (!previewRow) return;
    setSending(true);
    try {
      const trimmed = editedMsg.trim();
      const originalMsg = previewRow.preview.preview.trim();
      const mensagem_override = trimmed && trimmed !== originalMsg ? trimmed : null;
      const r = await api<{ sent: boolean; to: string; demo_redirected: boolean; cliente_nome: string }>(`/api/triggers/fire`, {
        method: 'POST',
        body: JSON.stringify({
          trigger: previewRow.trigger,
          cliente_id: previewRow.row.cliente_id,
          processo_id: previewRow.row.processo_id,
          apolice_id: previewRow.row.apolice_id,
          mensagem_override,
        }),
      });
      setFeedback(
        r.sent
          ? r.demo_redirected
            ? `✓ Enviado para ${r.to} (modo demo — em produção iria para ${previewRow.preview.cliente_nome}).`
            : `✓ Enviado para ${r.to}.`
          : `✓ Registado (sem destinatário verificado).`
      );
      setPreviewRow(null);
    } catch (e: any) {
      setFeedback(`Erro: ${e.message}`);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink-900">Atividades — pesquisa e envio</h1>
        <p className="text-ink-400 mt-1">
          Escolha a atividade e (opcional) um intervalo de datas — pode trocar de critério e de datas aqui mesmo.
          Clique <strong>Pré-visualizar</strong> para rever e enviar a mensagem WhatsApp.
        </p>
      </div>

      <div className="card space-y-4">
        <div>
          <div className="text-xs font-medium text-ink-400 uppercase tracking-wide">Atividade</div>
          <div className="flex flex-wrap gap-2 mt-2">
            {TRIGGER_OPTIONS.map((t) => (
              <button
                key={t}
                onClick={() => select(t)}
                className={`chip ${selected === t ? `${CHIP_ACTIVE[t] ?? '!bg-ink-900'} !text-white !font-semibold` : ''}`}
              >
                {TRIGGER_LABELS[t]}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs text-ink-400">
            De
            <input type="date" value={from} onChange={(e) => setFrom(e.target.value)}
              className="block mt-1 rounded-md border border-ink-200 px-2 py-1.5 text-sm text-ink-900" />
          </label>
          <label className="text-xs text-ink-400">
            Até
            <input type="date" value={to} onChange={(e) => setTo(e.target.value)}
              className="block mt-1 rounded-md border border-ink-200 px-2 py-1.5 text-sm text-ink-900" />
          </label>
          {(from || to) && (
            <button onClick={() => { setFrom(''); setTo(''); }} className="chip border border-ink-200">Limpar datas</button>
          )}
          <span className="text-xs text-ink-400">
            Sem datas, cada atividade usa a sua janela padrão (ex.: aniversários nos próximos 7 dias).
          </span>
        </div>
      </div>

      {feedback && <div className="card text-sm text-ink-700">{feedback}</div>}

      <ActivitySection key={selected} trigger={selected} label={TRIGGER_LABELS[selected]} from={from} to={to} onPreview={openPreview} />

      {previewRow && (
        <div className="fixed inset-0 bg-ink-900/40 z-50 flex items-end md:items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-xl w-full p-6 shadow-2xl">
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="font-semibold text-ink-900">Pré-visualização da mensagem</h3>
                <p className="text-ink-400 text-sm">
                  Para: <strong>{previewRow.preview.cliente_nome}</strong> · {previewRow.preview.cliente_telefone || '—'}
                </p>
              </div>
              <button onClick={() => setPreviewRow(null)} className="text-ink-400 hover:text-ds-600 text-2xl leading-none">×</button>
            </div>

            <p className="text-xs text-ink-400 mb-1">Pode ajustar a mensagem antes de enviar — esta edição aplica-se só a este envio, não altera o modelo base.</p>
            <textarea
              value={editedMsg}
              onChange={(e) => setEditedMsg(e.target.value)}
              className="w-full rounded-xl bg-ink-50 p-4 whitespace-pre-wrap text-sm text-ink-900 mb-4 min-h-[160px] border border-ink-100 focus:outline-none focus:border-ds-500"
            />
            {editedMsg.trim() !== previewRow.preview.preview.trim() && (
              <p className="text-xs text-ds-700 mb-3">✏️ Mensagem personalizada — irá enviar a sua versão.</p>
            )}

            {previewRow.preview.demo_redirect_to && (
              <div className="text-xs rounded-lg bg-ds-50 text-ds-700 px-3 py-2 mb-4">
                ℹ️ Modo demo: a mensagem será enviada para <strong>{previewRow.preview.demo_redirect_to}</strong> (o seu número verificado), porque o número do cliente ({previewRow.preview.cliente_telefone}) ainda não está autorizado no Meta. Em produção, com a API do CRM e os números reais, a mensagem irá directamente para o cliente.
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setPreviewRow(null)}>Cancelar</button>
              <button className="btn-primary" disabled={sending} onClick={confirmFire}>
                {sending ? 'A enviar …' : 'Confirmar e enviar'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ActivitySection({
  trigger,
  label,
  from,
  to,
  onPreview,
}: {
  trigger: string;
  label: string;
  from: string;
  to: string;
  onPreview: (row: Row, trigger: string) => void;
}) {
  const useRange = Boolean(from && to);
  const qs = `trigger=${trigger}${useRange ? `&date_from=${from}&date_to=${to}` : ''}`;
  const { data, isLoading } = useSWR<{ rows: Row[] }>(`/api/triggers/list?${qs}`, api);
  const isLead = trigger === 'lead_dormente';

  // Column filters for the Reactivations section (item 12): filter the loaded
  // leads by gestor and origem on the client.
  const [fGestor, setFGestor] = useState('');
  const [fOrigem, setFOrigem] = useState('');
  const allRows = data?.rows ?? [];
  const gestores = isLead ? Array.from(new Set(allRows.map((r) => (r as any).gestor).filter(Boolean))).sort() : [];
  const origens = isLead ? Array.from(new Set(allRows.map((r) => (r as any).origem).filter(Boolean))).sort() : [];
  const rows = isLead
    ? allRows.filter((r) => (!fGestor || (r as any).gestor === fGestor) && (!fOrigem || (r as any).origem === fOrigem))
    : allRows;

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold text-ink-900">
          {label}
          {data && <span className="chip ml-2">{rows.length}</span>}
        </h2>
        {useRange && !DATE_DRIVEN.has(trigger) && (
          <span className="text-[11px] text-ink-400">Esta atividade ignora o intervalo (janela própria).</span>
        )}
      </div>

      {isLead && allRows.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-3">
          <select value={fGestor} onChange={(e) => setFGestor(e.target.value)}
            className="rounded-md border border-ink-200 px-2 py-1.5 text-sm text-ink-700">
            <option value="">Todos os gestores</option>
            {gestores.map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
          <select value={fOrigem} onChange={(e) => setFOrigem(e.target.value)}
            className="rounded-md border border-ink-200 px-2 py-1.5 text-sm text-ink-700">
            <option value="">Todas as origens</option>
            {origens.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
          {(fGestor || fOrigem) && (
            <button onClick={() => { setFGestor(''); setFOrigem(''); }} className="chip border border-ink-200">Limpar filtros</button>
          )}
        </div>
      )}

      {isLoading || !data ? (
        <p className="text-ink-400 text-sm">A carregar contactos …</p>
      ) : rows.length === 0 ? (
        <p className="text-ink-400 text-sm">Sem contactos para esta atividade {useRange ? 'neste intervalo' : 'neste momento'}.</p>
      ) : (
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead>
            <tr className="text-left text-ink-400 border-b border-ink-100">
              <th className="py-2">Nome</th>
              <th className="py-2">Detalhe</th>
              {isLead && <th className="py-2">Origem</th>}
              <th className="py-2">Consultor</th>
              <th className="py-2">Contacto</th>
              <th className="py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-b border-ink-100/60 last:border-0">
                <td className="py-3 text-ink-900">{r.nome || '—'}</td>
                <td className="py-3 text-ink-700">
                  {trigger === 'aniversario' && r.data && (
                    <>Faz anos a <strong>{new Date(r.data).toLocaleDateString('pt-PT')}</strong>{r.dias_ate != null && <> ({r.dias_ate}d)</>}</>
                  )}
                  {(trigger === 'escritura_3m' || trigger === 'escritura_6m' || trigger === 'escritura_12m') && (
                    <>Escritura: {r.data_escritura} · aniv.: <strong>{r.aniversario}</strong></>
                  )}
                  {trigger === 'apolice_60d' && (
                    <>{r.ramo} ({r.seguradora}) — vence <strong>{r.data_vencimento}</strong> · €{r.premio_anual?.toFixed(0)}/ano</>
                  )}
                  {trigger === 'taxa_fixa_90d' && (
                    <>Taxa fixa até <strong>{r.taxa_fixa_ate}</strong> · €{r.valor_credito?.toFixed(0)}</>
                  )}
                  {trigger === 'doc_atraso' && (() => {
                    const count = (r as any).documentos_em_falta_count;
                    const mandatory = (r as any).docs_mandatory;
                    const tipo = (r as any).tipo;
                    const stageKey = (r as any).stage_key;
                    const stageLabel = (r as any).stage_label;
                    const stageStyle: Record<string, string> = {
                      nudge: 'bg-sky-100 text-sky-800 border-sky-200',
                      second: 'bg-amber-100 text-amber-800 border-amber-200',
                      pivot: 'bg-orange-100 text-orange-800 border-orange-300',
                      final: 'bg-rose-100 text-rose-800 border-rose-200',
                      standby: 'bg-ink-200 text-ink-700 border-ink-300',
                    };
                    return (
                      <>
                        <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border mr-2 ${stageStyle[stageKey] ?? ''}`}>
                          {stageLabel} (Dia {(r as any).dias_atraso})
                        </span>
                        Em atraso há <strong>{(r as any).dias_atraso}</strong> dias ·{' '}
                        {count != null && mandatory != null ? <>{count}/{mandatory} documento(s) pendente(s)</> : 'documentação pendente'}
                        {tipo && <> · <span className="text-ink-400">{tipo}</span></>}
                      </>
                    );
                  })()}
                  {trigger === 'lead_dormente' && (
                    <>{(r as any).produto} · dormente há <strong>{(r as any).dias_dormente ?? '—'}</strong> dias</>
                  )}
                </td>
                {isLead && <td className="py-3 text-ink-700">{(r as any).origem || '—'}</td>}
                <td className="py-3 text-ink-700">{r.gestor || '—'}</td>
                <td className="py-3 text-ink-700 font-mono text-xs">{r.telefone || '—'}</td>
                <td className="py-3 text-right">
                  <button className="btn-primary" onClick={() => onPreview(r, trigger)}>Pré-visualizar</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
    </div>
  );
}
