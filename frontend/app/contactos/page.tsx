'use client';
import { useEffect, useState } from 'react';
import useSWR from 'swr';
import { api } from '../../lib/api';

type Consultor = { id: string; nome: string; cargo: string; n_contactos: number };
type Contacto = { id: string; nome_cliente: string; telefone: string; email?: string; created_at: string };

const WELCOME_HINT =
  "Olá {{nome_cliente}}, é o {{nome_consultor}}. Quero informar que, desde já, estou a colaborar com a DS Crédito Ramada como consultor de crédito e seguros. Terei muito gosto em ser-lhe útil sempre que necessitar. Não hesite em contactar-me.";

export default function ContactosPage() {
  const { data: cdata, mutate: refreshConsultores } = useSWR<{ consultores: Consultor[] }>(
    '/api/broadcasts/consultores',
    api
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tipo, setTipo] = useState<'welcome' | 'custom'>('welcome');
  const [customMsg, setCustomMsg] = useState<string>(WELCOME_HINT);
  const [preview, setPreview] = useState<any | null>(null);
  const [sending, setSending] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  // manual contact entry state (for the demo — quicker than CSV upload)
  const [manualContacts, setManualContacts] = useState<{ nome_cliente: string; telefone: string }[]>([
    { nome_cliente: '', telefone: '' },
    { nome_cliente: '', telefone: '' },
    { nome_cliente: '', telefone: '' },
  ]);

  // Welcome message: fetched from the backend so the operator can see and
  // edit the real blast text before sending (item 5).
  const { data: welcomeTpl } = useSWR<{ template: string }>('/api/broadcasts/welcome-template', api);
  const [welcomeMsg, setWelcomeMsg] = useState('');
  useEffect(() => {
    if (welcomeTpl?.template) setWelcomeMsg(welcomeTpl.template);
  }, [welcomeTpl?.template]);

  const consultorSelecionado = cdata?.consultores.find((c) => c.id === selectedId);

  function downloadCsvTemplate() {
    const header = 'Nome do Consultor,Nome do Cliente,Número de contacto';
    const example = 'Bruno Sousa,Maria Silva,+351 912 345 678';
    // BOM so Excel opens it as UTF-8 (preserves acentos).
    const csv = '﻿' + header + '\r\n' + example + '\r\n';
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'modelo-contactos.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  const { data: contactos, mutate: refreshContactos } = useSWR<{ contactos: Contacto[] }>(
    selectedId ? `/api/broadcasts/contactos?consultor_id=${selectedId}` : null,
    api
  );

  async function addManualContacts() {
    if (!selectedId) return;
    const valid = manualContacts.filter((c) => c.nome_cliente.trim() && c.telefone.trim());
    if (!valid.length) return;
    await api('/api/broadcasts/contactos/add', {
      method: 'POST',
      body: JSON.stringify({ consultor_id: selectedId, contactos: valid }),
    });
    setManualContacts([{ nome_cliente: '', telefone: '' }, { nome_cliente: '', telefone: '' }, { nome_cliente: '', telefone: '' }]);
    refreshContactos();
    refreshConsultores();
  }

  async function uploadCSV(file: File) {
    setStatus('A processar CSV …');
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await fetch('/api/broadcasts/upload', { method: 'POST', body: fd });
      const j = await res.json();
      setStatus(`✓ ${j.inserted_total} contactos importados (${j.skipped} ignorados).`);
      refreshContactos();
      refreshConsultores();
    } catch (e: any) {
      setStatus(`Erro: ${e.message}`);
    }
  }

  async function previewBroadcast() {
    if (!selectedId) return;
    setStatus(null);
    const r = await api<any>('/api/broadcasts/preview', {
      method: 'POST',
      body: JSON.stringify({
        consultor_id: selectedId,
        tipo,
        template: tipo === 'custom' ? customMsg : welcomeMsg || null,
      }),
    });
    setPreview(r);
  }

  async function confirmSend() {
    if (!selectedId) return;
    setSending(true);
    try {
      const r = await api<{ enqueued: number; total: number; por_numero_proprio: boolean }>('/api/broadcasts/send', {
        method: 'POST',
        body: JSON.stringify({
          consultor_id: selectedId,
          tipo,
          template: tipo === 'custom' ? customMsg : welcomeMsg || null,
        }),
      });
      setStatus(`✓ ${r.enqueued} mensagem(ns) em fila — entrega faseada ${r.por_numero_proprio ? 'pelo número do próprio consultor' : 'pelo número do operador'}.`);
      setPreview(null);
    } catch (e: any) {
      setStatus(`Erro: ${e.message}`);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink-900">Contactos dos consultores</h1>
        <p className="text-ink-400 mt-1">
          Centralize e gira as carteiras de contactos da equipa. Permite
          automatizar réguas de comunicação e mensagens de acompanhamento
          regulares em nome de cada consultor.
        </p>
      </div>

      <div className="grid md:grid-cols-3 gap-6">
        <div className="card">
          <h2 className="font-semibold text-ink-900 mb-3">Consultores</h2>
          <ul className="space-y-1">
            {(cdata?.consultores || []).map((c) => (
              <li key={c.id}>
                <button
                  onClick={() => { setSelectedId(c.id); setPreview(null); setStatus(null); }}
                  className={`w-full text-left px-3 py-2 rounded-xl text-sm flex items-center justify-between ${selectedId === c.id ? 'bg-ds-50 text-ds-700' : 'hover:bg-ink-50 text-ink-700'}`}
                >
                  <span>{c.nome}<br/><span className="text-xs text-ink-400">{c.cargo}</span></span>
                  <span className="chip">{c.n_contactos}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="card md:col-span-2 space-y-5">
          {!consultorSelecionado ? (
            <p className="text-ink-400 text-sm">Seleccione um consultor à esquerda para gerir os seus contactos.</p>
          ) : (
            <>
              <div>
                <h2 className="font-semibold text-ink-900">{consultorSelecionado.nome}</h2>
                <p className="text-ink-400 text-sm">{consultorSelecionado.n_contactos} contactos carregados</p>
              </div>

              {/* CSV upload + manual entry */}
              <div className="rounded-xl border border-ink-100 p-4">
                <h3 className="font-medium text-ink-900 mb-2">Adicionar contactos</h3>
                <p className="text-xs text-ink-400 mb-3">
                  Upload CSV (colunas: <code>Nome do Consultor, Nome do Cliente, Número de contacto</code>), ou adicione manualmente abaixo.
                </p>
                <div className="flex items-center gap-3 mb-3 flex-wrap">
                  <input
                    type="file"
                    accept=".csv"
                    onChange={(e) => e.target.files && uploadCSV(e.target.files[0])}
                    className="text-sm"
                  />
                  <button type="button" onClick={downloadCsvTemplate} className="btn-ghost text-xs">
                    ↓ Descarregar modelo CSV
                  </button>
                </div>
                <div className="space-y-2">
                  {manualContacts.map((mc, i) => (
                    <div key={i} className="grid grid-cols-2 gap-2">
                      <input
                        value={mc.nome_cliente}
                        onChange={(e) => {
                          const next = [...manualContacts];
                          next[i] = { ...next[i], nome_cliente: e.target.value };
                          setManualContacts(next);
                        }}
                        placeholder="Nome do cliente"
                        className="rounded-lg border border-ink-100 px-2 py-1.5 text-sm"
                      />
                      <input
                        value={mc.telefone}
                        onChange={(e) => {
                          const next = [...manualContacts];
                          next[i] = { ...next[i], telefone: e.target.value };
                          setManualContacts(next);
                        }}
                        placeholder="+351 9XX XXX XXX"
                        className="rounded-lg border border-ink-100 px-2 py-1.5 text-sm font-mono"
                      />
                    </div>
                  ))}
                </div>
                <button className="btn-ghost mt-3" onClick={addManualContacts}>Adicionar contactos</button>
              </div>

              {/* Contact list */}
              {contactos && contactos.contactos.length > 0 && (
                <div className="rounded-xl border border-ink-100 p-4">
                  <h3 className="font-medium text-ink-900 mb-2">Lista actual</h3>
                  <ul className="text-sm divide-y divide-ink-100 max-h-48 overflow-auto">
                    {contactos.contactos.map((c) => (
                      <li key={c.id} className="py-1.5 flex items-center justify-between">
                        <span className="text-ink-900">{c.nome_cliente}</span>
                        <span className="font-mono text-xs text-ink-400">{c.telefone}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Broadcast composer */}
              {(contactos?.contactos.length || 0) > 0 && (
                <div className="rounded-xl border border-ink-100 p-4 space-y-3">
                  <h3 className="font-medium text-ink-900">Disparar mensagem</h3>
                  <div className="flex gap-2">
                    <button onClick={() => setTipo('welcome')} className={`chip ${tipo === 'welcome' ? 'bg-ds-500 text-white' : ''}`}>Boas-vindas</button>
                    <button onClick={() => setTipo('custom')} className={`chip ${tipo === 'custom' ? 'bg-ds-500 text-white' : ''}`}>Mensagem personalizada</button>
                  </div>

                  {tipo === 'welcome' && (
                    <>
                      <p className="text-xs text-ink-400">
                        Esta é a mensagem de boas-vindas enviada em nome do consultor. Pode editá-la antes de enviar — placeholders <code>{`{{nome_consultor}}`}</code> e <code>{`{{nome_cliente}}`}</code> são substituídos por cada destinatário.
                      </p>
                      <textarea
                        value={welcomeMsg}
                        onChange={(e) => setWelcomeMsg(e.target.value)}
                        className="w-full rounded-xl border border-ink-100 px-3 py-2 text-sm font-mono h-40"
                      />
                    </>
                  )}

                  {tipo === 'custom' && (
                    <>
                      <p className="text-xs text-ink-400">
                        Placeholders disponíveis: <code>{`{{nome_consultor}}`}</code>, <code>{`{{nome_cliente}}`}</code> — serão substituídos por cada destinatário.
                      </p>
                      <textarea
                        value={customMsg}
                        onChange={(e) => setCustomMsg(e.target.value)}
                        className="w-full rounded-xl border border-ink-100 px-3 py-2 text-sm font-mono h-32"
                      />
                    </>
                  )}

                  <button className="btn-primary" onClick={previewBroadcast}>
                    Pré-visualizar
                  </button>
                </div>
              )}

              {status && <div className="text-sm text-ink-700">{status}</div>}
            </>
          )}
        </div>
      </div>

      {/* Preview modal */}
      {preview && (
        <div className="fixed inset-0 bg-ink-900/40 z-50 flex items-end md:items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-xl w-full p-6 shadow-2xl">
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="font-semibold text-ink-900">Pré-visualização</h3>
                <p className="text-ink-400 text-sm">
                  De <strong>{preview.consultor_nome}</strong> para <strong>{preview.n_contactos}</strong> contactos · exemplo para <strong>{preview.sample_recipient}</strong>:
                </p>
              </div>
              <button onClick={() => setPreview(null)} className="text-ink-400 hover:text-ds-600 text-2xl leading-none">×</button>
            </div>

            <div className="rounded-xl bg-ink-50 p-4 whitespace-pre-wrap text-sm text-ink-900 mb-4">
              {preview.sample_message}
            </div>

            <div className="text-xs rounded-lg bg-ink-50 text-ink-500 px-3 py-2 mb-4">
              ℹ️ Envio faseado via WhatsApp {preview.por_numero_proprio
                ? 'pelo número do próprio consultor'
                : 'pelo número do operador (este consultor ainda não ligou o WhatsApp dele)'}. Respeita os limites de lote/intervalo configurados.
            </div>

            <div className="flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setPreview(null)}>Cancelar</button>
              <button className="btn-primary" disabled={sending} onClick={confirmSend}>
                {sending ? 'A enviar …' : `Enviar para ${preview.n_contactos} contactos`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
