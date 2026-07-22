'use client';
import { useState } from 'react';
import { api } from '../../lib/api';

type Proponente = {
  nome: string;
  idade?: number;
  data_nascimento?: string;
  nacionalidade?: string;
  profissao?: string | null;
  situacao_profissional?: string;
  rendimento_mensal?: number;
  nif?: number;
  cc_validade?: string;
  cc_expirado?: boolean;
  consentimento_rgpd?: boolean;
  garante?: boolean;
};
type Verificacao = { estado: 'ok' | 'alerta' | 'info'; titulo: string; detalhe: string };
type Sinal = {
  id: string;
  categoria?: string;
  severidade: 'alto' | 'medio' | 'baixo';
  titulo?: string;
  evidencia?: string;
  verificacao: 'confirmado_dados' | 'a_verificar_no_ficheiro' | 'confirmado_ficheiro';
  base_manual?: string;
  ficheiro?: string;
  documento?: string;
  proponente?: string;
};
type DocGrupo = {
  proponente: string;
  documentos: { documento: string; obrigatorio: boolean; validado: boolean; validade?: string | null }[];
};
type Analise = {
  referencia: string;
  processo: {
    referencia: string; tipo?: string; estado?: string; cliente?: string; gestor?: string;
    valor_eur?: number; criado_em?: string; atualizado_em?: string; conta_crm?: string;
  };
  ambito: string;
  proponentes: Proponente[];
  documentos: {
    validados: number; total: number;
    obrigatorios_pendentes: { proponente: string; documento: string }[];
    por_proponente: DocGrupo[];
  };
  verificacoes: Verificacao[];
  sinais_alerta: Sinal[];
  nota_metodologia: string;
  fonte: string;
  as_of: string;
};
type Conteudo = {
  referencia: string;
  total_ficheiros: number;
  ficheiros_analisados: { ficheiro: string; documento: string; proponente: string; n_sinais: number }[];
  ficheiros_ignorados: { ficheiro: string; motivo: string }[];
  sinais_alerta: Sinal[];
  nota_metodologia: string;
};

const EUR = (n?: number | null) =>
  (n ?? 0).toLocaleString('pt-PT', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 });
const ptDate = (s?: string) => (s ? new Date(s).toLocaleDateString('pt-PT') : '—');

const SEV_STYLE: Record<string, string> = {
  alto: 'border-rose-300 bg-rose-50',
  medio: 'border-amber-300 bg-amber-50',
  baixo: 'border-ink-200 bg-ink-50/60',
};
const SEV_LABEL: Record<string, string> = { alto: 'Alto', medio: 'Médio', baixo: 'Baixo' };
const VERIF_LABEL: Record<string, string> = {
  confirmado_dados: 'Confirmado pelos dados',
  a_verificar_no_ficheiro: 'A verificar no documento',
  confirmado_ficheiro: 'Confirmado no ficheiro',
};

