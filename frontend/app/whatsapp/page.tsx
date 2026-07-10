'use client';
import { useEffect, useMemo, useState } from 'react';
import useSWR from 'swr';
import { api } from '../../lib/api';
import { useMe } from '../../lib/useMe';

type Status = { configured: boolean; instance: string | null; connected: boolean; state: string | null; profile_name?: string | null; numero?: string | null };
type ConnectResp = { configured: boolean; instance: string; qr: string | null; code: string | null };
type Template = { id: number; nome: string; categoria: string | null; corpo: string; ativo: boolean };
type HistMsg = { id: number; destinatario: string; corpo: string; status: string; agendado_para: string | null; enviado_em: string | null; erro: string | null };
type Cliente = { crm_id: number; nome: string | null; telefone: string | null };

function qrSrc(qr: string) { return qr.startsWith('data:') ? qr : `data:image/png;base64,${qr}`; }
function resolve(text: string, cliente: string, consultor: string) {
  return text.split('{{nome_cliente}}').join(cliente || '').split('{{nome_consultor}}').join(consultor || '');
}
const STATUS_LABEL: Record<string, string> = { pendente: 'Em fila', enviado: 'Enviado', falhou: 'Falhou', cancelado: 'Cancelado' };

// ---- Connect (QR) --------------------------------------------------------
function ConnectCard({ status, onChange }: { status: Status; onChange: () => void }) {
  const [qr, setQr] = useState<string | null>(null);
  const [code, setCode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (status.connected) { setQr(null); setCode(null); } }, [status.connected]);

  async function connect() {
    setBusy(true); setErr(null);
    try {
      const r = await api<ConnectResp>('/api/messaging/whatsapp/connect', { method: 'POST' });
      setQr(r.qr); setCode(r.code); onChange();
    } catch (e: any) { setErr(e.message?.includes('não está configurado') ? 'Serviço WhatsApp não configurado no servidor.' : `Erro: ${e.message}`); }
    finally { setBusy(false); }
  }

  return (
    <div className="card space-y-4">
      <div className="flex items-center gap-3">
        <span className={`inline-block h-2.5 w-2.5 rounded-full ${status.state === 'connecting' ? 'bg-amber-500' : 'bg-ink-300'}`} />
        <span className="text-sm font-medium text-ink-900">{status.state === 'connecting' ? 'A ligar …' : 'Não ligado'}</span>
      </div>
      <button onClick={connect} disabled={busy} className="btn-primary">{busy ? 'A preparar …' : qr ? 'Gerar novo QR' : 'Ligar WhatsApp'}</button>
      {qr && (
        <div className="space-y-2">
          <p className="text-sm text-ink-600">No telemóvel: WhatsApp → <b>Dispositivos ligados</b> → <b>Ligar um dispositivo</b> e leia o código. Atualiza sozinho quando ligar.</p>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={qrSrc(qr)} alt="QR code WhatsApp" className="h-56 w-56 rounded-lg border border-ink-100" />
        </div>
      )}
      {!qr && code && <p className="text-sm text-ink-600">Código de emparelhamento: <b>{code}</b></p>}
      {err && <p className="text-sm text-ds-700">{err}</p>}
    </div>
  );
}

