'use client';
import useSWR from 'swr';
import { api } from '../lib/api';

// Semáforos de estado dos serviços de que a plataforma depende.
//
// Substituem um ponto verde que estava PINTADO no HTML e nunca mudava. Um
// indicador que está sempre verde não informa — mente. Este teria ficado
// vermelho durante os dois dias de julho em que as ingestões do CRM falharam
// todas as noites sem ninguém dar por isso.
//
// Cada semáforo diz o que sabe e nada mais: o do CRM mede a FRESCURA do espelho
// (a página lê `clientes_real`, não o CrediDesk ao vivo), o do WhatsApp mede se a
// instância do utilizador está mesmo emparelhada.

type EstadoCrm = { estado: 'ok' | 'atrasado' | 'falhou' | 'sem_dados'; ok: boolean; detalhe?: string; horas?: number };
type EstadoWa = { configured: boolean; connected: boolean; state: string | null; erro?: string | null; numero?: string | null };

const CORES: Record<string, string> = {
  verde: 'bg-emerald-500',
  ambar: 'bg-amber-500',
  vermelho: 'bg-ds-600',
  cinza: 'bg-ink-300',
};

function Luz({ cor, rotulo, titulo, pulsar }: { cor: string; rotulo: string; titulo: string; pulsar?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5" title={titulo}>
      <span className={`inline-flex h-2 w-2 rounded-full ${CORES[cor]} ${pulsar ? 'animate-pulse' : ''}`} />
      <span className="text-xs text-ink-500">{rotulo}</span>
    </span>
  );
}

export function SemaforoCrm() {
  // 60s chega: o dado por trás muda uma vez por dia.
  const { data, error } = useSWR<EstadoCrm>('/api/crm-live/estado', api, { refreshInterval: 60000 });
  if (error) return <Luz cor="cinza" rotulo="CRM" titulo="Não foi possível ler o estado da sincronização." />;
  if (!data) return <Luz cor="cinza" rotulo="CRM" titulo="A verificar …" />;
  const cor = data.estado === 'ok' ? 'verde' : data.estado === 'atrasado' ? 'ambar' : 'vermelho';
  const rotulo = data.estado === 'ok' ? 'CRM sincronizado'
    : data.estado === 'atrasado' ? `CRM desatualizado${data.horas ? ` (${Math.round(data.horas)}h)` : ''}`
    : data.estado === 'falhou' ? 'CRM com falha' : 'CRM sem dados';
  return <Luz cor={cor} rotulo={rotulo} titulo={data.detalhe || rotulo} pulsar={data.estado === 'ok'} />;
}

export function SemaforoWhatsApp() {
  const { data, error } = useSWR<EstadoWa>('/api/messaging/whatsapp/status', api, { refreshInterval: 30000 });
  if (error) return null;                      // sem permissão de envio: não mostra nada
  if (!data) return <Luz cor="cinza" rotulo="WhatsApp" titulo="A verificar …" />;
  if (!data.configured) return <Luz cor="cinza" rotulo="WhatsApp não configurado" titulo="O canal Evolution não está configurado nesta loja." />;
  if (data.connected) {
    return <Luz cor="verde" rotulo="WhatsApp ligado" titulo={`Ligado${data.numero ? ` — +${data.numero}` : ''}.`} pulsar />;
  }
  return (
    <Luz
      cor="vermelho"
      rotulo="WhatsApp desligado"
      titulo={data.erro ? `Serviço indisponível: ${data.erro}` : 'O seu número não está ligado. Vá a WhatsApp → Ligar WhatsApp.'}
    />
  );
}

export function BarraEstado({ className = '' }: { className?: string }) {
  return (
    <div className={`flex flex-wrap items-center gap-x-5 gap-y-1 ${className}`}>
      <SemaforoCrm />
      <SemaforoWhatsApp />
    </div>
  );
}
