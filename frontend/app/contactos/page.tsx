'use client';
import { useEffect, useMemo, useState } from 'react';
import useSWR from 'swr';
import { api } from '../../lib/api';

type Consultor = { id: string; nome: string; cargo: string; n_contactos: number };
type Contacto = { id: number; nome_cliente: string; telefone: string; email?: string };

const WELCOME_HINT =
  'Olá {{nome_cliente}}, é o {{nome_consultor}}. Estou disponível para o ajudar em questões de crédito e seguros. Não hesite em contactar-me.';

export default function ContactosPage() {
  const { data: cdata, mutate: refreshConsultores } = useSWR<{ consultores: Consultor[] }>('/api/broadcasts/consultores', api);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [consultorQ, setConsultorQ] = useState('');
  const [contactQ, setContactQ] = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [tipo, setTipo] = useState<'welcome' | 'custom'>('welcome');
  const [customMsg, setCustomMsg] = useState(WELCOME_HINT);
  const [preview, setPreview] = useState<any | null>(null);
  const [sending, setSending] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [manualContacts, setManualContacts] = useState<{ nome_cliente: string; telefone: string }[]>([
    { nome_cliente: '', telefone: '' }, { nome_cliente: '', telefone: '' },
  ]);

  const { data: welcomeTpl } = useSWR<{ template: string }>('/api/broadcasts/welcome-template', api);
  const [welcomeMsg, setWelcomeMsg] = useState('');
  useEffect(() => { if (welcomeTpl?.template) setWelcomeMsg(welcomeTpl.template); }, [welcomeTpl?.template]);

  const { data: contactos, mutate: refreshContactos } = useSWR<{ contactos: Contacto[] }>(
    selectedId ? `/api/broadcasts/contactos?consultor_id=${encodeURIComponent(selectedId)}` : null, api,
  );
  const consultorSelecionado = cdata?.consultores.find((c) => c.id === selectedId);

  // Reset selection/search when switching consultor
  useEffect(() => { setSelected(new Set()); setContactQ(''); setPreview(null); setStatus(null); }, [selectedId]);

  const consultoresFiltrados = useMemo(() => {
    const q = consultorQ.trim().toLowerCase();
    const list = cdata?.consultores || [];
    return q ? list.filter((c) => (c.nome || '').toLowerCase().includes(q)) : list;
  }, [cdata, consultorQ]);

  const contactosFiltrados = useMemo(() => {
    const list = contactos?.contactos || [];
    const q = contactQ.trim().toLowerCase();
    const qd = contactQ.replace(/\D/g, '');
    if (!q) return list;
    return list.filter((c) => (c.nome_cliente || '').toLowerCase().includes(q) || (qd && (c.telefone || '').replace(/\D/g, '').includes(qd)));
  }, [contactos, contactQ]);

  const allFilteredSelected = contactosFiltrados.length > 0 && contactosFiltrados.every((c) => selected.has(c.telefone));
  function toggleAll() {
    setSelected((prev) => {
      const next = new Set(prev);
      if (allFilteredSelected) contactosFiltrados.forEach((c) => next.delete(c.telefone));
      else contactosFiltrados.forEach((c) => next.add(c.telefone));
      return next;
    });
  }
  function toggleOne(tel: string) {
    setSelected((prev) => { const n = new Set(prev); n.has(tel) ? n.delete(tel) : n.add(tel); return n; });
  }

  const destinatarios = useMemo(() => {
    if (selected.size === 0) return undefined; // todos
    return (contactos?.contactos || []).filter((c) => selected.has(c.telefone)).map((c) => ({ nome_cliente: c.nome_cliente, telefone: c.telefone }));
  }, [selected, contactos]);

  const alvoCount = selected.size > 0 ? selected.size : (consultorSelecionado?.n_contactos ?? 0);

  async function previewBroadcast() {
    if (!selectedId) return;
    setStatus(null);
    const r = await api<any>('/api/broadcasts/preview', {
      method: 'POST',
      body: JSON.stringify({ consultor_id: selectedId, tipo, template: tipo === 'custom' ? customMsg : welcomeMsg || null, destinatarios }),
    });
    setPreview(r);
  }

  async function confirmSend() {
    if (!selectedId) return;
    setSending(true);
    try {
      const r = await api<{ enqueued: number; total: number; por_numero_proprio: boolean }>('/api/broadcasts/send', {
        method: 'POST',
        body: JSON.stringify({ consultor_id: selectedId, tipo, template: tipo === 'custom' ? customMsg : welcomeMsg || null, destinatarios }),
      });
      setStatus(`✓ ${r.enqueued} mensagem(ns) em fila — entrega faseada ${r.por_numero_proprio ? 'pelo número do próprio consultor' : 'pelo número do operador'}.`);
      setPreview(null); setSelected(new Set());
    } catch (e: any) { setStatus(`Erro: ${e.message}`); } finally { setSending(false); }
  }

  async function addManualContacts() {
    if (!selectedId) return;
    const valid = manualContacts.filter((c) => c.nome_cliente.trim() && c.telefone.trim());
    if (!valid.length) return;
    await api('/api/broadcasts/contactos/add', { method: 'POST', body: JSON.stringify({ consultor_id: selectedId, contactos: valid }) });
    setManualContacts([{ nome_cliente: '', telefone: '' }, { nome_cliente: '', telefone: '' }]);
    refreshContactos(); refreshConsultores();
  }
  async function uploadCSV(file: File) {
    setStatus('A processar CSV …');
    const fd = new FormData(); fd.append('file', file);
    try { const res = await fetch('/api/broadcasts/upload', { method: 'POST', body: fd }); const j = await res.json();
      setStatus(`✓ ${j.inserted_total} contactos importados (${j.skipped} ignorados).`); refreshContactos(); refreshConsultores();
    } catch (e: any) { setStatus(`Erro: ${e.message}`); }
  }
  function downloadCsvTemplate() {
    const csv = '﻿Nome do Consultor,Nome do Cliente,Número de contacto\r\nBruno Sousa,Maria Silva,+351 912 345 678\r\n';
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
    const a = document.createElement('a'); a.href = url; a.download = 'modelo-contactos.csv'; a.click(); URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink-900">Contactos dos consultores</h1>
        <p className="text-ink-400 mt-1">Carteiras de contactos vindas do CRM. Pesquise, selecione e envie mensagens em nome de cada consultor.</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        {/* Consultores */}
        <div className="card self-start">
          <input value={consultorQ} onChange={(e) => setConsultorQ(e.target.value)} placeholder="Procurar consultor…" className="mb-3 w-full rounded-lg border border-ink-200 px-3 py-2 text-sm" />
          <ul className="max-h-[70vh] space-y-1 overflow-auto">
            {consultoresFiltrados.map((c) => (
              <li key={c.id}>
                <button onClick={() => setSelectedId(c.id)} className={`flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm ${selectedId === c.id ? 'bg-ds-50 text-ds-700 font-medium' : 'text-ink-700 hover:bg-ink-50'}`}>
                  <span>{c.nome}</span>
                  <span className="chip">{c.n_contactos}</span>
                </button>
              </li>
            ))}
            {!consultoresFiltrados.length && <li className="px-3 text-sm text-ink-400">Sem consultores.</li>}
          </ul>
        </div>

        {/* Detalhe */}
        <div className="space-y-5">
          {!consultorSelecionado ? (
            <div className="card"><p className="text-sm text-ink-400">Seleccione um consultor à esquerda.</p></div>
          ) : (
            <>
              <div className="card">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h2 className="font-semibold text-ink-900">{consultorSelecionado.nome}</h2>
                    <p className="text-sm text-ink-400">{consultorSelecionado.n_contactos} contactos no CRM{selected.size > 0 ? ` · ${selected.size} selecionados` : ''}</p>
                  </div>
                  <button onClick={() => setShowAdd((v) => !v)} className="text-sm text-ds-700 hover:underline">{showAdd ? 'Fechar' : '+ Adicionar contactos'}</button>
                </div>

                {showAdd && (
                  <div className="mt-4 space-y-3 rounded-xl border border-ink-100 p-4">
                    <div className="flex flex-wrap items-center gap-3">
                      <input type="file" accept=".csv" onChange={(e) => e.target.files && uploadCSV(e.target.files[0])} className="text-sm" />
                      <button onClick={downloadCsvTemplate} className="btn-ghost text-xs">↓ Modelo CSV</button>
                    </div>
                    {manualContacts.map((mc, i) => (
                      <div key={i} className="grid grid-cols-2 gap-2">
                        <input value={mc.nome_cliente} onChange={(e) => { const n = [...manualContacts]; n[i] = { ...n[i], nome_cliente: e.target.value }; setManualContacts(n); }} placeholder="Nome do cliente" className="rounded-lg border border-ink-100 px-2 py-1.5 text-sm" />
                        <input value={mc.telefone} onChange={(e) => { const n = [...manualContacts]; n[i] = { ...n[i], telefone: e.target.value }; setManualContacts(n); }} placeholder="+351 9XX XXX XXX" className="rounded-lg border border-ink-100 px-2 py-1.5 text-sm font-mono" />
                      </div>
                    ))}
                    <button onClick={addManualContacts} className="btn-ghost">Adicionar</button>
                  </div>
                )}
              </div>

              {/* Tabela de contactos com pesquisa + multi-seleção */}
              <div className="card">
                <div className="mb-3 flex flex-wrap items-center gap-3">
                  <input value={contactQ} onChange={(e) => setContactQ(e.target.value)} placeholder="Procurar por nome ou telefone…" className="min-w-0 flex-1 rounded-lg border border-ink-200 px-3 py-2 text-sm" />
                  <span className="text-xs text-ink-400">{contactosFiltrados.length} de {contactos?.contactos.length ?? 0}</span>
                  {selected.size > 0 && <button onClick={() => setSelected(new Set())} className="text-xs text-ds-700 hover:underline">limpar seleção</button>}
                </div>
                <div className="max-h-[50vh] overflow-auto rounded-lg border border-ink-100">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-ink-50 text-left text-xs uppercase tracking-wider text-ink-400">
                      <tr>
                        <th className="w-10 px-3 py-2"><input type="checkbox" checked={allFilteredSelected} onChange={toggleAll} className="h-4 w-4 accent-[color:var(--accent)]" /></th>
                        <th className="px-2 py-2">Cliente</th>
                        <th className="px-2 py-2">Telefone</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-100">
                      {contactosFiltrados.map((c) => (
                        <tr key={c.id} className={selected.has(c.telefone) ? 'bg-ds-50/40' : 'hover:bg-ink-50/60'}>
                          <td className="px-3 py-1.5"><input type="checkbox" checked={selected.has(c.telefone)} onChange={() => toggleOne(c.telefone)} className="h-4 w-4 accent-[color:var(--accent)]" /></td>
                          <td className="px-2 py-1.5 text-ink-900">{c.nome_cliente}</td>
                          <td className="px-2 py-1.5 font-mono text-xs text-ink-500">{c.telefone}</td>
                        </tr>
                      ))}
                      {!contactosFiltrados.length && <tr><td colSpan={3} className="px-3 py-6 text-center text-sm text-ink-400">{contactos ? 'Sem contactos.' : 'A carregar …'}</td></tr>}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Compositor */}
              <div className="card space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="font-medium text-ink-900">Enviar mensagem</h3>
                  <div className="flex gap-2">
                    <button onClick={() => setTipo('welcome')} className={`chip ${tipo === 'welcome' ? 'bg-ds-500 text-white' : ''}`}>Boas-vindas</button>
                    <button onClick={() => setTipo('custom')} className={`chip ${tipo === 'custom' ? 'bg-ds-500 text-white' : ''}`}>Personalizada</button>
                  </div>
                </div>
                <textarea value={tipo === 'welcome' ? welcomeMsg : customMsg} onChange={(e) => (tipo === 'welcome' ? setWelcomeMsg : setCustomMsg)(e.target.value)} rows={tipo === 'welcome' ? 6 : 4} className="w-full rounded-xl border border-ink-100 px-3 py-2 text-sm" />
                <p className="text-xs text-ink-400">Placeholders: <code>{'{{nome_consultor}}'}</code>, <code>{'{{nome_cliente}}'}</code> — substituídos por destinatário.</p>
                <div className="flex flex-wrap items-center gap-3">
                  <button onClick={previewBroadcast} disabled={alvoCount === 0} className="btn-primary">Pré-visualizar e enviar</button>
                  <span className="text-sm text-ink-500">Alvo: <b>{alvoCount}</b> {selected.size > 0 ? 'selecionados' : 'contactos (todos)'}</span>
                </div>
                {status && <p className="text-sm text-ink-700">{status}</p>}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Preview modal */}
      {preview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 p-4">
          <div className="w-full max-w-xl rounded-2xl bg-white p-6 shadow-2xl">
            <div className="mb-3 flex items-start justify-between">
              <div>
                <h3 className="font-semibold text-ink-900">Pré-visualização</h3>
                <p className="text-sm text-ink-400">De <b>{preview.consultor_nome}</b> para <b>{preview.n_contactos}</b> contactos · exemplo para <b>{preview.sample_recipient}</b>:</p>
              </div>
              <button onClick={() => setPreview(null)} className="text-2xl leading-none text-ink-400 hover:text-ds-600">×</button>
            </div>
            <div className="mb-4 whitespace-pre-wrap rounded-xl bg-ink-50 p-4 text-sm text-ink-900">{preview.sample_message}</div>
            <div className="mb-4 rounded-lg bg-ink-50 px-3 py-2 text-xs text-ink-500">ℹ️ Envio faseado via WhatsApp {preview.por_numero_proprio ? 'pelo número do próprio consultor' : 'pelo número do operador'}. Respeita os limites de lote/intervalo.</div>
            <div className="flex justify-end gap-2">
              <button onClick={() => setPreview(null)} className="btn-ghost">Cancelar</button>
              <button onClick={confirmSend} disabled={sending} className="btn-primary">{sending ? 'A enviar …' : `Enviar para ${preview.n_contactos}`}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
