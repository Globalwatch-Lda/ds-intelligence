'use client';
import useSWR from 'swr';
import { api } from '../../lib/api';

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
  created_at: string;
};

// Estados de lead fechados no CrediDesk (não contam como dormentes).
const CLOSED = new Set(['Concluido', 'Concluído', 'Perdido']);

export default function LeadsPage() {
  const { data } = useSWR<{ leads: Lead[] }>('/api/leads/list', api);

  const leads = data?.leads || [];

  const dormentes = leads.filter((l) => {
    if (!l.ultima_acao || CLOSED.has(l.status)) return false;
    const diff = (Date.now() - new Date(l.ultima_acao).getTime()) / 86400000;
    return diff > 30;
  });

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
                <div className="text-ink-400 text-xs shrink-0">
                  última acção:{' '}
                  {l.ultima_acao ? new Date(l.ultima_acao).toLocaleDateString('pt-PT') : '—'}
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
              </tr>
            </thead>
            <tbody>
              {leads.map((l) => (
                <tr key={l.id} className="border-b border-ink-100/60 last:border-0">
                  <td className="py-2 text-ink-900">{l.nome}</td>
                  <td className="py-2 text-ink-700">{l.produto || '—'}</td>
                  <td className="py-2 text-ink-700">{l.consultor_nome || <span className="text-ink-300">— por atribuir —</span>}</td>
                  <td className="py-2"><span className="chip">{l.status || '—'}</span></td>
                  <td className="py-2 text-ink-400 text-xs">
                    {l.ultima_acao ? new Date(l.ultima_acao).toLocaleDateString('pt-PT') : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </div>
    </div>
  );
}
