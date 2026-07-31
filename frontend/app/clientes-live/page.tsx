'use client';
import { useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { api } from '../../lib/api';
import { SemaforoCrm } from '../../components/Semaforos';

type Customer = {
  crm_id: number;
  name: string;
  manager_name: string | null;
  email: string | null;
  telephone: string | null;
  tax_number: number | null;
  age: number | null;
  created_on_crm: string | null;
  processo_estado: string | null;
  processo_tipo: string | null;
};

type Page = {
  total: number;
  limit: number;
  offset: number;
  items: Customer[];
};

const PAGE_SIZE = 50;

function fmtDate(d: string | null) {
  if (!d) return '—';
  try {
    return new Date(d).toLocaleDateString('pt-PT');
  } catch {
    return d.slice(0, 10);
  }
}

type Filters = { managers: string[]; estados: string[]; tipos: string[] };

export default function ClientesLive() {
  const [q, setQ] = useState('');
  const [manager, setManager] = useState('');
  const [estado, setEstado] = useState('');
  const [tipo, setTipo] = useState('');
  const [comProc, setComProc] = useState(false);
  const [offset, setOffset] = useState(0);
  const qs = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
  if (q.trim()) qs.set('q', q.trim());
  if (manager) qs.set('manager', manager);
  if (estado) qs.set('estado', estado);
  if (tipo) qs.set('tipo', tipo);
  if (comProc) qs.set('com_processo', '1');
  const { data, error, isLoading } = useSWR<Page>(`/api/crm-live/customers?${qs}`, api);
  const { data: filters } = useSWR<Filters>('/api/crm-live/filters', api);
  const { data: me } = useSWR<{ role: string; nome: string | null }>('/api/auth/me', api);
  const scopeLbl = me
    ? me.role === 'diretor_loja' ? 'Loja toda'
      : me.role === 'diretor_comercial' ? `Equipa de ${me.nome ?? ''}`
      : `Carteira de ${me.nome ?? ''}`
    : '…';

  return (
    <div className="space-y-6">
      <section>
        <div className="flex items-center gap-3">
          {/* Era um ponto verde fixo no HTML: dizia "em direto" mesmo com o
              espelho por sincronizar há dias. Agora mede a frescura real. */}
          <h1 className="text-2xl font-semibold text-ink-900">Clientes em direto do CRM</h1>
          <SemaforoCrm />
        </div>
        <p className="text-ink-400 mt-1 text-sm">
          Âmbito: <span className="font-medium text-ink-600">{scopeLbl}</span>
        </p>
      </section>

      <section className="card">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setOffset(0);
            }}
            placeholder="Procurar por nome, NIF, telefone ou email…"
            className="flex-1 min-w-[260px] rounded-md border border-ink-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ds-300"
          />
          <select
            value={manager}
            onChange={(e) => { setManager(e.target.value); setOffset(0); }}
            className="rounded-md border border-ink-200 px-2 py-2 text-sm text-ink-700"
          >
            <option value="">Todos os gestores</option>
            {(filters?.managers || []).map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
          <select
            value={estado}
            onChange={(e) => { setEstado(e.target.value); setOffset(0); }}
            className="rounded-md border border-ink-200 px-2 py-2 text-sm text-ink-700"
          >
            <option value="">Todos os estados de processo</option>
            {(filters?.estados || []).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <select
            value={tipo}
            onChange={(e) => { setTipo(e.target.value); setOffset(0); }}
            className="rounded-md border border-ink-200 px-2 py-2 text-sm text-ink-700"
          >
            <option value="">Todos os tipos de processo</option>
            {(filters?.tipos || []).map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <label className="flex items-center gap-1.5 text-sm text-ink-700 select-none">
            <input
              type="checkbox"
              checked={comProc}
              onChange={(e) => { setComProc(e.target.checked); setOffset(0); }}
            />
            Só com processo
          </label>
          {(manager || estado || tipo || comProc) && (
            <button
              onClick={() => { setManager(''); setEstado(''); setTipo(''); setComProc(false); setOffset(0); }}
              className="rounded-md border border-ink-200 px-3 py-2 text-sm text-ink-700 hover:bg-ink-50"
            >
              Limpar filtros
            </button>
          )}
          <div className="text-sm text-ink-400">
            {isLoading
              ? 'A carregar…'
              : data
              ? `${data.total.toLocaleString('pt-PT')} clientes${q || manager || estado || tipo || comProc ? ' (filtrado)' : ''}`
              : ''}
          </div>
        </div>

        {error && (
          <p className="mt-4 text-sm text-ds-700">Erro: {String(error.message)}</p>
        )}

        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-ink-400 border-b border-ink-100">
              <tr>
                <th className="py-2 pr-4 font-medium">Nome</th>
                <th className="py-2 pr-4 font-medium">Gestor</th>
                <th className="py-2 pr-4 font-medium">Estado do processo</th>
                <th className="py-2 pr-4 font-medium">Tipo de processo</th>
                <th className="py-2 pr-4 font-medium">NIF</th>
                <th className="py-2 pr-4 font-medium">Telefone</th>
                <th className="py-2 pr-4 font-medium">Email</th>
                <th className="py-2 pr-4 font-medium">Idade</th>
                <th className="py-2 pr-4 font-medium">Criado em</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((c) => (
                <tr key={c.crm_id} className="border-b border-ink-50 hover:bg-ink-50/50">
                  <td className="py-2 pr-4 text-ink-900 font-medium">{c.name}</td>
                  <td className="py-2 pr-4 text-ink-700">{c.manager_name ?? '—'}</td>
                  <td className="py-2 pr-4">
                    {c.processo_estado ? (
                      <span className="inline-block rounded border border-sky-200 bg-sky-50 text-sky-800 text-xs px-1.5 py-0.5">
                        {c.processo_estado}
                      </span>
                    ) : (
                      <span className="text-ink-300">—</span>
                    )}
                  </td>
                  <td className="py-2 pr-4 text-ink-700">{c.processo_tipo ?? <span className="text-ink-300">—</span>}</td>
                  <td className="py-2 pr-4 text-ink-700 tabular-nums">{c.tax_number ?? '—'}</td>
                  <td className="py-2 pr-4 text-ink-700">{c.telephone ?? '—'}</td>
                  <td className="py-2 pr-4 text-ink-700">{c.email ?? '—'}</td>
                  <td className="py-2 pr-4 text-ink-700 tabular-nums">{c.age ?? '—'}</td>
                  <td className="py-2 pr-4 text-ink-400">{fmtDate(c.created_on_crm)}</td>
                </tr>
              ))}
              {data && data.items.length === 0 && (
                <tr>
                  <td colSpan={9} className="py-8 text-center text-ink-400">
                    Sem resultados.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {data && data.total > PAGE_SIZE && (
          <div className="mt-4 flex items-center justify-between">
            <button
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              disabled={offset === 0}
              className="rounded-md border border-ink-200 px-3 py-1.5 text-sm text-ink-700 disabled:opacity-40 hover:bg-ink-50"
            >
              ← Anterior
            </button>
            <div className="text-sm text-ink-400">
              {(offset + 1).toLocaleString('pt-PT')}–
              {Math.min(offset + PAGE_SIZE, data.total).toLocaleString('pt-PT')} de{' '}
              {data.total.toLocaleString('pt-PT')}
            </div>
            <button
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= data.total}
              className="rounded-md border border-ink-200 px-3 py-1.5 text-sm text-ink-700 disabled:opacity-40 hover:bg-ink-50"
            >
              Seguinte →
            </button>
          </div>
        )}
      </section>

      <Link href="/dashboard" className="inline-block text-sm text-ink-400 hover:text-ds-600">
        ← Voltar ao dashboard
      </Link>
    </div>
  );
}
