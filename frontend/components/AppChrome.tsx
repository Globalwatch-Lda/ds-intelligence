'use client';
import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import {
  SynertiaShell,
  type SynertiaConfig,
  IconContacts,
  IconDashboard,
  IconLeads,
  IconNewsletter,
  IconReport,
  VERSION as UI_VERSION,
} from '@globalwatch-lda/synertia-ui';
import ChatDock from './ChatDock';
import UserFooter from './UserFooter';
import { AboutDialog } from './AboutDialog';
import { useMe } from '../lib/useMe';
import { LOJA_NAME } from '../lib/loja';

// Which capability each nav destination requires (mirrors the backend catalog in
// backend/app/core/capabilities.py). A route with no entry here is always shown.
const PAGE_CAP: Record<string, string> = {
  '/contactos': 'page.contactos',
  '/dashboard': 'page.dashboard',
  '/leads': 'page.leads',
  '/newsletter': 'page.newsletter',
  '/recap': 'page.recap',
  '/clientes-live': 'page.crm_live',
  '/whatsapp': 'messaging.send',
};

// Inline chat-bubble icon for the WhatsApp nav item (avoids depending on a
// package icon export).
const IconWhatsApp = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-3.9-.9L3 21l1.9-5.6a8.5 8.5 0 0 1-.9-3.9A8.38 8.38 0 0 1 12.5 3 8.38 8.38 0 0 1 21 11.5z" />
  </svg>
);

// Versão: [plataforma].[pacote UI] build [git]. A plataforma está na v1; o git
// sha é injetado no build (NEXT_PUBLIC_BUILD_SHA, ver deploy.sh).
const BUILD_SHA = (process.env.NEXT_PUBLIC_BUILD_SHA ?? '').slice(0, 7);
const PLATFORM_VERSION = `1.${UI_VERSION}`;
const VERSION_LABEL = `${PLATFORM_VERSION}${BUILD_SHA ? ` build ${BUILD_SHA}` : ''}`;

// DS Matrix client tokens for the shared Synertia chrome. Only these change per
// platform; the navy chrome (responsive drawer + collapsible rail) lives in
// @globalwatch-lda/synertia-ui (>= 0.2.0).
const config: SynertiaConfig = {
  brandLogoSrc: '/logo-synertia.png',
  brandMarkSrc: '/logo-synertia-icon.png',
  clientLogoSrc: '/ds-logo.svg',
  productName: 'DS Matrix',
  clientName: LOJA_NAME,
  accent: '#a91b60',
  nav: [
    { href: '/contactos', label: 'Contactos', icon: <IconContacts /> },
    { href: '/dashboard', label: 'Dashboard', icon: <IconDashboard /> },
    { href: '/leads', label: 'Leads', icon: <IconLeads /> },
    { href: '/newsletter', label: 'Newsletter', icon: <IconNewsletter /> },
    { href: '/whatsapp', label: 'WhatsApp', icon: IconWhatsApp },
    { href: '/recap', label: 'Recap semanal', icon: <IconReport /> },
  ],
  liveLink: { href: '/clientes-live', label: 'CRM em direto' },
  fullWidthRoutes: ['/dashboard'],
};

export default function AppChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { me, caps } = useMe();
  const [aboutOpen, setAboutOpen] = useState(false);
  // Nome da loja (configurável na tab Loja) escreve no cabeçalho; cai no default
  // do config enquanto não carrega.
  const [lojaNome, setLojaNome] = useState<string | null>(null);
  useEffect(() => {
    fetch('/api/settings/loja')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d?.nome) setLojaNome(d.nome); })
      .catch(() => {});
  }, []);
  // Gate nav + live link by page capabilities. Until /me loads (capabilities
  // undefined) show everything, to avoid an empty-sidebar flash for full-access users.
  const hasCaps = !!me?.capabilities;
  const allow = (href: string) => !hasCaps || !PAGE_CAP[href] || caps.has(PAGE_CAP[href]);
  const nav = config.nav.filter((item) => allow(item.href));
  const liveLink = config.liveLink && allow(config.liveLink.href) ? config.liveLink : undefined;
  const cfg: SynertiaConfig = { ...config, nav, liveLink, clientName: lojaNome ?? config.clientName };
  return (
    <>
      <SynertiaShell
        config={cfg}
        brandSlot={
          <button
            type="button"
            onClick={() => setAboutOpen(true)}
            title="Sobre a DS Matrix"
            className="inline-block rounded-full border border-white/15 bg-white/10 px-2 py-0.5 text-[9px] font-semibold tracking-wider text-white/70 shadow-sm transition-colors hover:bg-white/20"
          >
            {VERSION_LABEL}
          </button>
        }
        userSlot={<UserFooter />}
      >
        {children}
      </SynertiaShell>
      {pathname !== '/login' && <ChatDock />}
      <AboutDialog
        open={aboutOpen}
        onClose={() => setAboutOpen(false)}
        platformVersion={PLATFORM_VERSION}
        buildSha={BUILD_SHA || undefined}
      />
    </>
  );
}
