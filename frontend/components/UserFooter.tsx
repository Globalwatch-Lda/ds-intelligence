'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { IconSettings, useSidebarCollapsed } from '@globalwatch-lda/synertia-ui';
import LogoutButton from './LogoutButton';
import { useMe } from '../lib/useMe';

// Sidebar footer: a "Configurações" link sitting directly ABOVE the user pill,
// then the pill itself (LogoutButton). In the collapsed desktop rail both shrink
// to icon-only, matching the nav items above.
export default function UserFooter() {
  const pathname = usePathname();
  const collapsed = useSidebarCollapsed();
  const { me, can } = useMe();
  const active = pathname === '/configuracoes' || pathname.startsWith('/configuracoes/');
  // Show Configurações only to users whose profile grants the page. Until /me
  // loads, show it (avoids a flash) — the page itself is capability-gated server-side.
  const showSettings = !me?.capabilities || can('page.configuracoes');

  return (
    <div className="flex flex-col gap-2">
      {showSettings && (
        <Link
          href="/configuracoes"
          title={collapsed ? 'Configurações' : undefined}
          className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
            collapsed ? 'lg:justify-center lg:px-0' : ''
          } ${
            active
              ? 'bg-white/15 text-white font-medium'
              : 'text-white/70 hover:text-white hover:bg-white/10'
          }`}
        >
          <IconSettings />
          <span className={collapsed ? 'lg:hidden' : ''}>Configurações</span>
        </Link>
      )}
      <LogoutButton />
    </div>
  );
}
