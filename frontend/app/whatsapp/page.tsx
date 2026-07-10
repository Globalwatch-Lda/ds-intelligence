'use client';
import { useEffect, useRef, useState } from 'react';
import useSWR from 'swr';
import { api } from '../../lib/api';

type Status = { configured: boolean; instance: string | null; connected: boolean; state: string | null };
type ConnectResp = { configured: boolean; instance: string; qr: string | null; code: string | null };

function qrSrc(qr: string): string {
  return qr.startsWith('data:') ? qr : `data:image/png;base64,${qr}`;
}

export default function WhatsAppPage() {
  const { data: status, mutate } = useSWR<Status>('/api/messaging/whatsapp/status', api, {
    refreshInterval: (d) => (d && d.configured && !d.connected ? 3000 : 0),
  });
  const [qr, setQr] = useState<string | null>(null);
  const [code, setCode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const wasConnecting = useRef(false);

  // Once connected, clear the QR.
  useEffect(() => {
    if (status?.connected) { setQr(null); setCode(null); wasConnecting.current = false; }
  }, [status?.connected]);

  async function connect() {
    setBusy(true); setErr(null);
    try {
      const r = await api<ConnectResp>('/api/messaging/whatsapp/connect', { method: 'POST' });
      setQr(r.qr); setCode(r.code); wasConnecting.current = true;
      mutate();
    } catch (e: any) {
      setErr(e.message?.includes('não está configurado') ? 'O serviço WhatsApp não está configurado no servidor.' : `Erro: ${e.message}`);
    } finally { setBusy(false); }
  }

  async function logout() {
    if (!confirm('Desligar o WhatsApp deste utilizador?')) return;
    setBusy(true);
    try { await api('/api/messaging/whatsapp/logout', { method: 'POST' }); setQr(null); setCode(null); mutate(); }
    catch (e: any) { setErr(`Erro: ${e.message}`); } finally { setBusy(false); }
  }

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-2xl font-semibold text-ink-900">WhatsApp</h1>
        <p className="text-ink-400 mt-1">
          Ligue o seu número de WhatsApp para enviar mensagens aos clientes <b>em seu nome</b>.
          As mensagens saem do seu próprio número.
        </p>
      </div>

      {status && !status.configured && (
        <div className="card">
          <p className="text-sm text-ink-600">
            O serviço WhatsApp (Evolution) ainda não está configurado no servidor. Assim que estiver,
            poderá ligar o seu número aqui.
          </p>
        </div>
      )}

      {status?.configured && (
        <div className="card space-y-4">
          <div className="flex items-center gap-3">
            <span className={`inline-block h-2.5 w-2.5 rounded-full ${status.connected ? 'bg-emerald-500' : 'bg-ink-300'}`} />
            <span className="text-sm font-medium text-ink-900">
              {status.connected ? 'Ligado' : status.state === 'connecting' ? 'A ligar …' : 'Não ligado'}
            </span>
            {status.instance && <span className="text-xs text-ink-400">({status.instance})</span>}
          </div>

          {status.connected ? (
            <button onClick={logout} disabled={busy} className="rounded-lg border border-ds-200 px-3 py-1.5 text-sm text-ds-700 hover:bg-ds-50">
              Desligar WhatsApp
            </button>
          ) : (
            <>
              <button onClick={connect} disabled={busy} className="btn-primary">
                {busy ? 'A preparar …' : qr ? 'Gerar novo QR' : 'Ligar WhatsApp'}
              </button>

              {qr && (
                <div className="space-y-2">
                  <p className="text-sm text-ink-600">
                    No telemóvel: WhatsApp → <b>Dispositivos ligados</b> → <b>Ligar um dispositivo</b> e
                    leia o código abaixo. A página atualiza sozinha quando ligar.
                  </p>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={qrSrc(qr)} alt="QR code WhatsApp" className="h-56 w-56 rounded-lg border border-ink-100" />
                </div>
              )}
              {!qr && code && <p className="text-sm text-ink-600">Código de emparelhamento: <b>{code}</b></p>}
            </>
          )}

          {err && <p className="text-sm text-ds-700">{err}</p>}
        </div>
      )}
    </div>
  );
}
