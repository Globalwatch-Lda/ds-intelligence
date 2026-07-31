'use client';
import Link from 'next/link';
import {
  BrandCard,
  IconContacts,
  IconLeads,
  IconNewsletter,
  IconReport,
} from '@globalwatch-lda/synertia-ui';
import { IconDocScan } from '../components/icons';
import { BarraEstado } from '../components/Semaforos';
import { useMe } from '../lib/useMe';

// `cap` alinha o cartão com a entrada do menu: sem isto o cartão aparecia a quem
// o menu escondia, e clicar levava a uma página sem permissão.
const CARDS = [
  { href: '/contactos', title: 'Contactos', desc: 'Lista e gestão de contactos', color: '#7c3aed', icon: <IconContacts className="h-9 w-9" /> },
  { href: '/leads', title: 'Leads', desc: 'Captação e reativação', color: '#3b6cf0', icon: <IconLeads className="h-9 w-9" /> },
  { href: '/newsletter', title: 'Newsletter', desc: 'Comunicação aos clientes', color: '#14b8a6', icon: <IconNewsletter className="h-9 w-9" /> },
  { href: '/recap', title: 'Recap semanal', desc: 'Resumo para coordenadores', color: '#6366f1', icon: <IconReport className="h-9 w-9" /> },
  { href: '/analise-documental', title: 'Análise documental', desc: 'Deteção de sinais de fraude', color: '#a91b60', icon: <IconDocScan className="h-9 w-9" />, cap: 'page.analise_documental' },
];

export default function Welcome() {
  const { caps, me } = useMe();
  // Enquanto /me não carrega mostra-se tudo, para não piscar cartões a quem os tem.
  const visiveis = CARDS.filter((c) => !c.cap || !me?.capabilities || caps.has(c.cap));
  return (
    <div className="min-h-[80vh] flex flex-col items-center justify-center text-center py-8">
      <img src="/ds-logo.svg" alt="DS Crédito" className="h-20 w-20 mb-6" />
      <h1 className="text-3xl md:text-4xl font-semibold text-ink-900">
        Bem-vindo à DS Matrix
      </h1>

      {/* Texto do Dashboard — entre o título e o botão de entrada. */}
      <p className="mt-4 max-w-2xl text-ink-400">
        Monitorize a atividade global da agência em tempo real. Acompanhe a
        sincronização com o CRM, pesquise datas-chave e consulte alertas urgentes
        de prazos e aniversários.
      </p>

      <div className="mt-8 flex justify-center">
        <Link href="/dashboard" className="btn-primary text-base px-6 py-3">
          Entrar no Dashboard →
        </Link>
      </div>

      {/* Estado real dos serviços de que a plataforma depende. */}
      <BarraEstado className="mt-6 justify-center" />

      <div className="mt-20 grid grid-cols-2 md:grid-cols-4 gap-6 w-full max-w-6xl mx-auto">
        {visiveis.map((c) => (
          <BrandCard key={c.href} href={c.href} title={c.title} desc={c.desc} color={c.color} icon={c.icon} />
        ))}
      </div>
    </div>
  );
}
