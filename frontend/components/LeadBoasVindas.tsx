'use client';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';

type Envio = {
  enviado_em: string;
  destinatario: string;
  entregue: boolean | null;
  erro: string | null;
  enviado_por: string | null;
};

type Preview = {
  lead: { id: string; nome: string; produto: string };
  destinatario: string;
  assunto: string;
  documentos: string[];
  html: string;
  consultor: string | null;
  envios: Envio[];
};

export function IconEnvelope({ className = '' }: { className?: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <path d="m22 7-10 6L2 7" />
    </svg>
  );
}

const fmt = (v: string) =>
  new Date(v).toLocaleString('pt-PT', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });

/**
 * Pré-visualização + envio do email de boas-vindas com a checklist de documentos
 * do produto negociado. Mostra-se SEMPRE o que vai sair antes de sair: é uma
 * comunicação a um cliente real e não há como a chamar de volta.
 */
export default function LeadBoasVindas({
  leadId,
  onClose,
  onEnviado,
}: {
  leadId: string;
  onClose: () => void;
  onEnviado: () => void;
}) {
  const [dados, setDados] = useState<Preview | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [resultado, setResultado] = useState<string | null>(null);

  async function carregar() {
    try {
      setDados(await api<Preview>(`/api/leads/${leadId}/boas-vindas`));
      setErro(null);
    } catch (e: any) {
      setErro(e.message);
    }
  }

  useEffect(() => { carregar(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [leadId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  async function enviar() {
    setEnviando(true);
    setResultado(null);
    try {
      const r = await api<{ entregue: boolean | null; erro: string | null; enfileirado: boolean }>(
        `/api/leads/${leadId}/boas-vindas`,
        { method: 'POST' },
      );
      setResultado(
        r.entregue
          ? 'Email enviado.'
          : r.erro
          ? `Ficou em fila — ${r.erro}. O envio será feito assim que o canal permitir.`
          : 'Email colocado em fila.',
      );
      await carregar();
      onEnviado();
    } catch (e: any) {
      setErro(e.message);
    } finally {
      setEnviando(false);
    }
  }

  const jaEnviado = !!dados?.envios?.length;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink-900/40 p-4"
         onClick={onClose}>
      <div className="mb-10 mt-10 w-[720px] max-w-full rounded-2xl bg-white shadow-2xl"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-4 border-b border-ink-100 px-5 py-4">
          <div>
            <div className="font-semibold text-ink-900">Email de boas-vindas</div>
            <div className="text-xs text-ink-400">
              {dados ? `${dados.lead.nome} · ${dados.lead.produto}` : 'A carregar…'}
            </div>
          </div>
          <button onClick={onClose} className="text-xl leading-none text-ink-400 hover:text-ds-600">×</button>
        </div>

        {erro && <p className="px-5 pt-3 text-sm text-ds-600">{erro}</p>}

        {dados && (
          <>
            <div className="space-y-1 border-b border-ink-100 px-5 py-3 text-sm">
              <div><span className="text-ink-400">Para:</span>{' '}
                {dados.destinatario
                  ? <span className="text-ink-900">{dados.destinatario}</span>
                  : <span className="text-ds-600">esta lead não tem email no CRM</span>}
              </div>
              <div><span className="text-ink-400">Assunto:</span> <span className="text-ink-900">{dados.assunto}</span></div>
              <div className="text-xs text-ink-400">
                Documentos incluídos: {dados.documentos.length} · assinado por {dados.consultor || 'loja'}
              </div>
            </div>

            {jaEnviado && (
              <div className="border-b border-ink-100 bg-ink-50/60 px-5 py-2 text-xs text-ink-700">
                Já enviado {fmt(dados.envios[0].enviado_em)}
                {dados.envios[0].entregue === false ? ' (não entregue)' : ''} — enviar outra vez repete a mensagem.
              </div>
            )}

            <div className="max-h-[50vh] overflow-y-auto bg-ink-50/40 px-5 py-4">
              {/* Pré-visualização do HTML tal como o cliente o recebe. O conteúdo é
                  gerado pelo nosso servidor a partir do catálogo de documentos,
                  não é texto livre de terceiros. */}
              <div className="rounded-xl border border-ink-100 bg-white p-3"
                   dangerouslySetInnerHTML={{ __html: dados.html }} />
            </div>

            <div className="flex items-center justify-between gap-4 px-5 py-4">
              <span className="text-xs text-ink-400">
                {resultado || 'Sai pela fila de envios da plataforma (com registo e cancelamento de subscrição).'}
              </span>
              <div className="flex gap-2">
                <button className="btn-ghost" onClick={onClose}>Fechar</button>
                <button className="btn-primary" disabled={enviando || !dados.destinatario} onClick={enviar}>
                  {enviando ? 'A enviar…' : jaEnviado ? 'Enviar novamente' : 'Enviar email'}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
