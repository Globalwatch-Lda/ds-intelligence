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

// Colunas por que a tabela se pode ordenar (clique no cabeçalho).
type Campo = 'nome' | 'created_at' | 'produto' | 'consultor_nome' | 'status' | 'ultima_acao' | 'nova';

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

  const [filtros, setFiltros] = useState({
    texto: '', produto: '', consultor: '', estado: '', soNovas: false, de: '', ate: '',
  });
  const [ordem, setOrdem] = useState<{ campo: Campo; desc: boolean }>({ campo: 'created_at', desc: true });

  const leads = data?.leads || [];
  const novas = leads.filter((l) => l.nova);
  const podeEnviar = caps.has('messaging.send');
  const notas = resumo?.por_lead || {};

  // Opções dos filtros vindas dos próprios dados: uma lista fixa no código
  // desactualizava-se assim que o CRM ganhasse um produto ou um consultor novo.
  const opcoes = (campo: 'produto' | 'consultor_nome' | 'status') =>
    Array.from(new Set(leads.map((l) => l[campo]).filter(Boolean) as string[])).sort((a, b) =>
      a.localeCompare(b, 'pt'),
    );

  const filtradas = leads.filter((l) => {
    const t = filtros.texto.trim().toLowerCase();
    if (t) {
      const alvo = `${l.nome || ''} ${l.email || ''} ${l.telefone || ''}`.toLowerCase();
      // Dígitos à parte: procurar "912345678" tem de encontrar "+351 912 345 678".
      const digitos = t.replace(/\D/g, '');
      const telDigitos = (l.telefone || '').replace(/\D/g, '');
      if (!alvo.includes(t) && !(digitos.length >= 3 && telDigitos.includes(digitos))) return false;
    }
    if (filtros.produto && l.produto !== filtros.produto) return false;
    if (filtros.consultor && l.consultor_nome !== filtros.consultor) return false;
    if (filtros.estado && l.status !== filtros.estado) return false;
    if (filtros.soNovas && !l.nova) return false;
    if (filtros.de && (!l.created_at || l.created_at.slice(0, 10) < filtros.de)) return false;
    if (filtros.ate && (!l.created_at || l.created_at.slice(0, 10) > filtros.ate)) return false;
    return true;
  });

  const ordenadas = [...filtradas].sort((a, b) => {
    const dir = ordem.desc ? -1 : 1;
    if (ordem.campo === 'nova') {
      // Novas primeiro e, dentro de cada grupo, as mais recentes à cabeça.
      if (a.nova !== b.nova) return (a.nova ? -1 : 1) * dir;
      return (b.created_at || '').localeCompare(a.created_at || '');
    }
    const va = a[ordem.campo] ?? '';
    const vb = b[ordem.campo] ?? '';
    // Datas vêm em ISO do CRM: a ordem alfabética é a cronológica.
    return String(va).localeCompare(String(vb), 'pt', { numeric: true }) * dir;
  });

  const temFiltros =
    !!filtros.texto || !!filtros.produto || !!filtros.consultor || !!filtros.estado ||
    filtros.soNovas || !!filtros.de || !!filtros.ate;

  function ordenarPor(campo: Campo) {
    setOrdem((o) => (o.campo === campo ? { campo, desc: !o.desc } : { campo, desc: campo !== 'nome' }));
  }

  function Th({ campo, children, className = '' }: { campo: Campo; children: React.ReactNode; className?: string }) {
    const activo = ordem.campo === campo;
    return (
      <th className={`py-2 ${className}`}>
        <button
          type="button"
          onClick={() => ordenarPor(campo)}
          className={`inline-flex items-center gap-1 hover:text-ds-600 ${activo ? 'text-ink-700' : ''}`}
        >
          {children}
          <span className={activo ? '' : 'opacity-0 group-hover:opacity-40'}>{activo && ordem.desc ? '▾' : '▴'}</span>
        </button>
      </th>
    );
  }

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
          As leads a negrito são as <b>novas</b>: entraram no CRM e ainda ninguém lhes registou contacto.
        </p>
      </div>

      <div className="card">
        <h3 className="text-base font-semibold text-ink-900 mb-3">
          Todas as leads{' '}
          <button
            type="button"
            onClick={() => setFiltros({ ...filtros, soNovas: false })}
            className={`chip ml-2 ${!filtros.soNovas ? 'ring-1 ring-ink-300' : ''}`}
            title="Mostrar todas as leads"
          >
            {leads.length}
          </button>
          {novas.length > 0 && (
            <button
              type="button"
              onClick={() => setFiltros({ ...filtros, soNovas: true })}
              className={`chip chip-alert ml-2 ${filtros.soNovas ? 'ring-1 ring-ds-600' : ''}`}
              title="Mostrar só as novas — sem contacto registado no CRM"
            >
              {novas.length} novas
            </button>
          )}
        </h3>

        <div className="mb-4 flex flex-wrap items-end gap-2 text-sm">
          <input
            value={filtros.texto}
            onChange={(e) => setFiltros({ ...filtros, texto: e.target.value })}
            placeholder="Procurar nome, email ou telefone"
            className="w-64 rounded-lg border border-ink-100 px-3 py-1.5"
          />
          <select value={filtros.produto} onChange={(e) => setFiltros({ ...filtros, produto: e.target.value })}
                  className="rounded-lg border border-ink-100 px-2 py-1.5">
            <option value="">Todos os produtos</option>
            {opcoes('produto').map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
          <select value={filtros.consultor} onChange={(e) => setFiltros({ ...filtros, consultor: e.target.value })}
                  className="rounded-lg border border-ink-100 px-2 py-1.5">
            <option value="">Todos os consultores</option>
            {opcoes('consultor_nome').map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
          <select value={filtros.estado} onChange={(e) => setFiltros({ ...filtros, estado: e.target.value })}
                  className="rounded-lg border border-ink-100 px-2 py-1.5">
            <option value="">Todos os estados</option>
            {opcoes('status').map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
          <label className="flex items-center gap-1 text-ink-400">
            criadas de
            <input type="date" value={filtros.de} onChange={(e) => setFiltros({ ...filtros, de: e.target.value })}
                   className="rounded-lg border border-ink-100 px-2 py-1.5 text-ink-900" />
          </label>
          <label className="flex items-center gap-1 text-ink-400">
            a
            <input type="date" value={filtros.ate} onChange={(e) => setFiltros({ ...filtros, ate: e.target.value })}
                   className="rounded-lg border border-ink-100 px-2 py-1.5 text-ink-900" />
          </label>
          {temFiltros && (
            <button
              className="text-xs text-ds-700 hover:underline"
              onClick={() => setFiltros({ texto: '', produto: '', consultor: '', estado: '', soNovas: false, de: '', ate: '' })}
            >
              limpar filtros
            </button>
          )}
        </div>
        {!ordenadas.length ? (
          <p className="text-ink-400 text-sm">
            {leads.length ? 'Nenhuma lead corresponde aos filtros.' : 'Sem leads no âmbito da sua carteira.'}
          </p>
        ) : (
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead>
              <tr className="group text-left text-ink-400 border-b border-ink-100">
                <Th campo="nome">Nome</Th>
                <Th campo="created_at">Criada em</Th>
                <Th campo="produto">Produto</Th>
                <Th campo="consultor_nome">Consultor</Th>
                <Th campo="status">Status</Th>
                <Th campo="ultima_acao">Última acção</Th>
                <th className="py-2 text-center">
                  <button type="button" onClick={() => ordenarPor('nova')}
                          className="hover:text-ds-600" title="Ordenar: novas primeiro">
                    Acções
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              {ordenadas.map((l) => (
                // Leads sem contacto registado no CRM a negrito — é a fila de
                // trabalho de quem abre a página.
                <tr key={l.id}
                    className={`border-b border-ink-100/60 last:border-0 align-top ${l.nova ? 'font-semibold' : ''}`}>
                  <td className="py-2 text-ink-900">
                    {l.nome}
                    {/* "nova" = sem contacto registado no CRM (não é a idade da
                        lead); o title do chip di-lo a quem passe o rato. */}
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