export default function AnaliseDocumentalPage() {
  const [ref, setRef] = useState('');
  const [data, setData] = useState<Analise | null>(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [conteudo, setConteudo] = useState<Conteudo | null>(null);
  const [loadingConteudo, setLoadingConteudo] = useState(false);
  const [erroConteudo, setErroConteudo] = useState<string | null>(null);

  const limparErro = (msg: string) =>
    msg.replace(/^API [^:]+→ \d+:\s*/, '').replace(/^\{.*"detail":"?/, '').replace(/"?\}?$/, '');

  async function analisar() {
    const r = ref.trim();
    if (!r) return;
    setLoading(true); setErro(null); setData(null); setConteudo(null); setErroConteudo(null);
    try {
      const res = await api<Analise>(`/api/analise-documental/${encodeURIComponent(r)}`);
      setData(res);
    } catch (e) {
      setErro(limparErro(e instanceof Error ? e.message : String(e)));
    } finally {
      setLoading(false);
    }
  }

  async function analisarConteudo() {
    if (!data) return;
    setLoadingConteudo(true); setErroConteudo(null); setConteudo(null);
    try {
      const res = await api<Conteudo>(`/api/analise-documental/${encodeURIComponent(data.referencia)}/conteudo`, { method: 'POST' });
      setConteudo(res);
    } catch (e) {
      setErroConteudo(limparErro(e instanceof Error ? e.message : String(e)));
    } finally {
      setLoadingConteudo(false);
    }
  }

  const estruturais = (data?.sinais_alerta ?? []).filter((s) => s.verificacao === 'confirmado_dados');
  const aVerificar = (data?.sinais_alerta ?? []).filter((s) => s.verificacao === 'a_verificar_no_ficheiro');

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold text-ink-900">Análise documental</h1>
        <p className="text-ink-400 mt-1">
          Deteção de sinais de alerta de falsificação num processo de crédito. A base de
          análise são os manuais internos de deteção de documentos falsificados da DS. A
          análise (Fase 1) cruza os dados estruturados do processo no CRM — proponentes e
          checklist de documentos — com o catálogo de sinais de alerta; não abre o
          conteúdo dos ficheiros.
        </p>
      </header>

      <section className="card">
        <label className="text-sm text-ink-600 font-medium">Número de processo</label>
        <div className="flex items-center gap-2 mt-2 flex-wrap">
          <input
            value={ref}
            onChange={(e) => setRef(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && analisar()}
            placeholder="ex.: P2026070907570535"
            className="rounded-md border border-ink-200 px-3 py-2 text-sm font-mono w-72"
          />
          <button className="btn-primary" onClick={analisar} disabled={loading || !ref.trim()}>
            {loading ? 'A analisar…' : 'Analisar'}
          </button>
        </div>
        {erro && <p className="text-sm text-rose-700 mt-3">{erro}</p>}
      </section>

      {data && (
        <>
          <section className="card">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <h2 className="text-lg font-semibold text-ink-900">
                  {data.processo.cliente} <span className="font-mono text-sm text-ink-400">· {data.processo.referencia}</span>
                </h2>
                <p className="text-sm text-ink-600 mt-1">
                  {data.processo.tipo} · {data.processo.estado} · {EUR(data.processo.valor_eur)}
                  {data.processo.gestor && <> · gestor {data.processo.gestor}</>}
                </p>
                <p className="text-xs text-ink-400 mt-1">
                  Criado {ptDate(data.processo.criado_em)} · atualizado {ptDate(data.processo.atualizado_em)} ·
                  {' '}{data.documentos.validados}/{data.documentos.total} documentos validados
                </p>
              </div>
              <div className="text-xs text-ink-400 text-right">
                <div>Âmbito: {data.ambito}</div>
                <div>Conta CRM: {data.processo.conta_crm}</div>
              </div>
            </div>
          </section>

          {/* Sinais confirmados pelos dados */}
          <section className="card">
            <h2 className="text-lg font-semibold text-ink-900 mb-1">
              Sinais confirmados pelos dados <span className="text-ink-400">({estruturais.length})</span>
            </h2>
            <p className="text-sm text-ink-400 mb-3">
              Sinais de alerta do catálogo confirmáveis com os dados estruturados do CRM.
            </p>
            {estruturais.length === 0 ? (
              <p className="text-sm text-emerald-700">Nenhum sinal estrutural detetado nos dados do processo.</p>
            ) : (
              <div className="space-y-3">
                {estruturais.map((s, i) => (
                  <SinalCard key={i} s={s} />
                ))}
              </div>
            )}
          </section>

          {/* Verificações objetivas */}
          <section className="card">
            <h2 className="text-lg font-semibold text-ink-900 mb-3">Verificações objetivas</h2>
            <div className="space-y-2">
              {data.verificacoes.map((v, i) => (
                <div key={i} className="flex items-start gap-2 text-sm">
                  <span className={
                    v.estado === 'alerta' ? 'text-rose-600' : v.estado === 'ok' ? 'text-emerald-600' : 'text-ink-400'
                  }>
                    {v.estado === 'alerta' ? '⚠' : v.estado === 'ok' ? '✓' : 'ℹ'}
                  </span>
                  <div>
                    <span className="text-ink-900 font-medium">{v.titulo}</span>
                    <span className="text-ink-600"> — {v.detalhe}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* A verificar no documento */}
          <section className="card">
            <h2 className="text-lg font-semibold text-ink-900 mb-1">
              A verificar no documento <span className="text-ink-400">({aVerificar.length})</span>
            </h2>
            <p className="text-sm text-ink-400 mb-3">
              Sinais que exigem inspeção manual do conteúdo do ficheiro (Fase 1 não abre ficheiros).
            </p>
            {aVerificar.length === 0 ? (
              <p className="text-sm text-ink-600">Sem recomendações de inspeção adicionais.</p>
            ) : (
              <div className="space-y-3">
                {aVerificar.map((s, i) => (
                  <SinalCard key={i} s={s} />
                ))}
              </div>
            )}
          </section>

          {/* Fase 2 — análise de conteúdo dos ficheiros */}
          <section className="card">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <h2 className="text-lg font-semibold text-ink-900">Análise profunda — conteúdo dos ficheiros</h2>
                <p className="text-sm text-ink-400 mt-1 max-w-2xl">
                  Descarrega os ficheiros do processo e lê o conteúdo (recibos, extratos, IRS,
                  cartas patronais) para detetar somatórios errados, tipos de letra, recibos
                  repetidos, QR/NIF e outras red-flags do manual. Tem custo por ficheiro.
                </p>
              </div>
              <button className="btn-primary shrink-0" onClick={analisarConteudo} disabled={loadingConteudo}>
                {loadingConteudo ? 'A ler ficheiros…' : 'Ler ficheiros'}
              </button>
            </div>
            {erroConteudo && <p className="text-sm text-rose-700 mt-3">{erroConteudo}</p>}

            {conteudo && (
              <div className="mt-4 space-y-4">
                <p className="text-sm text-ink-600">
                  {conteudo.ficheiros_analisados.length} de {conteudo.total_ficheiros} ficheiros analisados
                  {conteudo.ficheiros_ignorados.length > 0 && <> · {conteudo.ficheiros_ignorados.length} ignorados</>}
                </p>

                {conteudo.sinais_alerta.length === 0 ? (
                  <p className="text-sm text-emerald-700">Nenhum sinal de alerta detetado no conteúdo dos ficheiros.</p>
                ) : (
                  <div className="space-y-3">
                    {conteudo.sinais_alerta.map((s, i) => (
                      <div key={i}>
                        <SinalCard s={s} />
                        {(s.ficheiro || s.documento) && (
                          <p className="text-xs text-ink-400 mt-1 ml-1">
                            {s.documento}{s.ficheiro && <span className="font-mono"> · {s.ficheiro}</span>}
                            {s.proponente && <> · {s.proponente}</>}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                <details className="text-sm">
                  <summary className="cursor-pointer text-ink-600">Ficheiros analisados e ignorados</summary>
                  <div className="mt-2 space-y-1">
                    {conteudo.ficheiros_analisados.map((f, i) => (
                      <div key={`a${i}`} className="text-xs text-ink-600">
                        <span className={f.n_sinais > 0 ? 'text-amber-700' : 'text-emerald-700'}>
                          {f.n_sinais > 0 ? `⚠ ${f.n_sinais}` : '✓'}
                        </span>{' '}
                        <span className="font-mono">{f.ficheiro}</span> — {f.documento} ({f.proponente})
                      </div>
                    ))}
                    {conteudo.ficheiros_ignorados.map((f, i) => (
                      <div key={`i${i}`} className="text-xs text-ink-400">
                        — <span className="font-mono">{f.ficheiro}</span>: {f.motivo}
                      </div>
                    ))}
                  </div>
                </details>
              </div>
            )}
          </section>

          {/* Documentos por proponente */}
          <section className="card">
            <h2 className="text-lg font-semibold text-ink-900 mb-3">Checklist de documentos</h2>
            <div className="space-y-4">
              {data.documentos.por_proponente.map((g, gi) => (
                <div key={gi}>
                  <div className="text-sm font-medium text-ink-900 mb-1">{g.proponente}</div>
                  <div className="overflow-x-auto"><table className="w-full text-sm">
                    <tbody>
                      {g.documentos.map((d, di) => (
                        <tr key={di} className="border-b border-ink-100/60 last:border-0">
                          <td className="py-1 text-ink-700">
                            {d.documento}
                            {d.obrigatorio && <span className="text-rose-500 ml-1" title="Obrigatório">*</span>}
                          </td>
                          <td className="py-1 text-right">
                            {d.validado
                              ? <span className="text-emerald-700">Validado</span>
                              : <span className="text-ink-400">Por validar</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table></div>
                </div>
              ))}
            </div>
          </section>

          <footer className="text-xs text-ink-400 space-y-1">
            <p>{data.nota_metodologia}</p>
            <p>Fonte da base de análise: {data.fonte}</p>
          </footer>
        </>
      )}
    </div>
  );
}

function SinalCard({ s }: { s: Sinal }) {
  return (
    <div className={`rounded-lg border px-4 py-3 ${SEV_STYLE[s.severidade] ?? SEV_STYLE.baixo}`}>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm font-semibold text-ink-900">{s.titulo}</span>
        <span className="text-[11px] px-1.5 py-0.5 rounded bg-white/70 border border-ink-200 text-ink-600">
          {SEV_LABEL[s.severidade] ?? s.severidade}
        </span>
        {s.categoria && (
          <span className="text-[11px] px-1.5 py-0.5 rounded bg-white/70 border border-ink-200 text-ink-500">
            {s.categoria}
          </span>
        )}
        <span className="text-[11px] px-1.5 py-0.5 rounded bg-white/70 border border-ink-200 text-ink-500">
          {VERIF_LABEL[s.verificacao] ?? s.verificacao}
        </span>
      </div>
      {s.evidencia && <p className="text-sm text-ink-700 mt-1">{s.evidencia}</p>}
      {s.base_manual && <p className="text-xs text-ink-400 mt-1">Base (manual): {s.base_manual}</p>}
    </div>
  );
}