// ---- Template manager (modal) --------------------------------------------
function TemplateManager({ templates, onClose, onChange }: { templates: Template[]; onClose: () => void; onChange: () => void }) {
  const [sel, setSel] = useState<number | 'new' | null>(null);
  const cur = typeof sel === 'number' ? templates.find((t) => t.id === sel) : undefined;
  const [f, setF] = useState({ nome: '', categoria: '', corpo: '' });
  useEffect(() => {
    if (sel === 'new') setF({ nome: '', categoria: '', corpo: '' });
    else if (cur) setF({ nome: cur.nome, categoria: cur.categoria ?? '', corpo: cur.corpo });
  }, [sel, cur]);

  async function save() {
    const body = { nome: f.nome, categoria: f.categoria || null, corpo: f.corpo };
    if (sel === 'new') await api('/api/messaging/templates', { method: 'POST', body: JSON.stringify(body) });
    else if (cur) await api(`/api/messaging/templates/${cur.id}`, { method: 'PUT', body: JSON.stringify(body) });
    onChange(); setSel(null);
  }
  async function del() {
    if (!cur || !confirm(`Apagar o template "${cur.nome}"?`)) return;
    await api(`/api/messaging/templates/${cur.id}`, { method: 'DELETE' }); onChange(); setSel(null);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="w-full max-w-3xl rounded-2xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-ink-900">Templates da loja</h3>
          <button onClick={onClose} className="text-ink-400 hover:text-ds-600 text-2xl leading-none">×</button>
        </div>
        <div className="grid gap-4 md:grid-cols-[220px_1fr]">
          <nav className="space-y-1">
            <button onClick={() => setSel('new')} className="mb-1 w-full rounded-md bg-[color:var(--accent)] px-2 py-1 text-xs font-medium text-white">+ Novo template</button>
            {templates.map((t) => (
              <button key={t.id} onClick={() => setSel(t.id)} className={`block w-full rounded-lg px-3 py-2 text-left text-sm ${sel === t.id ? 'bg-ink-100 font-medium' : 'text-ink-600 hover:bg-ink-50'}`}>
                {t.nome}<span className="block text-[11px] text-ink-400">{t.categoria}</span>
              </button>
            ))}
          </nav>
          <div>
            {sel == null ? <p className="text-sm text-ink-400">Selecione um template ou crie um novo.</p> : (
              <div className="space-y-3">
                <input value={f.nome} onChange={(e) => setF({ ...f, nome: e.target.value })} placeholder="Nome" className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm" />
                <input value={f.categoria} onChange={(e) => setF({ ...f, categoria: e.target.value })} placeholder="Categoria (ex.: aniversario)" className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm" />
                <textarea value={f.corpo} onChange={(e) => setF({ ...f, corpo: e.target.value })} rows={5} className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm font-mono" placeholder="Mensagem. Placeholders: {{nome_cliente}}, {{nome_consultor}}" />
                <p className="text-xs text-ink-400">Placeholders: <code>{'{{nome_cliente}}'}</code>, <code>{'{{nome_consultor}}'}</code></p>
                <div className="flex gap-2">
                  <button onClick={save} disabled={!f.nome || !f.corpo} className="btn-primary">Guardar</button>
                  {cur && <button onClick={del} className="rounded-lg border border-ds-200 px-3 py-1.5 text-sm text-ds-700 hover:bg-ds-50">Apagar</button>}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---- Composer + history --------------------------------------------------
function Console({ status }: { status: Status }) {
  const { me, can } = useMe();
  const nomeConsultor = me?.nome ?? '';
  const { data: tdata, mutate: mutTpl } = useSWR<{ templates: Template[] }>('/api/messaging/templates', api);
  const { data: hist, mutate: mutHist } = useSWR<{ mensagens: HistMsg[] }>('/api/messaging/whatsapp/history', api, { refreshInterval: 15000 });
  const templates = tdata?.templates ?? [];

  const [mode, setMode] = useState<'crm' | 'manual'>('crm');
  const [q, setQ] = useState('');
  const { data: cli } = useSWR<{ clientes: Cliente[] }>(mode === 'crm' && q.trim().length >= 2 ? `/api/messaging/whatsapp/clientes?q=${encodeURIComponent(q)}` : null, api);
  const [sel, setSel] = useState<Cliente | null>(null);
  const [manualNome, setManualNome] = useState('');
  const [manualNum, setManualNum] = useState('');
  const [corpo, setCorpo] = useState('');
  const [quando, setQuando] = useState<'now' | 'later'>('now');
  const [dataHora, setDataHora] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [showTpl, setShowTpl] = useState(false);

  const nomeCliente = mode === 'crm' ? (sel?.nome ?? '') : manualNome;
  const numero = mode === 'crm' ? (sel?.telefone ?? '') : manualNum;
  const grupos = useMemo(() => {
    const g: Record<string, Template[]> = {};
    templates.forEach((t) => { (g[t.categoria || 'outros'] ??= []).push(t); });
    return g;
  }, [templates]);

  function applyTemplate(t: Template) { setCorpo(resolve(t.corpo, nomeCliente, nomeConsultor)); }

  async function send() {
    setMsg(null);
    if (!numero) { setMsg('Escolha um destinatário.'); return; }
    if (!corpo.trim()) { setMsg('Mensagem vazia.'); return; }
    if (quando === 'later' && !dataHora) { setMsg('Escolha a data/hora do agendamento.'); return; }
    setBusy(true);
    try {
      const finalCorpo = resolve(corpo, nomeCliente, nomeConsultor);
      const agendado_para = quando === 'later' ? new Date(dataHora).toISOString() : null;
      const r = await api<{ enqueued: number; agendado: boolean }>('/api/messaging/whatsapp/send', {
        method: 'POST', body: JSON.stringify({ numero, corpo: finalCorpo, agendado_para }),
      });
      setMsg(r.agendado ? `✓ Mensagem agendada para ${new Date(dataHora).toLocaleString('pt-PT')}.` : '✓ Mensagem em fila para envio.');
      setCorpo(''); mutHist();
    } catch (e: any) { setMsg(`Erro: ${e.message}`); } finally { setBusy(false); }
  }

  return (
    <div className="space-y-6">
      {/* Estado / perfil */}
      <div className="card flex flex-wrap items-center gap-3">
        <span className="inline-block h-2.5 w-2.5 rounded-full bg-emerald-500" />
        <span className="text-sm font-medium text-ink-900">Ligado</span>
        {status.profile_name && <span className="text-sm text-ink-600">· Aparece como <b>{status.profile_name}</b></span>}
        {status.numero && <span className="text-xs text-ink-400">(+{status.numero})</span>}
        <button onClick={async () => { if (confirm('Desligar o WhatsApp deste utilizador?')) { await api('/api/messaging/whatsapp/logout', { method: 'POST' }); location.reload(); } }}
          className="ml-auto text-xs text-ds-700 hover:underline">Desligar</button>
      </div>

      {/* Compositor */}
      <div className="card space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-ink-900">Nova mensagem</h2>
          {can('messaging.config') && <button onClick={() => setShowTpl(true)} className="text-sm text-ds-700 hover:underline">Gerir templates</button>}
        </div>

        {/* Destinatário */}
        <div className="flex gap-2 text-sm">
          <button onClick={() => setMode('crm')} className={`rounded-lg px-3 py-1.5 ${mode === 'crm' ? 'bg-ds-50 text-ds-700 font-medium' : 'text-ink-500 hover:bg-ink-50'}`}>Cliente do CRM</button>
          <button onClick={() => setMode('manual')} className={`rounded-lg px-3 py-1.5 ${mode === 'manual' ? 'bg-ds-50 text-ds-700 font-medium' : 'text-ink-500 hover:bg-ink-50'}`}>Número à mão</button>
        </div>
        {mode === 'crm' ? (
          <div>
            <input value={q} onChange={(e) => { setQ(e.target.value); setSel(null); }} placeholder="Pesquisar cliente por nome…" className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm" />
            {sel ? (
              <p className="mt-2 text-sm text-ink-700">Para: <b>{sel.nome}</b> <span className="text-ink-400">({sel.telefone})</span> <button onClick={() => { setSel(null); setQ(''); }} className="ml-2 text-xs text-ds-700 hover:underline">alterar</button></p>
            ) : (cli?.clientes?.length ? (
              <ul className="mt-2 max-h-40 divide-y divide-ink-100 overflow-auto rounded-lg border border-ink-100 text-sm">
                {cli.clientes.filter((c) => c.telefone).map((c) => (
                  <li key={c.crm_id}><button onClick={() => setSel(c)} className="flex w-full justify-between px-3 py-2 hover:bg-ink-50"><span>{c.nome}</span><span className="text-ink-400">{c.telefone}</span></button></li>
                ))}
              </ul>
            ) : q.trim().length >= 2 ? <p className="mt-2 text-sm text-ink-400">Sem resultados.</p> : null)}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            <input value={manualNome} onChange={(e) => setManualNome(e.target.value)} placeholder="Nome do cliente" className="rounded-lg border border-ink-200 px-3 py-2 text-sm" />
            <input value={manualNum} onChange={(e) => setManualNum(e.target.value)} placeholder="Número (+3519…)" className="rounded-lg border border-ink-200 px-3 py-2 text-sm" />
          </div>
        )}

        {/* Template + texto */}
        <div className="flex flex-wrap gap-2">
          {Object.entries(grupos).map(([cat, ts]) => ts.map((t) => (
            <button key={t.id} onClick={() => applyTemplate(t)} className="chip" title={t.categoria || ''}>{t.nome}</button>
          )))}
        </div>
        <textarea value={corpo} onChange={(e) => setCorpo(e.target.value)} rows={5} placeholder="Escreva a mensagem ou escolha um template acima…" className="w-full rounded-xl border border-ink-200 px-3 py-2 text-sm" />
        <p className="text-xs text-ink-400">Placeholders resolvidos no envio: <code>{'{{nome_cliente}}'}</code> → {nomeCliente || 'cliente'}, <code>{'{{nome_consultor}}'}</code> → {nomeConsultor || 'você'}.</p>

        {/* Agendamento */}
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1.5 text-sm"><input type="radio" checked={quando === 'now'} onChange={() => setQuando('now')} /> Enviar já</label>
          <label className="flex items-center gap-1.5 text-sm"><input type="radio" checked={quando === 'later'} onChange={() => setQuando('later')} /> Agendar</label>
          {quando === 'later' && <input type="datetime-local" value={dataHora} onChange={(e) => setDataHora(e.target.value)} className="rounded-lg border border-ink-200 px-3 py-1.5 text-sm" />}
          <button onClick={send} disabled={busy} className="btn-primary ml-auto">{busy ? 'A processar …' : quando === 'later' ? 'Agendar' : 'Enviar'}</button>
        </div>
        {msg && <p className="text-sm text-ink-700">{msg}</p>}
      </div>

      {/* Histórico */}
      <div className="card">
        <h3 className="mb-3 text-base font-semibold text-ink-900">Histórico</h3>
        {!hist?.mensagens?.length ? <p className="text-sm text-ink-400">Ainda não enviou mensagens.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs uppercase tracking-wider text-ink-400">
                <th className="py-2 pr-3">Para</th><th className="py-2 pr-3">Mensagem</th><th className="py-2 pr-3">Estado</th><th className="py-2">Quando</th>
              </tr></thead>
              <tbody className="divide-y divide-ink-100">
                {hist.mensagens.map((m) => (
                  <tr key={m.id}>
                    <td className="py-2 pr-3 whitespace-nowrap">+{m.destinatario}</td>
                    <td className="py-2 pr-3 text-ink-600">{m.corpo.slice(0, 60)}{m.corpo.length > 60 ? '…' : ''}</td>
                    <td className="py-2 pr-3"><span className={`rounded px-1.5 py-0.5 text-xs ${m.status === 'enviado' ? 'bg-emerald-50 text-emerald-700' : m.status === 'falhou' ? 'bg-ds-50 text-ds-700' : 'bg-ink-100 text-ink-500'}`}>{STATUS_LABEL[m.status] ?? m.status}</span></td>
                    <td className="py-2 whitespace-nowrap text-ink-400 text-xs">{new Date(m.enviado_em || m.agendado_para || '').toLocaleString('pt-PT')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showTpl && <TemplateManager templates={templates} onClose={() => setShowTpl(false)} onChange={() => mutTpl()} />}
    </div>
  );
}

export default function WhatsAppPage() {
  const { data: status, mutate } = useSWR<Status>('/api/messaging/whatsapp/status', api, {
    refreshInterval: (d) => (d && d.configured && !d.connected ? 3000 : 0),
  });

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-semibold text-ink-900">WhatsApp</h1>
        <p className="text-ink-400 mt-1">Envie mensagens aos clientes <b>em seu nome</b> — as mensagens saem do seu próprio número.</p>
      </div>

      {status && !status.configured && (
        <div className="card"><p className="text-sm text-ink-600">O serviço WhatsApp (Evolution) ainda não está configurado no servidor.</p></div>
      )}
      {status?.configured && !status.connected && <ConnectCard status={status} onChange={() => mutate()} />}
      {status?.configured && status.connected && <Console status={status} />}
      {!status && <p className="text-sm text-ink-400">A carregar …</p>}
    </div>
  );
}
