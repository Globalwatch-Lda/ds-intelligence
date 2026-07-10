'use client';
import useSWR from 'swr';
import { useState, Fragment } from 'react';
import { api } from '../../lib/api';

type WonRow = {
  reference: string;
  cliente: string;
  tipo: string;
  valor_eur?: number;
  comissao_eur?: number;
  consultor?: string;
  fechado_em?: string;
};
type LostRow = WonRow;
type StateRow = {
  state: string;
  count: number;
  volume_eur: number;
  processos?: { reference: string; cliente: string; tipo: string; valor_eur?: number; consultor?: string }[];
};
type LadderRow = { reference: string; cliente: string; tipo: string; dias_atraso: number; bucket: string };
type Totals = {
  open_now: number;
  open_volume_eur: number;
  closed_won: number;
  closed_lost: number;
  created_this_week: number;
  money_won_eur: number;
  commission_won_eur: number;
  money_lost_eur: number;
  ladder_total_atraso: number;
  reativacoes_pool: number;
};
type Recap = {
  loja: string;
  week_start: string;
  week_end: string;
  as_of: string;
  totals: Totals;
  open_by_state: StateRow[];
  closed_won_detail: WonRow[];
  closed_lost_detail: LostRow[];
  ladder: {
    buckets: Record<string, number>;
    rows: LadderRow[];
  };
};

const EUR = (n?: number | null) =>
  (n ?? 0).toLocaleString('pt-PT', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 });

const BUCKET_LABEL: Record<string, string> = {
  nudge_7_9: 'Lembrete (7-9d)',
  second_10_14: 'Segundo lembrete (10-14d)',
  pivot_15_19: 'Pergunta de continuidade (15-19d)',
  final_20_29: 'Última tentativa (20-29d)',
  standby_30plus: 'Stand-by sugerido (30d+)',
};

function isoToPt(s?: string) {
  if (!s) return '—';
  return new Date(s).toLocaleDateString('pt-PT');
}

