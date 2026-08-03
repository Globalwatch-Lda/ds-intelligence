'use client';
import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import useSWR from 'swr';
import { api } from '../../lib/api';
import LeadNotas, { IconSino, type ResumoNotas } from '../../components/LeadNotas';

type Lead = {
  id: string;
  nome: string;
  telefone: string | null;
  email: string | null;
  nif: string | null;
  produto: string | null;
  consultor_id: string | null;
  consultor_nome: string | null;
  status: string;
  ultima_acao: string | null;
  // O QUE foi a última intervenção, tal como registada no CRM (aba "Atividade"
  // da ficha da lead). Nulo enquanto o ingest nocturno não passar pela lead.
  ultima_acao_texto: string | null;
  ultima_acao_agente: string | null;
  ultima_acao_tipo: number | null;
  acoes_total: number | null;
  created_at: string;
};

// Estados de lead fechados no CrediDesk (não contam como dormentes).
const CLOSED = new Set(['Concluido', 'Concluído', 'Perdido']);

const fmtData = (v: string | null) => (v ? new Date(v).toLocaleDateString('pt-PT') : '—');

// useSearchParams obriga a uma fronteira de Suspense: sem ela o Next não
// consegue pré-renderizar a página e o build falha (missing-suspense-with-csr-bailout).
export default function LeadsPage() {
  return (
    <Suspense fallback={<p className="text-ink-400 text-sm">A carregar leads…</p>}>
      <LeadsConteudo />
    </Suspense>
  );
}

function LeadsConteudo() {
  const { data } = useSWR<{ leads: Lead[] }>('/api/leads/list', api);
  const { data: resumo, mutate: recarregarResumo } = useSWR<{ por_lead: ResumoNotas }>(
    '/api/lead-notas/resumo',
    api,
  );
  const params = useSearchParams();
  const [aberta, setAberta] = useState<Lead | null>(null);

  const leads = data?.leads || [];
  const notas = resumo?.por_lead || {};

  // Link do sino/email (`/leads?lead=<crm_id>`) abre logo o painel dessa lead.
  const leadParam = params.get('lead');
  useEffect(() => {
    if (!leadParam || !leads.length) return;
    const alvo = leads.find((l) => l.id === leadParam);
    if (alvo) setAberta(alvo);
  }, [leadParam, leads]);

  const dormentes = leads.filter((l) => {
    if (!l.ultima_acao || CLOSED.has(l.status)) return false;
    const diff = (Date.now() - new Date(l.ultima_acao).getTime()) / 86400000;
    return diff > 30;
  });

  function BotaoNotas({ lead }: { lead: Lead }) {
    const info = notas[lead.id];
    const cor = info?.vencido
      ? 'text-ds-600'
      : info?.proximo_lembrete
      ? 'text-amber-500'
      : info?.notas
      ? 'text-ink-700'
      : 'text-ink-300';
    const titulo = info?.vencido
      ? 'Lembrete por tratar'
      : info?.proximo_lembrete
      ? `Lembrete a ${new Date(info.proximo_lembrete).toLocaleString('pt-PT')}`
      : info?.notas
      ? `${info.notas} nota(s)`
      : 'Adicionar nota / lembrete';
    return (
      <button
        type="button"
        title={titulo}
        onClick={() => setAberta(lead)}
        className={`inline-flex items-center gap-1 rounded-lg px-2 py-1 hover:bg-ink-50 ${cor}`}
      >
        <IconSino />
        {!!info?.notas && <span className="text-xs">{info.notas}</span>}
      </button>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink-900">Leads</h1>
        <p className="text-ink-400 mt-1">
          Oportunidades vindas do CRM (CrediDesk), no âmbito da sua carteira.
          Identifique leads dormentes e recupere-as antes que arrefeçam.
        </p>
      </div>

      <div className="card">
        <h2 className="text-lg font-semibold text-ink-900 mb-3">
          Leads dormentes (&gt; 30 dias sem acção){' '}
          <span className="chip chip-alert ml-2">{dormentes.length}</span>
        </h2>
        {dormentes.length === 0 ? (
          <p className="text-ink-400 text-sm">Nenhuma lead dormente — bom trabalho.</p>
        ) : (
          <ul className="text-sm divide-y divide-ink-100">
            {dormentes.map((l) => (
              <li key={l.id} className="py-2 flex items-baseline justify-between gap-4">
                <div>
                  <div className="text-ink-900">{l.nome}</div>
                  <div className="text-ink-400 text-xs">
                    {l.produto || '—'} · {l.consultor_nome || 'por atribuir'}
                  </div>
                </div>
                <div className="text-ink-400 text-xs shrink-0 text-right">
                  <div>última acção: {fmtData(l.ultima_acao)}</div>
                  {l.ultima_acao_texto && (
                    <div className="max-w-[320px] truncate" title={l.ultima_acao_texto}>
                      {l.ultima_acao_texto}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="card">
        <h3 className="text-base font-semibold text-ink-900 mb-3">
          Todas as leads <span className="chip ml-2">{leads.length}</span>
        </h3>
        {!leads.length ? (
          <p className="text-ink-400 text-sm">Sem leads no âmbito da sua carteira.</p>
        ) : (
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead>
              <tr className="text-left text-ink-400 border-b border-ink-100">
                <th className="py-2">Nome</th>
                <th className="py-2">Produto</th>
                <th className="py-2">Consultor</th>
                <th className="py-2">Status</th>
                <th className="py-2">Última acção</th>
                <th className="py-2 text-center">Notas</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((l) => (
                <tr key={l.id} className="border-b border-ink-100/60 last:border-0 align-top">
                  <td className="py-2 text-ink-900">{l.nome}</td>
                  <td className="py-2 text-ink-700">{l.produto || '—'}</td>
                  <td className="py-2 text-ink-700">{l.consultor_nome || <span className="text-ink-300">— por atribuir —</span>}</td>
                  <td className="py-2"><span className="chip">{l.status || '—'}</span></td>
                  <td className="py-2 max-w-[380px]">
                    {l.ultima_acao_texto ? (
                      <>
                        <div className="text-ink-700 line-clamp-2" title={l.ultima_acao_texto}>
                          {l.ultima_acao_texto}
                        </div>
                        <div className="text-ink-400 text-xs">
                          {fmtData(l.ultima_acao)}
                          {l.ultima_acao_agente ? ` · ${l.ultima_acao_agente}` : ''}
                        </div>
                      </>
                    ) : (
                      <span className="text-ink-400 text-xs">{fmtData(l.ultima_acao)}</span>
                    )}
                  </td>
                  <td className="py-2 text-center"><BotaoNotas lead={l} /></td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </div>

      {aberta && (
        <LeadNotas
          leadId={aberta.id}
          leadNome={aberta.nome}
          onClose={() => setAberta(null)}
          onMudou={() => recarregarResumo()}
        />
      )}
    </div>
  );
}
