'use client';
import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import useSWR, { useSWRConfig } from 'swr';
import { api } from '../../lib/api';
import LeadNotas, { IconSino, type ResumoNotas } from '../../components/LeadNotas';
import LeadBoasVindas, { IconEnvelope } from '../../components/LeadBoasVindas';
import { useMe } from '../../lib/useMe';

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
  // Lead por trabalhar: ninguém registou contacto no CRM (só "criou a lead").
  nova: boolean;
  boas_vindas_em: string | null;
  created_at: string;
};

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
  const { caps } = useMe();
  const [aberta, setAberta] = useState<Lead | null>(null);
  const [emailPara, setEmailPara] = useState<Lead | null>(null);
  const { mutate: recarregarLeads } = useSWRConfig();

  const leads = data?.leads || [];
  const novas = leads.filter((l) => l.nova);
  const podeEnviar = caps.has('messaging.send');
  const notas = resumo?.por_lead || {};

  // Link do sino/email (`/leads?lead=<crm_id>`) abre logo o painel dessa lead.
  const leadParam = params.get('lead');
  useEffect(() => {
    if (!leadParam || !leads.length) return;
    const alvo = leads.find((l) => l.id === leadParam);
    if (alvo) setAberta(alvo);
  }, [leadParam, leads]);

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

  function BotaoEmail({ lead }: { lead: Lead }) {
    const enviado = !!lead.boas_vindas_em;
    if (!podeEnviar) return null;
    return (
      <button
        type="button"
        title={
          !lead.email
            ? 'Lead sem email no CRM'
            : enviado
            ? `Boas-vindas enviadas a ${new Date(lead.boas_vindas_em!).toLocaleDateString('pt-PT')}`
            : 'Enviar email de boas-vindas com os documentos necessários'
        }
        disabled={!lead.email}
        onClick={() => setEmailPara(lead)}
        className={`inline-flex items-center rounded-lg px-2 py-1 hover:bg-ink-50 disabled:opacity-30 disabled:hover:bg-transparent ${
          enviado ? 'text-emerald-600' : 'text-ink-400'
        }`}
      >
        <IconEnvelope />
      </button>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink-900">Leads</h1>
        <p className="text-ink-400 mt-1">
          Oportunidades vindas do CRM (CrediDesk), no âmbito da sua carteira.
          As leads a negrito ainda não têm contacto registado.
        </p>
      </div>

      <div className="card">
        <h3 className="text-base font-semibold text-ink-900 mb-3">
          Todas as leads <span className="chip ml-2">{leads.length}</span>
          {novas.length > 0 && (
            <span className="chip chip-alert ml-2" title="Sem contacto registado no CRM">
              {novas.length} novas
            </span>
          )}
        </h3>
        {!leads.length ? (
          <p className="text-ink-400 text-sm">Sem leads no âmbito da sua carteira.</p>
        ) : (
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead>
              <tr className="text-left text-ink-400 border-b border-ink-100">
                <th className="py-2">Nome</th>
                <th className="py-2">Criada em</th>
                <th className="py-2">Produto</th>
                <th className="py-2">Consultor</th>
                <th className="py-2">Status</th>
                <th className="py-2">Última acção</th>
                <th className="py-2 text-center">Acções</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((l) => (
                // Leads novas (sem contacto registado no CRM) a negrito — é a fila
                // de trabalho de quem abre a página.
                <tr key={l.id}
                    className={`border-b border-ink-100/60 last:border-0 align-top ${l.nova ? 'font-semibold' : ''}`}>
                  <td className="py-2 text-ink-900">
                    {l.nome}
                    {l.nova && (
                      <span className="chip chip-alert ml-2 font-medium" title="Sem contacto registado no CRM">
                        nova
                      </span>
                    )}
                  </td>
                  <td className="py-2 text-ink-700 whitespace-nowrap">{fmtData(l.created_at)}</td>
                  <td className="py-2 text-ink-700">{l.produto || '—'}</td>
                  <td className="py-2 text-ink-700">{l.consultor_nome || <span className="text-ink-300">— por atribuir —</span>}</td>
                  <td className="py-2"><span className="chip font-medium">{l.status || '—'}</span></td>
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
                  <td className="py-2">
                    <div className="flex items-center justify-center gap-1">
                      <BotaoNotas lead={l} />
                      <BotaoEmail lead={l} />
                    </div>
                  </td>
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

      {emailPara && (
        <LeadBoasVindas
          leadId={emailPara.id}
          onClose={() => setEmailPara(null)}
          // Recarrega a lista para o envelope passar a verde sem refrescar a página.
          onEnviado={() => recarregarLeads('/api/leads/list')}
        />
      )}
    </div>
  );
}
