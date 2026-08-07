'use client';
import { useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { api } from '../../lib/api';

// Semana ISO-8601 (segunda a domingo, semana 1 = a que contém a 1.ª quinta-feira
// do ano) — é a numeração de semana standard em Portugal, não a "semana do
// calendário" ingénua que conta a partir de 1 de Janeiro. Datas perto da
// viragem do ano podem pertencer à semana 1 do ano seguinte (ex. 29 Dez) ou à
// última semana do ano anterior — por isso o ano mostrado é o da PRÓPRIA
// semana ISO, não necessariamente o ano da data. Verificado byte a byte contra
// `datetime.date.isocalendar()` do Python (a implementação de referência),
// incluindo os dois casos de viragem de ano.
function semanaISO(dataStr: string): string {
  // `enviado_em` vem da BD como timestamptz ("2026-08-07T00:00:00+00:00"), não
  // como "YYYY-MM-DD" — dar isto ao Date() directamente em vez de fazer split('-'),
  // que parte a string ao meio no "T00:00:00+00:00" e dá NaN/NaN.
  const d0 = new Date(dataStr);
  const d = new Date(Date.UTC(d0.getUTCFullYear(), d0.getUTCMonth(), d0.getUTCDate()));
  const diaSemana = d.getUTCDay() || 7; // segunda=1 … domingo=7
  d.setUTCDate(d.getUTCDate() + 4 - diaSemana); // quinta-feira desta semana ISO
  const inicioAno = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const semana = Math.ceil((((d.getTime() - inicioAno.getTime()) / 86400000) + 1) / 7);
  return `Semana ${semana}/${d.getUTCFullYear()}`;
}

type Newsletter = {
  id: string;
  titulo: string;
  tema: string;
  conteudo_md?: string;
  enviado_em: string | null;
  destinatarios_count: number;
  created_at: string;
};

const TEMA_SUGESTOES = [
  'Como ler o seu spread em 2026',
  'Taxa fixa vs variável: o que pesa em 2026',
  'Revisão de seguros: 4 perguntas que devia fazer ao seu corretor',
  'Crédito habitação: documentos que valem a pena ter sempre actualizados',
];

function mdToHtml(md: string): string {
  // tiny markdown-to-HTML for a one-page preview — handles `# ## ### ` headings,
  // **bold**, bullets, paragraphs. Good enough for the demo preview.
  const lines = md.split('\n');
  let html = '';
  let inUl = false;
  for (const line of lines) {
    if (line.startsWith('### ')) {
      if (inUl) { html += '</ul>'; inUl = false; }
      html += `<h3 class="text-base font-semibold mt-4 mb-1">${line.slice(4)}</h3>`;
    } else if (line.startsWith('## ')) {
      if (inUl) { html += '</ul>'; inUl = false; }
      html += `<h2 class="text-lg font-semibold mt-5 mb-2 text-ds-700">${line.slice(3)}</h2>`;
    } else if (line.startsWith('# ')) {
      if (inUl) { html += '</ul>'; inUl = false; }
      html += `<h1 class="text-2xl font-bold mb-2 text-ink-900">${line.slice(2)}</h1>`;
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      if (!inUl) { html += '<ul class="list-disc pl-5 space-y-1 my-2">'; inUl = true; }
      html += `<li>${line.slice(2)}</li>`;
    } else if (line.trim() === '') {
      if (inUl) { html += '</ul>'; inUl = false; }
      html += '';
    } else {
      if (inUl) { html += '</ul>'; inUl = false; }
      html += `<p class="my-2 leading-relaxed">${line.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')}</p>`;
    }
  }
  if (inUl) html += '</ul>';
  return html;
}

export default function NewsletterPage() {
  const [tema, setTema] = useState(TEMA_SUGESTOES[0]);
  const [generating, setGenerating] = useState(false);
  const [draft, setDraft] = useState<Newsletter | null>(null);
  const [sendStatus, setSendStatus] = useState<string | null>(null);
  const [canais, setCanais] = useState<string[]>(['email']);
  const [semanaFiltro, setSemanaFiltro] = useState(''); // '' = todas as semanas

  function toggleCanal(c: string) {
    setCanais((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]));
  }

  const { data: list, mutate } = useSWR<{ newsletters: Newsletter[] }>('/api/newsletter/list', api);
  const { data: me } = useSWR<{ can_newsletter?: boolean }>('/api/auth/me', api);
  const canGenerate = !!me?.can_newsletter;
  // Quota diária por canal — refresca a cada 20s enquanto a página de compor
  // está aberta, para o número não ficar preso no que era verdade ao carregar.
  type Quota = { canal: string; ativo: boolean; cap_diario: number; enviado_hoje: number; restante: number };
  const { data: quota, mutate: mutateQuota } = useSWR<{ email: Quota; sms: Quota }>(
    canGenerate ? '/api/newsletter/quota' : null, api, { refreshInterval: 20000 },
  );

  // Read-only viewers: surface the latest SENT newsletter, rendered in full.
  const enviadas = (list?.newsletters || []).filter((n) => n.enviado_em);
  const latest = enviadas[0];
  // Semanas com pelo menos uma newsletter enviada, mais recente primeiro (a ordem
  // de `enviadas` já vem assim de `/api/newsletter/list`) — para o filtro só
  // mostrar semanas que existem, nunca uma lista vazia depois de escolhida.
  const semanasDisponiveis = Array.from(
    new Set(enviadas.map((n) => semanaISO(n.enviado_em!))),
  );
  const enviadasFiltradas = semanaFiltro
    ? enviadas.filter((n) => semanaISO(n.enviado_em!) === semanaFiltro)
    : enviadas;
  const { data: latestFull } = useSWR<Newsletter>(
    me && !canGenerate && latest ? `/api/newsletter/${latest.id}` : null,
    api,
  );

  async function generate() {
    setGenerating(true);
    setDraft(null);
    setSendStatus(null);
    try {
      const r = await api<Newsletter>('/api/newsletter/generate', {
        method: 'POST',
        body: JSON.stringify({ tema }),
      });
      setDraft(r);
      setEdited(r.conteudo_md || '');
      mutate();
    } finally {
      setGenerating(false);
    }
  }

  async function uploadFile(file: File) {
    setGenerating(true);
    setDraft(null);
    setSendStatus(`A processar ${file.name} …`);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch('/api/newsletter/upload', { method: 'POST', body: fd });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(t);
      }
      const r = (await res.json()) as Newsletter;
      setDraft(r);
      setEdited(r.conteudo_md || '');
      setSendStatus('✓ Documento reformatado pela IA — reveja e edite abaixo antes de enviar.');
      mutate();
    } catch (e: any) {
      setSendStatus(`Erro: ${e.message}`);
    } finally {
      setGenerating(false);
    }
  }

  const [edited, setEdited] = useState<string>('');

  async function saveEdits() {
    if (!draft) return;
    await fetch(`/api/newsletter/${draft.id}/edit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conteudo_md: edited }),
    });
    setDraft({ ...draft, conteudo_md: edited });
    setSendStatus('✓ Alterações guardadas.');
  }

  async function send() {
    if (!draft) return;
    // ensure latest edits are saved before sending
    if (edited && edited !== draft.conteudo_md) {
      await saveEdits();
    }
    if (canais.length === 0) { setSendStatus('Selecione pelo menos um canal.'); return; }
    setSendStatus('A colocar em fila …');
    try {
      const r = await api<{ enqueued: number; por_canal: Record<string, number> }>('/api/newsletter/send', {
        method: 'POST',
        body: JSON.stringify({ newsletter_id: draft.id, canais }),
      });
      const detalhe = Object.entries(r.por_canal || {}).map(([c, n]) => `${c}: ${n}`).join(', ');
      setSendStatus(`✓ ${r.enqueued} envio(s) em fila (${detalhe}). A entrega é faseada conforme os limites de cada canal.`);
      mutate();
      mutateQuota();
    } catch (e: any) {
      setSendStatus(`Erro: ${e.message}`);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink-900">Newsletter</h1>
        <p className="text-ink-400 mt-1">
          {canGenerate
            ? 'Gere conteúdos de literacia financeira com o apoio de Inteligência Artificial. Escolha um tema de mercado ou faça o upload de um ficheiro para envio rápido via WhatsApp.'
            : 'Consulte a última newsletter e o histórico de envios da loja. A criação e o envio de newsletters estão reservados aos utilizadores autorizados.'}
        </p>
      </div>

      {canGenerate && quota && (
        <p className="text-ink-400 text-xs flex flex-wrap gap-x-4 gap-y-1">
          {(['email', 'sms'] as const).map((c) => {
            const q = quota[c];
            const esgotado = q.ativo && q.restante === 0;
            return (
              <span key={c} className={esgotado ? 'text-amber-700 font-medium' : ''}>
                {c === 'email' ? 'Email' : 'SMS'}:{' '}
                {q.ativo ? `${q.restante} de ${q.cap_diario} ainda hoje` : 'canal inactivo'}
                {esgotado ? ' — teto atingido, o resto fica em fila para amanhã' : ''}
              </span>
            );
          })}
        </p>
      )}

      {canGenerate && (
        <div className="card space-y-4">
          <label className="block text-sm font-medium text-ink-700">Tema</label>
          <input
            value={tema}
            onChange={(e) => setTema(e.target.value)}
            className="w-full rounded-xl border border-ink-100 px-3 py-2 text-sm"
            placeholder="Ex.: Como ler o seu spread em 2026"
          />
          <div className="flex flex-wrap gap-2">
            {TEMA_SUGESTOES.map((t) => (
              <button key={t} onClick={() => setTema(t)} className="chip">{t}</button>
            ))}
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <button className="btn-primary" disabled={generating} onClick={generate}>
              {generating ? 'A gerar …' : 'Gerar newsletter'}
            </button>
            <span className="text-ink-400 text-sm">ou</span>
            <label className="btn-ghost cursor-pointer">
              <input
                type="file"
                accept=".txt,.md,.markdown,.docx"
                className="hidden"
                onChange={(e) => e.target.files?.[0] && uploadFile(e.target.files[0])}
              />
              Upload de ficheiro (.txt, .md, .docx)
            </label>
            <span className="text-ink-400 text-xs">a IA reformata para o estilo DS</span>
          </div>
        </div>
      )}

      {canGenerate && draft && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-lg font-semibold text-ink-900">Pré-visualização e edição</h2>
              <p className="text-ink-400 text-sm">Tema: {draft.tema} · pode editar o markdown antes de enviar</p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-3 text-sm">
                {(['email', 'sms'] as const).map((c) => (
                  <label key={c} className="flex items-center gap-1.5">
                    <input type="checkbox" checked={canais.includes(c)} onChange={() => toggleCanal(c)} className="h-4 w-4 accent-[color:var(--accent)]" />
                    {c === 'email' ? 'Email' : 'SMS'}
                  </label>
                ))}
              </div>
              <button className="btn-ghost" onClick={saveEdits} disabled={!edited || edited === draft.conteudo_md}>Guardar</button>
              <button className="btn-primary" onClick={send}>Enviar</button>
            </div>
          </div>
          <div className="grid md:grid-cols-2 gap-4">
            <textarea
              value={edited || draft.conteudo_md || ''}
              onChange={(e) => setEdited(e.target.value)}
              className="w-full h-96 rounded-xl border border-ink-100 px-3 py-2 text-sm font-mono"
            />
            <article className="prose max-w-none border border-ink-100 rounded-xl p-4 overflow-auto h-96" dangerouslySetInnerHTML={{ __html: mdToHtml(edited || draft.conteudo_md || '') }} />
          </div>
          {sendStatus && <p className="mt-4 text-sm text-ink-700">{sendStatus}</p>}
        </div>
      )}

      {/* Read-only viewers: last sent newsletter, rendered in full. */}
      {me && !canGenerate && (
        <div className="card">
          <h2 className="text-lg font-semibold text-ink-900 mb-1">Última newsletter</h2>
          {latest ? (
            <>
              <p className="text-ink-400 text-sm mb-4">
                Enviada {latest.enviado_em ? new Date(latest.enviado_em).toLocaleDateString('pt-PT') : ''}
                {latest.enviado_em ? ` (${semanaISO(latest.enviado_em)})` : ''} · {latest.destinatarios_count} destinatário(s)
                {' · '}
                <Link href={`/newsletter/${latest.id}`} className="text-ds-700 hover:underline">abrir página</Link>
              </p>
              {latestFull ? (
                <article
                  className="prose max-w-none border border-ink-100 rounded-xl p-4 overflow-auto"
                  dangerouslySetInnerHTML={{ __html: mdToHtml(latestFull.conteudo_md || '') }}
                />
              ) : (
                <p className="text-ink-400 text-sm">A carregar …</p>
              )}
            </>
          ) : (
            <p className="text-ink-400 text-sm">Ainda não foi enviada nenhuma newsletter.</p>
          )}
        </div>
      )}

      <div className="card">
        <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
          <h3 className="text-base font-semibold text-ink-900">Newsletters enviadas</h3>
          {semanasDisponiveis.length > 1 && (
            <label className="text-xs text-ink-400 flex items-center gap-2">
              Semana
              <select
                value={semanaFiltro}
                onChange={(e) => setSemanaFiltro(e.target.value)}
                className="rounded-lg border border-ink-100 px-2 py-1 text-xs text-ink-700"
              >
                <option value="">Todas</option>
                {semanasDisponiveis.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </label>
          )}
        </div>
        {enviadas.length === 0 ? (
          <p className="text-ink-400 text-sm">Ainda não foi enviada nenhuma newsletter.</p>
        ) : enviadasFiltradas.length === 0 ? (
          <p className="text-ink-400 text-sm">Nenhuma newsletter enviada nessa semana.</p>
        ) : (
          <ul className="text-sm divide-y divide-ink-100">
            {enviadasFiltradas.map((n) => (
              <li key={n.id}>
                <Link
                  href={`/newsletter/${n.id}`}
                  className="py-2 flex items-center justify-between gap-3 hover:bg-ink-50/60 rounded-md px-1 -mx-1"
                >
                  <span className="text-ds-700 underline-offset-2 hover:underline">{n.titulo}</span>
                  <span className="text-ink-400 text-xs whitespace-nowrap">
                    Enviada {n.enviado_em ? new Date(n.enviado_em).toLocaleDateString('pt-PT') : ''}
                    {n.enviado_em ? ` (${semanaISO(n.enviado_em)})` : ''} · {n.destinatarios_count} dest.
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