export default function RecapPage() {
  const [weekOf, setWeekOf] = useState<string>('');
  const [rFrom, setRFrom] = useState<string>('');
  const [rTo, setRTo] = useState<string>('');
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const url =
    rFrom && rTo
      ? `/api/recap/weekly?date_from=${rFrom}&date_to=${rTo}`
      : weekOf
      ? `/api/recap/weekly?week_of=${weekOf}`
      : '/api/recap/weekly';
  const { data, isLoading } = useSWR<Recap>(url, api);

  function shiftWeek(days: number) {
    setRFrom('');
    setRTo('');
    const base = data ? new Date(data.week_start) : new Date();
    base.setDate(base.getDate() + days);
    setWeekOf(base.toISOString().slice(0, 10));
  }

  if (isLoading || !data) return <p className="text-ink-400">A carregar recap …</p>;

  const t = data.totals;

  return (
    <div className="space-y-8">
      <header>
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-semibold text-ink-900">Recap semanal — coordenadores</h1>
            <p className="text-ink-400 mt-1">
              Análise de desempenho e métricas financeiras da semana. Monitorize
              os contratos celebrados, os novos processos criados e o volume
              total do pipeline distribuído por fases.
            </p>
            <p className="text-xs text-ink-400 mt-1">
              {data.loja} · período de <strong>{isoToPt(data.week_start)}</strong> a <strong>{isoToPt(data.week_end)}</strong>
            </p>
          </div>
          <div className="flex flex-col items-end gap-2 text-sm">
            <div className="flex items-center gap-2">
              <button className="chip" onClick={() => shiftWeek(-7)}>← Semana anterior</button>
              <button className="chip" onClick={() => { setRFrom(''); setRTo(''); setWeekOf(''); }}>Semana actual</button>
              <button className="chip" onClick={() => shiftWeek(7)}>Semana seguinte →</button>
            </div>
            <div className="flex items-center gap-2 flex-wrap justify-end">
              <span className="text-xs text-ink-400">ou intervalo:</span>
              <input type="date" value={rFrom} onChange={(e) => setRFrom(e.target.value)}
                className="rounded-md border border-ink-200 px-2 py-1 text-sm" />
              <input type="date" value={rTo} onChange={(e) => setRTo(e.target.value)}
                className="rounded-md border border-ink-200 px-2 py-1 text-sm" />
              {(rFrom || rTo) && <button className="chip" onClick={() => { setRFrom(''); setRTo(''); }}>Limpar</button>}
            </div>
          </div>
        </div>
      </header>

      <section className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <div className="card">
          <div className="text-sm text-ink-400">Contratos Celebrados</div>
          <div className="mt-2 text-3xl font-semibold text-emerald-700">{t.closed_won}</div>
          <div className="text-sm text-ink-600 mt-1">{EUR(t.money_won_eur)} financiados</div>
          <div className="text-xs text-ink-400">Comissão {EUR(t.commission_won_eur)}</div>
        </div>
        <div className="card">
          <div className="text-sm text-ink-400">Anulados/Perdidos</div>
          <div className="mt-2 text-3xl font-semibold text-rose-700">{t.closed_lost}</div>
          <div className="text-sm text-ink-600 mt-1">{EUR(t.money_lost_eur)} volume perdido</div>
        </div>
        <div className="card">
          <div className="text-sm text-ink-400">Novos processos criados</div>
          <div className="mt-2 text-3xl font-semibold text-sky-700">{t.created_this_week}</div>
        </div>
      </section>

      <section className="card">
        <h2 className="text-lg font-semibold text-ink-900 mb-3">Pipeline em aberto agora</h2>
        <p className="text-sm text-ink-400 mb-3">
          {t.open_now} processos abertos · volume total {EUR(t.open_volume_eur)} · clique num estado para ver os processos
        </p>
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead>
            <tr className="text-left text-ink-400 border-b border-ink-100">
              <th className="py-2">Estado</th>
              <th className="py-2 text-right">Nº processos</th>
              <th className="py-2 text-right">Volume</th>
            </tr>
          </thead>
          <tbody>
            {data.open_by_state.map((s) => (
              <Fragment key={s.state}>
                <tr
                  className="border-b border-ink-100/60 last:border-0 hover:bg-ink-50/60 cursor-pointer"
                  onClick={() => setExpanded((e) => ({ ...e, [s.state]: !e[s.state] }))}
                >
                  <td className="py-2 text-ink-900">
                    <span className="inline-block w-4 text-ink-400">{expanded[s.state] ? '▾' : '▸'}</span>
                    {s.state}
                  </td>
                  <td className="py-2 text-right text-ink-700">{s.count}</td>
                  <td className="py-2 text-right text-ink-700">{EUR(s.volume_eur)}</td>
                </tr>
                {expanded[s.state] &&
                  (s.processos || []).map((p) => (
                    <tr key={p.reference} className="bg-ink-50/40">
                      <td className="py-1 pl-8 text-xs text-ink-700">
                        <span className="font-mono text-ink-400 mr-2">{p.reference}</span>
                        {p.cliente}
                        <span className="text-ink-400"> · {p.tipo}</span>
                        {p.consultor && <span className="text-ink-400"> · {p.consultor}</span>}
                      </td>
                      <td></td>
                      <td className="py-1 text-right text-xs text-ink-600">{EUR(p.valor_eur)}</td>
                    </tr>
                  ))}
              </Fragment>
            ))}
          </tbody>
        </table></div>
      </section>

      {data.closed_won_detail.length > 0 && (
        <section className="card">
          <h2 className="text-lg font-semibold text-emerald-800 mb-3">✓ Contratos celebrados da semana ({data.closed_won_detail.length})</h2>
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead>
              <tr className="text-left text-ink-400 border-b border-ink-100">
                <th className="py-2">Referência</th>
                <th className="py-2">Cliente</th>
                <th className="py-2">Tipo</th>
                <th className="py-2 text-right">Valor</th>
                <th className="py-2 text-right">Comissão</th>
                <th className="py-2">Consultor</th>
              </tr>
            </thead>
            <tbody>
              {data.closed_won_detail.map((p) => (
                <tr key={p.reference} className="border-b border-ink-100/60 last:border-0">
                  <td className="py-2 font-mono text-xs">{p.reference}</td>
                  <td className="py-2 text-ink-900">{p.cliente}</td>
                  <td className="py-2 text-ink-700">{p.tipo}</td>
                  <td className="py-2 text-right text-emerald-700 font-medium">{EUR(p.valor_eur)}</td>
                  <td className="py-2 text-right text-ink-700">{EUR(p.comissao_eur)}</td>
                  <td className="py-2 text-ink-700">{p.consultor}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </section>
      )}

      {data.closed_lost_detail.length > 0 && (
        <section className="card">
          <h2 className="text-lg font-semibold text-rose-800 mb-3">✗ Anulados/Perdidos da semana ({data.closed_lost_detail.length})</h2>
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead>
              <tr className="text-left text-ink-400 border-b border-ink-100">
                <th className="py-2">Referência</th>
                <th className="py-2">Cliente</th>
                <th className="py-2">Tipo</th>
                <th className="py-2 text-right">Volume não realizado</th>
                <th className="py-2">Consultor</th>
              </tr>
            </thead>
            <tbody>
              {data.closed_lost_detail.map((p) => (
                <tr key={p.reference} className="border-b border-ink-100/60 last:border-0">
                  <td className="py-2 font-mono text-xs">{p.reference}</td>
                  <td className="py-2 text-ink-900">{p.cliente}</td>
                  <td className="py-2 text-ink-700">{p.tipo}</td>
                  <td className="py-2 text-right text-rose-700">{EUR(p.valor_eur)}</td>
                  <td className="py-2 text-ink-700">{p.consultor}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </section>
      )}

      <section className="card">
        <h2 className="text-lg font-semibold text-ink-900 mb-3">Documentação em atraso (escada de escalada)</h2>
        <p className="text-sm text-ink-400 mb-3">
          {t.ladder_total_atraso} processos com documentação pendente há mais de 7 dias.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3 mb-4">
          {Object.entries(data.ladder.buckets).map(([k, v]) => (
            <div key={k} className="rounded-lg border border-ink-100 px-3 py-2">
              <div className="text-[11px] text-ink-400">{BUCKET_LABEL[k] ?? k}</div>
              <div className="text-2xl font-semibold text-ink-900">{v}</div>
            </div>
          ))}
        </div>
        {data.ladder.rows.length > 0 && (
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead>
              <tr className="text-left text-ink-400 border-b border-ink-100">
                <th className="py-2">Cliente</th>
                <th className="py-2">Tipo</th>
                <th className="py-2 text-right">Dias em atraso</th>
                <th className="py-2">Estado da escada</th>
              </tr>
            </thead>
            <tbody>
              {data.ladder.rows.map((r) => (
                <tr key={r.reference} className="border-b border-ink-100/60 last:border-0">
                  <td className="py-2 text-ink-900">{r.cliente}</td>
                  <td className="py-2 text-ink-700">{r.tipo}</td>
                  <td className="py-2 text-right text-ink-700">{r.dias_atraso}</td>
                  <td className="py-2 text-ink-700">{BUCKET_LABEL[r.bucket] ?? r.bucket}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </section>

      <section className="card">
        <h2 className="text-lg font-semibold text-ink-900 mb-1">Reativações</h2>
        <p className="text-sm text-ink-600">
          <strong>{t.reativacoes_pool}</strong> leads pendentes sem actividade há mais de 30 dias. Ver{' '}
          <a href="/triggers?type=lead_dormente" className="text-ds-600 underline">Reativações</a> para a lista detalhada.
        </p>
      </section>

    </div>
  );
}
